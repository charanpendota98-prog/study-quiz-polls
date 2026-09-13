"""
AUTOPILOT — the bot fixes things itself and tells you at night what it did.

Runs from watch.py (every 30 min: tick; 22:45: night report). Each action is idempotent and
rate-limited so it can never spam.

Self-healing
  • low question stock in a channel  → run collector now (+ mark for backfill)
  • campus event open > 6 h with 0 registered → auto-close; > 6 h with players → remind organiser once
  • DM 'blocked' members are excluded from all sends (already) → weekly purge from DM lists
  • partner offers expired / vouchers stale → housekeeping (already daily) — also on tick if many

Growth on autopilot
  • 07:30  Personal Coach DM: 3 questions from each member's WEAKEST topics (own exam channel),
           sent as scored quiz polls through round_polls.json (round_id "C<date>") so points count.
           Members who answered the coach 5 days in a row get 🎯 Focus badge (+25).
  • 18:00  Win-back: members inactive 3 days → 1 DM ("మీ జిల్లా #k కి పడింది, 2 నిమిషాల quiz?"),
           inactive 7 days → different DM with offers hook, inactive 21 days → last one. Max 3 ever
           per silence period, resets when they play.
  • 12:00  Exam-countdown: if member.exam_date is set (or admin set per exam), "D-14 / D-7 / D-1"
           plan DM (topics + what to revise) — silent otherwise.

Night report (22:45, to STAFF_IDS): what was done today + tomorrow's plan.
State: data/autopilot.json
"""
from __future__ import annotations

from datetime import datetime, timedelta

from . import config
from .store import load_json, save_json_atomic

PATH = config.DATA / "autopilot.json"
LOW_STOCK = 60
COACH_Q = 3
COACH_BADGE_DAYS, COACH_BADGE_PTS = 5, 25
WINBACK_DAYS = {3: "😴 3 రోజులు ఆడలేదు! మీ జిల్లా {district} board లో మీ స్థానం పడిపోతోంది.\n2 నిమిషాలు → /quiz (మీ weak topic నుంచే వస్తుంది) 🎯",
                7: "👋 వారం అయింది. ఈ లోపు {district} లో కొత్త offers వచ్చాయి → /offers\nఈరోజు ఒక్క round ఆడితే streak మళ్ళీ మొదలు + 🛡 shield 🔥",
                21: "🙏 చివరి reminder — మీ {points} points అలాగే ఉన్నాయి (expire కావు).\nExam దగ్గర పడుతోంది; రోజూ 10 Q చాలు → /quiz. మళ్ళీ disturb చేయము."}


def _now():
    return datetime.now(config.IST)


def _day(dt=None):
    return (dt or _now()).strftime("%Y-%m-%d")


def _load():
    d = load_json(PATH, {}) or {}
    d.setdefault("log", {}); d.setdefault("flags", {})
    return d


def _save(d):
    save_json_atomic(PATH, d)


def _log(d, what):
    day = _day()
    d["log"].setdefault(day, []).append(f"{_now().strftime('%H:%M')} {what}")
    for k in list(d["log"]):
        if k < _day(_now() - timedelta(days=7)):
            d["log"].pop(k, None)


# ================================================================== healing
def heal(bank, members, tg, dry=False):
    d = _load()
    done = []
    # 1) low stock → collector
    low = []
    for ch in getattr(config, "PUBLIC_CHANNELS", []):
        try:
            n = len(bank.unused(ch))
        except Exception:
            continue
        if n < LOW_STOCK:
            low.append((ch, n))
    if low and d["flags"].get("collect_day") != _day():
        d["flags"]["collect_day"] = _day()
        if not dry:
            try:
                from .collector import collect_daily
                st = collect_daily()
                done.append(f"📉 low stock {', '.join(f'{c}:{n}' for c, n in low)} → collector ran (+{st.get('accepted', 0)})")
            except Exception as e:
                done.append(f"📉 low stock → collector error {e}")
        else:
            done.append(f"📉 low stock {low} → collector (dry)")
    # 2) stuck campus events
    try:
        from . import campus as C
        cd = C._load()
        for e in cd["events"].values():
            if e["state"] != "open":
                continue
            age_h = (_now() - datetime.fromisoformat(e["created"])).total_seconds() / 3600
            if age_h < 6:
                continue
            reg = sum(1 for u in e["players"] if (members.members.get(u) or {}).get("registered"))
            if reg == 0 and age_h > 12:
                e["state"] = "cancelled"; done.append(f"🎓 {e['code']} auto-closed (no students, {int(age_h)}h)")
            elif not e.get("_reminded") and e.get("by"):
                e["_reminded"] = True
                if not dry:
                    try:
                        tg.send_message(e["by"], f"⏰ {e['code']} {e['name']} ఇంకా open ({reg} students ready). Start: /campus")
                    except Exception:
                        pass
                done.append(f"🎓 {e['code']} organiser reminded")
        C._save(cd)
    except Exception as e:
        done.append(f"campus heal note: {e}")
    # 3) stale vouchers
    try:
        from . import partners as P, rewards as R
        n = P.expire_stale() + R.expire_stale(members)
        if n:
            done.append(f"🎟 released {n} expired vouchers")
    except Exception:
        pass
    for x in done:
        _log(d, x)
    _save(d)
    return done


