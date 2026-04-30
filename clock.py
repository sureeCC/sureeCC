"""
Qandle Auto Clock-In / Clock-Out
Weekdays: Clock In at 11:00 AM IST, Clock Out at 11:00 PM IST
"""

import os
import time
import logging
from datetime import date, datetime
import pytz
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

load_dotenv()

IST = pytz.timezone("Asia/Kolkata")
QANDLE_URL = "https://igs.qandle.com/#/"
DRY_RUN = True  # Set to False to enable actual clock actions

HOLIDAYS = {
    date(2026,  1, 15): "Uttarayana Punyakala / Makara Sankranti",
    date(2026,  1, 26): "Republic Day",
    date(2026,  3, 19): "Ugadi",
    date(2026,  5,  1): "May Day",
    date(2026,  9, 14): "Varasiddhi Vinayaka Vrata",
    date(2026, 10,  2): "Gandhi Jayanthi",
    date(2026, 10, 20): "Mahanavami / Ayudha Pooja",
    date(2026, 10, 21): "Vijayadashami",
    date(2026, 11, 10): "Balipadyami / Deepavali",
    date(2026, 12, 25): "Christmas",
}
LOG_FILE = os.path.join(os.path.dirname(__file__), "clock.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


CLOCK_IN_BTN  = 'button[aria-label="Clock In"]:not([aria-hidden="true"]), button[aria-label="Clock In"].ng-scope:not(.ng-hide)'
CLOCK_OUT_BTN = 'button[aria-label="Clock Out"]:not([aria-hidden="true"]), button[aria-label="Clock Out"].ng-scope:not(.ng-hide)'


def get_clock_state(page) -> str:
    """
    Returns "in" if currently clocked in (Clock Out button visible),
    "out" if clocked out (Clock In button visible), or "unknown".
    Angular hides one button via ng-hide/display:none; check visibility directly.
    """
    try:
        visible_label = page.evaluate("""() => {
            const btns = document.querySelectorAll('button[aria-label="Clock In"], button[aria-label="Clock Out"]');
            for (const b of btns) {
                if (!b.classList.contains('ng-hide') && b.offsetParent !== null)
                    return b.getAttribute('aria-label');
            }
            return null;
        }""")
        if visible_label == "Clock Out":
            return "in"
        if visible_label == "Clock In":
            return "out"
    except Exception:
        pass
    return "unknown"


def do_clock_action(action: str) -> bool:
    """
    action: "in" or "out"
    Checks current state first — skips with a message if already in desired state.
    Returns True on success or already-in-state, False on error.
    """
    email = os.getenv("QANDLE_EMAIL")
    password = os.getenv("QANDLE_PASSWORD")
    if not email or not password:
        log.error("QANDLE_EMAIL or QANDLE_PASSWORD not set in .env")
        return False

    with sync_playwright() as p:
        headless = os.getenv("CI", "false").lower() == "true"
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(timezone_id="Asia/Kolkata")
        page = ctx.new_page()

        try:
            log.info("Navigating to %s", QANDLE_URL)
            page.goto(QANDLE_URL, wait_until="networkidle", timeout=30_000)

            # --- Click Active Directory SSO ---
            page.click('button:has-text("Sign In With Active Directory")')
            log.info("Clicked Active Directory sign-in")

            # --- Microsoft login: email step ---
            page.wait_for_selector('input[type="email"]', timeout=15_000)
            page.fill('input[type="email"]', email)
            page.click('input[type="submit"], button:has-text("Next")')
            log.info("Submitted email to Microsoft login")

            # --- Microsoft login: password step ---
            page.wait_for_selector('input[type="password"]', timeout=15_000)
            page.fill('input[type="password"]', password)
            page.click('input[type="submit"], button:has-text("Sign in")')
            log.info("Submitted password")

            # --- Stay signed in prompt (optional) ---
            try:
                page.wait_for_selector('input[value="Yes"], button:has-text("Yes")', timeout=6_000)
                page.click('input[value="Yes"], button:has-text("Yes")')
                log.info("Dismissed stay-signed-in prompt")
            except PWTimeout:
                pass

            # --- Wait for redirect back to Qandle dashboard ---
            page.wait_for_url("**igs.qandle.com**", timeout=40_000)
            page.wait_for_load_state("networkidle", timeout=30_000)

            # Wait for Angular to render clock buttons via JS (ng-hide uses display:none)
            page.wait_for_function(
                """() => {
                    const btns = document.querySelectorAll('button[aria-label="Clock In"], button[aria-label="Clock Out"]');
                    return Array.from(btns).some(b => !b.classList.contains('ng-hide') && b.offsetParent !== null);
                }""",
                timeout=20_000,
            )
            log.info("Logged in via Active Directory successfully")

            # --- Check current state and enforce direction ---
            current_state = get_clock_state(page)

            if current_state == action:
                log.info("Already clocked %s — no action taken.", action.upper())
                print(f"Already clocked {action.upper()}.")
                return True

            # Hard guard: 11 AM task must only clock IN, 11 PM task must only clock OUT
            opposite = "out" if action == "in" else "in"
            if current_state == opposite:
                # This is the expected state — correct direction, proceed
                pass
            elif current_state == "unknown":
                log.warning("Could not determine clock state — aborting to be safe.")
                return False

            # --- Click the correct button ---
            button_label = "Clock In" if action == "in" else "Clock Out"

            if DRY_RUN:
                log.info("[DRY RUN] Would click '%s' — no action taken.", button_label)
                print(f"[DRY RUN] Would click '{button_label}' — no action taken.")
                return True

            page.evaluate(f"""() => {{
                const btns = document.querySelectorAll('button[aria-label="{button_label}"]');
                for (const b of btns) {{
                    if (!b.classList.contains('ng-hide') && b.offsetParent !== null) {{
                        b.click(); return;
                    }}
                }}
            }}""")
            log.info("Clicked '%s' button", button_label)

            # Accept the clock-out confirmation dialog (shows summary + YES/NO)
            try:
                page.wait_for_function(
                    "() => Array.from(document.querySelectorAll('button')).some(b => b.innerText.trim() === 'YES' && b.offsetParent !== null)",
                    timeout=8_000,
                )
                page.evaluate(
                    "() => { const b = Array.from(document.querySelectorAll('button')).find(b => b.innerText.trim() === 'YES' && b.offsetParent !== null); if(b) b.click(); }"
                )
                log.info("Clicked YES on confirmation dialog")
                time.sleep(2)
            except PWTimeout:
                btns = page.evaluate("() => Array.from(document.querySelectorAll('button')).map(b => b.innerText.trim())")
                log.error("YES button not found. Visible buttons: %s", btns)
                page.screenshot(path=os.path.join(os.path.dirname(__file__), f"error_{action}_confirm.png"))
                return False

            time.sleep(2)
            log.info("Clock %s completed at %s", action.upper(), datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST"))
            return True

        except PWTimeout as e:
            page.screenshot(path=os.path.join(os.path.dirname(__file__), f"error_{action}.png"))
            log.error("Timeout during clock %s: %s (screenshot saved)", action, e)
            return False
        except Exception as e:
            page.screenshot(path=os.path.join(os.path.dirname(__file__), f"error_{action}.png"))
            log.error("Error during clock %s: %s (screenshot saved)", action, e)
            return False
        finally:
            browser.close()


def seconds_until(hour: int, minute: int = 0) -> float:
    """Seconds until the next occurrence of HH:MM IST (today or tomorrow)."""
    now = datetime.now(IST)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        from datetime import timedelta
        target += timedelta(days=1)
    return (target - now).total_seconds()


def is_weekday(dt: datetime) -> bool:
    return dt.weekday() < 5  # Monday=0, Friday=4


def run_scheduler():
    log.info("Qandle auto-clocker started. Waiting for next scheduled time...")

    while True:
        now = datetime.now(IST)
        h, m = now.hour, now.minute

        # Determine next action
        if is_weekday(now):
            if h < 11:
                wait = seconds_until(11, 0)
                log.info("Next: Clock IN  in %.0f min", wait / 60)
                time.sleep(wait)
                if is_weekday(datetime.now(IST)):
                    do_clock_action("in")
                continue

            if 11 <= h < 23:
                wait = seconds_until(23, 0)
                log.info("Next: Clock OUT in %.0f min", wait / 60)
                time.sleep(wait)
                if is_weekday(datetime.now(IST)):
                    do_clock_action("out")
                continue

        # Past 11 PM or weekend — sleep until 10:55 AM next weekday
        wait = seconds_until(10, 55)
        # If that lands on a weekend, we'll loop again and re-evaluate
        log.info("Sleeping %.0f min until 10:55 AM IST check...", wait / 60)
        time.sleep(wait)


SCHEDULED_HOURS = {"in": 11, "out": 23}
WINDOW_MINUTES = 30  # skip if fired more than this many minutes late


def within_window(action: str) -> bool:
    """Return True if current IST time is within WINDOW_MINUTES of the scheduled hour."""
    now = datetime.now(IST)
    today = now.date()

    if today in HOLIDAYS:
        log.info("Skipping clock %s — today is a holiday: %s.", action.upper(), HOLIDAYS[today])
        print(f"Holiday today ({HOLIDAYS[today]}) — no action taken.")
        return False

    scheduled_hour = SCHEDULED_HOURS[action]
    minutes_past = (now.hour - scheduled_hour) * 60 + now.minute
    if 0 <= minutes_past <= WINDOW_MINUTES:
        return True
    log.warning(
        "Skipping clock %s — fired %d min past scheduled time (max allowed: %d min).",
        action.upper(), minutes_past, WINDOW_MINUTES,
    )
    return False


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Test mode: bypasses time-window guard, always uses DRY_RUN
        log.info("[TEST] Running full dry-run flow (time window bypassed).")
        ok = do_clock_action("in")
        sys.exit(0 if ok else 1)
    elif len(sys.argv) > 1 and sys.argv[1] == "force" and len(sys.argv) > 2 and sys.argv[2] in ("in", "out"):
        # Force mode: bypasses time-window guard, runs real action
        log.info("[FORCE] Running clock %s (time window bypassed).", sys.argv[2].upper())
        ok = do_clock_action(sys.argv[2])
        sys.exit(0 if ok else 1)
    elif len(sys.argv) > 1 and sys.argv[1] in ("in", "out"):
        action = sys.argv[1]
        if not within_window(action):
            sys.exit(0)  # too late, silent skip
        ok = do_clock_action(action)
        sys.exit(0 if ok else 1)
    else:
        run_scheduler()
