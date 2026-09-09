#!/usr/bin/env python3
"""
STUDENTUP — MEMBERS, REGISTRATION & POINTS ENGINE
- Member registration (name, exam target, language) via guided /register flow.
- Points: +10 per correct answer, +5 first activity of the day, streak
  milestone bonuses (3/7/15/30/100 days).
- Levels by points: Newcomer -> Bronze -> Silver -> Gold -> Platinum -> Champion.
- Ranks + weekly/all-time leaderboards (bilingual rendering).
- Auto-creates a profile for anyone who answers, so no points are ever lost;
  /register just adds name/exam/language.
Pure JSON (atomic), stdlib only.
"""
from __future__ import annotations

import re

from datetime import datetime, timedelta

from . import config
from .store import KV, now_iso

EXAM_TARGETS = ["TSPSC", "APPSC", "Banking", "Railway", "Police",
                "Defence", "SSC/UPSC", "Current Affairs GK"]
LANGUAGES = ["English", "Telugu", "Both (EN + TE)"]

# Points
P_CORRECT = 10
P_DAILY_FIRST = 5
STREAK_BONUS = {3: 20, 7: 75, 15: 200, 30: 500, 100: 2000}

# Levels: (min points, icon, title EN, title TE)
LEVELS = [
    (0, "🆕", "Newcomer", "కొత్తవారు"),
    (100, "🥉", "Bronze", "కాంస్యం"),
    (300, "🥈", "Silver", "రజతం"),
    (700, "🥇", "Gold", "స్వర్ణం"),
    (1500, "💎", "Platinum", "ప్లాటినం"),
    (3000, "👑", "Champion", "ఛాంపియన్"),
]


def _day(dt=None):
    return (dt or datetime.now(config.IST)).strftime("%Y-%m-%d")


def level_for(points: int):
    idx = 0
    for i, (thresh, *_rest) in enumerate(LEVELS):
        if points >= thresh:
            idx = i
    thresh, icon, title_en, title_te = LEVELS[idx]
    next_thresh = LEVELS[idx + 1][0] if idx + 1 < len(LEVELS) else None
    return {"icon": icon, "title_en": title_en, "title_te": title_te,
            "next": next_thresh, "index": idx}


def exam_channel(exam):
    m = {"TSPSC": "TSPSC", "APPSC": "APPSC", "Banking": "BANKING", "Railway": "RAILWAY",
         "Police": "POLICE", "Defence": "DEFENCE", "SSC": "SSC", "SSC/UPSC": "SSC",
         "Current Affairs GK": "CURRENT"}
    return m.get(exam or "", "TSPSC")


