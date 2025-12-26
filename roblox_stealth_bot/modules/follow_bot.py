import asyncio
import logging
import time
from playwright.async_api import Page, BrowserContext
from behavior.interaction import Interaction
from data.database import DatabaseManager, Account

logger = logging.getLogger(__name__)


class FollowBot:
    """
    Handles logging into accounts and performing follow actions.
    Supports cookie-based login and handles various UI states.
    """
    
    def __init__(self, session_manager, db_manager: DatabaseManager):
        self.session_manager = session_manager
        self.db = db_manager
        self.rate_limit_seconds = 30  # Minimum delay between follows

    async def follow_user(self, target_user_id: str, account_id: int = None) -> bool:
        """
        Logs in with a saved account and follows the target user.
        
        Args:
            target_user_id: The Roblox user ID to follow
            account_id: Specific account to use (optional, will pick best available if not specified)
            
        Returns:
            True if follow was successful
        """
        start_time = time.time()
        
        # 1. Fetch Account
        if account_id:
            account = Account.get_by_id(account_id)
        else:
            # Try to get least-used account first
            account = self.db.get_account_by_least_used()
            if not account:
                account = self.db.get_active_account()

        if not account:
            logger.error("No active account found in database.")
            self.db.log_task('follow', 'failed', target=target_user_id, 
                           error_message="No active account available")
            return False

        logger.info(f"Using account: {account.username} to follow {target_user_id}")
        
        # 2. Setup Browser
        context, page = await self.session_manager.create_context(proxy=None)
        interaction = Interaction(page)

        try:
            # 3. Login
            login_success = await self._login(page, interaction, account)
            if not login_success:
                logger.error("Login failed")
                self.db.log_task('follow', 'failed', target=target_user_id,
                               account_id=account.id, error_message="Login failed")
                return False
            
            logger.info("Login successful. Navigating to target user profile...")
            
            # 4. Navigate to Profile
            profile_url = f"https://www.roblox.com/users/{target_user_id}/profile"
            await page.goto(profile_url, wait_until='domcontentloaded')
            await interaction.random_pause(2, 4)
            
            # 5. Simulate browsing behavior before following
            await interaction.wander(duration_seconds=random.randint(3, 8))
            await interaction.human_input.scroll.scroll_natural('down', random.randint(200, 400))
            await interaction.random_pause(1, 3)

            # 6. Click Follow
            follow_success = await self._click_follow_button(page, interaction)
            
            duration = time.time() - start_time
            
            if follow_success:
                logger.info("Follow action completed successfully.")
                self.db.increment_follow_count(account.id)
                self.db.log_task('follow', 'success', target=target_user_id,
                               account_id=account.id, duration_seconds=duration)
                
                # Set cooldown to prevent rapid usage
                self.db.set_account_cooldown(account.id, minutes=random.randint(15, 45))
                return True
            else:
                logger.warning("Follow action may have failed.")
                self.db.log_task('follow', 'failed', target=target_user_id,
                               account_id=account.id, error_message="Failed to click follow button")
                return False

        except Exception as e:
            logger.error(f"Follow task failed: {e}")
            self.db.log_task('follow', 'failed', target=target_user_id,
                           account_id=account.id if account else None, 
                           error_message=str(e))
            return False
        finally:
            await self.session_manager.close_context(context)

    async def _login(self, page: Page, interaction: Interaction, account: Account) -> bool:
        """
        Attempts to log in with the given account.
        Tries cookie-based login first if available.
        """
        # Try cookie-based login first if cookie is stored
        if account.cookie:
            logger.info("Attempting cookie-based login...")
            try:
                # Parse and set cookies
                await self._set_cookies(page.context, account.cookie)
                await page.goto("https://www.roblox.com/home", wait_until='domcontentloaded')
                await asyncio.sleep(3)
                
                # Check if logged in
                if "login" not in page.url.lower():
                    profile_link = await page.query_selector('#nav-profile, .age-bracket-label')
                    if profile_link:
                        logger.info("Cookie login successful!")
                        return True
            except Exception as e:
                logger.warning(f"Cookie login failed: {e}")
        
        # Fall back to username/password login
        logger.info("Performing username/password login...")
        await page.goto("https://www.roblox.com/login", wait_until='domcontentloaded')
        await interaction.random_pause(1, 2)
        
        # Warm up before entering credentials
        await interaction._idle_movements()
        
        # Fill login form
        username_input = page.get_by_placeholder("Username")
        if await username_input.count() > 0:
            await interaction.human_input.type_humanlike(username_input, account.username)
        else:
            await interaction.human_input.type_humanlike('#login-username', account.username)
        
        await interaction.random_pause(0.5, 1.5)
        
        password_input = page.get_by_placeholder("Password")
        if await password_input.count() > 0:
            await interaction.human_input.type_humanlike(password_input, account.password)
        else:
            await interaction.human_input.type_humanlike('#login-password', account.password)

        await interaction.random_pause(0.5, 1.0)
        
        # Click login button
        login_button = page.get_by_role("button", name="Log In")
        if await login_button.count() > 0:
            await interaction.click_with_hesitation(login_button, hesitation_chance=0.2)
        else:
            await page.click('#login-button')
        
        # Wait for navigation/login result
        await asyncio.sleep(5)
        
        # Check for success
        if "login" in page.url.lower():
            # Still on login page - check for errors
            error_msg = await page.query_selector('.validation-summary-errors, .text-error')
            if error_msg:
                error_text = await error_msg.inner_text()
                logger.error(f"Login error: {error_text}")
                
                if "banned" in error_text.lower():
                    self.db.update_account_status(account.id, 'banned', error_text)
            return False
        
        # Try to save cookies for future use
        await self._save_cookies(page.context, account)
        
        return True

    async def _set_cookies(self, context: BrowserContext, cookie_string: str):
        """Parse and set cookies from stored string."""
        import json
        try:
            cookies = json.loads(cookie_string)
            await context.add_cookies(cookies)
        except:
            # Try simple format: name=value; name2=value2
            pass

    async def _save_cookies(self, context: BrowserContext, account: Account):
        """Save session cookies for future use."""
        import json
        try:
            cookies = await context.cookies()
            account.cookie = json.dumps(cookies)
            account.save()
            logger.info("Session cookies saved for future logins")
        except Exception as e:
            logger.warning(f"Failed to save cookies: {e}")

    async def _click_follow_button(self, page: Page, interaction: Interaction) -> bool:
        """
        Attempts to click the follow button using multiple strategies.
        Handles both visible button and menu-hidden button.
        """
        # Strategy 1: Direct follow button
        follow_button = page.get_by_role("button", name="Follow")
        if await follow_button.count() > 0:
            visible = await follow_button.first.is_visible()
            if visible:
                logger.info("Found visible Follow button")
                await interaction.click_with_hesitation(follow_button.first)
                await asyncio.sleep(2)
                return True
        
        # Strategy 2: Text-based locator
        follow_text = page.get_by_text("Follow", exact=True)
        if await follow_text.count() > 0:
            for i in range(await follow_text.count()):
                elem = follow_text.nth(i)
                if await elem.is_visible():
                    logger.info("Found Follow text element")
                    await interaction.click_with_hesitation(elem)
                    await asyncio.sleep(2)
                    return True
        
        # Strategy 3: Look in three-dots menu
        logger.info("Looking for Follow in dropdown menu...")
        more_button = await page.query_selector('[data-testid="more-button"], .more-btn, [aria-label="More"]')
        if more_button:
            box = await more_button.bounding_box()
            if box:
                await interaction.human_input.mouse.click_at(
                    box['x'] + box['width']/2, 
                    box['y'] + box['height']/2
                )
                await asyncio.sleep(1)
                
                # Look for follow in dropdown
                menu_follow = page.locator('[data-testid="follow-button"], .dropdown-menu >> text=Follow')
                if await menu_follow.count() > 0:
                    await menu_follow.first.click()
                    await asyncio.sleep(2)
                    return True
        
        # Strategy 4: CSS selector fallback
        fallback_selectors = [
            'button[data-testid="follow-button"]',
            '.follow-button',
            '#follow-btn',
            'button:has-text("Follow")'
        ]
        
        for selector in fallback_selectors:
            try:
                btn = await page.query_selector(selector)
                if btn:
                    await btn.click()
                    await asyncio.sleep(2)
                    return True
            except:
                continue
        
        logger.warning("Could not find Follow button with any strategy")
        return False

    async def batch_follow(self, target_user_ids: list, delay_between: int = None) -> dict:
        """
        Follow multiple users with delays between each.
        
        Args:
            target_user_ids: List of user IDs to follow
            delay_between: Seconds between follows (default: rate_limit_seconds)
            
        Returns:
            Dict with success/failure counts
        """
        if delay_between is None:
            delay_between = self.rate_limit_seconds
        
        results = {"success": 0, "failed": 0}
        
        for i, user_id in enumerate(target_user_ids):
            logger.info(f"Processing follow {i+1}/{len(target_user_ids)}: {user_id}")
            
            success = await self.follow_user(user_id)
            if success:
                results["success"] += 1
            else:
                results["failed"] += 1
            
            # Delay before next (except for last one)
            if i < len(target_user_ids) - 1:
                wait_time = delay_between + random.randint(-10, 30)
                logger.info(f"Waiting {wait_time}s before next follow...")
                await asyncio.sleep(wait_time)
        
        logger.info(f"Batch complete. Success: {results['success']}, Failed: {results['failed']}")
        return results


# Import at end to avoid circular imports
import random