# ================================================================== coach
def coach_targets(members, limit=5000):
    out = []
    for uid, m in members.members.items():
        if not m.get("registered") or m.get("dm_blocked") or m.get("no_coach"):
            continue
        if (m.get("last_active") or "") < _day(_now() - timedelta(days=14)):
            continue          # win-back handles the silent ones
        out.append(uid)
    return out[:limit]


def coach_round(bank, members, tg, dry=False):
    """07:30 — 3 weak-topic questions per active member, scored as round C<date>."""
    from .content import build_question_text, build_options, build_explanation
    from .members import exam_channel
    d = _load()
    if d["flags"].get("coach_day") == _day():
        return 0
    d["flags"]["coach_day"] = _day(); _save(d)
    round_id = "C" + _now().strftime("%Y%m%d")
    dm_map = {}
    sent_members = 0
    tf = bool(getattr(config, "TELUGU_FIRST", True))
    for uid in coach_targets(members):
        m = members.members[uid]
        ch = exam_channel(m.get("exam", "")) or "CURRENT"
        if ch not in config.CHANNELS:
            ch = "CURRENT"
        weak = members.weak_topics(uid) if hasattr(members, "weak_topics") else []
        qs = []
        for _ in range(COACH_Q):
            try:
                q = bank.pick_adaptive(ch, weak_topics=weak, review_qids=None)
            except Exception:
                q = None
            if not q:
                try:
                    picked = bank.pick(ch, 1); q = picked[0] if picked else None
                except Exception:
                    q = None
            if q and q["id"] not in {x["id"] for x in qs}:
                qs.append(q)
        if not qs:
            continue
        head = f"🎯 Personal Coach — {m.get('name', '')[:14]}\n" + (f"Weak topics: {', '.join(t.title() for t in weak[:3])}\n" if weak else "") + \
               f"{len(qs)} Q · ప్రతి ✅ +10 · 5 రోజులు వరుసగా ఆడితే 🎯 Focus badge +{COACH_BADGE_PTS}"
        if dry:
            sent_members += 1; continue
        try:
            tg.send_message(uid, head)
        except Exception as e:
            if "blocked" in str(e).lower():
                m["dm_blocked"] = True
            continue
        cfg = config.CHANNELS[ch]
        for i, q in enumerate(qs, 1):
            payload = {"chat_id": uid, "question": build_question_text(q, cfg, telugu_first=tf, position=f"Coach {i}/{len(qs)}")[:300],
                       "options": [{"text": o} for o in build_options(q, telugu_first=tf)], "type": "quiz",
                       "is_anonymous": False, "correct_option_id": q["answer_index"]}
            ex = build_explanation(q, telugu_first=tf)
            if ex.strip():
                payload["explanation"] = ex[:config.TG_POLL_EXPLANATION_MAX]
            try:
                res = tg._call("sendPoll", payload)
                pid = (res or {}).get("result", {}).get("poll", {}).get("id")
                if pid:
                    dm_map[str(pid)] = [round_id, ch, q["id"], int(q["answer_index"]), str(uid), q.get("topic", "")]
            except Exception:
                break
        sent_members += 1
    if dm_map:
        path = config.DATA / "round_polls.json"
        cur = load_json(path, {})
        cur.update(dm_map)
        if len(cur) > 8000:
            for k in list(cur)[:-8000]:
                cur.pop(k, None)
        save_json_atomic(path, cur)
    try:
        members.kv.save()
    except Exception:
        pass
    d = _load(); _log(d, f"🎯 coach: {sent_members} members × {COACH_Q} Q"); _save(d)
    return sent_members


