"""
Test script for the new intelligent system.
Run with: python test_system.py
"""

import asyncio
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_account_flow():
    """Test the complete account creation flow."""
    from core.session_manager import SessionManager
    from data.database import DatabaseManager
    from flows.account_flow import AccountFlow
    
    print("\n" + "="*60)
    print("INTELLIGENT SYSTEM TEST - Account Creation Flow")
    print("="*60 + "\n")
    
    # Initialize components
    print("[1] Initializing components...")
    db = DatabaseManager()
    session = SessionManager(headless=False)  # Visible browser
    await session.start()
    
    print("[2] Creating AccountFlow...")
    flow = AccountFlow(session, db)
    
    print("[3] Executing flow (watch the browser)...")
    print("-" * 40)
    
    result = await flow.execute(use_proxy=False)
    
    print("-" * 40)
    print("\n[4] Result:")
    print(f"    Success: {result.success}")
    if result.success:
        print(f"    Username: {result.identity.username}")
        print(f"    Account ID: {result.account_id}")
    else:
        print(f"    Error: {result.error}")
    print(f"    Duration: {result.duration_seconds:.1f}s")
    print(f"    States visited: {len(result.states_visited)}")
    
    # Cleanup
    await session.stop()
    db.close()
    
    print("\n" + "="*60)
    print("TEST COMPLETE")
    print("="*60)
    
    return result


async def test_state_machine():
    """Test state machine transitions."""
    from core.state_machine import (
        create_account_state_machine, Event, SystemState
    )
    
    print("\n[State Machine Test]")
    sm = create_account_state_machine()
    
    # Test transitions
    print(f"Initial state: {sm.state.value}")
    
    # Simulate account creation flow
    sm.context.task_type = "create_account"
    await sm.handle_event(Event.START)
    print(f"After START: {sm.state.value}")
    
    await sm.handle_event(Event.PAGE_LOADED)
    print(f"After PAGE_LOADED: {sm.state.value}")
    
    await sm.handle_event(Event.FORM_COMPLETE)
    print(f"After FORM_COMPLETE: {sm.state.value}")
    
    await sm.handle_event(Event.SUBMITTED)
    print(f"After SUBMITTED: {sm.state.value}")
    
    await sm.handle_event(Event.ACCOUNT_CREATED)
    print(f"After ACCOUNT_CREATED: {sm.state.value}")
    
    print(f"Is terminal: {sm.is_terminal()}")
    print("✓ State machine test passed!\n")


async def test_identity_generator():
    """Test identity generation."""
    from generators.identity_generator import IdentityGenerator
    
    print("\n[Identity Generator Test]")
    gen = IdentityGenerator()
    
    # Generate multiple identities
    for i in range(5):
        identity = gen.generate()
        print(f"  {i+1}. {identity.username} | {identity.birthday['month']} {identity.birthday['day']}, {identity.birthday['year']}")
    
    stats = gen.get_stats()
    print(f"\nStats: {stats}")
    print("✓ Identity generator test passed!\n")


async def test_page_detector():
    """Test page detection (requires browser)."""
    from core.session_manager import SessionManager
    from core.page_detector import PageDetector
    
    print("\n[Page Detector Test]")
    
    session = SessionManager(headless=True)
    await session.start()
    
    context, page = await session.create_context()
    detector = PageDetector()
    
    # Test signup page detection
    await page.goto("https://www.roblox.com")
    await asyncio.sleep(3)
    
    result = await detector.detect(page)
    print(f"  Page: {result.page_type.value}")
    print(f"  Confidence: {result.confidence:.2f}")
    print(f"  Actions: {result.available_actions[:3]}...")
    
    await session.close_context(context)
    await session.stop()
    
    print("✓ Page detector test passed!\n")


async def test_follow_flow():
    """Test the follow flow (requires existing account)."""
    from core.session_manager import SessionManager
    from data.database import DatabaseManager, Account
    from flows.follow_flow import FollowFlow
    
    print("\n" + "="*60)
    print("FOLLOW FLOW TEST")
    print("="*60 + "\n")
    
    # Check for existing account
    db = DatabaseManager()
    account = db.get_account_by_least_used()
    
    if not account:
        print("No accounts available. Create an account first:")
        print("  python test_system.py account")
        return None
    
    print(f"[1] Using account: {account.username}")
    
    # Get target user ID (Roblox's official account as example)
    target_id = "1"  # Roblox's user ID is 1
    
    print(f"[2] Target user ID: {target_id}")
    
    session = SessionManager(headless=False)
    await session.start()
    
    print("[3] Executing follow flow...")
    print("-" * 40)
    
    flow = FollowFlow(session, db)
    result = await flow.execute(target_user=target_id, target_is_id=True)
    
    print("-" * 40)
    print("\n[4] Result:")
    print(f"    Success: {result.success}")
    print(f"    Account: {result.account_used}")
    print(f"    Already Following: {result.already_following}")
    if result.verification:
        print(f"    Verification: {result.verification.method} ({result.verification.confidence:.2f})")
    if result.error:
        print(f"    Error: {result.error}")
    print(f"    Duration: {result.duration_seconds:.1f}s")
    
    await session.stop()
    db.close()
    
    print("\n" + "="*60)
    return result


async def main():
    """Run all tests or specific test."""
    import sys
    
    if len(sys.argv) > 1:
        test_name = sys.argv[1]
        if test_name == "account":
            await test_account_flow()
        elif test_name == "follow":
            await test_follow_flow()
        elif test_name == "sm":
            await test_state_machine()
        elif test_name == "identity":
            await test_identity_generator()
        elif test_name == "page":
            await test_page_detector()
        else:
            print(f"Unknown test: {test_name}")
            print("Available: account, follow, sm, identity, page")
    else:
        # Run quick tests
        await test_state_machine()
        await test_identity_generator()
        
        print("\nAvailable browser tests:")
        print("  python test_system.py account  - Create account")
        print("  python test_system.py follow   - Follow a user")


if __name__ == "__main__":
    asyncio.run(main())
