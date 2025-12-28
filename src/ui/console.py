"""
UI Console - Global Rich console and settings.

This module provides:
- Global console instance
- Verbose mode toggle
- Logging suppression
- Consistent styling
"""

import logging
from rich.console import Console

# Global console instance
console = Console()

# Verbose mode flag
_verbose = False

# Original log level storage
_original_log_levels = {}


def set_verbose(enabled: bool):
    """Set verbose mode globally and adjust logging."""
    global _verbose
    _verbose = enabled
    
    if enabled:
        # Restore original logging levels
        _restore_logging()
    else:
        # Suppress most logging
        _suppress_logging()


def is_verbose() -> bool:
    """Check if verbose mode is enabled."""
    return _verbose


def _suppress_logging():
    """Suppress logging output for clean display."""
    global _original_log_levels
    
    # Store and suppress common loggers
    loggers_to_suppress = [
        'src.flows.follow_flow',
        'src.flows.account_flow',
        'src.core.session_validator',
        'src.core.session_renewer',
        'src.core.fallback_login',
        'src.core.page_detector',
        'src.control.commander',
        'playwright',
        'asyncio',
        '',  # Root logger
    ]
    
    for name in loggers_to_suppress:
        logger = logging.getLogger(name)
        _original_log_levels[name] = logger.level
        logger.setLevel(logging.CRITICAL + 1)  # Suppress all


def _restore_logging():
    """Restore original logging levels."""
    global _original_log_levels
    
    for name, level in _original_log_levels.items():
        logger = logging.getLogger(name)
        logger.setLevel(level)
    
    _original_log_levels = {}


def print_verbose(message: str):
    """Print only if verbose mode is enabled."""
    if _verbose:
        console.print(f"[dim]{message}[/dim]")


def print_step(message: str):
    """Print a step message (always visible)."""
    console.print(f"  → {message}")


def print_success(message: str):
    """Print success message."""
    console.print(f"  ✓ {message}", style="green")


def print_error(message: str):
    """Print error message."""
    console.print(f"  ✗ {message}", style="red")


def print_warning(message: str):
    """Print warning message."""
    console.print(f"  ⚠ {message}", style="yellow")
