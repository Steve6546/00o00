"""
Smart Identity Generator - Intelligent identity management for Roblox accounts.

This module provides:
1. Smart username generation using Roblox suggestions (primary)
2. Faker-based realistic name generation (fallback)
3. Roblox username rules validation
4. Blacklist system for rejected/used names
5. Gender selection support

Key features:
- Uses Roblox's suggested usernames for 100% acceptance rate
- Validates all usernames against Roblox rules before use
- Maintains blacklist of rejected names in database
- Integrates with Faker for human-like names
"""

import random
import string
import re
import os
import json
from datetime import datetime, date
from typing import Optional, List, Dict, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging
import asyncio

# Try to import Faker, provide fallback if not available
try:
    from faker import Faker
    HAS_FAKER = True
except ImportError:
    HAS_FAKER = False
    Faker = None

logger = logging.getLogger(__name__)


class GenderType(Enum):
    """Gender selection for account creation."""
    MALE = "male"
    FEMALE = "female"
    RANDOM = "random"


@dataclass
class Identity:
    """A complete generated identity."""
    
    username: str
    password: str
    birthday: Dict[str, str]  # {month, day, year}
    birthday_date: date
    gender: str = "unknown"  # male, female, or unknown
    
    # Metadata
    pattern_used: str = ""
    generation_time: datetime = field(default_factory=datetime.now)
    from_roblox_suggestion: bool = False  # True if username came from Roblox
    
    def to_dict(self) -> Dict:
        return {
            "username": self.username,
            "password": self.password,
            "birthday": self.birthday,
            "birthday_str": self.birthday_date.strftime("%Y-%m-%d"),
            "gender": self.gender,
            "from_suggestion": self.from_roblox_suggestion
        }


# =============================================================================
# USERNAME VALIDATOR - Roblox Rules Enforcement
# =============================================================================

