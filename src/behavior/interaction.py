import asyncio
import random
from src.behavior.human_input import HumanInput

class Interaction:
    """High-level interaction patterns for simulating human browsing behavior."""
    
    def __init__(self, page):
        self.page = page
        self.human_input = HumanInput(page)

    async def warm_up(self, intensity='medium'):
        """
        Performs warm-up actions before the main task.
        This helps establish a normal browsing pattern before taking targeted actions.
        
        Args:
            intensity: 'light' (1 page), 'medium' (1-3 pages), 'heavy' (3-5 pages)
        """
        sites = [
            "https://www.roblox.com/discover",
            "https://www.roblox.com/catalog",
            "https://www.roblox.com/create",
            "https://www.roblox.com/games",
            "https://www.roblox.com/upgrades/robux",
            "https://www.roblox.com/develop",
        ]
        
        # Determine visit count based on intensity
        if intensity == 'light':
            steps = 1
        elif intensity == 'heavy':
            steps = random.randint(3, 5)
        else:
            steps = random.randint(1, 3)
        
        for _ in range(steps):
            target = random.choice(sites)
            try:
                await self.page.goto(target, wait_until='domcontentloaded')
                await self.random_pause(1, 3)
                
                # Scroll and read
                await self._simulate_reading()
                
                # Random mouse movements
                await self._idle_movements()
                
                await self.random_pause(2, 5)
            except Exception:
                pass  # Ignore navigation errors during warm-up

    async def _simulate_reading(self):
        """Simulate reading content on the page."""
        try:
            # Get page content length to estimate reading time
            content = await self.page.evaluate("""
                () => {
                    const text = document.body.innerText || '';
                    return text.length;
                }
            """)
            
            # Calculate reading time (average 250 words/min, ~5 chars/word)
            words = content / 5
            reading_time = min((words / 250) * 60, 30)  # Cap at 30 seconds
            
            if reading_time > 2:
                # Scroll while "reading"
                scroll_chunks = int(reading_time / 3)
                for _ in range(min(scroll_chunks, 5)):
                    await self.human_input.scroll.scroll_natural('down', random.randint(150, 400))
                    await asyncio.sleep(random.uniform(1.5, 4.0))
        except:
            # Fallback to simple scroll
            await self.human_input.scroll.scroll_natural('down', random.randint(200, 500))

    async def _idle_movements(self):
        """Perform idle mouse movements like a human might do."""
        try:
            viewport = self.page.viewport_size
            if viewport:
                width = viewport['width']
                height = viewport['height']
                
                # 2-4 random movements
                for _ in range(random.randint(2, 4)):
                    x = random.randint(int(width * 0.1), int(width * 0.9))
                    y = random.randint(int(height * 0.1), int(height * 0.9))
                    await self.human_input.move_mouse(x, y)
                    await asyncio.sleep(random.uniform(0.3, 1.0))
        except:
            pass

    async def wander(self, duration_seconds: int = 10):
        """
        Random wandering on the current page.
        Moves mouse, scrolls, hovers over elements.
        
        Args:
            duration_seconds: How long to wander
        """
        start_time = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start_time) < duration_seconds:
            action = random.choice(['move', 'scroll', 'hover'])
            
            if action == 'move':
                await self._idle_movements()
            elif action == 'scroll':
                direction = random.choice(['up', 'down'])
                amount = random.randint(100, 300)
                await self.human_input.scroll.scroll_natural(direction, amount)
            elif action == 'hover':
                await self._hover_random_element()
            
            await asyncio.sleep(random.uniform(0.5, 2.0))

    async def _hover_random_element(self):
        """Hover over a random clickable element on the page."""
        try:
            # Get all visible clickable elements
            elements = await self.page.query_selector_all('a, button, [role="button"]')
            if elements:
                element = random.choice(elements[:20])  # Limit to first 20
                box = await element.bounding_box()
                if box:
                    x = box['x'] + box['width'] / 2
                    y = box['y'] + box['height'] / 2
                    await self.human_input.move_mouse(x, y)
                    await asyncio.sleep(random.uniform(0.2, 0.8))
        except:
            pass

    async def random_pause(self, min_seconds=1, max_seconds=5):
        """Pause for a random duration with human-like variance."""
        # Add slight skew towards shorter pauses
        base = random.uniform(min_seconds, max_seconds)
        variance = random.gauss(0, (max_seconds - min_seconds) * 0.1)
        pause = max(min_seconds, base + variance)
        await asyncio.sleep(pause)

    async def focus_and_type(self, selector, text, clear_first=False):
        """
        Focus an input and type with human behavior.
        
        Args:
            selector: CSS selector or locator for the input
            text: Text to type
            clear_first: Whether to clear existing content first
        """
        if isinstance(selector, str):
            element = await self.page.query_selector(selector)
        else:
            element = selector
        
        if element:
            # Move mouse to element
            box = await element.bounding_box()
            if box:
                x = box['x'] + box['width'] / 2
                y = box['y'] + box['height'] / 2
                await self.human_input.move_mouse(x, y)
                await asyncio.sleep(random.uniform(0.1, 0.3))
            
            await element.click()
            await asyncio.sleep(random.uniform(0.2, 0.5))
            
            if clear_first:
                await self.page.keyboard.press('Control+a')
                await asyncio.sleep(0.1)
                await self.page.keyboard.press('Backspace')
                await asyncio.sleep(random.uniform(0.1, 0.3))
            
            await self.human_input.keyboard.type_text(text)

    async def click_with_hesitation(self, locator, hesitation_chance=0.3):
        """
        Click an element with possible hesitation (move away then back).
        
        Args:
            locator: Element to click
            hesitation_chance: Probability of showing hesitation
        """
        box = await locator.bounding_box()
        if not box:
            await locator.click()
            return
        
        x = box['x'] + box['width'] / 2
        y = box['y'] + box['height'] / 2
        
        # Move to element
        await self.human_input.move_mouse(x, y)
        
        # Hesitation behavior
        if random.random() < hesitation_chance:
            # Move away slightly
            await self.human_input.move_mouse(
                x + random.randint(-50, 50),
                y + random.randint(-50, 50)
            )
            await asyncio.sleep(random.uniform(0.3, 1.0))
            # Move back
            await self.human_input.move_mouse(x, y)
            await asyncio.sleep(random.uniform(0.1, 0.3))
        
        await locator.click()

