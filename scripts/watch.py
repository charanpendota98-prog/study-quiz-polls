#!/usr/bin/env python3
"""
STUDENTUP — MASTER WATCH SERVICE (systemd: studentup.service)
24/7 IST-aware scheduler. Single Python process, stdlib only.

Schedule (IST):
  04:45  deep source audit (content-gated; auto-pause/enable sources)
  05:30 / 07:45 / 08:15 / 11:00 / 16:00 / 19:45 / 20:15 / 22:30  collector
  06:00  filler top-up
  07:00  morning greeting
  07:30 / 19:30  quiz slots (10 polls x 7 channels)
  08:00 / 20:00  delayed answer key (no-op if ANSWER_MODE=instant)
  14:30  study tip
  21:30  CA digest
  every :00 / :30   jobs update (private channel)
  5/1 min before each quiz slot    reminders (T-5 preview, T-1 start)

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


def due_reminders(hhmm, weekday=None):
    """Return reminder lead-minutes if hhmm is 5 or 1 min before a quiz slot
    (Sunday: the Grand Test time counts as a slot too)."""
    h, m = map(int, hhmm.split(":"))
    now_min = h * 60 + m
    slots = list(QUIZ_SLOTS)
    if weekday == 6:
        slots.append(config.GRAND_TEST_TIME)
    for slot in slots:
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
        if task == "collect":
            try:
                from core.collector import collect_daily, retry_pending, ingest_inbox
                st = collect_daily()
                pdf = ingest_inbox()
                log(f"collect: +{st['accepted']} scraped, "
                    f"{st['parsed']} parsed, {st['duplicates']} dup, "
                    f"{st['parked']} parked, +{pdf.get('accepted', 0)} from PDFs")
                if st["parked"] or True:
                    try:
                        retry_pending()  # translate parked when a key exists
                    except Exception as e:
                        log(f"collect retry note: {e}")
                ran.append("collect")
            except Exception as e:
                log(f"collect error: {e}")
        elif task == "backfill":
            # Nightly 3-month archive campaign: walks live sources 5x deeper
            # and ingests harvested previous-paper PDFs; idles once complete.
            try:
                from core.collector import backfill
                bs = backfill()
                log(f"backfill: run {bs.get('runs')} +{bs.get('last_stats')} "
                    f"total={bs.get('accepted')} done={bs.get('done')}")
                ran.append("backfill")
            except Exception as e:
                log(f"backfill error: {e}")
        elif task == "verify":
            eng.verify_questions(limit=int(meta.get("limit", 120))); ran.append("verify")
        elif task == "telegram":
            try:
                from core.resilience import collect_telegram, solve_pending
                ts = collect_telegram()
                sv = solve_pending()
                log(f"telegram: ch={ts.get('channels')} keyed={ts.get('keyed')} "
                    f"polls={ts.get('parked_polls')} accepted={ts.get('accepted')} "
                    f"solved={sv.get('solved')}")
                ran.append("telegram")
            except Exception as e:
                log(f"telegram error: {e}")
        elif task == "supply":
            try:
                from core.resilience import supply_guard
                rep = supply_guard(notify=getattr(eng.tg, "admin_notify", None))
                log(f"supply: low={rep.get('low_before')} after={rep.get('low_after')} "
                    f"steps={len(rep.get('did', []))}")
                ran.append("supply")
            except Exception as e:
                log(f"supply error: {e}")
        elif task == "scout":
            # Continuous deep source discovery: crawls exam hubs, probes PDFs,
            # appends verified papers to pyq_papers.json. Time-boxed + capped.
            try:
                from core.scout import run as scout_run
                ss = scout_run()
                log(f"scout: pages={ss.get('pages')} new={ss.get('new')} "
                    f"promoted={ss.get('promoted')} rejected={ss.get('rejected')} "
                    f"inbox_deleted={ss.get('inbox_deleted')} {ss.get('seconds')}s")
                ran.append("scout")
            except Exception as e:
                log(f"scout error: {e}")
        elif task == "pyq":
            eng.harvest_pyq(); ran.append("pyq")
        elif task == "audit":
            # Daily deep, content-gated source audit: dead sources auto-pause,
            # verified-clean candidates auto-enable. Never crashes the loop.
            try:
                from core.auditor import audit_all
                res = audit_all()
                log(f"audit: checked={res['checked']} live={res['live']} "
                    f"warn={res.get('warn', 0)} dead={res['dead']} "
                    f"changes={res['enabled_changed']}")
                ran.append("audit")
            except Exception as e:
                log(f"audit error: {e}")
        elif task == "filler":
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
        elif task == "answer_key":
            try:
                eng.post_answer_key(round_label=meta.get("round", ""))
                ran.append("answer_key")
            except Exception as e:
                log(f"answer_key error: {e}")

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

    # People-features (bot DMs + CURRENT hub only)
    if hhmm == "20:30":
        eng.streak_nudge(); ran.append("streak-nudge")
    if hhmm == "21:40":
        eng.daily_champions(); ran.append("champions")
    import calendar
    if hhmm == "21:00" and now.day == calendar.monthrange(now.year, now.month)[1]:
        eng.hall_of_fame(); ran.append("hall-of-fame")
    if hhmm == "20:00" and now.weekday() == 6:
        eng.district_cup(); ran.append("district-cup")
    if now.weekday() == 0 and hhmm == config.LEAGUE_POST_TIME:
        try:
            eng.district_league(); ran.append("district-league")
        except Exception as e:
            log(f"league error: {e}")
    # 🏟 Sunday Grand Test: Saturday teaser + Sunday morning mock (T-5/T-1 alerts too)
    if now.weekday() == 5 and hhmm == config.GRAND_TEST_TEASER_TIME:
        try:
            eng.grand_test_teaser(); ran.append("grand-teaser")
        except Exception as e:
            log(f"grand-teaser error: {e}")
    if now.weekday() == 6 and hhmm == config.GRAND_TEST_TIME:
        try:
            eng.run_grand_test(); ran.append("grand-test")
        except Exception as e:
            log(f"grand-test error: {e}")

    rem = due_reminders(hhmm, now.weekday())
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
