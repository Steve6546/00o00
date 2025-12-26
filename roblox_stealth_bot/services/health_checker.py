"""
Account Health Checker - Verifies account status and detects banned accounts.

Features:
- Login verification
- Ban detection
- Batch health checks
- Auto-update account status
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Dict
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Account health status."""
    ACTIVE = "active"
    BANNED = "banned"
    SUSPENDED = "suspended"
    CAPTCHA_REQUIRED = "captcha_required"
    LOGIN_FAILED = "login_failed"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """Result of a health check."""
    status: HealthStatus
    message: str
    checked_at: datetime
    details: Optional[Dict] = None


class AccountHealthChecker:
    """
    Checks account health by attempting login and detecting ban messages.
    
    Usage:
        checker = AccountHealthChecker(browser)
        result = await checker.check_account(account)
    """
    
    # Ban detection indicators
    BAN_INDICATORS = [
        "account has been banned",
        "account has been terminated",
        "account has been suspended",
        "you have been banned",
        "account deleted",
        "moderated",
        "this account is unavailable"
    ]
    
    def __init__(self, browser_context=None):
        self.browser = browser_context
        self.results_cache: Dict[str, HealthCheckResult] = {}
    
    async def check_account(self, account, page=None) -> HealthCheckResult:
        """
        Check health of a single account.
        
        Args:
            account: Account model instance
            page: Optional Playwright page (creates new if not provided)
        """
        logger.info(f"Checking health: {account.username}")
        
        try:
            # If we have a browser, try to login
            if self.browser and page:
                return await self._check_with_login(account, page)
            else:
                # Without browser, just check database status
                return self._check_database_status(account)
                
        except Exception as e:
            logger.error(f"Health check failed for {account.username}: {e}")
            return HealthCheckResult(
                status=HealthStatus.UNKNOWN,
                message=str(e),
                checked_at=datetime.now()
            )
    
    async def _check_with_login(self, account, page) -> HealthCheckResult:
        """Check account by attempting login."""
        try:
            # Navigate to login page
            await page.goto("https://www.roblox.com/login", wait_until="networkidle")
            await asyncio.sleep(2)
            
            # Check for ban messages on the page
            page_text = await page.content()
            for indicator in self.BAN_INDICATORS:
                if indicator.lower() in page_text.lower():
                    return HealthCheckResult(
                        status=HealthStatus.BANNED,
                        message=f"Ban indicator found: {indicator}",
                        checked_at=datetime.now()
                    )
            
            # Try cookie-based login if available
            if account.cookie:
                # Check if already logged in
                if "home" in page.url.lower() or await page.query_selector('[data-testid="user-menu"]'):
                    return HealthCheckResult(
                        status=HealthStatus.ACTIVE,
                        message="Account is active (logged in)",
                        checked_at=datetime.now()
                    )
            
            # Try credential login
            username_input = await page.query_selector("#login-username")
            if username_input:
                await username_input.fill(account.username)
                
                password_input = await page.query_selector("#login-password")
                if password_input:
                    await password_input.fill(account.password)
                    
                    # Click login button
                    login_btn = await page.query_selector("#login-button")
                    if login_btn:
                        await login_btn.click()
                        await asyncio.sleep(3)
                        
                        # Check result
                        page_text = await page.content()
                        
                        for indicator in self.BAN_INDICATORS:
                            if indicator.lower() in page_text.lower():
                                return HealthCheckResult(
                                    status=HealthStatus.BANNED,
                                    message=f"Ban detected after login: {indicator}",
                                    checked_at=datetime.now()
                                )
                        
                        if "captcha" in page_text.lower():
                            return HealthCheckResult(
                                status=HealthStatus.CAPTCHA_REQUIRED,
                                message="CAPTCHA required",
                                checked_at=datetime.now()
                            )
                        
                        if "home" in page.url.lower():
                            return HealthCheckResult(
                                status=HealthStatus.ACTIVE,
                                message="Login successful",
                                checked_at=datetime.now()
                            )
            
            return HealthCheckResult(
                status=HealthStatus.LOGIN_FAILED,
                message="Could not verify login",
                checked_at=datetime.now()
            )
            
        except Exception as e:
            return HealthCheckResult(
                status=HealthStatus.UNKNOWN,
                message=f"Check failed: {e}",
                checked_at=datetime.now()
            )
    
    def _check_database_status(self, account) -> HealthCheckResult:
        """Check account status from database only."""
        if account.is_banned or account.status == "banned":
            return HealthCheckResult(
                status=HealthStatus.BANNED,
                message="Marked as banned in database",
                checked_at=datetime.now()
            )
        
        if account.status == "suspended":
            return HealthCheckResult(
                status=HealthStatus.SUSPENDED,
                message="Marked as suspended",
                checked_at=datetime.now()
            )
        
        return HealthCheckResult(
            status=HealthStatus.ACTIVE,
            message=f"Status: {account.status}",
            checked_at=datetime.now()
        )
    
    async def check_all_accounts(self, db_manager, update_db: bool = True) -> List[Dict]:
        """
        Check all accounts in database.
        
        Args:
            db_manager: DatabaseManager instance
            update_db: Whether to update account status in database
            
        Returns:
            List of results
        """
        from data.database import Account
        
        accounts = Account.select()
        results = []
        
        for account in accounts:
            result = await self.check_account(account)
            
            results.append({
                "username": account.username,
                "status": result.status.value,
                "message": result.message,
                "checked_at": result.checked_at
            })
            
            if update_db:
                account.last_health_check = result.checked_at
                account.is_banned = result.status == HealthStatus.BANNED
                if result.status == HealthStatus.BANNED:
                    account.status = "banned"
                account.save()
            
            # Small delay between checks
            await asyncio.sleep(0.5)
        
        return results


def get_account_summary(db_manager) -> Dict:
    """Get summary of all accounts without browser."""
    from data.database import Account, FollowRecord
    
    accounts = Account.select()
    
    summary = {
        "total": accounts.count(),
        "active": accounts.where(Account.status == "active").count(),
        "banned": accounts.where(Account.is_banned == True).count(),
        "male": accounts.where(Account.gender == "male").count(),
        "female": accounts.where(Account.gender == "female").count(),
        "accounts": []
    }
    
    for account in accounts:
        follows = FollowRecord.select().where(FollowRecord.account == account)
        
        summary["accounts"].append({
            "username": account.username,
            "gender": account.gender or "unknown",
            "status": account.status,
            "is_banned": account.is_banned,
            "follow_count": follows.count(),
            "created_at": account.created_at.strftime("%Y-%m-%d") if account.created_at else None,
            "last_health_check": account.last_health_check.strftime("%Y-%m-%d %H:%M") if account.last_health_check else None
        })
    
    return summary


def get_account_details(username: str) -> Optional[Dict]:
    """Get detailed info for a specific account."""
    from data.database import Account, FollowRecord
    
    try:
        account = Account.get(Account.username == username)
    except:
        return None
    
    follows = FollowRecord.select().where(FollowRecord.account == account)
    
    return {
        "username": account.username,
        "password": account.password,
        "gender": account.gender or "unknown",
        "birthday": str(account.birthday),
        "status": account.status,
        "is_banned": account.is_banned,
        "created_at": str(account.created_at),
        "last_used": str(account.last_used) if account.last_used else None,
        "last_health_check": str(account.last_health_check) if account.last_health_check else None,
        "follow_count": follows.count(),
        "follows": [
            {
                "target_id": f.target_id,
                "target_username": f.target_username,
                "followed_at": str(f.followed_at),
                "verified": f.verified
            }
            for f in follows
        ]
    }
