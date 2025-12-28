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

from src.core.state_machine import (
    StateMachine, SystemState, Event, StateContext, 
    create_account_state_machine
)
from src.core.page_detector import PageDetector, PageType
from src.generators.identity_generator import IdentityGenerator, Identity
from src.core.session_manager import SessionManager
from src.behavior.human_input import HumanInput
from src.modules.captcha_solver import CaptchaManager
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
            # Already on signup page with form visible
            logger.info("Signup form detected, proceeding to fill form")
            await self.sm.handle_event(Event.FORM_READY)
        
        elif page_result.page_type == PageType.CAPTCHA:
            # CAPTCHA appeared
            await self.sm.handle_event(Event.CAPTCHA_DETECTED)
        
        elif page_result.page_type == PageType.LANDING:
            # On landing page - need to click Sign Up button to show form
            logger.info("On landing page, clicking Sign Up button to open form...")
            await self._click_signup_on_landing()
        
        else:
            # Navigate to roblox.com
            logger.info("Navigating to Roblox...")
            await self.page.goto("https://www.roblox.com", wait_until='domcontentloaded')
            await asyncio.sleep(2)
            
            # Re-detect page
            new_result = await self.page_detector.detect(self.page)
            
            if new_result.page_type == PageType.SIGNUP:
                # Form is already visible
                await self.sm.handle_event(Event.FORM_READY)
            elif new_result.page_type == PageType.LANDING:
                # Need to click signup button
                logger.info("On landing page, clicking Sign Up to open form...")
                await self._click_signup_on_landing()
            else:
                self.context.last_error = f"Unexpected page: {new_result.page_type.value}"
                await self.sm.handle_event(Event.ERROR)
    
    async def _click_signup_on_landing(self):
        """Click the Sign Up button on the landing page to reveal the signup form."""
        try:
            # Try multiple selectors for the signup button on landing page
            signup_selectors = [
                "a[href*='signup']:has-text('Sign Up')",
                "button:has-text('Sign Up')",
                ".signup-button",
                "a.signup-button",
                "[data-testid='signup-button']",
                "a[href='/signup']",
            ]
            
            clicked = False
            for selector in signup_selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element and await element.is_visible():
                        await element.click()
                        clicked = True
                        logger.info(f"Clicked signup button: {selector}")
                        break
                except Exception:
                    continue
            
            if not clicked:
                # Fallback: try pressing tab and clicking first visible button
                logger.warning("Could not find signup button, trying fallback...")
                await self.page.keyboard.press("Tab")
                await asyncio.sleep(0.5)
            
            # Wait for form to appear
            await asyncio.sleep(2)
            
            # Check if signup form appeared
            new_result = await self.page_detector.detect(self.page)
            
            if new_result.page_type == PageType.SIGNUP:
                logger.info("Signup form now visible!")
                await self.sm.handle_event(Event.FORM_READY)
            elif new_result.page_type == PageType.CAPTCHA:
                await self.sm.handle_event(Event.CAPTCHA_DETECTED)
            else:
                # Form still not visible - maybe it's an inline form on the page
                # Check for specific form elements
                username_field = await self.page.query_selector("#signup-username")
                if username_field:
                    logger.info("Found signup form elements inline")
                    await self.sm.handle_event(Event.FORM_READY)
                else:
                    self.context.last_error = "Signup form did not appear after clicking button"
                    await self.sm.handle_event(Event.ERROR)
        
        except Exception as e:
            self.context.last_error = f"Failed to open signup form: {e}"
            logger.error(f"Error clicking signup: {e}")
            await self.sm.handle_event(Event.ERROR)
    
    async def _handle_filling_form(self, page_result):
        """Handle CREATING_FILLING_FORM state with smart username handling."""
        
        if page_result.page_type != PageType.SIGNUP:
            # Lost the signup page
            self.context.last_error = "Lost signup page"
            await self.sm.handle_event(Event.ERROR)
            return
        
        try:
            # Verify form elements exist before attempting to fill
            await self._verify_form_elements()
            
            # Step 1: Fill birthday first
            logger.info("Filling birthday...")
            await self._fill_birthday()
            await asyncio.sleep(0.5)
            
            # Step 2: Fill username with smart retry
            username_accepted = await self._fill_username_smart()
            if not username_accepted:
                raise ValueError("Could not find an acceptable username")
            await asyncio.sleep(0.5)
            
            # Step 3: Fill password
            logger.info("Filling password...")
            filled = await self._fill_field_validated("password_input", self.identity.password)
            if not filled:
                raise ValueError("Failed to fill password field")
            await asyncio.sleep(0.5)
            
            # Step 4: Select gender (optional but recommended)
            await self._select_gender()
            await asyncio.sleep(0.3)
            
            # Verify fields were actually filled
            await self._verify_fields_filled()
            
            # Form complete
            logger.info("Form filled successfully!")
            await self.sm.handle_event(Event.FORM_COMPLETE)
        
        except Exception as e:
            self.context.last_error = f"Form filling failed: {e}"
            self.context.errors.append(str(e))
            logger.error(f"Form filling error: {e}")
            await self.sm.handle_event(Event.ERROR)
    
    async def _fill_username_smart(self) -> bool:
        """
        Smart username filling with Roblox suggestions fallback.
        
        Strategy:
        1. Try the generated username
        2. If rejected, check for Roblox suggestions
        3. If suggestions exist, use the first one
        4. If no suggestions, generate a new username and retry
        """
        max_attempts = 3
        current_username = self.identity.username
        
        for attempt in range(max_attempts):
            logger.info(f"Trying username (attempt {attempt + 1}): {current_username}")
            
            # Fill the username field
            filled = await self._fill_field_validated("username_input", current_username)
            if not filled:
                logger.error("Could not fill username field")
                return False
            
            # Wait for Roblox validation
            await asyncio.sleep(2)
            
            # Check if username was rejected
            username_error = await self._check_username_error()
            
            if not username_error:
                # Username accepted!
                logger.info(f"Username accepted: {current_username}")
                self.identity.username = current_username
                return True
            
            logger.warning(f"Username rejected: {username_error}")
            
            # Blacklist the rejected username
            self.identity_gen.blacklist_username(current_username, username_error)
            
            # Try to use Roblox suggestions
            suggestions = await self.identity_gen.get_roblox_suggestions(self.page)
            
            if suggestions:
                # Use the first suggestion
                current_username = suggestions[0]
                logger.info(f"Using Roblox suggestion: {current_username}")
                
                # Try to click the suggestion button
                clicked = await self.identity_gen.use_roblox_suggestion(self.page, 0)
                if clicked:
                    self.identity.username = clicked
                    self.identity.from_roblox_suggestion = True
                    return True
            else:
                # Generate a new username
                new_identity = self.identity_gen.generate()
                current_username = new_identity.username
                logger.info(f"Generated new username: {current_username}")
                
                # Clear the field and try again
                await self._clear_username_field()
        
        return False
    
    async def _check_username_error(self) -> Optional[str]:
        """Check if there's a username validation error."""
        error_selectors = [
            ".username-validation-error",
            "#signup-usernameInputValidation",
            ".input-validation-error",
            ".form-field-error",
            "[id*='username'][class*='error']"
        ]
        
        for selector in error_selectors:
            try:
                element = await self.page.query_selector(selector)
                if element and await element.is_visible():
                    text = await element.inner_text()
                    if text and text.strip():
                        return text.strip()
            except:
                continue
        
        # Also check for common error text patterns
        try:
            page_text = await self.page.content()
            error_patterns = [
                "already in use",
                "not appropriate",
                "not available",
                "invalid username",
                "username taken"
            ]
            for pattern in error_patterns:
                if pattern.lower() in page_text.lower():
                    return pattern
        except:
            pass
        
        return None
    
    async def _clear_username_field(self):
        """Clear the username input field."""
        try:
            username_input = await self.page.query_selector("#signup-username")
            if username_input:
                await username_input.click()
                await self.page.keyboard.press("Control+a")
                await self.page.keyboard.press("Delete")
                await asyncio.sleep(0.3)
        except Exception as e:
            logger.debug(f"Could not clear username field: {e}")
    
    async def _select_gender(self):
        """Select gender in the signup form."""
        try:
            gender = self.identity.gender
            
            if gender == "male":
                # Try to find and click male button
                selectors = [
                    "[data-testid='gender-male']",
                    ".gender-male",
                    "#gender-male",
                    "button[aria-label='Male']",
                    # Based on the screenshot, it might be the first gender button
                    ".gender-option:first-child",
                    "button.gender-btn:first-child"
                ]
            elif gender == "female":
                # Try to find and click female button
                selectors = [
                    "[data-testid='gender-female']",
                    ".gender-female",
                    "#gender-female",
                    "button[aria-label='Female']",
                    ".gender-option:last-child",
                    "button.gender-btn:last-child"
                ]
            else:
                # Skip gender selection if unknown
                return
            
            for selector in selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element and await element.is_visible():
                        await element.click()
                        logger.info(f"Selected gender: {gender}")
                        return
                except:
                    continue
            
            # Fallback: Try clicking gender by icon/symbol
            try:
                gender_container = await self.page.query_selector(".gender-container, .gender-options")
                if gender_container:
                    buttons = await gender_container.query_selector_all("button, div[role='button']")
                    if buttons and len(buttons) >= 2:
                        # First = male, Second = female typically
                        idx = 0 if gender == "male" else 1
                        await buttons[idx].click()
                        logger.info(f"Selected gender via container: {gender}")
                        return
            except:
                pass
            
            logger.debug(f"Could not find gender selector for {gender}")
            
        except Exception as e:
            logger.debug(f"Gender selection failed (non-critical): {e}")

    
    async def _verify_form_elements(self):
        """Verify that required form elements exist before filling."""
        required_elements = [
            ("#MonthDropdown", "Birthday Month dropdown"),
            ("#DayDropdown", "Birthday Day dropdown"),
            ("#YearDropdown", "Birthday Year dropdown"),
        ]
        
        missing = []
        for selector, name in required_elements:
            element = await self.page.query_selector(selector)
            if not element:
                missing.append(name)
        
        if missing:
            raise ValueError(f"Missing form elements: {', '.join(missing)}")
        
        # Check username field (multiple possible selectors)
        username_field = await self.page.query_selector("#signup-username")
        if not username_field:
            username_field = await self.page.query_selector("input[name='username']")
        if not username_field:
            raise ValueError("Username input field not found")
        
        logger.debug("All required form elements verified")
    
    async def _verify_fields_filled(self):
        """Verify that the username and password fields have values."""
        # Check username field has value
        username_value = await self.page.eval_on_selector(
            "#signup-username", 
            "el => el.value"
        )
        if not username_value:
            logger.warning("Username field appears empty after filling")
        
        # Check password field has value
        password_value = await self.page.eval_on_selector(
            "#signup-password",
            "el => el.value"
        )
        if not password_value:
            logger.warning("Password field appears empty after filling")
    
    async def _handle_submitting(self, page_result):
        """Handle CREATING_SUBMITTING state."""
        
        try:
            # First check for form validation errors
            error_messages = await self._check_form_errors()
            if error_messages:
                logger.error(f"Form validation errors: {error_messages}")
                self.context.last_error = f"Form validation failed: {', '.join(error_messages)}"
                await self.sm.handle_event(Event.ERROR)
                return
            
            # Find signup button
            button_selector = "#signup-button"
            button = await self.page.query_selector(button_selector)
            
            if not button:
                # Try alternative selectors
                for selector in ["button:has-text('Sign Up')", ".signup-submit-button"]:
                    button = await self.page.query_selector(selector)
                    if button:
                        button_selector = selector
                        break
            
            if not button:
                self.context.last_error = "Signup button not found"
                await self.sm.handle_event(Event.ERROR)
                return
            
            # Check if button is enabled
            is_disabled = await button.get_attribute("disabled")
            if is_disabled:
                logger.warning("Signup button is disabled - waiting for it to be enabled...")
                
                # Wait for button to become enabled (max 10 seconds)
                for _ in range(20):
                    await asyncio.sleep(0.5)
                    is_disabled = await button.get_attribute("disabled")
                    if not is_disabled:
                        break
                else:
                    # Button still disabled - check for errors
                    error_messages = await self._check_form_errors()
                    if error_messages:
                        self.context.last_error = f"Form errors: {', '.join(error_messages)}"
                    else:
                        self.context.last_error = "Signup button remained disabled (form validation failed)"
                    await self.sm.handle_event(Event.ERROR)
                    return
            
            # Button is enabled - click it
            logger.info("Clicking signup button...")
            await button.click()
            await asyncio.sleep(1)  # Wait for submission
            await self.sm.handle_event(Event.SUBMITTED)
        
        except Exception as e:
            self.context.last_error = f"Submit failed: {e}"
            await self.sm.handle_event(Event.ERROR)
    
    async def _check_form_errors(self) -> list:
        """Check for form validation error messages."""
        errors = []
        
        # Common error selectors on Roblox signup form
        error_selectors = [
            ".form-error",
            ".alert-error",
            ".validation-error",
            ".text-error",
            "[class*='error']",
            ".status-error",
            "#signup-error",
        ]
        
        for selector in error_selectors:
            try:
                elements = await self.page.query_selector_all(selector)
                for element in elements:
                    if await element.is_visible():
                        text = await element.inner_text()
                        if text and text.strip():
                            errors.append(text.strip())
            except:
                continue
        
        return errors
    
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
                return True
        
        # Fallback to direct selectors
        fallbacks = {
            "username_input": "#signup-username",
            "password_input": "#signup-password",
        }
        
        fallback = fallbacks.get(element_type)
        if fallback:
            element = await self.page.query_selector(fallback)
            if element:
                await self.page.fill(fallback, value)
                return True
        
        return False
    
    async def _fill_field_validated(self, element_type: str, value: str) -> bool:
        """
        Fill a form field with validation.
        
        Returns True if field was successfully filled, False otherwise.
        Raises ValueError if field not found at all.
        """
        selector = await self.page_detector.find_element(self.page, element_type)
        
        if selector:
            element = await self.page.query_selector(selector)
            if element and await element.is_visible():
                await element.click()
                await asyncio.sleep(0.2)
                await self.human_input.type_humanlike(element, value)
                return True
        
        # Fallback to direct selectors
        fallbacks = {
            "username_input": "#signup-username",
            "password_input": "#signup-password",
        }
        
        fallback = fallbacks.get(element_type)
        if fallback:
            element = await self.page.query_selector(fallback)
            if element and await element.is_visible():
                await element.click()
                await asyncio.sleep(0.2)
                await self.page.fill(fallback, value)
                return True
        
        # Field not found - this is an error
        logger.error(f"Form field not found: {element_type}")
        return False
    
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

