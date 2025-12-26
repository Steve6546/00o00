"""
Auto-Updating Proxy Lists - Free proxy sources that update automatically.

Gets fresh proxies from multiple GitHub repositories that update daily.

Zero Cost - No API keys needed!

Usage:
    from scripts.auto_proxy import AutoProxyManager
    
    manager = AutoProxyManager()
    await manager.fetch_all()
    proxy = manager.get_random()
"""

import asyncio
import aiohttp
import logging
import random
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Paths
DATA_DIR = Path(__file__).parent.parent / "data" / "proxies"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class AutoProxyManager:
    """
    Auto-updating proxy manager using free GitHub proxy lists.
    
    Sources are updated daily by their maintainers.
    """
    
    # Free proxy sources (GitHub raw links - always fresh)
    SOURCES = {
        "http": [
            "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
            "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
            "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
            "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
            "https://raw.githubusercontent.com/mmpx12/proxy-list/master/http.txt",
            "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
        ],
        "socks5": [
            "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
            "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
            "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks5.txt",
        ],
        "socks4": [
            "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks4.txt",
            "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt",
        ]
    }
    
    def __init__(self, proxy_type: str = "http"):
        self.proxy_type = proxy_type
        self.proxies: List[str] = []
        self.valid_proxies: List[str] = []
        self.last_fetch: Optional[datetime] = None
        self.proxy_file = DATA_DIR / f"{proxy_type}_proxies.txt"
        self.valid_file = DATA_DIR / f"{proxy_type}_valid.txt"
    
    async def fetch_all(self) -> int:
        """
        Fetch proxies from all sources.
        
        Returns:
            Number of unique proxies fetched
        """
        all_proxies = set()
        sources = self.SOURCES.get(self.proxy_type, self.SOURCES["http"])
        
        logger.info(f"📥 Fetching {self.proxy_type} proxies from {len(sources)} sources...")
        
        async with aiohttp.ClientSession() as session:
            for url in sources:
                try:
                    async with session.get(url, timeout=15) as response:
                        if response.status == 200:
                            text = await response.text()
                            proxies = [
                                p.strip() 
                                for p in text.split('\n') 
                                if p.strip() and ':' in p
                            ]
                            all_proxies.update(proxies)
                            logger.debug(f"Fetched {len(proxies)} from {url.split('/')[-1]}")
                except Exception as e:
                    logger.debug(f"Failed: {url} - {e}")
        
        self.proxies = list(all_proxies)
        self.last_fetch = datetime.now()
        
        # Save to file
        with open(self.proxy_file, 'w') as f:
            f.write('\n'.join(self.proxies))
        
        logger.info(f"✅ Fetched {len(self.proxies)} unique proxies")
        return len(self.proxies)
    
    async def validate_proxies(
        self,
        limit: int = 50,
        target_url: str = "https://www.roblox.com",
        timeout: int = 5
    ) -> int:
        """
        Validate proxies against target site.
        
        Args:
            limit: Max proxies to validate
            target_url: Site to test against
            timeout: Connection timeout
            
        Returns:
            Number of valid proxies
        """
        if not self.proxies:
            await self.fetch_all()
        
        proxies_to_test = random.sample(self.proxies, min(limit, len(self.proxies)))
        valid = []
        
        logger.info(f"🔍 Validating {len(proxies_to_test)} proxies...")
        
        async def test_proxy(proxy: str) -> bool:
            try:
                proxy_url = f"http://{proxy}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        target_url,
                        proxy=proxy_url,
                        timeout=aiohttp.ClientTimeout(total=timeout)
                    ) as resp:
                        return resp.status == 200
            except:
                return False
        
        # Test in batches
        batch_size = 10
        for i in range(0, len(proxies_to_test), batch_size):
            batch = proxies_to_test[i:i+batch_size]
            tasks = [test_proxy(p) for p in batch]
            results = await asyncio.gather(*tasks)
            
            for proxy, is_valid in zip(batch, results):
                if is_valid:
                    valid.append(proxy)
            
            # Progress
            logger.debug(f"Tested {min(i+batch_size, len(proxies_to_test))}/{len(proxies_to_test)}")
        
        self.valid_proxies = valid
        
        # Save valid proxies
        with open(self.valid_file, 'w') as f:
            f.write('\n'.join(self.valid_proxies))
        
        logger.info(f"✅ Found {len(self.valid_proxies)} valid proxies")
        return len(self.valid_proxies)
    
    def get_random(self, validated_only: bool = True) -> Optional[Dict]:
        """
        Get a random proxy.
        
        Returns:
            Proxy config dict for Playwright
        """
        pool = self.valid_proxies if validated_only else self.proxies
        
        if not pool:
            # Try loading from file
            pool = self._load_from_file(validated_only)
        
        if not pool:
            return None
        
        proxy = random.choice(pool)
        return {"server": f"http://{proxy}"}
    
    def get_all(self, validated_only: bool = True) -> List[str]:
        """Get all proxies."""
        pool = self.valid_proxies if validated_only else self.proxies
        
        if not pool:
            pool = self._load_from_file(validated_only)
        
        return pool
    
    def _load_from_file(self, validated_only: bool) -> List[str]:
        """Load proxies from saved file."""
        file_path = self.valid_file if validated_only else self.proxy_file
        
        if file_path.exists():
            with open(file_path, 'r') as f:
                return [l.strip() for l in f.readlines() if l.strip()]
        
        return []
    
    def needs_refresh(self, max_age_hours: int = 6) -> bool:
        """Check if proxies need refreshing."""
        if not self.last_fetch:
            return True
        
        age = datetime.now() - self.last_fetch
        return age > timedelta(hours=max_age_hours)


class ProxyRotator:
    """
    Simple proxy rotator that cycles through proxies.
    """
    
    def __init__(self, manager: AutoProxyManager):
        self.manager = manager
        self.index = 0
        self.failed_proxies: set = set()
    
    def next(self) -> Optional[Dict]:
        """Get next proxy in rotation."""
        proxies = self.manager.get_all()
        
        if not proxies:
            return None
        
        # Skip failed proxies
        available = [p for p in proxies if p not in self.failed_proxies]
        
        if not available:
            # Reset failed list
            self.failed_proxies.clear()
            available = proxies
        
        self.index = (self.index + 1) % len(available)
        proxy = available[self.index]
        
        return {"server": f"http://{proxy}"}
    
    def mark_failed(self, proxy: Dict):
        """Mark a proxy as failed."""
        server = proxy.get("server", "").replace("http://", "")
        self.failed_proxies.add(server)
        logger.debug(f"Marked proxy as failed: {server}")


async def setup_free_proxies(validate: bool = True, limit: int = 30) -> AutoProxyManager:
    """
    Quick setup for free proxies.
    
    Usage:
        manager = await setup_free_proxies()
        proxy = manager.get_random()
    """
    manager = AutoProxyManager()
    await manager.fetch_all()
    
    if validate:
        await manager.validate_proxies(limit=limit)
    
    return manager


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    async def main():
        manager = await setup_free_proxies(validate=True, limit=20)
        
        print(f"\nTotal proxies: {len(manager.proxies)}")
        print(f"Valid proxies: {len(manager.valid_proxies)}")
        
        proxy = manager.get_random()
        if proxy:
            print(f"\nRandom proxy: {proxy['server']}")
    
    asyncio.run(main())
