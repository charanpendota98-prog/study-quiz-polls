#!/usr/bin/env python3
"""
STUDENTUP — POSTING ENGINE (the brain)
Runs a quiz slot, reminders, morning greeting, study tip, CA digest, and jobs
update across the 7 public channels + 1 private jobs channel.
Every public channel gets bilingual (EN + Telugu) native quiz polls with
instant right/wrong feedback and an explanation.
"""
from __future__ import annotations

import random
import json
from datetime import datetime

from . import config
from .telegram import Telegram, TelegramError
from .question_bank import Bank
from .content import (build_question_text, build_options, build_explanation,
                      build_answer_key)
from .leaderboard import Leaderboard
from .members import Members
from .store import load_json


WEEKDAYS_TE = ["సోమవారం", "మంగళవారం", "బుధవారం", "గురువారం", "శుక్రవారం", "శనివారం", "ఆదివారం"]


class Engine:
    def __init__(self, dry=False):
        self.tg = Telegram(dry=dry)
        self.bank = Bank()
        self.lb = Leaderboard()
        self.members = Members()
        self.dry = dry
        self._ensure_filled()

    def _ensure_filled(self):
        """Top-up any channel that has fewer than one slot of unused questions."""
        stats = self.bank.stats()
        if any(stats[ch]["unused"] < config.POLLS_PER_SLOT for ch in config.PUBLIC_CHANNELS):
            try:
                from .generator import top_up
                added, errs = top_up(per_channel_min=config.FILLER_TRIGGER_UNUSED)
                if added:
                    print(f"   [filler] auto top-up: {len(added)} new questions "
                          f"({len(errs)} rejected)")
                    self.bank = Bank()  # reload
            except Exception as e:
                print(f"   [filler] top-up note: {e}")

    # ------------------------------------------------------------- quizzes
    def send_quiz(self, channel_key, q):
        cfg = config.CHANNELS[channel_key]
        chat = config.channel_chat_id(channel_key)
        tf = bool(getattr(config, "TELUGU_FIRST", True))
        text = build_question_text(q, cfg, telugu_first=tf)
        opts = build_options(q, telugu_first=tf)
        expl = build_explanation(q, telugu_first=tf)
        # Instant = show explanation with poll; delayed = withhold for answer-key post
        instant = getattr(config, "ANSWER_MODE", "instant") != "delayed"
        try:
            res = self.tg.send_quiz(
                chat, text, opts, q["answer_index"], expl,
                open_period=getattr(config, "QUIZ_OPEN_PERIOD", 300),
                with_explanation=instant,
            )
            poll = res.get("result", {}).get("poll") or {}
            poll_id = poll.get("id")
            if poll_id:
                self.lb.register_poll(poll_id, q["answer_index"], channel_key, q["id"])
            return True
        except TelegramError as e:
            print(f"   [quiz] {channel_key} {q['id']} FAILED: {e}")
            return False

    def run_quiz_slot(self, slot=None, channels=None, round_label=""):
        channels = channels or config.PUBLIC_CHANNELS
        total = 0
        label = f"{round_label} " if round_label else ""
        # Track this round's questions so a delayed answer-key can be posted later.
        self._last_round = {"label": round_label or "", "by_channel": {}}
        delayed = getattr(config, "ANSWER_MODE", "instant") == "delayed"
        for ch in channels:
            qs = self.bank.pick(ch, config.POLLS_PER_SLOT)
            if not qs:
                print(f"   [slot] {ch}: no questions available")
                continue
            self._last_round["by_channel"][ch] = qs
            cfg = config.CHANNELS[ch]
            n_pyq = sum(1 for q in qs if q.get("source") == "pyq")
            mode_note = ("సమాధానాలు రౌండ్ తర్వాత — answer key after round 🔑"
                         if delayed else
                         "సరైన/తప్పు వెంటనే — instant ✅/❌ feedback")
            # slot opener (Telugu-first)
            opener = (f"{cfg['emoji']} {label}{cfg['subject']} — Quiz Round!\n"
                      f"📝 {len(qs)} ప్రశ్నలు — వాటిలో {n_pyq} PYQ (మునుపటి ప్రశ్నపత్రాలు).\n"
                      f"{len(qs)} questions — including {n_pyq} previous-paper (PYQ).\n"
                      f"{mode_note}\n"
                      f"Play in our bot group with /quiz to earn points & ranks! ⭐")
            try:
                self.tg.send_message(config.channel_chat_id(ch), opener)
            except TelegramError as e:
                print(f"   [slot] {ch} opener failed: {e}")
            for i, q in enumerate(qs, 1):
                ok = self.send_quiz(ch, q)
                total += 1 if ok else 0
                if i < len(qs):
                    self.tg.polite_gap(not self.dry)
            # completion message
            if delayed:
                done = (f"🎌 Round complete! {len(qs)} questions done.\n"
                        f"🔑 Answer key posts shortly — సమాధానాలు కాసేపట్లో.\n"
                        f"10/10 కొట్టినవారు కామెంట్‌లో 👇 రాయండి!\n"
                        f"Points & ranks: /register in our quiz bot ⭐")
            else:
                done = (f"🎌 Round complete! {len(qs)} questions done.\n"
                        f"10/10 కొట్టినవారు కామెంట్‌లో 👇 రాయండి!\n"
                        f"Want points, ranks & streaks? Register with /register in our quiz bot ⭐\n"
                        f"Next round: see the daily schedule. Keep your streak 🔥")
            try:
                self.tg.send_message(config.channel_chat_id(ch), done)
            except TelegramError as e:
                print(f"   [slot] {ch} closer failed: {e}")
            self.tg.polite_gap(not self.dry)
        # Persist last-round snapshot for the delayed answer-key job
        try:
            from .store import save_json_atomic
            snap = {
                "label": self._last_round.get("label", ""),
                "by_channel": {
                    ch: [{"id": q.get("id"), "topic": q.get("topic"),
                          "answer_index": q.get("answer_index"),
                          "options_en": q.get("options_en"),
                          "options_te": q.get("options_te"),
                          "explanation_en": q.get("explanation_en"),
                          "explanation_te": q.get("explanation_te")}
                         for q in qs]
                    for ch, qs in self._last_round.get("by_channel", {}).items()
                },
            }
            save_json_atomic(config.DATA / "last_round.json", snap)
        except Exception as e:
            print(f"   [slot] last_round save note: {e}")
        print(f"[slot] posted {total} polls across {len(channels)} channels "
              f"(mode={getattr(config, 'ANSWER_MODE', 'instant')})")
        return total

    def post_answer_key(self, round_label: str = "", channels=None):
        """Post the delayed bilingual answer key (no-op when ANSWER_MODE=instant)."""
        if getattr(config, "ANSWER_MODE", "instant") != "delayed":
            print("[answer_key] skipped (ANSWER_MODE=instant — keys already on polls)")
            return 0
        channels = channels or config.PUBLIC_CHANNELS
        snap = {}
        try:
            snap = load_json(config.DATA / "last_round.json", {})
        except Exception:
            snap = getattr(self, "_last_round", {}) or {}
        by_ch = snap.get("by_channel") or {}
        label = round_label or snap.get("label") or ""
        posted = 0
        for ch in channels:
            qs = by_ch.get(ch) or []
            if not qs:
                continue
            text = build_answer_key(qs, round_label=label)
            try:
                self.tg.send_message(config.channel_chat_id(ch), text)
                posted += 1
            except TelegramError as e:
                print(f"   [answer_key] {ch} failed: {e}")
            self.tg.polite_gap(not self.dry)
        print(f"[answer_key] posted to {posted} channels")
        return posted

    # ------------------------------------------------------------ morning
    def morning(self):
        now = datetime.now(config.IST)
        wd = WEEKDAYS_TE[now.weekday()]
        sched = ("⛅ 07:30 — Morning quiz round\n🌙 19:30 — Evening quiz round\n"
                 "14:30 — Study tip | 21:30 — Current Affairs digest\n"
                 "💼 Jobs updates every 30 min")
        for ch in config.PUBLIC_CHANNELS:
            cfg = config.CHANNELS[ch]
            msg = (f"{cfg['emoji']} శుభోదయం! Good morning, aspirants!\n"
                   f"Today is {now.strftime('%A')} / {wd} ({now.strftime('%d %b %Y')}).\n\n"
                   f"📅 Today's schedule — నేటి షెడ్యూల్:\n{sched}\n\n"
                   f"Consistency wins. Let's go! 💪")
            try:
                self.tg.send_message(config.channel_chat_id(ch), msg)
            except TelegramError as e:
                print(f"   [morning] {ch} failed: {e}")
            self.tg.polite_gap(not self.dry)
        print("[morning] greeting sent to all public channels")

    # --------------------------------------------------------------- tips
    def tip(self):
        tips = load_json(config.TIPS_JSON, {"tips": []}).get("tips", [])
        if not tips:
            return
        t = random.choice(tips)
        for ch in config.PUBLIC_CHANNELS:
            cfg = config.CHANNELS[ch]
            msg = f"💡 {cfg['subject']} — Study Tip\n{t['en']}\n⤷ {t['te']}"
            try:
                self.tg.send_message(config.channel_chat_id(ch), msg)
            except TelegramError as e:
                print(f"   [tip] {ch} failed: {e}")
            self.tg.polite_gap(not self.dry)
        print("[tip] study tip sent")

    # ------------------------------------------------------- collector
    def collect_exam_content(self):
        """Daily scrape of exam-prep websites/apps -> bank (see core.collector)."""
        try:
            from .collector import collect_daily, retry_pending
            stats = collect_daily()
            retry_pending()
            return stats
        except Exception as e:
            print(f"   [collect] error (non-fatal): {e}")
            return {"accepted": 0, "error": str(e)}

    # ----------------------------------------------------------- coach
    def coach_lesson(self, channel=None):
        """Post a friendly expert reasoning/aptitude coaching trick."""
        lessons = load_json(config.DATA / "coach_lessons.json",
                            {"lessons": []}).get("lessons", [])
        if not lessons:
            return None
        # pick a lesson matching the channel if possible, else random
        pool = [l for l in lessons if l.get("channel") == channel] if channel else lessons
        lesson = random.choice(pool or lessons)
        msg = f"{lesson['en']}\n\n⤷ {lesson['te']}"
        return msg

    def coach_broadcast(self):
        """Post today's coaching trick to all public channels (topic-rotated)."""
        from datetime import datetime
        idx = datetime.now(config.IST).timetuple().tm_yday % 16
        lessons = load_json(config.DATA / "coach_lessons.json",
                            {"lessons": []}).get("lessons", [])
        if not lessons:
            return
        for ch in config.PUBLIC_CHANNELS:
            lesson = lessons[idx % len(lessons)]
            msg = f"{lesson['en']}\n\n⤷ {lesson['te']}"
            try:
                self.tg.send_message(config.channel_chat_id(ch), msg)
            except TelegramError as e:
                print(f"   [coach] {ch} failed: {e}")
            self.tg.polite_gap(not self.dry)
            idx += 1
        print("[coach] daily expert lessons sent")

    # ----------------------------------------------------------- reminder
    def reminder(self, slot_minutes):
        for ch in config.PUBLIC_CHANNELS:
            cfg = config.CHANNELS[ch]
            msg = (f"⏰ {cfg['emoji']} Quiz starts in {slot_minutes} min!\n"
                   f"క్విజ్ {slot_minutes} నిమిషాల్లో మొదలవుతుంది — ready? 🔥")
            try:
                self.tg.send_message(config.channel_chat_id(ch), msg)
            except TelegramError as e:
                print(f"   [reminder] {ch} failed: {e}")
        print(f"[reminder] T-{slot_minutes} min sent")

    # ------------------------------------------------------------- digest
    def _digest_items(self):
        """Prefer live aggregated CA; fall back to curated so we are never silent."""
        agg = load_json(config.DATA / "aggregated_ca.json", {"items": []})
        items = [i for i in agg.get("items", []) if i.get("en")]
        if len(items) < 3:
            curated = load_json(config.CA_CURATED_JSON, {"items": []}).get("items", [])
            items = (items + curated)
        # dedup by english text, take 6
        seen, out = set(), []
        for i in items:
            key = i["en"][:60]
            if key in seen:
                continue
            seen.add(key)
            out.append(i)
        random.shuffle(out)
        return out[:6]

    def digest(self):
        items = self._digest_items()
        now = datetime.now(config.IST)
        header = (f"🗞️ Daily Current Affairs — {now.strftime('%d %b %Y')}\n"
                  f"నేటి కరెంట్ అఫైర్స్ (పరీక్షలకు ముఖ్యమైనవి మాత్రమే)\n")
        body_lines = []
        for n, it in enumerate(items, 1):
            line = f"\n{n}. {it['en']}"
            te = it.get("te", "")
            if te:
                line += f"\n⤷ {te}"
            body_lines.append(line)
        footer = "\n\n— Source: StudentUp | పరీక్ష-సంబంధ వార్తలు మాత్రమే ✅"
        text = header + "".join(body_lines) + footer
        # post to CURRENT channel (home) — digest is one message; also to all public
        for ch in ["CURRENT"]:  # digest home channel; avoids cross-channel spam
            try:
                self.tg.send_message(config.channel_chat_id(ch), text)
            except TelegramError as e:
                print(f"   [digest] {ch} failed: {e}")
        print(f"[digest] {len(items)} CA items posted")
        return items

    # --------------------------------------------------------------- jobs
    def jobs(self):
        agg = load_json(config.DATA / "aggregated_jobs.json", {"items": []})
        items = [i for i in agg.get("items", []) if i.get("en")]
        cfg = config.CHANNELS["JOBS"]
        if not items:
            # Never silent — use verified curated fallback (live feeds override).
            items = load_json(config.DATA / "jobs_curated.json", {"items": []}).get("items", [])
            print("[jobs] live feeds empty — using curated fallback")
        items = items[: cfg["max_items"]]
        lines = [f"💼 Jobs & Exams Update • ఉద్యోగాలు & పరీక్షల అప్‌డేట్\n"]
        for n, it in enumerate(items, 1):
            line = f"\n{n}. {it['en']}"
            if it.get("te"):
                line += f"\n⤷ {it['te']}"
            if it.get("link"):
                line += f"\n🔗 {it['link']}"
            lines.append(line)
        lines.append("\n— Source: StudentUp Jobs | TS/AP + Central only ✅")
        try:
            self.tg.send_message(config.channel_chat_id("JOBS"), "".join(lines))
            print(f"[jobs] {len(items)} items posted to private channel")
            return len(items)
        except TelegramError as e:
            print(f"   [jobs] failed: {e}")
            return 0

    # ---------------------------------------------------------- leaderboard
    def leaderboard_post(self, chat_id=None):
        text = self.lb.render_weekly()
        chat = chat_id or config.channel_chat_id("CURRENT")
        try:
            self.tg.send_message(chat, text)
            print("[leaderboard] posted")
        except TelegramError as e:
            print(f"   [leaderboard] failed: {e}")

    def weekly_leaderboard(self, channels=None):
        """Post the points-based weekly member leaderboard to channels."""
        text = self.members.render_leaderboard()
        targets = channels or ["CURRENT"]
        for ch in targets:
            try:
                self.tg.send_message(config.channel_chat_id(ch), text, parse_mode="Markdown")
                print(f"[weekly-leaderboard] posted to {ch}")
            except TelegramError as e:
                print(f"   [weekly-leaderboard] {ch} failed: {e}")