def coach_streaks(members, tg, dry=False):
    """22:40 — who answered today's coach round? streak + badge."""
    today = "C" + _now().strftime("%Y%m%d")
    r = members.data.get("rounds", {}).get(today, {}) if hasattr(members, "data") else {}
    played = {u for ch in r.get("by_channel", {}).values() for u in ch}
    n_badge = 0
    for uid, m in members.members.items():
        if not m.get("registered"):
            continue
        if uid in played:
            m["coach_streak"] = m.get("coach_streak", 0) + 1
            if m["coach_streak"] % COACH_BADGE_DAYS == 0:
                m["points"] = m.get("points", 0) + COACH_BADGE_PTS
                if "focus" not in m.setdefault("badges", []):
                    m["badges"].append("focus")
                n_badge += 1
                if not dry:
                    try:
                        tg.send_message(uid, f"🎯 FOCUS BADGE! {m['coach_streak']} రోజులు వరుసగా coach ఆడారు → +{COACH_BADGE_PTS} pts. Weak topics ఇప్పుడు strong అవుతున్నాయి 💪")
                    except Exception:
                        pass
        elif m.get("coach_streak"):
            m["coach_streak"] = 0
    members.kv.save()
    d = _load(); _log(d, f"🎯 coach played by {len(played)} · badges {n_badge}"); _save(d)
    return len(played), n_badge


# ================================================================== win-back
def winback(members, tg, dry=False):
    d = _load()
    if d["flags"].get("winback_day") == _day():
        return 0
    d["flags"]["winback_day"] = _day()
    today = _now().date()
    n = 0
    for uid, m in members.members.items():
        if not m.get("registered") or m.get("dm_blocked"):
            continue
        la = m.get("last_active") or (m.get("registered_at") or "")[:10]
        try:
            silent = (today - datetime.fromisoformat(la).date()).days
        except Exception:
            continue
        if silent <= 0:
            m["_wb_sent"] = []
            continue
        if silent not in WINBACK_DAYS or silent in (m.get("_wb_sent") or []):
            continue
        txt = WINBACK_DAYS[silent].format(district=m.get("district", "మీ జిల్లా"), points=m.get("points", 0))
        m.setdefault("_wb_sent", []).append(silent)
        if not dry:
            try:
                tg.send_message(uid, txt)
            except Exception as e:
                if "blocked" in str(e).lower():
                    m["dm_blocked"] = True
                continue
        n += 1
    members.kv.save()
    _log(d, f"😴 win-back DMs: {n}"); _save(d)
    return n


# ================================================================== exam countdown
def exam_countdown(members, tg, dry=False):
    """EXAM_DATES env: 'TSPSC=2026-10-15,APPSC=2026-11-02' → D-14/D-7/D-3/D-1 plan DMs."""
    raw = getattr(config, "EXAM_DATES", "") or ""
    dates = {}
    for part in raw.split(","):
        if "=" in part:
            k, v = part.split("=", 1); dates[k.strip().upper()] = v.strip()
    if not dates:
        return 0
    d = _load()
    if d["flags"].get("countdown_day") == _day():
        return 0
    d["flags"]["countdown_day"] = _day()
    today = _now().date()
    n = 0
    plans = {14: "📅 D-14: రోజూ 2 rounds + weak topics coach. Syllabus మొత్తం ఒకసారి revise.",
             7: "📅 D-7: PYQ mode — /quiz లో previous-paper Q ఎక్కువ వస్తాయి. రోజూ mock (Grand Test ఆదివారం).",
             3: "📅 D-3: కొత్తవి చదవొద్దు. /review (missed Qs) + Current Affairs నెల PDF (/redeem).",
             1: "📅 D-1: Light revision, 7 గంటలు నిద్ర. Hall ticket, ID ready. All the best 💪 Exam అయ్యాక /examdone → offers!"}
    for uid, m in members.members.items():
        if not m.get("registered") or m.get("dm_blocked"):
            continue
        ex = (m.get("exam") or "").upper()
        for key, ds in dates.items():
            if key not in ex and ex not in key:
                continue
            try:
                left = (datetime.fromisoformat(ds).date() - today).days
            except Exception:
                continue
            if left in plans:
                if not dry:
                    try:
                        tg.send_message(uid, f"🎯 {key} exam {left} రోజుల్లో ({ds})\n{plans[left]}")
                    except Exception:
                        continue
                n += 1
    _log(d, f"📅 exam countdown DMs: {n}"); _save(d)
    return n


# ================================================================== night report
def night_report(members, tg, dry=False):
    d = _load()
    today = d["log"].get(_day(), [])
    y = _day(_now() - timedelta(days=1))
    lines = ["🌙 Autopilot — ఈరోజు నేను చేసినవి:", ""]
    lines += [f"• {x}" for x in today] or ["• (ఏమీ అవసరం లేదు — అంతా normal)"]
    lines += ["", "రేపు: 07:30 coach · 08:00 brief · ad slots · 12:00 countdown · 18:00 win-back · 21:00 War · 21:30 exam boards"]
    txt = "\n".join(lines)
    n = 0
    for aid in getattr(config, "STAFF_IDS", []) or ([str(config.ADMIN_ID)] if config.ADMIN_ID else []):
        if dry:
            n += 1; continue
        try:
            tg.send_message(aid, txt); n += 1
        except Exception:
            pass
    return txt if n or dry else ""
