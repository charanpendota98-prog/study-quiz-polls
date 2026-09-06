#!/usr/bin/env python3
"""
STUDENTUP — MASTER WATCH SERVICE (systemd: studentup.service)
24/7 IST-aware scheduler. Single Python process, stdlib only.

Schedule (IST):
  06:00  filler top-up
  07:00  morning greeting
  07:30 / 10:30 / 13:30 / 16:30 / 19:30  quiz slots (10 polls x 7 channels)
  14:30  study tip
  21:30  CA digest
  every :00 / :30   jobs update (private channel)
  10/5/1 min before each quiz slot  reminders

Modes:
  python3 watch.py            # run forever (production)
  python3 watch.py --once     # evaluate the current minute once and exit (test)
  python3 watch.py --sim HH:MM  # run as if time were HH:MM IST (test)
  STUDENTUP_DRY=1 python3 watch.py --once   # dry run
"""
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))
from core import config
from core.engine import Engine
from core.feeds import aggregate

LOG = config.LOGS / "watch.log"

# Quiz slot minutes for reminder lookups (2 daily rounds)
QUIZ_SLOTS = config.QUIZ_SLOT_TIMES


def log(msg):
    line = f"[{datetime.now(config.IST).strftime('%Y-%m-%d %H:%M:%S')} IST] {msg}"
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def current_hhmm(now):
    return now.strftime("%H:%M")


def due_reminders(hhmm):
    """Return reminder lead-minutes if hhmm is 10/5/1 min before a quiz slot."""
    h, m = map(int, hhmm.split(":"))
    now_min = h * 60 + m
    for slot in QUIZ_SLOTS:
        sh, sm = map(int, slot.split(":"))
        slot_min = sh * 60 + sm
        diff = slot_min - now_min
        if diff in config.REMINDER_BEFORE_MIN:
            return diff
    return None


def tick(eng, now, dry=False):
    """Evaluate the schedule for one minute. Returns a description of what ran."""
    hhmm = current_hhmm(now)
    ran = []

    # Feeds refreshed a few minutes before digest/jobs so content is fresh.
    if hhmm in ("05:55", "12:25", "21:20"):
        log("Refreshing RSS feeds…")
        try:
            aggregate(dry=dry)
        except Exception as e:
            log(f"feed refresh note: {e}")

    if hhmm in config.SCHEDULE:
        task, meta = config.SCHEDULE[hhmm]
        if task == "filler":
            try:
                from core.generator import top_up
                added, errs = top_up()
                log(f"filler: +{len(added)} questions ({len(errs)} rejected)")
                ran.append("filler")
            except Exception as e:
                log(f"filler error: {e}")
        elif task == "morning":
            eng.morning(); ran.append("morning")
        elif task == "quiz":
            eng.run_quiz_slot(round_label=meta.get("round", ""))
            ran.append(f"quiz{meta.get('slot','')}")
        elif task == "tip":
            eng.tip(); ran.append("tip")
        elif task == "coach":
            eng.coach_broadcast(); ran.append("coach")
        elif task == "digest":
            eng.digest(); ran.append("digest")
        elif task == "leaderboard":
            if meta.get("when") == "sunday" and now.weekday() == 6:
                eng.weekly_leaderboard(); ran.append("leaderboard")
            elif meta.get("when") != "sunday":
                eng.weekly_leaderboard(); ran.append("leaderboard")

    rem = due_reminders(hhmm)
    if rem is not None:
        eng.reminder(rem); ran.append(f"reminder-{rem}")

    # Jobs every 30 minutes (skip minutes that already fire a quiz/digest)
    _busy = ("07:30", "10:30", "13:30", "16:30", "19:30", "21:30")
    if now.minute % config.JOBS_INTERVAL_MIN == 0 and hhmm not in _busy:
        eng.jobs(); ran.append("jobs")

    return ran


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--sim", help="Simulate HH:MM IST (e.g. 07:30)")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    dry = args.dry or config.DRY
    log("STUDENTUP WATCH START — 24/7 IST scheduler "
        f"(dry={dry}) version={getattr(config, '__version__', '3.0')}")
    eng = Engine(dry=dry)
    log(f"Bank: {eng.bank.stats()}")

    if args.sim:
        h, m = map(int, args.sim.split(":"))
        now = datetime.now(config.IST).replace(hour=h, minute=m, second=0)
        ran = tick(eng, now, dry=dry)
        log(f"SIM {args.sim} -> ran: {ran or 'nothing (idle minute)'}")
        return

    if args.once:
        ran = tick(eng, datetime.now(config.IST), dry=dry)
        log(f"ONCE -> ran: {ran or 'nothing (idle minute)'}")
        return

    # Production loop — wake every 20s, fire each scheduled minute once.
    last_fired = set()
    while True:
        try:
            now = datetime.now(config.IST)
            key = now.strftime("%Y-%m-%d %H:%M")
            hhmm = current_hhmm(now)
            # fire at the top of the minute
            if now.second < 20 and key not in last_fired:
                ran = tick(eng, now, dry=dry)
                if ran:
                    log(f"tick {hhmm} -> {ran}")
                last_fired.add(key)
                # keep set small
                if len(last_fired) > 200:
                    last_fired = set(sorted(last_fired)[-100:])
            time.sleep(20)
        except KeyboardInterrupt:
            log("WATCH stopped by user")
            break
        except Exception as e:
            log(f"WATCH loop error (continuing): {e}")
            time.sleep(30)


if __name__ == "__main__":
    main()
