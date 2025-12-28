"""
Session Pool - Thread-safe session management with smart selection.

This module provides:
1. Centralized session pool with locking
2. Smart account selection (prioritizes healthy sessions)
3. Quarantine management for failed sessions
4. Session lifecycle tracking

Key principle: Every account gets a fair chance.
Old accounts are not deprioritized - only quarantined accounts are skipped.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Set
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class SessionState(Enum):
    """State of a session in the pool."""
    AVAILABLE = "available"    # Ready for use
    IN_USE = "in_use"          # Currently being used
    QUARANTINE = "quarantine"  # Temporarily blocked
    NEEDS_REVIEW = "needs_review"  # Manual review required


@dataclass
class PooledSession:
    """A session in the pool."""
    
    account_id: int
    username: str
    state: SessionState = SessionState.AVAILABLE
    
    # Usage tracking
    last_used: Optional[datetime] = None
    times_used: int = 0
    
    # Health tracking
    consecutive_failures: int = 0
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    
    # Quarantine info
    quarantine_until: Optional[datetime] = None
    quarantine_reason: str = ""
    
    def is_available(self) -> bool:
        """Check if session is available for use."""
        if self.state == SessionState.IN_USE:
            return False
        if self.state == SessionState.QUARANTINE:
            # Check if quarantine expired
            if self.quarantine_until and datetime.now() > self.quarantine_until:
                self.state = SessionState.AVAILABLE
                self.quarantine_reason = ""
                return True
            return False
        if self.state == SessionState.NEEDS_REVIEW:
            return False
        return True


@dataclass 
class QuarantineInfo:
    """Information about a quarantined session."""
    
    account_id: int
    reason: str
    quarantined_at: datetime
    expires_at: datetime
    failure_count: int = 0


class SessionPool:
    """
    Thread-safe session pool with smart selection.
    
    Features:
    - Acquires lock before session selection (prevents race conditions)
    - Tracks session health and usage
    - Manages quarantine for failed sessions
    - Provides fair rotation among available accounts
    
    Principle: No account is permanently rejected.
    Quarantine is always temporary unless manually marked for review.
    """
    
    def __init__(self, db_manager=None):
        self.db = db_manager
        self._lock = asyncio.Lock()
        self._sessions: Dict[int, PooledSession] = {}
        self._in_use: Set[int] = set()
        
        # Quarantine settings
        self._default_quarantine_duration = 300  # 5 minutes
        self._max_quarantine_duration = 3600  # 1 hour max
        
        # Stats
        self._total_acquires = 0
        self._total_releases = 0
        self._total_quarantines = 0
    
    async def initialize(self):
        """Initialize pool from database."""
        if not self.db:
            logger.warning("SessionPool initialized without database")
            return
        
        try:
            from data.database import Account
            accounts = Account.select().where(Account.status == 'active')
            
            for account in accounts:
                self._sessions[account.id] = PooledSession(
                    account_id=account.id,
                    username=account.username,
                    state=SessionState.AVAILABLE
                )
            
            logger.info(f"SessionPool initialized with {len(self._sessions)} sessions")
            
        except Exception as e:
            logger.error(f"Failed to initialize SessionPool: {e}")
    
    async def acquire(self, purpose: str = "unknown") -> Optional[any]:
        """
        Acquire an available session for use.
        
        Args:
            purpose: What the session will be used for (for logging)
            
        Returns:
            Account object or None if no sessions available
        """
        async with self._lock:
            self._total_acquires += 1
            
            # Find best available session
            best_session = self._select_best_session()
            
            if not best_session:
                logger.warning(f"No available sessions for: {purpose}")
                return None
            
            # Mark as in use
            best_session.state = SessionState.IN_USE
            best_session.last_used = datetime.now()
            best_session.times_used += 1
            self._in_use.add(best_session.account_id)
            
            logger.info(
                f"Acquired session: {best_session.username} "
                f"(id={best_session.account_id}) for {purpose}"
            )
            
            # Get actual account object from database
            if self.db:
                try:
                    from data.database import Account
                    account = Account.get_by_id(best_session.account_id)
                    return account
                except Exception as e:
                    logger.error(f"Could not load account {best_session.account_id}: {e}")
                    # Release session since we couldn't get account
                    await self._release_internal(best_session.account_id, "load_failed")
                    return None
            
            return None
    
    def _select_best_session(self) -> Optional[PooledSession]:
        """
        Select the best available session.
        
        Selection criteria (in order):
        1. Must be available (not in use, not quarantined)
        2. Prefer sessions with recent success
        3. Prefer sessions used less frequently (fair rotation)
        4. Prefer sessions not used recently
        """
        available = [
            s for s in self._sessions.values() 
            if s.is_available()
        ]
        
        if not available:
            return None
        
        # Sort by criteria
        def session_score(s: PooledSession) -> tuple:
            # Lower score = better
            failure_penalty = s.consecutive_failures * 100
            
            # Success recency bonus (negative = better)
            if s.last_success:
                success_age = (datetime.now() - s.last_success).total_seconds()
                success_bonus = -min(success_age, 86400) / 86400 * 50  # Max 50 bonus
            else:
                success_bonus = 0
            
            # Usage count (fair rotation)
            usage_penalty = s.times_used
            
            # Recent use penalty
            if s.last_used:
                use_recency = (datetime.now() - s.last_used).total_seconds()
                recency_bonus = -min(use_recency, 3600) / 3600 * 20
            else:
                recency_bonus = -20  # Never used = bonus
            
            return (failure_penalty + success_bonus + usage_penalty + recency_bonus,)
        
        available.sort(key=session_score)
        
        return available[0]
    
    async def release(self, account_id: int, result: str = "success"):
        """
        Release a session back to the pool.
        
        Args:
            account_id: ID of account to release
            result: "success" or failure reason
        """
        async with self._lock:
            await self._release_internal(account_id, result)
    
    async def _release_internal(self, account_id: int, result: str):
        """Internal release logic (must hold lock)."""
        self._total_releases += 1
        
        if account_id not in self._sessions:
            logger.warning(f"Tried to release unknown session: {account_id}")
            return
        
        session = self._sessions[account_id]
        self._in_use.discard(account_id)
        
        if result == "success":
            session.consecutive_failures = 0
            session.last_success = datetime.now()
            session.state = SessionState.AVAILABLE
            logger.debug(f"Released session {session.username} with success")
        else:
            session.consecutive_failures += 1
            session.last_failure = datetime.now()
            
            # Check if should quarantine
            if session.consecutive_failures >= 3:
                await self._quarantine_internal(
                    account_id,
                    f"Consecutive failures: {session.consecutive_failures}",
                    duration_seconds=self._default_quarantine_duration
                )
            else:
                session.state = SessionState.AVAILABLE
                logger.debug(
                    f"Released session {session.username} with failure "
                    f"(failures: {session.consecutive_failures})"
                )
    
    async def quarantine(
        self, 
        account_id: int, 
        reason: str, 
        duration_seconds: int = None
    ):
        """
        Put a session in quarantine.
        
        Quarantine is TEMPORARY. Sessions auto-recover after duration.
        """
        async with self._lock:
            await self._quarantine_internal(account_id, reason, duration_seconds)
    
    async def _quarantine_internal(
        self, 
        account_id: int, 
        reason: str, 
        duration_seconds: int = None
    ):
        """Internal quarantine logic (must hold lock)."""
        if account_id not in self._sessions:
            return
        
        duration = duration_seconds or self._default_quarantine_duration
        duration = min(duration, self._max_quarantine_duration)
        
        session = self._sessions[account_id]
        session.state = SessionState.QUARANTINE
        session.quarantine_until = datetime.now() + timedelta(seconds=duration)
        session.quarantine_reason = reason
        
        self._in_use.discard(account_id)
        self._total_quarantines += 1
        
        logger.warning(
            f"Quarantined session {session.username}: {reason} "
            f"(until {session.quarantine_until.strftime('%H:%M:%S')})"
        )
    
    async def unquarantine(self, account_id: int):
        """Remove a session from quarantine."""
        async with self._lock:
            if account_id in self._sessions:
                session = self._sessions[account_id]
                session.state = SessionState.AVAILABLE
                session.quarantine_until = None
                session.quarantine_reason = ""
                session.consecutive_failures = 0
                logger.info(f"Unquarantined session {session.username}")
    
    async def mark_for_review(self, account_id: int, reason: str):
        """Mark a session for manual review."""
        async with self._lock:
            if account_id in self._sessions:
                session = self._sessions[account_id]
                session.state = SessionState.NEEDS_REVIEW
                session.quarantine_reason = reason
                logger.warning(f"Session {session.username} marked for review: {reason}")
    
    def add_session(self, account_id: int, username: str):
        """Add a new session to the pool."""
        if account_id not in self._sessions:
            self._sessions[account_id] = PooledSession(
                account_id=account_id,
                username=username,
                state=SessionState.AVAILABLE
            )
            logger.debug(f"Added session to pool: {username}")
    
    def remove_session(self, account_id: int):
        """Remove a session from the pool."""
        self._sessions.pop(account_id, None)
        self._in_use.discard(account_id)
    
    def get_stats(self) -> Dict:
        """Get pool statistics."""
        available = sum(1 for s in self._sessions.values() if s.is_available())
        in_use = len(self._in_use)
        quarantined = sum(
            1 for s in self._sessions.values() 
            if s.state == SessionState.QUARANTINE
        )
        needs_review = sum(
            1 for s in self._sessions.values() 
            if s.state == SessionState.NEEDS_REVIEW
        )
        
        return {
            "total_sessions": len(self._sessions),
            "available": available,
            "in_use": in_use,
            "quarantined": quarantined,
            "needs_review": needs_review,
            "total_acquires": self._total_acquires,
            "total_releases": self._total_releases,
            "total_quarantines": self._total_quarantines,
        }
    
    def get_session_details(self, account_id: int) -> Optional[Dict]:
        """Get detailed info about a specific session."""
        if account_id not in self._sessions:
            return None
        
        session = self._sessions[account_id]
        return {
            "account_id": session.account_id,
            "username": session.username,
            "state": session.state.value,
            "times_used": session.times_used,
            "consecutive_failures": session.consecutive_failures,
            "last_used": session.last_used.isoformat() if session.last_used else None,
            "last_success": session.last_success.isoformat() if session.last_success else None,
            "last_failure": session.last_failure.isoformat() if session.last_failure else None,
            "quarantine_until": session.quarantine_until.isoformat() if session.quarantine_until else None,
            "quarantine_reason": session.quarantine_reason,
        }
    
    def list_quarantined(self) -> List[Dict]:
        """List all quarantined sessions."""
        return [
            self.get_session_details(s.account_id)
            for s in self._sessions.values()
            if s.state == SessionState.QUARANTINE
        ]
