"""
Session Validator - Smart session health verification.

This module provides intelligent session validation that:
1. Checks session health BEFORE use (not after failure)
2. Validates cookies are present and not expired
3. Performs quick page check to confirm login status
4. Returns detailed validation result for decision making

Key principle: NO session is rejected without attempting validation.
Old and new accounts are treated equally - both get full validation.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class SessionStatus(Enum):
    """Session health status."""
    VALID = "valid"              # Session is healthy, ready to use
    NEEDS_RENEWAL = "needs_renewal"  # Cookies exist but may be stale
    EXPIRED = "expired"          # Session definitely expired
    INVALID_COOKIES = "invalid_cookies"  # Cookie format/structure issues
    NO_COOKIES = "no_cookies"    # No cookies available
    UNKNOWN = "unknown"          # Could not determine status


@dataclass
class ValidationResult:
    """Result of session validation."""
    
    status: SessionStatus
    is_usable: bool  # Can this session be used for operations?
    needs_login: bool  # Does this need login attempt?
    reason: str = ""
    details: Dict = field(default_factory=dict)
    validation_time: datetime = field(default_factory=datetime.now)
    
    def __str__(self):
        return f"ValidationResult({self.status.value}: {self.reason})"


class SessionValidator:
    """
    Validates session health before use.
    
    Validation strategy:
    1. Quick check: Cookie structure and expiry dates
    2. Live check: Navigate to Roblox and verify login status
    
    IMPORTANT: This validator does NOT reject old sessions.
    It only determines what action is needed (use directly, renew, or login).
    """
    
    # Required Roblox cookies for a valid session
    REQUIRED_COOKIES = [
        ".ROBLOSECURITY",  # Main authentication cookie
    ]
    
    # Optional but helpful cookies
    HELPFUL_COOKIES = [
        "RBXSessionTracker",
        "RBXEventTrackerV2",
    ]
    
    def __init__(self):
        self._cache: Dict[int, ValidationResult] = {}
        self._cache_ttl = 300  # 5 minutes cache
    
    async def validate(self, account, page=None) -> ValidationResult:
        """
        Validate an account's session.
        
        Args:
            account: Account object with cookies and credentials
            page: Optional Playwright page for live validation
            
        Returns:
            ValidationResult with status and recommendations
        """
        account_id = account.id if hasattr(account, 'id') else 0
        
        # Check cache first
        cached = self._get_cached(account_id)
        if cached:
            logger.debug(f"Using cached validation for account {account_id}")
            return cached
        
        logger.info(f"Validating session for account: {account.username}")
        
        # Step 1: Quick cookie check
        cookie_result = self._validate_cookies(account)
        
        if cookie_result.status == SessionStatus.NO_COOKIES:
            # No cookies - need full login, but account is still usable
            result = ValidationResult(
                status=SessionStatus.NO_COOKIES,
                is_usable=True,  # Can still login with credentials
                needs_login=True,
                reason="No session cookies found - will attempt login",
                details={"has_credentials": bool(account.password)}
            )
            logger.info(f"Account {account.username}: No cookies, login required")
            return result
        
        if cookie_result.status == SessionStatus.INVALID_COOKIES:
            # Bad cookie format - try to parse anyway
            result = ValidationResult(
                status=SessionStatus.INVALID_COOKIES,
                is_usable=True,
                needs_login=True,
                reason=cookie_result.reason,
                details=cookie_result.details
            )
            logger.warning(f"Account {account.username}: Invalid cookie format")
            return result
        
        # Step 2: If we have a page, do live validation
        if page:
            live_result = await self._validate_live(account, page)
            self._cache_result(account_id, live_result)
            return live_result
        
        # Step 3: Without page, make best guess from cookies
        if cookie_result.status == SessionStatus.VALID:
            result = ValidationResult(
                status=SessionStatus.NEEDS_RENEWAL,  # Need to verify with page
                is_usable=True,
                needs_login=False,
                reason="Cookies look valid - need page check to confirm",
                details=cookie_result.details
            )
        else:
            result = cookie_result
        
        self._cache_result(account_id, result)
        return result
    
    def _validate_cookies(self, account) -> ValidationResult:
        """Quick validation of cookie structure and expiry."""
        
        if not account.cookie:
            return ValidationResult(
                status=SessionStatus.NO_COOKIES,
                is_usable=True,
                needs_login=True,
                reason="No cookies stored for this account"
            )
        
        try:
            # Parse cookies
            if isinstance(account.cookie, str):
                cookies = json.loads(account.cookie)
            else:
                cookies = account.cookie
            
            if not isinstance(cookies, list):
                return ValidationResult(
                    status=SessionStatus.INVALID_COOKIES,
                    is_usable=True,
                    needs_login=True,
                    reason="Cookie data is not a list",
                    details={"cookie_type": type(cookies).__name__}
                )
            
            if len(cookies) == 0:
                return ValidationResult(
                    status=SessionStatus.NO_COOKIES,
                    is_usable=True,
                    needs_login=True,
                    reason="Cookie list is empty"
                )
            
            # Check for required cookies
            cookie_names = {c.get("name", "") for c in cookies}
            missing_required = []
            
            for required in self.REQUIRED_COOKIES:
                if required not in cookie_names:
                    missing_required.append(required)
            
            if missing_required:
                return ValidationResult(
                    status=SessionStatus.EXPIRED,
                    is_usable=True,
                    needs_login=True,
                    reason=f"Missing required cookies: {missing_required}",
                    details={"missing": missing_required, "present": list(cookie_names)}
                )
            
            # Check expiry of main auth cookie
            auth_cookie = next(
                (c for c in cookies if c.get("name") == ".ROBLOSECURITY"),
                None
            )
            
            if auth_cookie:
                expires = auth_cookie.get("expires", 0)
                if expires > 0:
                    expiry_time = datetime.fromtimestamp(expires)
                    now = datetime.now()
                    
                    if expiry_time < now:
                        return ValidationResult(
                            status=SessionStatus.EXPIRED,
                            is_usable=True,
                            needs_login=True,
                            reason="Authentication cookie has expired",
                            details={"expired_at": expiry_time.isoformat()}
                        )
                    
                    # Check if expiring soon (within 1 hour)
                    if expiry_time < now + timedelta(hours=1):
                        return ValidationResult(
                            status=SessionStatus.NEEDS_RENEWAL,
                            is_usable=True,
                            needs_login=False,
                            reason="Session expiring soon - recommend renewal",
                            details={"expires_at": expiry_time.isoformat()}
                        )
            
            # Cookies look good
            return ValidationResult(
                status=SessionStatus.VALID,
                is_usable=True,
                needs_login=False,
                reason="Cookies appear valid",
                details={"cookie_count": len(cookies)}
            )
            
        except json.JSONDecodeError as e:
            return ValidationResult(
                status=SessionStatus.INVALID_COOKIES,
                is_usable=True,
                needs_login=True,
                reason=f"Could not parse cookie JSON: {e}",
                details={"error": str(e)}
            )
        except Exception as e:
            return ValidationResult(
                status=SessionStatus.UNKNOWN,
                is_usable=True,
                needs_login=True,
                reason=f"Cookie validation error: {e}",
                details={"error": str(e)}
            )
    
    async def _validate_live(self, account, page) -> ValidationResult:
        """
        Live validation by checking actual login status on Roblox.
        
        This is the most accurate check but requires a page.
        """
        try:
            # First apply cookies if available
            if account.cookie:
                try:
                    cookies = json.loads(account.cookie) if isinstance(account.cookie, str) else account.cookie
                    await page.context.add_cookies(cookies)
                    logger.debug(f"Applied {len(cookies)} cookies for {account.username}")
                except Exception as e:
                    logger.warning(f"Could not apply cookies: {e}")
            
            # Navigate to home page to check login status
            await page.goto("https://www.roblox.com/home", wait_until='domcontentloaded')
            await asyncio.sleep(2)
            
            # Check for login indicators
            logged_in = await self._check_logged_in(page)
            
            if logged_in:
                logger.info(f"Account {account.username}: Session VALID (live check)")
                return ValidationResult(
                    status=SessionStatus.VALID,
                    is_usable=True,
                    needs_login=False,
                    reason="Live check confirmed: user is logged in",
                    details={"method": "live_check"}
                )
            else:
                # Not logged in - cookies may be expired
                logger.info(f"Account {account.username}: Session EXPIRED (live check)")
                return ValidationResult(
                    status=SessionStatus.EXPIRED,
                    is_usable=True,
                    needs_login=True,
                    reason="Live check: not logged in despite cookies",
                    details={"method": "live_check"}
                )
                
        except Exception as e:
            logger.error(f"Live validation error for {account.username}: {e}")
            return ValidationResult(
                status=SessionStatus.UNKNOWN,
                is_usable=True,
                needs_login=True,
                reason=f"Live validation failed: {e}",
                details={"error": str(e)}
            )
    
    async def _check_logged_in(self, page) -> bool:
        """Check if we're logged in on the current page."""
        
        # Multiple indicators of being logged in
        logged_in_selectors = [
            "#nav-profile",  # Profile icon in nav
            ".age-bracket-label",  # Age bracket shown
            "[data-testid='user-avatar']",  # User avatar
            ".authenticated-user",  # Auth user class
        ]
        
        # Indicators of NOT being logged in
        logged_out_selectors = [
            "#login-button",
            ".login-button",
            "a[href='/login']",
        ]
        
        # Check for logged-in indicators
        for selector in logged_in_selectors:
            try:
                element = await page.query_selector(selector)
                if element and await element.is_visible():
                    return True
            except:
                continue
        
        # Check for logged-out indicators
        for selector in logged_out_selectors:
            try:
                element = await page.query_selector(selector)
                if element and await element.is_visible():
                    return False
            except:
                continue
        
        # Check URL - if redirected to login, not logged in
        current_url = page.url
        if "/login" in current_url or "login" in current_url.lower():
            return False
        
        # Default to unknown - treat as needing verification
        return False
    
    def _get_cached(self, account_id: int) -> Optional[ValidationResult]:
        """Get cached validation result if still valid."""
        if account_id in self._cache:
            result = self._cache[account_id]
            age = (datetime.now() - result.validation_time).total_seconds()
            if age < self._cache_ttl:
                return result
            else:
                del self._cache[account_id]
        return None
    
    def _cache_result(self, account_id: int, result: ValidationResult):
        """Cache a validation result."""
        self._cache[account_id] = result
    
    def invalidate_cache(self, account_id: int = None):
        """Invalidate cache for a specific account or all."""
        if account_id:
            self._cache.pop(account_id, None)
        else:
            self._cache.clear()
    
    def get_validation_summary(self) -> Dict:
        """Get summary of all cached validations."""
        summary = {
            "total_cached": len(self._cache),
            "by_status": {}
        }
        
        for result in self._cache.values():
            status = result.status.value
            summary["by_status"][status] = summary["by_status"].get(status, 0) + 1
        
        return summary
