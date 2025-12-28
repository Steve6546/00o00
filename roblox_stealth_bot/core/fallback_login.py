"""
Fallback Login - Complete re-login system for failed sessions.

This is the LAST line of defense when:
1. Session validation fails
2. Session renewal fails

This module performs a full human-like login:
1. Navigate to login page
2. Fill username and password
3. Handle CAPTCHA if needed
4. Save new cookies on success

Key principle: Never give up on an account without trying full login.
Even accounts with expired/corrupt cookies might just need a fresh login.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, Dict
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class LoginStatus(Enum):
    """Result of login attempt."""
    SUCCESS = "success"
    FAILED = "failed"
    CAPTCHA_REQUIRED = "captcha_required"
    INVALID_CREDENTIALS = "invalid_credentials"
    ACCOUNT_LOCKED = "account_locked"
    NETWORK_ERROR = "network_error"


@dataclass
class LoginResult:
    """Result of fallback login attempt."""
    
    status: LoginStatus
    success: bool
    reason: str = ""
    new_cookies: Optional[str] = None
    requires_manual: bool = False
    details: Dict = field(default_factory=dict)
    
    def __str__(self):
        return f"LoginResult({self.status.value}: {self.reason})"


class FallbackLogin:
    """
    Performs full re-login when session renewal fails.
    
    This is the self-healing mechanism that allows old accounts
    to come back to life. Even if cookies are completely dead,
    we can still login with credentials.
    
    Login flow:
    1. Navigate to login page
    2. Fill credentials with human-like behavior
    3. Handle CAPTCHA if it appears
    4. Verify login success
    5. Save new cookies
    """
    
    def __init__(self, captcha_manager=None, human_input=None):
        self.captcha_manager = captcha_manager
        self.human_input = human_input
        
        # Track login attempts per account
        self._login_attempts: Dict[int, int] = {}
        self._max_attempts = 3
    
    async def login(self, account, page) -> LoginResult:
        """
        Attempt full login with credentials.
        
        Args:
            account: Account object with username and password
            page: Playwright page
            
        Returns:
            LoginResult with status and new cookies if successful
        """
        account_id = account.id if hasattr(account, 'id') else 0
        
        # Check attempt limit
        attempts = self._login_attempts.get(account_id, 0)
        if attempts >= self._max_attempts:
            logger.warning(f"Max login attempts reached for {account.username}")
            return LoginResult(
                status=LoginStatus.FAILED,
                success=False,
                reason="Max login attempts exceeded",
                requires_manual=True
            )
        
        self._login_attempts[account_id] = attempts + 1
        
        logger.info(f"Attempting fallback login for: {account.username}")
        
        # Check if we have credentials
        if not account.password:
            return LoginResult(
                status=LoginStatus.INVALID_CREDENTIALS,
                success=False,
                reason="No password stored for account",
                requires_manual=True
            )
        
        try:
            # Clear any existing cookies to start fresh
            await page.context.clear_cookies()
            
            # Navigate to login page
            await page.goto("https://www.roblox.com/login", wait_until='domcontentloaded')
            await asyncio.sleep(2)
            
            # Fill login form
            result = await self._fill_login_form(account, page)
            if not result.success:
                return result
            
            # Submit and wait
            await self._submit_login(page)
            await asyncio.sleep(5)
            
            # Check for CAPTCHA
            if await self._has_captcha(page):
                logger.info(f"CAPTCHA detected for {account.username}")
                
                if self.captcha_manager:
                    solved = await self.captcha_manager.solve(page, timeout=120)
                    if solved:
                        logger.info("CAPTCHA solved, verifying login...")
                        await asyncio.sleep(3)
                    else:
                        return LoginResult(
                            status=LoginStatus.CAPTCHA_REQUIRED,
                            success=False,
                            reason="CAPTCHA solving failed",
                            requires_manual=True
                        )
                else:
                    return LoginResult(
                        status=LoginStatus.CAPTCHA_REQUIRED,
                        success=False,
                        reason="CAPTCHA detected but no solver available",
                        requires_manual=True
                    )
            
            # Check for login errors
            error = await self._check_login_error(page)
            if error:
                return self._handle_login_error(error, account)
            
            # Verify we're logged in
            if await self._verify_logged_in(page):
                # Get and save cookies
                cookies = await page.context.cookies()
                cookies_json = json.dumps(cookies)
                
                # Save to account
                await self._save_cookies(account, cookies_json)
                
                # Reset attempt counter
                self._login_attempts[account_id] = 0
                
                logger.info(f"Fallback login SUCCESS for {account.username}")
                
                return LoginResult(
                    status=LoginStatus.SUCCESS,
                    success=True,
                    reason="Login successful",
                    new_cookies=cookies_json,
                    details={"cookie_count": len(cookies)}
                )
            else:
                return LoginResult(
                    status=LoginStatus.FAILED,
                    success=False,
                    reason="Login completed but not verified as logged in"
                )
                
        except Exception as e:
            logger.error(f"Fallback login error for {account.username}: {e}")
            return LoginResult(
                status=LoginStatus.NETWORK_ERROR,
                success=False,
                reason=f"Login error: {e}",
                details={"error": str(e)}
            )
    
    async def _fill_login_form(self, account, page) -> LoginResult:
        """Fill the login form with credentials."""
        try:
            # Find and fill username
            username_selectors = [
                "#login-username",
                "input[name='username']",
                "#username",
            ]
            
            username_filled = False
            for selector in username_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element and await element.is_visible():
                        await element.click()
                        await asyncio.sleep(0.2)
                        await element.fill(account.username)
                        username_filled = True
                        break
                except:
                    continue
            
            if not username_filled:
                return LoginResult(
                    status=LoginStatus.FAILED,
                    success=False,
                    reason="Could not find username field"
                )
            
            await asyncio.sleep(0.5)
            
            # Find and fill password
            password_selectors = [
                "#login-password",
                "input[name='password']",
                "#password",
                "input[type='password']",
            ]
            
            password_filled = False
            for selector in password_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element and await element.is_visible():
                        await element.click()
                        await asyncio.sleep(0.2)
                        await element.fill(account.password)
                        password_filled = True
                        break
                except:
                    continue
            
            if not password_filled:
                return LoginResult(
                    status=LoginStatus.FAILED,
                    success=False,
                    reason="Could not find password field"
                )
            
            return LoginResult(
                status=LoginStatus.SUCCESS,
                success=True,
                reason="Form filled"
            )
            
        except Exception as e:
            return LoginResult(
                status=LoginStatus.FAILED,
                success=False,
                reason=f"Form filling error: {e}"
            )
    
    async def _submit_login(self, page):
        """Submit the login form."""
        submit_selectors = [
            "#login-button",
            "button[type='submit']",
            ".login-button",
            "button:has-text('Log In')",
        ]
        
        for selector in submit_selectors:
            try:
                button = await page.query_selector(selector)
                if button and await button.is_visible():
                    await button.click()
                    return
            except:
                continue
        
        # Fallback: try pressing Enter
        await page.keyboard.press("Enter")
    
    async def _has_captcha(self, page) -> bool:
        """Check if CAPTCHA is present."""
        captcha_selectors = [
            "iframe[src*='funcaptcha']",
            "iframe[src*='captcha']",
            "#captcha-container",
            ".captcha-wrapper",
            "[data-testid='captcha']",
        ]
        
        for selector in captcha_selectors:
            try:
                element = await page.query_selector(selector)
                if element and await element.is_visible():
                    return True
            except:
                continue
        
        return False
    
    async def _check_login_error(self, page) -> Optional[str]:
        """Check for login error messages."""
        error_selectors = [
            ".alert-error",
            ".login-error",
            "#login-error",
            ".text-error",
            "[data-testid='login-error']",
        ]
        
        for selector in error_selectors:
            try:
                element = await page.query_selector(selector)
                if element and await element.is_visible():
                    text = await element.inner_text()
                    if text and text.strip():
                        return text.strip()
            except:
                continue
        
        return None
    
    def _handle_login_error(self, error: str, account) -> LoginResult:
        """Handle specific login errors."""
        error_lower = error.lower()
        
        if "incorrect" in error_lower or "invalid" in error_lower:
            return LoginResult(
                status=LoginStatus.INVALID_CREDENTIALS,
                success=False,
                reason=f"Invalid credentials: {error}",
                requires_manual=True,
                details={"error_message": error}
            )
        
        if "locked" in error_lower or "banned" in error_lower:
            return LoginResult(
                status=LoginStatus.ACCOUNT_LOCKED,
                success=False,
                reason=f"Account locked/banned: {error}",
                requires_manual=True,
                details={"error_message": error}
            )
        
        return LoginResult(
            status=LoginStatus.FAILED,
            success=False,
            reason=f"Login error: {error}",
            details={"error_message": error}
        )
    
    async def _verify_logged_in(self, page) -> bool:
        """Verify that we're logged in."""
        # Check URL - should be redirected away from login
        current_url = page.url
        if "/login" in current_url.lower():
            return False
        
        # Check for logged-in indicators
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
        
        # Check if on home page
        if "/home" in current_url.lower():
            return True
        
        return False
    
    async def _save_cookies(self, account, cookies_json: str):
        """Save new cookies to account."""
        try:
            if hasattr(account, 'cookie'):
                account.cookie = cookies_json
                if hasattr(account, 'save'):
                    account.save()
                    logger.debug(f"Saved new login cookies for {account.username}")
        except Exception as e:
            logger.warning(f"Could not save login cookies: {e}")
    
    def reset_attempts(self, account_id: int = None):
        """Reset login attempt counter."""
        if account_id:
            self._login_attempts.pop(account_id, None)
        else:
            self._login_attempts.clear()
    
    def get_attempt_count(self, account_id: int) -> int:
        """Get number of login attempts for an account."""
        return self._login_attempts.get(account_id, 0)
