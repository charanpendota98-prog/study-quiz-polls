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


def norm_mobile(raw) -> str:
    """' +91 93944-83300 ' -> '9394483300' (or '' if not a valid 10-digit number)."""
    digits = re.sub(r"\D", "", str(raw or ""))
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) == 10 and digits[0] in "6789":
        return digits
    return ""


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


# Qualification options (button text EN / TE) -> stored code
QUALIFICATIONS = [
    ("SSC",    "10th / SSC",              "పదో తరగతి"),
    ("INTER",  "Intermediate / 10+2",     "ఇంటర్"),
    ("ITI",    "ITI / Diploma",           "ఐటీఐ / డిప్లొమా"),
    ("UG",     "Graduation (Degree/B.Tech)", "డిగ్రీ / బీటెక్"),
    ("PG",     "Post Graduation",         "పీజీ"),
    ("OTHER",  "Other / Studying",        "ఇతర / చదువుతున్నాను"),
]
QUAL_LABEL = {c: f"{en} / {te}" for c, en, te in QUALIFICATIONS}


def match_qualification(text):
    t = (text or "").strip().lower()
    if not t:
        return None
    if t.isdigit() and 1 <= int(t) <= len(QUALIFICATIONS):
        return QUALIFICATIONS[int(t) - 1][0]
    codes = {c.lower(): c for c, _, _ in QUALIFICATIONS}
    if t in codes:
        return codes[t]
    alias = {"10th": "SSC", "10": "SSC", "ssc": "SSC", "tenth": "SSC", "పదో": "SSC",
             "12": "INTER", "10+2": "INTER", "inter": "INTER", "intermediate": "INTER", "ఇంటర్": "INTER",
             "iti": "ITI", "diploma": "ITI", "polytechnic": "ITI",
             "degree": "UG", "graduation": "UG", "graduate": "UG", "b.tech": "UG", "btech": "UG",
             "bsc": "UG", "b.sc": "UG", "ba": "UG", "bcom": "UG", "b.com": "UG", "ug": "UG", "డిగ్రీ": "UG",
             "pg": "PG", "post graduation": "PG", "postgraduation": "PG", "mtech": "PG", "m.tech": "PG",
             "msc": "PG", "m.sc": "PG", "ma": "PG", "mba": "PG", "mca": "PG", "పీజీ": "PG",
             "other": "OTHER", "studying": "OTHER"}
    if t in alias:
        return alias[t]
    for k, v in sorted(alias.items(), key=lambda kv: -len(kv[0])):   # most specific first
        if len(k) > 2 and k in t:
            return v
    return None


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
        # 🚫 mobile numbers are unique: never overwrite/assign one that already
        # belongs to a different registered member (duplicate-account guard).
        mb = norm_mobile(extra.get("mobile") or extra.get("phone"))
        if mb:
            holder = self.find_by_mobile(mb)
            if holder and str(holder) != str(uid):
                extra = {k: v for k, v in extra.items() if k not in ("mobile", "phone")}
                extra["mobile_conflict_with"] = str(holder)
            else:
                extra["mobile"] = mb
                extra.pop("phone", None)
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
            # 🔓 release escrowed points earned before registering
            if m.get("locked_points"):
                m["unlocked_on_register"] = m["locked_points"]
                m["points"] += m.pop("locked_points")
            m["points"] += 25  # registration bonus
        self.kv.save()
        try:                       # mirror to Google Sheet CRM (no-op if not configured)
            from . import crm
            crm.push_member(uid, m, members_dict=self.members)
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
        # 14-day daily log for the weekly report card: day -> [answered, correct]
        dl = m.setdefault("daylog", {})
        rec = dl.setdefault(today, [0, 0])
        rec[0] += 1
        if correct:
            rec[1] += 1
        if len(dl) > 14:
            for k in sorted(dl)[:-14]:
                dl.pop(k, None)

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
            try:      # 🛡 shields every 7 days + 7/30/100 milestones (channel shout-out queued)
                from .hooks import on_daily_activity
                hk = on_daily_activity(m, today, yesterday)
                if hk.get("shield_earned"):
                    events.append("🛡 +1 streak shield")
                if hk.get("milestone"):
                    earned += 0
                    events.append(f"🔥 {hk['milestone']}-day milestone +{hk['bonus']}")
                    self.data.setdefault("shoutouts", []).append(
                        {"uid": str(uid), "streak": hk["milestone"], "ts": now_iso()})
            except Exception:
                pass
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

        # 🔒 Not registered yet → points go to escrow ("locked") and are
        # released the moment registration completes (see register()).
        locked = 0
        if not m.get("registered") and earned:
            m["points"] -= earned
            m["locked_points"] = m.get("locked_points", 0) + earned
            locked = m["locked_points"]
        self.kv.save()
        return {"earned": earned, "events": events, "level_up": leveled_up,
                "points": m["points"], "streak": m["streak"],
                "new_badges": new_badges, "locked": locked}

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
        if not has("round_top1") and m.get("round_wins", 0) >= 1:
            out.append({"id": "round_top1", "icon": "🥇", "en": "Round Winner", "te": "రౌండ్ విజేత"})
        if not has("round_top5") and m.get("round_wins", 0) >= 5:
            out.append({"id": "round_top5", "icon": "🏆", "en": "5× Round Winner", "te": "5 సార్లు విజేత"})
        if not has("district_king") and m.get("district_tops", 0) >= 3:
            out.append({"id": "district_king", "icon": "👑", "en": "District Topper ×3", "te": "జిల్లా టాపర్ ×3"})
        if not has("perfect") and m.get("perfect_rounds", 0) >= 1:
            out.append({"id": "perfect", "icon": "💎", "en": "Perfect Round 10/10", "te": "పర్ఫెక్ట్ రౌండ్"})
        if not has("referrer3") and m.get("referrals", 0) >= 3:
            out.append({"id": "referrer3", "icon": "🤝", "en": "Brought 3 Friends", "te": "3 ఫ్రెండ్స్ తెచ్చారు"})
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
        if p.get("qualification"):
            lines.append(f"🎓 {QUAL_LABEL.get(p['qualification'], p['qualification'])}")
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
            {"id": "beat_topper", "icon": "🥊"}, {"id": "defender", "icon": "🛡"},
        ]

    def is_registered(self, uid) -> bool:
        m = self.members.get(str(uid))
        return bool(m and m.get("registered"))

    # ------------------------------------------------------------ uniqueness
    def mobile_index(self) -> dict:
        """mobile -> uid for every member that has a valid mobile number."""
        idx = {}
        for uid, m in self.members.items():
            mb = norm_mobile(m.get("mobile"))
            if mb:
                idx[mb] = uid
        return idx

    def find_by_mobile(self, mobile):
        """uid of the member holding this mobile number, or None."""
        mb = norm_mobile(mobile)
        if not mb:
            return None
        return self.mobile_index().get(mb)

    def already_registered_text(self, uid) -> str:
        """Shown when a registered user triggers /register (or any re-ask):
        registration is strictly one-time — confirm the account instead."""
        m = self.members.get(str(uid)) or {}
        head = ("✅ మీరు ఇప్పటికే రిజిస్టర్ అయ్యారు — మళ్ళీ అవసరం లేదు (ఒక్కసారే, ఎప్పటికీ గుర్తు ఉంటుంది).\n"
                "⤷ You are already registered — one-time only, never asked again.\n")
        if m.get("mobile"):
            head += f"📱 మీ నంబర్: {m['mobile']} · మార్చాలంటే staff కి చెప్పండి.\n"
        return head + "\n" + self.render_profile(uid)

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
                acc = round(100 * m.get("correct", 0) / m["total"]) if m.get("total") else 0
                lines.append(f"{r} {m.get('name') or 'player'} — ⭐{m.get('points',0)} · {lvl['title_en']} · 🎯{acc}%")
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
            if correct:
                e.setdefault("right", []).append(qid)
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
        dor = self.district_of_round(round_id, channel_key)
        if dor:
            lines.append(f"👑 District of the round: {dor['district']} ({D.telugu_name(dor['district'])}) — "
                         f"{dor['avg']}% avg · {dor['players']} players")
        top_d = sorted(dist_count.items(), key=lambda kv: -kv[1])
        if len(top_d) >= 2 and top_d[0][1] == top_d[1][1] and top_d[0][1] >= 2:
            lines.append(f"⚔️ Rivalry: {top_d[0][0]} vs {top_d[1][0]} — tied! రేపు తేలుద్దాం.")
        lines += ["", "మీ పేరు + జిల్లా ఇక్కడ రావాలంటే → bot లో /start, ఒక్కసారి register 📝",
                  "Your name & district here → /start in our bot, register once ✅"]
        return "\n".join(lines)


    # ------------------------------------------------------------ advanced round intel
    def round_question_stats(self, round_id, channel_key):
        """{qid: {correct,total}} from DM-mirror answers (needs per-answer log)."""
        out = {}
        ch = self.data.get("rounds", {}).get(round_id, {}).get("by_channel", {}).get(channel_key, {})
        for e in ch.values():
            for qid in e.get("qids", []):
                st = out.setdefault(qid, {"correct": 0, "total": 0})
                st["total"] += 1
            for qid in e.get("right", []):
                out.setdefault(qid, {"correct": 0, "total": 0})["correct"] += 1
        return out

    def round_players(self, round_id, channel_key):
        return self.data.get("rounds", {}).get(round_id, {}).get("by_channel", {}).get(channel_key, {})

    def personal_round_card(self, uid, round_id, channel_key, round_label=""):
        """Private DM report after a round: score, rank, district rank, percentile,
        streak, next-level distance — the 'why I come back tomorrow' message."""
        from . import districts as D
        players = self.round_players(round_id, channel_key)
        e = players.get(str(uid))
        m = self.members.get(str(uid))
        if not e or not m:
            return ""
        rows, n = self.round_top(round_id, channel_key, limit=10_000)
        rank = next((i + 1 for i, r in enumerate(rows) if str(r["uid"]) == str(uid)), None)
        pct = round(100 * (1 - (rank - 1) / max(n, 1))) if rank else 0
        d = m.get("district", "")
        d_rows = [r for r in rows if r["district"] == d] if d else []
        d_rank = next((i + 1 for i, r in enumerate(d_rows) if str(r["uid"]) == str(uid)), None)
        lvl = level_for(m.get("points", 0))
        nxt = next((t for t, *_ in LEVELS if t > m.get("points", 0)), None)
        label = f"{round_label} " if round_label else ""
        score = f"{e['correct']}/{e['total']}"
        mood = ("🔥 Outstanding!" if e["total"] and e["correct"] / e["total"] >= 0.9 else
                "👏 Strong round" if e["total"] and e["correct"] / e["total"] >= 0.7 else
                "💪 Keep going — PYQ practice pays")
        lines = [f"📊 {label}Round card — {m.get('name') or 'you'}",
                 f"✅ Score {score} · {mood}",
                 f"🏅 Rank #{rank} of {n} players (top {max(100 - pct, 1)}%)"]
        if d and d_rank:
            lines.append(f"📍 {d} ({D.telugu_name(d)}) rank: #{d_rank} of {len(d_rows)}")
            if d_rank == 1 and len(d_rows) > 1:
                lines.append(f"👑 మీ జిల్లాలో మీరే టాపర్! You topped {d}!")
        lines.append(f"⭐ Points {m.get('points', 0)} · {lvl['icon']} {lvl['title_en']}"
                     + (f" · next level in {nxt - m.get('points', 0)} pts" if nxt else " · MAX level"))
        if m.get("streak", 0) >= 2:
            lines.append(f"🔥 Streak {m['streak']} days — రేపు కూడా ఆడితే {m['streak'] + 1}!")
        else:
            lines.append("🔥 Play again tomorrow to start a streak (+bonus points)")
        weak = self._weak_topics(m)
        if weak:
            lines.append("🎯 Focus: " + ", ".join(t.title() for t in weak[:3]) + " → /review")
        lines.append(self.render_hall_of_fame_card(uid))
        lines.append("Invite friends: /invite · District board: /district")
        return "\n".join(lines)

    def _weak_topics(self, m, min_total=2):
        rows = [(t, v) for t, v in (m.get("topics") or {}).items() if v.get("total", 0) >= min_total]
        rows.sort(key=lambda kv: (kv[1]["correct"] / max(kv[1]["total"], 1), -kv[1]["total"]))
        return [t for t, v in rows if v["correct"] / max(v["total"], 1) < 0.6][:5]

    def district_of_round(self, round_id, channel_key, min_players=2):
        """District with the best average score this round (>= min_players)."""
        rows, _ = self.round_top(round_id, channel_key, limit=10_000)
        agg = {}
        for r in rows:
            if not r["district"]:
                continue
            a = agg.setdefault(r["district"], [0, 0, 0])
            a[0] += r["correct"]; a[1] += r["total"]; a[2] += 1
        best = [(d, c / max(t, 1), n) for d, (c, t, n) in agg.items() if n >= min_players]
        if not best:
            return None
        best.sort(key=lambda x: (-x[1], -x[2]))
        d, avg, n = best[0]
        return {"district": d, "avg": round(100 * avg), "players": n}

    def daily_champions(self, day=None, limit=10):
        """Aggregate all rounds of a day → top scorers with district."""
        day = day or _day()
        agg = {}
        for rid, r in self.data.get("rounds", {}).items():
            if not rid.startswith(day.replace("-", "")):
                continue
            for ch, players in r.get("by_channel", {}).items():
                for uid, e in players.items():
                    a = agg.setdefault(uid, [0, 0, 0])
                    a[0] += e["correct"]; a[1] += e["total"]; a[2] += 1
        rows = []
        for uid, (c, t, rounds) in agg.items():
            m = self.members.get(str(uid)) or {}
            if not m.get("registered"):
                continue
            rows.append({"uid": uid, "name": m.get("name") or "Player", "district": m.get("district", ""),
                         "correct": c, "total": t, "rounds": rounds, "points": m.get("points", 0)})
        rows.sort(key=lambda r: (-r["correct"], r["total"]))
        return rows[:limit], len(agg)

    def render_daily_champions(self, day=None):
        from . import districts as D
        rows, n = self.daily_champions(day)
        if not rows:
            return ""
        medals = ["🥇", "🥈", "🥉"] + [f"{i}." for i in range(4, 11)]
        lines = [f"🌟 Today's Champions — ఈరోజు ఛాంపియన్స్ ({(day or _day())})",
                 f"👥 {n} players across all rounds", ""]
        for i, r in enumerate(rows):
            d = f" · {r['district']} ({D.telugu_name(r['district'])})" if r["district"] else ""
            lines.append(f"{medals[i]} {r['name'][:24]}{d} — {r['correct']}/{r['total']} · {r['rounds']} rounds")
        lines += ["", "రేపు మీ పేరు ఇక్కడ ఉండాలంటే — ప్రతి రౌండ్ ఆడండి 🔥",
                  "Register once in our bot: /start ✅"]
        return "\n".join(lines)

    def weekly_district_cup(self, limit=10):
        """District championship: sum of correct answers in last 7 days, with
        per-player average so big districts don't automatically win."""
        from . import districts as D
        from datetime import timedelta
        since = (datetime.now(config.IST) - timedelta(days=7)).strftime("%Y%m%d")
        agg = {}
        for rid, r in self.data.get("rounds", {}).items():
            if rid[:8] < since:
                continue
            for ch, players in r.get("by_channel", {}).items():
                for uid, e in players.items():
                    m = self.members.get(str(uid)) or {}
                    d = m.get("district")
                    if not d:
                        continue
                    a = agg.setdefault(d, {"correct": 0, "total": 0, "players": set()})
                    a["correct"] += e["correct"]; a["total"] += e["total"]; a["players"].add(uid)
        rows = [(d, a["correct"], a["total"], len(a["players"])) for d, a in agg.items()]
        rows.sort(key=lambda x: (-x[1], -x[3]))
        if not rows:
            return ""
        lines = ["🏆 District Cup — వారపు జిల్లా ఛాంపియన్‌షిప్", ""]
        medals = ["🥇", "🥈", "🥉"] + [f"{i}." for i in range(4, limit + 1)]
        for i, (d, c, t, n) in enumerate(rows[:limit]):
            acc = round(100 * c / max(t, 1))
            lines.append(f"{medals[i]} {d} ({D.telugu_name(d)}) — {c} ✅ · {n} players · {acc}% acc")
        lines += ["", "మీ జిల్లా ఎక్కడ? ఫ్రెండ్స్‌ని పిలవండి 👉 /invite",
                  "Where is your district? Bring friends — register once in our bot ✅"]
        return "\n".join(lines)

    def streak_at_risk(self):
        """Members who played yesterday but not today (for evening nudge)."""
        from datetime import timedelta
        today = _day()
        yday = _day(datetime.now(config.IST) - timedelta(days=1))
        return [uid for uid, m in self.members.items()
                if m.get("registered") and not m.get("dm_blocked")
                and m.get("last_active") == yday and m.get("streak", 0) >= 2]

    def add_referral(self, new_uid, ref_uid):
        """+20 pts to the referrer when a NEW member registers via their link."""
        if str(new_uid) == str(ref_uid) or str(ref_uid) not in self.members:
            return False
        m = self._get(new_uid)
        if m.get("referred_by"):
            return False
        m["referred_by"] = str(ref_uid)
        r = self._get(ref_uid)
        r["referrals"] = r.get("referrals", 0) + 1
        r["points"] = r.get("points", 0) + 20
        self.kv.save()
        return True

    # ------------------------------------------------------------ hall of fame
    def settle_round(self, round_id, channel_key):
        """Called once after a round: record wins / district tops / perfect
        rounds on member profiles (feeds badges + monthly hall of fame) and
        award round-place bonus points (🥇+30 🥈+20 🥉+10, district top +10)."""
        rows, n = self.round_top(round_id, channel_key, limit=10_000)
        if not rows:
            return {}
        awarded = {}
        seen_d = set()
        for i, r in enumerate(rows):
            m = self._get(r["uid"])
            bonus = 0
            if i == 0 and n >= 3:
                m["round_wins"] = m.get("round_wins", 0) + 1
                bonus += 30
            elif i == 1 and n >= 3:
                bonus += 20
            elif i == 2 and n >= 3:
                bonus += 10
            if r["district"] and r["district"] not in seen_d:
                seen_d.add(r["district"])
                if sum(1 for x in rows if x["district"] == r["district"]) >= 2:
                    m["district_tops"] = m.get("district_tops", 0) + 1
                    bonus += 10
            if r["total"] >= 8 and r["correct"] == r["total"]:
                m["perfect_rounds"] = m.get("perfect_rounds", 0) + 1
            if bonus:
                m["points"] = m.get("points", 0) + bonus
                awarded[str(r["uid"])] = bonus
            for b in self._earned_badges(m):
                m.setdefault("badges", []).append(b["id"])
        hist = self.data.setdefault("round_history", [])
        hist.append({"round_id": round_id, "channel": channel_key, "players": n,
                     "winner": rows[0]["name"], "district": rows[0]["district"]})
        del hist[:-500]
        self.kv.save()
        return awarded

    def monthly_hall_of_fame(self, limit=10):
        from . import districts as D
        month = datetime.now(config.IST).strftime("%Y%m")
        agg = {}
        for rid, r in self.data.get("rounds", {}).items():
            if not rid.startswith(month):
                continue
            for ch, players in r.get("by_channel", {}).items():
                for uid, e in players.items():
                    a = agg.setdefault(uid, [0, 0, 0])
                    a[0] += e["correct"]; a[1] += e["total"]; a[2] += 1
        rows = []
        for uid, (c, t, rn) in agg.items():
            m = self.members.get(str(uid)) or {}
            if m.get("registered"):
                rows.append((m.get("name") or "Player", m.get("district", ""), c, t, rn, m.get("round_wins", 0)))
        rows.sort(key=lambda x: (-x[2], x[3]))
        if not rows:
            return ""
        lines = [f"🏛 Hall of Fame — {datetime.now(config.IST):%B %Y}", ""]
        medals = ["🥇", "🥈", "🥉"] + [f"{i}." for i in range(4, limit + 1)]
        for i, (nm, d, c, t, rn, w) in enumerate(rows[:limit]):
            dd = f" · {d} ({D.telugu_name(d)})" if d else ""
            lines.append(f"{medals[i]} {nm[:24]}{dd} — {c} ✅ / {rn} rounds · 🥇×{w}")
        lines += ["", "Consistency wins — రోజూ ఆడినవారే ఇక్కడ ఉంటారు 🔥"]
        return "\n".join(lines)

    def render_hall_of_fame_card(self, uid):
        m = self.members.get(str(uid)) or {}
        return (f"🥇 Round wins: {m.get('round_wins', 0)} · 👑 District tops: {m.get('district_tops', 0)} · "
                f"💎 Perfect rounds: {m.get('perfect_rounds', 0)} · 🤝 Referrals: {m.get('referrals', 0)}")

    # ------------------------------------------------------------ register flow
    def start_registration(self, uid, username="", quick=None):
        """quick={'state_code','state','district','qualification','exam'} → only name + mobile asked.

        Registration is ONE-TIME: already-registered members are never asked
        again (returns False, no pending state created). An in-progress form is
        kept as-is so progress isn't lost. Returns True when a form is active.
        """
        if self.is_registered(uid):
            return False
        st = self.pending.get(str(uid))
        if st and not quick:
            return True          # already filling the form — don't reset progress
        st = {"step": "name", "username": username}
        if quick:
            st.update({k: v for k, v in quick.items() if v}); st["quick"] = True
        self.pending[str(uid)] = st
        self.kv.save()
        return True

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
            if st.get("quick") and st.get("district"):
                st["step"] = "qualification"
                self.kv.save()
                return "ask_qualification", (f"👍 {text}!\n\n🎓 Step 2 of 3 — మీరు చదువుతున్నది? / Your course\nTap a button below ⬇️")
            st["step"] = "state"
            self.kv.save()
            return "ask_state", (f"👍 {text}!\n\n🗺 Step 2 of 5 — మీ రాష్ట్రం? / Your state?\n"
                                 "Tap a button below ⬇️")
        if st["step"] == "state":
            code = D.match_state(text)
            if code not in ("TS", "AP"):
                if code == "OTHER":
                    st["state_code"], st["state"], st["district"] = "OTHER", "Other", ""
                    st["step"] = "qualification"
                    self.kv.save()
                    return "ask_qualification", ("✅ Other state\n\n🎓 Step 4 of 5 — Highest qualification / అర్హత\n"
                                                 "Tap a button below ⬇️")
                return "ask_state", "Please tap Telangana or Andhra Pradesh.\n⤷ బటన్ నొక్కండి."
            st["state_code"], st["state"] = code, D.STATES[code][0]
            st["step"] = "district"
            self.kv.save()
            return "ask_district", (f"✅ {D.STATES[code][0]} / {D.STATES[code][1]}\n\n"
                                    f"📍 Step 3 of 5 — మీ జిల్లా? / Your district?\n"
                                    "Tap your district below (A → Z) or type its name ⬇️")
        if st["step"] == "district":
            code = st.get("state_code", "")
            d = D.match_district(code, text) if code in ("TS", "AP") else None
            if not d:
                return "ask_district", ("❓ District not found — tap a button below or type the name.\n"
                                        "⤷ కింద బటన్ నొక్కండి లేదా జిల్లా పేరు టైప్ చేయండి.")
            st["district"] = d
            st["step"] = "qualification"
            self.kv.save()
            return "ask_qualification", (f"✅ {d} / {D.telugu_name(d)}\n\n🎓 Step 4 of 5 — Highest qualification / అర్హత\n"
                                         "Tap a button below ⬇️")
        if st["step"] == "qualification":
            q = match_qualification(text)
            if not q:
                return "ask_qualification", ("❓ Please tap a button or send 1–6.\n⤷ బటన్ నొక్కండి లేదా 1–6 పంపండి.")
            st["qualification"] = q
            st["step"] = "mobile"
            self.kv.save()
            return "ask_mobile", (f"✅ {QUAL_LABEL[q]}\n\n📱 Step {'3 of 3' if st.get('quick') else '5 of 5'} — Mobile number (10 digits) "
                                  "for exam alerts & prizes. Send `skip` to skip.\n"
                                  "⤷ మొబైల్ నంబర్ పంపండి (లేదా skip):")
        if st["step"] == "mobile":
            if text.lower() in ("skip", "no", "వద్దు", "-"):
                mobile = ""
            else:
                mobile = norm_mobile(text)
                if not mobile:
                    return "ask_mobile", "Send a valid 10-digit mobile (starts 6–9) or `skip`.\n⤷ సరైన నంబర్ లేదా skip పంపండి."
            # 🚫 duplicate guard — one mobile = one account, one person = one entry
            if mobile:
                holder = self.find_by_mobile(mobile)
                if holder and str(holder) != str(uid):
                    hm = self.members.get(str(holder)) or {}
                    st["last_dup"] = {"mobile": mobile, "holder": str(holder),
                                      "name": hm.get("name", ""), "district": hm.get("district", ""),
                                      "ts": now_iso()}
                    self.kv.save()
                    return "duplicate", (
                        f"⚠️ ఈ నంబర్ ({mobile}) ఇప్పటికే రిజిస్టర్ అయింది — "
                        f"{hm.get('name') or 'player'} · {hm.get('district') or '—'}.\n"
                        "ఒక్కరికి ఒకటే అకౌంట్ — అది మీదే అయితే అదే అకౌంట్ వాడండి (లేదా staff కి చెప్పండి).\n"
                        "వేరే నంబర్ ఉంటే పంపండి, లేకపోతే `skip` పంపండి.\n\n"
                        f"⤷ This number is already registered ({hm.get('name') or 'player'} · "
                        f"{hm.get('district') or '—'}). One person = one account only.\n"
                        "Send a different number, or `skip`.")
            exam = st.get("exam") or default_exam or "TSPSC"
            self.register(uid, name=st.get("name"), exam=exam, lang="Both",
                          username=st.get("username", ""),
                          state=st.get("state", ""), district=st.get("district", ""),
                          qualification=st.get("qualification", ""), mobile=mobile, source="bot")
            self.pending.pop(str(uid), None)
            self.kv.save()
            unlocked = (self.members.get(str(uid)) or {}).get("unlocked_on_register", 0)
            unlock_line = (f"🔓 {unlocked} locked points released!\n⤷ లాక్ అయిన {unlocked} పాయింట్లు విడుదల!\n" if unlocked else "")
            return "done", (unlock_line + "🎉 Registration complete — +25 bonus points!\n"
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
