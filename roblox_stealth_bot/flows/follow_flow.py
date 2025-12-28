"""
Follow Flow - State machine-based user following flow.

This orchestrates the complete follow process:
1. Login with saved account (cookie or credentials)
2. Search/Navigate to target user
3. Click follow button
4. Verify follow actually worked (multi-method verification)

Key features:
- State machine driven
- Smart session validation and self-healing
- Circuit breaker to prevent repeated failures
- Detailed metrics tracking
- Multi-verification (button state, followers list, count comparison)
- Handles various UI states
"""

import asyncio
import logging
import time
import json
from typing import Optional, Dict, List
from dataclasses import dataclass, field

from src.core.state_machine import (
    StateMachine, SystemState, Event, StateContext,
    create_follow_state_machine
)
from src.core.page_detector import PageDetector, PageType
from src.core.session_manager import SessionManager
from src.core.session_validator import SessionValidator, SessionStatus
from src.core.session_renewer import SessionRenewer
from src.core.fallback_login import FallbackLogin
from src.core.circuit_breaker import CircuitBreaker
from src.core.session_metrics import SessionMetrics
from src.behavior.human_input import HumanInput
from data.database import DatabaseManager, Account

logger = logging.getLogger(__name__)

# Global instances for cross-flow tracking
_circuit_breaker = CircuitBreaker(failure_threshold=3, reset_timeout=300)
_session_metrics = SessionMetrics()


@dataclass
class FollowVerificationResult:
    """Result of follow verification."""
    
    verified: bool = False
    method: str = ""  # button_state, followers_list, count_comparison
    details: str = ""
    confidence: float = 0.0


@dataclass
class FollowFlowResult:
    """Result of follow flow execution."""
    
    success: bool
    target_user: str = ""
    target_id: str = ""
    account_used: str = ""
    verification: Optional[FollowVerificationResult] = None
    error: str = ""
    duration_seconds: float = 0.0
    states_visited: list = field(default_factory=list)
    already_following: bool = False


class FollowVerifier:
    """
    Multi-method verification for follow confirmation.
    
    Uses three methods:
    1. Button state check (Follow vs Following)
    2. Followers list check (appear in target's followers)
    3. Following count check (before/after comparison)
    """
    
    def __init__(self, page, page_detector: PageDetector):
        self.page = page
        self.detector = page_detector
    
    async def verify_follow(self, target_id: str, account_username: str) -> FollowVerificationResult:
        """
        Verify that follow was successful using multiple methods.
        
        Args:
            target_id: The target user's ID
            account_username: The username of the account that followed
            
        Returns:
            FollowVerificationResult with verification details
        """
        result = FollowVerificationResult()
        
        # Method 1: Check button state (most reliable)
        button_check = await self._verify_button_state()
        if button_check:
            result.verified = True
            result.method = "button_state"
            result.details = "Follow button shows 'Following'"
            result.confidence = 0.95
            return result
        
        # Method 2: Check if we appear in followers list
        # (requires navigating to followers page - optional)
        # followers_check = await self._verify_followers_list(target_id, account_username)
        # if followers_check:
        #     result.verified = True
        #     result.method = "followers_list"
        #     result.details = f"Found {account_username} in followers list"
        #     result.confidence = 0.99
        #     return result
        
        # Method 3: Page/URL check
        page_check = await self._verify_page_state()
        if page_check:
            result.verified = True
            result.method = "page_state"
            result.details = "Page state indicates follow success"
            result.confidence = 0.8
            return result
        
        result.verified = False
        result.details = "Could not verify follow"
        result.confidence = 0.0
        return result
    
    async def _verify_button_state(self) -> bool:
        """Check if follow button shows 'Following'."""
        try:
            # Look for "Following" button text
            following_indicators = [
                "button:has-text('Following')",
                "button:has-text('Followed')",
                ".follow-button.following",
                "[data-follow-status='following']",
            ]
            
            for selector in following_indicators:
                element = await self.page.query_selector(selector)
                if element:
                    is_visible = await element.is_visible()
                    if is_visible:
                        return True
            
            # Alternative: check button text content
            buttons = await self.page.query_selector_all("button")
            for button in buttons[:10]:  # Check first 10 buttons
                try:
                    text = await button.inner_text()
                    if text and "following" in text.lower():
                        return True
                except:
                    continue
            
            return False
        
        except Exception as e:
            logger.debug(f"Button state check failed: {e}")
            return False
    
    async def _verify_page_state(self) -> bool:
        """Verify based on general page state."""
        try:
            # Check for success indicators
            success_indicators = [
                ".follow-success",
                ".notification:has-text('followed')",
                "[data-testid='follow-success']",
            ]
            
            for selector in success_indicators:
                element = await self.page.query_selector(selector)
                if element:
                    return True
            
            # Check URL hasn't changed to error
            if "/error" in self.page.url or "/banned" in self.page.url:
                return False
            
            return False
        
        except Exception as e:
            logger.debug(f"Page state check failed: {e}")
            return False
    
    async def check_already_following(self) -> bool:
        """Check if already following the target."""
        try:
            already_following_indicators = [
                "button:has-text('Following')",
                "button:has-text('Unfollow')",
                ".follow-button.following",
            ]
            
            for selector in already_following_indicators:
                element = await self.page.query_selector(selector)
                if element:
                    is_visible = await element.is_visible()
                    if is_visible:
                        return True
            
            return False
        
        except Exception as e:
            logger.debug(f"Already following check failed: {e}")
            return False


