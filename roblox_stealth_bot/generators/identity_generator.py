"""
Identity Generator - Smart generation of unique identities for accounts.

This module generates:
- Unique usernames (with availability check and fallback)
- Strong passwords (meeting Roblox requirements)
- Realistic birthdays (proper age distribution, no patterns)

Key features:
- Remembers used data to avoid repetition
- Multiple generation strategies
- Fallback mechanisms
- Database integration for uniqueness
"""

import random
import string
import hashlib
from datetime import datetime, date
from typing import Optional, List, Dict, Set, Tuple
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class Identity:
    """A complete generated identity."""
    
    username: str
    password: str
    birthday: Dict[str, str]  # {month, day, year}
    birthday_date: date
    
    # Metadata
    pattern_used: str = ""
    generation_time: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict:
        return {
            "username": self.username,
            "password": self.password,
            "birthday": self.birthday,
            "birthday_str": self.birthday_date.strftime("%Y-%m-%d"),
        }


class UsernameGenerator:
    """
    Generates unique usernames with multiple strategies.
    
    Strategies:
    1. Adjective + Noun + Numbers (CoolNinja123)
    2. Name + Action + Numbers (JakeRuns99)
    3. Word + Word + Numbers (SkyFire2024)
    4. Random + Numbers (Xkr8924)
    """
    
    ADJECTIVES = [
        "Cool", "Super", "Fast", "Silent", "Neon", "Dark", "Light", "Hyper",
        "Epic", "Pro", "Swift", "Blazing", "Shadow", "Cosmic", "Turbo", "Ultra",
        "Brave", "Mighty", "Noble", "Fierce", "Wild", "Mystic", "Royal", "Prime",
        "Cyber", "Pixel", "Ninja", "Stealth", "Thunder", "Storm", "Fire", "Ice"
    ]
    
    NOUNS = [
        "Tiger", "Ninja", "Warrior", "Gamer", "Pilot", "Striker", "Phoenix",
        "Dragon", "Knight", "Racer", "Hunter", "Legend", "Storm", "Wolf",
        "Hawk", "Viper", "Falcon", "Panther", "Lion", "Eagle", "Bear", "Fox",
        "Shark", "Blade", "Arrow", "Shield", "Star", "Moon", "Sun", "King"
    ]
    
    VERBS = [
        "Runs", "Plays", "Fights", "Builds", "Wins", "Rocks", "Rules", "Strikes",
        "Hunts", "Games", "Codes", "Flies", "Jumps", "Dashes", "Blasts"
    ]
    
    NAMES = [
        "Jake", "Alex", "Max", "Sam", "Leo", "Ryan", "Kyle", "Zack",
        "Luna", "Nova", "Aria", "Zara", "Maya", "Lily", "Ruby", "Skye",
        "Finn", "Cole", "Nash", "Jace", "Kai", "Axel", "Rex", "Blaze"
    ]
    
    def __init__(self, db_manager=None):
        self.db = db_manager
        self.used_usernames: Set[str] = set()
        self.used_patterns: Dict[str, int] = {}
        
        # Load existing usernames from database
        if self.db:
            self._load_existing_usernames()
    
    def _load_existing_usernames(self):
        """Load existing usernames from database."""
        try:
            from data.database import Account
            accounts = Account.select(Account.username)
            self.used_usernames = {a.username.lower() for a in accounts}
            logger.info(f"Loaded {len(self.used_usernames)} existing usernames")
        except Exception as e:
            logger.warning(f"Could not load existing usernames: {e}")
    
    def generate(self, strategy: str = "auto") -> str:
        """
        Generate a unique username.
        
        Args:
            strategy: "adjective_noun", "name_verb", "words", "random", or "auto"
        """
        if strategy == "auto":
            # Choose least-used strategy
            strategies = ["adjective_noun", "name_verb", "words", "random"]
            strategy = min(strategies, key=lambda s: self.used_patterns.get(s, 0))
        
        max_attempts = 50
        for _ in range(max_attempts):
            if strategy == "adjective_noun":
                username = self._generate_adjective_noun()
            elif strategy == "name_verb":
                username = self._generate_name_verb()
            elif strategy == "words":
                username = self._generate_words()
            else:
                username = self._generate_random()
            
            if self._is_unique(username):
                self.used_usernames.add(username.lower())
                self.used_patterns[strategy] = self.used_patterns.get(strategy, 0) + 1
                return username
        
        # Fallback: add more random digits
        username = self._generate_random() + str(random.randint(100, 999))
        self.used_usernames.add(username.lower())
        return username
    
    def _generate_adjective_noun(self) -> str:
        """CoolNinja123 style"""
        adj = random.choice(self.ADJECTIVES)
        noun = random.choice(self.NOUNS)
        nums = ''.join(random.choices(string.digits, k=random.randint(2, 4)))
        return f"{adj}{noun}{nums}"
    
    def _generate_name_verb(self) -> str:
        """JakeRuns99 style"""
        name = random.choice(self.NAMES)
        verb = random.choice(self.VERBS)
        nums = ''.join(random.choices(string.digits, k=random.randint(1, 3)))
        return f"{name}{verb}{nums}"
    
    def _generate_words(self) -> str:
        """SkyFire2024 style"""
        word1 = random.choice(self.ADJECTIVES + self.NOUNS)
        word2 = random.choice(self.NOUNS + self.VERBS)
        year = random.choice(["2024", "2025", str(random.randint(100, 999))])
        return f"{word1}{word2}{year}"
    
    def _generate_random(self) -> str:
        """Xkr8924 style"""
        consonants = "bcdfghjklmnpqrstvwxyz"
        vowels = "aeiou"
        
        # Start with consonant or X/Z for cool factor
        start = random.choice(["X", "Z"] + list(consonants))
        middle = random.choice(vowels) + random.choice(consonants)
        nums = ''.join(random.choices(string.digits, k=random.randint(3, 5)))
        
        return f"{start}{middle}{nums}"
    
    def _is_unique(self, username: str) -> bool:
        """Check if username is unique (not used before)."""
        return username.lower() not in self.used_usernames
    
    async def check_availability(self, page, username: str) -> bool:
        """
        Check if username is available on Roblox.
        
        Note: This uses the signup form's built-in validation.
        Fallback: assume available if check fails.
        """
        try:
            # Type username in the field
            username_input = await page.query_selector("#signup-username")
            if username_input:
                await username_input.fill("")
                await username_input.type(username)
                await asyncio.sleep(1)  # Wait for validation
                
                # Check for error message
                error = await page.query_selector(".username-error, .input-validation-error")
                if error:
                    error_text = await error.inner_text()
                    if "taken" in error_text.lower() or "not available" in error_text.lower():
                        return False
                
                return True
        except Exception as e:
            logger.debug(f"Availability check failed: {e}")
        
        # Fallback: assume available
        return True


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
        """
        Generate a strong password.
        
        Args:
            length: Password length (8-20)
            include_special: Include special characters
        """
        if length < 8:
            length = 8
        if length > 20:
            length = 20
        
        # Ensure at least one of each required type
        password_chars = []
        
        # Add required character types
        password_chars.append(random.choice(string.ascii_uppercase))
        password_chars.append(random.choice(string.ascii_lowercase))
        password_chars.append(random.choice(string.digits))
        
        if include_special:
            # Roblox-safe special characters
            safe_special = "!@#$%^&*"
            password_chars.append(random.choice(safe_special))
        
        # Fill remaining with random mix
        all_chars = string.ascii_letters + string.digits
        if include_special:
            all_chars += "!@#$%^&*"
        
        remaining = length - len(password_chars)
        password_chars.extend(random.choices(all_chars, k=remaining))
        
        # Shuffle to randomize position
        random.shuffle(password_chars)
        password = ''.join(password_chars)
        
        # Ensure uniqueness
        while password in self.used_passwords:
            random.shuffle(password_chars)
            password = ''.join(password_chars)
        
        self.used_passwords.add(password)
        return password
    
    def generate_memorable(self) -> str:
        """Generate a more memorable password."""
        words = ["Sun", "Moon", "Star", "Fire", "Ice", "Wind", "Rock", "Wave"]
        word = random.choice(words)
        nums = ''.join(random.choices(string.digits, k=4))
        special = random.choice("!@#$")
        
        return f"{word}{nums}{special}"


