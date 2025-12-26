"""
State Machine - Event-driven state engine for the Roblox automation system.

This is the brain of the system. It manages transitions between states
and ensures the bot always knows where it is and what to do next.

Key concepts:
- States: Where the system currently is (IDLE, CREATING, etc.)
- Events: What happened (success, failure, captcha_detected, etc.)
- Transitions: Which state to move to based on current state + event
- Actions: What to do when entering/exiting a state
"""

import asyncio
import logging
from enum import Enum, auto
from typing import Callable, Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


class SystemState(Enum):
    """All possible states of the system."""
    
    # Idle states
    IDLE = "idle"
    
    # Account creation flow
    CREATING_NAVIGATING = "creating.navigating"
    CREATING_FILLING_FORM = "creating.filling_form"
    CREATING_SUBMITTING = "creating.submitting"
    CREATING_CAPTCHA = "creating.captcha"
    CREATING_WAITING = "creating.waiting"
    
    # Account verification
    VERIFYING_LOGIN = "verifying.login"
    VERIFYING_CHECK = "verifying.check"
    
    # Account ready
    ACCOUNT_READY = "account.ready"
    
    # Follow flow
    FOLLOWING_SEARCHING = "following.searching"
    FOLLOWING_NAVIGATING = "following.navigating"
    FOLLOWING_ACTION = "following.action"
    FOLLOWING_CONFIRMING = "following.confirming"
    
    # Terminal states
    SUCCESS = "success"
    FAILED = "failed"
    PAUSED = "paused"


class Event(Enum):
    """Events that can trigger state transitions."""
    
    # General
    START = "start"
    STOP = "stop"
    PAUSE = "pause"
    RESUME = "resume"
    RETRY = "retry"
    TIMEOUT = "timeout"
    ERROR = "error"
    
    # Navigation
    PAGE_LOADED = "page_loaded"
    PAGE_DETECTED = "page_detected"
    
    # Form filling
    FORM_READY = "form_ready"
    FIELD_FILLED = "field_filled"
    FORM_COMPLETE = "form_complete"
    
    # Submission
    SUBMITTED = "submitted"
    CAPTCHA_DETECTED = "captcha_detected"
    CAPTCHA_SOLVED = "captcha_solved"
    CAPTCHA_FAILED = "captcha_failed"
    
    # Account
    ACCOUNT_CREATED = "account_created"
    ACCOUNT_VERIFIED = "account_verified"
    ACCOUNT_FAILED = "account_failed"
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    
    # Follow
    TARGET_FOUND = "target_found"
    TARGET_NOT_FOUND = "target_not_found"
    FOLLOW_CLICKED = "follow_clicked"
    FOLLOW_CONFIRMED = "follow_confirmed"
    FOLLOW_FAILED = "follow_failed"
    ALREADY_FOLLOWING = "already_following"


@dataclass
class Transition:
    """Defines a state transition."""
    from_state: SystemState
    event: Event
    to_state: SystemState
    condition: Optional[Callable[['StateContext'], bool]] = None
    action: Optional[Callable[['StateContext'], Any]] = None


@dataclass
class StateContext:
    """Context data passed through state transitions."""
    
    # Current task info
    task_type: str = ""  # "create_account", "follow", etc.
    task_id: str = ""
    
    # Account being created/used
    username: str = ""
    password: str = ""
    birthday: Dict = field(default_factory=dict)
    account_id: Optional[int] = None
    
    # Target for following
    target_user: str = ""
    target_id: str = ""
    
    # Retry tracking
    retry_count: int = 0
    max_retries: int = 3
    
    # Timing
    started_at: Optional[datetime] = None
    last_event_at: Optional[datetime] = None
    
    # Error tracking
    last_error: str = ""
    errors: List[str] = field(default_factory=list)
    
    # Custom data for flows
    data: Dict = field(default_factory=dict)
    
    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries
    
    def increment_retry(self):
        self.retry_count += 1
    
    def reset_retries(self):
        self.retry_count = 0


