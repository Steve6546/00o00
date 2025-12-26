"""
Session Manager - Advanced browser session management with persistence.

Key features:
- storage_state support for session persistence
- Automatic session save/load
- Fingerprint management
- Proxy support
"""

import asyncio
import os
import json
from pathlib import Path
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from core.stealth_layer import StealthLayer
from fake_useragent import UserAgent
import logging

logger = logging.getLogger(__name__)

# Session storage directory
SESSIONS_DIR = Path(__file__).parent.parent / "sessions"
SESSIONS_DIR.mkdir(exist_ok=True)


class SessionManager:
    """
    Advanced session manager with persistence support.
    
    Features:
    - Save/load browser sessions using storage_state
    - Stealth fingerprinting
    - Proxy rotation support
    - Context pooling
    """
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.stealth_layer = StealthLayer()
        self.playwright = None
        self.browser: Browser = None
        self.ua = UserAgent()
        self.active_contexts: dict = {}  # username -> context
    
    async def start(self):
        """Starts the Playwright engine and browser."""
        self.playwright = await async_playwright().start()
        
        # Launch options for stealth
        args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-accelerated-2d-canvas",
            "--no-first-run",
            "--no-zygote",
            "--disable-gpu"
        ]
        
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=args
        )
        logger.info("Browser session started.")
    
    async def create_context(self, proxy=None, username: str = None) -> tuple:
        """
        Creates a new browser context with optional session loading.
        
        Args:
            proxy: Proxy configuration dict
            username: If provided, try to load saved session
            
        Returns:
            tuple: (BrowserContext, Page)
        """
        fingerprint = self.stealth_layer.get_random_fingerprint()
        
        # Prepare context options
        context_options = {
            "user_agent": fingerprint['userAgent'],
            "viewport": fingerprint['screen'],
            "locale": fingerprint['locale'],
            "timezone_id": fingerprint['timezone'],
            "has_touch": True,
            "is_mobile": False,
            "device_scale_factor": 1.0,
        }
        
        # Add proxy if provided
        if proxy:
            context_options["proxy"] = {
                "server": proxy.get('server'),
                "username": proxy.get('username'),
                "password": proxy.get('password')
            }
        
        # Try to load existing session
        if username:
            session_file = self.get_session_path(username)
            if session_file.exists():
                logger.info(f"Loading saved session for {username}")
                context_options["storage_state"] = str(session_file)
        
        context = await self.browser.new_context(**context_options)
        
        # Apply stealth
        await self.stealth_layer.apply_stealth(context, fingerprint)
        
        page = await context.new_page()
        
        # Track context if username provided
        if username:
            self.active_contexts[username] = context
        
        return context, page
    
    async def create_context_with_session(self, username: str, proxy=None) -> tuple:
        """
        Create context and automatically load session if exists.
        Shorthand for create_context with username.
        """
        return await self.create_context(proxy=proxy, username=username)
    
    async def save_session(self, context: BrowserContext, username: str):
        """
        Save browser session to file.
        
        This saves:
        - Cookies
        - localStorage
        - sessionStorage
        - Authentication state
        """
        session_file = self.get_session_path(username)
        
        try:
            await context.storage_state(path=str(session_file))
            logger.info(f"Session saved for {username}: {session_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to save session for {username}: {e}")
            return False
    
    async def load_session(self, username: str) -> dict:
        """
        Load session data from file.
        
        Returns:
            Session data dict or None if not found
        """
        session_file = self.get_session_path(username)
        
        if session_file.exists():
            try:
                with open(session_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load session for {username}: {e}")
        
        return None
    
    def has_session(self, username: str) -> bool:
        """Check if user has a saved session."""
        return self.get_session_path(username).exists()
    
    def get_session_path(self, username: str) -> Path:
        """Get path to session file for a user."""
        # Sanitize username for filename
        safe_name = "".join(c for c in username if c.isalnum() or c in "_-")
        return SESSIONS_DIR / f"{safe_name}_session.json"
    
    async def validate_session(self, username: str) -> bool:
        """
        Check if saved session is still valid.
        
        Returns:
            True if session is valid and logged in
        """
        if not self.has_session(username):
            return False
        
        try:
            context, page = await self.create_context(username=username)
            
            # Navigate to Roblox home to check login status
            await page.goto("https://www.roblox.com/home", wait_until='domcontentloaded')
            await asyncio.sleep(2)
            
            # Check if we're logged in (look for profile element)
            logged_in = await page.query_selector("#nav-profile, .age-bracket-label")
            
            await self.close_context(context)
            
            if logged_in:
                logger.info(f"Session for {username} is valid")
                return True
            else:
                logger.warning(f"Session for {username} is expired")
                return False
        
        except Exception as e:
            logger.error(f"Session validation failed for {username}: {e}")
            return False
    
    def delete_session(self, username: str):
        """Delete saved session for a user."""
        session_file = self.get_session_path(username)
        if session_file.exists():
            session_file.unlink()
            logger.info(f"Session deleted for {username}")
    
    def list_sessions(self) -> list:
        """List all saved sessions."""
        sessions = []
        for f in SESSIONS_DIR.glob("*_session.json"):
            username = f.stem.replace("_session", "")
            sessions.append({
                "username": username,
                "file": str(f),
                "size": f.stat().st_size,
                "modified": f.stat().st_mtime
            })
        return sessions
    
    async def close_context(self, context: BrowserContext):
        """Closes a browser context."""
        # Remove from active contexts
        for username, ctx in list(self.active_contexts.items()):
            if ctx == context:
                del self.active_contexts[username]
                break
        
        await context.close()
    
    async def stop(self):
        """Stops the browser and Playwright engine."""
        # Close all active contexts
        for username, context in list(self.active_contexts.items()):
            try:
                await context.close()
            except:
                pass
        self.active_contexts.clear()
        
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Browser session stopped.")


# Utility functions
def get_all_sessions() -> list:
    """Get list of all saved sessions."""
    sessions = []
    for f in SESSIONS_DIR.glob("*_session.json"):
        username = f.stem.replace("_session", "")
        sessions.append(username)
    return sessions


def clear_all_sessions():
    """Delete all saved sessions."""
    for f in SESSIONS_DIR.glob("*_session.json"):
        f.unlink()
    logger.info("All sessions cleared")