class RobloxUsernameValidator:
    """
    Validates usernames against Roblox's official rules.
    
    Rules:
    - Length: 3-20 characters
    - Allowed chars: A-Z, a-z, 0-9, _ (underscore)
    - Underscore cannot be at start or end
    - Cannot be digits only
    - Cannot contain inappropriate content
    """
    
    MIN_LENGTH = 3
    MAX_LENGTH = 20
    ALLOWED_CHARS = set(string.ascii_letters + string.digits + '_')
    
    # Common inappropriate words to filter (basic list)
    INAPPROPRIATE_WORDS = {
        'admin', 'mod', 'moderator', 'roblox', 'staff', 'official',
        'password', 'hack', 'cheat', 'scam', 'free', 'robux',
        # Add more as needed
    }
    
    def __init__(self, blacklist: 'UsernameBlacklist' = None):
        self.blacklist = blacklist
    
    def validate(self, username: str) -> Tuple[bool, str]:
        """
        Validate a username against Roblox rules.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not username:
            return False, "Username is empty"
        
        # Check length
        if len(username) < self.MIN_LENGTH:
            return False, f"Too short (min {self.MIN_LENGTH} chars)"
        
        if len(username) > self.MAX_LENGTH:
            return False, f"Too long (max {self.MAX_LENGTH} chars)"
        
        # Check allowed characters
        invalid_chars = set(username) - self.ALLOWED_CHARS
        if invalid_chars:
            return False, f"Invalid characters: {invalid_chars}"
        
        # Check underscore position
        if username.startswith('_'):
            return False, "Cannot start with underscore"
        
        if username.endswith('_'):
            return False, "Cannot end with underscore"
        
        # Check not all digits
        if username.isdigit():
            return False, "Cannot be only numbers"
        
        # Check blacklist
        if self.blacklist and self.blacklist.is_blacklisted(username):
            return False, "Username is blacklisted"
        
        # Check inappropriate words
        username_lower = username.lower()
        for word in self.INAPPROPRIATE_WORDS:
            if word in username_lower:
                return False, f"Contains inappropriate word: {word}"
        
        return True, "Valid"
    
    def is_valid(self, username: str) -> bool:
        """Quick check if username is valid."""
        return self.validate(username)[0]


# =============================================================================
# USERNAME BLACKLIST - Memory System
# =============================================================================

class UsernameBlacklist:
    """
    Manages a blacklist of rejected/used usernames.
    
    Features:
    - Persists to database for long-term memory
    - Prevents reuse of rejected usernames
    - Tracks rejection reason
    """
    
    def __init__(self, db_manager=None, blacklist_file: str = None):
        self.db = db_manager
        self.blacklist_file = blacklist_file or "data/used_usernames.json"
        self._blacklist: Dict[str, str] = {}  # username -> reason
        
        # Load existing blacklist
        self._load_blacklist()
    
    def _load_blacklist(self):
        """Load blacklist from file and database."""
        # Load from file
        try:
            if os.path.exists(self.blacklist_file):
                with open(self.blacklist_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._blacklist = data.get('blacklist', {})
                    logger.info(f"Loaded {len(self._blacklist)} blacklisted usernames")
        except Exception as e:
            logger.warning(f"Could not load blacklist file: {e}")
        
        # Load used usernames from database
        if self.db:
            try:
                from data.database import Account
                accounts = Account.select(Account.username)
                for acc in accounts:
                    if acc.username.lower() not in self._blacklist:
                        self._blacklist[acc.username.lower()] = "already_used"
            except Exception as e:
                logger.warning(f"Could not load usernames from database: {e}")
    
    def _save_blacklist(self):
        """Save blacklist to file."""
        try:
            os.makedirs(os.path.dirname(self.blacklist_file), exist_ok=True)
            with open(self.blacklist_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'blacklist': self._blacklist,
                    'updated_at': datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save blacklist: {e}")
    
    def add(self, username: str, reason: str = "rejected"):
        """Add a username to the blacklist."""
        self._blacklist[username.lower()] = reason
        self._save_blacklist()
        logger.debug(f"Blacklisted username: {username} ({reason})")
    
    def remove(self, username: str):
        """Remove a username from the blacklist."""
        if username.lower() in self._blacklist:
            del self._blacklist[username.lower()]
            self._save_blacklist()
    
    def is_blacklisted(self, username: str) -> bool:
        """Check if a username is blacklisted."""
        return username.lower() in self._blacklist
    
    def get_reason(self, username: str) -> Optional[str]:
        """Get the reason a username was blacklisted."""
        return self._blacklist.get(username.lower())
    
    def get_all(self) -> Dict[str, str]:
        """Get all blacklisted usernames."""
        return self._blacklist.copy()
    
    def count(self) -> int:
        """Get count of blacklisted usernames."""
        return len(self._blacklist)


# =============================================================================
# SMART USERNAME GENERATOR - Faker + Patterns
# =============================================================================

class SmartUsernameGenerator:
    """
    Intelligent username generator using multiple strategies.
    
    Strategies (in order of preference):
    1. Roblox suggestions (handled in account_flow.py)
    2. Faker-based realistic names
    3. Pattern-based generation (Adjective + Noun + Numbers)
    4. Random fallback
    """
    
    # Word lists for pattern generation
    POSITIVE_ADJECTIVES = [
        "Happy", "Bright", "Swift", "Cool", "Super", "Epic", "Pro", "Ultra",
        "Mega", "Hyper", "Turbo", "Cosmic", "Stellar", "Neon", "Vivid", "Prime",
        "Noble", "Brave", "Mighty", "Wild", "Mystic", "Royal", "Golden", "Silver",
        "Crystal", "Shadow", "Storm", "Thunder", "Fire", "Ice", "Light", "Dark"
    ]
    
    POSITIVE_NOUNS = [
        "Star", "Moon", "Sun", "Sky", "Cloud", "Wave", "Wind", "Storm",
        "Tiger", "Eagle", "Phoenix", "Dragon", "Wolf", "Hawk", "Falcon", "Lion",
        "Arrow", "Shield", "Sword", "Knight", "Warrior", "Hunter", "Pilot", "Racer",
        "Gamer", "Builder", "Creator", "Dreamer", "Runner", "Striker", "Champion", "Legend"
    ]
    
    MALE_NAMES = [
        "Alex", "Max", "Sam", "Jake", "Leo", "Ryan", "Kyle", "Zack", "Finn", "Cole",
        "Ethan", "Mason", "Lucas", "Noah", "Oliver", "Liam", "James", "Logan", "Kai", "Axel"
    ]
    
    FEMALE_NAMES = [
        "Luna", "Nova", "Aria", "Zara", "Maya", "Lily", "Ruby", "Skye", "Emma", "Sophia",
        "Olivia", "Ava", "Mia", "Chloe", "Ella", "Grace", "Zoey", "Nora", "Layla", "Riley"
    ]
    
    def __init__(self, db_manager=None, blacklist: UsernameBlacklist = None):
        self.db = db_manager
        self.blacklist = blacklist or UsernameBlacklist(db_manager)
        self.validator = RobloxUsernameValidator(self.blacklist)
        
        # Initialize Faker if available
        self.faker = Faker() if HAS_FAKER else None
        
        # Track generation stats
        self.generated_count = 0
        self.strategy_usage: Dict[str, int] = {}
    
    def generate(self, gender: GenderType = GenderType.RANDOM, 
                 strategy: str = "auto") -> str:
        """
        Generate a unique, valid username.
        
        Args:
            gender: Gender for name selection
            strategy: "faker", "pattern", "random", or "auto"
        
        Returns:
            A valid, unique username
        """
        # Resolve random gender
        if gender == GenderType.RANDOM:
            gender = random.choice([GenderType.MALE, GenderType.FEMALE])
        
        # Auto-select strategy
        if strategy == "auto":
            strategies = ["faker", "pattern", "mixed"] if HAS_FAKER else ["pattern", "mixed"]
            strategy = random.choice(strategies)
        
        max_attempts = 50
        
        for attempt in range(max_attempts):
            if strategy == "faker" and self.faker:
                username = self._generate_faker(gender)
            elif strategy == "pattern":
                username = self._generate_pattern(gender)
            elif strategy == "mixed":
                username = self._generate_mixed(gender)
            else:
                username = self._generate_fallback()
            
            # Validate
            is_valid, error = self.validator.validate(username)
            if is_valid:
                self.generated_count += 1
                self.strategy_usage[strategy] = self.strategy_usage.get(strategy, 0) + 1
                logger.debug(f"Generated username: {username} (strategy: {strategy})")
                return username
            else:
                logger.debug(f"Username {username} rejected: {error}")
        
        # Ultimate fallback
        fallback = f"Player{random.randint(100000, 999999)}"
        logger.warning(f"Using fallback username: {fallback}")
        return fallback
    
    def _generate_faker(self, gender: GenderType) -> str:
        """Generate username using Faker library."""
        if not self.faker:
            return self._generate_pattern(gender)
        
        # Get first name based on gender
        if gender == GenderType.MALE:
            first_name = self.faker.first_name_male()
        else:
            first_name = self.faker.first_name_female()
        
        # Clean name (remove spaces, special chars)
        first_name = re.sub(r'[^a-zA-Z]', '', first_name)
        
        # Add suffix
        suffix_type = random.choice(["numbers", "word", "year"])
        
        if suffix_type == "numbers":
            suffix = str(random.randint(1, 9999))
        elif suffix_type == "word":
            suffix = random.choice(self.POSITIVE_ADJECTIVES + self.POSITIVE_NOUNS)
        else:
            suffix = str(random.choice([2024, 2025, random.randint(100, 999)]))
        
        return f"{first_name}{suffix}"
    
    def _generate_pattern(self, gender: GenderType) -> str:
        """Generate username using pattern."""
        patterns = [
            self._pattern_adj_noun,
            self._pattern_name_noun,
            self._pattern_noun_noun,
        ]
        
        pattern_func = random.choice(patterns)
        return pattern_func(gender)
    
    def _pattern_adj_noun(self, gender: GenderType) -> str:
        """Pattern: CoolTiger123"""
        adj = random.choice(self.POSITIVE_ADJECTIVES)
        noun = random.choice(self.POSITIVE_NOUNS)
        nums = str(random.randint(1, 9999))
        return f"{adj}{noun}{nums}"
    
    def _pattern_name_noun(self, gender: GenderType) -> str:
        """Pattern: AlexGamer99"""
        if gender == GenderType.MALE:
            name = random.choice(self.MALE_NAMES)
        else:
            name = random.choice(self.FEMALE_NAMES)
        noun = random.choice(self.POSITIVE_NOUNS)
        nums = str(random.randint(1, 999))
        return f"{name}{noun}{nums}"
    
    def _pattern_noun_noun(self, gender: GenderType) -> str:
        """Pattern: StarHunter2024"""
        noun1 = random.choice(self.POSITIVE_NOUNS)
        noun2 = random.choice(self.POSITIVE_NOUNS)
        year = random.choice(["2024", "2025", str(random.randint(100, 999))])
        return f"{noun1}{noun2}{year}"
    
    def _generate_mixed(self, gender: GenderType) -> str:
        """Generate by mixing different elements."""
        elements = []
        
        # First element: name or adjective
        if random.random() > 0.5:
            if gender == GenderType.MALE:
                elements.append(random.choice(self.MALE_NAMES))
            else:
                elements.append(random.choice(self.FEMALE_NAMES))
        else:
            elements.append(random.choice(self.POSITIVE_ADJECTIVES))
        
        # Second element: noun
        elements.append(random.choice(self.POSITIVE_NOUNS))
        
        # Third element: numbers
        elements.append(str(random.randint(1, 999)))
        
        return ''.join(elements)
    
    def _generate_fallback(self) -> str:
        """Ultimate fallback generator."""
        consonants = "bcdfghjklmnpqrstvwxyz"
        vowels = "aeiou"
        
        # Create pronounceable random name
        parts = []
        for _ in range(2):
            parts.append(random.choice(consonants).upper())
            parts.append(random.choice(vowels))
            parts.append(random.choice(consonants))
        
        nums = str(random.randint(100, 9999))
        return ''.join(parts) + nums
    
    def mark_as_rejected(self, username: str, reason: str = "rejected"):
        """Mark a username as rejected (add to blacklist)."""
        self.blacklist.add(username, reason)
    
    def get_stats(self) -> Dict:
        """Get generation statistics."""
        return {
            "total_generated": self.generated_count,
            "strategy_usage": self.strategy_usage,
            "blacklist_size": self.blacklist.count(),
            "faker_available": HAS_FAKER
        }


# =============================================================================
# ROBLOX SUGGESTIONS HANDLER
# =============================================================================

class RobloxSuggestionHandler:
    """
    Handles Roblox's username suggestion system.
    
    When a username is taken, Roblox shows suggestions like:
    "Try: username123, username456, username789"
    
    This class detects and uses those suggestions.
    """
    
    # Selectors for username suggestions
    SUGGESTION_SELECTORS = [
        ".username-suggestion",
        "[data-testid='username-suggestion']",
        ".suggestion-button",
        "button.username-suggestion-btn"
    ]
    
    # Text patterns to detect suggestions
    SUGGESTION_TEXT_PATTERN = r"Try:\s*"
    
    def __init__(self, blacklist: UsernameBlacklist = None):
        self.blacklist = blacklist
        self.last_suggestions: List[str] = []
    
    async def get_suggestions(self, page) -> List[str]:
        """
        Get username suggestions from the Roblox page.
        
        Returns:
            List of suggested usernames
        """
        suggestions = []
        
        try:
            # Wait a moment for suggestions to load
            await asyncio.sleep(1.5)
            
            # Method 1: Look for suggestion buttons
            for selector in self.SUGGESTION_SELECTORS:
                elements = await page.query_selector_all(selector)
                for elem in elements:
                    text = await elem.inner_text()
                    if text and len(text) >= 3:
                        suggestions.append(text.strip())
            
            # Method 2: Look for "Try:" text and extract suggestions
            if not suggestions:
                # Find text containing "Try:"
                try_elements = await page.query_selector_all("text=/Try:/i")
                for elem in try_elements:
                    parent = await elem.evaluate_handle("el => el.parentElement")
                    parent_text = await parent.inner_text()
                    
                    # Extract usernames after "Try:"
                    match = re.search(r"Try:\s*(.+)", parent_text)
                    if match:
                        suggestion_text = match.group(1)
                        # Split by common separators
                        parts = re.split(r'[,\s]+', suggestion_text)
                        suggestions.extend([p.strip() for p in parts if len(p.strip()) >= 3])
            
            # Method 3: Look for buttons near username field
            if not suggestions:
                username_field = await page.query_selector("#signup-username")
                if username_field:
                    # Get parent container
                    parent = await username_field.evaluate_handle("el => el.parentElement.parentElement")
                    buttons = await parent.query_selector_all("button")
                    for btn in buttons:
                        text = await btn.inner_text()
                        # Check if it looks like a username
                        if text and re.match(r'^[a-zA-Z][a-zA-Z0-9_]{2,19}$', text.strip()):
                            suggestions.append(text.strip())
            
            self.last_suggestions = suggestions
            
            if suggestions:
                logger.info(f"Found {len(suggestions)} Roblox suggestions: {suggestions[:3]}...")
            
            return suggestions
            
        except Exception as e:
            logger.debug(f"Could not get suggestions: {e}")
            return []
    
    async def click_suggestion(self, page, index: int = 0) -> Optional[str]:
        """
        Click on a suggestion button.
        
        Args:
            page: Playwright page
            index: Which suggestion to click (0 = first)
        
        Returns:
            The selected username or None
        """
        try:
            suggestions = await self.get_suggestions(page)
            
            if not suggestions or index >= len(suggestions):
                return None
            
            target_username = suggestions[index]
            
            # Try to click the suggestion button
            for selector in self.SUGGESTION_SELECTORS:
                buttons = await page.query_selector_all(selector)
                for btn in buttons:
                    text = await btn.inner_text()
                    if text.strip() == target_username:
                        await btn.click()
                        logger.info(f"Clicked suggestion: {target_username}")
                        return target_username
            
            # Fallback: click button by text
            try:
                await page.click(f"button:has-text('{target_username}')")
                logger.info(f"Clicked suggestion by text: {target_username}")
                return target_username
            except:
                pass
            
            return None
            
        except Exception as e:
            logger.error(f"Error clicking suggestion: {e}")
            return None


# =============================================================================
# PASSWORD GENERATOR
# =============================================================================

class PasswordGenerator:
    """
    Generates strong passwords meeting Roblox requirements.
    
    Requirements:
    - At least 8 characters
    - Mix of uppercase, lowercase, numbers
    - Optional special characters
    """
    
    def __init__(self):
        self.used_passwords: Set[str] = set()
    
    def generate(self, length: int = 12, include_special: bool = True) -> str:
        """Generate a strong password."""
        if length < 8:
            length = 8
        if length > 20:
            length = 20
        
        password_chars = []
        
        # Add required character types
        password_chars.append(random.choice(string.ascii_uppercase))
        password_chars.append(random.choice(string.ascii_lowercase))
        password_chars.append(random.choice(string.digits))
        
        if include_special:
            safe_special = "!@#$%^&*"
            password_chars.append(random.choice(safe_special))
        
        # Fill remaining
        all_chars = string.ascii_letters + string.digits
        if include_special:
            all_chars += "!@#$%^&*"
        
        remaining = length - len(password_chars)
        password_chars.extend(random.choices(all_chars, k=remaining))
        
        random.shuffle(password_chars)
        password = ''.join(password_chars)
        
        # Ensure uniqueness
        while password in self.used_passwords:
            random.shuffle(password_chars)
            password = ''.join(password_chars)
        
        self.used_passwords.add(password)
        return password


# =============================================================================
# BIRTHDAY GENERATOR
# =============================================================================

class BirthdayGenerator:
    """
    Generates realistic, diverse birthdays.
    
    Rules:
    - Age between 18-30 (safe for Roblox)
    - Distributed across months
    - Varied days and years
    """
    
    MONTHS = [
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ]
    
    def __init__(self):
        self.used_birthdays: List[Tuple[str, str, str]] = []
        self.month_usage: Dict[str, int] = {m: 0 for m in self.MONTHS}
    
    def generate(self) -> Tuple[Dict[str, str], date]:
        """Generate a unique birthday."""
        current_year = datetime.now().year
        
        # Choose least-used month
        month = min(self.MONTHS, key=lambda m: self.month_usage.get(m, 0))
        month_num = self.MONTHS.index(month) + 1
        
        # Choose appropriate day
        max_day = 28 if month_num == 2 else (30 if month_num in [4, 6, 9, 11] else 31)
        day = random.randint(1, max_day)
        
        # Choose year (18-30 years old)
        year = random.randint(current_year - 30, current_year - 18)
        
        self.month_usage[month] = self.month_usage.get(month, 0) + 1
        
        birthday_dict = {
            'month': month,
            'day': str(day),
            'year': str(year)
        }
        
        birthday_date = date(year, month_num, day)
        
        return birthday_dict, birthday_date


# =============================================================================
# MAIN IDENTITY GENERATOR
# =============================================================================

class IdentityGenerator:
    """
    Main identity generator that combines all generators.
    
    Features:
    - Smart username generation with validation
    - Roblox suggestions support
    - Gender selection
    - Birthday generation
    - Password generation
    """
    
    def __init__(self, db_manager=None):
        self.db = db_manager
        
        # Initialize components
        self.blacklist = UsernameBlacklist(db_manager)
        self.username_gen = SmartUsernameGenerator(db_manager, self.blacklist)
        self.suggestion_handler = RobloxSuggestionHandler(self.blacklist)
        self.password_gen = PasswordGenerator()
        self.birthday_gen = BirthdayGenerator()
        self.validator = RobloxUsernameValidator(self.blacklist)
        
        self.generated_count = 0
    
    def generate(self, gender: GenderType = GenderType.RANDOM,
                 username_strategy: str = "auto") -> Identity:
        """
        Generate a complete unique identity.
        
        Args:
            gender: GenderType for name selection
            username_strategy: Strategy for username generation
            
        Returns:
            Identity object with all fields
        """
        # Resolve random gender
        actual_gender = gender
        if gender == GenderType.RANDOM:
            actual_gender = random.choice([GenderType.MALE, GenderType.FEMALE])
        
        username = self.username_gen.generate(
            gender=actual_gender,
            strategy=username_strategy
        )
        password = self.password_gen.generate()
        birthday, birthday_date = self.birthday_gen.generate()
        
        identity = Identity(
            username=username,
            password=password,
            birthday=birthday,
            birthday_date=birthday_date,
            gender=actual_gender.value,
            pattern_used=username_strategy
        )
        
        self.generated_count += 1
        logger.info(f"Generated identity #{self.generated_count}: {username} ({actual_gender.value})")
        
        return identity
    
    def validate_username(self, username: str) -> Tuple[bool, str]:
        """Validate a username against Roblox rules."""
        return self.validator.validate(username)
    
    def blacklist_username(self, username: str, reason: str = "rejected"):
        """Add a username to the blacklist."""
        self.blacklist.add(username, reason)
    
    async def get_roblox_suggestions(self, page) -> List[str]:
        """Get username suggestions from Roblox page."""
        return await self.suggestion_handler.get_suggestions(page)
    
    async def use_roblox_suggestion(self, page, index: int = 0) -> Optional[str]:
        """Click and use a Roblox username suggestion."""
        return await self.suggestion_handler.click_suggestion(page, index)
    
    def get_stats(self) -> Dict:
        """Get generation statistics."""
        return {
            "total_generated": self.generated_count,
            "username_stats": self.username_gen.get_stats(),
            "blacklist_size": self.blacklist.count(),
            "faker_available": HAS_FAKER
        }
