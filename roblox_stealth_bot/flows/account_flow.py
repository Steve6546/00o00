"""
Account Flow - State machine-based account creation flow.

This is the main orchestrator for account creation.
It uses the StateMachine to manage states and transitions,
and coordinates between PageDetector, IdentityGenerator, and HumanInput.

Key principle: The flow never assumes state - it always detects and reacts.
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Tuple
from dataclasses import dataclass

from core.state_machine import (
    StateMachine, SystemState, Event, StateContext, 
    create_account_state_machine
)
from core.page_detector import PageDetector, PageType
from generators.identity_generator import IdentityGenerator, Identity
from core.session_manager import SessionManager
from behavior.human_input import HumanInput
from modules.captcha_solver import CaptchaManager
from data.database import DatabaseManager

logger = logging.getLogger(__name__)


@dataclass
class AccountFlowResult:
    """Result of account creation flow."""
    
    success: bool
    identity: Optional[Identity] = None
    account_id: Optional[int] = None
    error: str = ""
    duration_seconds: float = 0.0
    states_visited: list = None
    
    def __post_init__(self):
        if self.states_visited is None:
            self.states_visited = []


class AccountFlow:
    """
    State machine-based account creation flow.
    
    This class orchestrates the entire account creation process:
    1. Generate identity
    2. Navigate to signup
    3. Fill form with human-like behavior
    4. Handle CAPTCHA if needed
    5. Verify success
    6. Save to database
    
    Usage:
        flow = AccountFlow(session_manager, db_manager)
        result = await flow.execute()
        if result.success:
            print(f"Created: {result.identity.username}")
    """
    
    def __init__(self, session_manager: SessionManager, db_manager: DatabaseManager,
                 proxy_manager=None):
        self.session = session_manager
        self.db = db_manager
        self.proxy_manager = proxy_manager
        
        # Components
        self.page_detector = PageDetector()
        self.identity_gen = IdentityGenerator(db_manager)
        self.captcha_manager = CaptchaManager()
        
        # State machine
        self.sm = create_account_state_machine()
        
        # Current execution state
        self.page = None
        self.context = None
        self.human_input = None
        self.identity = None
    
    async def execute(self, use_proxy: bool = True) -> AccountFlowResult:
        """
        Execute the complete account creation flow.
        
        Returns:
            AccountFlowResult with success status and details
        """
        start_time = time.time()
        result = AccountFlowResult(success=False)
        
        # Generate identity
        self.identity = self.identity_gen.generate()
        logger.info(f"Generated identity: {self.identity.username}")
        
        # Setup context
        self.context = StateContext(
            task_type="create_account",
            username=self.identity.username,
            password=self.identity.password,
            birthday=self.identity.birthday,
            max_retries=3
        )
        self.sm.set_context(self.context)
        
        # Get proxy if enabled
        proxy = None
        if use_proxy and self.proxy_manager:
            proxy = self.proxy_manager.get_proxy()
            if proxy:
                logger.info(f"Using proxy: {proxy['server']}")
        
        # Create browser context
        browser_context, self.page = await self.session.create_context(proxy=proxy)
        self.human_input = HumanInput(self.page)
        
        try:
            # Register state handlers
            self._register_handlers()
            
            # Start the state machine
            await self.sm.handle_event(Event.START)
            
            # Main loop: process until terminal state
            while not self.sm.is_terminal():
                # Detect current page
                page_result = await self.page_detector.detect(self.page)
                logger.debug(f"Detected page: {page_result.page_type.value} ({page_result.confidence:.2f})")
                
                # Process based on current state and page
                await self._process_state(page_result)
                
                # Small delay between iterations
                await asyncio.sleep(0.5)
                
                # Track visited states
                result.states_visited.append(self.sm.state.value)
            
            # Check final result
            if self.sm.state == SystemState.SUCCESS:
                result.success = True
                result.identity = self.identity
                
                # Save cookies for future login
                try:
                    import json
                    cookies = await browser_context.cookies()
                    cookie_str = json.dumps(cookies) if cookies else None
                except Exception as e:
                    logger.warning(f"Could not save cookies: {e}")
                    cookie_str = None
                
                # Save to database with cookies
                account = self.db.save_account({
                    "username": self.identity.username,
                    "password": self.identity.password,
                    "birthday": self.identity.birthday_date,
                    "status": "active",  # Changed to active
                    "cookie": cookie_str
                })
                result.account_id = account.id
                
                # Also save session file for session_manager
                try:
                    await self.session.save_session(browser_context, self.identity.username)
                except Exception as e:
                    logger.warning(f"Could not save session file: {e}")
                
                logger.info(f"✓ Account created successfully: {self.identity.username}")
            else:
                result.error = self.context.last_error or "Unknown error"
                logger.error(f"✗ Account creation failed: {result.error}")
        
        except Exception as e:
            result.error = str(e)
            logger.error(f"Flow execution error: {e}")
        
        finally:
            # Cleanup
            await self.session.close_context(browser_context)
            result.duration_seconds = time.time() - start_time
            
            # Log task
            self.db.log_task(
                task_type="account_creation",
                status="success" if result.success else "failed",
                error_message=result.error if not result.success else None,
                duration_seconds=result.duration_seconds,
                proxy_used=proxy['server'] if proxy else None
            )
        
        return result
    
    def _register_handlers(self):
        """Register state enter/exit handlers."""
        
        # Log state changes
        for state in SystemState:
            self.sm.on_enter(state, lambda ctx, s=state: logger.info(f"Entering state: {s.value}"))
    
    async def _process_state(self, page_result):
        """Process current state and trigger appropriate events."""
        
        state = self.sm.state
        page_type = page_result.page_type
        
        # State: Navigating -> Need to go to signup page
        if state == SystemState.CREATING_NAVIGATING:
            await self._handle_navigating(page_result)
        
        # State: Filling form
        elif state == SystemState.CREATING_FILLING_FORM:
            await self._handle_filling_form(page_result)
        
        # State: Submitting
        elif state == SystemState.CREATING_SUBMITTING:
            await self._handle_submitting(page_result)
        
        # State: CAPTCHA
        elif state == SystemState.CREATING_CAPTCHA:
            await self._handle_captcha(page_result)
        
        # State: Waiting for result
        elif state == SystemState.CREATING_WAITING:
            await self._handle_waiting(page_result)
    
    async def _handle_navigating(self, page_result):
        """Handle CREATING_NAVIGATING state."""
        
        if page_result.page_type == PageType.SIGNUP:
            # Already on signup page
            await self.sm.handle_event(Event.FORM_READY)
        
        elif page_result.page_type == PageType.CAPTCHA:
            # CAPTCHA appeared
            await self.sm.handle_event(Event.CAPTCHA_DETECTED)
        
        else:
            # Navigate to signup
            logger.info("Navigating to Roblox signup...")
            await self.page.goto("https://www.roblox.com", wait_until='domcontentloaded')
            await asyncio.sleep(2)
            
            # Check if we're on signup now
            new_result = await self.page_detector.detect(self.page)
            if new_result.page_type == PageType.SIGNUP:
                await self.sm.handle_event(Event.FORM_READY)
            else:
                self.context.last_error = "Could not reach signup page"
                await self.sm.handle_event(Event.ERROR)
    
    async def _handle_filling_form(self, page_result):
        """Handle CREATING_FILLING_FORM state."""
        
        if page_result.page_type != PageType.SIGNUP:
            # Lost the signup page
            self.context.last_error = "Lost signup page"
            await self.sm.handle_event(Event.ERROR)
            return
        
        try:
            # Fill birthday
            logger.info("Filling birthday...")
            await self._fill_birthday()
            await asyncio.sleep(0.5)
            
            # Fill username
            logger.info(f"Filling username: {self.identity.username}")
            await self._fill_field("username_input", self.identity.username)
            await asyncio.sleep(0.5)
            
            # Fill password
            logger.info("Filling password...")
            await self._fill_field("password_input", self.identity.password)
            await asyncio.sleep(0.5)
            
            # Form complete
            await self.sm.handle_event(Event.FORM_COMPLETE)
        
        except Exception as e:
            self.context.last_error = f"Form filling failed: {e}"
            self.context.errors.append(str(e))
            await self.sm.handle_event(Event.ERROR)
    
    async def _handle_submitting(self, page_result):
        """Handle CREATING_SUBMITTING state."""
        
        try:
            # Find and click signup button
            button_selector = await self.page_detector.find_element(self.page, "signup_button")
            
            if button_selector:
                logger.info("Clicking signup button...")
                await self.page.click(button_selector)
                await self.sm.handle_event(Event.SUBMITTED)
            else:
                # Fallback
                await self.page.click("#signup-button")
                await self.sm.handle_event(Event.SUBMITTED)
        
        except Exception as e:
            self.context.last_error = f"Submit failed: {e}"
            await self.sm.handle_event(Event.ERROR)
    
    async def _handle_captcha(self, page_result):
        """Handle CREATING_CAPTCHA state."""
        
        logger.info("Attempting to solve CAPTCHA...")
        
        solved = await self.captcha_manager.solve(self.page, timeout=120)
        
        if solved:
            logger.info("CAPTCHA solved!")
            await self.sm.handle_event(Event.CAPTCHA_SOLVED)
        else:
            logger.warning("CAPTCHA solving failed")
            await self.sm.handle_event(Event.CAPTCHA_FAILED)
    
    async def _handle_waiting(self, page_result):
        """Handle CREATING_WAITING state - waiting for result."""
        
        # Wait a bit for page to settle
        await asyncio.sleep(3)
        
        # Re-detect page
        new_result = await self.page_detector.detect(self.page)
        
        if new_result.page_type == PageType.HOME:
            # Success! Redirected to home
            await self.sm.handle_event(Event.ACCOUNT_CREATED)
        
        elif new_result.page_type == PageType.CAPTCHA:
            # CAPTCHA appeared
            await self.sm.handle_event(Event.CAPTCHA_DETECTED)
        
        elif new_result.page_type == PageType.ERROR:
            self.context.last_error = "Signup error detected"
            await self.sm.handle_event(Event.ACCOUNT_FAILED)
        
        elif new_result.page_type == PageType.SIGNUP:
            # Still on signup - check for errors
            error_elem = await self.page.query_selector(".alert-error, .validation-error")
            if error_elem:
                error_text = await error_elem.inner_text()
                self.context.last_error = f"Signup error: {error_text}"
                await self.sm.handle_event(Event.ACCOUNT_FAILED)
            else:
                # Wait more
                await asyncio.sleep(2)
        
        else:
            # Check URL for success indicators
            if "/home" in self.page.url or "/games" in self.page.url:
                await self.sm.handle_event(Event.ACCOUNT_CREATED)
    
    async def _fill_birthday(self):
        """Fill birthday dropdowns using value-based selection."""
        bd = self.identity.birthday
        
        # Roblox uses specific values for months
        month_names = [
            'January', 'February', 'March', 'April', 'May', 'June',
            'July', 'August', 'September', 'October', 'November', 'December'
        ]
        month_values = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        
        # Get month value
        try:
            month_index = month_names.index(bd['month'])
            month_value = month_values[month_index]
        except ValueError:
            month_value = bd['month'][:3]  # Fallback to first 3 chars
        
        try:
            # Month - try both value and label approaches
            logger.debug(f"Selecting month: {bd['month']} (value: {month_value})")
            try:
                await self.page.select_option("#MonthDropdown", value=month_value, timeout=5000)
            except:
                # Fallback to label
                await self.page.select_option("#MonthDropdown", label=bd['month'], timeout=5000)
            
            await asyncio.sleep(0.3)
            
            # Day - numeric value
            logger.debug(f"Selecting day: {bd['day']}")
            await self.page.select_option("#DayDropdown", value=bd['day'], timeout=5000)
            
            await asyncio.sleep(0.3)
            
            # Year - 4 digit string
            logger.debug(f"Selecting year: {bd['year']}")
            await self.page.select_option("#YearDropdown", value=bd['year'], timeout=5000)
            
        except Exception as e:
            logger.warning(f"Dropdown selection failed: {e}, trying click method")
            await self._fill_birthday_click_method(bd)
    
    async def _fill_field(self, element_type: str, value: str):
        """Fill a form field with human-like typing."""
        
        selector = await self.page_detector.find_element(self.page, element_type)
        
        if selector:
            element = await self.page.query_selector(selector)
            if element:
                await element.click()
                await asyncio.sleep(0.2)
                await self.human_input.type_humanlike(element, value)
                return
        
        # Fallback to direct selectors
        fallbacks = {
            "username_input": "#signup-username",
            "password_input": "#signup-password",
        }
        
        fallback = fallbacks.get(element_type)
        if fallback:
            await self.page.fill(fallback, value)
    
    async def _fill_birthday_click_method(self, bd: dict):
        """Fallback: Fill birthday using click-based selection."""
        logger.info("Using click-based birthday selection")
        
        try:
            # Month
            await self.page.click("#MonthDropdown")
            await asyncio.sleep(0.3)
            await self.page.click(f"#MonthDropdown option[value='{bd['month'][:3]}']")
        except:
            try:
                await self.page.click(f"text={bd['month']}")
            except:
                pass
        
        await asyncio.sleep(0.3)
        
        try:
            # Day
            await self.page.click("#DayDropdown")
            await asyncio.sleep(0.3)
            await self.page.click(f"#DayDropdown option[value='{bd['day']}']")
        except:
            try:
                await self.page.click(f"text={bd['day']}")
            except:
                pass
        
        await asyncio.sleep(0.3)
        
        try:
            # Year
            await self.page.click("#YearDropdown")
            await asyncio.sleep(0.3)
            await self.page.click(f"#YearDropdown option[value='{bd['year']}']")
        except:
            try:
                await self.page.click(f"text={bd['year']}")
            except:
                pass


# Convenience function
async def create_account(session_manager: SessionManager, db_manager: DatabaseManager,
                         proxy_manager=None, use_proxy: bool = True) -> AccountFlowResult:
    """
    Convenience function to create a single account.
    
    Usage:
        result = await create_account(session, db)
        if result.success:
            print(result.identity.username)
    """
    flow = AccountFlow(session_manager, db_manager, proxy_manager)
    return await flow.execute(use_proxy=use_proxy)
