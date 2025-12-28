"""
Session Metrics - Track session performance and health statistics.

Purpose:
- Monitor success rates per session
- Compare old vs new session performance
- Track quarantine and recovery events
- Provide data for diagnostics

Metrics tracked:
- Login attempts and success rate
- Session renewals and success rate
- Fallback logins and success rate
- Time in each state
- Overall availability
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SessionEvent:
    """A single session event."""
    
    timestamp: datetime
    event_type: str  # validation, renewal, login, follow, quarantine
    success: bool
    details: str = ""
    duration_ms: Optional[float] = None


@dataclass
class SessionStats:
    """Statistics for a single session."""
    
    account_id: int
    username: str = ""
    
    # Counts
    total_operations: int = 0
    successful_operations: int = 0
    
    # Validation
    validation_attempts: int = 0
    validation_successes: int = 0
    
    # Renewal
    renewal_attempts: int = 0
    renewal_successes: int = 0
    
    # Login
    login_attempts: int = 0
    login_successes: int = 0
    
    # Follow
    follow_attempts: int = 0
    follow_successes: int = 0
    
    # Quarantine
    quarantine_count: int = 0
    current_quarantine: bool = False
    total_quarantine_time_seconds: float = 0.0
    
    # Timing
    created_at: Optional[datetime] = None
    last_used: Optional[datetime] = None
    last_success: Optional[datetime] = None
    
    # Recent events (keep last 20)
    recent_events: List[Dict] = field(default_factory=list)
    
    @property
    def success_rate(self) -> float:
        if self.total_operations == 0:
            return 0.0
        return self.successful_operations / self.total_operations * 100
    
    @property
    def login_success_rate(self) -> float:
        if self.login_attempts == 0:
            return 0.0
        return self.login_successes / self.login_attempts * 100
    
    @property
    def renewal_success_rate(self) -> float:
        if self.renewal_attempts == 0:
            return 0.0
        return self.renewal_successes / self.renewal_attempts * 100


class SessionMetrics:
    """
    Centralized metrics tracking for all sessions.
    
    Usage:
        metrics = SessionMetrics()
        
        # Record events
        metrics.record_validation(account_id, success=True)
        metrics.record_login(account_id, success=True, method="cookie")
        metrics.record_follow(account_id, success=True)
        
        # Get stats
        stats = metrics.get_session_stats(account_id)
        summary = metrics.get_summary()
    """
    
    def __init__(self, persist_path: str = None):
        """
        Initialize metrics tracker.
        
        Args:
            persist_path: Optional path to save metrics (JSON)
        """
        self._sessions: Dict[int, SessionStats] = {}
        self._global_stats = {
            "total_validations": 0,
            "total_renewals": 0,
            "total_logins": 0,
            "total_follows": 0,
            "total_quarantines": 0,
        }
        self._persist_path = persist_path
        self._start_time = datetime.now()
        
        if persist_path:
            self._load()
    
    def record_validation(
        self, 
        account_id: int, 
        success: bool, 
        status: str = "",
        username: str = ""
    ):
        """Record a session validation event."""
        stats = self._get_or_create(account_id, username)
        
        stats.validation_attempts += 1
        if success:
            stats.validation_successes += 1
        
        self._global_stats["total_validations"] += 1
        self._add_event(stats, "validation", success, status)
        
        logger.debug(
            f"Metrics: Validation for {account_id} - {status} "
            f"(success_rate: {stats.success_rate:.1f}%)"
        )
    
    def record_renewal(
        self, 
        account_id: int, 
        success: bool, 
        method: str = "",
        username: str = ""
    ):
        """Record a session renewal event."""
        stats = self._get_or_create(account_id, username)
        
        stats.renewal_attempts += 1
        if success:
            stats.renewal_successes += 1
        
        self._global_stats["total_renewals"] += 1
        self._add_event(stats, "renewal", success, method)
    
    def record_login(
        self, 
        account_id: int, 
        success: bool, 
        method: str = "credentials",
        username: str = ""
    ):
        """Record a login event."""
        stats = self._get_or_create(account_id, username)
        
        stats.login_attempts += 1
        stats.total_operations += 1
        
        if success:
            stats.login_successes += 1
            stats.successful_operations += 1
            stats.last_success = datetime.now()
        
        stats.last_used = datetime.now()
        
        self._global_stats["total_logins"] += 1
        self._add_event(stats, "login", success, method)
    
    def record_follow(
        self, 
        account_id: int, 
        success: bool, 
        target: str = "",
        username: str = ""
    ):
        """Record a follow event."""
        stats = self._get_or_create(account_id, username)
        
        stats.follow_attempts += 1
        stats.total_operations += 1
        
        if success:
            stats.follow_successes += 1
            stats.successful_operations += 1
            stats.last_success = datetime.now()
        
        stats.last_used = datetime.now()
        
        self._global_stats["total_follows"] += 1
        self._add_event(stats, "follow", success, target)
    
    def record_quarantine(
        self, 
        account_id: int, 
        reason: str = "",
        username: str = ""
    ):
        """Record a quarantine event."""
        stats = self._get_or_create(account_id, username)
        
        stats.quarantine_count += 1
        stats.current_quarantine = True
        
        self._global_stats["total_quarantines"] += 1
        self._add_event(stats, "quarantine", False, reason)
    
    def record_unquarantine(self, account_id: int, username: str = ""):
        """Record end of quarantine."""
        stats = self._get_or_create(account_id, username)
        stats.current_quarantine = False
        self._add_event(stats, "unquarantine", True, "recovered")
    
    def _get_or_create(self, account_id: int, username: str = "") -> SessionStats:
        """Get or create stats for an account."""
        if account_id not in self._sessions:
            self._sessions[account_id] = SessionStats(
                account_id=account_id,
                username=username,
                created_at=datetime.now()
            )
        elif username:
            self._sessions[account_id].username = username
        return self._sessions[account_id]
    
    def _add_event(
        self, 
        stats: SessionStats, 
        event_type: str, 
        success: bool, 
        details: str
    ):
        """Add an event to session history."""
        event = {
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "success": success,
            "details": details
        }
        
        stats.recent_events.append(event)
        
        # Keep only last 20 events
        if len(stats.recent_events) > 20:
            stats.recent_events = stats.recent_events[-20:]
        
        # Auto-save if persist path set
        if self._persist_path:
            self._save()
    
    def get_session_stats(self, account_id: int) -> Optional[Dict]:
        """Get stats for a specific session."""
        if account_id not in self._sessions:
            return None
        
        stats = self._sessions[account_id]
        return {
            "account_id": stats.account_id,
            "username": stats.username,
            "success_rate": f"{stats.success_rate:.1f}%",
            "login_success_rate": f"{stats.login_success_rate:.1f}%",
            "renewal_success_rate": f"{stats.renewal_success_rate:.1f}%",
            "total_operations": stats.total_operations,
            "successful_operations": stats.successful_operations,
            "follow_attempts": stats.follow_attempts,
            "follow_successes": stats.follow_successes,
            "quarantine_count": stats.quarantine_count,
            "currently_quarantined": stats.current_quarantine,
            "last_used": stats.last_used.isoformat() if stats.last_used else None,
            "last_success": stats.last_success.isoformat() if stats.last_success else None,
        }
    
    def get_summary(self) -> Dict:
        """Get overall metrics summary."""
        total_sessions = len(self._sessions)
        active_sessions = sum(
            1 for s in self._sessions.values() 
            if not s.current_quarantine
        )
        quarantined = total_sessions - active_sessions
        
        # Calculate average success rate
        if total_sessions > 0:
            avg_success = sum(
                s.success_rate for s in self._sessions.values()
            ) / total_sessions
        else:
            avg_success = 0
        
        # Uptime
        uptime = datetime.now() - self._start_time
        
        return {
            "uptime": str(uptime).split('.')[0],
            "total_sessions": total_sessions,
            "active_sessions": active_sessions,
            "quarantined_sessions": quarantined,
            "average_success_rate": f"{avg_success:.1f}%",
            **self._global_stats
        }
    
    def get_top_performers(self, limit: int = 5) -> List[Dict]:
        """Get top performing sessions by success rate."""
        sorted_sessions = sorted(
            self._sessions.values(),
            key=lambda s: (s.success_rate, s.total_operations),
            reverse=True
        )
        
        return [
            self.get_session_stats(s.account_id)
            for s in sorted_sessions[:limit]
            if s.total_operations > 0
        ]
    
    def get_problem_sessions(self) -> List[Dict]:
        """Get sessions with low success rate or in quarantine."""
        problems = []
        
        for stats in self._sessions.values():
            is_problem = (
                stats.current_quarantine or
                (stats.total_operations > 0 and stats.success_rate < 50) or
                stats.quarantine_count >= 2
            )
            
            if is_problem:
                problems.append({
                    **self.get_session_stats(stats.account_id),
                    "problem_reason": self._identify_problem(stats)
                })
        
        return problems
    
    def _identify_problem(self, stats: SessionStats) -> str:
        """Identify why a session is problematic."""
        reasons = []
        
        if stats.current_quarantine:
            reasons.append("currently quarantined")
        if stats.success_rate < 50 and stats.total_operations > 0:
            reasons.append(f"low success rate ({stats.success_rate:.1f}%)")
        if stats.quarantine_count >= 2:
            reasons.append(f"multiple quarantines ({stats.quarantine_count})")
        if stats.login_success_rate < 50 and stats.login_attempts > 0:
            reasons.append("login issues")
        
        return ", ".join(reasons) if reasons else "unknown"
    
    def _save(self):
        """Save metrics to file."""
        if not self._persist_path:
            return
        
        try:
            data = {
                "saved_at": datetime.now().isoformat(),
                "global_stats": self._global_stats,
                "sessions": {
                    str(k): {
                        "account_id": v.account_id,
                        "username": v.username,
                        "total_operations": v.total_operations,
                        "successful_operations": v.successful_operations,
                        "validation_attempts": v.validation_attempts,
                        "validation_successes": v.validation_successes,
                        "renewal_attempts": v.renewal_attempts,
                        "renewal_successes": v.renewal_successes,
                        "login_attempts": v.login_attempts,
                        "login_successes": v.login_successes,
                        "follow_attempts": v.follow_attempts,
                        "follow_successes": v.follow_successes,
                        "quarantine_count": v.quarantine_count,
                    }
                    for k, v in self._sessions.items()
                }
            }
            
            Path(self._persist_path).write_text(json.dumps(data, indent=2))
            
        except Exception as e:
            logger.warning(f"Could not save metrics: {e}")
    
    def _load(self):
        """Load metrics from file."""
        if not self._persist_path:
            return
        
        try:
            path = Path(self._persist_path)
            if not path.exists():
                return
            
            data = json.loads(path.read_text())
            self._global_stats.update(data.get("global_stats", {}))
            
            for aid, sdata in data.get("sessions", {}).items():
                stats = SessionStats(
                    account_id=sdata.get("account_id", int(aid)),
                    username=sdata.get("username", ""),
                    total_operations=sdata.get("total_operations", 0),
                    successful_operations=sdata.get("successful_operations", 0),
                    validation_attempts=sdata.get("validation_attempts", 0),
                    validation_successes=sdata.get("validation_successes", 0),
                    renewal_attempts=sdata.get("renewal_attempts", 0),
                    renewal_successes=sdata.get("renewal_successes", 0),
                    login_attempts=sdata.get("login_attempts", 0),
                    login_successes=sdata.get("login_successes", 0),
                    follow_attempts=sdata.get("follow_attempts", 0),
                    follow_successes=sdata.get("follow_successes", 0),
                    quarantine_count=sdata.get("quarantine_count", 0),
                )
                self._sessions[int(aid)] = stats
            
            logger.info(f"Loaded metrics for {len(self._sessions)} sessions")
            
        except Exception as e:
            logger.warning(f"Could not load metrics: {e}")
