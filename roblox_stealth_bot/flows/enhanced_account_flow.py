"""
Enhanced Account Flow - Complete account creation with email verification.

This is an enhanced version that integrates all zero-cost modules:
- Free email (1secmail/Mail.tm)
- Auto proxy (GitHub lists)
- Free CAPTCHA solver

Usage:
    from flows.enhanced_account_flow import create_verified_account
    
    result = await create_verified_account(session, db)
    if result.success:
        print(f"Created: {result.identity.username}")
        print(f"Email: {result.email}")
"""

import asyncio
import logging
import time
from typing import Optional, Dict
from dataclasses import dataclass, field

from core.state_machine import (
    StateMachine, SystemState, Event, StateContext, 
    create_account_state_machine
)
from core.page_detector import PageDetector, PageType
from generators.identity_generator import IdentityGenerator, Identity
from core.session_manager import SessionManager
from behavior.human_input import HumanInput
from data.database import DatabaseManager

# Zero-cost imports
from services.free_email import FreeEmailService
from scripts.auto_proxy import AutoProxyManager
from scripts.free_captcha import solve_captcha_free, CAPTCHABypassStrategies

logger = logging.getLogger(__name__)


@dataclass
class EnhancedAccountResult:
    """Result of enhanced account creation."""
    
    success: bool
    identity: Optional[Identity] = None
    email: str = ""
    email_verified: bool = False
    account_id: Optional[int] = None
    error: str = ""
    duration_seconds: float = 0.0
    states_visited: list = field(default_factory=list)
    captcha_solved: bool = False
    proxy_used: str = ""


