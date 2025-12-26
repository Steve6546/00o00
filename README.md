# 🤖 Roblox Stealth Bot

A sophisticated Python-based automation platform for Roblox account creation and user following, designed with stealth and sustainability in mind.

## 📋 Table of Contents
- [Overview](#overview)
- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Interactive Shell](#-interactive-shell)
- [Configuration](#configuration)
- [Architecture](#architecture)
- [Warnings & Limits](#warnings--limits)
- [Troubleshooting](#troubleshooting)

---

## 🎯 Overview

This bot automates two primary tasks:
1. **Account Creation** - Creates Roblox accounts with unique identities
2. **User Following** - Follows target users from created accounts

### How It Works (High-Level Flow)

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Start Session  │────▶│  Login/Create   │────▶│  Navigate to    │
│  (Load Cookies) │     │  Account        │     │  Target Profile │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
┌─────────────────┐     ┌─────────────────┐              │
│  Verify Follow  │◀────│  Click Follow   │◀─────────────┘
│  (Reload Check) │     │  Button         │
└─────────────────┘     └─────────────────┘
```

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🎭 **Stealth Mode** | Human-like delays, random actions, fingerprint rotation |
| 👤 **Identity Generator** | Creates unique usernames, passwords, birthdays with gender support |
| 📊 **Account Dashboard** | CLI to view all accounts, follow counts, status |
| 🖥️ **Interactive Shell** | Advanced command shell with nested commands |
| 🔍 **Health Checker** | Detects banned accounts automatically |
| ⏱️ **Rate Limiting** | Protects from detection with action limits |
| 📝 **Checkpoint Logging** | Clear ✔️/❌ status for every step |

---

## 📦 Requirements

- **Python** 3.10+
- **Playwright** browser automation
- **Windows/Linux/macOS**

### Dependencies
```
playwright>=1.40.0
peewee>=3.17.0
pyyaml>=6.0
rich>=13.0
click>=8.0
```

---

## 🚀 Installation

### 1. Clone Repository
```bash
git clone <repository-url>
cd 00o00
```

### 2. Create Virtual Environment
```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/macOS
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
playwright install chromium
```

### 4. Initialize Database
```bash
python -c "from data.database import db; db.connect(); print('Database ready!')"
```

---

## 💻 Usage

### Create Accounts
```bash
# Create 1 account
python cli.py create

# Create 5 accounts
python cli.py create --count 5

# Create with visible browser
python cli.py --no-headless create
```

### Follow Users
```bash
# Follow by user ID
python cli.py follow 5816318414

# Follow with visible browser
python cli.py --no-headless follow 5816318414
```

### Account Management
```bash
# List all accounts
python cli.py accounts list

# View specific account details
python cli.py accounts info <username>

# Check health of all accounts
python cli.py accounts health-check
```

### Check System Status
```bash
python cli.py status
```

---

## 🖥️ Interactive Shell

### Start the Interactive Shell
```bash
python cli.py shell
```

### Shell Commands

The interactive shell provides a powerful command interface with nested contexts:

```
bot> accounts          # Enter accounts context
bot/accounts> list     # List all accounts
bot/accounts> info player001  # Account details
bot/accounts> health   # Health check
bot/accounts> back     # Return to main

bot> system           # Enter system context
bot/system> status    # Full system status
bot/system> tasks     # Recent tasks
bot/system> errors    # Recent errors

bot> proxies          # Enter proxy context
bot/proxies> list     # List proxies
```

### Shell Features

| Feature | Description |
|---------|-------------|
| **Nested Contexts** | Navigate: accounts → list → info → back |
| **Auto-complete** | Press Tab for suggestions |
| **Command History** | Use ↑↓ arrows |
| **Aliases** | `ls`=list, `q`=exit, `h`=help, `b`=back |
| **Account Inspection** | View follower counts, health status |

---

## ⚙️ Configuration

Configuration file: `config/config.yaml`

```yaml
system:
  headless: false          # Browser visibility
  slow_mo: 100            # Delay between actions (ms)
  auto_health_check: true # Check accounts on startup

rate_limits:
  actions_per_hour: 30    # Max actions per hour
  follows_per_day: 50     # Max follows per day
  cooldown_on_fail: 300   # Cooldown after failure (seconds)

behavior:
  min_delay_ms: 1000      # Minimum delay between actions
  max_delay_ms: 5000      # Maximum delay between actions
  random_breaks: true     # Occasional longer breaks
```

---

## 🏗️ Architecture

```
00o00/
├── cli.py              # Command-line interface
├── shell.py            # Interactive shell (NEW)
├── main.py             # Entry point
├── requirements.txt    # Dependencies
│
├── src/                # Source code
│   ├── core/           # State machine, page detection
│   ├── flows/          # Account creation, follow flows
│   ├── services/       # Health checker, anti-detection
│   ├── generators/     # Identity generation
│   ├── behavior/       # Human-like behavior
│   ├── control/        # Commander, Inspector, session
│   ├── modules/        # Additional modules
│   └── utils/          # Logging utilities
│
├── config/             # Configuration files
├── data/               # Database
├── docs/               # Documentation
├── logs/               # Log files
├── scripts/            # Helper scripts
├── sessions/           # Browser sessions
└── tests/              # Test files
```

---

## ⚠️ Warnings & Limits

### Detection Risks
| Risk | Mitigation |
|------|------------|
| Too many follows | Rate limiting (50/day max) |
| Same IP | Proxy rotation support |
| Bot-like timing | Random human delays |
| Fingerprinting | Browser context isolation |

### Account Safety
- ⚠️ Accounts may be banned if used aggressively
- ⚠️ Use at your own risk
- ⚠️ Roblox ToS prohibits botting

### Recommended Limits
- **Follows per account**: 10-20 per day
- **Actions per hour**: 20-30 max
- **Cooldown between accounts**: 5+ minutes

---

## 🔧 Troubleshooting

See [docs/troubleshooting.md](docs/troubleshooting.md) for detailed solutions.

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| "Menu button not found" | DOM changed | Update selectors |
| "Follow NOT verified" | Click didn't register | Increase wait time |
| "Account banned" | Too many actions | Use rate limiting |
| Import errors | Wrong directory | Run from project root |

---

## 📝 License

This project is for educational purposes only.

---

## 🤝 Contributing

1. Fork the repository
2. Create feature branch
3. Submit pull request

---

**⚠️ Disclaimer**: This tool is for educational purposes. Use responsibly and at your own risk.