class StateMachine:
    """
    Event-driven state machine for controlling the automation flow.
    
    Usage:
        sm = StateMachine()
        sm.register_account_flow_transitions()
        
        # Start a task
        context = StateContext(task_type="create_account")
        sm.set_context(context)
        sm.start()
        
        # Feed events
        await sm.handle_event(Event.PAGE_LOADED)
        await sm.handle_event(Event.FORM_READY)
        ...
    """
    
    def __init__(self):
        self.state = SystemState.IDLE
        self.context = StateContext()
        self.transitions: List[Transition] = []
        self.state_enter_handlers: Dict[SystemState, List[Callable]] = {}
        self.state_exit_handlers: Dict[SystemState, List[Callable]] = {}
        self.event_listeners: Dict[Event, List[Callable]] = {}
        self.history: List[tuple] = []  # (timestamp, from_state, event, to_state)
        
        # Register default transitions
        self._register_default_transitions()
    
    def _register_default_transitions(self):
        """Register common transitions."""
        # From any state, STOP goes to IDLE
        for state in SystemState:
            if state not in [SystemState.IDLE]:
                self.add_transition(Transition(state, Event.STOP, SystemState.IDLE))
                self.add_transition(Transition(state, Event.PAUSE, SystemState.PAUSED))
        
        # Resume from paused
        self.add_transition(Transition(SystemState.PAUSED, Event.RESUME, SystemState.IDLE))
    
    def register_account_flow_transitions(self):
        """Register transitions for account creation flow."""
        
        # IDLE -> Start creating
        self.add_transition(Transition(
            SystemState.IDLE,
            Event.START,
            SystemState.CREATING_NAVIGATING,
            condition=lambda ctx: ctx.task_type == "create_account"
        ))
        
        # Navigating -> Form ready
        self.add_transition(Transition(
            SystemState.CREATING_NAVIGATING,
            Event.PAGE_LOADED,
            SystemState.CREATING_FILLING_FORM
        ))
        
        self.add_transition(Transition(
            SystemState.CREATING_NAVIGATING,
            Event.FORM_READY,
            SystemState.CREATING_FILLING_FORM
        ))
        
        # Filling form -> Submit
        self.add_transition(Transition(
            SystemState.CREATING_FILLING_FORM,
            Event.FORM_COMPLETE,
            SystemState.CREATING_SUBMITTING
        ))
        
        # Submit -> various outcomes
        self.add_transition(Transition(
            SystemState.CREATING_SUBMITTING,
            Event.SUBMITTED,
            SystemState.CREATING_WAITING
        ))
        
        self.add_transition(Transition(
            SystemState.CREATING_SUBMITTING,
            Event.CAPTCHA_DETECTED,
            SystemState.CREATING_CAPTCHA
        ))
        
        # CAPTCHA handling
        self.add_transition(Transition(
            SystemState.CREATING_CAPTCHA,
            Event.CAPTCHA_SOLVED,
            SystemState.CREATING_WAITING
        ))
        
        self.add_transition(Transition(
            SystemState.CREATING_CAPTCHA,
            Event.CAPTCHA_FAILED,
            SystemState.FAILED,
            condition=lambda ctx: not ctx.can_retry()
        ))
        
        self.add_transition(Transition(
            SystemState.CREATING_CAPTCHA,
            Event.CAPTCHA_FAILED,
            SystemState.CREATING_NAVIGATING,  # Retry from start
            condition=lambda ctx: ctx.can_retry(),
            action=lambda ctx: ctx.increment_retry()
        ))
        
        # Waiting -> Account created
        self.add_transition(Transition(
            SystemState.CREATING_WAITING,
            Event.ACCOUNT_CREATED,
            SystemState.SUCCESS
        ))
        
        self.add_transition(Transition(
            SystemState.CREATING_WAITING,
            Event.CAPTCHA_DETECTED,
            SystemState.CREATING_CAPTCHA
        ))
        
        self.add_transition(Transition(
            SystemState.CREATING_WAITING,
            Event.ACCOUNT_FAILED,
            SystemState.FAILED
        ))
        
        # Error handling
        self.add_transition(Transition(
            SystemState.CREATING_FILLING_FORM,
            Event.ERROR,
            SystemState.FAILED,
            condition=lambda ctx: not ctx.can_retry()
        ))
        
        self.add_transition(Transition(
            SystemState.CREATING_FILLING_FORM,
            Event.ERROR,
            SystemState.CREATING_NAVIGATING,
            condition=lambda ctx: ctx.can_retry(),
            action=lambda ctx: ctx.increment_retry()
        ))
    
    def register_follow_flow_transitions(self):
        """Register transitions for follow flow."""
        
        # IDLE -> Start following
        self.add_transition(Transition(
            SystemState.IDLE,
            Event.START,
            SystemState.VERIFYING_LOGIN,
            condition=lambda ctx: ctx.task_type == "follow"
        ))
        
        # Login flow
        self.add_transition(Transition(
            SystemState.VERIFYING_LOGIN,
            Event.LOGIN_SUCCESS,
            SystemState.FOLLOWING_SEARCHING
        ))
        
        self.add_transition(Transition(
            SystemState.VERIFYING_LOGIN,
            Event.LOGIN_FAILED,
            SystemState.FAILED
        ))
        
        # Search for target
        self.add_transition(Transition(
            SystemState.FOLLOWING_SEARCHING,
            Event.TARGET_FOUND,
            SystemState.FOLLOWING_NAVIGATING
        ))
        
        self.add_transition(Transition(
            SystemState.FOLLOWING_SEARCHING,
            Event.TARGET_NOT_FOUND,
            SystemState.FAILED
        ))
        
        # Navigate to profile
        self.add_transition(Transition(
            SystemState.FOLLOWING_NAVIGATING,
            Event.PAGE_LOADED,
            SystemState.FOLLOWING_ACTION
        ))
        
        # Click follow
        self.add_transition(Transition(
            SystemState.FOLLOWING_ACTION,
            Event.FOLLOW_CLICKED,
            SystemState.FOLLOWING_CONFIRMING
        ))
        
        self.add_transition(Transition(
            SystemState.FOLLOWING_ACTION,
            Event.ALREADY_FOLLOWING,
            SystemState.SUCCESS
        ))
        
        # Confirm follow
        self.add_transition(Transition(
            SystemState.FOLLOWING_CONFIRMING,
            Event.FOLLOW_CONFIRMED,
            SystemState.SUCCESS
        ))
        
        self.add_transition(Transition(
            SystemState.FOLLOWING_CONFIRMING,
            Event.FOLLOW_FAILED,
            SystemState.FAILED
        ))
    
    def add_transition(self, transition: Transition):
        """Add a transition to the state machine."""
        self.transitions.append(transition)
    
    def on_enter(self, state: SystemState, handler: Callable):
        """Register a handler to run when entering a state."""
        if state not in self.state_enter_handlers:
            self.state_enter_handlers[state] = []
        self.state_enter_handlers[state].append(handler)
    
    def on_exit(self, state: SystemState, handler: Callable):
        """Register a handler to run when exiting a state."""
        if state not in self.state_exit_handlers:
            self.state_exit_handlers[state] = []
        self.state_exit_handlers[state].append(handler)
    
    def on_event(self, event: Event, handler: Callable):
        """Register a handler to run when an event occurs (regardless of transition)."""
        if event not in self.event_listeners:
            self.event_listeners[event] = []
        self.event_listeners[event].append(handler)
    
    def set_context(self, context: StateContext):
        """Set the context for the current task."""
        self.context = context
        self.context.started_at = datetime.now()
    
    async def handle_event(self, event: Event, data: Dict = None) -> bool:
        """
        Handle an event and potentially transition to a new state.
        
        Returns True if a transition occurred.
        """
        self.context.last_event_at = datetime.now()
        
        if data:
            self.context.data.update(data)
        
        logger.debug(f"Event: {event.value} in state: {self.state.value}")
        
        # Notify event listeners
        if event in self.event_listeners:
            for handler in self.event_listeners[event]:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(self.context, event)
                    else:
                        handler(self.context, event)
                except Exception as e:
                    logger.error(f"Event listener error: {e}")
        
        # Find matching transition
        for transition in self.transitions:
            if transition.from_state == self.state and transition.event == event:
                # Check condition if exists
                if transition.condition and not transition.condition(self.context):
                    continue
                
                # Transition found!
                await self._transition_to(transition.to_state, event, transition.action)
                return True
        
        logger.debug(f"No transition found for {event.value} in {self.state.value}")
        return False
    
    async def _transition_to(self, new_state: SystemState, event: Event, action: Callable = None):
        """Execute a transition to a new state."""
        old_state = self.state
        
        logger.info(f"Transition: {old_state.value} --[{event.value}]--> {new_state.value}")
        
        # Record in history
        self.history.append((datetime.now(), old_state, event, new_state))
        
        # Exit handlers
        if old_state in self.state_exit_handlers:
            for handler in self.state_exit_handlers[old_state]:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(self.context)
                    else:
                        handler(self.context)
                except Exception as e:
                    logger.error(f"Exit handler error: {e}")
        
        # Transition action
        if action:
            try:
                if asyncio.iscoroutinefunction(action):
                    await action(self.context)
                else:
                    action(self.context)
            except Exception as e:
                logger.error(f"Transition action error: {e}")
        
        # Update state
        self.state = new_state
        
        # Enter handlers
        if new_state in self.state_enter_handlers:
            for handler in self.state_enter_handlers[new_state]:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(self.context)
                    else:
                        handler(self.context)
                except Exception as e:
                    logger.error(f"Enter handler error: {e}")
    
    def is_terminal(self) -> bool:
        """Check if current state is terminal (success/failed)."""
        return self.state in [SystemState.SUCCESS, SystemState.FAILED]
    
    def is_active(self) -> bool:
        """Check if state machine is actively processing."""
        return self.state not in [SystemState.IDLE, SystemState.SUCCESS, 
                                   SystemState.FAILED, SystemState.PAUSED]
    
    def reset(self):
        """Reset state machine to IDLE."""
        self.state = SystemState.IDLE
        self.context = StateContext()
        self.history = []
    
    def get_status(self) -> Dict:
        """Get current status."""
        return {
            "state": self.state.value,
            "task_type": self.context.task_type,
            "retry_count": self.context.retry_count,
            "is_terminal": self.is_terminal(),
            "is_active": self.is_active(),
            "history_length": len(self.history),
            "last_event": self.history[-1] if self.history else None
        }


# Convenience factory
def create_account_state_machine() -> StateMachine:
    """Create a state machine configured for account creation."""
    sm = StateMachine()
    sm.register_account_flow_transitions()
    return sm


def create_follow_state_machine() -> StateMachine:
    """Create a state machine configured for following."""
    sm = StateMachine()
    sm.register_follow_flow_transitions()
    return sm


def create_full_state_machine() -> StateMachine:
    """Create a state machine with all flows registered."""
    sm = StateMachine()
    sm.register_account_flow_transitions()
    sm.register_follow_flow_transitions()
    return sm