class EnhancedAccountFlow:
    """
    Enhanced account creation with all zero-cost features.
    
    Features:
    1. Free temporary email (1secmail)
    2. Auto-updating free proxies
    3. Free CAPTCHA solving
    4. Session persistence
    5. Email verification
    """
    
    def __init__(
        self,
        session_manager: SessionManager,
        db_manager: DatabaseManager,
        use_email: bool = True,
        use_proxy: bool = True
    ):
        self.session = session_manager
        self.db = db_manager
        self.use_email = use_email
        self.use_proxy = use_proxy
        
        # Components
        self.page_detector = PageDetector()
        self.identity_gen = IdentityGenerator(db_manager)
        
        # Zero-cost services
        self.email_service = FreeEmailService("1secmail") if use_email else None
        self.proxy_manager = AutoProxyManager() if use_proxy else None
        
        # State machine
        self.sm = create_account_state_machine()
        
        # Current state
        self.page = None
        self.context = None
        self.human_input = None
        self.identity = None
        self.email_address = None
    
    async def execute(self, with_verification: bool = True) -> EnhancedAccountResult:
        """
        Execute complete account creation flow.
        
        Args:
            with_verification: Whether to verify email after creation
            
        Returns:
            EnhancedAccountResult with all details
        """
        start_time = time.time()
        result = EnhancedAccountResult(success=False)
        
        try:
            # Step 1: Generate email
            if self.use_email and self.email_service:
                self.email_address = await self.email_service.create_inbox()
                result.email = self.email_address
                logger.info(f"📧 Email ready: {self.email_address}")
            
            # Step 2: Generate identity
            self.identity = self.identity_gen.generate()
            if self.email_address:
                self.identity.email = self.email_address
            
            logger.info(f"🎭 Identity: {self.identity.username}")
            result.identity = self.identity
            
            # Step 3: Get proxy
            proxy = None
            if self.use_proxy and self.proxy_manager:
                # Fetch fresh proxies if needed
                if self.proxy_manager.needs_refresh():
                    await self.proxy_manager.fetch_all()
                
                proxy = self.proxy_manager.get_random(validated_only=False)
                if proxy:
                    result.proxy_used = proxy.get('server', '')
                    logger.info(f"🔄 Proxy: {result.proxy_used}")
            
            # Step 4: Create browser context
            browser_context, self.page = await self.session.create_context(proxy=proxy)
            self.human_input = HumanInput(self.page)
            
            # Step 5: Warm up session (reduces CAPTCHA)
            await CAPTCHABypassStrategies.warm_up_session(self.page, duration=15)
            
            # Step 6: Setup state machine
            self.context = StateContext(
                task_type="create_account",
                username=self.identity.username,
                password=self.identity.password,
                birthday=self.identity.birthday,
                max_retries=3
            )
            self.sm.set_context(self.context)
            
            # Step 7: Run main flow
            await self.sm.handle_event(Event.START)
            
            while not self.sm.is_terminal():
                page_result = await self.page_detector.detect(self.page)
                await self._process_state(page_result, result)
                await asyncio.sleep(0.5)
                result.states_visited.append(self.sm.state.value)
            
            # Step 8: Check result
            if self.sm.state == SystemState.SUCCESS:
                result.success = True
                
                # Save to database
                account = self.db.save_account({
                    "username": self.identity.username,
                    "password": self.identity.password,
                    "email": self.email_address or "",
                    "birthday": str(self.identity.birthday),
                    "status": "created"
                })
                result.account_id = account.id
                
                # Save session for future use
                await self.session.save_session(browser_context, self.identity.username)
                
                logger.info(f"✅ Account created: {self.identity.username}")
                
                # Step 9: Email verification
                if with_verification and self.email_service and self.email_address:
                    result.email_verified = await self._verify_email()
            
            else:
                result.error = self.context.last_error or "Account creation failed"
        
        except Exception as e:
            result.error = str(e)
            logger.error(f"❌ Flow error: {e}")
        
        finally:
            if browser_context:
                await self.session.close_context(browser_context)
            
            result.duration_seconds = time.time() - start_time
            
            # Log task
            self.db.log_task(
                task_type="create_account_enhanced",
                status="success" if result.success else "failed",
                target=self.identity.username if self.identity else "",
                error_message=result.error if result.error else None,
                duration_seconds=result.duration_seconds
            )
        
        return result
    
    async def _process_state(self, page_result, result: EnhancedAccountResult):
        """Process current state."""
        state = self.sm.state
        
        if state == SystemState.NAVIGATING:
            await self._handle_navigating()
        
        elif state == SystemState.FILLING_FORMS:
            await self._handle_filling_form(page_result)
        
        elif state == SystemState.HANDLING_CAPTCHA:
            solved = await solve_captcha_free(self.page)
            result.captcha_solved = solved
            if solved:
                await self.sm.handle_event(Event.CAPTCHA_SOLVED)
            else:
                await self.sm.handle_event(Event.CAPTCHA_FAILED)
        
        elif state == SystemState.VERIFYING_RESULT:
            await self._handle_verification(page_result)
    
    async def _handle_navigating(self):
        """Navigate to signup page."""
        logger.info("📍 Navigating to signup...")
        await self.page.goto("https://www.roblox.com/account/signupredir", wait_until='domcontentloaded')
        await asyncio.sleep(3)
        
        page_result = await self.page_detector.detect(self.page)
        if page_result.page_type == PageType.SIGNUP:
            await self.sm.handle_event(Event.PAGE_LOADED)
        else:
            await self.page.goto("https://www.roblox.com", wait_until='domcontentloaded')
            await asyncio.sleep(2)
            await self.sm.handle_event(Event.PAGE_LOADED)
    
    async def _handle_filling_form(self, page_result):
        """Fill signup form."""
        logger.info("📝 Filling signup form...")
        
        try:
            # Fill birthday
            await self._fill_birthday()
            await asyncio.sleep(0.5)
            
            # Fill username
            await self._fill_field("#signup-username", self.identity.username)
            await asyncio.sleep(0.5)
            
            # Fill password
            await self._fill_field("#signup-password", self.identity.password)
            await asyncio.sleep(0.5)
            
            # Fill email if available
            if self.email_address:
                try:
                    await self._fill_field("#signup-email", self.email_address)
                except:
                    pass
            
            # Submit
            await asyncio.sleep(1)
            submit_btn = await self.page.query_selector("#signup-button, button[type='submit']")
            if submit_btn:
                await submit_btn.click()
            
            await asyncio.sleep(3)
            
            # Check for CAPTCHA
            new_result = await self.page_detector.detect(self.page)
            if new_result.page_type == PageType.CAPTCHA:
                await self.sm.handle_event(Event.CAPTCHA_DETECTED)
            else:
                await self.sm.handle_event(Event.FORM_SUBMITTED)
        
        except Exception as e:
            logger.error(f"Form fill error: {e}")
            self.context.last_error = str(e)
            await self.sm.handle_event(Event.ERROR)
    
    async def _fill_birthday(self):
        """Fill birthday dropdowns."""
        bd = self.identity.birthday
        
        month_map = {
            'January': 'Jan', 'February': 'Feb', 'March': 'Mar',
            'April': 'Apr', 'May': 'May', 'June': 'Jun',
            'July': 'Jul', 'August': 'Aug', 'September': 'Sep',
            'October': 'Oct', 'November': 'Nov', 'December': 'Dec'
        }
        
        month_value = month_map.get(bd['month'], bd['month'][:3])
        
        try:
            await self.page.select_option("#MonthDropdown", value=month_value, timeout=5000)
            await asyncio.sleep(0.3)
            await self.page.select_option("#DayDropdown", value=bd['day'], timeout=5000)
            await asyncio.sleep(0.3)
            await self.page.select_option("#YearDropdown", value=bd['year'], timeout=5000)
        except Exception as e:
            logger.debug(f"Birthday select failed: {e}")
    
    async def _fill_field(self, selector: str, value: str):
        """Fill a form field with human-like typing."""
        element = await self.page.query_selector(selector)
        if element:
            await element.click()
            await asyncio.sleep(0.2)
            await self.human_input.type_humanlike(element, value)
    
    async def _handle_verification(self, page_result):
        """Verify account creation."""
        if page_result.page_type == PageType.HOME:
            await self.sm.handle_event(Event.ACCOUNT_CREATED)
        elif "error" in self.page.url.lower() or page_result.page_type == PageType.ERROR:
            self.context.last_error = "Account creation failed"
            await self.sm.handle_event(Event.ERROR)
        else:
            await asyncio.sleep(2)
            await self.sm.handle_event(Event.ACCOUNT_CREATED)
    
    async def _verify_email(self) -> bool:
        """Wait for and click email verification."""
        logger.info("📧 Waiting for verification email...")
        
        link = await self.email_service.wait_for_verification(
            email=self.email_address,
            from_filter="roblox",
            timeout=120
        )
        
        if link:
            logger.info("✅ Verification link received!")
            try:
                await self.page.goto(link, wait_until='domcontentloaded')
                await asyncio.sleep(3)
                return True
            except Exception as e:
                logger.error(f"Failed to verify: {e}")
        
        return False


