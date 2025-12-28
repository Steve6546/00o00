"""
Cookie Migrator - Handle old cookie formats and migration.

Purpose:
- Validate cookie structure and required fields
- Convert old cookie formats to new format
- Repair incomplete or corrupted cookies
- Flag cookies that need manual review

Roblox required cookies:
- .ROBLOSECURITY - Main authentication cookie
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class CookieStatus(Enum):
    """Status of cookie validation/migration."""
    VALID = "valid"
    MIGRATED = "migrated"
    REPAIRED = "repaired"
    INVALID = "invalid"
    NEEDS_REVIEW = "needs_review"


@dataclass
class MigrationResult:
    """Result of cookie migration."""
    
    status: CookieStatus
    cookies: Optional[List[Dict]] = None
    original_cookies: Optional[Any] = None
    changes_made: List[str] = None
    errors: List[str] = None
    
    def __post_init__(self):
        if self.changes_made is None:
            self.changes_made = []
        if self.errors is None:
            self.errors = []


class CookieMigrator:
    """
    Migrates and validates cookie formats.
    
    Handles:
    - Old string-based cookies
    - JSON with missing fields
    - Expired cookies (flags them)
    - Invalid structures
    """
    
    # Required cookie fields for Playwright
    REQUIRED_FIELDS = ["name", "value", "domain"]
    
    # Optional but helpful fields
    OPTIONAL_FIELDS = ["path", "expires", "httpOnly", "secure", "sameSite"]
    
    # Domain defaults for Roblox
    ROBLOX_DOMAIN = ".roblox.com"
    
    # The critical cookie
    AUTH_COOKIE = ".ROBLOSECURITY"
    
    def __init__(self):
        self._migration_stats = {
            "total_processed": 0,
            "valid": 0,
            "migrated": 0,
            "repaired": 0,
            "invalid": 0,
            "needs_review": 0
        }
    
    def migrate(self, cookies: Any) -> MigrationResult:
        """
        Migrate cookies to valid format.
        
        Args:
            cookies: Cookie data (string, list, or dict)
            
        Returns:
            MigrationResult with validated cookies
        """
        self._migration_stats["total_processed"] += 1
        
        # Handle None/empty
        if not cookies:
            return MigrationResult(
                status=CookieStatus.INVALID,
                errors=["No cookie data provided"]
            )
        
        # Parse if string
        if isinstance(cookies, str):
            parsed = self._parse_string_cookies(cookies)
            if parsed is None:
                return MigrationResult(
                    status=CookieStatus.INVALID,
                    original_cookies=cookies,
                    errors=["Could not parse cookie string"]
                )
            cookies = parsed
        
        # Handle dict (single cookie)
        if isinstance(cookies, dict):
            cookies = [cookies]
        
        # Must be list now
        if not isinstance(cookies, list):
            return MigrationResult(
                status=CookieStatus.INVALID,
                original_cookies=cookies,
                errors=[f"Unexpected cookie type: {type(cookies).__name__}"]
            )
        
        # Validate and repair each cookie
        result_cookies = []
        changes = []
        errors = []
        
        for i, cookie in enumerate(cookies):
            validated, cookie_changes, cookie_errors = self._validate_cookie(cookie, i)
            
            if validated:
                result_cookies.append(validated)
                changes.extend(cookie_changes)
            else:
                errors.extend(cookie_errors)
        
        # Check for required auth cookie
        has_auth = any(
            c.get("name") == self.AUTH_COOKIE 
            for c in result_cookies
        )
        
        if not has_auth and result_cookies:
            errors.append(f"Missing required cookie: {self.AUTH_COOKIE}")
            self._migration_stats["needs_review"] += 1
            return MigrationResult(
                status=CookieStatus.NEEDS_REVIEW,
                cookies=result_cookies,
                original_cookies=cookies,
                changes_made=changes,
                errors=errors
            )
        
        if not result_cookies:
            self._migration_stats["invalid"] += 1
            return MigrationResult(
                status=CookieStatus.INVALID,
                original_cookies=cookies,
                errors=errors
            )
        
        # Determine status
        if errors:
            self._migration_stats["needs_review"] += 1
            status = CookieStatus.NEEDS_REVIEW
        elif changes:
            self._migration_stats["repaired"] += 1
            status = CookieStatus.REPAIRED
        elif cookies != result_cookies:
            self._migration_stats["migrated"] += 1
            status = CookieStatus.MIGRATED
        else:
            self._migration_stats["valid"] += 1
            status = CookieStatus.VALID
        
        return MigrationResult(
            status=status,
            cookies=result_cookies,
            original_cookies=cookies,
            changes_made=changes,
            errors=errors
        )
    
    def _parse_string_cookies(self, cookie_str: str) -> Optional[List[Dict]]:
        """Parse a cookie string into list of dicts."""
        
        # Try JSON first
        try:
            parsed = json.loads(cookie_str)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                return [parsed]
        except json.JSONDecodeError:
            pass
        
        # Try cookie header format: name=value; name2=value2
        if "=" in cookie_str and not cookie_str.startswith("{"):
            try:
                cookies = []
                for part in cookie_str.split(";"):
                    part = part.strip()
                    if "=" in part:
                        name, value = part.split("=", 1)
                        cookies.append({
                            "name": name.strip(),
                            "value": value.strip(),
                            "domain": self.ROBLOX_DOMAIN
                        })
                if cookies:
                    return cookies
            except:
                pass
        
        return None
    
    def _validate_cookie(
        self, 
        cookie: Any, 
        index: int
    ) -> Tuple[Optional[Dict], List[str], List[str]]:
        """
        Validate and repair a single cookie.
        
        Returns:
            (validated_cookie, changes_made, errors)
        """
        changes = []
        errors = []
        
        if not isinstance(cookie, dict):
            errors.append(f"Cookie {index}: Not a dict")
            return None, changes, errors
        
        # Check required fields
        validated = {}
        
        # Name
        if "name" not in cookie:
            errors.append(f"Cookie {index}: Missing 'name'")
            return None, changes, errors
        validated["name"] = str(cookie["name"])
        
        # Value
        if "value" not in cookie:
            errors.append(f"Cookie {index}: Missing 'value'")
            return None, changes, errors
        validated["value"] = str(cookie["value"])
        
        # Domain - add default if missing
        if "domain" not in cookie:
            validated["domain"] = self.ROBLOX_DOMAIN
            changes.append(f"Cookie {index}: Added default domain")
        else:
            validated["domain"] = str(cookie["domain"])
        
        # Path - add default if missing
        if "path" not in cookie:
            validated["path"] = "/"
            changes.append(f"Cookie {index}: Added default path '/'")
        else:
            validated["path"] = str(cookie["path"])
        
        # Expires - validate if present
        if "expires" in cookie:
            expires = cookie["expires"]
            if isinstance(expires, (int, float)):
                validated["expires"] = expires
                
                # Check if expired
                if expires > 0 and expires < datetime.now().timestamp():
                    changes.append(f"Cookie {index}: EXPIRED")
            else:
                # Try to parse string
                try:
                    validated["expires"] = float(expires)
                except (ValueError, TypeError):
                    changes.append(f"Cookie {index}: Invalid expires, removed")
        
        # Boolean fields
        for field in ["httpOnly", "secure"]:
            if field in cookie:
                validated[field] = bool(cookie[field])
        
        # sameSite
        if "sameSite" in cookie:
            same_site = str(cookie["sameSite"]).capitalize()
            if same_site in ["Strict", "Lax", "None"]:
                validated["sameSite"] = same_site
        
        return validated, changes, errors
    
    def validate_structure(self, cookies: List[Dict]) -> Tuple[bool, List[str]]:
        """
        Validate cookie structure without modifying.
        
        Returns:
            (is_valid, list of issues)
        """
        issues = []
        
        if not cookies:
            return False, ["No cookies"]
        
        if not isinstance(cookies, list):
            return False, ["Cookies is not a list"]
        
        has_auth = False
        
        for i, cookie in enumerate(cookies):
            if not isinstance(cookie, dict):
                issues.append(f"Cookie {i}: Not a dict")
                continue
            
            for field in self.REQUIRED_FIELDS:
                if field not in cookie:
                    issues.append(f"Cookie {i} ({cookie.get('name', '?')}): Missing {field}")
            
            if cookie.get("name") == self.AUTH_COOKIE:
                has_auth = True
                
                # Check if auth cookie is expired
                expires = cookie.get("expires", 0)
                if expires > 0 and expires < datetime.now().timestamp():
                    issues.append("Auth cookie is EXPIRED")
        
        if not has_auth:
            issues.append(f"Missing required {self.AUTH_COOKIE}")
        
        return len(issues) == 0, issues
    
    def get_stats(self) -> Dict:
        """Get migration statistics."""
        return {
            **self._migration_stats,
            "success_rate": self._calculate_success_rate()
        }
    
    def _calculate_success_rate(self) -> str:
        """Calculate success rate of migrations."""
        total = self._migration_stats["total_processed"]
        if total == 0:
            return "N/A"
        
        successful = (
            self._migration_stats["valid"] + 
            self._migration_stats["migrated"] + 
            self._migration_stats["repaired"]
        )
        
        return f"{successful / total * 100:.1f}%"
    
    def export_cookies_for_playwright(self, cookies: List[Dict]) -> str:
        """Export cookies in format suitable for Playwright."""
        # Run through migration to ensure valid format
        result = self.migrate(cookies)
        
        if result.status in [CookieStatus.VALID, CookieStatus.MIGRATED, CookieStatus.REPAIRED]:
            return json.dumps(result.cookies)
        
        # Return as-is if migration failed
        return json.dumps(cookies)