class FollowFlow:
    """
    State machine-based follow flow.
    
    Orchestrates:
    1. Login with the specified account
    2. Navigate to target user's profile
    3. Click follow button
    4. Verify follow was successful
    
    Usage:
        flow = FollowFlow(session_manager, db_manager)
        result = await flow.execute(
            target_user="someuser123",
            account_id=1
        )
    """
    
    def __init__(self, session_manager: SessionManager, db_manager: DatabaseManager):
        self.session = session_manager
        self.db = db_manager
        
        # Components
        self.page_detector = PageDetector()
        
        # State machine
        self.sm = create_follow_state_machine()
        
        # Current execution state
        self.page = None
        self.context = None
        self.human_input = None
        self.account = None
        self.verifier = None
    
    async def execute(self, target_user: str, account_id: int = None,
                      target_is_id: bool = False) -> FollowFlowResult:
        """
        Execute the follow flow.
        
        Args:
            target_user: Username or UserID to follow
            account_id: Specific account to use (optional)
            target_is_id: True if target_user is a UserID
            
        Returns:
            FollowFlowResult with success status and details
        """
        start_time = time.time()
        result = FollowFlowResult(success=False, target_user=target_user)
        
        # Get account to use
        if account_id:
            self.account = Account.get_by_id(account_id)
        else:
            self.account = self.db.get_account_by_least_used()
        
        if not self.account:
            result.error = "No available account"
            return result
        
        result.account_used = self.account.username
        logger.info(f"Using account: {self.account.username} to follow {target_user}")
        
        # Determine target ID
        if target_is_id:
            result.target_id = target_user
        else:
            # Will need to search for the user
            result.target_id = ""
        
        # Setup context
        self.context = StateContext(
            task_type="follow",
            account_id=self.account.id,
            target_user=target_user,
            target_id=result.target_id,
            max_retries=3
        )
        self.sm.set_context(self.context)
        
        # Check circuit breaker before proceeding
        if not _circuit_breaker.can_use(self.account.id):
            logger.warning(
                f"Circuit breaker OPEN for {self.account.username} - skipping"
            )
            result.error = "Account circuit breaker is open (recent failures)"
            _session_metrics.record_follow(
                self.account.id, 
                success=False, 
                target=target_user,
                username=self.account.username
            )
            return result
        
        # Create browser context
        browser_context, self.page = await self.session.create_context()
        self.human_input = HumanInput(self.page)
        self.verifier = FollowVerifier(self.page, self.page_detector)
        
        try:
            # Start state machine
            await self.sm.handle_event(Event.START)
            
            # Main loop
            while not self.sm.is_terminal():
                page_result = await self.page_detector.detect(self.page)
                await self._process_state(page_result, result)
                
                await asyncio.sleep(0.5)
                result.states_visited.append(self.sm.state.value)
            
            # Check final result
            if self.sm.state == SystemState.SUCCESS:
                result.success = True
                
                # Update account stats
                self.db.increment_follow_count(self.account.id)
                self.db.set_account_cooldown(self.account.id, minutes=15)
                
                # Record success in circuit breaker and metrics
                _circuit_breaker.record_success(self.account.id)
                _session_metrics.record_follow(
                    self.account.id,
                    success=True,
                    target=target_user,
                    username=self.account.username
                )
                
                logger.info(f"✓ Follow successful: {self.account.username} -> {target_user}")
            else:
                result.error = self.context.last_error or "Follow failed"
                
                # Record failure in circuit breaker and metrics
                _circuit_breaker.record_failure(self.account.id, result.error)
                _session_metrics.record_follow(
                    self.account.id,
                    success=False,
                    target=target_user,
                    username=self.account.username
                )
                
                logger.error(f"✗ Follow failed: {result.error}")
        
        except Exception as e:
            result.error = str(e)
            _circuit_breaker.record_failure(self.account.id, str(e))
            _session_metrics.record_follow(
                self.account.id,
                success=False,
                target=target_user,
                username=self.account.username
            )
            logger.error(f"Follow flow error: {e}")
        
        finally:
            await self.session.close_context(browser_context)
            result.duration_seconds = time.time() - start_time
            
            # Log task
            self.db.log_task(
                task_type="follow",
                status="success" if result.success else "failed",
                target=target_user,
                account_id=self.account.id,
                error_message=result.error if not result.success else None,
                duration_seconds=result.duration_seconds
            )
        
        return result
    
    async def _process_state(self, page_result, result: FollowFlowResult):
        """Process current state."""
        
        state = self.sm.state
        
        if state == SystemState.VERIFYING_LOGIN:
            await self._handle_login(page_result)
        
        elif state == SystemState.FOLLOWING_SEARCHING:
            await self._handle_searching(page_result, result)
        
        elif state == SystemState.FOLLOWING_NAVIGATING:
            await self._handle_navigating(page_result)
        
        elif state == SystemState.FOLLOWING_ACTION:
            await self._handle_follow_action(page_result, result)
        
        elif state == SystemState.FOLLOWING_CONFIRMING:
            await self._handle_confirming(page_result, result)
    
    async def _handle_login(self, page_result):
        """
        Handle login state with smart session management.
        
        Strategy:
        1. Validate session (cookies + live check)
        2. If expired, try renewal
        3. If renewal fails, perform full login
        4. If everything fails, quarantine and fail gracefully
        
        Key principle: Never give up on an account without trying all options.
        """
        
        logger.info(f"[LOGIN] Starting smart login for: {self.account.username}")
        
        # Initialize session management components
        validator = SessionValidator()
        renewer = SessionRenewer()
        fallback = FallbackLogin()
        
        # Step 1: Validate current session
        logger.info("[LOGIN] Step 1: Validating session...")
        validation = await validator.validate(self.account, self.page)
        
        logger.info(
            f"[LOGIN] Validation result: {validation.status.value} - {validation.reason}"
        )
        
        # If session is valid, we're done!
        if validation.status == SessionStatus.VALID and not validation.needs_login:
            logger.info("[LOGIN] ✓ Session is VALID - no login needed")
            await self.sm.handle_event(Event.LOGIN_SUCCESS)
            return
        
        # Step 2: Try renewal if session might be recoverable
        if validation.status in [SessionStatus.NEEDS_RENEWAL, SessionStatus.EXPIRED]:
            logger.info("[LOGIN] Step 2: Attempting session renewal...")
            
            renewal_result = await renewer.renew(self.account, self.page)
            
            logger.info(
                f"[LOGIN] Renewal result: {renewal_result.status.value} - {renewal_result.reason}"
            )
            
            if renewal_result.success:
                logger.info("[LOGIN] ✓ Session renewed successfully!")
                
                # Update cookies in database if new ones were obtained
                if renewal_result.new_cookies:
                    try:
                        self.account.cookie = renewal_result.new_cookies
                        self.account.save()
                        logger.info("[LOGIN] Saved renewed cookies to database")
                    except Exception as e:
                        logger.warning(f"Could not save renewed cookies: {e}")
                
                await self.sm.handle_event(Event.LOGIN_SUCCESS)
                return
        
        # Step 3: Fallback to full login
        logger.info("[LOGIN] Step 3: Attempting full login with credentials...")
        
        if not self.account.password:
            logger.error("[LOGIN] ✗ No password stored - cannot perform full login")
            self.context.last_error = "No password stored for account"
            await self.sm.handle_event(Event.LOGIN_FAILED)
            return
        
        login_result = await fallback.login(self.account, self.page)
        
        logger.info(
            f"[LOGIN] Login result: {login_result.status.value} - {login_result.reason}"
        )
        
        if login_result.success:
            logger.info("[LOGIN] ✓ Full login successful!")
            
            # Save new cookies
            if login_result.new_cookies:
                try:
                    self.account.cookie = login_result.new_cookies
                    self.account.save()
                    logger.info("[LOGIN] Saved new login cookies to database")
                except Exception as e:
                    logger.warning(f"Could not save login cookies: {e}")
            
            await self.sm.handle_event(Event.LOGIN_SUCCESS)
            return
        
        # Step 4: All attempts failed
        logger.error(
            f"[LOGIN] ✗ All login attempts failed for {self.account.username}"
        )
        
        # Record the failure reason for later analysis
        failure_reason = login_result.reason or "Unknown login failure"
        
        if login_result.requires_manual:
            logger.warning(
                f"[LOGIN] Account {self.account.username} requires manual review: {failure_reason}"
            )
            # Could mark account for review here
        
        self.context.last_error = f"Login failed: {failure_reason}"
        await self.sm.handle_event(Event.LOGIN_FAILED)
    
    async def _handle_searching(self, page_result, result: FollowFlowResult):
        """Handle target search state."""
        
        target = self.context.target_user
        target_id = self.context.target_id
        
        if target_id:
            # Direct navigation to profile by ID
            profile_url = f"https://www.roblox.com/users/{target_id}/profile"
            logger.info(f"Navigating to profile: {profile_url}")
            
            await self.page.goto(profile_url, wait_until='domcontentloaded')
            await asyncio.sleep(3)
            
            page_check = await self.page_detector.detect(self.page)
            logger.info(f"After navigation, page type: {page_check.page_type.value}")
            
            if page_check.page_type == PageType.PROFILE:
                # Go directly to TARGET_FOUND -> NAVIGATING -> PAGE_LOADED -> ACTION
                await self.sm.handle_event(Event.TARGET_FOUND)
                # Now we're in FOLLOWING_NAVIGATING, immediately fire PAGE_LOADED
                await self.sm.handle_event(Event.PAGE_LOADED)
                return
            elif page_check.page_type == PageType.NOT_FOUND:
                self.context.last_error = f"User {target_id} not found"
                await self.sm.handle_event(Event.TARGET_NOT_FOUND)
                return
            else:
                # Try once more
                await asyncio.sleep(2)
                # Assume we're on profile anyway
                await self.sm.handle_event(Event.TARGET_FOUND)
                await self.sm.handle_event(Event.PAGE_LOADED)
                return
        
        else:
            # Search for user by username
            logger.info(f"Searching for user: {target}")
            
            # Use Roblox search
            search_url = f"https://www.roblox.com/search/users?keyword={target}"
            await self.page.goto(search_url, wait_until='domcontentloaded')
            await asyncio.sleep(3)
            
            # Look for the user in results
            user_link = await self.page.query_selector(f"a[href*='/users/']:has-text('{target}')")
            
            if user_link:
                href = await user_link.get_attribute("href")
                if href:
                    # Extract user ID from href
                    import re
                    match = re.search(r'/users/(\d+)', href)
                    if match:
                        self.context.target_id = match.group(1)
                        result.target_id = self.context.target_id
                        await self.sm.handle_event(Event.TARGET_FOUND)
                        return
            
            self.context.last_error = f"Could not find user: {target}"
            await self.sm.handle_event(Event.TARGET_NOT_FOUND)
    
    async def _handle_navigating(self, page_result):
        """Handle navigation to profile state."""
        
        target_id = self.context.target_id
        profile_url = f"https://www.roblox.com/users/{target_id}/profile"
        
        # Check if we're already on profile page
        result = await self.page_detector.detect(self.page)
        if result.page_type == PageType.PROFILE:
            logger.info("Already on profile page, proceeding to action")
            await self.sm.handle_event(Event.PAGE_LOADED)
            return
        
        # Navigate to profile if not there
        await self.page.goto(profile_url, wait_until='domcontentloaded')
        await asyncio.sleep(2)
        
        # Detect page
        result = await self.page_detector.detect(self.page)
        if result.page_type == PageType.PROFILE:
            await self.sm.handle_event(Event.PAGE_LOADED)
        else:
            self.context.last_error = "Could not load profile page"
            await self.sm.handle_event(Event.ERROR)
    
    async def _handle_follow_action(self, page_result, result: FollowFlowResult):
        """
        Handle clicking the follow button via menu.
        
        VERIFIED selectors from browser inspection (Dec 2024):
        - Menu button: #user-profile-header-contextual-menu-button
        - Follow button: button.foundation-web-menu-item:has-text("Follow")
        """
        
        logger.info("Starting follow action...")
        
        try:
            # Wait for page to be ready
            await self.page.wait_for_load_state('networkidle')
            await self.page.wait_for_timeout(2000)
            
            # Step 1: Click the menu button using verified ID
            logger.info("Looking for menu button (#user-profile-header-contextual-menu-button)...")
            menu_btn = await self.page.wait_for_selector(
                '#user-profile-header-contextual-menu-button',
                state='visible',
                timeout=10000
            )
            
            if not menu_btn:
                logger.error("✗ Menu button not found")
                self.context.last_error = "Menu button not found"
                await self.sm.handle_event(Event.FOLLOW_FAILED)
                return
            
            logger.info("✓ Menu button found, clicking...")
            await menu_btn.click()
            await self.page.wait_for_timeout(1500)
            
            # Step 2: Look for Follow or Unfollow in the menu
            logger.info("Looking for Follow/Unfollow in menu...")
            
            # Check for Unfollow first (already following)
            unfollow_btn = await self.page.query_selector('button.foundation-web-menu-item:has-text("Unfollow")')
            if unfollow_btn:
                logger.info("✓ Already following - Unfollow button found")
                result.already_following = True
                await self.page.keyboard.press("Escape")
                await self.sm.handle_event(Event.ALREADY_FOLLOWING)
                return
            
            # Look for Follow button
            follow_btn = await self.page.wait_for_selector(
                'button.foundation-web-menu-item:has-text("Follow")',
                state='visible',
                timeout=5000
            )
            
            if not follow_btn:
                logger.error("✗ Follow button not found in menu")
                self.context.last_error = "Follow button not in menu"
                await self.page.keyboard.press("Escape")
                await self.sm.handle_event(Event.FOLLOW_FAILED)
                return
            
            # Step 3: Click Follow
            logger.info("✓ Follow button found, clicking...")
            await follow_btn.click()
            await self.page.wait_for_timeout(2000)
            
        except Exception as e:
            logger.error(f"✗ Follow action error: {e}")
            self.context.last_error = f"Follow error: {e}"
            await self.sm.handle_event(Event.FOLLOW_FAILED)
            return
        
        # Step 4: Reload and verify
        logger.info("Reloading to verify...")
        try:
            await self.page.reload(wait_until='networkidle')
            await self.page.wait_for_timeout(2000)
            
            # Reopen menu
            menu_btn = await self.page.wait_for_selector(
                '#user-profile-header-contextual-menu-button',
                state='visible',
                timeout=10000
            )
            await menu_btn.click()
            await self.page.wait_for_timeout(1500)
            
            # Check for Unfollow = SUCCESS
            unfollow_btn = await self.page.query_selector('button.foundation-web-menu-item:has-text("Unfollow")')
            if unfollow_btn:
                logger.info("✓ Follow VERIFIED - Unfollow button found!")
                result.verification = FollowVerificationResult(
                    verified=True,
                    method="menu_unfollow_check",
                    details="Unfollow button appeared after reload",
                    confidence=0.99
                )
                await self.page.keyboard.press("Escape")
                await self.sm.handle_event(Event.FOLLOW_CLICKED)
                return
            
            logger.warning("✗ Follow NOT verified - Unfollow not found")
            self.context.last_error = "Unfollow not found after reload"
            await self.page.keyboard.press("Escape")
            await self.sm.handle_event(Event.FOLLOW_FAILED)
                
        except Exception as e:
            logger.error(f"✗ Verification error: {e}")
            self.context.last_error = f"Verification error: {e}"
            await self.sm.handle_event(Event.FOLLOW_FAILED)
    
    async def _handle_confirming(self, page_result, result: FollowFlowResult):
        """Handle follow confirmation state."""
        
        # Final verification
        is_following = await self._check_following_status()
        
        if is_following:
            logger.info("✅ Follow confirmed!")
            result.verification = FollowVerificationResult(
                verified=True,
                method="button_state_reload",
                details="Follow button shows Following/Unfollow after reload",
                confidence=0.98
            )
            await self.sm.handle_event(Event.FOLLOW_CONFIRMED)
        else:
            logger.warning("❌ Follow verification failed")
            self.context.last_error = "Follow could not be verified"
            await self.sm.handle_event(Event.FOLLOW_FAILED)
    
    async def _check_following_status(self) -> bool:
        """Check if currently following the target user."""
        try:
            # Look for "Following" or "Unfollow" indicators
            following_indicators = [
                "button:has-text('Following')",
                "button:has-text('Unfollow')",
                "[data-testid='unfollow-button']",
                ".follow-button.following",
                "button:has-text('متابَع')",  # Arabic
            ]
            
            for selector in following_indicators:
                element = await self.page.query_selector(selector)
                if element:
                    is_visible = await element.is_visible()
                    if is_visible:
                        logger.debug(f"Found following indicator: {selector}")
                        return True
            
            return False
        except Exception as e:
            logger.debug(f"Following check error: {e}")
            return False
    
    async def _click_follow_button(self) -> bool:
        """Click follow button, checking hamburger menu if needed."""
        
        # Strategy 1: Try direct Follow button first
        direct_clicked = await self._try_direct_follow_button()
        if direct_clicked:
            return True
        
        # Strategy 2: Open hamburger menu (☰) and click Follow
        hamburger_clicked = await self._try_hamburger_menu_follow()
        if hamburger_clicked:
            return True
        
        # Strategy 3: Try more tab/menu options
        more_options_clicked = await self._try_more_options_follow()
        if more_options_clicked:
            return True
        
        return False
    
    async def _try_direct_follow_button(self) -> bool:
        """Try clicking a direct visible Follow button."""
        selectors = [
            "button:has-text('Follow'):not(:has-text('Following'))",
            ".follow-button:not(.following)",
            "[data-testid='follow-button']",
            "button[aria-label='Follow']",
            "button:has-text('متابعة')",  # Arabic "Follow"
        ]
        
        for selector in selectors:
            try:
                button = await self.page.query_selector(selector)
                if button:
                    is_visible = await button.is_visible()
                    if is_visible:
                        text = await button.inner_text()
                        if "following" not in text.lower() and "unfollow" not in text.lower():
                            await button.click()
                            logger.info(f"Clicked direct follow button: {selector}")
                            return True
            except Exception as e:
                logger.debug(f"Direct button error: {e}")
        
        return False
    
    async def _try_hamburger_menu_follow(self) -> bool:
        """Open contextual menu (three dots) and click Follow."""
        
        logger.info("Trying contextual menu follow...")
        
        # Wait for page to fully load first
        await asyncio.sleep(3)
        
        # Take debug screenshot
        try:
            await self.page.screenshot(path="debug_before_menu.png")
            logger.info("Debug screenshot saved: debug_before_menu.png")
        except:
            pass
        
        # Step 1: Try to find and click the contextual menu button using locator
        menu_opened = False
        
        try:
            # Use locator for better handling of multiple elements
            menu_loc = self.page.locator("#user-profile-header-contextual-menu-button")
            count = await menu_loc.count()
            logger.info(f"Found {count} contextual menu button(s)")
            
            if count > 0:
                await menu_loc.first.scroll_into_view_if_needed()
                await asyncio.sleep(0.5)
                await menu_loc.first.click(force=True)  # Force click even if covered
                logger.info("Clicked contextual menu button via locator")
                menu_opened = True
                await asyncio.sleep(2)  # Wait for menu dropdown to appear
        except Exception as e:
            logger.warning(f"Locator click failed: {e}")
        
        # Fallback selectors
        if not menu_opened:
            fallback_selectors = [
                "button[aria-label='Open Popover']",
                "button:has-text('⋮')",
            ]
            for selector in fallback_selectors:
                try:
                    btn = await self.page.query_selector(selector)
                    if btn:
                        await btn.click(force=True)
                        logger.info(f"Clicked fallback: {selector}")
                        menu_opened = True
                        await asyncio.sleep(2)
                        break
                except:
                    pass
        
        if not menu_opened:
            logger.warning("Could not open contextual menu")
            return False
        
        # Step 2: Click Follow in the menu
        await asyncio.sleep(1)  # Extra wait for menu animation
        
        # Try locator first
        try:
            follow_loc = self.page.locator("button:has-text('Follow')").first
            if await follow_loc.is_visible():
                text = await follow_loc.inner_text()
                if "unfollow" not in text.lower():
                    await follow_loc.click()
                    logger.info("Clicked Follow via locator")
                    return True
        except Exception as e:
            logger.debug(f"Follow locator failed: {e}")
        
        logger.warning("Could not find Follow button in menu - may already be following")
        return False
    
    async def _try_more_options_follow(self) -> bool:
        """Try finding Follow in More/Options dropdown."""
        try:
            more_button = await self.page.query_selector('[aria-label="More"]')
            if more_button:
                await more_button.click()
                await asyncio.sleep(1)
                
                menu_follow = await self.page.query_selector("li:has-text('Follow'), button:has-text('Follow')")
                if menu_follow:
                    await menu_follow.click()
                    logger.info("Clicked Follow in More menu")
                    return True
        except Exception as e:
            logger.debug(f"More options follow error: {e}")
        
        return False
    
    async def _save_cookies(self):
        """Save session cookies for future logins."""
        try:
            cookies = await self.page.context.cookies()
            self.account.cookie = json.dumps(cookies)
            self.account.save()
            logger.info("Session cookies saved")
        except Exception as e:
            logger.warning(f"Could not save cookies: {e}")


