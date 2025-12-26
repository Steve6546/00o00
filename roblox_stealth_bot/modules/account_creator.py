"""
Account Creator - Automates Roblox account registration with CAPTCHA handling.
"""

import asyncio
import random
import string
import logging
import time
from playwright.async_api import Page
from behavior.interaction import Interaction
from data.database import DatabaseManager
from modules.captcha_solver import CaptchaManager

logger = logging.getLogger(__name__)


class AccountCreator:
    """
    Handles automated Roblox account creation with:
    - Human-like form filling
    - CAPTCHA solving via CaptchaManager
    - Retry logic with exponential backoff
    - Database logging
    """
    
    def __init__(self, session_manager, db_manager: DatabaseManager, proxy_manager=None):
        self.session_manager = session_manager
        self.db = db_manager
        self.proxy_manager = proxy_manager
        self.captcha_manager = CaptchaManager()

    def generate_username(self) -> str:
        """Generate a random Roblox-style username."""
        adjectives = [
            "Cool", "Super", "Fast", "Silent", "Neon", "Dark", "Light", "Hyper",
            "Epic", "Pro", "Swift", "Blazing", "Shadow", "Cosmic", "Turbo", "Ultra"
        ]
        nouns = [
            "Tiger", "Ninja", "Warrior", "Gamer", "Pilot", "Striker", "Phoenix",
            "Dragon", "Knight", "Racer", "Hunter", "Legend", "Storm", "Wolf"
        ]
        base = f"{random.choice(adjectives)}{random.choice(nouns)}"
        suffix = ''.join(random.choices(string.digits, k=random.randint(3, 5)))
        return f"{base}{suffix}"

    def generate_password(self) -> str:
        """Generate a secure password."""
        # Ensure at least one of each: upper, lower, digit, special
        upper = random.choice(string.ascii_uppercase)
        lower = random.choice(string.ascii_lowercase)
        digit = random.choice(string.digits)
        special = random.choice("!@#$%^&*")
        rest = ''.join(random.choices(
            string.ascii_letters + string.digits + "!@#$%", 
            k=random.randint(8, 12)
        ))
        password = upper + lower + digit + special + rest
        # Shuffle the password
        password_list = list(password)
        random.shuffle(password_list)
        return ''.join(password_list)

    def generate_birthday(self) -> dict:
        """Generate a random birthday for 18+ user."""
        months = ['January', 'February', 'March', 'April', 'May', 'June',
                  'July', 'August', 'September', 'October', 'November', 'December']
        return {
            'month': random.choice(months),
            'day': str(random.randint(1, 28)),
            'year': str(random.randint(1990, 2005))
        }

    async def create_account(self, use_proxy: bool = True) -> dict:
        """
        Create a new Roblox account.
        
        Returns:
            dict with 'success', 'username', 'password', 'error' keys
        """
        start_time = time.time()
        result = {"success": False, "username": None, "password": None, "error": None}
        
        # Get proxy if available
        proxy = None
        if use_proxy and self.proxy_manager:
            proxy = self.proxy_manager.get_proxy()
            if proxy:
                logger.info(f"Using proxy: {proxy['server']}")
        
        context, page = await self.session_manager.create_context(proxy=proxy)
        interaction = Interaction(page)
        
        username = self.generate_username()
        password = self.generate_password()
        birthday = self.generate_birthday()
        
        try:
            # 1. Navigate to Roblox
            logger.info("Navigating to Roblox...")
            await page.goto("https://www.roblox.com", wait_until='domcontentloaded')
            await interaction.random_pause(2, 4)
            
            # 2. Light warm-up (skip for faster testing, or use 'light' for stealth)
            # logger.info("Performing warm-up browsing...")
            # await interaction.warm_up(intensity='light')
            
            # 3. Ensure we're on the signup page
            logger.info("Ensuring on signup page...")
            await page.goto("https://www.roblox.com", wait_until='domcontentloaded')
            await interaction.random_pause(1, 2)
            
            # Wait for signup form to be visible
            await page.wait_for_selector('#MonthDropdown', timeout=10000)
            
            # 4. Fill Birthday
            logger.info("Filling birthday...")
            await self._fill_birthday(page, interaction, birthday)
            
            # 5. Fill Username
            logger.info(f"Typing username: {username}")
            await self._fill_username(page, interaction, username)
            
            # 6. Fill Password
            logger.info("Typing password...")
            await self._fill_password(page, interaction, password)
            
            # 7. Submit form
            logger.info("Clicking sign up...")
            await interaction.random_pause(0.5, 1.5)
            await self._click_signup(page, interaction)
            
            # 8. Handle CAPTCHA and verify success
            logger.info("Checking for CAPTCHA...")
            success = await self._handle_post_signup(page, interaction, username, password, birthday)
            
            if success:
                result["success"] = True
                result["username"] = username
                result["password"] = password
                duration = time.time() - start_time
                self.db.log_task('account_creation', 'success', duration_seconds=duration,
                               proxy_used=proxy['server'] if proxy else None)
            else:
                result["error"] = "CAPTCHA or verification failed"
                self.db.log_task('account_creation', 'failed', 
                               error_message="CAPTCHA/verification failed",
                               proxy_used=proxy['server'] if proxy else None)
            
            return result
            
        except Exception as e:
            logger.error(f"Account creation failed: {e}")
            result["error"] = str(e)
            self.db.log_task('account_creation', 'failed', error_message=str(e),
                           proxy_used=proxy['server'] if proxy else None)
            return result
        finally:
            await self.session_manager.close_context(context)

    async def _fill_birthday(self, page: Page, interaction: Interaction, birthday: dict):
        """Fill birthday dropdowns."""
        try:
            # Try ARIA-based locators first
            month_select = page.get_by_role("combobox", name="Month")
            if await month_select.count() > 0:
                await month_select.select_option(label=birthday['month'])
                await interaction.random_pause(0.3, 0.8)
                
                await page.get_by_role("combobox", name="Day").select_option(label=birthday['day'])
                await interaction.random_pause(0.3, 0.8)
                
                await page.get_by_role("combobox", name="Year").select_option(label=birthday['year'])
                await interaction.random_pause(0.5, 1.0)
            else:
                # Fallback to ID-based selectors
                await page.select_option('#MonthDropdown', label=birthday['month'])
                await interaction.random_pause(0.3, 0.8)
                await page.select_option('#DayDropdown', label=birthday['day'])
                await interaction.random_pause(0.3, 0.8)
                await page.select_option('#YearDropdown', label=birthday['year'])
        except Exception as e:
            logger.warning(f"Birthday fill fallback: {e}")
            # Try alternative approach
            await page.select_option('select[id*="Month"], select[name*="month"]', label=birthday['month'])
            await page.select_option('select[id*="Day"], select[name*="day"]', label=birthday['day'])
            await page.select_option('select[id*="Year"], select[name*="year"]', label=birthday['year'])

    async def _fill_username(self, page: Page, interaction: Interaction, username: str):
        """Fill username field with human-like typing."""
        selectors = [
            page.get_by_placeholder("Username"),
            page.get_by_placeholder("Don't use your real name"),
            page.locator('#signup-username'),
            page.locator('input[name="username"]')
        ]
        
        for selector in selectors:
            try:
                if await selector.count() > 0:
                    await interaction.human_input.type_humanlike(selector.first, username)
                    await interaction.random_pause(0.5, 1.5)
                    return
            except:
                continue
        
        raise Exception("Could not find username field")

    async def _fill_password(self, page: Page, interaction: Interaction, password: str):
        """Fill password field with human-like typing."""
        selectors = [
            page.get_by_placeholder("Password"),
            page.get_by_placeholder("At least 8 characters"),
            page.locator('#signup-password'),
            page.locator('input[name="password"]')
        ]
        
        for selector in selectors:
            try:
                if await selector.count() > 0:
                    await interaction.human_input.type_humanlike(selector.first, password)
                    await interaction.random_pause(0.5, 1.0)
                    return
            except:
                continue
        
        raise Exception("Could not find password field")

    async def _click_signup(self, page: Page, interaction: Interaction):
        """Click the signup button."""
        selectors = [
            page.get_by_role("button", name="Sign Up"),
            page.get_by_role("button", name="Create Account"),
            page.locator('#signup-button'),
            page.locator('button[type="submit"]')
        ]
        
        for selector in selectors:
            try:
                if await selector.count() > 0 and await selector.first.is_visible():
                    await interaction.click_with_hesitation(selector.first, hesitation_chance=0.2)
                    return
            except:
                continue
        
        # Last resort
        await page.click('#signup-button')

    async def _handle_post_signup(self, page: Page, interaction: Interaction, 
                                   username: str, password: str, birthday: dict) -> bool:
        """Handle CAPTCHA and verify account creation success."""
        max_attempts = 3
        
        for attempt in range(max_attempts):
            logger.info(f"Post-signup check attempt {attempt + 1}/{max_attempts}")
            
            try:
                # Wait for either CAPTCHA, success, or error
                await page.wait_for_selector(
                    'iframe[src*="arkoselabs"], iframe[src*="funcaptcha"], '
                    '.security-questions-modal, #nav-profile, .home-container, '
                    '.alert-error, .validation-error',
                    timeout=20000
                )
            except:
                pass
            
            await asyncio.sleep(2)
            
            # Check for success first
            if await self._check_success(page):
                logger.info("Account created successfully!")
                self.db.save_account({
                    "username": username,
                    "password": password,
                    "birthday": f"{birthday['year']}-01-01",
                    "user_agent": await page.evaluate("navigator.userAgent"),
                    "status": "active"
                })
                return True
            
            # Check for CAPTCHA
            if await self._detect_captcha(page):
                logger.warning("CAPTCHA detected, attempting to solve...")
                solved = await self.captcha_manager.solve(page, timeout=120)
                
                if solved:
                    logger.info("CAPTCHA solved, waiting for result...")
                    await asyncio.sleep(3)
                    
                    if await self._check_success(page):
                        logger.info("Account created after CAPTCHA!")
                        self.db.save_account({
                            "username": username,
                            "password": password,
                            "birthday": f"{birthday['year']}-01-01",
                            "user_agent": await page.evaluate("navigator.userAgent"),
                            "status": "active"
                        })
                        return True
                else:
                    logger.warning("CAPTCHA solving failed")
                    if attempt < max_attempts - 1:
                        # Retry with page reload
                        await page.reload()
                        await interaction.random_pause(2, 4)
                        continue
            
            # Check for errors
            error = await page.query_selector('.alert-error, .validation-error, .error-message')
            if error:
                error_text = await error.inner_text()
                logger.error(f"Signup error: {error_text}")
                if "username" in error_text.lower():
                    # Username taken - could retry with different username
                    pass
                return False
            
            # Wait and retry
            if attempt < max_attempts - 1:
                await interaction.random_pause(3, 6)
        
        logger.error("Max attempts reached without success")
        return False

    async def _check_success(self, page: Page) -> bool:
        """Check if account creation was successful."""
        success_indicators = [
            '#nav-profile',
            '.home-container',
            '[data-testid="user-avatar"]',
            '.age-bracket-label'
        ]
        
        # Also check URL
        if any(x in page.url for x in ['/home', '/games', '/discover']):
            return True
        
        for selector in success_indicators:
            element = await page.query_selector(selector)
            if element:
                return True
        
        return False

    async def _detect_captcha(self, page: Page) -> bool:
        """Detect if CAPTCHA is present."""
        captcha_selectors = [
            'iframe[src*="arkoselabs"]',
            'iframe[src*="funcaptcha"]',
            '.security-questions-modal',
            '#FunCaptcha',
            '[data-testid="captcha-container"]'
        ]
        
        for selector in captcha_selectors:
            element = await page.query_selector(selector)
            if element:
                return True
        
        return False

    async def batch_create(self, count: int, delay_between: int = 60) -> dict:
        """
        Create multiple accounts with delays between each.
        
        Args:
            count: Number of accounts to create
            delay_between: Base delay in seconds between attempts
            
        Returns:
            dict with results summary
        """
        results = {"success": 0, "failed": 0, "accounts": []}
        
        for i in range(count):
            logger.info(f"Creating account {i + 1}/{count}...")
            
            result = await self.create_account()
            
            if result["success"]:
                results["success"] += 1
                results["accounts"].append({
                    "username": result["username"],
                    "password": result["password"]
                })
            else:
                results["failed"] += 1
            
            # Delay before next (with randomization)
            if i < count - 1:
                wait_time = delay_between + random.randint(-15, 30)
                logger.info(f"Waiting {wait_time}s before next account...")
                await asyncio.sleep(wait_time)
        
        logger.info(f"Batch complete: {results['success']}/{count} successful")
        return results
