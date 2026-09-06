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
        })

    def register(self, uid, name=None, exam=None, lang=None, username=""):
        m = self._get(uid)
        if name:
            m["name"] = name
        if username:
            m["username"] = username
        if exam:
            m["exam"] = exam
        if lang:
            m["lang"] = lang
        if not m["registered"]:
            m["registered"] = True
            m["registered_at"] = now_iso()
            m["points"] += 25  # registration bonus
        self.kv.save()
        return m

    # ------------------------------------------------------------ points
    def award_answer(self, uid, username="", correct=True):
        """Award points for a poll answer. Returns a dict describing the award."""
        m = self._get(uid)
        if username:
            m["username"] = username
        if not m["name"]:
            m["name"] = username or f"player{uid}"
        m["total"] += 1
        today = _day()
        yesterday = _day(datetime.now(config.IST) - timedelta(days=1))
        earned = 0
        events = []

        if m["last_active"] != today:
            earned += P_DAILY_FIRST            # daily participation bonus
            events.append(f"+{P_DAILY_FIRST} daily")
        m["last_active"] = today

        leveled_up = None
        if correct:
            m["correct"] += 1
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

        self.kv.save()
        return {"earned": earned, "events": events, "level_up": leveled_up,
                "points": m["points"], "streak": m["streak"]}

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
            "form_source": "google_form",
        }
        if tg_id:
            m = self.register(tg_id, name=base["name"] or None, exam=base["exam"] or None,
                              lang=base["lang"] or None, username=uname)
            for k in ("phone", "email", "state", "district", "stage", "coaching", "form_source"):
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
        for k in ("phone", "email", "state", "district", "stage", "coaching"):
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
        if lvl["next"]:
            lines.append(f"📈 {lvl['next'] - p['points']} points to next level")
        else:
            lines.append("👑 Maximum level reached — Champion!")
        lines.append("⤷ పాయింట్లు సంపాదించి ఛాంపియన్‌గా ఎదగండి! /quiz ఆడండి.")
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

    # ------------------------------------------------------------ register flow
    def start_registration(self, uid, username=""):
        self.pending[str(uid)] = {"step": "name", "username": username}
        self.kv.save()

    def pending_step(self, uid):
        return self.pending.get(str(uid))

    def cancel_registration(self, uid):
        self.pending.pop(str(uid), None)
        self.kv.save()

    def registration_input(self, uid, text):
        """
        Feed a free-text message during registration. Returns (status, reply).
        status: 'ask_exam' | 'ask_lang' | 'done'
        """
        st = self.pending.get(str(uid))
        if not st:
            return None, None
        text = (text or "").strip()
        if st["step"] == "name":
            st["name"] = text
            st["step"] = "exam"
            self.kv.save()
            exams = "\n".join(f"  {i+1}. {e}" for i, e in enumerate(EXAM_TARGETS))
            return "ask_exam", ("🎯 Choose your exam target — send the number or name:\n"
                                f"{exams}\n⤷ మీ పరీక్ష లక్ష్యాన్ని ఎంచుకోండి (నంబర్ పంపండి):")
        if st["step"] == "exam":
            exam = self._match_exam(text)
            if not exam:
                return "ask_exam", "Please send a valid exam number/name (e.g. 1 or TSPSC).\n⤷ సరైన నంబర్ పంపండి."
            st["exam"] = exam
            st["step"] = "lang"
            self.kv.save()
            langs = "\n".join(f"  {i+1}. {l}" for i, l in enumerate(LANGUAGES))
            return "ask_lang", ("🗣 Choose language — send number or name:\n"
                                f"{langs}\n⤷ భాష ఎంచుకోండి:")
        if st["step"] == "lang":
            lang = self._match_lang(text)
            if not lang:
                return "ask_lang", "Please send 1, 2 or 3 (English / Telugu / Both)."
            self.register(uid, name=st.get("name"), exam=st.get("exam"),
                          lang=lang, username=st.get("username", ""))
            self.pending.pop(str(uid), None)
            self.kv.save()
            p = self.profile(uid)
            return "done", ("✅ Registration complete! You earned +25 bonus points.\n\n"
                            + self.render_profile(uid))
        return None, None

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