# ============== Convenience Functions ==============

async def create_verified_account(
    session_manager: SessionManager,
    db_manager: DatabaseManager,
    use_email: bool = True,
    use_proxy: bool = True
) -> EnhancedAccountResult:
    """
    One-liner to create a verified account.
    
    Usage:
        result = await create_verified_account(session, db)
    """
    flow = EnhancedAccountFlow(
        session_manager,
        db_manager,
        use_email=use_email,
        use_proxy=use_proxy
    )
    return await flow.execute(with_verification=use_email)


async def create_multiple_accounts(
    session_manager: SessionManager,
    db_manager: DatabaseManager,
    count: int = 5,
    delay_between: int = 30,
    use_email: bool = True,
    use_proxy: bool = True
) -> Dict:
    """
    Create multiple accounts with delays.
    
    Returns:
        Summary dict with success/failed counts
    """
    results = {
        "success": 0,
        "failed": 0,
        "accounts": []
    }
    
    for i in range(count):
        logger.info(f"Creating account {i+1}/{count}...")
        
        result = await create_verified_account(
            session_manager, db_manager,
            use_email=use_email, use_proxy=use_proxy
        )
        
        if result.success:
            results["success"] += 1
            results["accounts"].append({
                "username": result.identity.username,
                "email": result.email,
                "verified": result.email_verified
            })
        else:
            results["failed"] += 1
        
        if i < count - 1:
            logger.info(f"Waiting {delay_between}s...")
            await asyncio.sleep(delay_between)
    
    return results
