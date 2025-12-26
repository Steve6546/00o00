"""
Mubeng Proxy Integration - Self-hosted proxy rotation.

Mubeng is a Go-based proxy rotator that:
- Tests proxy lists for validity
- Rotates through working proxies
- Provides a single endpoint for all requests

Usage:
    # 1. Install Mubeng (requires Go)
    go install github.com/kitabisa/mubeng/cmd/mubeng@latest
    
    # 2. Run proxy manager
    from scripts.mubeng_integration import MubengManager
    manager = MubengManager()
    await manager.start()
    
    # 3. Use in Playwright
    proxy = manager.get_proxy_config()
"""

import asyncio
import subprocess
import os
import shutil
import logging
import aiohttp
import json
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime

logger = logging.getLogger(__name__)

# Paths
SCRIPTS_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPTS_DIR.parent
PROXY_DIR = PROJECT_DIR / "data" / "proxies"
PROXY_DIR.mkdir(parents=True, exist_ok=True)


class ProxyFetcher:
    """
    Fetches free proxy lists from multiple sources.
    """
    
    SOURCES = [
        "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
        "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
        "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/proxy.txt",
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
        "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
    ]
    
    def __init__(self):
        self.proxies: List[str] = []
    
    async def fetch_all(self) -> List[str]:
        """Fetch proxies from all sources."""
        all_proxies = set()
        
        async with aiohttp.ClientSession() as session:
            for url in self.SOURCES:
                try:
                    async with session.get(url, timeout=10) as response:
                        if response.status == 200:
                            text = await response.text()
                            proxies = [p.strip() for p in text.split('\n') if p.strip()]
                            all_proxies.update(proxies)
                            logger.info(f"Fetched {len(proxies)} proxies from {url}")
                except Exception as e:
                    logger.warning(f"Failed to fetch from {url}: {e}")
        
        self.proxies = list(all_proxies)
        logger.info(f"Total unique proxies fetched: {len(self.proxies)}")
        return self.proxies
    
    def save_to_file(self, filepath: str = None) -> str:
        """Save proxies to file."""
        if not filepath:
            filepath = str(PROXY_DIR / "proxies.txt")
        
        with open(filepath, 'w') as f:
            for proxy in self.proxies:
                f.write(f"{proxy}\n")
        
        logger.info(f"Saved {len(self.proxies)} proxies to {filepath}")
        return filepath