class BirthdayGenerator:
    """
    Generates realistic, diverse birthdays.
    
    Rules:
    - Age between 18-30 (safe for Roblox)
    - Distributed across months (not all January)
    - Distributed across days (not all 1st)
    - Years varied (not all same year)
    """
    
    MONTHS = [
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ]
    
    def __init__(self):
        self.used_birthdays: List[Tuple[str, str, str]] = []
        self.month_usage: Dict[str, int] = {m: 0 for m in self.MONTHS}
        self.year_usage: Dict[int, int] = {}
        self.day_usage: Dict[int, int] = {}
    
    def generate(self) -> Tuple[Dict[str, str], date]:
        """
        Generate a unique birthday.
        
        Returns:
            Tuple of (birthday_dict, date_object)
        """
        max_attempts = 100
        
        for _ in range(max_attempts):
            # Choose least-used month
            month = min(self.MONTHS, key=lambda m: self.month_usage.get(m, 0))
            
            # Choose appropriate day for month
            month_num = self.MONTHS.index(month) + 1
            max_day = 28 if month_num == 2 else (30 if month_num in [4, 6, 9, 11] else 31)
            
            # Prefer less-used days
            day_weights = [1.0 / (self.day_usage.get(d, 0) + 1) for d in range(1, max_day + 1)]
            day = random.choices(range(1, max_day + 1), weights=day_weights)[0]
            
            # Choose year (18-30 years old)
            current_year = datetime.now().year
            min_year = current_year - 30
            max_year = current_year - 18
            
            # Prefer less-used years
            years = list(range(min_year, max_year + 1))
            year_weights = [1.0 / (self.year_usage.get(y, 0) + 1) for y in years]
            year = random.choices(years, weights=year_weights)[0]
            
            # Check if this combination was used
            combo = (month, str(day), str(year))
            if combo not in self.used_birthdays:
                self.used_birthdays.append(combo)
                self.month_usage[month] = self.month_usage.get(month, 0) + 1
                self.day_usage[day] = self.day_usage.get(day, 0) + 1
                self.year_usage[year] = self.year_usage.get(year, 0) + 1
                
                birthday_dict = {
                    'month': month,
                    'day': str(day),
                    'year': str(year)
                }
                
                birthday_date = date(year, month_num, day)
                
                return birthday_dict, birthday_date
        
        # Fallback: just generate random
        month = random.choice(self.MONTHS)
        day = random.randint(1, 28)
        year = random.randint(current_year - 28, current_year - 18)
        
        return {
            'month': month,
            'day': str(day),
            'year': str(year)
        }, date(year, self.MONTHS.index(month) + 1, day)


