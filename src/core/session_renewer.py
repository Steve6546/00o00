"""
Session Renewer - Automatic session renewal system.

This module attempts to renew expired sessions WITHOUT full login.
Renewal strategies:
1. Page refresh with existing cookies
2. Navigate to session-refresh endpoints
3. Trigger cookie refresh via site interaction

Only if all renewal attempts fail do we escalate to full login.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, Dict
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class RenewalStatus(Enum):
    """Result of renewal attempt."""
    SUCCESS = "success"        # Session renewed successfully
    FAILED = "failed"          # Renewal failed, need full login
    PARTIAL = "partial"        # Some renewal happened, may work
    NOT_NEEDED = "not_needed"  # Session was already valid


@dataclass
class RenewalResult:
    """Result of session renewal attempt."""
    
    status: RenewalStatus
    success: bool
    method_used: str = ""
    reason: str = ""
    new_cookies: Optional[str] = None
    details: Dict = field(default_factory=dict)
    
    def __str__(self):
        return f"RenewalResult({self.status.value}: {self.reason})"


class SessionRenewer:
    """
    Attempts to renew expired sessions.
    
    This is the SECOND line of defense after validation fails.
    Before falling back to full login, we try non-intrusive renewal.
    
    Priority principle: We never give up on an account easily.
    Old accounts deserve the same renewal attempts as new ones.
    """
    
    def __init__(self):
        self._renewal_attempts: Dict[int, int] = {}
        self._max_attempts = 3
    
    async def renew(self, account, page) -> RenewalResult:
        """
        Attempt to renew an account's session.
        
        Args:
            account: Account object
            page: Playwright page
            
        Returns:
            RenewalResult with success status
        """
        account_id = account.id if hasattr(account, 'id') else 0
        
        logger.info(f"Attempting session renewal for: {account.username}")
        
        # Track attempts
        attempts = self._renewal_attempts.get(account_id, 0)
        if attempts >= self._max_attempts:
            logger.warning(f"Max renewal attempts reached for {account.username}")
            return RenewalResult(
                status=RenewalStatus.FAILED,
                success=False,
                reason="Max renewal attempts exceeded"
            )
        
        self._renewal_attempts[account_id] = attempts + 1
        
        # Try renewal strategies in order
        strategies = [
            ("cookie_refresh", self._try_cookie_refresh),
            ("page_refresh", self._try_page_refresh),
            ("home_navigation", self._try_home_navigation),
            ("session_endpoint", self._try_session_endpoint),
        ]
        
        for strategy_name, strategy_func in strategies:
            try:
                logger.debug(f"Trying renewal strategy: {strategy_name}")
                result = await strategy_func(account, page)
                
                if result.success:
                    logger.info(f"Renewal SUCCESS via {strategy_name} for {account.username}")
                    # Reset attempt counter on success
                    self._renewal_attempts[account_id] = 0
                    
                    # Save new cookies if available
                    if result.new_cookies:
                        await self._save_cookies(account, result.new_cookies)
                    
                    return result
                    
            except Exception as e:
                logger.debug(f"Strategy {strategy_name} failed: {e}")
                continue
        
        # All strategies failed
        logger.warning(f"All renewal strategies failed for {account.username}")
        return RenewalResult(
            status=RenewalStatus.FAILED,
            success=False,
            reason="All renewal strategies exhausted",
            details={"attempts": attempts + 1}
        )
    
    async def _try_cookie_refresh(self, account, page) -> RenewalResult:
        """
        Try refreshing by re-applying cookies and checking.
        
        Sometimes cookies just need to be re-sent to the browser.
        """
        if not account.cookie:
            return RenewalResult(
                status=RenewalStatus.FAILED,
                success=False,
                reason="No cookies to refresh"
            )
        
        try:
            # Parse and re-apply cookies
            cookies = json.loads(account.cookie) if isinstance(account.cookie, str) else account.cookie
            
            # Clear existing cookies for Roblox
            await page.context.clear_cookies()
            
            # Re-add cookies
            await page.context.add_cookies(cookies)
            
            # Navigate to verify
            await page.goto("https://www.roblox.com/home", wait_until='domcontentloaded')
            await asyncio.sleep(2)
            
            # Check if logged in
            if await self._is_logged_in(page):
                # Get updated cookies
                new_cookies = await page.context.cookies()
                
                return RenewalResult(
                    status=RenewalStatus.SUCCESS,
                    success=True,
                    method_used="cookie_refresh",
                    reason="Cookies refreshed successfully",
                    new_cookies=json.dumps(new_cookies)
                )
            
            return RenewalResult(
                status=RenewalStatus.FAILED,
                success=False,
                reason="Cookie refresh did not restore session"
            )
            
        except Exception as e:
            return RenewalResult(
                status=RenewalStatus.FAILED,
                success=False,
                reason=f"Cookie refresh error: {e}"
            )
    
    async def _try_page_refresh(self, account, page) -> RenewalResult:
        """
        Try simple page refresh to trigger session renewal.
        
        Sometimes the session is valid but needs a refresh.
        """
        try:
            # Reload current page
            await page.reload(wait_until='domcontentloaded')
            await asyncio.sleep(2)
            
            if await self._is_logged_in(page):
                new_cookies = await page.context.cookies()
                
                return RenewalResult(
                    status=RenewalStatus.SUCCESS,
                    success=True,
                    method_used="page_refresh",
                    reason="Session restored via page refresh",
                    new_cookies=json.dumps(new_cookies)
                )
            
            return RenewalResult(
                status=RenewalStatus.FAILED,
                success=False,
                reason="Page refresh did not restore session"
            )
            
        except Exception as e:
            return RenewalResult(
                status=RenewalStatus.FAILED,
                success=False,
                reason=f"Page refresh error: {e}"
            )
    
    async def _try_home_navigation(self, account, page) -> RenewalResult:
        """
        Navigate to home page to trigger session check.
        """
        try:
            await page.goto("https://www.roblox.com/home", wait_until='networkidle')
            await asyncio.sleep(3)
            
            if await self._is_logged_in(page):
                new_cookies = await page.context.cookies()
                
                return RenewalResult(
                    status=RenewalStatus.SUCCESS,
                    success=True,
                    method_used="home_navigation",
                    reason="Session valid after home navigation",
                    new_cookies=json.dumps(new_cookies)
                )
            
            return RenewalResult(
                status=RenewalStatus.FAILED,
                success=False,
                reason="Not logged in after home navigation"
            )
            
        except Exception as e:
            return RenewalResult(
                status=RenewalStatus.FAILED,
                success=False,
                reason=f"Home navigation error: {e}"
            )
    
    async def _try_session_endpoint(self, account, page) -> RenewalResult:
        """
        Try hitting known session refresh endpoints.
        """
        try:
            # These endpoints sometimes refresh the session
            refresh_urls = [
                "https://www.roblox.com/my/account",
                "https://www.roblox.com/my/account#!/info",
            ]
            
            for url in refresh_urls:
                try:
                    await page.goto(url, wait_until='domcontentloaded')
                    await asyncio.sleep(2)
                    
                    if await self._is_logged_in(page):
                        new_cookies = await page.context.cookies()
                        
                        return RenewalResult(
                            status=RenewalStatus.SUCCESS,
                            success=True,
                            method_used="session_endpoint",
                            reason=f"Session refreshed via {url}",
                            new_cookies=json.dumps(new_cookies)
                        )
                except:
                    continue
            
            return RenewalResult(
                status=RenewalStatus.FAILED,
                success=False,
                reason="Session endpoints did not restore session"
            )
            
        except Exception as e:
            return RenewalResult(
                status=RenewalStatus.FAILED,
                success=False,
                reason=f"Session endpoint error: {e}"
            )
    
    async def _is_logged_in(self, page) -> bool:
        """Check if currently logged in."""
        
        # Positive indicators
        logged_in_selectors = [
            "#nav-profile",
            ".age-bracket-label",
            "[data-testid='user-avatar']",
        ]
        
        for selector in logged_in_selectors:
            try:
                element = await page.query_selector(selector)
                if element and await element.is_visible():
                    return True
            except:
                continue
        
        # Check URL
        if "/login" in page.url.lower():
            return False
        
        return False
    
    async def _save_cookies(self, account, cookies_json: str):
        """Save new cookies to database."""
        try:
            # Update account cookie in database
            if hasattr(account, 'cookie'):
                account.cookie = cookies_json
                if hasattr(account, 'save'):
                    account.save()
                    logger.debug(f"Saved renewed cookies for {account.username}")
        except Exception as e:
            logger.warning(f"Could not save renewed cookies: {e}")
    
    def reset_attempts(self, account_id: int = None):
        """Reset renewal attempt counter."""
        if account_id:
            self._renewal_attempts.pop(account_id, None)
        else:
            self._renewal_attempts.clear()
    
    def get_attempt_count(self, account_id: int) -> int:
        """Get number of renewal attempts for an account."""
        return self._renewal_attempts.get(account_id, 0)
