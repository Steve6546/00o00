import requests
import random
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


class RotationStrategy(Enum):
    RANDOM = "random"
    ROUND_ROBIN = "round_robin"
    LEAST_USED = "least_used"


class ProxyManager:
    """
    Manages proxy fetching, validation, rotation, and health tracking.
    """
    
    def __init__(self, check_url: str = "https://httpbin.org/ip", db_manager=None):
        self.proxies: List[Dict] = []
        self.check_url = check_url
        self.working_proxies: List[Dict] = []
        self.db_manager = db_manager
        self.rotation_strategy = RotationStrategy.RANDOM
        self.round_robin_index = 0
        self.usage_count: Dict[str, int] = {}
        
    def set_rotation_strategy(self, strategy: RotationStrategy):
        """Set the proxy rotation strategy."""
        self.rotation_strategy = strategy
        logger.info(f"Proxy rotation strategy set to: {strategy.value}")

    def fetch_free_proxies(self, sources: List[str] = None):
        """
        Fetches free proxies from public APIs.
        Note: Free proxies are often unreliable and may be blacklisted.
        """
        if sources is None:
            sources = [
                "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all",
                "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
            ]
        
        logger.info("Fetching free proxies...")
        all_proxies = []
        
        for source in sources:
            try:
                response = requests.get(source, timeout=15)
                if response.status_code == 200:
                    proxy_list = response.text.strip().splitlines()
                    for p in proxy_list:
                        p = p.strip()
                        if p and ':' in p:
                            all_proxies.append({
                                "server": f"http://{p}",
                                "username": "",
                                "password": "",
                                "source": source,
                                "latency_ms": None,
                                "last_checked": None
                            })
                    logger.info(f"Fetched {len(proxy_list)} proxies from {source}")
            except Exception as e:
                logger.warning(f"Failed to fetch from {source}: {e}")
        
        # Deduplicate by server
        seen = set()
        unique = []
        for p in all_proxies:
            if p['server'] not in seen:
                seen.add(p['server'])
                unique.append(p)
        
        self.proxies = unique
        logger.info(f"Total unique proxies: {len(self.proxies)}")
        return self.proxies

    def load_custom_proxies(self, proxies: List[Dict]):
        """
        Load custom proxies (e.g., from paid providers).
        
        Format: [{"server": "http://ip:port", "username": "user", "password": "pass"}, ...]
        """
        for p in proxies:
            if 'server' in p:
                if not p.get('username'):
                    p['username'] = ""
                if not p.get('password'):
                    p['password'] = ""
                p['latency_ms'] = None
                p['last_checked'] = None
                self.proxies.append(p)
        
        logger.info(f"Loaded {len(proxies)} custom proxies")

    def validate_proxy(self, proxy: Dict) -> tuple:
        """
        Validates a proxy and measures latency.
        Returns (proxy, is_working, latency_ms)
        """
        proxies_config = {
            "http": proxy['server'],
            "https": proxy['server'],
        }
        
        if proxy.get('username') and proxy.get('password'):
            # Format with auth
            server = proxy['server']
            auth = f"{proxy['username']}:{proxy['password']}"
            if '://' in server:
                protocol, rest = server.split('://', 1)
                proxies_config = {
                    "http": f"{protocol}://{auth}@{rest}",
                    "https": f"{protocol}://{auth}@{rest}",
                }
        
        try:
            start = time.time()
            resp = requests.get(self.check_url, proxies=proxies_config, timeout=10)
            latency_ms = int((time.time() - start) * 1000)
            
            if resp.status_code == 200:
                proxy['latency_ms'] = latency_ms
                proxy['last_checked'] = time.time()
                return (proxy, True, latency_ms)
        except Exception as e:
            logger.debug(f"Proxy {proxy['server']} failed: {e}")
        
        return (proxy, False, None)

    def check_proxies(self, max_workers: int = 20, limit: int = None):
        """
        Validates proxies in parallel and populates working_proxies.
        
        Args:
            max_workers: Number of parallel validation threads
            limit: Optional limit on number of proxies to check
        """
        to_check = self.proxies[:limit] if limit else self.proxies
        logger.info(f"Validating {len(to_check)} proxies with {max_workers} workers...")
        
        self.working_proxies = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(self.validate_proxy, to_check))
        
        for proxy, is_working, latency in results:
            if is_working:
                self.working_proxies.append(proxy)
                # Track in database if available
                if self.db_manager:
                    try:
                        self.db_manager.update_proxy_health(proxy['server'], True, latency)
                    except:
                        pass
        
        # Sort by latency (fastest first)
        self.working_proxies.sort(key=lambda p: p.get('latency_ms', 9999))
        
        logger.info(f"Found {len(self.working_proxies)} working proxies")
        if self.working_proxies:
            avg_latency = sum(p['latency_ms'] for p in self.working_proxies) / len(self.working_proxies)
            logger.info(f"Average latency: {avg_latency:.0f}ms")
        
        return self.working_proxies

    def get_proxy(self) -> Optional[Dict]:
        """
        Returns a proxy based on the current rotation strategy.
        Automatically refreshes if pool is empty.
        """
        if not self.working_proxies:
            logger.warning("No working proxies available. Attempting refresh...")
            self.fetch_free_proxies()
            self.check_proxies(limit=50)  # Quick check
        
        if not self.working_proxies:
            logger.error("No working proxies found after refresh")
            return None
        
        proxy = None
        
        if self.rotation_strategy == RotationStrategy.RANDOM:
            proxy = random.choice(self.working_proxies)
            
        elif self.rotation_strategy == RotationStrategy.ROUND_ROBIN:
            proxy = self.working_proxies[self.round_robin_index % len(self.working_proxies)]
            self.round_robin_index += 1
            
        elif self.rotation_strategy == RotationStrategy.LEAST_USED:
            # Find proxy with least usage
            min_usage = float('inf')
            for p in self.working_proxies:
                usage = self.usage_count.get(p['server'], 0)
                if usage < min_usage:
                    min_usage = usage
                    proxy = p
        
        if proxy:
            # Track usage
            self.usage_count[proxy['server']] = self.usage_count.get(proxy['server'], 0) + 1
            logger.debug(f"Selected proxy: {proxy['server']} (usage: {self.usage_count[proxy['server']]})")
        
        return proxy

    def mark_proxy_bad(self, proxy: Dict):
        """Remove a proxy from the working pool."""
        server = proxy.get('server')
        self.working_proxies = [p for p in self.working_proxies if p['server'] != server]
        logger.info(f"Marked proxy as bad: {server}. Remaining: {len(self.working_proxies)}")
        
        if self.db_manager:
            try:
                self.db_manager.update_proxy_health(server, False, None)
            except:
                pass

    def get_stats(self) -> Dict:
        """Get proxy pool statistics."""
        return {
            "total_fetched": len(self.proxies),
            "working": len(self.working_proxies),
            "strategy": self.rotation_strategy.value,
            "usage_count": dict(self.usage_count)
        }