class IdentityGenerator:
    """
    Main identity generator that combines all generators.
    
    Usage:
        gen = IdentityGenerator(db_manager)
        identity = gen.generate()
        print(identity.username, identity.password)
    """
    
    def __init__(self, db_manager=None):
        self.db = db_manager
        self.username_gen = UsernameGenerator(db_manager)
        self.password_gen = PasswordGenerator()
        self.birthday_gen = BirthdayGenerator()
        
        self.generated_count = 0
    
    def generate(self, username_strategy: str = "auto") -> Identity:
        """
        Generate a complete unique identity.
        
        Args:
            username_strategy: Strategy for username generation
            
        Returns:
            Identity object with all fields
        """
        username = self.username_gen.generate(strategy=username_strategy)
        password = self.password_gen.generate()
        birthday, birthday_date = self.birthday_gen.generate()
        
        identity = Identity(
            username=username,
            password=password,
            birthday=birthday,
            birthday_date=birthday_date,
            pattern_used=username_strategy
        )
        
        self.generated_count += 1
        logger.info(f"Generated identity #{self.generated_count}: {username}")
        
        return identity
    
    def generate_batch(self, count: int) -> List[Identity]:
        """Generate multiple identities."""
        return [self.generate() for _ in range(count)]
    
    def get_stats(self) -> Dict:
        """Get generation statistics."""
        return {
            "total_generated": self.generated_count,
            "username_patterns": dict(self.username_gen.used_patterns),
            "month_distribution": dict(self.birthday_gen.month_usage),
            "unique_usernames": len(self.username_gen.used_usernames),
        }


# Import for async availability check
import asyncio