class Members:
    def __init__(self):
        self.kv = KV(config.DATA / "members.json", default={"members": {}, "pending": {}})
        self.data = self.kv.data
        self.members = self.data.setdefault("members", {})
        self.pending = self.data.setdefault("pending", {})
        # Form sign-ups we couldn't link to a numeric id yet (keyed by @username)
        self.form_pending = self.data.setdefault("form_pending", {})

    # ------------------------------------------------------------ profile
    def _get(self, uid):
        return self.members.setdefault(str(uid), {
            "name": "", "username": "", "exam": "", "lang": "",
            "registered": False, "registered_at": "",
            "points": 0, "correct": 0, "total": 0,
            "streak": 0, "best_streak": 0,
            "last_active": "", "last_correct": "", "claimed": [],
            # adaptive learning
            "topics": {},          # topic -> {"correct":n,"total":n}
            "review": [],          # spaced-repetition queue (missed questions)
            "badges": [],          # earned badge ids
            "answers_today": 0,    # for daily cap / gamification
        })

    def register(self, uid, name=None, exam=None, lang=None, username="", **extra):
        m = self._get(uid)
        if name:
            m["name"] = name
        if username:
            m["username"] = username
        if exam:
            m["exam"] = exam
        if lang:
            m["lang"] = lang
        for k, v in extra.items():
            if v and not m.get(k):
                m[k] = v
            else:
                m.setdefault(k, v if v is not None else "")
        if not m.get("follow"):
            m["follow"] = list(dict.fromkeys([exam_channel(m.get("exam", "")), "CURRENT"]))
        first = not m["registered"]
        if first:
            m["registered"] = True
            m["registered_at"] = now_iso()
            m["points"] += 25  # registration bonus
        self.kv.save()
        try:                       # mirror to Google Sheet CRM (no-op if not configured)
            from . import crm
            crm.push_member(uid, m)
        except Exception as e:
            print(f"   [members] crm note: {e}")
        return m

    # ------------------------------------------------------------ points
    def award_answer(self, uid, username="", correct=True, topic="", qid=""):
        """Award points for a poll answer. Returns a dict describing the award."""
        m = self._get(uid)
        if username:
            m["username"] = username
        if not m["name"]:
            m["name"] = username or f"player{uid}"
        m["total"] += 1
        m["answers_today"] = m.get("answers_today", 0) + 1
        today = _day()
        yesterday = _day(datetime.now(config.IST) - timedelta(days=1))
        earned = 0
        events = []
        new_badges = []

        # ---- topic-level stats for adaptive learning
        if topic:
            t = m["topics"].setdefault(topic.lower(), {"correct": 0, "total": 0})
            t["total"] += 1

        # ---- spaced-repetition review queue
        if qid:
            m["review"] = [r for r in m.get("review", []) if r.get("qid") != qid]
            if not correct:
                # missed question -> due immediately (same-day /review), then
                # spaced: 3d -> 7d as they answer it correctly.
                m["review"].append({"qid": qid, "due": _day(),
                                    "interval": 0, "topic": topic})
            else:
                # correct -> advance this spaced-repetition card
                #   interval 0 (same-day) -> 3 days -> 7 days -> mastered (drop)
                kept = []
                for r in m.get("review", []):
                    if r.get("qid") == qid:
                        nxt = {0: 3, 3: 7}.get(r["interval"])
                        if nxt:
                            r["interval"] = nxt
                            r["due"] = (datetime.now(config.IST) +
                                       timedelta(days=nxt)).strftime("%Y-%m-%d")
                            kept.append(r)
                        # interval 7 correct -> mastered, drop
                    else:
                        kept.append(r)
                m["review"] = kept

        if m["last_active"] != today:
            earned += P_DAILY_FIRST            # daily participation bonus
            events.append(f"+{P_DAILY_FIRST} daily")
        m["last_active"] = today

        leveled_up = None
        if correct:
            m["correct"] += 1
            if topic:
                m["topics"][topic.lower()]["correct"] += 1
            before_level = level_for(m["points"])["index"]
            earned += P_CORRECT
            events.append(f"+{P_CORRECT} correct")
            # streak over consecutive days with a correct answer
            if m["last_correct"] == yesterday:
                m["streak"] += 1
            elif m["last_correct"] != today:
                m["streak"] = 1
            m["last_correct"] = today
            m["best_streak"] = max(m["best_streak"], m["streak"])
            # streak milestone bonuses
            for days, bonus in STREAK_BONUS.items():
                if m["streak"] >= days and days not in m["claimed"]:
                    m["claimed"].append(days)
                    earned += bonus
                    events.append(f"+{bonus} streak {days}d 🔥")
            m["points"] += earned
            after_level = level_for(m["points"])
            if after_level["index"] > before_level:
                leveled_up = after_level
        else:
            m["points"] += earned

        # ---- badges (recompute deterministically)
        before_badges = set(m.get("badges", []))
        for b in self._earned_badges(m):
            if b["id"] not in before_badges:
                m.setdefault("badges", []).append(b["id"])
                new_badges.append(b)

        self.kv.save()
        return {"earned": earned, "events": events, "level_up": leveled_up,
                "points": m["points"], "streak": m["streak"],
                "new_badges": new_badges}

    # ------------------------------------------------------------ badges
    def _earned_badges(self, m):
        """Deterministic list of badges earned for a member's current stats."""
        out = []
        def has(bid): return bid in m.get("badges", [])
        if not has("first") and m["total"] >= 1:
            out.append({"id": "first", "icon": "🎯", "en": "First Answer", "te": "మొదటి సమాధానం"})
        if not has("correct10") and m["correct"] >= 10:
            out.append({"id": "correct10", "icon": "✅", "en": "10 Correct", "te": "10 సరైనవి"})
        if not has("correct100") and m["correct"] >= 100:
            out.append({"id": "correct100", "icon": "💯", "en": "Century — 100 Correct", "te": "100 సరైనవి"})
        if not has("streak3") and m["best_streak"] >= 3:
            out.append({"id": "streak3", "icon": "🔥", "en": "3-Day Streak", "te": "3 రోజుల స్ట్రీక్"})
        if not has("streak7") and m["best_streak"] >= 7:
            out.append({"id": "streak7", "icon": "🔥", "en": "7-Day Streak", "te": "7 రోజుల స్ట్రీక్"})
        if not has("streak30") and m["best_streak"] >= 30:
            out.append({"id": "streak30", "icon": "🔥", "en": "30-Day Streak", "te": "30 రోజుల స్ట్రీక్"})
        if not has("sharp") and m["total"] >= 20 and (m["correct"] / m["total"]) >= 0.9:
            out.append({"id": "sharp", "icon": "🧠", "en": "Sharp Shooter (90%+) — 20+ attempts", "te": "90%+ ఖచ్చితత్వం"})
        if not has("champion") and m["points"] >= 3000:
            out.append({"id": "champion", "icon": "👑", "en": "Champion Level", "te": "ఛాంపియన్"})
        return out

    # ------------------------------------------------------------ adaptive
    def weak_topics(self, uid, limit=3, weak_below=0.75):
        """Topics below 75% accuracy (min 2 attempts), weakest first."""
        m = self.members.get(str(uid)) or {}
        rows = []
        for topic, st in (m.get("topics") or {}).items():
            if st["total"] >= 2:
                acc = st["correct"] / st["total"]
                if acc < weak_below:
                    rows.append((acc, st["total"], topic))
        rows.sort()  # lowest accuracy first
        return [t for _acc, _n, t in rows[:limit]]

    def due_reviews(self, uid):
        """Spaced-repetition questions due for re-asking today."""
        m = self.members.get(str(uid)) or {}
        today = _day()
        return [r for r in m.get("review", []) if r.get("due", "9999") <= today]

    # ------------------------------------------------------------ queries
    def profile(self, uid):
        m = self.members.get(str(uid))
        if not m:
            return None
        lvl = level_for(m["points"])
        acc = round(100 * m["correct"] / m["total"], 1) if m["total"] else 0.0
        rank = self.rank(uid)
        return {**m, "level": lvl, "accuracy": acc, "rank": rank}

    def rank(self, uid):
        order = sorted(self.members.items(),
                       key=lambda kv: kv[1].get("points", 0), reverse=True)
        for i, (mid, _m) in enumerate(order, 1):
            if str(mid) == str(uid):
                return i
        return len(order)

    # ------------------------------------------------------------ analytics
    def analytics(self):
        """Aggregate member stats for admin reports."""
        from collections import Counter
        reg = [m for m in self.members.values() if m.get("registered")]
        by_exam = Counter((m.get("exam") or "Unknown") for m in reg)
        by_state = Counter((m.get("state") or "Unknown") for m in reg)
        by_district = Counter((m.get("district") or "Unknown") for m in reg if m.get("district"))
        by_lang = Counter((m.get("lang") or "Unknown") for m in reg)
        by_source = Counter((m.get("source") or "Unknown") for m in reg if m.get("source"))
        total_points = sum(m.get("points", 0) for m in reg)
        total_correct = sum(m.get("correct", 0) for m in reg)
        total_answers = sum(m.get("total", 0) for m in reg)
        active_today = sum(1 for m in reg if m.get("last_active") == _day())
        return {
            "registered": len(reg), "form_pending": len(self.form_pending),
            "by_exam": by_exam, "by_state": by_state, "by_district": by_district,
            "by_lang": by_lang, "by_source": by_source,
            "total_points": total_points, "total_correct": total_correct,
            "total_answers": total_answers, "active_today": active_today,
        }

    def render_analytics(self):
        a = self.analytics()
        L = ["📊 *StudentUp — Member Analytics*", ""]
        L.append(f"👥 Registered: *{a['registered']}*  (form pending: {a['form_pending']})")
        L.append(f"✅ Answers: {a['total_correct']}/{a['total_answers']} correct  ·  ⭐ {a['total_points']} points")
        L.append(f"⚡ Active today: {a['active_today']}")

        def block(title, counter, limit=8):
            if not counter:
                return []
            lines = [f"\n*{title}*"]
            for name, n in counter.most_common(limit):
                bar = "█" * min(n, 12)
                lines.append(f"  {bar} {n}  {name}")
            return lines

        L += block("By exam target", a["by_exam"])
        L += block("By state", a["by_state"])
        L += block("Top districts", a["by_district"])
        L += block("By medium", a["by_lang"])
        L += block("How they found us", a["by_source"])
        return "\n".join(L)

    def top(self, limit=10):
        rows = [(uid, m) for uid, m in self.members.items()
                if m.get("points", 0) > 0]
        rows.sort(key=lambda kv: kv[1].get("points", 0), reverse=True)
        return rows[:limit]

    def count(self):
        return len([m for m in self.members.values() if m.get("registered")])

    def count_form(self):
        """Total registered = in-bot + Google-Form signups."""
        return self.count() + len(self.form_pending)

    # ------------------------------------------------------------ form import
    def import_form_signup(self, info: dict):
        """
        Record a Google-Form registration. `info` keys may include:
        name, username (@handle), tg_id (numeric), phone, email, state, district,
        exam, lang, stage, coaching, source.
        If a numeric id is known, the member is created immediately; otherwise
        it's held in form_pending keyed by @username until they /start the bot.
        Returns ('linked', uid) or ('pending', username).
        """
        uname = (info.get("username") or "").lstrip("@").strip().lower()
        tg_id = info.get("tg_id")
        base = {
            "name": info.get("name", ""), "username": uname,
            "exam": info.get("exam", ""), "lang": info.get("lang", ""),
            "phone": info.get("phone", ""), "email": info.get("email", ""),
            "state": info.get("state", ""), "district": info.get("district", ""),
            "stage": info.get("stage", ""), "coaching": info.get("coaching", ""),
            "education": info.get("education", ""),
            "target_year": info.get("target_year", ""),
            "study_mode": info.get("study_mode", info.get("coaching", "")),
            "hours": info.get("hours", ""),
            "updates": info.get("updates", ""),
            "form_source": "google_form",
        }
        if tg_id:
            m = self.register(tg_id, name=base["name"] or None, exam=base["exam"] or None,
                              lang=base["lang"] or None, username=uname)
            for k in ("phone","email","state","district","stage","coaching","education","target_year","study_mode","hours","updates","form_source"):
                if base.get(k):
                    m[k] = base[k]
            self.kv.save()
            return "linked", str(tg_id)
        # only a username — try to match an existing member by @username
        for uid, m in self.members.items():
            if (m.get("username") or "").lstrip("@").lower() == uname and uname:
                for k, v in base.items():
                    if v and not m.get(k):
                        m[k] = v
                m["registered"] = True
                self.kv.save()
                return "linked", uid
        # hold until they appear in Telegram
        if uname or base["phone"]:
            key = uname or base["phone"]
            self.form_pending[key] = {**base, "registered": True, "registered_at": now_iso()}
            self.kv.save()
            return "pending", key
        return "ignored", None

    def link_if_pending(self, uid, username, name=""):
        """When a user /starts the bot, link any matching Google-Form signup."""
        uname = (username or "").lstrip("@").strip().lower()
        entry = self.form_pending.pop(uname, None) if uname else None
        if not entry:
            return False
        m = self.register(uid, name=entry.get("name") or name or None,
                          exam=entry.get("exam") or None,
                          lang=entry.get("lang") or None, username=uname)
        for k in ("phone","email","state","district","stage","coaching","education","target_year","study_mode","hours","updates"):
            if entry.get(k):
                m[k] = entry[k]
        m["form_source"] = "google_form"
        self.kv.save()
        return True

    # ------------------------------------------------------------ rendering
    def render_profile(self, uid):
        p = self.profile(uid)
        if not p:
            return ("You're not registered yet. Send /register to join and start "
                    "earning points! 🏆\n⤷ ఇంకా రిజిస్టర్ కాలేదు. /register పంపి చేరండి, "
                    "పాయింట్లు సంపాదించండి!")
        lvl = p["level"]
        name = p["name"] or "player"
        lines = [
            f"{lvl['icon']} {name} — {lvl['title_en']} ({lvl['title_te']})",
            f"⭐ Points: {p['points']}   🏅 Rank: #{p['rank']}",
            f"✅ Correct: {p['correct']}/{p['total']} ({p['accuracy']}%)",
            f"🔥 Streak: {p['streak']} day(s) | Best: {p['best_streak']}",
        ]
        if p.get("exam"):
            lines.append(f"🎯 Target: {p['exam']}")
        if p.get("district"):
            lines.append(f"📍 {p['district']}" + (f", {p['state']}" if p.get("state") else ""))
        badges = p.get("badges", [])
        if badges:
            bdict = {b["id"]: b["icon"] for b in self._all_badge_defs()}
            lines.append("🏅 Badges: " + " ".join(bdict.get(b, b) for b in badges))
        weak = self.weak_topics(uid)
        if weak:
            lines.append("📌 Practice more: " + ", ".join(weak[:3]))
        due = self.due_reviews(uid)
        if due:
            lines.append(f"🔁 {len(due)} revision question(s) due — send /review")
        if lvl["next"]:
            lines.append(f"📈 {lvl['next'] - p['points']} points to next level")
        else:
            lines.append("👑 Maximum level reached — Champion!")
        lines.append("⤷ /quiz ఆడి పాయింట్లు సంపాదించండి!")
        return "\n".join(lines)

    @staticmethod
    def _all_badge_defs():
        # single source for badge icons (mirror of _earned_badges)
        return [
            {"id": "first", "icon": "🎯"}, {"id": "correct10", "icon": "✅"},
            {"id": "correct100", "icon": "💯"}, {"id": "streak3", "icon": "🔥"},
            {"id": "streak7", "icon": "🔥"}, {"id": "streak30", "icon": "🔥"},
            {"id": "sharp", "icon": "🧠"}, {"id": "champion", "icon": "👑"},
        ]

    def is_registered(self, uid) -> bool:
        m = self.members.get(str(uid))
        return bool(m and m.get("registered"))

    # ------------------------------------------------------------ districts
    def district_board(self, limit=10):
        """District-wise ranking: total points, members, avg accuracy."""
        agg = {}
        for m in self.members.values():
            d = m.get("district")
            if not d or not m.get("registered"):
                continue
            a = agg.setdefault(d, {"state": m.get("state", ""), "points": 0, "members": 0,
                                   "correct": 0, "total": 0, "top": ("", 0)})
            a["points"] += m.get("points", 0)
            a["members"] += 1
            a["correct"] += m.get("correct", 0)
            a["total"] += m.get("total", 0)
            if m.get("points", 0) > a["top"][1]:
                a["top"] = (m.get("name") or "player", m.get("points", 0))
        rows = sorted(agg.items(), key=lambda kv: kv[1]["points"], reverse=True)
        return rows[:limit]

    def top_in_district(self, district, limit=5):
        rows = [(uid, m) for uid, m in self.members.items()
                if m.get("district") == district and m.get("points", 0) > 0]
        rows.sort(key=lambda kv: kv[1].get("points", 0), reverse=True)
        return rows[:limit]

    def render_district_board(self, district=None):
        from . import districts as D
        if district:
            rows = self.top_in_district(district)
            te = D.telugu_name(district)
            if not rows:
                return (f"📍 {district} / {te}\nNo scores yet — be the first! /quiz\n"
                        f"⤷ ఇంకా స్కోర్లు లేవు — మీరే మొదటివారు అవ్వండి!")
            medals = ["🥇", "🥈", "🥉"]
            lines = [f"📍 *{district} / {te} — District Toppers*", ""]
            for i, (uid, m) in enumerate(rows):
                lvl = level_for(m.get("points", 0))
                r = medals[i] if i < 3 else f"{i+1}."
                lines.append(f"{r} {lvl['icon']} {m.get('name') or 'player'} — ⭐{m.get('points',0)}")
            return "\n".join(lines)
        board = self.district_board()
        if not board:
            return ("🗺 District Leaderboard\nNo district scores yet — /register with your district and play /quiz!\n"
                    "⤷ /register లో మీ జిల్లా ఇచ్చి /quiz ఆడండి.")
        medals = ["🥇", "🥈", "🥉"]
        lines = ["🗺 *District Leaderboard — జిల్లాల ర్యాంకింగ్*", ""]
        for i, (d, a) in enumerate(board):
            r = medals[i] if i < 3 else f"{i+1}."
            acc = round(100 * a["correct"] / a["total"]) if a["total"] else 0
            st = "TS" if a["state"].startswith("Tel") else ("AP" if a["state"].startswith("Andhra") else "")
            lines.append(f"{r} {d}{' (' + st + ')' if st else ''} — ⭐{a['points']} · 👥{a['members']} · 🎯{acc}%  "
                         f"(top: {a['top'][0]})")
        lines.append("")
        lines.append("Your district: /district · Join: /register ⭐")
        return "\n".join(lines)

    def render_leaderboard(self, weekly_note=True):
        top = self.top(10)
        if not top:
            return ("🏆 Leaderboard\nఇంకా స్కోర్లు లేవు — /register చేసి /quiz ఆడండి!\n"
                    "(No scores yet — register and play /quiz!)")
        medals = ["🥇", "🥈", "🥉"]
        lines = ["🏆 *StudentUp Leaderboard* • టాప్ ప్లేయర్లు", ""]
        for i, (uid, m) in enumerate(top):
            lvl = level_for(m.get("points", 0))
            rank = medals[i] if i < 3 else f"{i+1}."
            nm = m.get("name") or f"player{uid}"
            lines.append(f"{rank} {lvl['icon']} {nm} — ⭐{m.get('points',0)} "
                         f"(🔥{m.get('streak',0)}d)")
        lines.append("")
        lines.append("Play /quiz in this chat to climb! ⭐ | /register to join.")
        return "\n".join(lines)

    # ------------------------------------------------------------ live rounds
    # Channel polls are anonymous in Telegram, so the engine mirrors every
    # round question into registered members' DMs (non-anonymous). Answers
    # land here, keyed by round_id, and the Top-10 is posted back to the channel.
    def reload(self):
        self.kv = KV(config.DATA / "members.json", default={"members": {}, "pending": {}})
        self.data = self.kv.data
        self.members = self.data.setdefault("members", {})
        self.pending = self.data.setdefault("pending", {})
        self.form_pending = self.data.setdefault("form_pending", {})
        return self

    def recipients_for(self, channel_key):
        """Registered members who should receive this channel's round in DM."""
        out = []
        for uid, m in self.members.items():
            if not m.get("registered") or m.get("dm_blocked"):
                continue
            follow = m.get("follow") or [exam_channel(m.get("exam", "")), "CURRENT"]
            if channel_key in follow:
                out.append(uid)
        return out

    def set_follow(self, uid, channels):
        m = self._get(uid)
        m["follow"] = [c for c in channels if c in config.CHANNELS]
        self.kv.save()
        return m["follow"]

    def mark_blocked(self, uid):
        m = self._get(uid)
        m["dm_blocked"] = True
        self.kv.save()

    def record_round_answer(self, uid, round_id, channel_key, correct, qid=""):
        rounds = self.data.setdefault("rounds", {})
        r = rounds.setdefault(round_id, {"ts": now_iso(), "by_channel": {}})
        ch = r["by_channel"].setdefault(channel_key, {})
        e = ch.setdefault(str(uid), {"correct": 0, "total": 0, "qids": [], "first": now_iso()})
        if qid and qid in e["qids"]:
            return e
        e["total"] += 1
        e["correct"] += 1 if correct else 0
        if qid:
            e["qids"].append(qid)
        e["last"] = now_iso()
        # keep only last 60 rounds
        if len(rounds) > 60:
            for k in sorted(rounds)[:-60]:
                rounds.pop(k, None)
        self.kv.save()
        return e

    def sync_sheet_all(self):
        from . import crm
        return crm.push_all(self.members)

    def round_top(self, round_id, channel_key, limit=10):
        ch = self.data.get("rounds", {}).get(round_id, {}).get("by_channel", {}).get(channel_key, {})
        rows = []
        for uid, e in ch.items():
            m = self.members.get(str(uid)) or {}
            if not m.get("registered"):
                continue          # names/districts needed for the public list
            rows.append({"uid": uid, "name": m.get("name") or m.get("username") or "Player",
                         "district": m.get("district", ""), "state": m.get("state", ""),
                         "correct": e["correct"], "total": e["total"],
                         "points": m.get("points", 0), "first": e.get("first", ""),
                         "last": e.get("last", "")})
        # most correct, then fewest attempts, then who finished earliest
        rows.sort(key=lambda r: (-r["correct"], r["total"], r["last"]))
        return rows[:limit], len(ch)

    def render_round_top(self, round_id, channel_key, round_label="", cfg=None, limit=10):
        from . import districts as D
        rows, n_players = self.round_top(round_id, channel_key, limit)
        if not rows:
            return ""
        medals = ["🥇", "🥈", "🥉"] + [f"{i}." for i in range(4, limit + 1)]
        head = f"{cfg['emoji']} " if cfg else ""
        label = f"{round_label} " if round_label else ""
        lines = [f"{head}🏆 {label}Round — Top {len(rows)} · టాప్ {len(rows)}",
                 f"👥 {n_players} players · ఆడినవారు {n_players}", ""]
        dist_count = {}
        for i, r in enumerate(rows):
            d = r["district"]
            dte = D.telugu_name(d) if d else ""
            place = f" · {d} ({dte})" if d and dte and dte != d else (f" · {d}" if d else "")
            lines.append(f"{medals[i]} {r['name'][:24]}{place} — {r['correct']}/{r['total']} ✅ · ⭐{r['points']}")
            if d:
                dist_count[d] = dist_count.get(d, 0) + 1
        if dist_count:
            top_d = sorted(dist_count.items(), key=lambda kv: -kv[1])[:5]
            lines += ["", "📍 జిల్లాలు / Districts: " + " · ".join(f"{d} {n}" for d, n in top_d)]
        lines += ["", "మీ పేరు + జిల్లా ఇక్కడ రావాలంటే → bot లో /start, ఒక్కసారి register 📝",
                  "Your name & district here → /start in our bot, register once ✅"]
        return "\n".join(lines)


    # ------------------------------------------------------------ register flow
    def start_registration(self, uid, username=""):
        self.pending[str(uid)] = {"step": "name", "username": username}
        self.kv.save()

    def pending_step(self, uid):
        return self.pending.get(str(uid))

    def cancel_registration(self, uid):
        self.pending.pop(str(uid), None)
        self.kv.save()

    def registration_input(self, uid, text, default_exam=""):
        """
        One-time, 3-step registration (asked ONCE, never again):
            name -> district (TS/AP, typed or number) -> mobile (10 digits / skip)
        Exam target defaults to the channel the member came from (or TSPSC)
        and can be changed later with /exam. Returns (status, reply).
        """
        st = self.pending.get(str(uid))
        if not st:
            return None, None
        text = (text or "").strip()
        from . import districts as D
        if st["step"] == "name":
            if len(text) < 2 or len(text) > 60 or text.startswith("/"):
                return "ask_name", "Please send your real name (2–60 letters).\n⤷ మీ పూర్తి పేరు పంపండి:"
            st["name"] = text
            st["step"] = "district"
            self.kv.save()
            return "ask_district", (f"👍 {text}!\n\n📍 Step 2 of 3 — మీ జిల్లా? / Your district?\n"
                                    "Type the name (e.g. Warangal, Guntur, Hyderabad, Nellore) — TS or AP.\n"
                                    "⤷ జిల్లా పేరు టైప్ చేయండి (ఉదా: వరంగల్, గుంటూరు):")
        if st["step"] == "district":
            code, d = D.match_any_district(text)
            if not d:
                return "ask_district", ("❓ District not recognised. Send the number or name:\n\n"
                                        f"🟪 Telangana\n{D.district_list_text('TS')}\n\n"
                                        f"🟦 Andhra Pradesh\n{D.district_list_text('AP')}\n"
                                        "⤷ ఉదా: T12 / A5 / వరంగల్")
            st["state_code"], st["state"], st["district"] = code, D.STATES[code][0], d
            st["step"] = "mobile"
            self.kv.save()
            return "ask_mobile", (f"✅ {d} / {D.telugu_name(d)}\n\n📱 Step 3 of 3 — Mobile number (10 digits) "
                                  "for exam alerts & prizes. Send `skip` to skip.\n"
                                  "⤷ మొబైల్ నంబర్ పంపండి (లేదా skip):")
        if st["step"] == "mobile":
            digits = re.sub(r"\D", "", text)
            if text.lower() in ("skip", "no", "వద్దు", "-"):
                mobile = ""
            elif len(digits) == 12 and digits.startswith("91"):
                mobile = digits[2:]
            elif len(digits) == 10 and digits[0] in "6789":
                mobile = digits
            else:
                return "ask_mobile", "Send a valid 10-digit mobile (starts 6–9) or `skip`.\n⤷ సరైన నంబర్ లేదా skip పంపండి."
            exam = st.get("exam") or default_exam or "TSPSC"
            self.register(uid, name=st.get("name"), exam=exam, lang="Both",
                          username=st.get("username", ""),
                          state=st.get("state", ""), district=st.get("district", ""),
                          mobile=mobile, source="bot")
            self.pending.pop(str(uid), None)
            self.kv.save()
            return "done", ("🎉 Registration complete — +25 bonus points!\n"
                            "⤷ రిజిస్ట్రేషన్ పూర్తయింది. ఇక మళ్లీ అడగము ✅\n\n"
                            "Every round your name + district can appear in the channel Top-10 🏆\n"
                            "⤷ ప్రతి రౌండ్ తర్వాత Top-10 లో మీ పేరు, జిల్లా ఛానల్‌లో వస్తుంది!\n\n"
                            + self.render_profile(uid))
        return None, None

    def register_default_exam(self, uid, exam):
        st = self.pending.get(str(uid))
        if st is not None and exam:
            st["exam"] = exam
            self.kv.save()

    def set_exam(self, uid, exam):
        exam = self._match_exam(exam) if exam else None
        if not exam:
            return None
        m = self._get(uid)
        m["exam"] = exam
        self.kv.save()
        return exam

    @staticmethod
    def _match_exam(text):
        t = text.strip().lower()
        if t.isdigit() and 1 <= int(t) <= len(EXAM_TARGETS):
            return EXAM_TARGETS[int(t) - 1]
        for e in EXAM_TARGETS:
            if e.lower() in t or t in e.lower():
                return e
        # short codes
        codes = {"tspsc": "TSPSC", "appsc": "APPSC", "bank": "Banking", "ibps": "Banking",
                 "sbi": "Banking", "railway": "Railway", "rrb": "Railway",
                 "police": "Police", "constable": "Police", "si": "Police",
                 "defence": "Defence", "nda": "Defence", "army": "Defence",
                 "ssc": "SSC/UPSC", "upsc": "SSC/UPSC", "current": "Current Affairs GK",
                 "gk": "Current Affairs GK"}
        for k, v in codes.items():
            if k in t:
                return v
        return None

    @staticmethod
    def _match_lang(text):
        t = text.strip().lower()
        if t in ("1",):
            return "English"
        if t in ("2",):
            return "Telugu"
        if t in ("3", "both", "both (en + te)"):
            return "Both (EN + TE)"
        if "telugu" in t:
            return "Telugu"
        if "english" in t:
            return "English"
        if "both" in t:
            return "Both (EN + TE)"
        return None


if __name__ == "__main__":
    mb = Members()
    print(mb.render_leaderboard())
