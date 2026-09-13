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
    if hhmm == "20:15" and now.weekday() == 6:
        try:
            eng.exam_boards("week"); ran.append("exam-week")
        except Exception as e:
            log(f"examboard error: {e}")
    if hhmm == "21:30":
        try:
            eng.exam_boards("today"); ran.append("exam-today")
        except Exception as e:
            log(f"examboard error: {e}")
    if now.weekday() == 0 and hhmm == config.LEAGUE_POST_TIME:
        try:
            eng.district_league(); ran.append("district-league")
            eng.referral_board(); ran.append("referral-board")
        except Exception as e:
            log(f"league error: {e}")
    # ⚔️ District War: T-5 / T-1 alerts, start, publish result (~20 min later), Sunday season table
    try:
        wh, wm = map(int, config.WAR_TIME.split(":"))
        wmin = wh * 60 + wm
        nmin = now.hour * 60 + now.minute
        if wmin - nmin == 5:
            eng.war_alert(5); ran.append("war-alert-5")
        elif wmin - nmin == 1:
            eng.war_alert(1); ran.append("war-alert-1")
        elif nmin == wmin:
            eng.war_start(); ran.append("war-start")
        elif nmin - wmin in (18, 25, 35):
            if eng.war_publish():
                ran.append("war-result")
        if now.weekday() == 6 and hhmm == "21:45":
            eng.war_season(); ran.append("war-season")
    except Exception as e:
        log(f"war error: {e}")
    if hhmm == "00:10":
        try:
            eng.streak_shield_job(); ran.append("streak-shield")
        except Exception as e:
            log(f"shield error: {e}")
    if now.weekday() == 0 and hhmm == "08:05":
        try:
            eng.squad_board(); ran.append("squad-board")
            eng.arena_board(); ran.append("arena-board")
        except Exception as e:
            log(f"squad error: {e}")
    from core import partners as _pa
    if hhmm in _pa.AD_SLOTS:
        try:
            eng.partner_ad(); ran.append("partner-ad")
        except Exception as e:
            log(f"ad error: {e}")
    # ---- scheduled campaigns (/msg)
    try:
        if eng.campaigns_due():
            ran.append("campaign")
    except Exception as e:
        log(f"campaign error: {e}")
    # ---- autopilot
    if now.minute in (5, 35):
        try:
            done = eng.autopilot("heal")
            if done:
                ran.append("heal")
        except Exception as e:
            log(f"autopilot heal error: {e}")
    for t, what in (("07:30", "coach"), ("12:00", "countdown"), ("18:00", "winback"), ("22:40", "coach_streaks"), ("22:45", "night")):
        if hhmm == t:
            try:
                eng.autopilot(what); ran.append("ap-" + what)
            except Exception as e:
                log(f"autopilot {what} error: {e}")
    if hhmm == "20:05":
        try:
            log(f"gate chase: {eng.gate_chase()} DMs"); ran.append("gate-chase")
        except Exception as e:
            log(f"gate chase error: {e}")
    for t, what in (("09:00", "remind"), ("19:00", "digest")):
        if hhmm == t:
            try:
                n = eng.jobradar(what); ran.append(f"jobradar-{what}"); log(f"job radar {what}: {n} DMs")
            except Exception as e:
                log(f"job radar {what} error: {e}")
    if hhmm == "23:30":
        try:
            log(f"sheet nightly: {eng.sheet_nightly()}"); ran.append("sheet-nightly")
        except Exception as e:
            log(f"sheet nightly error: {e}")
    if hhmm == "20:30" and now.weekday() == 6:
        try:
            log(f"report cards: {eng.report_cards()}"); ran.append("report-cards")
        except Exception as e:
            log(f"report cards error: {e}")
    if hhmm == "09:00" and now.weekday() == 0:
        try:
            eng.college_toppers(); ran.append("college-toppers")
        except Exception as e:
            log(f"college toppers error: {e}")
    if hhmm == "08:00":
        try:
            eng.morning_brief(); ran.append("hq-brief")
        except Exception as e:
            log(f"hq error: {e}")
    if hhmm == "11:00" and now.weekday() == 2:
        try:
            eng.join_nudge(); ran.append("join-nudge")
        except Exception as e:
            log(f"join nudge error: {e}")
    if hhmm == "10:00":
        try:
            eng.campus_drip(); ran.append("campus-drip")
        except Exception as e:
            log(f"campus drip error: {e}")
    if hhmm == "19:00" and now.day == 1:
        try:
            eng.college_league(); ran.append("college-league")
        except Exception as e:
            log(f"college league error: {e}")
    if hhmm == "12:30":
        try:
            eng.examday_checkins(); ran.append("examday-checkin")
        except Exception as e:
            log(f"examday error: {e}")
    if hhmm == "08:30" and now.weekday() == 0:
        try:
            eng.partner_weekly(); ran.append("partner-weekly")
        except Exception as e:
            log(f"partner-weekly error: {e}")
    if hhmm == "00:20":
        try:
            eng.rewards_housekeeping(); ran.append("rewards-expiry")
            eng.partner_housekeeping(); ran.append("partner-expiry")
        except Exception as e:
            log(f"rewards error: {e}")
    if now.weekday() == 5 and hhmm == "11:00":
        try:
            from core import social as _so
            for ch in getattr(config, "CHAMPION_CHANNELS", ["CURRENT"]):
                if not dry:
                    eng.tg.send_message(config.channel_chat_id(ch), "📸 Follow & earn:\n" + _so.follow_prompt())
            ran.append("social-promo")
        except Exception as e:
            log(f"social promo error: {e}")
    if now.weekday() in (1, 4) and hhmm == config.REWARDS_PROMO_TIME:
        try:
            eng.rewards_promo(); ran.append("rewards-promo")
        except Exception as e:
            log(f"rewards promo error: {e}")
    if now.weekday() == 6 and hhmm == "21:15":
        try:
            eng.weekly_report_cards(); ran.append("report-cards")
        except Exception as e:
            log(f"report error: {e}")
    if now.weekday() < 6 and hhmm == config.CHALLENGE_TIME:
        try:
            eng.challenge_invite(); ran.append("challenge")
        except Exception as e:
            log(f"challenge error: {e}")
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
    _busy = ("07:30", "10:30", "13:30", "16:30", "19:30", "21:00", "21:30")
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
