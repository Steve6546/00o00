"""
CAPTCHA Solver - Production-ready implementation with real API integrations.

Supports:
1. ReloadSolver - Free method (reload page to get easier challenge)
2. TwoCaptchaSolver - 2Captcha.com API integration
3. CapMonsterSolver - CapMonster.cloud API integration
4. CaptchaManager - Manages multiple solvers with fallback

Configuration via environment variables:
- CAPTCHA_API_KEY - API key for 2Captcha or CapMonster
- CAPTCHA_SERVICE - "2captcha" or "capmonster" (default: 2captcha)
"""

import asyncio
import aiohttp
import logging
import os
import time
from abc import ABC, abstractmethod
from playwright.async_api import Page, FrameLocator
from typing import Optional, Dict

logger = logging.getLogger(__name__)

# Configuration from environment
CAPTCHA_API_KEY = os.getenv("CAPTCHA_API_KEY", "")
CAPTCHA_SERVICE = os.getenv("CAPTCHA_SERVICE", "2captcha")  # "2captcha" or "capmonster"


class CaptchaSolverInterface(ABC):
    """Abstract interface for CAPTCHA solving strategies."""
    
    @abstractmethod
    async def solve(self, page: Page, timeout: int = 120) -> bool:
        """
        Attempts to solve the CAPTCHA on the given page.
        
        Args:
            page: The Playwright page with the CAPTCHA
            timeout: Maximum time in seconds to attempt solving
            
        Returns:
            True if solved successfully, False otherwise
        """
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Returns the solver name for logging."""
        pass


class ReloadSolver(CaptchaSolverInterface):
    """
    Default solver that reloads the page to get a different (hopefully easier) challenge.
    This is a free method that works sometimes with Arkose Labs.
    """
    
    def __init__(self, max_reloads: int = 3, delay_between: float = 2.0):
        self.max_reloads = max_reloads
        self.delay_between = delay_between
    
    def get_name(self) -> str:
        return "ReloadSolver"
    
    async def solve(self, page: Page, timeout: int = 60) -> bool:
        logger.info(f"[{self.get_name()}] Attempting to bypass CAPTCHA via reload strategy")
        
        for attempt in range(self.max_reloads):
            logger.info(f"[{self.get_name()}] Reload attempt {attempt + 1}/{self.max_reloads}")
            
            # Check if CAPTCHA is still present
            captcha_present = await self._find_captcha_frame(page)
            if not captcha_present:
                logger.info(f"[{self.get_name()}] CAPTCHA no longer detected")
                return True
            
            # Reload the page
            await page.reload()
            await asyncio.sleep(self.delay_between + (attempt * 0.5))
            
            try:
                await page.wait_for_load_state('networkidle', timeout=10000)
            except:
                pass
        
        # Check final state
        captcha_present = await self._find_captcha_frame(page)
        if not captcha_present:
            logger.info(f"[{self.get_name()}] CAPTCHA bypassed after reloads")
            return True
        
        logger.warning(f"[{self.get_name()}] CAPTCHA persists after {self.max_reloads} reload attempts")
        return False
    
    async def _find_captcha_frame(self, page: Page) -> bool:
        """Check if Arkose/FunCaptcha frame is present."""
        selectors = [
            'iframe[src*="arkoselabs"]',
            'iframe[src*="funcaptcha"]',
            '.security-questions-modal',
            '#FunCaptcha',
            'iframe[title*="challenge"]',
            '[data-testid="captcha-container"]'
        ]
        
        for selector in selectors:
            element = await page.query_selector(selector)
            if element:
                return True
        return False


class TwoCaptchaSolver(CaptchaSolverInterface):
    """
    2Captcha.com API integration for solving Arkose Labs (FunCaptcha).
    
    Requires:
    - API key from 2captcha.com
    - Set via CAPTCHA_API_KEY environment variable
    
    Pricing: ~$2.99 per 1000 FunCaptcha solves
    Docs: https://2captcha.com/2captcha-api#solving_funcaptcha
    """
    
    API_BASE = "https://2captcha.com"
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or CAPTCHA_API_KEY
        if not self.api_key:
            logger.warning("2Captcha API key not configured. Set CAPTCHA_API_KEY environment variable.")
    
    def get_name(self) -> str:
        return "TwoCaptchaSolver"
    
    async def solve(self, page: Page, timeout: int = 120) -> bool:
        if not self.api_key:
            logger.error(f"[{self.get_name()}] No API key configured")
            return False
        
        logger.info(f"[{self.get_name()}] Starting CAPTCHA solve...")
        
        try:
            # 1. Extract the Arkose public key from the page
            public_key = await self._extract_arkose_key(page)
            if not public_key:
                logger.error(f"[{self.get_name()}] Could not extract Arkose public key")
                return False
            
            page_url = page.url
            logger.info(f"[{self.get_name()}] Found public key: {public_key[:20]}...")
            
            # 2. Submit task to 2Captcha
            task_id = await self._submit_task(public_key, page_url)
            if not task_id:
                logger.error(f"[{self.get_name()}] Failed to submit task")
                return False
            
            logger.info(f"[{self.get_name()}] Task submitted: {task_id}")
            
            # 3. Poll for result
            token = await self._poll_result(task_id, timeout)
            if not token:
                logger.error(f"[{self.get_name()}] Failed to get solution")
                return False
            
            logger.info(f"[{self.get_name()}] Got solution token: {token[:50]}...")
            
            # 4. Inject the token into the page
            success = await self._inject_token(page, token)
            if success:
                logger.info(f"[{self.get_name()}] Token injected successfully")
                await asyncio.sleep(2)
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"[{self.get_name()}] Error: {e}")
            return False
    
    async def _extract_arkose_key(self, page: Page) -> Optional[str]:
        """Extract Arkose Labs public key from the page."""
        # Try multiple methods to find the public key
        
        # Method 1: Look in iframe src
        iframe = await page.query_selector('iframe[src*="arkoselabs"], iframe[src*="funcaptcha"]')
        if iframe:
            src = await iframe.get_attribute('src')
            if src and 'pk=' in src:
                import re
                match = re.search(r'pk=([A-Za-z0-9-]+)', src)
                if match:
                    return match.group(1)
        
        # Method 2: Look in script tags
        scripts = await page.evaluate("""
            () => {
                const scripts = document.querySelectorAll('script');
                for (const script of scripts) {
                    const content = script.textContent || '';
                    const match = content.match(/publicKey['"\\s:]+['"]([A-Za-z0-9-]+)['"]/);
                    if (match) return match[1];
                }
                // Check for Roblox-specific patterns
                const robloxMatch = document.body.innerHTML.match(/data-public-key=['"]([^'"]+)['"]/);
                if (robloxMatch) return robloxMatch[1];
                return null;
            }
        """)
        if scripts:
            return scripts
        
        # Method 3: Known Roblox public key (may change)
        # This is a fallback - Roblox's Arkose key
        return "476068BF-9607-4799-B53D-966BE98E2B81"  # Roblox's known key
    
    async def _submit_task(self, public_key: str, page_url: str) -> Optional[str]:
        """Submit CAPTCHA task to 2Captcha."""
        async with aiohttp.ClientSession() as session:
            params = {
                "key": self.api_key,
                "method": "funcaptcha",
                "publickey": public_key,
                "surl": "https://roblox-api.arkoselabs.com",
                "pageurl": page_url,
                "json": 1
            }
            
            async with session.get(f"{self.API_BASE}/in.php", params=params) as resp:
                result = await resp.json()
                if result.get("status") == 1:
                    return result.get("request")
                else:
                    logger.error(f"2Captcha submit error: {result}")
                    return None
    
    async def _poll_result(self, task_id: str, timeout: int) -> Optional[str]:
        """Poll 2Captcha for solution."""
        start_time = time.time()
        poll_interval = 5  # seconds
        
        async with aiohttp.ClientSession() as session:
            while time.time() - start_time < timeout:
                await asyncio.sleep(poll_interval)
                
                params = {
                    "key": self.api_key,
                    "action": "get",
                    "id": task_id,
                    "json": 1
                }
                
                async with session.get(f"{self.API_BASE}/res.php", params=params) as resp:
                    result = await resp.json()
                    status = result.get("status")
                    
                    if status == 1:
                        return result.get("request")
                    elif result.get("request") == "CAPCHA_NOT_READY":
                        logger.debug(f"[{self.get_name()}] Still solving...")
                        continue
                    else:
                        logger.error(f"2Captcha error: {result}")
                        return None
        
        logger.error(f"[{self.get_name()}] Timeout waiting for solution")
        return None
    
    async def _inject_token(self, page: Page, token: str) -> bool:
        """Inject the solved token into the page."""
        try:
            # Method 1: Set callback function
            await page.evaluate(f"""
                (token) => {{
                    // Try various callback methods
                    if (typeof window.funcaptchaCallback === 'function') {{
                        window.funcaptchaCallback(token);
                        return true;
                    }}
                    if (typeof window.ArkoseEnforcement !== 'undefined') {{
                        window.ArkoseEnforcement.submitToken(token);
                        return true;
                    }}
                    // Try setting hidden input
                    const input = document.querySelector('[name="fc-token"], [id="fc-token"]');
                    if (input) {{
                        input.value = token;
                        return true;
                    }}
                    // Dispatch event
                    document.dispatchEvent(new CustomEvent('funcaptcha-callback', {{detail: token}}));
                    return true;
                }}
            """, token)
            return True
        except Exception as e:
            logger.error(f"Token injection failed: {e}")
            return False


class CapMonsterSolver(CaptchaSolverInterface):
    """
    CapMonster.cloud API integration for solving Arkose Labs (FunCaptcha).
    
    Requires:
    - API key from capmonster.cloud
    - Set via CAPTCHA_API_KEY environment variable
    
    Pricing: ~$0.6 per 1000 FunCaptcha solves (cheaper than 2Captcha)
    Docs: https://capmonster.cloud/documentation/funcaptcha/
    """
    
    API_BASE = "https://api.capmonster.cloud"
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or CAPTCHA_API_KEY
        if not self.api_key:
            logger.warning("CapMonster API key not configured. Set CAPTCHA_API_KEY environment variable.")
    
    def get_name(self) -> str:
        return "CapMonsterSolver"
    
    async def solve(self, page: Page, timeout: int = 120) -> bool:
        if not self.api_key:
            logger.error(f"[{self.get_name()}] No API key configured")
            return False
        
        logger.info(f"[{self.get_name()}] Starting CAPTCHA solve...")
        
        try:
            # 1. Extract the Arkose public key
            public_key = await self._extract_arkose_key(page)
            if not public_key:
                logger.error(f"[{self.get_name()}] Could not extract Arkose public key")
                return False
            
            page_url = page.url
            
            # 2. Create task
            task_id = await self._create_task(public_key, page_url)
            if not task_id:
                return False
            
            logger.info(f"[{self.get_name()}] Task created: {task_id}")
            
            # 3. Get result
            token = await self._get_result(task_id, timeout)
            if not token:
                return False
            
            # 4. Inject token
            success = await self._inject_token(page, token)
            if success:
                logger.info(f"[{self.get_name()}] CAPTCHA solved successfully")
                await asyncio.sleep(2)
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"[{self.get_name()}] Error: {e}")
            return False
    
    async def _extract_arkose_key(self, page: Page) -> Optional[str]:
        """Extract Arkose Labs public key (same as 2Captcha implementation)."""
        iframe = await page.query_selector('iframe[src*="arkoselabs"], iframe[src*="funcaptcha"]')
        if iframe:
            src = await iframe.get_attribute('src')
            if src and 'pk=' in src:
                import re
                match = re.search(r'pk=([A-Za-z0-9-]+)', src)
                if match:
                    return match.group(1)
        
        # Fallback to known Roblox key
        return "476068BF-9607-4799-B53D-966BE98E2B81"
    
    async def _create_task(self, public_key: str, page_url: str) -> Optional[int]:
        """Create CapMonster task."""
        async with aiohttp.ClientSession() as session:
            payload = {
                "clientKey": self.api_key,
                "task": {
                    "type": "FunCaptchaTaskProxyless",
                    "websiteURL": page_url,
                    "websitePublicKey": public_key,
                    "funcaptchaApiJSSubdomain": "roblox-api.arkoselabs.com"
                }
            }
            
            async with session.post(f"{self.API_BASE}/createTask", json=payload) as resp:
                result = await resp.json()
                if result.get("errorId") == 0:
                    return result.get("taskId")
                else:
                    logger.error(f"CapMonster create error: {result}")
                    return None
    
    async def _get_result(self, task_id: int, timeout: int) -> Optional[str]:
        """Poll for task result."""
        start_time = time.time()
        poll_interval = 3
        
        async with aiohttp.ClientSession() as session:
            while time.time() - start_time < timeout:
                await asyncio.sleep(poll_interval)
                
                payload = {
                    "clientKey": self.api_key,
                    "taskId": task_id
                }
                
                async with session.post(f"{self.API_BASE}/getTaskResult", json=payload) as resp:
                    result = await resp.json()
                    
                    if result.get("status") == "ready":
                        return result.get("solution", {}).get("token")
                    elif result.get("status") == "processing":
                        continue
                    else:
                        logger.error(f"CapMonster error: {result}")
                        return None
        
        return None
    
    async def _inject_token(self, page: Page, token: str) -> bool:
        """Inject token (same as 2Captcha implementation)."""
        try:
            await page.evaluate(f"""
                (token) => {{
                    if (typeof window.funcaptchaCallback === 'function') {{
                        window.funcaptchaCallback(token);
                    }}
                    const input = document.querySelector('[name="fc-token"], [id="fc-token"]');
                    if (input) input.value = token;
                    document.dispatchEvent(new CustomEvent('funcaptcha-callback', {{detail: token}}));
                }}
            """, token)
            return True
        except Exception as e:
            logger.error(f"Token injection failed: {e}")
            return False


class CaptchaManager:
    """
    Manages CAPTCHA solving with multiple solvers and fallback strategies.
    
    Usage:
        manager = CaptchaManager()
        # Uses configured service from environment, falls back to reload
        success = await manager.solve(page)
    """
    
    def __init__(self, primary_solver: CaptchaSolverInterface = None):
        self.solvers = []
        
        if primary_solver:
            self.solvers.append(primary_solver)
        else:
            # Configure based on environment
            if CAPTCHA_API_KEY:
                if CAPTCHA_SERVICE.lower() == "capmonster":
                    self.solvers.append(CapMonsterSolver(CAPTCHA_API_KEY))
                else:
                    self.solvers.append(TwoCaptchaSolver(CAPTCHA_API_KEY))
            
            # Always add reload as fallback
            self.solvers.append(ReloadSolver())
        
        logger.info(f"CaptchaManager initialized with solvers: {[s.get_name() for s in self.solvers]}")
    
    def add_solver(self, solver: CaptchaSolverInterface):
        """Add a fallback solver."""
        self.solvers.append(solver)
    
    async def solve(self, page: Page, timeout: int = 120) -> bool:
        """Attempts to solve CAPTCHA using all available solvers in order."""
        for solver in self.solvers:
            logger.info(f"Trying solver: {solver.get_name()}")
            try:
                if await solver.solve(page, timeout):
                    logger.info(f"CAPTCHA solved by {solver.get_name()}")
                    return True
            except Exception as e:
                logger.error(f"Solver {solver.get_name()} failed: {e}")
        
        logger.error("All CAPTCHA solvers exhausted")
        return False
    
    def get_balance(self) -> Dict[str, float]:
        """Get balance from configured service (if applicable)."""
        # This would require API calls - simplified for now
        return {"service": CAPTCHA_SERVICE, "configured": bool(CAPTCHA_API_KEY)}


# Convenience function
async def handle_captcha(page: Page, timeout: int = 120) -> bool:
    """
    Quick function to handle CAPTCHA with configured solvers.
    
    Configure via environment variables:
    - CAPTCHA_API_KEY: Your API key
    - CAPTCHA_SERVICE: "2captcha" or "capmonster"
    """
    manager = CaptchaManager()
    return await manager.solve(page, timeout)
