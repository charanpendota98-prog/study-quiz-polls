#!/usr/bin/env python3
"""
STUDENTUP — LEADERBOARD & STREAK ENGINE
Tracks poll answers per user (works in group chats / via bot-private quizzes),
maintains daily streaks, and builds a weekly top-10 leaderboard.
Channel polls are anonymous by Telegram design (no per-user data) — this engine
powers (a) non-anonymous quiz posts in study groups and (b) the bot DM leaderboard.
Pure JSON stores, atomic writes.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from . import config
from .store import KV, now_iso, load_json


def _week_key(dt=None):
    dt = dt or datetime.now(config.IST)
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _day_key(dt=None):
    return (dt or datetime.now(config.IST)).strftime("%Y-%m-%d")


class Leaderboard:
    def __init__(self):
        self.kv = KV(config.STORE_LEADERBOARD, default={
            "users": {}, "polls": {}, "weeks": {}})
        self.users = self.kv.data.setdefault("users", {})
        self.polls = self.kv.data.setdefault("polls", {})
        self.weeks = self.kv.data.setdefault("weeks", {})

    # ------------------------------------------------------------- register
    def register_poll(self, poll_id, answer_index, channel, qid):
        self.polls[str(poll_id)] = {
            "answer": answer_index, "channel": channel, "qid": qid,
            "day": _day_key(), "week": _week_key(),
        }
        self.kv.save()

    def record_poll_totals(self, poll_obj: dict):
        """`poll` update from Telegram (channel polls are anonymous but the
        aggregate votes per option are public) → correct/total per question."""
        pid = str(poll_obj.get("id"))
        poll = self.polls.get(pid)
        if not poll:
            return
        opts = poll_obj.get("options") or []
        total = sum(int(o.get("voter_count", 0)) for o in opts)
        idx = int(poll.get("answer", -1))
        correct = int(opts[idx].get("voter_count", 0)) if 0 <= idx < len(opts) else 0
        if total and total >= poll.get("total", 0):
            poll["total"], poll["correct"] = total, correct
            self.kv.save()

    def record_answer(self, poll_id, user_id, user_name, chosen_index):
        poll = self.polls.get(str(poll_id))
        if not poll:
            return None
        correct = int(poll["answer"]) == int(chosen_index)
        poll["total"] = poll.get("total", 0) + 1
        poll["correct"] = poll.get("correct", 0) + (1 if correct else 0)
        u = self.users.setdefault(str(user_id), {
            "name": user_name or f"user{user_id}", "total": 0, "correct": 0,
            "streak": 0, "last_day": "", "best_streak": 0})
        u["name"] = user_name or u["name"]
        u["total"] += 1
        today = _day_key()
        if correct:
            u["correct"] += 1
            if u["last_day"] != today:
                yesterday = (datetime.now(config.IST) - timedelta(days=1)).strftime("%Y-%m-%d")
                u["streak"] = u["streak"] + 1 if u["last_day"] in (yesterday, today) else 1
                u["best_streak"] = max(u["best_streak"], u["streak"])
            u["last_day"] = today
        # weekly aggregate
        wk = self.weeks.setdefault(poll["week"], {})
        w = wk.setdefault(str(user_id), {"name": u["name"], "correct": 0, "total": 0})
        w["total"] += 1
        w["correct"] += 1 if correct else 0
        w["name"] = u["name"]
        self.kv.save()
        return correct

    # ------------------------------------------------------------- queries
    def stats_by_qid(self, qids):
        """Best-effort per-question vote stats {qid: {correct,total}}."""
        out = {}
        for pid, meta in self.polls.items():
            qid = meta.get("qid")
            if qid in qids and meta.get("total"):
                out[qid] = {"correct": meta.get("correct", 0), "total": meta.get("total", 0)}
        return out

    def user_card(self, user_id):
        u = self.users.get(str(user_id))
        if not u:
            return None
        acc = round(100 * u["correct"] / u["total"], 1) if u["total"] else 0.0
        return {"name": u["name"], "total": u["total"], "correct": u["correct"],
                "accuracy": acc, "streak": u["streak"], "best_streak": u["best_streak"]}

    def weekly_top(self, week=None, limit=10):
        week = week or _week_key()
        wk = self.weeks.get(week, {})
        rows = [{"uid": uid, **v} for uid, v in wk.items() if v["total"] > 0]
        rows.sort(key=lambda r: (r["correct"], r["total"]), reverse=True)
        return rows[:limit]

    def render_weekly(self, week=None):
        top = self.weekly_top(week)
        if not top:
            return ("🏆 Weekly Leaderboard\nఈ వారం ఇంకా స్కోర్లు లేవు — మొదటి క్విజ్ రాయండి!\n"
                    "(No scores yet this week — answer the first quiz!)")
        medals = ["🥇", "🥈", "🥉"]
        lines = ["🏆 Weekly Leaderboard • వారపు ర్యాంకింగ్", ""]
        for i, r in enumerate(top):
            medal = medals[i] if i < 3 else f"{i+1}."
            lines.append(f"{medal} {r['name']} — {r['correct']}/{r['total']} ✅")
        lines.append("")
        lines.append("Keep your streak going! 🔥 | స్ట్రీక్ కొనసాగించండి!")
        return "\n".join(lines)

    def render_user(self, user_id):
        c = self.user_card(user_id)
        if not c:
            return ("You haven't answered yet. Answer a quiz to start your streak! 🔥\n"
                    "మీరింకా సమాధానం ఇవ్వలేదు — క్విజ్ రాసి స్ట్రీక్ ప్రారంభించండి!")
        return (f"📊 {c['name']} — Your Stats\n"
                f"✅ Correct: {c['correct']}/{c['total']} ({c['accuracy']}%)\n"
                f"🔥 Current streak: {c['streak']} day(s) | Best: {c['best_streak']}\n"
                f"⤷ సరైనవి: {c['correct']}/{c['total']} ({c['accuracy']}%) | స్ట్రీక్: {c['streak']} రోజులు")


if __name__ == "__main__":
    lb = Leaderboard()
    print(lb.render_weekly())
