"""
Production Runner - Long-running session management with logging and monitoring.

Features:
- Rotating file logs
- Stability monitoring
- Graceful shutdown handling
- Session statistics
- Risk/rate control
"""

import asyncio
import logging
import signal
import sys
import time
import random
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from logging.handlers import RotatingFileHandler
import os

from src.core.session_manager import SessionManager
from src.core.proxy_manager import ProxyManager, RotationStrategy
from data.database import DatabaseManager
from src.modules.account_creator import AccountCreator
from src.modules.follow_bot import FollowBot


class RiskController:
    """
    Manages rate limiting, cooldowns, and adaptive behavior based on success rates.
    """
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        
        # Rate limits
        self.hourly_account_limit = 5  # Max accounts per hour
        self.hourly_follow_limit = 20  # Max follows per hour
        self.daily_account_limit = 20  # Max accounts per day
        self.daily_follow_limit = 100  # Max follows per day
        
        # Adaptive delays
        self.base_delay = 30  # Base delay between operations (seconds)
        self.min_delay = 15
        self.max_delay = 180
        self.current_delay = self.base_delay
        
        # Tracking
        self.hourly_accounts = 0
        self.hourly_follows = 0
        self.daily_accounts = 0
        self.daily_follows = 0
        self.last_hour_reset = datetime.now()
        self.last_day_reset = datetime.now()
        
        # Success tracking for adaptive behavior
        self.recent_results: List[bool] = []
        self.suspicious_activity_count = 0
    
    def reset_counters_if_needed(self):
        """Reset hourly/daily counters."""
        now = datetime.now()
        
        if now - self.last_hour_reset > timedelta(hours=1):
            self.hourly_accounts = 0
            self.hourly_follows = 0
            self.last_hour_reset = now
        
        if now - self.last_day_reset > timedelta(days=1):
            self.daily_accounts = 0
            self.daily_follows = 0
            self.last_day_reset = now
    
    def can_create_account(self) -> tuple:
        """Check if we can create an account."""
        self.reset_counters_if_needed()
        
        if self.daily_accounts >= self.daily_account_limit:
            return False, f"Daily limit reached ({self.daily_account_limit})"
        if self.hourly_accounts >= self.hourly_account_limit:
            return False, f"Hourly limit reached ({self.hourly_account_limit})"
        if self.suspicious_activity_count >= 3:
            return False, "Too many suspicious activities, cooling down"
        
        return True, "OK"
    
    def can_follow(self) -> tuple:
        """Check if we can perform a follow."""
        self.reset_counters_if_needed()
        
        if self.daily_follows >= self.daily_follow_limit:
            return False, f"Daily follow limit reached ({self.daily_follow_limit})"
        if self.hourly_follows >= self.hourly_follow_limit:
            return False, f"Hourly follow limit reached ({self.hourly_follow_limit})"
        
        return True, "OK"
    
    def record_result(self, success: bool, task_type: str):
        """Record operation result and adjust delays."""
        self.recent_results.append(success)
        if len(self.recent_results) > 10:
            self.recent_results.pop(0)
        
        if task_type == 'account_creation':
            self.hourly_accounts += 1
            self.daily_accounts += 1
        elif task_type == 'follow':
            self.hourly_follows += 1
            self.daily_follows += 1
        
        self._adjust_delay()
    
    def record_suspicious_activity(self, reason: str):
        """Record suspicious activity (CAPTCHA, ban, etc.)."""
        self.suspicious_activity_count += 1
        logging.warning(f"Suspicious activity recorded: {reason} (count: {self.suspicious_activity_count})")
        
        # Increase delay significantly
        self.current_delay = min(self.max_delay, self.current_delay * 2)
        
        # Reset after cooldown
        if self.suspicious_activity_count >= 3:
            logging.warning("Entering extended cooldown due to suspicious activity")
    
    def reset_suspicious_count(self):
        """Reset suspicious activity counter (call after successful operations)."""
        if self.suspicious_activity_count > 0:
            self.suspicious_activity_count = max(0, self.suspicious_activity_count - 1)
    
    def _adjust_delay(self):
        """Adjust delay based on recent success rate."""
        if len(self.recent_results) < 3:
            return
        
        success_rate = sum(self.recent_results) / len(self.recent_results)
        
        if success_rate >= 0.8:
            # High success, can decrease delay
            self.current_delay = max(self.min_delay, self.current_delay * 0.9)
        elif success_rate < 0.5:
            # Low success, increase delay
            self.current_delay = min(self.max_delay, self.current_delay * 1.5)
    
    def get_delay(self) -> int:
        """Get current delay with some randomization."""
        variance = self.current_delay * 0.3
        return int(self.current_delay + random.uniform(-variance, variance))
    
    def get_stats(self) -> Dict:
        """Get current risk control statistics."""
        return {
            "hourly_accounts": f"{self.hourly_accounts}/{self.hourly_account_limit}",
            "hourly_follows": f"{self.hourly_follows}/{self.hourly_follow_limit}",
            "daily_accounts": f"{self.daily_accounts}/{self.daily_account_limit}",
            "daily_follows": f"{self.daily_follows}/{self.daily_follow_limit}",
            "current_delay": f"{self.current_delay:.1f}s",
            "suspicious_count": self.suspicious_activity_count,
            "recent_success_rate": f"{sum(self.recent_results)/len(self.recent_results)*100:.1f}%" if self.recent_results else "N/A"
        }


