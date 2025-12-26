"""
Professional Logging System - Structured and categorized logs.

Features:
- Categorized logs (INFO/WARNING/ERROR/DEBUG)
- Console and file output
- Checkpoint logging with ✔️/❌
- Formatted timestamps
"""

import logging
import os
from datetime import datetime
from typing import Optional
from rich.logging import RichHandler
from rich.console import Console

# Create logs directory if not exists
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')
os.makedirs(LOGS_DIR, exist_ok=True)

# Console for rich output
console = Console()


class CheckpointLogger:
    """
    Logger with checkpoint support for tracking execution flow.
    
    Usage:
        logger = CheckpointLogger("FollowFlow")
        logger.checkpoint("Page loaded", success=True)
        logger.checkpoint("Button click", success=False, reason="Element not found")
    """
    
    def __init__(self, module_name: str):
        self.module = module_name
        self.logger = logging.getLogger(module_name)
        self.checkpoints = []
    
    def checkpoint(self, step: str, success: bool, reason: str = None, details: dict = None):
        """
        Log a checkpoint with success/failure status.
        
        Args:
            step: Description of the step
            success: True if successful, False if failed
            reason: Explanation for failure (required if success=False)
            details: Additional details dict
        """
        icon = "✔️" if success else "❌"
        status = "SUCCESS" if success else "FAILED"
        
        message = f"[{self.module}] {icon} {step}"
        if not success and reason:
            message += f" - Reason: {reason}"
        
        # Store checkpoint
        self.checkpoints.append({
            "step": step,
            "success": success,
            "reason": reason,
            "details": details,
            "timestamp": datetime.now()
        })
        
        # Log appropriately
        if success:
            self.logger.info(message)
        else:
            self.logger.error(message)
        
        return success
    
    def get_summary(self) -> dict:
        """Get summary of all checkpoints."""
        total = len(self.checkpoints)
        passed = sum(1 for c in self.checkpoints if c['success'])
        failed = total - passed
        
        return {
            "module": self.module,
            "total": total,
            "passed": passed,
            "failed": failed,
            "success_rate": f"{(passed/total*100):.1f}%" if total > 0 else "N/A",
            "checkpoints": self.checkpoints
        }
    
    def print_summary(self):
        """Print formatted checkpoint summary."""
        summary = self.get_summary()
        console.print(f"\n[bold]📊 Checkpoint Summary: {self.module}[/bold]")
        console.print(f"   Total: {summary['total']} | "
                     f"[green]Passed: {summary['passed']}[/green] | "
                     f"[red]Failed: {summary['failed']}[/red] | "
                     f"Rate: {summary['success_rate']}")


def setup_logging(level: str = "INFO", log_file: str = "bot.log") -> logging.Logger:
    """
    Setup professional logging configuration.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Name of log file
        
    Returns:
        Configured root logger
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Create formatters
    file_formatter = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # File handler
    log_path = os.path.join(LOGS_DIR, log_file)
    file_handler = logging.FileHandler(log_path, encoding='utf-8')
    file_handler.setLevel(log_level)
    file_handler.setFormatter(file_formatter)
    
    # Console handler with Rich
    console_handler = RichHandler(
        console=console,
        show_time=True,
        show_level=True,
        show_path=False,
        rich_tracebacks=True
    )
    console_handler.setLevel(log_level)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get a named logger."""
    return logging.getLogger(name)


def get_checkpoint_logger(module: str) -> CheckpointLogger:
    """Get a checkpoint logger for a module."""
    return CheckpointLogger(module)


# Convenience logging functions
def log_info(message: str, module: str = "Bot"):
    """Log info message."""
    logging.getLogger(module).info(message)


def log_warning(message: str, module: str = "Bot"):
    """Log warning message."""
    logging.getLogger(module).warning(message)


def log_error(message: str, module: str = "Bot", exception: Exception = None):
    """
    Log error message with detailed explanation.
    
    Args:
        message: What happened
        module: Module name
        exception: Optional exception object
    """
    logger = logging.getLogger(module)
    if exception:
        logger.error(f"{message} | Exception: {type(exception).__name__}: {str(exception)}")
    else:
        logger.error(message)


def log_step(step_name: str, status: str, details: str = None):
    """
    Log an execution step.
    
    Args:
        step_name: Name of the step
        status: "start", "success", "failed"
        details: Additional details
    """
    icons = {"start": "🔄", "success": "✔️", "failed": "❌"}
    icon = icons.get(status, "•")
    
    message = f"{icon} {step_name}"
    if details:
        message += f" - {details}"
    
    if status == "failed":
        logging.error(message)
    else:
        logging.info(message)

