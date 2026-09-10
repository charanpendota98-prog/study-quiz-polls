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
import time
from datetime import datetime

from . import config
from .telegram import Telegram, TelegramError
from .question_bank import Bank
from .content import (build_question_text, build_options, build_explanation,
                      build_answer_key, build_round_report)
from .members import Members
from .leaderboard import Leaderboard
from .store import load_json, save_json_atomic
from .blueprint import pace_seconds, pace_label, difficulty_of, subject_of, round_profile


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
    @staticmethod
    def _paced():
        return bool(getattr(config, "PACED_ROUNDS", True))

    def send_quiz(self, channel_key, q, position="", open_period=None):
        cfg = config.CHANNELS[channel_key]
        chat = config.channel_chat_id(channel_key)
        tf = bool(getattr(config, "TELUGU_FIRST", True))
        badge = pace_label(q) if self._paced() else ""
        text = build_question_text(q, cfg, telugu_first=tf, position=position, badge=badge)
        opts = build_options(q, telugu_first=tf)
        expl = build_explanation(q, telugu_first=tf)
        # Instant = show explanation with poll; delayed = withhold for answer-key post
        instant = getattr(config, "ANSWER_MODE", "instant") != "delayed"
        if open_period is None:
            open_period = pace_seconds(q) if self._paced() else getattr(config, "QUIZ_OPEN_PERIOD", 300)
        try:
            res = self.tg.send_quiz(
                chat, text, opts, q["answer_index"], expl,
                open_period=open_period,
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
        round_id = datetime.now(config.IST).strftime("%Y%m%d-%H%M")
        self._members = Members()
        dm_map = {}       # poll_id -> (round_id, ch, qid, answer_index, uid)
        delayed = getattr(config, "ANSWER_MODE", "instant") == "delayed"
        paced = self._paced()
        mode_note = ("సమాధానాలు రౌండ్ తర్వాత — answer key after round 🔑"
                     if delayed else
                     "సరైన/తప్పు వెంటనే — instant ✅/❌ feedback")
        # 1) compose every channel's round up front
        rounds = {}
        for ch in channels:
            qs = self.bank.pick(ch, config.POLLS_PER_SLOT)
            if not qs:
                print(f"   [slot] {ch}: no questions available")
                continue
            rounds[ch] = qs
            self._last_round["by_channel"][ch] = qs
        if not rounds:
            return 0
        # 2) openers
        for ch, qs in rounds.items():
            cfg = config.CHANNELS[ch]
            n_pyq = sum(1 for q in qs if q.get("source") == "pyq")
            total_secs = sum(pace_seconds(q) + config.PACE_BUFFER_SEC for q in qs) if paced else 0
            opener = self._round_opener(cfg, label, qs, n_pyq, mode_note, paced, total_secs)
            try:
                self.tg.send_message(config.channel_chat_id(ch), opener)
            except TelegramError as e:
                print(f"   [slot] {ch} opener failed: {e}")
            self.tg.polite_gap(not self.dry)
        # 3) questions — all channels move in LOCKSTEP: Q1 goes to every
        #    channel, then we wait for the longest timer among them, then Q2…
        #    So every channel gets true one-question-at-a-time pacing and the
        #    whole slot still finishes in ~13 min instead of 8 × 13.
        n_max = max(len(qs) for qs in rounds.values())
        for i in range(n_max):
            step_secs = 0
            for ch, qs in rounds.items():
                if i >= len(qs):
                    continue
                q = qs[i]
                ok = self.send_quiz(ch, q, position=f"Q {i + 1}/{len(qs)}")
                total += 1 if ok else 0
                step_secs = max(step_secs, pace_seconds(q))
                self.tg.polite_gap(not self.dry)
                # Named scoring: channel polls are anonymous, so the same
                # question also goes to registered members' DMs (named polls).
                self._mirror_to_members(ch, q, i + 1, len(qs), round_id, dm_map)
            if paced:
                self._pace_wait(step_secs + config.PACE_BUFFER_SEC)
        # 4) closers + advanced round report (Q-by-Q answers, difficulty,
        #    subject split, toughest Q, revision tags). In delayed mode the
        #    report doubles as the answer key (posted by post_answer_key).
        for ch, qs in rounds.items():
            try:
                self.tg.send_message(config.channel_chat_id(ch), self._round_closer(qs, delayed))
                if not delayed:
                    stats = self._poll_stats_for(qs)
                    self.tg.send_message(config.channel_chat_id(ch),
                                         build_round_report(qs, round_label or "", config.CHANNELS[ch], stats))
                # 🏆 Top-10 with name + district (registered members only)
                mem = self._members.reload()
                bonuses = mem.settle_round(round_id, ch)
                top = mem.render_round_top(round_id, ch, round_label or "", config.CHANNELS[ch])
                if top and bonuses:
                    top += "\n🎁 Podium bonus: 🥇+30 · 🥈+20 · 🥉+10 · జిల్లా టాపర్ +10 pts"
                if top:
                    self.tg.send_message(config.channel_chat_id(ch), top)
                    self._dm_round_cards(mem, round_id, ch, round_label or "")
                    try:   # history of winners + refreshed member stats → Google Sheet
                        from . import crm
                        rows, _n = mem.round_top(round_id, ch)
                        crm.push_round_top(round_id, ch, rows)
                        for r in rows:
                            crm.push_member(r["uid"], mem.members.get(str(r["uid"]), {}))
                    except Exception as e:
                        print(f"   [slot] crm note: {e}")
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

    def _mirror_to_members(self, ch, q, pos, n, round_id, dm_map):
        """Send this round question as a NON-anonymous quiz poll to every
        registered member following `ch`; record poll->answer map so the bot
        can score it under round_id."""
        members = self._members
        uids = members.recipients_for(ch)
        if not uids:
            return 0
        cfg = config.CHANNELS[ch]
        tf = bool(getattr(config, "TELUGU_FIRST", True))
        text = build_question_text(q, cfg, telugu_first=tf, position=f"Q {pos}/{n}")
        opts = build_options(q, telugu_first=tf)
        expl = build_explanation(q, telugu_first=tf)
        sent = 0
        for uid in uids:
            payload = {"chat_id": uid, "question": text[:300],
                       "options": [{"text": o} for o in opts], "type": "quiz",
                       "is_anonymous": False, "allows_multiple_answers": False,
                       "correct_option_id": q["answer_index"],
                       "open_period": pace_seconds(q) if self._paced() else getattr(config, "QUIZ_OPEN_PERIOD", 300)}
            if expl.strip():
                payload["explanation"] = expl[:config.TG_POLL_EXPLANATION_MAX]
            try:
                res = self.tg._call("sendPoll", payload)
            except TelegramError as e:
                if "blocked" in str(e).lower() or "chat not found" in str(e).lower():
                    members.mark_blocked(uid)
                continue
            poll = (res or {}).get("result", {}).get("poll") or {}
            if poll.get("id"):
                dm_map[str(poll["id"])] = [round_id, ch, q["id"], int(q["answer_index"]), str(uid), q.get("topic", "")]
                sent += 1
            if sent % 20 == 0:
                time.sleep(0 if self.dry else 1.1)   # ~20 msg/s Telegram limit
        # merge into the bot's poll registry (shared file)
        try:
            path = config.DATA / "round_polls.json"
            cur = load_json(path, {})
            cur.update(dm_map)
            if len(cur) > 5000:
                for k in list(cur)[:-5000]:
                    cur.pop(k, None)
            save_json_atomic(path, cur)
        except Exception as e:
            print(f"   [mirror] save note: {e}")
        return sent

    def _dm_round_cards(self, mem, round_id, ch, label):
        """Personal report card to every registered player of this round."""
        sent = 0
        for uid in list(mem.round_players(round_id, ch).keys()):
            card = mem.personal_round_card(uid, round_id, ch, label)
            if not card:
                continue
            try:
                self.tg.send_message(uid, card)
                sent += 1
            except TelegramError:
                mem.mark_blocked(uid)
            if sent % 20 == 0:
                time.sleep(0 if self.dry else 1.1)
        if sent:
            print(f"   [slot] {ch}: {sent} personal round cards sent")

    def daily_champions(self):
        """21:35 — one post per public channel? No: polls-only rule → post to
        CURRENT only (it is the GK/all-exams hub) + Sheet. Others stay clean."""
        mem = Members()
        text = mem.render_daily_champions()
        if not text:
            print("[champions] nothing today")
            return 0
        targets = getattr(config, "CHAMPION_CHANNELS", ["CURRENT"])
        for ch in targets:
            try:
                self.tg.send_message(config.channel_chat_id(ch), text)
            except TelegramError as e:
                print(f"   [champions] {ch} failed: {e}")
        return 1

    def district_cup(self):
        """Sunday — weekly district championship."""
        mem = Members()
        text = mem.weekly_district_cup()
        if not text:
            return 0
        for ch in getattr(config, "CHAMPION_CHANNELS", ["CURRENT"]):
            try:
                self.tg.send_message(config.channel_chat_id(ch), text)
            except TelegramError as e:
                print(f"   [cup] {ch} failed: {e}")
        return 1

    def hall_of_fame(self):
        """Last day of month 21:00 — monthly Hall of Fame to hub channel."""
        mem = Members()
        text = mem.monthly_hall_of_fame()
        if not text:
            return 0
        for ch in getattr(config, "CHAMPION_CHANNELS", ["CURRENT"]):
            try:
                self.tg.send_message(config.channel_chat_id(ch), text)
            except TelegramError as e:
                print(f"   [hof] {ch} failed: {e}")
        return 1

    def nightly_member_file(self):
        """22:00 — send the full member list (CSV, Excel/Google-Sheet ready) to
        ADMIN_ID by DM. Zero setup: no Apps Script, no permissions. Also pushes
        to the Sheet web app if it is configured."""
        from . import crm
        mem = Members()
        if not config.ADMIN_ID:
            print("[member-file] ADMIN_ID not set")
            return 0
        data = crm.export_csv(mem.members)
        fn = f"studentup_members_{datetime.now(config.IST):%Y%m%d}.csv"
        n = sum(1 for m in mem.members.values() if m.get("registered"))
        cap = (f"👥 {n} registered members — name, mobile, district, exam, points\n"
               f"Open in Google Sheets: File → Import → Upload → Replace")
        try:
            self.tg.send_document(config.ADMIN_ID, fn, data, caption=cap)
        except TelegramError as e:
            print(f"   [member-file] failed: {e}")
            return 0
        if crm.sheet_enabled():
            mem.sync_sheet_all()
        return n

    def streak_nudge(self):
        """Evening DM to members whose streak will break if they skip today."""
        mem = Members()
        n = 0
        for uid in mem.streak_at_risk():
            m = mem.members[str(uid)]
            msg = (f"🔥 {m.get('name') or ''}, మీ {m['streak']}-day streak ఈరోజు break అవుతుంది!\n"
                   f"Your {m['streak']}-day streak ends tonight — one /quiz keeps it alive (+bonus).")
            try:
                self.tg.send_message(uid, msg)
                n += 1
            except TelegramError:
                mem.mark_blocked(uid)
            if n % 20 == 0:
                time.sleep(0 if self.dry else 1.1)
        print(f"[streak-nudge] {n} sent")
        return n

    def _poll_stats_for(self, qs):
        """{qid: {correct, total}} from the leaderboard's poll registry when
        vote counts are available (channel polls are anonymous, so this is
        best-effort — the report simply omits % when unknown)."""
        try:
            return self.lb.stats_by_qid([q.get("id") for q in qs])
        except Exception:
            return {}

    # ------------------------------------------------- paced-round helpers
    def _pace_wait(self, secs: int):
        """Sleep for one question's timer (skipped in dry/test runs)."""
        if self.dry:
            return
        time.sleep(max(0, int(secs)))

    @staticmethod
    def _fmt_min(secs: int) -> str:
        m = max(1, round(secs / 60))
        return f"{m} min"

    @staticmethod
    def _subject_line(qs) -> str:
        """'GK 5 · Reasoning 3 · Aptitude 2' — what this round covers."""
        names = {"gk": "GK", "reasoning": "Reasoning", "quant": "Aptitude", "english": "English"}
        prof = round_profile(qs)
        subs = prof.get("subjects") or {}
        parts = [f"{names.get(k, k.title())} {v}" for k, v in
                 sorted(subs.items(), key=lambda kv: -kv[1]) if v]
        return " · ".join(parts)

    def _round_opener(self, cfg, label, qs, n_pyq, mode_note, paced, total_secs):
        diff = round_profile(qs).get("difficulty") or {}
        n_hard = diff.get("hard", 0)
        lines = [f"{cfg['emoji']} {label}{cfg['subject']} — Quiz Round 📋",
                 f"📝 {len(qs)} ప్రశ్నలు · {n_pyq} PYQ · {n_hard} hard",
                 f"📚 {self._subject_line(qs)}"]
        if paced:
            lines += [f"⏱ ఒక్కో ప్రశ్న 1–1.5 నిమిషాలు (easy 1 · hard 1.5) — "
                      f"one question at a time, exam-hall pace",
                      f"🕒 Round ≈ {self._fmt_min(total_secs)}"]
        lines += [mode_note,
                  "Points & ranks: /quiz in our bot group ⭐"]
        return "\n".join(lines)

    @staticmethod
    def _round_closer(qs, delayed):
        head = f"🎌 Round complete — {len(qs)} questions done."
        if delayed:
            return (f"{head}\n🔑 Answer key posts shortly — సమాధానాలు కాసేపట్లో.\n"
                    f"10/10 కొట్టినవారు కామెంట్‌లో 👇 రాయండి!\n"
                    f"Points & ranks: /register in our quiz bot ⭐")
        return (f"{head}\n10/10 కొట్టినవారు కామెంట్‌లో 👇 రాయండి!\n"
                f"Points, ranks & streaks: /register in our quiz bot ⭐\n"
                f"Next round: see the daily schedule. Keep your streak 🔥")

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
            text = build_round_report(qs, round_label=label, channel_cfg=config.CHANNELS.get(ch))
            try:
                self.tg.send_message(config.channel_chat_id(ch), text)
                posted += 1
            except TelegramError as e:
                print(f"   [answer_key] {ch} failed: {e}")
            self.tg.polite_gap(not self.dry)
        print(f"[answer_key] posted to {posted} channels")
        return posted

    # ------------------------------------------------------------ morning
    @staticmethod
    def _polls_only() -> bool:
        return bool(getattr(config, "PUBLIC_POLLS_ONLY", True))

    def morning(self):
        if self._polls_only():
            print("[morning] skipped (PUBLIC_POLLS_ONLY — quiz channels carry polls only)")
            return
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
        if self._polls_only():
            print("[tip] skipped (PUBLIC_POLLS_ONLY)")
            return
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
            from .collector import collect_daily, retry_pending, ingest_inbox
            stats = collect_daily()
            stats["pdf_inbox"] = ingest_inbox()      # harvested / dropped PDFs
            retry_pending()
            return stats
        except Exception as e:
            print(f"   [collect] error (non-fatal): {e}")
            return {"accepted": 0, "error": str(e)}

    def backfill_exam_content(self):
        """Nightly deep archive sweep (3-month campaign, auto-completes)."""
        try:
            from .collector import backfill
            return backfill()
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
        if self._polls_only():
            print("[coach] skipped (PUBLIC_POLLS_ONLY)")
            return
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
        """Two professional alerts only: T-5 (round preview) and T-1 (starting)."""
        n = config.POLLS_PER_SLOT
        for ch in config.PUBLIC_CHANNELS:
            cfg = config.CHANNELS[ch]
            if slot_minutes >= 5:
                msg = (f"🔔 {cfg['emoji']} {cfg['subject']} Quiz — {slot_minutes} నిమిషాల్లో\n"
                       f"📋 {n} questions · exam-hall pace · one at a time\n"
                       f"⏱ 1 min easy · 1.5 min hard — పెన్ను, పేపర్ సిద్ధం చేసుకోండి\n"
                       f"Starts in {slot_minutes} min. Be ready ✍️")
            else:
                msg = (f"🚀 {cfg['emoji']} {cfg['subject']} Quiz — 1 నిమిషంలో మొదలు!\n"
                       f"Starting in 1 minute. Q1 arrives at the top of the minute. "
                       f"All the best 🔥")
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
        if self._polls_only():
            print("[digest] skipped (PUBLIC_POLLS_ONLY)")
            return []
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
        """Structured job cards → PRIVATE jobs channel only (core/jobs.py).
        Falls back to the legacy feed digest if the desk raises."""
        try:
            from . import jobs as jobsdesk
            return jobsdesk.run(self.tg, dry=self.dry)
        except Exception as e:
            print(f"   [jobs] desk error → legacy digest: {e}")
        return self._jobs_legacy()

    def _jobs_legacy(self):
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
        if self._polls_only() and not channels:
            print("[weekly-leaderboard] skipped (PUBLIC_POLLS_ONLY)")
            return
        text = self.members.render_leaderboard()
        targets = channels or ["CURRENT"]
        for ch in targets:
            try:
                self.tg.send_message(config.channel_chat_id(ch), text, parse_mode="Markdown")
                print(f"[weekly-leaderboard] posted to {ch}")
            except TelegramError as e:
                print(f"   [weekly-leaderboard] {ch} failed: {e}")
