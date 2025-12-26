"""
Test suite for Proxy Manager functionality.
Run with: python -m pytest tests/test_proxy.py -v
"""

import pytest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.proxy_manager import ProxyManager, RotationStrategy


class TestProxyManager:
    """Tests for ProxyManager class."""
    
    def test_initialization(self):
        """Test ProxyManager initializes correctly."""
        pm = ProxyManager()
        assert pm.proxies == []
        assert pm.working_proxies == []
        assert pm.rotation_strategy == RotationStrategy.RANDOM
    
    def test_set_rotation_strategy(self):
        """Test rotation strategy can be changed."""
        pm = ProxyManager()
        pm.set_rotation_strategy(RotationStrategy.ROUND_ROBIN)
        assert pm.rotation_strategy == RotationStrategy.ROUND_ROBIN
        
        pm.set_rotation_strategy(RotationStrategy.LEAST_USED)
        assert pm.rotation_strategy == RotationStrategy.LEAST_USED
    
    def test_load_custom_proxies(self):
        """Test loading custom proxy list."""
        pm = ProxyManager()
        custom = [
            {"server": "http://1.2.3.4:8080", "username": "user1", "password": "pass1"},
            {"server": "http://5.6.7.8:3128"},
        ]
        pm.load_custom_proxies(custom)
        
        assert len(pm.proxies) == 2
        assert pm.proxies[0]['server'] == "http://1.2.3.4:8080"
        assert pm.proxies[1]['username'] == ""  # Should default to empty

    def test_fetch_free_proxies(self):
        """Test fetching proxies from public sources."""
        pm = ProxyManager()
        proxies = pm.fetch_free_proxies()
        
        # Should fetch at least some proxies (may fail if sources are down)
        # This is a best-effort test
        print(f"Fetched {len(proxies)} proxies")
        assert isinstance(proxies, list)
    
    def test_validate_proxy_format(self):
        """Test proxy validation returns correct tuple format."""
        pm = ProxyManager()
        test_proxy = {"server": "http://invalid.proxy:9999", "username": "", "password": ""}
        
        result = pm.validate_proxy(test_proxy)
        
        assert isinstance(result, tuple)
        assert len(result) == 3
        assert result[0] == test_proxy  # Same proxy dict
        assert isinstance(result[1], bool)  # is_working
        # result[2] is latency or None

    def test_round_robin_rotation(self):
        """Test round-robin proxy selection."""
        pm = ProxyManager()
        pm.working_proxies = [
            {"server": "http://1.1.1.1:80"},
            {"server": "http://2.2.2.2:80"},
            {"server": "http://3.3.3.3:80"},
        ]
        pm.set_rotation_strategy(RotationStrategy.ROUND_ROBIN)
        
        # Should cycle through proxies in order
        p1 = pm.get_proxy()
        p2 = pm.get_proxy()
        p3 = pm.get_proxy()
        p4 = pm.get_proxy()
        
        assert p1['server'] == "http://1.1.1.1:80"
        assert p2['server'] == "http://2.2.2.2:80"
        assert p3['server'] == "http://3.3.3.3:80"
        assert p4['server'] == "http://1.1.1.1:80"  # Wraps around

    def test_least_used_rotation(self):
        """Test least-used proxy selection."""
        pm = ProxyManager()
        pm.working_proxies = [
            {"server": "http://1.1.1.1:80"},
            {"server": "http://2.2.2.2:80"},
        ]
        pm.set_rotation_strategy(RotationStrategy.LEAST_USED)
        
        # Pre-set usage counts
        pm.usage_count = {"http://1.1.1.1:80": 5, "http://2.2.2.2:80": 1}
        
        proxy = pm.get_proxy()
        assert proxy['server'] == "http://2.2.2.2:80"  # Less used

    def test_mark_proxy_bad(self):
        """Test removing bad proxies."""
        pm = ProxyManager()
        pm.working_proxies = [
            {"server": "http://good.proxy:80"},
            {"server": "http://bad.proxy:80"},
        ]
        
        pm.mark_proxy_bad({"server": "http://bad.proxy:80"})
        
        assert len(pm.working_proxies) == 1
        assert pm.working_proxies[0]['server'] == "http://good.proxy:80"

    def test_get_stats(self):
        """Test statistics reporting."""
        pm = ProxyManager()
        pm.proxies = [{"server": "a"}, {"server": "b"}, {"server": "c"}]
        pm.working_proxies = [{"server": "a"}]
        pm.usage_count = {"a": 3}
        
        stats = pm.get_stats()
        
        assert stats['total_fetched'] == 3
        assert stats['working'] == 1
        assert stats['usage_count'] == {"a": 3}


class TestProxyValidation:
    """Integration tests for proxy validation (requires network)."""
    
    @pytest.mark.slow
    def test_check_proxies_integration(self):
        """Test full proxy check flow (slow, requires network)."""
        pm = ProxyManager()
        
        # Load a small set of test proxies
        pm.proxies = [
            {"server": "http://8.8.8.8:80", "username": "", "password": ""},  # Google DNS, won't work as proxy
        ]
        
        working = pm.check_proxies(max_workers=2)
        
        # Most test proxies won't work, but function should complete
        assert isinstance(working, list)
        print(f"Found {len(working)} working proxies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
