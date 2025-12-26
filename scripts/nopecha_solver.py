"""
NopeCHA CAPTCHA Solver - Open source CAPTCHA solving using NopeCHA extension.

NopeCHA supports:
- reCAPTCHA v2/v3
- hCaptcha
- FunCaptcha (Arkose Labs) - Used by Roblox!
- Text CAPTCHA

Methods:
1. Browser Extension (recommended for Roblox)
2. API calls

Usage:
    from scripts.nopecha_solver import NopeCHASolver
    
    solver = NopeCHASolver(api_key="your_key")  # Optional key
    
    # With extension (recommended)
    context = await solver.create_context_with_extension(playwright)
    
    # With API
    token = await solver.solve_funcaptcha(public_key, site_url)
"""

import asyncio
import os
import json
import logging
import aiohttp
from pathlib import Path
from typing import Optional, Dict
from playwright.async_api import async_playwright, BrowserContext

logger = logging.getLogger(__name__)

# Extension paths
EXTENSIONS_DIR = Path(__file__).parent.parent / "extensions"
NOPECHA_DIR = EXTENSIONS_DIR / "nopecha"


class NopeCHASolver:
    """
    NopeCHA CAPTCHA solver integration.
    
    Supports two modes:
    1. Extension: Automatically solves CAPTCHAs in browser
    2. API: Programmatic solving for token injection
    """
    
    API_URL = "https://api.nopecha.com"
    
    def __init__(self, api_key: str = None):
        """
        Initialize NopeCHA solver.
        
        Args:
            api_key: NopeCHA API key (optional for extension mode)
        """
        self.api_key = api_key or os.environ.get("NOPECHA_KEY")
        self.extension_path = str(NOPECHA_DIR) if NOPECHA_DIR.exists() else None
    
    # ============== Extension Mode ==============
    
    async def create_context_with_extension(
        self,
        playwright,
        headless: bool = False,
        user_data_dir: str = None
    ) -> BrowserContext:
        """
        Create browser context with NopeCHA extension loaded.
        
        Note: Extensions require non-headless mode in Chromium.
        
        Args:
            playwright: Playwright instance
            headless: Must be False for extensions
            user_data_dir: Persistent user data directory
            
        Returns:
            BrowserContext with extension loaded
        """
        if not self.extension_path:
            raise ValueError(
                "NopeCHA extension not found! "
                "Download from: https://nopecha.com/setup#extension"
            )
        
        if headless:
            logger.warning("Extensions don't work in headless mode. Using headed mode.")
            headless = False
        
        user_data_dir = user_data_dir or str(Path.home() / ".nopecha_user_data")
        
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=headless,
            args=[
                f"--disable-extensions-except={self.extension_path}",
                f"--load-extension={self.extension_path}",
                "--disable-blink-features=AutomationControlled",
            ]
        )
        
        logger.info("✅ NopeCHA extension loaded")
        return context
    
    def is_extension_installed(self) -> bool:
        """Check if NopeCHA extension is installed."""
        return self.extension_path is not None and Path(self.extension_path).exists()
    
    # ============== API Mode ==============
    
    async def solve_funcaptcha(
        self,
        public_key: str,
        site_url: str,
        service_url: str = None,
        timeout: int = 120
    ) -> Optional[str]:
        """
        Solve FunCaptcha (Arkose Labs) via API.
        
        Args:
            public_key: Arkose public key
            site_url: Website URL
            service_url: Arkose service URL
            timeout: Max solve time
            
        Returns:
            Solving token or None
        """
        if not self.api_key:
            logger.error("NopeCHA API key required for API mode")
            return None
        
        payload = {
            "key": self.api_key,
            "type": "funcaptcha",
            "sitekey": public_key,
            "url": site_url,
        }
        
        if service_url:
            payload["service_url"] = service_url
        
        async with aiohttp.ClientSession() as session:
            try:
                # Create task
                async with session.post(
                    f"{self.API_URL}/",
                    json=payload,
                    timeout=30
                ) as response:
                    result = await response.json()
                    
                    if result.get("error"):
                        logger.error(f"NopeCHA error: {result['error']}")
                        return None
                    
                    task_id = result.get("data")
                    if not task_id:
                        logger.error("No task ID returned")
                        return None
                
                # Poll for result
                return await self._poll_result(session, task_id, timeout)
            
            except Exception as e:
                logger.error(f"FunCaptcha solve failed: {e}")
                return None
    
    async def solve_recaptcha(
        self,
        site_key: str,
        site_url: str,
        timeout: int = 120
    ) -> Optional[str]:
        """
        Solve reCAPTCHA v2/v3 via API.
        
        Args:
            site_key: reCAPTCHA site key
            site_url: Website URL
            timeout: Max solve time
            
        Returns:
            g-recaptcha-response token or None
        """
        if not self.api_key:
            logger.error("NopeCHA API key required")
            return None
        
        payload = {
            "key": self.api_key,
            "type": "recaptcha2",
            "sitekey": site_key,
            "url": site_url,
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{self.API_URL}/",
                    json=payload,
                    timeout=30
                ) as response:
                    result = await response.json()
                    
                    if result.get("error"):
                        logger.error(f"NopeCHA error: {result['error']}")
                        return None
                    
                    task_id = result.get("data")
                    if not task_id:
                        return None
                
                return await self._poll_result(session, task_id, timeout)
            
            except Exception as e:
                logger.error(f"reCAPTCHA solve failed: {e}")
                return None
    
    async def _poll_result(
        self,
        session: aiohttp.ClientSession,
        task_id: str,
        timeout: int
    ) -> Optional[str]:
        """Poll for task result."""
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            try:
                async with session.get(
                    f"{self.API_URL}/?key={self.api_key}&id={task_id}",
                    timeout=10
                ) as response:
                    result = await response.json()
                    
                    if result.get("error"):
                        if "processing" in result.get("error", "").lower():
                            await asyncio.sleep(3)
                            continue
                        logger.error(f"NopeCHA poll error: {result['error']}")
                        return None
                    
                    if result.get("data"):
                        logger.info("✅ CAPTCHA solved!")
                        return result["data"]
            
            except Exception as e:
                logger.debug(f"Poll error: {e}")
            
            await asyncio.sleep(3)
        
        logger.error("CAPTCHA solve timeout")
        return None
    
    # ============== Balance & Status ==============
    
    async def get_balance(self) -> Optional[int]:
        """Get remaining API credits."""
        if not self.api_key:
            return None
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"{self.API_URL}/balance?key={self.api_key}",
                    timeout=10
                ) as response:
                    result = await response.json()
                    return result.get("data")
            except:
                return None


