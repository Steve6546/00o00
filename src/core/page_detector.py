"""
Page Detector - Heuristic-based page understanding for Roblox.

This module helps the bot "understand" where it is on the website.
Instead of just checking fixed selectors, it uses multiple signals
(heuristics) to determine the current page state with confidence.

Key features:
- Multiple detection methods (selectors, URL patterns, text content)
- Confidence scoring
- Fallback mechanisms
- Available actions detection
"""

import asyncio
import logging
import re
from enum import Enum
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from playwright.async_api import Page

logger = logging.getLogger(__name__)


class PageType(Enum):
    """Types of pages the bot can encounter."""
    
    UNKNOWN = "unknown"
    
    # Main pages
    LANDING = "landing"  # Main roblox.com page (not logged in, no form visible)
    SIGNUP = "signup"    # Actual signup form with fields visible
    LOGIN = "login"
    HOME = "home"
    
    # User pages
    PROFILE = "profile"
    SEARCH_RESULTS = "search_results"
    
    # Challenge pages
    CAPTCHA = "captcha"
    VERIFICATION = "verification"
    
    # Error pages
    ERROR = "error"
    BANNED = "banned"
    RATE_LIMITED = "rate_limited"
    NOT_FOUND = "not_found"


@dataclass
class PageSignal:
    """A signal used to detect a page type."""
    
    signal_type: str  # "selector", "url", "text", "script"
    pattern: str
    weight: float = 1.0  # Importance of this signal (0-1)
    negative: bool = False  # If True, presence means NOT this page


@dataclass
class PageDetectionResult:
    """Result of page detection."""
    
    page_type: PageType
    confidence: float  # 0-1
    signals_matched: List[str]
    available_actions: List[str]
    detected_elements: Dict[str, bool]
    url: str


