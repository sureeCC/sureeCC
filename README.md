# Qandle Auto Clock-In / Clock-Out

## What it does
Automates daily attendance on [https://igs.qandle.com](https://igs.qandle.com) for **S Suresh (IGS0759)**.
- Clocks **IN** at **11:00 AM IST** on weekdays
- Clocks **OUT** at **11:00 PM IST** on weekdays
- Skips public holidays automatically
- Wakes laptop from sleep to run, screen stays black — fully silent

---

## File Structure
```
D:\local\qandle_clocker\
  clock.py               ← main script
  .env                   ← credentials (never commit this)
  requirements.txt       ← Python dependencies
  task_clock_in.xml      ← Task Scheduler XML for 11 AM
  task_clock_out.xml     ← Task Scheduler XML for 11 PM
  task_dryrun_test.xml   ← one-time test task (reusable)
  setup_tasks.bat        ← registers 11 AM + 11 PM tasks
  clock.log              ← runtime log (check this for activity)
  error_in.png           ← screenshot saved on clock-in error
  error_out.png          ← screenshot saved on clock-out error
```

---

## Credentials
Stored in `.env` (not committed to git):
```
QANDLE_EMAIL=suresh.selvam@igsglobal.com
QANDLE_PASSWORD=<AD password>
```
Login method: **Sign In With Active Directory** (Microsoft SSO) — NOT the email/password form.

---

## Python Environment
```
Interpreter : C:\Users\Suresh\.virtualenvs\bff-service-0G38rcZ1\Scripts\python.exe
Python      : 3.12.1
Browser     : Playwright Chromium (headless)
```

Install dependencies (run once):
```bash
pip install -r requirements.txt
playwright install chromium
```

---

## How the Script Works (`clock.py`)

### Key constants
| Constant | Value | Purpose |
|---|---|---|
| `DRY_RUN` | `False` (live) | Set `True` to test without touching portal |
| `WINDOW_MINUTES` | `15` | Skip if task fires more than 15 min late |
| `SCHEDULED_HOURS` | `{"in": 11, "out": 23}` | Expected fire times |

### Flow for each run
1. Check if today is a **holiday** → skip if yes
2. Check if fired within **15-minute window** of scheduled time → skip if late
3. Open headless Chromium, navigate to Qandle
4. Click **Sign In With Active Directory**
5. Fill Microsoft login (email → Next → password → Sign In)
6. Dismiss "Stay signed in?" prompt if shown
7. Detect current clock state via JavaScript (checks `ng-hide` class)
8. **Enforce direction**: `clock.py in` will NEVER clock out; `clock.py out` will NEVER clock in
9. If already in correct state → log "Already clocked IN/OUT" and exit
10. If state unknown → abort safely
11. Click the correct button via JavaScript
12. Log result to `clock.log`

### CLI usage
```bash
python clock.py in      # clock in (respects time window + holidays)
python clock.py out     # clock out (respects time window + holidays)
python clock.py test    # full dry-run, bypasses time window (for testing)
```

---

## Windows Task Scheduler

### Registered tasks
| Task Name | Schedule | Action |
|---|---|---|
| Qandle Clock In | Mon–Fri 11:00 AM | `clock.py in` |
| Qandle Clock Out | Mon–Fri 11:00 PM | `clock.py out` |

### Key settings (in XML)
- `WakeToRun = true` — wakes laptop from sleep
- `StartWhenAvailable = false` — does NOT run if laptop was off (missed = skipped)
- `DisallowStartIfOnBatteries = false` — runs on battery too
- `RunOnlyIfNetworkAvailable = true` — skips if no internet

### Re-register tasks (run as Administrator)
```
D:\local\qandle_clocker\setup_tasks.bat
```

### Check task status
```powershell
schtasks /query /tn "Qandle Clock In"  /fo LIST
schtasks /query /tn "Qandle Clock Out" /fo LIST
```

### Delete tasks
```powershell
schtasks /delete /tn "Qandle Clock In"  /f
schtasks /delete /tn "Qandle Clock Out" /f
```

---

## Sleep / Shutdown Behaviour
Laptop is configured to **never sleep** (display turns off only). Task runs exactly at 11 AM and 11 PM.

> Note: This machine uses S0 Modern Standby — WakeToRun does not work. Hibernate wake also not supported. Never-sleep is the reliable solution.

| Scenario | What happens |
|---|---|
| Laptop **on** at 11 AM/11 PM | Runs exactly on time |
| Laptop **off**, turned on later | Task was missed — nothing happens (by design) |
| Task fires 30+ min late | Script detects it, logs warning, exits without action |

---

## Holiday List (2026)
| Date | Holiday |
|---|---|
| 15-Jan-2026 | Uttarayana Punyakala / Makara Sankranti |
| 26-Jan-2026 | Republic Day |
| 19-Mar-2026 | Ugadi |
| 01-May-2026 | May Day |
| 14-Sep-2026 | Varasiddhi Vinayaka Vrata |
| 02-Oct-2026 | Gandhi Jayanthi |
| 20-Oct-2026 | Mahanavami / Ayudha Pooja |
| 21-Oct-2026 | Vijayadashami |
| 10-Nov-2026 | Balipadyami / Deepavali |
| 25-Dec-2026 | Christmas |

To add/remove holidays, edit the `HOLIDAYS` dict in `clock.py`.

---

## Testing (Wake-from-Sleep Dry Run)
1. Set `DRY_RUN = True` in `clock.py`
2. Update `task_dryrun_test.xml` with a time 5 minutes from now
3. Register it: `schtasks /create /tn "Qandle DryRun Test" /xml "D:\local\qandle_clocker\task_dryrun_test.xml" /f`
4. Sleep the laptop
5. After wake, check: `tail -20 d:/local/qandle_clocker/clock.log`
6. Expected log ending: `[TEST] Running full dry-run flow` → `Already clocked IN — no action taken.`

---

## Troubleshooting

### Check the log
```bash
tail -30 d:/local/qandle_clocker/clock.log
```

### Error screenshot saved
If the script errors, it saves a screenshot to `error_in.png` or `error_out.png` — open it to see what the browser saw.

### Common issues
| Symptom | Likely cause | Fix |
|---|---|---|
| `Wrong username/password` | AD password changed | Update `QANDLE_PASSWORD` in `.env` |
| `Timeout` on clock button | Page loaded differently | Check `error_*.png` screenshot |
| `Already clocked IN/OUT` | Already actioned manually | Normal — no action needed |
| `State unknown — aborting` | Page didn't load correctly | Check internet, re-run manually |
| Task not running at all | Task Scheduler needs re-registration | Run `setup_tasks.bat` as Administrator |