class CAPTCHAHandler:
    """
    Unified CAPTCHA handler for the bot.
    
    Tries multiple solving methods in order of preference.
    """
    
    def __init__(
        self,
        nopecha_key: str = None,
        twocaptcha_key: str = None,
        capmonster_key: str = None
    ):
        self.nopecha = NopeCHASolver(nopecha_key) if nopecha_key else None
        
        # Fallback solvers
        self.twocaptcha_key = twocaptcha_key
        self.capmonster_key = capmonster_key
    
    async def solve_roblox_captcha(
        self,
        page,
        timeout: int = 120
    ) -> bool:
        """
        Solve Roblox's FunCaptcha.
        
        Args:
            page: Playwright page
            timeout: Max solve time
            
        Returns:
            True if solved
        """
        logger.info("Attempting to solve Roblox CAPTCHA...")
        
        # Method 1: Try NopeCHA extension (auto-solves)
        if self.nopecha and self.nopecha.is_extension_installed():
            logger.info("Using NopeCHA extension (auto-solve)...")
            
            # Wait for extension to solve
            for _ in range(timeout // 5):
                # Check if CAPTCHA is gone
                captcha = await page.query_selector("#FunCaptcha, [data-theme='funcaptcha']")
                if not captcha:
                    logger.info("✅ CAPTCHA solved by extension!")
                    return True
                
                # Check for success indicator
                success = await page.query_selector(".captcha-success, [data-captcha='solved']")
                if success:
                    logger.info("✅ CAPTCHA solved!")
                    return True
                
                await asyncio.sleep(5)
            
            logger.warning("Extension solve timeout")
        
        # Method 2: Try NopeCHA API
        if self.nopecha and self.nopecha.api_key:
            logger.info("Using NopeCHA API...")
            
            # Extract CAPTCHA info
            captcha_info = await self._extract_funcaptcha_info(page)
            if captcha_info:
                token = await self.nopecha.solve_funcaptcha(
                    public_key=captcha_info['public_key'],
                    site_url=captcha_info['site_url'],
                    timeout=timeout
                )
                
                if token:
                    # Inject token
                    return await self._inject_funcaptcha_token(page, token)
        
        # Method 3: Fallback to 2Captcha/CapMonster
        # ... (use existing captcha_solver.py logic)
        
        logger.error("All CAPTCHA solving methods failed")
        return False
    
    async def _extract_funcaptcha_info(self, page) -> Optional[Dict]:
        """Extract FunCaptcha public key from page."""
        try:
            # Try to find the public key
            scripts = await page.query_selector_all("script")
            for script in scripts:
                content = await script.inner_text()
                if "public_key" in content.lower() or "arkoselabs" in content.lower():
                    # Parse the public key
                    import re
                    match = re.search(r'public_key["\']?\s*[:=]\s*["\']([A-Za-z0-9-]+)', content)
                    if match:
                        return {
                            "public_key": match.group(1),
                            "site_url": page.url
                        }
            
            # Try data attributes
            captcha_elem = await page.query_selector("[data-pkey]")
            if captcha_elem:
                pkey = await captcha_elem.get_attribute("data-pkey")
                if pkey:
                    return {"public_key": pkey, "site_url": page.url}
        
        except Exception as e:
            logger.debug(f"Failed to extract CAPTCHA info: {e}")
        
        return None
    
    async def _inject_funcaptcha_token(self, page, token: str) -> bool:
        """Inject solved CAPTCHA token into page."""
        try:
            await page.evaluate(f"""
                (function() {{
                    var input = document.querySelector('input[name="fc-token"]');
                    if (input) {{
                        input.value = '{token}';
                        return true;
                    }}
                    
                    // Try to find and fill any funcaptcha token field
                    var hidden = document.querySelector('[id*="FunCaptcha"] input[type="hidden"]');
                    if (hidden) {{
                        hidden.value = '{token}';
                        return true;
                    }}
                    
                    return false;
                }})()
            """)
            
            logger.info("✅ Token injected")
            return True
        
        except Exception as e:
            logger.error(f"Token injection failed: {e}")
            return False


# ============== Setup Instructions ==============

NOPECHA_SETUP = """
# NopeCHA Setup Instructions

## Option 1: Browser Extension (Recommended for Roblox)

1. Download extension from: https://nopecha.com/setup#extension
2. Extract to: extensions/nopecha/
3. The bot will auto-load it

## Option 2: API Key

1. Get free API key: https://nopecha.com
2. Set environment variable: NOPECHA_KEY=your_key
3. Or pass to constructor: NopeCHASolver(api_key="your_key")

## Free Tier Limits
- 100 CAPTCHAs/day free
- No credit card required

## Pricing (if you need more)
- Standard: $2.99/1000 solves
- Pro: $0.99/1000 solves (subscription)
"""


def print_setup():
    print(NOPECHA_SETUP)


if __name__ == "__main__":
    print_setup()
