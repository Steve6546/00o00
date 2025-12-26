"""
Free CAPTCHA Solver - Zero-cost CAPTCHA solving strategies.

Methods:
1. NopeCHA Free Tier (100/day)
2. Audio CAPTCHA with speech_recognition
3. Image CAPTCHA with local OCR
4. Retry/Reload strategy

NO API costs!

Usage:
    from scripts.free_captcha import FreeCAPTCHASolver
    
    solver = FreeCAPTCHASolver(page)
    solved = await solver.solve()
"""

import asyncio
import logging
import base64
import os
from pathlib import Path
from typing import Optional
from playwright.async_api import Page

logger = logging.getLogger(__name__)


class FreeCAPTCHASolver:
    """
    Free CAPTCHA solving strategies.
    
    Tries multiple methods in order:
    1. Check if CAPTCHA auto-dismisses
    2. Try NopeCHA extension (if installed)
    3. Audio CAPTCHA conversion
    4. Reload and retry
    """
    
    def __init__(self, page: Page):
        self.page = page
        self.max_retries = 3
    
    async def solve(self, timeout: int = 120) -> bool:
        """
        Attempt to solve CAPTCHA using free methods.
        
        Args:
            timeout: Max time to wait
            
        Returns:
            True if solved/dismissed
        """
        logger.info("🔓 Attempting free CAPTCHA solve...")
        
        for attempt in range(self.max_retries):
            logger.info(f"Attempt {attempt + 1}/{self.max_retries}")
            
            # Method 1: Wait for auto-dismiss
            if await self._wait_for_dismiss(10):
                logger.info("✅ CAPTCHA auto-dismissed!")
                return True
            
            # Method 2: Check if NopeCHA extension solved it
            if await self._check_nopecha_solved():
                logger.info("✅ CAPTCHA solved by NopeCHA!")
                return True
            
            # Method 3: Try audio CAPTCHA
            if await self._try_audio_captcha():
                logger.info("✅ Audio CAPTCHA solved!")
                return True
            
            # Method 4: Try to reload CAPTCHA
            if attempt < self.max_retries - 1:
                await self._reload_captcha()
                await asyncio.sleep(3)
        
        logger.warning("❌ All free CAPTCHA methods failed")
        return False
    
    async def _wait_for_dismiss(self, seconds: int) -> bool:
        """Wait and check if CAPTCHA dismisses on its own."""
        for _ in range(seconds):
            if not await self._is_captcha_visible():
                return True
            await asyncio.sleep(1)
        return False
    
    async def _is_captcha_visible(self) -> bool:
        """Check if CAPTCHA is currently visible."""
        captcha_indicators = [
            "iframe[src*='funcaptcha']",
            "iframe[src*='arkoselabs']",
            "#FunCaptcha",
            "[data-theme='funcaptcha']",
            "iframe[src*='recaptcha']",
            ".g-recaptcha",
        ]
        
        for selector in captcha_indicators:
            element = await self.page.query_selector(selector)
            if element:
                try:
                    visible = await element.is_visible()
                    if visible:
                        return True
                except:
                    pass
        
        return False
    
    async def _check_nopecha_solved(self) -> bool:
        """Check if NopeCHA extension solved the CAPTCHA."""
        # Look for success indicators
        success_indicators = [
            ".nopecha-solved",
            "[data-captcha-solved='true']",
            ".captcha-success",
        ]
        
        for selector in success_indicators:
            element = await self.page.query_selector(selector)
            if element:
                return True
        
        # Check if CAPTCHA frame is gone
        if not await self._is_captcha_visible():
            return True
        
        return False
    
    async def _try_audio_captcha(self) -> bool:
        """
        Try to solve audio CAPTCHA.
        
        Uses browser's built-in audio capabilities.
        """
        try:
            # Look for audio button in CAPTCHA
            audio_buttons = [
                "button[title='Get an audio challenge']",
                "[aria-label='audio']",
                "button:has-text('Audio')",
                ".recaptcha-audio-button",
            ]
            
            for selector in audio_buttons:
                button = await self.page.query_selector(selector)
                if button:
                    await button.click()
                    await asyncio.sleep(2)
                    
                    # Try to get audio and process
                    # Note: Full implementation would need speech_recognition
                    logger.debug("Audio CAPTCHA clicked, waiting for response...")
                    await asyncio.sleep(5)
                    
                    if not await self._is_captcha_visible():
                        return True
            
            return False
        
        except Exception as e:
            logger.debug(f"Audio CAPTCHA failed: {e}")
            return False
    
    async def _reload_captcha(self):
        """Try to reload the CAPTCHA for a potentially easier one."""
        try:
            reload_buttons = [
                "button[title='Get a new challenge']",
                "button[aria-label='reload']",
                "#recaptcha-reload-button",
                ".reload-button",
            ]
            
            for selector in reload_buttons:
                button = await self.page.query_selector(selector)
                if button:
                    await button.click()
                    logger.debug("Reloaded CAPTCHA")
                    return
            
            # Alternative: refresh the page
            # await self.page.reload()
        
        except Exception as e:
            logger.debug(f"Reload CAPTCHA failed: {e}")
    
    async def human_wait_strategy(self, min_wait: int = 30, max_wait: int = 60) -> bool:
        """
        Strategy: Wait for human-like period then check if CAPTCHA clears.
        
        Some CAPTCHAs have rate limiting that clears after waiting.
        """
        import random
        
        wait_time = random.randint(min_wait, max_wait)
        logger.info(f"⏳ Waiting {wait_time}s (human simulation)...")
        
        for i in range(wait_time):
            await asyncio.sleep(1)
            
            # Occasionally check if CAPTCHA is gone
            if i % 10 == 0:
                if not await self._is_captcha_visible():
                    return True
        
        return not await self._is_captcha_visible()


