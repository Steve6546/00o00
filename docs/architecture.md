# 🏗️ Architecture Overview

## System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLI Interface                           │
│                         (cli.py)                                │
└─────────────────────────────┬───────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│                         Commander                                │
│                    (src/control/commander.py)                   │
│  • Orchestrates all operations                                  │
│  • Manages browser sessions                                     │
│  • Handles rate limiting                                        │
└─────────────────────────────┬───────────────────────────────────┘
                              │
          ┌───────────────────┴───────────────────┐
          │                                       │
┌─────────▼─────────┐               ┌─────────────▼─────────────┐
│   Account Flow    │               │      Follow Flow          │
│ (src/flows/       │               │ (src/flows/follow_flow.py)│
│  account_flow.py) │               │                           │
└─────────┬─────────┘               └─────────────┬─────────────┘
          │                                       │
          │         ┌─────────────────────┐       │
          └────────▶│   State Machine     │◀──────┘
                    │ (src/core/          │
                    │  state_machine.py)  │
                    └─────────────────────┘
```

---

## Core Components

### 1. State Machine (`src/core/state_machine.py`)
Central control mechanism for all flows.

```python
States:
├── idle
├── verifying
│   ├── login
│   └── captcha
├── following
│   ├── searching
│   ├── navigating
│   └── action
└── complete
    ├── success
    └── failed
```

### 2. Page Detector (`src/core/page_detector.py`)
Identifies current page type using URL patterns and DOM elements.

```python
Page Types:
- home
- login
- signup
- profile
- captcha
- unknown
```

### 3. Flows (`src/flows/`)

| Flow | Purpose |
|------|---------|
| `account_flow.py` | Creates new Roblox accounts |
| `follow_flow.py` | Follows target users |
| `login_flow.py` | Handles authentication |

### 4. Services (`src/services/`)

| Service | Purpose |
|---------|---------|
| `health_checker.py` | Checks account ban status |
| `anti_detection.py` | Human-like delays, rate limiting |

---

## Data Flow

### Follow Action Flow

```
1. Load Account Session
         │
         ▼
2. Navigate to Profile (roblox.com/users/{id}/profile)
         │
         ▼
3. Detect Page Type (wait for profile)
         │
         ▼
4. Find Menu Button (#user-profile-header-contextual-menu-button)
         │
         ▼
5. Click Menu → Wait for Popover
         │
         ▼
6. Find Follow Button (button.foundation-web-menu-item)
         │
         ▼
7. Click Follow → Wait 2s
         │
         ▼
8. Reload Page → Reopen Menu
         │
         ▼
9. Verify: Unfollow button exists = SUCCESS
```

---

## Database Schema

```sql
-- Account table
CREATE TABLE account (
    id INTEGER PRIMARY KEY,
    username VARCHAR UNIQUE,
    password VARCHAR,
    birthday DATE,
    gender VARCHAR,
    status VARCHAR DEFAULT 'active',
    is_banned BOOLEAN DEFAULT FALSE,
    follow_count INTEGER DEFAULT 0,
    created_at DATETIME
);

-- Follow records
CREATE TABLE followrecord (
    id INTEGER PRIMARY KEY,
    account_id INTEGER REFERENCES account(id),
    target_id VARCHAR,
    target_username VARCHAR,
    followed_at DATETIME,
    verified BOOLEAN
);
```

---

## Configuration

Main config: `config/config.yaml`

```yaml
system:
  headless: false
  slow_mo: 100

rate_limits:
  actions_per_hour: 30
  follows_per_day: 50
```

---

## Logging System

```
logs/bot.log
├── INFO: Normal operations
├── WARNING: Potential issues
└── ERROR: Failures with explanations
```

Format:
```
2024-12-26 18:30:00 | INFO     | FollowFlow           | ✔️ Menu button found
2024-12-26 18:30:01 | ERROR    | FollowFlow           | ❌ Follow failed - Button not found
```
