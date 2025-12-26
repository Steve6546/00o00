"""
Scheduler - Automated task scheduling for 24/7 operation.

Uses APScheduler to run tasks on:
- Intervals (every X minutes/hours)
- Cron schedules (specific times)
- One-time execution

Usage:
    from control.scheduler import BotScheduler
    
    scheduler = BotScheduler()
    scheduler.add_account_job(count=2, interval_hours=4)
    scheduler.add_follow_job(target="user123", interval_minutes=30)
    scheduler.start()
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Callable
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_MISSED

logger = logging.getLogger(__name__)


class BotScheduler:
    """
    Advanced task scheduler for automated bot operations.
    
    Features:
    - Multiple job types (account creation, following)
    - Cron and interval scheduling
    - Job persistence (memory-based)
    - Error handling and retry
    - Rate limiting integration
    """
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler(
            jobstores={'default': MemoryJobStore()},
            job_defaults={
                'coalesce': True,  # Combine missed executions
                'max_instances': 1,  # Only one instance at a time
                'misfire_grace_time': 300  # 5 min grace period
            }
        )
        
        self.is_running = False
        self.job_history: List[Dict] = []
        
        # Register event listeners
        self.scheduler.add_listener(self._on_job_executed, EVENT_JOB_EXECUTED)
        self.scheduler.add_listener(self._on_job_error, EVENT_JOB_ERROR)
        self.scheduler.add_listener(self._on_job_missed, EVENT_JOB_MISSED)
    
    def start(self):
        """Start the scheduler."""
        if not self.is_running:
            self.scheduler.start()
            self.is_running = True
            logger.info("🚀 Scheduler started")
    
    def stop(self):
        """Stop the scheduler."""
        if self.is_running:
            self.scheduler.shutdown(wait=True)
            self.is_running = False
            logger.info("⏹️ Scheduler stopped")
    
    def pause(self):
        """Pause all jobs."""
        self.scheduler.pause()
        logger.info("⏸️ Scheduler paused")
    
    def resume(self):
        """Resume all jobs."""
        self.scheduler.resume()
        logger.info("▶️ Scheduler resumed")
    
    # ============== Job Creation ==============
    
    def add_account_creation_job(
        self,
        count: int = 1,
        interval_hours: int = None,
        interval_minutes: int = None,
        cron_hour: int = None,
        cron_minute: int = 0,
        use_proxy: bool = False,
        job_id: str = None
    ) -> str:
        """
        Schedule account creation job.
        
        Args:
            count: Number of accounts per execution
            interval_hours: Run every X hours
            interval_minutes: Run every X minutes
            cron_hour: Run at specific hour (0-23)
            cron_minute: Run at specific minute (0-59)
            use_proxy: Whether to use proxy
            job_id: Custom job ID
        
        Returns:
            Job ID
        """
        job_id = job_id or f"account_creation_{datetime.now().strftime('%H%M%S')}"
        
        # Determine trigger
        if interval_hours:
            trigger = IntervalTrigger(hours=interval_hours)
        elif interval_minutes:
            trigger = IntervalTrigger(minutes=interval_minutes)
        elif cron_hour is not None:
            trigger = CronTrigger(hour=cron_hour, minute=cron_minute)
        else:
            trigger = IntervalTrigger(hours=6)  # Default: every 6 hours
        
        self.scheduler.add_job(
            func=self._run_account_creation,
            trigger=trigger,
            id=job_id,
            name=f"Create {count} accounts",
            kwargs={'count': count, 'use_proxy': use_proxy},
            replace_existing=True
        )
        
        logger.info(f"📝 Scheduled account creation job: {job_id}")
        return job_id
    
    def add_follow_job(
        self,
        target: str,
        count: int = 1,
        target_is_id: bool = True,
        interval_hours: int = None,
        interval_minutes: int = None,
        cron_hour: int = None,
        job_id: str = None
    ) -> str:
        """
        Schedule follow job.
        
        Args:
            target: Target user ID or username
            count: Number of accounts to use
            target_is_id: Whether target is a user ID
            interval_hours: Run every X hours
            interval_minutes: Run every X minutes
            cron_hour: Run at specific hour
            job_id: Custom job ID
        
        Returns:
            Job ID
        """
        job_id = job_id or f"follow_{target}_{datetime.now().strftime('%H%M%S')}"
        
        if interval_hours:
            trigger = IntervalTrigger(hours=interval_hours)
        elif interval_minutes:
            trigger = IntervalTrigger(minutes=interval_minutes)
        elif cron_hour is not None:
            trigger = CronTrigger(hour=cron_hour)
        else:
            trigger = IntervalTrigger(hours=1)  # Default: hourly
        
        self.scheduler.add_job(
            func=self._run_follow,
            trigger=trigger,
            id=job_id,
            name=f"Follow {target}",
            kwargs={
                'target': target, 
                'count': count, 
                'target_is_id': target_is_id
            },
            replace_existing=True
        )
        
        logger.info(f"👥 Scheduled follow job: {job_id}")
        return job_id
    
    def add_one_time_job(
        self,
        func: Callable,
        run_at: datetime,
        job_id: str = None,
        **kwargs
    ) -> str:
        """Schedule a one-time job."""
        job_id = job_id or f"onetime_{datetime.now().strftime('%H%M%S')}"
        
        self.scheduler.add_job(
            func=func,
            trigger=DateTrigger(run_date=run_at),
            id=job_id,
            kwargs=kwargs,
            replace_existing=True
        )
        
        logger.info(f"🎯 Scheduled one-time job: {job_id} at {run_at}")
        return job_id
    
    # ============== Job Execution ==============
    
    async def _run_account_creation(self, count: int, use_proxy: bool):
        """Execute account creation job."""
        logger.info(f"🔄 Running scheduled account creation: {count} accounts")
        
        try:
            from control.commander import Commander
            
            commander = Commander()
            await commander.initialize()
            
            result = await commander.create_accounts(count, use_proxy)
            
            await commander.shutdown()
            
            self._record_job_result("account_creation", {
                "count": count,
                "success": result.completed if result else 0,
                "failed": result.failed if result else count
            })
            
        except Exception as e:
            logger.error(f"Account creation job failed: {e}")
            self._record_job_result("account_creation", {"error": str(e)})
    
    async def _run_follow(self, target: str, count: int, target_is_id: bool):
        """Execute follow job."""
        logger.info(f"🔄 Running scheduled follow: {target}")
        
        try:
            from control.commander import Commander
            
            commander = Commander()
            await commander.initialize()
            
            result = await commander.follow_user(target, count, target_is_id)
            
            await commander.shutdown()
            
            self._record_job_result("follow", {
                "target": target,
                "success": result.completed if result else 0,
                "failed": result.failed if result else count
            })
            
        except Exception as e:
            logger.error(f"Follow job failed: {e}")
            self._record_job_result("follow", {"error": str(e)})
    
    # ============== Job Management ==============
    
    def remove_job(self, job_id: str):
        """Remove a scheduled job."""
        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"🗑️ Removed job: {job_id}")
        except Exception as e:
            logger.error(f"Failed to remove job {job_id}: {e}")
    
    def list_jobs(self) -> List[Dict]:
        """Get list of all scheduled jobs."""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time) if job.next_run_time else None,
                "trigger": str(job.trigger)
            })
        return jobs
    
    def get_job(self, job_id: str) -> Optional[Dict]:
        """Get info about a specific job."""
        job = self.scheduler.get_job(job_id)
        if job:
            return {
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time) if job.next_run_time else None,
                "trigger": str(job.trigger),
                "pending": job.pending
            }
        return None
    
    # ============== Event Handlers ==============
    
    def _on_job_executed(self, event):
        """Handle successful job execution."""
        logger.info(f"✅ Job executed: {event.job_id}")
    
    def _on_job_error(self, event):
        """Handle job execution error."""
        logger.error(f"❌ Job error: {event.job_id} - {event.exception}")
    
    def _on_job_missed(self, event):
        """Handle missed job execution."""
        logger.warning(f"⚠️ Job missed: {event.job_id}")
    
    def _record_job_result(self, job_type: str, result: Dict):
        """Record job execution result."""
        self.job_history.append({
            "type": job_type,
            "result": result,
            "timestamp": datetime.now().isoformat()
        })
        
        # Keep only last 100 results
        if len(self.job_history) > 100:
            self.job_history = self.job_history[-100:]
    
    def get_history(self, limit: int = 10) -> List[Dict]:
        """Get recent job execution history."""
        return self.job_history[-limit:]
    
    def get_stats(self) -> Dict:
        """Get scheduler statistics."""
        return {
            "is_running": self.is_running,
            "total_jobs": len(self.scheduler.get_jobs()),
            "history_count": len(self.job_history),
            "jobs": self.list_jobs()
        }


# ============== CLI Integration ==============

async def run_scheduler_daemon():
    """
    Run scheduler as a daemon process.
    
    Usage:
        python -m control.scheduler
    """
    import signal
    import yaml
    
    # Load schedule config
    try:
        with open("config/config.yaml", 'r') as f:
            config = yaml.safe_load(f)
    except:
        config = {}
    
    scheduler = BotScheduler()
    
    # Add default jobs from config
    schedule_config = config.get('schedule', {})
    
    if schedule_config.get('account_creation', {}).get('enabled', False):
        acc_config = schedule_config['account_creation']
        scheduler.add_account_creation_job(
            count=acc_config.get('count', 1),
            interval_hours=acc_config.get('interval_hours', 6)
        )
    
    if schedule_config.get('follow', {}).get('enabled', False):
        follow_config = schedule_config['follow']
        scheduler.add_follow_job(
            target=follow_config.get('target', ''),
            count=follow_config.get('count', 1),
            interval_hours=follow_config.get('interval_hours', 1)
        )
    
    # Handle shutdown
    def shutdown(sig, frame):
        logger.info("Received shutdown signal...")
        scheduler.stop()
    
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    scheduler.start()
    
    # Keep running
    logger.info("Scheduler daemon running. Press Ctrl+C to stop.")
    
    try:
        while scheduler.is_running:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        scheduler.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_scheduler_daemon())
