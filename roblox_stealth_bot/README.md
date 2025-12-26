# Roblox Automation System

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Playwright](https://img.shields.io/badge/playwright-latest-green.svg)](https://playwright.dev/)

An intelligent, state-machine based automation system for Roblox account management.

## Features

- 🤖 **Smart Account Creation** - Human-like form filling with real typing delays
- 🎯 **State Machine Architecture** - Robust, event-driven flow control
- 🔍 **Heuristic Page Detection** - Understands page state with confidence scoring
- 🛡️ **Stealth Layer** - Browser fingerprint spoofing
- 📊 **Rich CLI** - Beautiful command-line interface
- ⚡ **Self-Improving Rules** - Adapts delays based on success rates

## Quick Start

```powershell
# 1. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 2. Initialize database
python cli.py init

# 3. Create an account (visible browser)
python cli.py --no-headless create -n 1

# 4. Check accounts
python cli.py accounts
```

## CLI Commands

```powershell
python cli.py --help              # Show all commands
python cli.py status              # System status
python cli.py accounts            # List accounts
python cli.py create -n 5         # Create 5 accounts
python cli.py follow 123456       # Follow user by ID
python cli.py auto TARGET -a 5    # Auto: create + follow
```

## Project Structure

```
roblox_stealth_bot/
├── core/               # Core engine
├── generators/         # Data generation
├── flows/              # Business logic
├── control/            # Command center
├── data/               # Database
├── config/             # Configuration
└── cli.py              # CLI interface
```

## Configuration

Edit `config/config.yaml` for:
- Rate limits
- Delays between actions
- CAPTCHA settings
- Proxy configuration

## Requirements

- Python 3.8+
- Windows/macOS/Linux
- Chromium browser (installed via Playwright)

## ⚠️ Disclaimer

This project is for educational purposes only. Use responsibly and in compliance with Roblox Terms of Service. The authors are not responsible for any misuse.

## License

MIT
