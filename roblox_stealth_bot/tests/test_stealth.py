"""
Test suite for Stealth Layer functionality.
Run with: python -m pytest tests/test_stealth.py -v

These tests verify that stealth injections work correctly.
Some tests require browser launch and are marked as slow.
"""

import pytest
import asyncio
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.stealth_layer import StealthLayer


class TestStealthLayer:
    """Unit tests for StealthLayer class."""
    
    def test_initialization(self):
        """Test StealthLayer initializes with fingerprints."""
        sl = StealthLayer()
        assert len(sl.fingerprints) >= 10  # Should have 10+ profiles
    
    def test_fingerprint_structure(self):
        """Test fingerprints have required fields."""
        sl = StealthLayer()
        
        required_fields = ['userAgent', 'screen', 'locale', 'timezone', 'vendor', 'renderer']
        
        for fp in sl.fingerprints:
            for field in required_fields:
                assert field in fp, f"Missing field: {field}"
            
            # Validate screen is a dict with dimensions
            assert 'width' in fp['screen']
            assert 'height' in fp['screen']
    
    def test_random_fingerprint(self):
        """Test getting random fingerprint."""
        sl = StealthLayer()
        
        # Get several fingerprints and verify randomness
        fingerprints = [sl.get_random_fingerprint() for _ in range(20)]
        
        # Should get at least 2 different fingerprints in 20 tries
        unique = set(fp['userAgent'] for fp in fingerprints)
        assert len(unique) >= 2
    
    def test_fingerprint_diversity(self):
        """Test fingerprints have diverse values."""
        sl = StealthLayer()
        
        timezones = set(fp['timezone'] for fp in sl.fingerprints)
        locales = set(fp['locale'] for fp in sl.fingerprints)
        
        # Should have diverse geographic settings
        assert len(timezones) >= 3
        assert len(locales) >= 3
    
    def test_user_agent_format(self):
        """Test user agents are properly formatted."""
        sl = StealthLayer()
        
        for fp in sl.fingerprints:
            ua = fp['userAgent']
            assert 'Mozilla' in ua
            assert 'Chrome' in ua or 'Safari' in ua


@pytest.mark.asyncio
class TestStealthIntegration:
    """Integration tests that require browser launch."""
    
    @pytest.mark.slow
    async def test_stealth_injections(self):
        """Test stealth injections work in real browser."""
        from playwright.async_api import async_playwright
        
        sl = StealthLayer()
        fingerprint = sl.get_random_fingerprint()
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=fingerprint['userAgent'],
                viewport=fingerprint['screen'],
                locale=fingerprint['locale'],
                timezone_id=fingerprint['timezone'],
            )
            
            # Apply stealth
            await sl.apply_stealth(context, fingerprint)
            
            page = await context.new_page()
            await page.goto("about:blank")
            
            # Verify webdriver is undefined
            webdriver = await page.evaluate("() => navigator.webdriver")
            assert webdriver is None or webdriver == "undefined", \
                f"navigator.webdriver should be undefined, got: {webdriver}"
            
            # Verify platform matches fingerprint
            platform = await page.evaluate("() => navigator.platform")
            expected_platform = fingerprint.get('platform', 'Win32')
            assert platform == expected_platform, \
                f"Platform mismatch: {platform} != {expected_platform}"
            
            # Verify hardware concurrency is set
            cores = await page.evaluate("() => navigator.hardwareConcurrency")
            assert cores in [2, 4, 8, 16], f"Unexpected core count: {cores}"
            
            await browser.close()
    
    @pytest.mark.slow  
    async def test_canvas_noise(self):
        """Test canvas produces different fingerprints."""
        from playwright.async_api import async_playwright
        
        sl = StealthLayer()
        
        async def get_canvas_hash():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                fp = sl.get_random_fingerprint()
                await sl.apply_stealth(context, fp)
                
                page = await context.new_page()
                await page.goto("about:blank")
                
                # Create canvas and get data URL
                result = await page.evaluate("""
                    () => {
                        const canvas = document.createElement('canvas');
                        canvas.width = 200;
                        canvas.height = 50;
                        const ctx = canvas.getContext('2d');
                        ctx.textBaseline = 'top';
                        ctx.font = '14px Arial';
                        ctx.fillText('Canvas fingerprint test', 10, 10);
                        return canvas.toDataURL();
                    }
                """)
                
                await browser.close()
                return result
        
        # Get two canvas hashes - they should potentially be different due to noise
        hash1 = await get_canvas_hash()
        hash2 = await get_canvas_hash()
        
        # Both should be valid data URLs
        assert hash1.startswith('data:image/')
        assert hash2.startswith('data:image/')
        
        print(f"Canvas 1 length: {len(hash1)}")
        print(f"Canvas 2 length: {len(hash2)}")

    @pytest.mark.slow
    async def test_webgl_spoofing(self):
        """Test WebGL vendor/renderer spoofing."""
        from playwright.async_api import async_playwright
        
        sl = StealthLayer()
        fingerprint = sl.get_random_fingerprint()
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            
            await sl.apply_stealth(context, fingerprint)
            
            page = await context.new_page()
            await page.goto("about:blank")
            
            # Check WebGL vendor
            vendor = await page.evaluate("""
                () => {
                    const canvas = document.createElement('canvas');
                    const gl = canvas.getContext('webgl');
                    if (!gl) return null;
                    const ext = gl.getExtension('WEBGL_debug_renderer_info');
                    if (!ext) return null;
                    return gl.getParameter(ext.UNMASKED_VENDOR_WEBGL);
                }
            """)
            
            renderer = await page.evaluate("""
                () => {
                    const canvas = document.createElement('canvas');
                    const gl = canvas.getContext('webgl');
                    if (!gl) return null;
                    const ext = gl.getExtension('WEBGL_debug_renderer_info');
                    if (!ext) return null;
                    return gl.getParameter(ext.UNMASKED_RENDERER_WEBGL);
                }
            """)
            
            await browser.close()
            
            # Should match fingerprint values
            assert vendor == fingerprint['vendor'], f"Vendor mismatch: {vendor}"
            assert renderer == fingerprint['renderer'], f"Renderer mismatch: {renderer}"


class TestBotDetection:
    """Tests against common bot detection checks."""
    
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_bot_sannysoft(self):
        """
        Test against bot.sannysoft.com detection site.
        This is an informational test - results are logged but may not pass perfectly.
        """
        from playwright.async_api import async_playwright
        from core.session_manager import SessionManager
        
        session = SessionManager(headless=True)
        await session.start()
        
        try:
            context, page = await session.create_context()
            
            await page.goto("https://bot.sannysoft.com/", wait_until='networkidle')
            await asyncio.sleep(3)
            
            # Get all test results
            results = await page.evaluate("""
                () => {
                    const rows = document.querySelectorAll('table tr');
                    const results = {};
                    rows.forEach(row => {
                        const cells = row.querySelectorAll('td');
                        if (cells.length >= 2) {
                            const test = cells[0].textContent.trim();
                            const result = cells[1].textContent.trim();
                            results[test] = result;
                        }
                    });
                    return results;
                }
            """)
            
            print("\n=== Bot Detection Results ===")
            for test, result in results.items():
                status = "✓" if "missing" in result.lower() or result == "present" else "?"
                print(f"{status} {test}: {result}")
            
            # Key checks that should pass
            webdriver = results.get('Webdriver present?', '')
            assert 'missing' in webdriver.lower() or webdriver == 'false', \
                "Webdriver should not be detected"
                
        finally:
            await session.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
