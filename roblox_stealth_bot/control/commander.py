"""
Commander - Central command system for the Roblox automation bot.

This is the brain that coordinates all operations:
- Manages configuration
- Schedules tasks
- Applies rules
- Monitors health
- Provides unified API

Usage:
    commander = Commander()
    await commander.initialize()
    await commander.create_accounts(count=5)
    await commander.follow_user("target123", count=10)
"""

import asyncio
import logging
import yaml
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

from core.session_manager import SessionManager
from core.proxy_manager import ProxyManager, RotationStrategy
from data.database import DatabaseManager
from flows.account_flow import AccountFlow, AccountFlowResult
from flows.follow_flow import FollowFlow, FollowFlowResult, batch_follow

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


@dataclass
class TaskInfo:
    """Information about a scheduled/running task."""
    
    task_id: str
    task_type: str  # "create_accounts", "follow"
    status: TaskStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Task parameters
    params: Dict = field(default_factory=dict)
    
    # Progress
    total: int = 0
    completed: int = 0
    failed: int = 0
    
    # Results
    results: List[Dict] = field(default_factory=list)
    error: str = ""
    
    @property
    def progress_percent(self) -> float:
        if self.total == 0:
            return 0
        return (self.completed + self.failed) / self.total * 100


class RuleEngine:
    """
    Self-improving rules engine.
    
    Monitors performance and adjusts behavior automatically.
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.rules_config = config.get('rules', {})
        self.enabled = self.rules_config.get('enabled', True)
        
        # Tracking
        self.recent_results: List[bool] = []
        self.failure_streak = 0
        self.last_adjustment = datetime.now()
        
        # Current multipliers
        self.delay_multiplier = 1.0
        self.pause_until: Optional[datetime] = None
    
    def record_result(self, success: bool, task_type: str):
        """Record a task result and trigger rule evaluation."""
        if not self.enabled:
            return
        
        self.recent_results.append(success)
        if len(self.recent_results) > 20:
            self.recent_results.pop(0)
        
        if success:
            self.failure_streak = 0
            self._on_success()
        else:
            self.failure_streak += 1
            self._on_failure()
    
    def _on_success(self):
        """Handle successful result."""
        # Gradually reduce delay multiplier on success
        if self.delay_multiplier > 1.0:
            self.delay_multiplier = max(1.0, self.delay_multiplier * 0.95)
            logger.debug(f"Delay multiplier reduced to {self.delay_multiplier:.2f}")
    
    def _on_failure(self):
        """Handle failed result."""
        failure_config = self.rules_config.get('failure_streak_adjustment', {})
        
        if failure_config.get('enabled', True):
            threshold = failure_config.get('threshold', 3)
            multiplier = failure_config.get('delay_multiplier', 2.0)
            
            if self.failure_streak >= threshold:
                self.delay_multiplier = min(5.0, self.delay_multiplier * multiplier)
                logger.warning(f"Failure streak reached {threshold}. Delay multiplier: {self.delay_multiplier:.2f}")
                self.failure_streak = 0
    
    def record_ban(self):
        """Handle ban detection."""
        ban_config = self.rules_config.get('ban_detection', {})
        
        if ban_config.get('enabled', True):
            pause_hours = ban_config.get('pause_hours', 6)
            self.pause_until = datetime.now() + timedelta(hours=pause_hours)
            logger.warning(f"Ban detected! Pausing until {self.pause_until}")
    
    def can_proceed(self) -> tuple:
        """Check if operations can proceed."""
        if self.pause_until and datetime.now() < self.pause_until:
            remaining = self.pause_until - datetime.now()
            return False, f"Paused for {remaining.seconds // 60} more minutes (ban cooldown)"
        
        return True, "OK"
    
    def get_adjusted_delay(self, base_delay: float) -> float:
        """Get delay with rule adjustments applied."""
        return base_delay * self.delay_multiplier
    
    def get_success_rate(self) -> float:
        """Get recent success rate."""
        if not self.recent_results:
            return 1.0
        return sum(self.recent_results) / len(self.recent_results)
    
    def get_stats(self) -> Dict:
        """Get rule engine statistics."""
        return {
            "enabled": self.enabled,
            "delay_multiplier": round(self.delay_multiplier, 2),
            "failure_streak": self.failure_streak,
            "success_rate": f"{self.get_success_rate()*100:.1f}%",
            "paused_until": str(self.pause_until) if self.pause_until else None
        }


class Commander:
    """
    Central command system.
    
    This is the main entry point for all bot operations.
    """
    
    def __init__(self, config_path: str = "config/config.yaml", headless: bool = None):
        self.config_path = config_path
        self.config: Dict = {}
        self.headless_override = headless  # CLI can override config
        
        # Components (initialized in initialize())
        self.session: Optional[SessionManager] = None
        self.db: Optional[DatabaseManager] = None
        self.proxy_manager: Optional[ProxyManager] = None
        self.rule_engine: Optional[RuleEngine] = None
        
        # Task management
        self.tasks: Dict[str, TaskInfo] = {}
        self.task_counter = 0
        self.running = False
        self.current_task: Optional[TaskInfo] = None
        
        # Stats
        self.started_at: Optional[datetime] = None
        self.total_accounts_created = 0
        self.total_follows = 0
    
    def _load_config(self):
        """Load configuration from YAML file."""
        try:
            with open(self.config_path, 'r') as f:
                self.config = yaml.safe_load(f)
            logger.info(f"Configuration loaded from {self.config_path}")
        except FileNotFoundError:
            logger.warning(f"Config not found: {self.config_path}. Using defaults.")
            self.config = self._default_config()
    
    def _default_config(self) -> Dict:
        """Return default configuration."""
        return {
            'system': {'headless': False, 'log_level': 'INFO'},
            'rate_limits': {
                'accounts_per_hour': 5,
                'accounts_per_day': 20,
                'follows_per_hour': 20
            },
            'delays': {
                'between_accounts_min': 30,
                'between_accounts_max': 90
            },
            'rules': {'enabled': True}
        }
    
    async def initialize(self):
        """Initialize all components."""
        logger.info("Initializing Commander...")
        
        # Load config
        self._load_config()
        
        # Initialize database
        self.db = DatabaseManager()
        
        # Initialize session manager - CLI override takes precedence
        if self.headless_override is not None:
            headless = self.headless_override
        else:
            headless = self.config.get('system', {}).get('headless', False)
        self.session = SessionManager(headless=headless)
        await self.session.start()
        
        # Initialize proxy manager
        proxy_config = self.config.get('proxy', {})
        self.proxy_manager = ProxyManager(db_manager=self.db)
        
        if proxy_config.get('enabled', False):
            if proxy_config.get('auto_fetch', True):
                self.proxy_manager.fetch_free_proxies()
                limit = proxy_config.get('fetch_limit', 100)
                self.proxy_manager.check_proxies(limit=limit)
            
            strategy = proxy_config.get('rotation_strategy', 'least_used')
            self.proxy_manager.set_rotation_strategy(RotationStrategy[strategy.upper()])
        
        # Initialize rule engine
        self.rule_engine = RuleEngine(self.config)
        
        self.running = True
        self.started_at = datetime.now()
        
        logger.info("Commander initialized successfully")
    
    async def shutdown(self):
        """Graceful shutdown."""
        logger.info("Shutting down Commander...")
        self.running = False
        
        if self.session:
            await self.session.stop()
        
        if self.db:
            self.db.close()
        
        self._print_summary()
        logger.info("Commander shutdown complete")
    
    def _print_summary(self):
        """Print session summary."""
        if not self.started_at:
            return
        
        duration = datetime.now() - self.started_at
        
        logger.info("="*50)
        logger.info("SESSION SUMMARY")
        logger.info(f"  Duration: {duration}")
        logger.info(f"  Accounts Created: {self.total_accounts_created}")
        logger.info(f"  Follows Completed: {self.total_follows}")
        logger.info(f"  Tasks Completed: {len([t for t in self.tasks.values() if t.status == TaskStatus.COMPLETED])}")
        if self.rule_engine:
            logger.info(f"  Rule Engine: {self.rule_engine.get_stats()}")
        logger.info("="*50)
    
    # ============== Core Operations ==============
    
    async def create_accounts(self, count: int = 1, use_proxy: bool = None) -> TaskInfo:
        """
        Create multiple accounts.
        
        Args:
            count: Number of accounts to create
            use_proxy: Whether to use proxy (None = use config)
        """
        # Check rules
        can_proceed, reason = self.rule_engine.can_proceed()
        if not can_proceed:
            logger.warning(f"Cannot proceed: {reason}")
            return None
        
        # Create task
        task = self._create_task("create_accounts", {"count": count}, total=count)
        
        if use_proxy is None:
            use_proxy = self.config.get('proxy', {}).get('enabled', False)
        
        logger.info(f"Starting task {task.task_id}: Create {count} accounts")
        
        for i in range(count):
            if not self.running:
                task.status = TaskStatus.CANCELLED
                break
            
            logger.info(f"Creating account {i+1}/{count}...")
            
            # Create account
            flow = AccountFlow(self.session, self.db, self.proxy_manager)
            result = await flow.execute(use_proxy=use_proxy)
            
            # Record result
            self.rule_engine.record_result(result.success, "create_accounts")
            
            if result.success:
                task.completed += 1
                self.total_accounts_created += 1
                task.results.append({
                    "username": result.identity.username,
                    "success": True
                })
            else:
                task.failed += 1
                task.results.append({
                    "error": result.error,
                    "success": False
                })
            
            # Delay between accounts
            if i < count - 1:
                delay = self._get_delay("between_accounts")
                delay = self.rule_engine.get_adjusted_delay(delay)
                logger.info(f"Waiting {delay:.0f}s before next account...")
                await asyncio.sleep(delay)
        
        task.status = TaskStatus.COMPLETED if task.failed == 0 else TaskStatus.FAILED
        task.completed_at = datetime.now()
        
        return task
    
    async def follow_user(self, target: str, count: int = 1, 
                          target_is_id: bool = False) -> TaskInfo:
        """
        Follow a user with multiple accounts.
        
        Args:
            target: Username or UserID to follow
            count: Number of accounts to use
            target_is_id: True if target is a numeric UserID
        """
        can_proceed, reason = self.rule_engine.can_proceed()
        if not can_proceed:
            logger.warning(f"Cannot proceed: {reason}")
            return None
        
        task = self._create_task("follow", {"target": target, "count": count}, total=count)
        
        logger.info(f"Starting task {task.task_id}: Follow {target} with {count} accounts")
        
        for i in range(count):
            if not self.running:
                task.status = TaskStatus.CANCELLED
                break
            
            logger.info(f"Follow attempt {i+1}/{count}...")
            
            flow = FollowFlow(self.session, self.db)
            result = await flow.execute(target, target_is_id=target_is_id)
            
            self.rule_engine.record_result(result.success, "follow")
            
            if result.success:
                task.completed += 1
                self.total_follows += 1
            elif result.already_following:
                task.completed += 1  # Count as success
            else:
                task.failed += 1
            
            task.results.append({
                "account": result.account_used,
                "success": result.success,
                "already_following": result.already_following,
                "error": result.error
            })
            
            # Delay
            if i < count - 1:
                delay = self._get_delay("between_follows")
                delay = self.rule_engine.get_adjusted_delay(delay)
                await asyncio.sleep(delay)
        
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now()
        
        return task
    
    # ============== Helper Methods ==============
    
    def _create_task(self, task_type: str, params: Dict, total: int = 0) -> TaskInfo:
        """Create a new task."""
        self.task_counter += 1
        task_id = f"{task_type}_{self.task_counter}"
        
        task = TaskInfo(
            task_id=task_id,
            task_type=task_type,
            status=TaskStatus.RUNNING,
            created_at=datetime.now(),
            started_at=datetime.now(),
            params=params,
            total=total
        )
        
        self.tasks[task_id] = task
        self.current_task = task
        
        return task
    
    def _get_delay(self, delay_type: str) -> float:
        """Get configured delay with randomization."""
        import random
        
        delays = self.config.get('delays', {})
        min_delay = delays.get(f'{delay_type}_min', 30)
        max_delay = delays.get(f'{delay_type}_max', 90)
        
        return random.uniform(min_delay, max_delay)
    
    # ============== Status & Info ==============
    
    def get_status(self) -> Dict:
        """Get current system status."""
        return {
            "running": self.running,
            "started_at": str(self.started_at) if self.started_at else None,
            "uptime": str(datetime.now() - self.started_at) if self.started_at else None,
            "accounts_created": self.total_accounts_created,
            "follows_completed": self.total_follows,
            "current_task": self.current_task.task_id if self.current_task else None,
            "total_tasks": len(self.tasks),
            "rule_engine": self.rule_engine.get_stats() if self.rule_engine else None,
            "accounts_available": self.db.get_account_stats()['active'] if self.db else 0
        }
    
    def get_accounts(self, limit: int = 10) -> List[Dict]:
        """Get list of accounts."""
        from data.database import Account
        accounts = Account.select().order_by(Account.created_at.desc()).limit(limit)
        return [{"username": a.username, "status": a.status, 
                 "follow_count": a.follow_count, "created": str(a.created_at)} 
                for a in accounts]
    
    def get_task_history(self) -> List[Dict]:
        """Get task history."""
        return [
            {
                "id": t.task_id,
                "type": t.task_type,
                "status": t.status.value,
                "progress": f"{t.completed}/{t.total}",
                "created": str(t.created_at)
            }
            for t in self.tasks.values()
        ]


# Convenience function
async def quick_run(action: str, **kwargs):
    """
    Quick run function for simple operations.
    
    Examples:
        await quick_run("create", count=3)
        await quick_run("follow", target="123456", count=5)
    """
    commander = Commander()
    await commander.initialize()
    
    try:
        if action == "create":
            count = kwargs.get("count", 1)
            result = await commander.create_accounts(count)
            return result
        
        elif action == "follow":
            target = kwargs.get("target")
            count = kwargs.get("count", 1)
            if not target:
                raise ValueError("target is required for follow action")
            result = await commander.follow_user(target, count)
            return result
        
        elif action == "status":
            return commander.get_status()
    
    finally:
        await commander.shutdown()