class PageDetector:
    """
    Heuristic-based page detector for Roblox website.
    
    Uses multiple signals to determine page type with confidence scoring.
    """
    
    # Signal definitions for each page type
    PAGE_SIGNALS: Dict[PageType, List[PageSignal]] = {
        # LANDING: Main roblox.com page without signup form visible
        PageType.LANDING: [
            PageSignal("url", r"^https?://www\.roblox\.com/?$", weight=0.8),
            PageSignal("text", "Sign Up", weight=0.5),
            PageSignal("text", "Log In", weight=0.4),
            # Negative signals - if form elements exist, it's not LANDING
            PageSignal("selector", "#signup-username", weight=0.9, negative=True),
            PageSignal("selector", "#MonthDropdown", weight=0.9, negative=True),
        ],
        
        # SIGNUP: Actual signup form with visible form fields
        PageType.SIGNUP: [
            # High-weight REQUIRED signals - form must have these elements
            PageSignal("selector", "#MonthDropdown", weight=1.0),
            PageSignal("selector", "#signup-username", weight=1.0),
            PageSignal("selector", "#signup-password", weight=0.9),
            PageSignal("selector", "#DayDropdown", weight=0.8),
            PageSignal("selector", "#YearDropdown", weight=0.8),
            PageSignal("selector", "#signup-button", weight=0.7),
            # URL is low weight - form can appear on main URL or modal
            PageSignal("url", r"roblox\.com", weight=0.2),
            # Negative: login elements mean we're on login not signup
            PageSignal("selector", "#login-button", weight=0.5, negative=True),
        ],
        
        PageType.LOGIN: [
            PageSignal("selector", "#login-username", weight=0.9),
            PageSignal("selector", "#login-password", weight=0.9),
            PageSignal("selector", "#login-button", weight=0.8),
            PageSignal("url", r"/login", weight=0.7),
            PageSignal("text", "Log In", weight=0.4),
            PageSignal("selector", "#signup-username", weight=0.5, negative=True),
        ],
        
        PageType.HOME: [
            PageSignal("selector", "#nav-profile", weight=0.9),
            PageSignal("selector", ".home-container", weight=0.8),
            PageSignal("selector", ".age-bracket-label", weight=0.7),
            PageSignal("selector", "[data-testid='user-avatar']", weight=0.7),
            PageSignal("url", r"/home", weight=0.6),
            PageSignal("url", r"/discover", weight=0.5),
            PageSignal("url", r"/games", weight=0.5),
        ],
        
        PageType.PROFILE: [
            PageSignal("selector", ".profile-header", weight=0.9),
            PageSignal("selector", ".follow-button, button:has-text('Follow')", weight=0.7),
            PageSignal("selector", ".profile-about-content", weight=0.6),
            PageSignal("url", r"/users/\d+/profile", weight=0.9),
            PageSignal("text", "Following", weight=0.4),
            PageSignal("text", "Followers", weight=0.4),
        ],
        
        PageType.CAPTCHA: [
            PageSignal("selector", "iframe[src*='arkoselabs']", weight=1.0),
            PageSignal("selector", "iframe[src*='funcaptcha']", weight=1.0),
            PageSignal("selector", ".security-questions-modal", weight=0.9),
            PageSignal("selector", "#FunCaptcha", weight=0.9),
            PageSignal("selector", "[data-testid='captcha-container']", weight=0.8),
            PageSignal("selector", "iframe[title*='challenge']", weight=0.7),
        ],
        
        PageType.ERROR: [
            PageSignal("selector", ".alert-error", weight=0.9),
            PageSignal("selector", ".validation-error", weight=0.8),
            PageSignal("selector", ".error-message", weight=0.8),
            PageSignal("text", "error", weight=0.3),
            PageSignal("text", "something went wrong", weight=0.7),
        ],
        
        PageType.BANNED: [
            PageSignal("text", "banned", weight=0.9),
            PageSignal("text", "suspended", weight=0.8),
            PageSignal("text", "terminated", weight=0.8),
            PageSignal("url", r"/not-approved", weight=0.7),
        ],
        
        PageType.RATE_LIMITED: [
            PageSignal("text", "too many requests", weight=0.9),
            PageSignal("text", "rate limit", weight=0.9),
            PageSignal("text", "try again later", weight=0.6),
            PageSignal("selector", ".rate-limit-error", weight=0.9),
        ],
        
        PageType.NOT_FOUND: [
            PageSignal("text", "404", weight=0.7),
            PageSignal("text", "not found", weight=0.6),
            PageSignal("text", "page doesn't exist", weight=0.8),
        ],
        
        PageType.SEARCH_RESULTS: [
            PageSignal("url", r"/search", weight=0.8),
            PageSignal("selector", ".search-results", weight=0.8),
            PageSignal("selector", "[data-testid='search-results']", weight=0.9),
        ],
    }
    
    # Available actions per page type
    PAGE_ACTIONS: Dict[PageType, List[str]] = {
        PageType.LANDING: ["click_signup_button", "go_to_login", "wait"],
        PageType.SIGNUP: ["fill_birthday", "fill_username", "fill_password", "submit_signup", "go_to_login"],
        PageType.LOGIN: ["fill_username", "fill_password", "submit_login", "go_to_signup"],
        PageType.HOME: ["navigate_profile", "navigate_games", "search", "logout"],
        PageType.PROFILE: ["follow", "unfollow", "send_message", "view_followers", "view_following"],
        PageType.CAPTCHA: ["solve_captcha", "reload_page", "wait"],
        PageType.ERROR: ["retry", "go_back", "report_error"],
        PageType.BANNED: ["report_ban", "switch_account"],
        PageType.RATE_LIMITED: ["wait", "switch_proxy"],
        PageType.NOT_FOUND: ["go_back", "retry"],
        PageType.SEARCH_RESULTS: ["select_result", "refine_search"],
        PageType.UNKNOWN: ["analyze_page", "wait", "reload"],
    }
    
    def __init__(self):
        self.last_detection: Optional[PageDetectionResult] = None
        self.detection_history: List[PageDetectionResult] = []
    
    async def detect(self, page: Page) -> PageDetectionResult:
        """
        Detect the current page type using heuristics.
        
        Returns a PageDetectionResult with confidence score.
        """
        url = page.url
        scores: Dict[PageType, float] = {}
        matched_signals: Dict[PageType, List[str]] = {}
        detected_elements: Dict[str, bool] = {}
        
        for page_type, signals in self.PAGE_SIGNALS.items():
            score = 0.0
            total_weight = 0.0
            matches = []
            
            for signal in signals:
                total_weight += signal.weight
                match = await self._check_signal(page, signal, url)
                
                if match:
                    if signal.negative:
                        score -= signal.weight
                        matches.append(f"NOT:{signal.pattern}")
                    else:
                        score += signal.weight
                        matches.append(signal.pattern)
                        detected_elements[signal.pattern] = True
            
            # Normalize score to 0-1
            if total_weight > 0:
                normalized_score = max(0, score / total_weight)
                scores[page_type] = normalized_score
                matched_signals[page_type] = matches
        
        # Find best match
        best_type = PageType.UNKNOWN
        best_score = 0.0
        
        for page_type, score in scores.items():
            if score > best_score:
                best_score = score
                best_type = page_type
        
        # Require minimum confidence
        if best_score < 0.3:
            best_type = PageType.UNKNOWN
            best_score = 0.0
        
        result = PageDetectionResult(
            page_type=best_type,
            confidence=best_score,
            signals_matched=matched_signals.get(best_type, []),
            available_actions=self.PAGE_ACTIONS.get(best_type, []),
            detected_elements=detected_elements,
            url=url
        )
        
        self.last_detection = result
        self.detection_history.append(result)
        
        logger.info(f"Page detected: {best_type.value} (confidence: {best_score:.2f})")
        
        return result
    
    async def _check_signal(self, page: Page, signal: PageSignal, url: str) -> bool:
        """Check if a signal matches."""
        
        try:
            if signal.signal_type == "selector":
                element = await page.query_selector(signal.pattern)
                return element is not None
            
            elif signal.signal_type == "url":
                return bool(re.search(signal.pattern, url, re.IGNORECASE))
            
            elif signal.signal_type == "text":
                # Check page text content
                content = await page.content()
                return signal.pattern.lower() in content.lower()
            
            elif signal.signal_type == "script":
                # Execute JavaScript to check
                result = await page.evaluate(signal.pattern)
                return bool(result)
        
        except Exception as e:
            logger.debug(f"Signal check failed: {signal.pattern} - {e}")
            return False
        
        return False
    
    async def wait_for_page(self, page: Page, expected: PageType, 
                            timeout: int = 30000, poll_interval: int = 500) -> PageDetectionResult:
        """
        Wait for a specific page type to appear.
        
        Args:
            page: Playwright page
            expected: Expected page type
            timeout: Max wait time in ms
            poll_interval: Check interval in ms
            
        Returns:
            PageDetectionResult when expected page is detected
            
        Raises:
            TimeoutError if page not detected within timeout
        """
        start_time = asyncio.get_event_loop().time()
        timeout_sec = timeout / 1000
        
        while (asyncio.get_event_loop().time() - start_time) < timeout_sec:
            result = await self.detect(page)
            
            if result.page_type == expected:
                return result
            
            await asyncio.sleep(poll_interval / 1000)
        
        raise TimeoutError(f"Timeout waiting for page type: {expected.value}")
    
    async def wait_for_any(self, page: Page, expected: List[PageType],
                           timeout: int = 30000) -> PageDetectionResult:
        """Wait for any of the expected page types."""
        start_time = asyncio.get_event_loop().time()
        timeout_sec = timeout / 1000
        
        while (asyncio.get_event_loop().time() - start_time) < timeout_sec:
            result = await self.detect(page)
            
            if result.page_type in expected:
                return result
            
            await asyncio.sleep(0.5)
        
        raise TimeoutError(f"Timeout waiting for any of: {[p.value for p in expected]}")
    
    async def get_available_actions(self, page: Page) -> List[str]:
        """Get list of available actions for current page."""
        if self.last_detection is None:
            await self.detect(page)
        
        return self.last_detection.available_actions if self.last_detection else []
    
    async def can_action(self, page: Page, action: str) -> bool:
        """Check if a specific action is available."""
        actions = await self.get_available_actions(page)
        return action in actions
    
    async def find_element(self, page: Page, element_type: str) -> Optional[str]:
        """
        Find element selector using multiple strategies.
        
        Args:
            element_type: Type of element (username_input, password_input, submit_button, etc.)
            
        Returns:
            Working selector or None
        """
        strategies = self._get_element_strategies(element_type)
        
        for selector in strategies:
            try:
                element = await page.query_selector(selector)
                if element:
                    is_visible = await element.is_visible()
                    if is_visible:
                        return selector
            except:
                continue
        
        return None
    
    def _get_element_strategies(self, element_type: str) -> List[str]:
        """Get ordered list of selectors to try for an element type."""
        
        strategies = {
            "username_input": [
                "#signup-username",
                "#login-username",
                "input[name='username']",
                "input[name='signupUsername']",
                "input[placeholder*='username' i]",
                "input[placeholder*=\"Don't use your real name\"]",
            ],
            "password_input": [
                "#signup-password",
                "#login-password",
                "input[name='password']",
                "input[name='signupPassword']",
                "input[placeholder*='password' i]",
                "input[type='password']",
            ],
            "month_dropdown": [
                "#MonthDropdown",
                "select[name='birthdayMonth']",
                "select[id*='month' i]",
            ],
            "day_dropdown": [
                "#DayDropdown",
                "select[name='birthdayDay']",
                "select[id*='day' i]",
            ],
            "year_dropdown": [
                "#YearDropdown",
                "select[name='birthdayYear']",
                "select[id*='year' i]",
            ],
            "signup_button": [
                "#signup-button",
                "button[type='submit']:has-text('Sign Up')",
                ".signup-submit-button",
                "button:has-text('Sign Up')",
            ],
            "login_button": [
                "#login-button",
                "button[type='submit']:has-text('Log In')",
                "button:has-text('Log In')",
            ],
            "follow_button": [
                "button:has-text('Follow')",
                ".follow-button",
                "[data-testid='follow-button']",
                "button[aria-label='Follow']",
            ],
            "unfollow_button": [
                "button:has-text('Following')",
                "button:has-text('Unfollow')",
                ".unfollow-button",
            ],
        }
        
        return strategies.get(element_type, [])
    
    def get_detection_summary(self) -> Dict:
        """Get summary of recent detections."""
        if not self.detection_history:
            return {"detections": 0}
        
        recent = self.detection_history[-10:]
        types = [d.page_type.value for d in recent]
        avg_confidence = sum(d.confidence for d in recent) / len(recent)
        
        return {
            "detections": len(self.detection_history),
            "recent_types": types,
            "avg_confidence": round(avg_confidence, 2),
            "last_type": recent[-1].page_type.value if recent else None,
        }