class MubengManager:
    """
    Manages Mubeng proxy rotator process.
    
    Mubeng runs as a local server that:
    - Validates proxies against target site
    - Rotates through valid proxies
    - Provides single proxy endpoint
    """
    
    def __init__(self, port: int = 8080):
        self.port = port
        self.process: Optional[subprocess.Popen] = None
        self.proxy_file = str(PROXY_DIR / "proxies.txt")
        self.live_file = str(PROXY_DIR / "live_proxies.txt")
        self.mubeng_path = self._find_mubeng()
        self.is_running = False
    
    def _find_mubeng(self) -> Optional[str]:
        """Find Mubeng executable."""
        # Check common locations
        locations = [
            shutil.which("mubeng"),
            os.path.expanduser("~/go/bin/mubeng"),
            os.path.expanduser("~/go/bin/mubeng.exe"),
            "C:/Users/Go/bin/mubeng.exe",
        ]
        
        for loc in locations:
            if loc and os.path.exists(loc):
                return loc
        
        return None
    
    def is_installed(self) -> bool:
        """Check if Mubeng is installed."""
        return self.mubeng_path is not None
    
    async def check_proxies(self, target_url: str = "https://www.roblox.com") -> int:
        """
        Validate proxies against target site.
        
        Returns:
            Number of valid proxies
        """
        if not self.is_installed():
            logger.warning("Mubeng not installed. Using Python-based checking.")
            return await self._python_check_proxies(target_url)
        
        # Use Mubeng for checking
        cmd = [
            self.mubeng_path,
            "-f", self.proxy_file,
            "-o", self.live_file,
            "-c", target_url,
            "--timeout", "5s"
        ]
        
        try:
            process = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            # Count valid proxies
            if os.path.exists(self.live_file):
                with open(self.live_file, 'r') as f:
                    valid = len([l for l in f.readlines() if l.strip()])
                logger.info(f"Mubeng validated {valid} proxies")
                return valid
        
        except subprocess.TimeoutExpired:
            logger.error("Proxy validation timed out")
        except Exception as e:
            logger.error(f"Proxy validation failed: {e}")
        
        return 0
    
    async def _python_check_proxies(self, target_url: str) -> int:
        """Fallback Python-based proxy checking."""
        valid_proxies = []
        
        if not os.path.exists(self.proxy_file):
            logger.warning("No proxy file found")
            return 0
        
        with open(self.proxy_file, 'r') as f:
            proxies = [l.strip() for l in f.readlines() if l.strip()]
        
        logger.info(f"Checking {len(proxies)} proxies...")
        
        async with aiohttp.ClientSession() as session:
            for i, proxy in enumerate(proxies[:100]):  # Limit to 100
                try:
                    proxy_url = f"http://{proxy}"
                    async with session.get(
                        target_url,
                        proxy=proxy_url,
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as response:
                        if response.status == 200:
                            valid_proxies.append(proxy)
                            logger.debug(f"✓ Valid: {proxy}")
                except:
                    pass
                
                if (i + 1) % 20 == 0:
                    logger.info(f"Checked {i+1} proxies, {len(valid_proxies)} valid")
        
        # Save valid proxies
        with open(self.live_file, 'w') as f:
            for proxy in valid_proxies:
                f.write(f"{proxy}\n")
        
        logger.info(f"Found {len(valid_proxies)} valid proxies")
        return len(valid_proxies)
    
    def start_server(self) -> bool:
        """
        Start Mubeng as a proxy server.
        
        Returns:
            True if started successfully
        """
        if not self.is_installed():
            logger.warning("Mubeng not installed. Install with: go install github.com/kitabisa/mubeng/cmd/mubeng@latest")
            return False
        
        if not os.path.exists(self.live_file):
            logger.error(f"No validated proxies file: {self.live_file}")
            return False
        
        # Start Mubeng server
        cmd = [
            self.mubeng_path,
            "-f", self.live_file,
            "-a", f"127.0.0.1:{self.port}",
            "-r", "10",  # Rotate every 10 requests
            "-m", "random"  # Random rotation
        ]
        
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            self.is_running = True
            logger.info(f"🔄 Mubeng server started on port {self.port}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to start Mubeng: {e}")
            return False
    
    def stop_server(self):
        """Stop Mubeng server."""
        if self.process:
            self.process.terminate()
            self.process = None
            self.is_running = False
            logger.info("⏹️ Mubeng server stopped")
    
    def get_proxy_config(self) -> Dict:
        """
        Get proxy configuration for Playwright.
        
        Returns:
            Proxy config dict for Playwright
        """
        return {
            "server": f"http://127.0.0.1:{self.port}"
        }
    
    async def get_fallback_proxy(self) -> Optional[Dict]:
        """
        Get a proxy directly from file if Mubeng isn't running.
        
        Returns:
            Proxy config dict
        """
        proxy_file = self.live_file if os.path.exists(self.live_file) else self.proxy_file
        
        if not os.path.exists(proxy_file):
            return None
        
        with open(proxy_file, 'r') as f:
            proxies = [l.strip() for l in f.readlines() if l.strip()]
        
        if not proxies:
            return None
        
        import random
        proxy = random.choice(proxies)
        
        return {"server": f"http://{proxy}"}


# ============== Convenience Functions ==============

async def setup_proxies():
    """
    One-time setup: fetch and validate proxies.
    
    Usage:
        python -c "import asyncio; from scripts.mubeng_integration import setup_proxies; asyncio.run(setup_proxies())"
    """
    logger.info("Setting up proxy system...")
    
    # Fetch proxies
    fetcher = ProxyFetcher()
    await fetcher.fetch_all()
    fetcher.save_to_file()
    
    # Validate proxies
    manager = MubengManager()
    valid_count = await manager.check_proxies()
    
    logger.info(f"✅ Proxy setup complete. {valid_count} valid proxies ready.")
    return valid_count


async def start_proxy_server(port: int = 8080):
    """Start Mubeng proxy server."""
    manager = MubengManager(port=port)
    
    if not manager.is_installed():
        logger.error("Mubeng not installed! Install with:")
        logger.error("  go install github.com/kitabisa/mubeng/cmd/mubeng@latest")
        return None
    
    success = manager.start_server()
    if success:
        return manager
    return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(setup_proxies())
