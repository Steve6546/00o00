import asyncio
import random
import math
import numpy as np
from playwright.async_api import Page

# QWERTY keyboard layout for realistic typos
KEYBOARD_LAYOUT = {
    'q': ['w', 'a', 's'], 'w': ['q', 'e', 'a', 's', 'd'], 'e': ['w', 'r', 's', 'd', 'f'],
    'r': ['e', 't', 'd', 'f', 'g'], 't': ['r', 'y', 'f', 'g', 'h'], 'y': ['t', 'u', 'g', 'h', 'j'],
    'u': ['y', 'i', 'h', 'j', 'k'], 'i': ['u', 'o', 'j', 'k', 'l'], 'o': ['i', 'p', 'k', 'l'],
    'p': ['o', 'l'], 'a': ['q', 'w', 's', 'z', 'x'], 's': ['q', 'w', 'e', 'a', 'd', 'z', 'x', 'c'],
    'd': ['w', 'e', 'r', 's', 'f', 'x', 'c', 'v'], 'f': ['e', 'r', 't', 'd', 'g', 'c', 'v', 'b'],
    'g': ['r', 't', 'y', 'f', 'h', 'v', 'b', 'n'], 'h': ['t', 'y', 'u', 'g', 'j', 'b', 'n', 'm'],
    'j': ['y', 'u', 'i', 'h', 'k', 'n', 'm'], 'k': ['u', 'i', 'o', 'j', 'l', 'm'],
    'l': ['i', 'o', 'p', 'k'], 'z': ['a', 's', 'x'], 'x': ['z', 's', 'd', 'c'],
    'c': ['x', 'd', 'f', 'v'], 'v': ['c', 'f', 'g', 'b'], 'b': ['v', 'g', 'h', 'n'],
    'n': ['b', 'h', 'j', 'm'], 'm': ['n', 'j', 'k'],
    '1': ['2', 'q'], '2': ['1', '3', 'q', 'w'], '3': ['2', '4', 'w', 'e'],
    '4': ['3', '5', 'e', 'r'], '5': ['4', '6', 'r', 't'], '6': ['5', '7', 't', 'y'],
    '7': ['6', '8', 'y', 'u'], '8': ['7', '9', 'u', 'i'], '9': ['8', '0', 'i', 'o'],
    '0': ['9', 'o', 'p']
}


class HumanMouse:
    """Simulates human-like mouse movements with Bezier curves and micro-corrections."""
    
    def __init__(self, page: Page):
        self.page = page
        self.current_x = 0
        self.current_y = 0
    
    async def _bezier_curve(self, start_x, start_y, end_x, end_y, steps):
        """Generates points for a cubic Bezier curve with random control points."""
        path = []
        
        # Calculate distance for appropriate control point deviation
        distance = math.sqrt((end_x - start_x)**2 + (end_y - start_y)**2)
        deviation = min(distance * 0.3, 100)
        
        # Random control points with deviation proportional to distance
        control_x1 = start_x + (end_x - start_x) * 0.25 + random.uniform(-deviation, deviation)
        control_y1 = start_y + (end_y - start_y) * 0.25 + random.uniform(-deviation, deviation)
        control_x2 = start_x + (end_x - start_x) * 0.75 + random.uniform(-deviation, deviation)
        control_y2 = start_y + (end_y - start_y) * 0.75 + random.uniform(-deviation, deviation)

        for t in np.linspace(0, 1, steps):
            # Cubic Bezier formula
            x = (1 - t)**3 * start_x + 3 * (1 - t)**2 * t * control_x1 + \
                3 * (1 - t) * t**2 * control_x2 + t**3 * end_x
            y = (1 - t)**3 * start_y + 3 * (1 - t)**2 * t * control_y1 + \
                3 * (1 - t) * t**2 * control_y2 + t**3 * end_y
            path.append((x, y))
        
        return path

    async def move_to(self, x, y, steps=None):
        """Moves mouse to (x, y) using a human-like Bezier curve with variable speed."""
        distance = math.sqrt((x - self.current_x)**2 + (y - self.current_y)**2)
        
        # Dynamic step count based on distance
        if steps is None:
            steps = max(10, min(50, int(distance / 10)))
        
        path = await self._bezier_curve(self.current_x, self.current_y, x, y, steps)
        
        for i, (px, py) in enumerate(path):
            await self.page.mouse.move(px, py)
            
            # Variable delay - faster in middle, slower at ends (easing)
            progress = i / len(path)
            # Ease-in-out timing
            if progress < 0.5:
                speed_factor = 2 * progress
            else:
                speed_factor = 2 * (1 - progress)
            
            base_delay = random.uniform(0.002, 0.015)
            delay = base_delay * (1.5 - speed_factor * 0.8)
            await asyncio.sleep(delay)
        
        self.current_x, self.current_y = x, y
        
        # Overshoot and correction (30% chance)
        if random.random() > 0.7:
            overshoot_x = x + random.randint(-5, 5)
            overshoot_y = y + random.randint(-5, 5)
            await self.page.mouse.move(overshoot_x, overshoot_y)
            await asyncio.sleep(random.uniform(0.05, 0.15))
            await self.page.mouse.move(x, y)
            
        # Micro-jitter at rest (20% chance)
        if random.random() > 0.8:
            await asyncio.sleep(random.uniform(0.1, 0.3))
            await self.page.mouse.move(x + random.uniform(-1, 1), y + random.uniform(-1, 1))

    async def click_at(self, x, y, button='left'):
        """Moves to position and clicks with human-like timing."""
        await self.move_to(x, y)
        await asyncio.sleep(random.uniform(0.05, 0.15))
        await self.page.mouse.click(x, y, button=button)