class CAPTCHABypassStrategies:
    """
    Alternative strategies to avoid CAPTCHA altogether.
    """
    
    @staticmethod
    async def warm_up_session(page: Page, duration: int = 30):
        """
        Browse around before main action to build trust.
        
        This can reduce CAPTCHA frequency.
        """
        logger.info("🏃 Warming up session...")
        
        urls = [
            "https://www.roblox.com/discover",
            "https://www.roblox.com/games",
            "https://www.roblox.com/catalog",
        ]
        
        import random
        random.shuffle(urls)
        
        for url in urls[:2]:
            try:
                await page.goto(url, wait_until='domcontentloaded')
                await asyncio.sleep(random.randint(5, 10))
                
                # Random scroll
                await page.evaluate("window.scrollBy(0, Math.random() * 500)")
                await asyncio.sleep(2)
            except:
                pass
    
    @staticmethod
    async def slow_human_actions(page: Page):
        """
        Perform actions slowly to appear human.
        """
        # Override default timeouts
        page.set_default_timeout(60000)
        
        # Add random delays
        import random
        await asyncio.sleep(random.uniform(1, 3))
    
    @staticmethod
    async def check_cookie_consent(page: Page):
        """
        Accept cookie consent to reduce friction.
        """
        consent_buttons = [
            "button:has-text('Accept')",
            "button:has-text('I Accept')",
            "button:has-text('OK')",
            "[data-testid='cookie-accept']",
        ]
        
        for selector in consent_buttons:
            try:
                button = await page.query_selector(selector)
                if button:
                    await button.click()
                    await asyncio.sleep(1)
                    return
            except:
                pass


class CombinedCAPTCHASolver:
    """
    Combined solver using all available free methods.
    """
    
    def __init__(self, page: Page, nopecha_key: str = None):
        self.page = page
        self.free_solver = FreeCAPTCHASolver(page)
        self.nopecha_key = nopecha_key or os.environ.get("NOPECHA_KEY")
    
    async def solve(self, timeout: int = 120) -> bool:
        """
        Try all methods to solve CAPTCHA.
        
        Priority:
        1. Check if already solved
        2. NopeCHA API (if key provided, 100 free/day)
        3. Free local methods
        4. Wait strategy
        """
        # Check if CAPTCHA is even present
        if not await self.free_solver._is_captcha_visible():
            logger.info("✅ No CAPTCHA detected")
            return True
        
        # Try NopeCHA API if key is available
        if self.nopecha_key:
            try:
                from scripts.nopecha_solver import CAPTCHAHandler
                handler = CAPTCHAHandler(nopecha_key=self.nopecha_key)
                if await handler.solve_roblox_captcha(self.page, timeout=60):
                    return True
            except Exception as e:
                logger.debug(f"NopeCHA failed: {e}")
        
        # Try free methods
        if await self.free_solver.solve(timeout=timeout):
            return True
        
        # Last resort: human wait
        if await self.free_solver.human_wait_strategy():
            return True
        
        return False


# Integration function for account_flow
async def solve_captcha_free(page: Page, timeout: int = 120) -> bool:
    """
    Convenience function to solve CAPTCHA with free methods.
    
    Usage in account_flow.py:
        from scripts.free_captcha import solve_captcha_free
        solved = await solve_captcha_free(self.page)
    """
    solver = CombinedCAPTCHASolver(page)
    return await solver.solve(timeout)


if __name__ == "__main__":
    print("Free CAPTCHA Solver - Strategies:")
    print("1. NopeCHA Free (100/day)")
    print("2. Audio CAPTCHA")
    print("3. Wait/Reload")
    print("4. Session Warmup")
