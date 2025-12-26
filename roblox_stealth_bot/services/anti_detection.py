"""
Anti-Detection Protection - Human-like behavior simulation and rate limiting.

Features:
- Random human-like delays
- Rate limiting per account
- Session isolation
- Action variation
"""

import random
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    max_actions_per_hour: int = 30
    max_follows_per_day: int = 50
    cooldown_after_fail_seconds: int = 300  # 5 minutes
    min_delay_between_actions_ms: int = 2000
    max_delay_between_actions_ms: int = 8000


class HumanDelay:
    """
    Simulates human-like delays between actions.
    
    Uses random distributions to appear more natural.
    """
    
    @staticmethod
    async def short():
        """Short delay (0.5-1.5 seconds) - like button clicks"""
        delay = random.uniform(0.5, 1.5)
        await asyncio.sleep(delay)
    
    @staticmethod
    async def medium():
        """Medium delay (1-3 seconds) - like reading"""
        delay = random.uniform(1.0, 3.0)
        await asyncio.sleep(delay)
    
    @staticmethod
    async def long():
        """Long delay (3-8 seconds) - like thinking"""
        delay = random.uniform(3.0, 8.0)
        await asyncio.sleep(delay)
    
    @staticmethod
    async def typing(text_length: int):
        """Typing delay based on text length (40-80 WPM)"""
        wpm = random.uniform(40, 80)
        chars_per_second = (wpm * 5) / 60  # 5 chars per word avg
        delay = text_length / chars_per_second
        # Add some randomness
        delay *= random.uniform(0.8, 1.2)
        await asyncio.sleep(delay)
    
    @staticmethod
    async def random_pause():
        """Random pause (0.1-0.5 seconds) - micro-delays"""
        delay = random.uniform(0.1, 0.5)
        await asyncio.sleep(delay)
    
    @staticmethod
    async def page_load():
        """Page load wait (2-5 seconds)"""
        delay = random.uniform(2.0, 5.0)
        await asyncio.sleep(delay)


class RateLimiter:
    """
    Rate limiter to prevent bot detection through action frequency.
    
    Tracks actions per account and enforces limits.
    """
    
    def __init__(self, config: RateLimitConfig = None):
        self.config = config or RateLimitConfig()
        self.action_log: Dict[str, List[datetime]] = {}
        self.follow_log: Dict[str, List[datetime]] = {}
        self.cooldowns: Dict[str, datetime] = {}
    
    def _cleanup_old_actions(self, account_id: str, log: Dict, hours: int = 1):
        """Remove actions older than specified hours."""
        if account_id not in log:
            log[account_id] = []
            return
        
        cutoff = datetime.now() - timedelta(hours=hours)
        log[account_id] = [t for t in log[account_id] if t > cutoff]
    
    def can_act(self, account_id: str) -> bool:
        """Check if account can perform an action now."""
        # Check cooldown
        if account_id in self.cooldowns:
            if datetime.now() < self.cooldowns[account_id]:
                return False
        
        # Check hourly rate
        self._cleanup_old_actions(account_id, self.action_log, hours=1)
        if len(self.action_log.get(account_id, [])) >= self.config.max_actions_per_hour:
            return False
        
        return True
    
    def can_follow(self, account_id: str) -> bool:
        """Check if account can perform a follow action."""
        if not self.can_act(account_id):
            return False
        
        # Check daily follow limit
        self._cleanup_old_actions(account_id, self.follow_log, hours=24)
        if len(self.follow_log.get(account_id, [])) >= self.config.max_follows_per_day:
            return False
        
        return True
    
    def record_action(self, account_id: str):
        """Record an action for rate limiting."""
        if account_id not in self.action_log:
            self.action_log[account_id] = []
        self.action_log[account_id].append(datetime.now())
    
    def record_follow(self, account_id: str):
        """Record a follow action."""
        self.record_action(account_id)
        if account_id not in self.follow_log:
            self.follow_log[account_id] = []
        self.follow_log[account_id].append(datetime.now())
    
    def apply_cooldown(self, account_id: str, seconds: int = None):
        """Apply cooldown to an account."""
        duration = seconds or self.config.cooldown_after_fail_seconds
        self.cooldowns[account_id] = datetime.now() + timedelta(seconds=duration)
        logger.info(f"Applied {duration}s cooldown to account {account_id}")
    
    def get_wait_time(self, account_id: str) -> int:
        """Get seconds to wait before next action."""
        if account_id in self.cooldowns:
            remaining = (self.cooldowns[account_id] - datetime.now()).total_seconds()
            if remaining > 0:
                return int(remaining)
        return 0
    
    async def wait_if_needed(self, account_id: str):
        """Wait if rate limit requires it."""
        wait_time = self.get_wait_time(account_id)
        if wait_time > 0:
            logger.info(f"Waiting {wait_time}s for rate limit...")
            await asyncio.sleep(wait_time)
    
    def get_stats(self, account_id: str) -> Dict:
        """Get rate limit stats for an account."""
        self._cleanup_old_actions(account_id, self.action_log, hours=1)
        self._cleanup_old_actions(account_id, self.follow_log, hours=24)
        
        return {
            "actions_this_hour": len(self.action_log.get(account_id, [])),
            "max_actions_per_hour": self.config.max_actions_per_hour,
            "follows_today": len(self.follow_log.get(account_id, [])),
            "max_follows_per_day": self.config.max_follows_per_day,
            "cooldown_remaining": self.get_wait_time(account_id)
        }


class ActionRandomizer:
    """
    Randomizes actions to appear more human-like.
    
    - Random mouse movements
    - Variable timing
    - Occasional "mistakes"
    """
    
    @staticmethod
    def random_scroll_distance() -> int:
        """Random scroll distance for human-like scrolling."""
        return random.randint(100, 500)
    
    @staticmethod
    def random_click_offset() -> tuple:
        """Random offset from element center for more natural clicking."""
        return (random.randint(-5, 5), random.randint(-5, 5))
    
    @staticmethod
    def should_take_break() -> bool:
        """Randomly decide if bot should take a longer break (5% chance)."""
        return random.random() < 0.05
    
    @staticmethod
    async def maybe_take_break():
        """Occasionally take a longer break."""
        if ActionRandomizer.should_take_break():
            break_time = random.uniform(30, 120)  # 30s to 2min
            logger.info(f"Taking a {int(break_time)}s break to appear human-like")
            await asyncio.sleep(break_time)
    
    @staticmethod
    def random_viewport() -> Dict:
        """Random viewport size for fingerprint variation."""
        viewports = [
            {"width": 1920, "height": 1080},
            {"width": 1366, "height": 768},
            {"width": 1536, "height": 864},
            {"width": 1440, "height": 900},
            {"width": 1280, "height": 720},
        ]
        return random.choice(viewports)


# Global instances
human_delay = HumanDelay()
rate_limiter = RateLimiter()
action_randomizer = ActionRandomizer()


# Convenience functions
async def delay_short():
    """Short human delay."""
    await human_delay.short()


async def delay_medium():
    """Medium human delay."""
    await human_delay.medium()


async def delay_long():
    """Long human delay."""
    await human_delay.long()