class HumanKeyboard:
    """Simulates human-like keyboard input with variable speeds and realistic typos."""
    
    def __init__(self, page: Page):
        self.page = page
        self.wpm = random.uniform(40, 70)  # Words per minute
        
    def _get_adjacent_key(self, char):
        """Returns an adjacent key for realistic typo."""
        char_lower = char.lower()
        if char_lower in KEYBOARD_LAYOUT:
            adjacent = random.choice(KEYBOARD_LAYOUT[char_lower])
            return adjacent.upper() if char.isupper() else adjacent
        return char
    
    def _get_char_delay(self):
        """Returns delay between keystrokes based on WPM."""
        # Average 5 chars per word
        chars_per_minute = self.wpm * 5
        base_delay = 60 / chars_per_minute
        # Add human variance
        return random.normalvariate(base_delay, base_delay * 0.3)

    async def type_text(self, text, click_target=None):
        """Types text with human-like timing, pauses, and occasional typos."""
        if click_target:
            if isinstance(click_target, str):
                await self.page.click(click_target)
            else:
                await click_target.click()
            await asyncio.sleep(random.uniform(0.2, 0.5))
        
        i = 0
        while i < len(text):
            char = text[i]
            
            # 4% chance of typo
            if random.random() < 0.04:
                typo_char = self._get_adjacent_key(char)
                await self.page.keyboard.type(typo_char)
                await asyncio.sleep(random.uniform(0.15, 0.35))
                await self.page.keyboard.press("Backspace")
                await asyncio.sleep(random.uniform(0.1, 0.25))
            
            # Type the correct character
            await self.page.keyboard.type(char)
            
            delay = self._get_char_delay()
            if delay < 0.02:
                delay = 0.02
            await asyncio.sleep(delay)
            
            # 2% chance of a thinking pause
            if random.random() < 0.02:
                await asyncio.sleep(random.uniform(0.5, 2.0))
            
            # 1% chance of double character (quickly fixed)
            if random.random() < 0.01:
                await self.page.keyboard.type(char)
                await asyncio.sleep(random.uniform(0.1, 0.2))
                await self.page.keyboard.press("Backspace")
                await asyncio.sleep(random.uniform(0.08, 0.15))
            
            i += 1
            
            # Longer pause after words (space)
            if char == ' ':
                await asyncio.sleep(random.uniform(0.05, 0.15))


class HumanScroll:
    """Simulates human-like scrolling with physics-based momentum."""
    
    def __init__(self, page: Page):
        self.page = page
    
    async def scroll_natural(self, direction='down', amount=None):
        """Scrolls with momentum and variable speed."""
        if amount is None:
            amount = random.randint(300, 800)
        
        if direction == 'up':
            amount = -amount
        
        # Break into smaller chunks with momentum decay
        remaining = abs(amount)
        velocity = random.uniform(80, 150)  # Initial velocity
        friction = random.uniform(0.85, 0.95)  # Deceleration factor
        
        while remaining > 10:
            chunk = min(velocity, remaining)
            if amount < 0:
                chunk = -chunk
            
            await self.page.mouse.wheel(0, chunk)
            remaining -= abs(chunk)
            velocity *= friction
            
            # Variable pause between scroll chunks
            await asyncio.sleep(random.uniform(0.02, 0.08))
        
        # Reading pause after scroll
        await asyncio.sleep(random.uniform(0.3, 1.5))
    
    async def scroll_to_bottom(self, read_pauses=True):
        """Scrolls through the page naturally, pausing to 'read'."""
        total_height = await self.page.evaluate("document.body.scrollHeight")
        current_scroll = 0
        
        while current_scroll < total_height * 0.85:
            scroll_amount = random.randint(250, 600)
            await self.scroll_natural('down', scroll_amount)
            current_scroll += scroll_amount
            
            if read_pauses:
                # Simulate reading
                await asyncio.sleep(random.uniform(1.0, 3.5))
            
            # Occasionally scroll back up a bit (15% chance)
            if random.random() > 0.85:
                up_amount = random.randint(50, 150)
                await self.scroll_natural('up', up_amount)
                current_scroll -= up_amount
                await asyncio.sleep(random.uniform(0.5, 1.0))


class HumanInput:
    """Combined interface for all human-like input simulation."""
    
    def __init__(self, page: Page):
        self.page = page
        self.mouse = HumanMouse(page)
        self.keyboard = HumanKeyboard(page)
        self.scroll = HumanScroll(page)
        
        # Backwards compatibility
        self.current_x = 0
        self.current_y = 0
    
    async def move_mouse(self, x, y, steps=None):
        """Move mouse to coordinates with human-like motion."""
        await self.mouse.move_to(x, y, steps)
        self.current_x, self.current_y = x, y
    
    async def type_humanlike(self, selector_or_locator, text):
        """Type text into an element with human-like behavior."""
        await self.keyboard.type_text(text, click_target=selector_or_locator)
    
    async def natural_scroll(self):
        """Scroll the page naturally."""
        await self.scroll.scroll_to_bottom(read_pauses=True)
    
    async def click_element(self, locator):
        """Click an element with human-like mouse movement."""
        box = await locator.bounding_box()
        if box:
            # Click at a random point within the element
            x = box['x'] + random.uniform(box['width'] * 0.2, box['width'] * 0.8)
            y = box['y'] + random.uniform(box['height'] * 0.2, box['height'] * 0.8)
            await self.mouse.click_at(x, y)