class ProductionRunner:
    """
    Production-ready runner for long-running sessions.
    """
    
    def __init__(self, headless: bool = True, log_dir: str = "logs"):
        self.headless = headless
        self.log_dir = log_dir
        self.running = False
        self.shutdown_requested = False
        
        # Setup logging
        self._setup_logging()
        
        # Initialize components
        self.db = DatabaseManager()
        self.session = SessionManager(headless=headless)
        self.proxy_manager = ProxyManager(db_manager=self.db)
        self.risk_controller = RiskController(self.db)
        
        # Statistics
        self.start_time = None
        self.total_accounts_created = 0
        self.total_follows = 0
        self.total_failures = 0
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        self.logger = logging.getLogger("ProductionRunner")
    
    def _setup_logging(self):
        """Setup rotating file logs and console logging."""
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Create formatters
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # Root logger setup
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        
        # Remove existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # Rotating file handler (10MB max, keep 5 files)
        file_handler = RotatingFileHandler(
            os.path.join(self.log_dir, 'bot.log'),
            maxBytes=10*1024*1024,
            backupCount=5
        )
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(logging.DEBUG)
        root_logger.addHandler(file_handler)
        
        # Error log (separate file)
        error_handler = RotatingFileHandler(
            os.path.join(self.log_dir, 'errors.log'),
            maxBytes=5*1024*1024,
            backupCount=3
        )
        error_handler.setFormatter(file_formatter)
        error_handler.setLevel(logging.ERROR)
        root_logger.addHandler(error_handler)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(console_formatter)
        console_handler.setLevel(logging.INFO)
        root_logger.addHandler(console_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self.logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.shutdown_requested = True
    
    async def initialize(self):
        """Initialize all components."""
        self.logger.info("Initializing ProductionRunner...")
        
        # Start browser
        await self.session.start()
        
        # Setup proxies
        self.logger.info("Fetching and validating proxies...")
        self.proxy_manager.fetch_free_proxies()
        self.proxy_manager.check_proxies(max_workers=20, limit=100)
        self.proxy_manager.set_rotation_strategy(RotationStrategy.LEAST_USED)
        
        self.start_time = datetime.now()
        self.running = True
        self.logger.info("Initialization complete")
    
    async def shutdown(self):
        """Graceful shutdown."""
        self.logger.info("Shutting down...")
        self.running = False
        
        # Print final statistics
        self._print_session_summary()
        
        # Cleanup
        await self.session.stop()
        self.db.close()
        
        self.logger.info("Shutdown complete")
    
    def _print_session_summary(self):
        """Print session summary."""
        if not self.start_time:
            return
        
        duration = datetime.now() - self.start_time
        hours = duration.total_seconds() / 3600
        
        self.logger.info("=" * 50)
        self.logger.info("SESSION SUMMARY")
        self.logger.info("=" * 50)
        self.logger.info(f"Duration: {duration}")
        self.logger.info(f"Accounts Created: {self.total_accounts_created}")
        self.logger.info(f"Follows Completed: {self.total_follows}")
        self.logger.info(f"Total Failures: {self.total_failures}")
        if hours > 0:
            self.logger.info(f"Accounts/Hour: {self.total_accounts_created/hours:.2f}")
            self.logger.info(f"Follows/Hour: {self.total_follows/hours:.2f}")
        self.logger.info("Risk Control Stats: " + str(self.risk_controller.get_stats()))
        self.logger.info("=" * 50)
    
    async def run_account_creation_loop(self, target_count: int = None):
        """
        Run account creation loop.
        
        Args:
            target_count: Target number of accounts (None for infinite)
        """
        await self.initialize()
        
        creator = AccountCreator(self.session, self.db, self.proxy_manager)
        count = 0
        
        self.logger.info(f"Starting account creation loop (target: {target_count or 'unlimited'})")
        
        try:
            while self.running and not self.shutdown_requested:
                if target_count and count >= target_count:
                    self.logger.info(f"Target count {target_count} reached")
                    break
                
                # Check rate limits
                can_proceed, reason = self.risk_controller.can_create_account()
                if not can_proceed:
                    self.logger.warning(f"Rate limit: {reason}. Waiting 1 hour...")
                    await asyncio.sleep(3600)
                    continue
                
                # Create account
                self.logger.info(f"Creating account #{count + 1}...")
                result = await creator.create_account(use_proxy=True)
                
                if result["success"]:
                    self.total_accounts_created += 1
                    self.risk_controller.record_result(True, 'account_creation')
                    self.risk_controller.reset_suspicious_count()
                    self.logger.info(f"✓ Account created: {result['username']}")
                else:
                    self.total_failures += 1
                    self.risk_controller.record_result(False, 'account_creation')
                    
                    if "captcha" in str(result.get("error", "")).lower():
                        self.risk_controller.record_suspicious_activity("CAPTCHA failure")
                    
                    self.logger.warning(f"✗ Account creation failed: {result.get('error')}")
                
                count += 1
                
                # Adaptive delay
                delay = self.risk_controller.get_delay()
                self.logger.info(f"Waiting {delay}s before next attempt...")
                await asyncio.sleep(delay)
                
                # Periodic stats
                if count % 5 == 0:
                    self.logger.info(f"Stats: {self.risk_controller.get_stats()}")
        
        except Exception as e:
            self.logger.error(f"Loop error: {e}")
        finally:
            await self.shutdown()
    
    async def run_follow_loop(self, target_user_id: str, target_count: int = None):
        """
        Run follow loop for a specific user.
        
        Args:
            target_user_id: The Roblox user ID to follow
            target_count: Target number of follows (None for infinite)
        """
        await self.initialize()
        
        bot = FollowBot(self.session, self.db)
        count = 0
        
        self.logger.info(f"Starting follow loop for user {target_user_id} (target: {target_count or 'unlimited'})")
        
        try:
            while self.running and not self.shutdown_requested:
                if target_count and count >= target_count:
                    self.logger.info(f"Target count {target_count} reached")
                    break
                
                # Check rate limits
                can_proceed, reason = self.risk_controller.can_follow()
                if not can_proceed:
                    self.logger.warning(f"Rate limit: {reason}. Waiting 1 hour...")
                    await asyncio.sleep(3600)
                    continue
                
                # Get an available account
                account = self.db.get_account_by_least_used()
                if not account:
                    self.logger.warning("No available accounts. Waiting...")
                    await asyncio.sleep(300)
                    continue
                
                # Perform follow
                self.logger.info(f"Following with account {account.username}...")
                success = await bot.follow_user(target_user_id, account.id)
                
                if success:
                    self.total_follows += 1
                    self.risk_controller.record_result(True, 'follow')
                    self.logger.info(f"✓ Follow successful with {account.username}")
                else:
                    self.total_failures += 1
                    self.risk_controller.record_result(False, 'follow')
                    self.logger.warning(f"✗ Follow failed with {account.username}")
                
                count += 1
                
                # Delay
                delay = self.risk_controller.get_delay()
                self.logger.info(f"Waiting {delay}s before next follow...")
                await asyncio.sleep(delay)
        
        except Exception as e:
            self.logger.error(f"Loop error: {e}")
        finally:
            await self.shutdown()
    
    async def run_mixed_loop(self, target_user_id: str, account_ratio: float = 0.3):
        """
        Run mixed loop: create accounts and follow.
        
        Args:
            target_user_id: User to follow with created accounts
            account_ratio: Ratio of account creation vs follows (0.3 = 30% creation)
        """
        await self.initialize()
        
        creator = AccountCreator(self.session, self.db, self.proxy_manager)
        bot = FollowBot(self.session, self.db)
        
        self.logger.info(f"Starting mixed loop (account ratio: {account_ratio})")
        
        try:
            while self.running and not self.shutdown_requested:
                # Decide action based on ratio and limits
                should_create = random.random() < account_ratio
                
                if should_create:
                    can_create, reason = self.risk_controller.can_create_account()
                    if can_create:
                        result = await creator.create_account(use_proxy=True)
                        if result["success"]:
                            self.total_accounts_created += 1
                            self.risk_controller.record_result(True, 'account_creation')
                        else:
                            self.total_failures += 1
                            self.risk_controller.record_result(False, 'account_creation')
                    else:
                        should_create = False  # Fall back to follow
                
                if not should_create:
                    can_follow, reason = self.risk_controller.can_follow()
                    if can_follow:
                        account = self.db.get_account_by_least_used()
                        if account:
                            success = await bot.follow_user(target_user_id, account.id)
                            if success:
                                self.total_follows += 1
                                self.risk_controller.record_result(True, 'follow')
                            else:
                                self.total_failures += 1
                                self.risk_controller.record_result(False, 'follow')
                
                # Delay
                delay = self.risk_controller.get_delay()
                await asyncio.sleep(delay)
                
        except Exception as e:
            self.logger.error(f"Loop error: {e}")
        finally:
            await self.shutdown()


# CLI entry point
async def main():
    """Main entry point for production runner."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Production Roblox Bot Runner")
    parser.add_argument("--mode", choices=["accounts", "follow", "mixed"], default="accounts",
                       help="Operation mode")
    parser.add_argument("--target-user", type=str, help="Target user ID for follow mode")
    parser.add_argument("--count", type=int, default=None, help="Target count (optional)")
    parser.add_argument("--headless", action="store_true", default=True, help="Run headless")
    parser.add_argument("--no-headless", action="store_true", help="Run with visible browser")
    
    args = parser.parse_args()
    
    headless = not args.no_headless
    runner = ProductionRunner(headless=headless)
    
    if args.mode == "accounts":
        await runner.run_account_creation_loop(target_count=args.count)
    elif args.mode == "follow":
        if not args.target_user:
            print("Error: --target-user required for follow mode")
            return
        await runner.run_follow_loop(args.target_user, target_count=args.count)
    elif args.mode == "mixed":
        if not args.target_user:
            print("Error: --target-user required for mixed mode")
            return
        await runner.run_mixed_loop(args.target_user)


if __name__ == "__main__":
    asyncio.run(main())