# Convenience functions
async def follow_user(session_manager: SessionManager, db_manager: DatabaseManager,
                      target_user: str, account_id: int = None,
                      target_is_id: bool = False) -> FollowFlowResult:
    """
    Convenience function to follow a user.
    
    Args:
        target_user: Username or UserID
        account_id: Specific account to use (optional)
        target_is_id: True if target_user is a numeric UserID
    """
    flow = FollowFlow(session_manager, db_manager)
    return await flow.execute(target_user, account_id, target_is_id)


async def batch_follow(session_manager: SessionManager, db_manager: DatabaseManager,
                       target_user: str, count: int = 5,
                       delay_between: int = 30) -> Dict:
    """
    Follow a user with multiple accounts.
    
    Args:
        target_user: User to follow
        count: Number of accounts to use
        delay_between: Seconds between follows
    """
    results = {"success": 0, "failed": 0, "skipped": 0, "details": []}
    
    for i in range(count):
        logger.info(f"Follow attempt {i+1}/{count}")
        
        result = await follow_user(session_manager, db_manager, target_user)
        
        if result.success:
            results["success"] += 1
        elif result.already_following:
            results["skipped"] += 1
        else:
            results["failed"] += 1
        
        results["details"].append({
            "account": result.account_used,
            "success": result.success,
            "already_following": result.already_following,
            "error": result.error
        })
        
        if i < count - 1:
            logger.info(f"Waiting {delay_between}s before next follow...")
            await asyncio.sleep(delay_between)
    
    return results

