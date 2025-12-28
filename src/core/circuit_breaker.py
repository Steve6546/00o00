"""
Circuit Breaker - Prevents repeated failures on the same session.

Purpose:
- Stop hammering a failing session/account
- Give accounts time to recover
- Prevent wasting resources on dead sessions

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Circuit tripped, all requests blocked
- HALF_OPEN: Testing if service recovered

Pattern: After N consecutive failures, open circuit.
After timeout, move to half-open and test with one request.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """State of a circuit."""
    CLOSED = "closed"      # Normal - requests pass through
    OPEN = "open"          # Tripped - requests blocked
    HALF_OPEN = "half_open"  # Testing - one request allowed


@dataclass
class CircuitInfo:
    """Information about a circuit."""
    
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure: Optional[datetime] = None
    last_success: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    
    # For half-open state
    test_allowed: bool = True


class CircuitBreaker:
    """
    Circuit breaker for session/account operations.
    
    Usage:
        breaker = CircuitBreaker()
        
        # Before operation
        if not breaker.can_use(account_id):
            # Skip this account
            continue
            
        # After operation
        if success:
            breaker.record_success(account_id)
        else:
            breaker.record_failure(account_id)
    """
    
    def __init__(
        self,
        failure_threshold: int = 3,
        reset_timeout: int = 300,
        half_open_max_calls: int = 1
    ):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Failures before opening circuit
            reset_timeout: Seconds before trying half-open
            half_open_max_calls: Test calls allowed in half-open
        """
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.half_open_max_calls = half_open_max_calls
        
        self._circuits: Dict[int, CircuitInfo] = {}
        self._lock = asyncio.Lock()
        
        # Stats
        self._total_trips = 0
        self._total_recoveries = 0
    
    def can_use(self, account_id: int) -> bool:
        """
        Check if an account can be used.
        
        Returns:
            True if the circuit allows the operation
        """
        circuit = self._get_or_create(account_id)
        
        if circuit.state == CircuitState.CLOSED:
            return True
        
        if circuit.state == CircuitState.OPEN:
            # Check if we should transition to half-open
            if self._should_try_recovery(circuit):
                self._transition_to_half_open(account_id, circuit)
                return True
            return False
        
        if circuit.state == CircuitState.HALF_OPEN:
            # Only allow if test not already in progress
            if circuit.test_allowed:
                circuit.test_allowed = False
                return True
            return False
        
        return False
    
    def record_success(self, account_id: int):
        """
        Record a successful operation.
        
        Resets failure count and closes circuit if half-open.
        """
        circuit = self._get_or_create(account_id)
        
        circuit.success_count += 1
        circuit.last_success = datetime.now()
        circuit.failure_count = 0
        
        if circuit.state == CircuitState.HALF_OPEN:
            # Recovery successful!
            self._close_circuit(account_id, circuit)
        
        logger.debug(
            f"Circuit {account_id}: SUCCESS (state={circuit.state.value})"
        )
    
    def record_failure(self, account_id: int, reason: str = ""):
        """
        Record a failed operation.
        
        Opens circuit if threshold reached.
        """
        circuit = self._get_or_create(account_id)
        
        circuit.failure_count += 1
        circuit.last_failure = datetime.now()
        
        if circuit.state == CircuitState.HALF_OPEN:
            # Test failed, reopen circuit
            self._open_circuit(account_id, circuit, f"Half-open test failed: {reason}")
        
        elif circuit.state == CircuitState.CLOSED:
            if circuit.failure_count >= self.failure_threshold:
                self._open_circuit(account_id, circuit, reason)
        
        logger.debug(
            f"Circuit {account_id}: FAILURE #{circuit.failure_count} "
            f"(state={circuit.state.value}, reason={reason})"
        )
    
    def force_open(self, account_id: int, reason: str = "Manual"):
        """Force open a circuit."""
        circuit = self._get_or_create(account_id)
        self._open_circuit(account_id, circuit, reason)
    
    def force_close(self, account_id: int):
        """Force close a circuit."""
        circuit = self._get_or_create(account_id)
        self._close_circuit(account_id, circuit)
    
    def reset(self, account_id: int = None):
        """Reset a circuit or all circuits."""
        if account_id:
            self._circuits.pop(account_id, None)
        else:
            self._circuits.clear()
    
    def _get_or_create(self, account_id: int) -> CircuitInfo:
        """Get or create circuit info for an account."""
        if account_id not in self._circuits:
            self._circuits[account_id] = CircuitInfo()
        return self._circuits[account_id]
    
    def _should_try_recovery(self, circuit: CircuitInfo) -> bool:
        """Check if we should try to recover an open circuit."""
        if not circuit.opened_at:
            return True
        
        elapsed = (datetime.now() - circuit.opened_at).total_seconds()
        return elapsed >= self.reset_timeout
    
    def _transition_to_half_open(self, account_id: int, circuit: CircuitInfo):
        """Transition circuit to half-open state."""
        circuit.state = CircuitState.HALF_OPEN
        circuit.test_allowed = True
        
        logger.info(
            f"Circuit {account_id}: OPEN → HALF_OPEN (testing recovery)"
        )
    
    def _open_circuit(self, account_id: int, circuit: CircuitInfo, reason: str):
        """Open (trip) a circuit."""
        was_closed = circuit.state == CircuitState.CLOSED
        
        circuit.state = CircuitState.OPEN
        circuit.opened_at = datetime.now()
        
        if was_closed:
            self._total_trips += 1
        
        logger.warning(
            f"Circuit {account_id}: OPENED - {reason} "
            f"(failures={circuit.failure_count}, will retry after {self.reset_timeout}s)"
        )
    
    def _close_circuit(self, account_id: int, circuit: CircuitInfo):
        """Close (recover) a circuit."""
        was_open = circuit.state in [CircuitState.OPEN, CircuitState.HALF_OPEN]
        
        circuit.state = CircuitState.CLOSED
        circuit.failure_count = 0
        circuit.opened_at = None
        circuit.test_allowed = True
        
        if was_open:
            self._total_recoveries += 1
            logger.info(
                f"Circuit {account_id}: RECOVERED and CLOSED"
            )
    
    def get_status(self, account_id: int) -> Dict:
        """Get circuit status for an account."""
        if account_id not in self._circuits:
            return {"state": "unknown", "exists": False}
        
        circuit = self._circuits[account_id]
        return {
            "state": circuit.state.value,
            "failure_count": circuit.failure_count,
            "success_count": circuit.success_count,
            "last_failure": circuit.last_failure.isoformat() if circuit.last_failure else None,
            "last_success": circuit.last_success.isoformat() if circuit.last_success else None,
            "opened_at": circuit.opened_at.isoformat() if circuit.opened_at else None,
            "exists": True
        }
    
    def get_stats(self) -> Dict:
        """Get overall circuit breaker stats."""
        open_count = sum(
            1 for c in self._circuits.values() 
            if c.state == CircuitState.OPEN
        )
        half_open_count = sum(
            1 for c in self._circuits.values() 
            if c.state == CircuitState.HALF_OPEN
        )
        closed_count = sum(
            1 for c in self._circuits.values() 
            if c.state == CircuitState.CLOSED
        )
        
        return {
            "total_circuits": len(self._circuits),
            "open": open_count,
            "half_open": half_open_count,
            "closed": closed_count,
            "total_trips": self._total_trips,
            "total_recoveries": self._total_recoveries,
            "failure_threshold": self.failure_threshold,
            "reset_timeout_seconds": self.reset_timeout
        }
    
    def list_open_circuits(self) -> list:
        """List all open/half-open circuits."""
        return [
            {"account_id": aid, **self.get_status(aid)}
            for aid, circuit in self._circuits.items()
            if circuit.state != CircuitState.CLOSED
        ]
