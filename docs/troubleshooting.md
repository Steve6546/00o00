# 🔧 Troubleshooting Guide

## Common Issues and Solutions

---

## 1. Element Not Found Errors

### ❌ "Menu button not found"

**What happened:** The bot couldn't find the three-dots menu button on the profile page.

**Why it failed:**
- Roblox updated their DOM structure
- Page didn't fully load
- Wrong selector used

**Solutions:**
```python
# Current working selector (Dec 2024):
#user-profile-header-contextual-menu-button

# Verification:
1. Open profile page manually
2. Right-click menu button → Inspect
3. Check if ID matches
```

**Fix in code:**
```python
# src/flows/follow_flow.py
menu_btn = await page.wait_for_selector(
    '#user-profile-header-contextual-menu-button',
    state='visible',
    timeout=10000  # Increase timeout
)
```

---

### ❌ "Follow button not found in menu"

**What happened:** Menu opened but Follow button wasn't detected.

**Why it failed:**
- User already followed (shows "Unfollow")
- Menu animation not complete
- Selector outdated

**Solutions:**
```python
# Current working selector:
button.foundation-web-menu-item:has-text("Follow")

# Check for already following:
unfollow = await page.query_selector('button.foundation-web-menu-item:has-text("Unfollow")')
if unfollow:
    print("Already following!")
```

---

## 2. Verification Failures

### ❌ "Follow NOT verified - Unfollow not found"

**What happened:** Clicked Follow but verification failed.

**Why it failed:**
- Click didn't register (page still loading)
- Network delay
- Rate limited by Roblox

**Solutions:**
1. **Increase wait time:**
```python
await follow_btn.click()
await page.wait_for_timeout(3000)  # Wait 3 seconds
```

2. **Check network:**
```python
await page.reload(wait_until='networkidle')
```

3. **Use force click:**
```python
await follow_btn.click(force=True)
```

---

## 3. Login Issues

### ❌ "Cookie login failed"

**What happened:** Session cookies didn't work.

**Why it failed:**
- Cookies expired
- Account banned
- Different browser fingerprint

**Solutions:**
1. **Re-login manually:**
```bash
python cli.py --no-headless follow <target>
# Login manually when browser opens
```

2. **Clear old session:**
```python
# Delete sessions folder
rm -rf sessions/
```

3. **Check account status:**
```bash
python cli.py accounts health-check
```

---

## 4. Rate Limiting

### ❌ "Action cooldown active"

**What happened:** Too many actions in short time.

**Why it failed:**
- Exceeded hourly limit
- Previous action failed, triggered cooldown

**Solutions:**
1. **Wait for cooldown:**
```python
from src.services.anti_detection import rate_limiter
wait_time = rate_limiter.get_wait_time(account_id)
print(f"Wait {wait_time} seconds")
```

2. **Increase limits:**
```yaml
# config/config.yaml
rate_limits:
  actions_per_hour: 40  # Increase carefully
  cooldown_on_fail: 180  # Reduce cooldown
```

---

## 5. DOM/Page Changes

### ❌ Page structure changed

**Detection:** Selectors that used to work now fail.

**Solution Process:**
1. Open Roblox profile in browser
2. Open Developer Tools (F12)
3. Find the target element
4. Note the new selector
5. Update in code:

```python
# src/flows/follow_flow.py
# Old selector (broken):
# menu_btn = '#old-selector'

# New selector (updated):
menu_btn = '#new-selector'
```

---

## 6. Import Errors

### ❌ "ModuleNotFoundError"

**What happened:** Python can't find modules.

**Why it failed:**
- Running from wrong directory
- Virtual environment not activated

**Solutions:**
1. **Activate venv:**
```bash
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux
```

2. **Run from project root:**
```bash
cd c:\Users\...\00o00
python cli.py accounts list
```

3. **Add project to path:**
```python
import sys
sys.path.insert(0, '/path/to/00o00')
```

---

## 7. Database Issues

### ❌ "no such column"

**What happened:** Database schema outdated.

**Solution - Run migration:**
```bash
python -c "
from data.database import db
db.connect()
db.execute_sql('ALTER TABLE account ADD COLUMN is_banned INTEGER DEFAULT 0')
db.execute_sql('ALTER TABLE account ADD COLUMN last_health_check DATETIME NULL')
print('Migration complete!')
"
```

---

## 8. Browser Issues

### ❌ "Browser closed unexpectedly"

**Solutions:**
1. **Install/update Playwright:**
```bash
pip install --upgrade playwright
playwright install chromium
```

2. **Check headless mode:**
```bash
python cli.py --no-headless follow <target>
```

---

## Diagnostic Checklist

When something fails, check:

- [ ] Virtual environment activated?
- [ ] Running from project root?
- [ ] Browser installed? (`playwright install`)
- [ ] Account not banned? (`accounts health-check`)
- [ ] Rate limit clear? (check logs)
- [ ] Selectors up to date? (test manually)
- [ ] Network working? (check Roblox.com)

---

## Getting Help

1. **Check logs:** `logs/bot.log`
2. **Enable verbose:** `python cli.py -v`
3. **Run visible:** `python cli.py --no-headless`
4. **Take screenshot:** Add debug screenshots in code
