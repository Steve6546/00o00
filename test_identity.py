"""Quick test for Smart Identity Generator"""

from src.generators.identity_generator import (
    IdentityGenerator, 
    RobloxUsernameValidator, 
    SmartUsernameGenerator,
    UsernameBlacklist,
    GenderType
)

print("=" * 50)
print("Testing Smart Identity Generator")
print("=" * 50)

# Test Validator
print("\n1. Testing Username Validator:")
v = RobloxUsernameValidator()

test_cases = [
    ("CoolPlayer123", True),
    ("AB", False),  # Too short
    ("_BadName", False),  # Starts with underscore
    ("BadName_", False),  # Ends with underscore
    ("12345", False),  # Only digits
    ("Good_Name123", True),
    ("A" * 25, False),  # Too long
]

for username, expected in test_cases:
    is_valid, msg = v.validate(username)
    status = "✓" if is_valid == expected else "✗"
    print(f"  {status} {username}: {is_valid} ({msg})")

# Test Generator
print("\n2. Testing Smart Username Generator:")
g = SmartUsernameGenerator()

print("  Generated usernames:")
for i in range(5):
    username = g.generate(gender=GenderType.RANDOM)
    print(f"    {i+1}. {username}")

print(f"\n  Stats: {g.get_stats()}")

# Test Full Identity Generator
print("\n3. Testing Full Identity Generator:")
gen = IdentityGenerator()

for i in range(3):
    identity = gen.generate(gender=GenderType.RANDOM)
    print(f"  Identity {i+1}:")
    print(f"    Username: {identity.username}")
    print(f"    Gender: {identity.gender}")
    print(f"    Birthday: {identity.birthday}")

print("\n" + "=" * 50)
print("All tests completed!")
print("=" * 50)
