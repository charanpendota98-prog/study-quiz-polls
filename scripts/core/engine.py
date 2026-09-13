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
        if not getattr(config, "POLL_AUTO_CLOSE", False):
            open_period = None        # never auto-close → never auto-reveal ✅ to non-voters
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
                     "మీరు answer చేసిన తర్వాతే ✅/❌ కనిపిస్తుంది — key shows only after YOU answer")
        # 1) compose every channel's round up front
        rounds = {}
        for ch in channels:
            qs = self.bank.pick(ch, config.POLLS_PER_SLOT)
            # Send-time safety: never expose the key (markers / answer-in-stem)
            # and balance the correct option across A-D for this round.
            from .content import poll_safe
            safe = []
            for q in qs:
                sq = poll_safe(q, seed=round_id)
                if sq is None:
                    print(f"   [slot] {ch}: skipped {q.get('id')} (answer leak guard)")
                    continue
                safe.append(sq)
            qs = safe
            if not qs:
                print(f"   [slot] {ch}: no questions available")
                continue
            rounds[ch] = qs
            self._last_round["by_channel"][ch] = qs
        if not rounds:
            return 0
        # 2a) previous round's Q-by-Q key (only now — every earlier poll had its full window)
        self.post_previous_key(channels=list(rounds))
        # 2) openers
        for ch, qs in rounds.items():
            cfg = config.CHANNELS[ch]
            n_pyq = sum(1 for q in qs if q.get("source") == "pyq")
            total_secs = sum(pace_seconds(q) + config.PACE_BUFFER_SEC for q in qs) if paced else 0
            opener = self._round_opener(cfg, label, qs, n_pyq, mode_note, paced, total_secs)
            try:
                from . import gate as _gate
                _btn = _gate.cta_buttons()
            except Exception:
                _btn = None
            try:
                self.tg.send_message(config.channel_chat_id(ch), opener, buttons=_btn)
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
                # Q-by-Q key report is NOT posted now: polls stay open so
                # late players can still answer without seeing the key. It is
                # posted by post_previous_key() right before the NEXT round.
                # 🏆 Top-10 with name + district (registered members only)
                mem = self._members.reload()
                bonuses = mem.settle_round(round_id, ch)
                try:
                    from . import roundshow
                    top = roundshow.render(mem, round_id, ch, len(qs), round_label or "", config.CHANNELS[ch])
                except Exception as e:
                    print(f"   [roundshow] {e}"); top = ""
                if not top:
                    top = mem.render_round_top(round_id, ch, round_label or "", config.CHANNELS[ch])
                if top:
                    try:
                        from . import examboard
                        top += examboard.round_clash(mem, round_id, ch)
                    except Exception as e:
                        print(f"   [examboard] {e}")
                if top and bonuses:
                    top += "\n🎁 Podium bonus: 🥇+30 · 🥈+20 · 🥉+10 · జిల్లా టాపర్ +10 pts"
                try:      # 🎁 mystery multiplier reveal
                    from . import hooks
                    mw = hooks.apply_mystery(mem, round_id, ch, [q["id"] for q in qs])
                    ml = hooks.mystery_line(round_id, ch, len(qs), len(mw))
                    if top and ml:
                        top += "\n" + ml
                except Exception as e:
                    print(f"   [mystery] {e}")
                _gbtn = None
                try:
                    from . import gate
                    _rows, _n_all = mem.round_top(round_id, ch, limit=10_000)
                    if top:
                        top += "\n\n" + gate.top10_tail(mem, max(0, _n_all - len(_rows)))
                    _gbtn = gate.cta_buttons()
                    gate.after_round_dms(mem, self.tg, round_id, ch, len(qs), dry=self.dry)
                except Exception as e:
                    print(f"   [gate] {e}")
                if top:
                    self.tg.send_message(config.channel_chat_id(ch), top, buttons=_gbtn)
                    self._dm_round_cards(mem, round_id, ch, round_label or "")
                    self._rank_cards(mem, round_id, ch, f"{round_label or 'Round'}")
                    self._share_posters(mem, round_id, ch, round_label or "Round")
                    try:   # history of winners + refreshed member stats → Google Sheet
                        from . import crm
                        rows, _n = mem.round_top(round_id, ch)
                        crm.push_round_top(round_id, ch, rows)
                        for r in rows:
                            crm.push_member(r["uid"], mem.members.get(str(r["uid"]), {}))
                    except Exception as e:
                        print(f"   [slot] crm note: {e}")
                self._streak_shoutouts(mem, ch)
                self._arena_shoutouts(ch)
            except TelegramError as e:
                print(f"   [slot] {ch} closer failed: {e}")
            self.tg.polite_gap(not self.dry)
        # Persist last-round snapshot for the delayed answer-key job
        try:
            from .store import save_json_atomic
            snap = {
                "label": self._last_round.get("label", ""),
                "round_id": round_id,
                "key_posted": False,
                "by_channel": {
                    ch: [{"id": q.get("id"), "topic": q.get("topic"), "q_en": q.get("q_en"),
                          "q_te": q.get("q_te"), "difficulty": q.get("difficulty"),
                          "source": q.get("source"), "exam": q.get("exam"), "year": q.get("year"),
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
        try:      # week log → Sunday Grand Test revision pool
            from . import grandtest
            for ch, qs in rounds.items():
                grandtest.log_round(ch, [q["id"] for q in qs])
        except Exception as e:
            print(f"   [slot] week-log note: {e}")
        print(f"[slot] posted {total} polls across {len(channels)} channels "
              f"(mode={getattr(config, 'ANSWER_MODE', 'instant')})")
        return total

    # ------------------------------------------------------------ Sunday Grand Test
    def grand_test_teaser(self, channels=None):
        """Saturday evening: one professional teaser per quiz channel."""
        from . import grandtest
        n = 0
        from datetime import timedelta
        mega = grandtest.is_last_sunday(datetime.now(config.IST) + timedelta(days=1))
        for ch in channels or config.PUBLIC_CHANNELS:
            try:
                cfg = config.CHANNELS[ch]
                self.tg.send_message(config.channel_chat_id(ch),
                                     grandtest.mega_teaser(cfg) if mega else grandtest.teaser(cfg))
                n += 1
            except TelegramError as e:
                print(f"   [grand-teaser] {ch} failed: {e}")
            self.tg.polite_gap(not self.dry)
        return n

    def run_grand_test(self, channels=None, mega=None):
        """Sunday morning real-exam mock: revision (toughest of the week) +
        fresh, sections easy→hard, negative marking, double points."""
        from . import grandtest
        from .content import poll_safe
        channels = channels or config.PUBLIC_CHANNELS
        if mega is None:
            mega = grandtest.is_last_sunday()
        n_q = grandtest.MEGA_Q if mega else grandtest.GRAND_Q
        window = 30 if mega else 6
        label = "Monthly Mega Test 🏆" if mega else "Sunday Grand Test 🏟"
        round_id = datetime.now(config.IST).strftime(("M" if mega else "G") + "%Y%m%d-%H%M")
        self._members = Members()
        dm_map = {}
        paced = self._paced()
        self.post_previous_key(channels=channels)
        rounds, metas = {}, {}
        for ch in channels:
            qs, meta = grandtest.compose_grand_test(self.bank, ch, n=n_q, lb=self.lb, days=window)
            safe = [sq for sq in (poll_safe(q, seed=round_id) for q in qs) if sq]
            if len(safe) < 5:
                print(f"   [grand] {ch}: only {len(safe)} questions — skipped")
                continue
            rounds[ch], metas[ch] = safe, meta
        if not rounds:
            return 0
        for ch, qs in rounds.items():
            cfg = config.CHANNELS[ch]
            total_secs = sum(pace_seconds(q) + config.PACE_BUFFER_SEC for q in qs) if paced else 0
            try:
                self.tg.send_message(config.channel_chat_id(ch),
                                     grandtest.opener(cfg, metas[ch], self._fmt_min(total_secs), mega=mega))
            except TelegramError as e:
                print(f"   [grand] {ch} opener failed: {e}")
            self.tg.polite_gap(not self.dry)
        total = 0
        n_max = max(len(qs) for qs in rounds.values())
        last_section = {}
        for i in range(n_max):
            step_secs = 0
            for ch, qs in rounds.items():
                if i >= len(qs):
                    continue
                q = qs[i]
                sec = grandtest._difficulty(q)
                if last_section.get(ch) != sec:      # section divider like a real paper
                    last_section[ch] = sec
                    label = {"easy": "Section A · Easy", "medium": "Section B · Medium",
                             "hard": "Section C · Hard"}.get(sec, sec)
                    try:
                        self.tg.send_message(config.channel_chat_id(ch), f"📑 {label}")
                    except TelegramError:
                        pass
                ok = self.send_quiz(ch, q, position=f"Q {i + 1}/{len(qs)}")
                total += 1 if ok else 0
                step_secs = max(step_secs, pace_seconds(q))
                self.tg.polite_gap(not self.dry)
                self._mirror_to_members(ch, q, i + 1, len(qs), round_id, dm_map)
            if paced:
                self._pace_wait(step_secs + config.PACE_BUFFER_SEC)
        # results: negative-marking ranks, cut-offs, district of the week
        for ch, qs in rounds.items():
            try:
                self.tg.send_message(config.channel_chat_id(ch),
                                     "🏁 Grand Test over — results in a moment. Answer key: before next round 🔑")
                mem = self._members.reload()
                grandtest.settle_grand(mem, round_id, ch, mega=mega)
                text = grandtest.render_grand_top(mem, round_id, ch, config.CHANNELS[ch], n_q=len(qs), mega=mega)
                if text:
                    self.tg.send_message(config.channel_chat_id(ch), text)
                    self._dm_round_cards(mem, round_id, ch, label)
                    self._rank_cards(mem, round_id, ch, label, n_q=len(qs), grand=True)
                    try:
                        from . import crm
                        rows, _n, _all = grandtest.grand_rows(mem, round_id, ch)
                        crm.push_round_top(round_id, ch, rows)
                    except Exception as e:
                        print(f"   [grand] crm note: {e}")
            except TelegramError as e:
                print(f"   [grand] {ch} closer failed: {e}")
            self.tg.polite_gap(not self.dry)
        # snapshot for the delayed Q-by-Q key (same path as daily rounds)
        try:
            snap = {"label": label, "round_id": round_id, "key_posted": False,
                    "by_channel": {ch: [{k: q.get(k) for k in (
                        "id", "topic", "q_en", "q_te", "difficulty", "source", "exam", "year",
                        "answer_index", "options_en", "options_te", "explanation_en", "explanation_te")}
                        for q in qs] for ch, qs in rounds.items()}}
            save_json_atomic(config.DATA / "last_round.json", snap)
        except Exception as e:
            print(f"   [grand] last_round save note: {e}")
        print(f"[grand] posted {total} polls across {len(rounds)} channels")
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
                       "correct_option_id": q["answer_index"]}
            if getattr(config, "POLL_AUTO_CLOSE", False):
                payload["open_period"] = pace_seconds(q) if self._paced() else getattr(config, "QUIZ_OPEN_PERIOD", 300)
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

    def _share_posters(self, mem, round_id, ch, label):
        """Personal 'నా score' PNG to every registered player (WhatsApp-status
        ready). Skips silently without Pillow."""
        try:
            from . import rankcard, districts as D
            if not rankcard.available():
                return 0
            rows, n = mem.round_top(round_id, ch, limit=10_000)
            cfg = config.CHANNELS[ch]
            sent = 0
            for i, r in enumerate(rows, 1):
                if i <= 3:
                    continue          # podium already got the gold/silver/bronze card
                m = mem.members.get(str(r["uid"])) or {}
                png = rankcard.render(
                    {"name": r["name"], "district": r["district"],
                     "district_te": D.telugu_name(r["district"]) if r["district"] else ""},
                    title=f"{label} — {cfg.get('subject', ch)}", subtitle_te="నా స్కోర్ · StudentUp",
                    exam=f"Rank #{i} of {n}", rank=i, score=f"{r['correct']} / {r['total']}",
                    extra=f"🔥 {m.get('streak', 0)}-day streak · ⭐ {m.get('points', 0)} pts")
                if not png:
                    continue
                try:
                    self.tg.send_photo(str(r["uid"]), png,
                                       caption="Status లో పెట్టండి 📲 friends ని పిలవండి — /invite (+20 pts)")
                    sent += 1
                except TelegramError:
                    mem.mark_blocked(r["uid"])
                if sent % 15 == 0:
                    time.sleep(0 if self.dry else 1.1)
            return sent
        except Exception as e:
            print(f"   [poster] note: {e}")
            return 0

    def _streak_shoutouts(self, mem, ch):
        """Channel shout-out for 7/30/100-day streak milestones queued by members."""
        try:
            from . import hooks
            q = mem.data.get("shoutouts") or []
            if not q:
                return 0
            cfg = config.CHANNELS[ch]
            n = 0
            for so in q[:3]:
                m = mem.members.get(so["uid"]) or {}
                try:
                    self.tg.send_message(config.channel_chat_id(ch), hooks.milestone_post(m, so["streak"], cfg))
                    n += 1
                except TelegramError:
                    pass
            mem.data["shoutouts"] = q[3:]
            mem.kv.save()
            return n
        except Exception as e:
            print(f"   [shoutout] {e}")
            return 0

    # ------------------------------------------------------------ Partner ads
    def partner_ad(self):
        """Ad slot: ONE digest card per hub channel (state + district offers, register CTA) and ONE
        personal digest DM per member with all offers in their mandal/district/state. Partner photos
        (if any) ride along as the card's picture. Impressions counted per partner."""
        from . import partners, rewards
        from .members import Members
        mem = Members()
        card = partners.digest_for_channel(mem)
        if not card:
            print("[ads] no active partner offers")
            return 0
        n = 0
        # hub channels: text digest (+ first photo partner as picture, if any)
        photo = next((p["photo"] for p in partners._load()["partners"].values() if p.get("active") and p.get("photo")), "")
        for ch in partners.AD_CHANNELS:
            if ch not in config.CHANNELS:
                continue
            try:
                if photo and not self.dry:
                    self.tg._call("sendPhoto", {"chat_id": config.channel_chat_id(ch), "photo": photo, "caption": card[:1000]})
                else:
                    self.tg.send_message(config.channel_chat_id(ch), card)
                n += 1
            except Exception as e:
                print(f"   [ads] {ch}: {e}")
        # personal digests
        seen_partner = {}
        sent = 0
        for uid, m in mem.members.items():
            if not (m.get("registered") and not m.get("dm_blocked") and not m.get("no_ads")):
                continue
            bal = rewards.balance(mem, uid)["available"]
            txt, btns = partners.digest_for_member(mem, uid, bal)
            if not txt:
                continue
            for row in btns:
                seen_partner[row[0][1]] = seen_partner.get(row[0][1], 0) + 1
            if self.dry:
                sent += 1; continue
            try:
                self.tg.send_message(uid, txt, buttons=btns); sent += 1
            except TelegramError as e:
                if "blocked" in str(e).lower() or "deactivated" in str(e).lower():
                    m["dm_blocked"] = True
        d = partners._load()
        for o in d["offers"].values():
            k = f"poffer:{o['id']}"
            if k in seen_partner:
                p = d["partners"].get(o["partner"])
                if p:
                    p["dm_impressions"] = p.get("dm_impressions", 0) + seen_partner[k]
                    p["impressions"] = p.get("impressions", 0) + n
                o["last_shown"] = partners._now().isoformat()
        partners._save(d)
        try:
            mem.kv.save()
        except Exception:
            pass
        print(f"[ads] digest → {n} channels, {sent} personal DMs")
        return n + sent

    def partner_housekeeping(self):
        from . import partners
        return partners.expire_stale()

    def examday_checkins(self):
        """Exam day (inside an exam-day offer window): DM matching students a
        'నేను exam రాశాను' button → bonus + unlocks that district's offers."""
        from . import partners
        from .members import Members
        mem = Members()
        n = 0
        for uid, exam, offs in partners.examday_prompts(mem):
            if self.dry:
                n += 1; continue
            try:
                self.tg.send_message(uid, partners.examday_prompt_text(exam, offs),
                                     buttons=[[(f"✅ నేను {exam} exam రాశాను", f"pexam:{exam}")]])
                n += 1
            except TelegramError:
                pass
        print(f"[examday] prompted {n}")
        return n

    def exam_boards(self, period="today"):
        """Per exam channel: today's Top-10 + district clash (21:30) or Sunday weekly champions."""
        from . import examboard
        mem = self._members.reload() if hasattr(self, "_members") else Members()
        n = 0
        for ch in config.PUBLIC_CHANNELS:
            try:
                txt = examboard.weekly_close(mem, ch) if period == "week" else examboard.render_board(mem, ch, period)
                if not txt:
                    continue
                if not self.dry:
                    self.tg.send_message(config.channel_chat_id(ch), txt)
                n += 1
            except Exception as e:
                print(f"   [examboard] {ch}: {e}")
        print(f"[examboard] {period}: {n} channels")
        return n

    def gate_chase(self):
        from . import gate
        return gate.chase_locked(Members(), self.tg, self.dry)

    def jobradar(self, what):
        from . import jobradar as JR
        mem = Members()
        if what == "digest":
            return JR.daily_digest(mem, self.tg, self.dry)
        return JR.deadline_reminders(mem, self.tg, self.dry)

    def sheet_nightly(self):
        from . import crm
        if self.dry:
            return {"dry": True}
        return crm.nightly_sync(Members().members)

    def campaigns_due(self):
        from . import messenger
        return messenger.run_due(self.tg, Members(), dry=self.dry)

    def report_cards(self):
        from . import reportcard
        return reportcard.weekly_send(self.tg, Members(), dry=self.dry)

    def college_toppers(self):
        from . import roster
        txt = roster.weekly_toppers(Members())
        if not txt or self.dry:
            return txt
        for ch in getattr(config, "CHAMPION_CHANNELS", ["CURRENT"]):
            try:
                self.tg.send_message(config.channel_chat_id(ch), txt)
            except Exception:
                pass
        return txt

    # ------------------------------------------------------------ autopilot
    def autopilot(self, what):
        from . import autopilot as A
        mem = Members()
        bank = self.bank if hasattr(self, "bank") else None
        if what == "heal":
            return A.heal(bank, mem, self.tg, self.dry)
        if what == "coach":
            return A.coach_round(bank, mem, self.tg, self.dry)
        if what == "coach_streaks":
            return A.coach_streaks(mem, self.tg, self.dry)
        if what == "winback":
            return A.winback(mem, self.tg, self.dry)
        if what == "countdown":
            return A.exam_countdown(mem, self.tg, self.dry)
        if what == "night":
            return A.night_report(mem, self.tg, self.dry)
        return None

    def morning_brief(self):
        from . import hq
        txt = hq.morning_brief(Members(), self.bank if hasattr(self, "bank") else None)
        if not txt:
            print("[hq] no news"); return 0
        n = 0
        for aid in getattr(config, "STAFF_IDS", []) or ([str(config.ADMIN_ID)] if config.ADMIN_ID else []):
            if self.dry:
                n += 1; continue
            try:
                self.tg.send_message(aid, txt, buttons=hq.buttons()); n += 1
            except TelegramError:
                pass
        return n

    def join_nudge(self):
        """Wed 11:00: DM members who never verified channel join (max 3 times)."""
        from . import joingate
        mem = Members()
        n = 0
        for uid in joingate.nudge_targets(mem):
            m = mem._get(uid)
            if not self.dry:
                try:
                    self.tg.send_message(uid, joingate.nudge_text(m), buttons=joingate.buttons(m))
                except TelegramError as e:
                    if "blocked" in str(e).lower():
                        m["dm_blocked"] = True
                    continue
            m["join_nudges"] = m.get("join_nudges", 0) + 1
            m["join_nudged"] = datetime.now(config.IST).isoformat()
            n += 1
        mem.kv.save()
        print(f"[join] nudged {n}")
        return n

    def campus_drip(self):
        from . import campus
        n = 0 if self.dry else campus.onboarding_drip(self.tg, Members())
        print(f"[campus] drip sent {n}")
        return n

    def college_league(self):
        from . import campus
        txt = campus.college_league(Members())
        if not txt:
            return 0
        if not self.dry:
            for ch in getattr(config, "CHAMPION_CHANNELS", ["CURRENT"]):
                try:
                    self.tg.send_message(config.channel_chat_id(ch), txt)
                except Exception as e:
                    print(f"   [college-league] {e}")
        return 1

    def partner_call(self):
        """Monday hub post: 'partner with StudentUp' + biggest districts → inbound leads."""
        from . import social
        from .members import Members
        txt = social.weekly_partner_call(Members())
        if not txt:
            return 0
        n = 0
        for ch in getattr(config, "CHAMPION_CHANNELS", ["CURRENT"]):
            if self.dry:
                n += 1; continue
            try:
                self.tg.send_message(config.channel_chat_id(ch), txt); n += 1
            except Exception as e:
                print(f"   [partner-call] {ch}: {e}")
        return n

    def partner_weekly(self):
        """Monday: Top Recruiter spotlight (channels + winner DM) + merchant reports."""
        from . import partners
        from .members import Members
        mem = Members()
        txt, win = partners.weekly_top_recruiters(mem)
        if txt and not self.dry:
            for ch in getattr(config, "CHAMPION_CHANNELS", ["CURRENT"]):
                try:
                    self.tg.send_message(config.channel_chat_id(ch), txt)
                except Exception as e:
                    print(f"   [recruiter] {ch}: {e}")
            try:
                self.tg.send_message(win, txt)
            except TelegramError:
                pass
        sent = 0
        for mu, rep in partners.weekly_merchant_reports():
            if self.dry:
                sent += 1; continue
            try:
                self.tg.send_message(mu, rep); sent += 1
            except TelegramError:
                pass
        try:
            self.partner_call()
        except Exception as e:
            print(f"   [partner-call] {e}")
        print(f"[partner-weekly] recruiters={'yes' if txt else 'none'} merchant reports={sent}")
        return sent

    # ------------------------------------------------------------ District War
    def war_alert(self, minutes):
        from . import districtwar
        mem = Members()
        if minutes >= 5:
            districtwar.open_lobby()          # today's opt-in lobby opens now
        txt = districtwar.alert_text(minutes)
        btn = districtwar.lobby_buttons(minutes)
        joined = set((districtwar._load().get("lobby") or {}).get("joined", {}).keys())
        n = 0
        for uid, m in mem.members.items():
            if m.get("registered") and m.get("district") and not m.get("dm_blocked"):
                if minutes < 5 and str(uid) in joined:
                    continue                  # already in — don't nag at T-1
                try:
                    self.tg.send_message(uid, txt, buttons=btn); n += 1
                except TelegramError:
                    mem.mark_blocked(uid)
                if n % 25 == 0:
                    time.sleep(0 if self.dry else 1.0)
        if minutes >= 5:
            for ch in getattr(config, "WAR_CHANNELS", None) or getattr(config, "CHAMPION_CHANNELS", ["CURRENT"]):
                try:
                    self.tg.send_message(config.channel_chat_id(ch), districtwar.channel_alert_text(minutes),
                                         buttons=districtwar.channel_buttons())
                except TelegramError:
                    pass
        print(f"[war] T-{minutes} alert → {n} fighters")
        return n

    def war_start(self):
        from . import districtwar
        ok, info = districtwar.start_war(self.bank, Members(), self.tg)
        print(f"[war] start: {ok} {info}")
        if not ok:
            self.tg.admin_notify(f"District War not started: {info}")
        return ok

    def war_publish(self):
        """After the war finishes (bot loop runs it): post result to hub + season table Sundays."""
        from . import districtwar
        txt = districtwar.pop_channel_post()
        if not txt:
            return 0
        for ch in getattr(config, "WAR_CHANNELS", None) or getattr(config, "CHAMPION_CHANNELS", ["CURRENT"]):
            try:
                self.tg.send_message(config.channel_chat_id(ch), txt)
            except TelegramError as e:
                print(f"   [war] {ch} failed: {e}")
        return 1

    def war_season(self, channels=None):
        from . import districtwar
        txt = districtwar.season_table()
        if not txt:
            return 0
        for ch in channels or getattr(config, "WAR_CHANNELS", None) or getattr(config, "CHAMPION_CHANNELS", ["CURRENT"]):
            try:
                self.tg.send_message(config.channel_chat_id(ch), txt)
            except TelegramError:
                pass
        return 1

    def _arena_shoutouts(self, ch):
        """Squad-battle results → the channel of that mode (max 2 per round)."""
        try:
            from . import arena
            n = 0
            for so in arena.pop_shoutouts():
                target = so.get("channel") if so.get("channel") in config.PUBLIC_CHANNELS else ch
                if target != ch:
                    continue
                self.tg.send_message(config.channel_chat_id(ch), arena.shout_text(so, config.CHANNELS[ch]))
                n += 1
                if n >= 2:
                    break
            return n
        except Exception as e:
            print(f"   [arena-shout] {e}")
            return 0

    def arena_board(self, channels=None):
        from . import arena
        txt = arena.render_top(Members())
        if "మొదలవలేదు" in txt:
            return 0
        for ch in channels or getattr(config, "CHAMPION_CHANNELS", ["CURRENT"]):
            try:
                self.tg.send_message(config.channel_chat_id(ch), txt)
            except TelegramError as e:
                print(f"   [arena] {ch} failed: {e}")
        return 1

    def streak_shield_job(self):
        """00:10 daily — consume shields for members who missed yesterday."""
        from . import hooks
        mem = Members()
        saved = hooks.protect_streaks(mem)
        for uid, streak in saved:
            try:
                self.tg.send_message(uid, hooks.shield_dm(mem.members[str(uid)], streak))
            except TelegramError:
                mem.mark_blocked(uid)
        print(f"[shield] {len(saved)} streaks protected")
        return len(saved)

    def squad_board(self, channels=None):
        from . import hooks
        txt = hooks.render_squad_top(Members(), cfg=None)
        if not txt:
            return 0
        for ch in channels or getattr(config, "CHAMPION_CHANNELS", ["CURRENT"]):
            try:
                self.tg.send_message(config.channel_chat_id(ch), txt)
            except TelegramError as e:
                print(f"   [squad] {ch} failed: {e}")
        return 1

    def _rank_cards(self, mem, round_id, ch, label, n_q=None, grand=False):
        """Shareable PNG rank cards for the podium → channel (Top-3) + DM to
        the winners. Silent no-op when Pillow is missing or RANK_CARDS=0."""
        try:
            from . import rankcard
            if not rankcard.available():
                return 0
            cfg = config.CHANNELS[ch]
            if grand:
                from . import grandtest
                rows, _n, _all = grandtest.grand_rows(mem, round_id, ch)
                n_q = n_q or grandtest.GRAND_Q
                fmt = lambda r: f"{r['marks']:g} / {n_q}"
            else:
                rows, _n = mem.round_top(round_id, ch)
                fmt = lambda r: f"{r['correct']} / {r['total']}"
            cards = rankcard.top3_cards(rows, title=f"{label} — TOP 3", subtitle_te="టాప్ 3 · అభినందనలు",
                                        exam=cfg.get("subject", ch), score_fmt=fmt)
            sent = 0
            for rank, r, png in cards:
                medal = {1: "🥇", 2: "🥈", 3: "🥉"}[rank]
                cap = f"{medal} {r['name']} · {r.get('district', '')} — {label}\nShare చేయండి 📲 {getattr(config, 'BRAND_HANDLE', '')}"
                try:
                    if rank == 1:      # channel stays clean: only the winner's card goes public
                        self.tg.send_photo(config.channel_chat_id(ch), png, caption=cap)
                    self.tg.send_photo(str(r["uid"]), png, caption=cap)
                    sent += 1
                except TelegramError as e:
                    print(f"   [rankcard] {ch} #{rank}: {e}")
                self.tg.polite_gap(not self.dry)
            return sent
        except Exception as e:
            print(f"   [rankcard] note: {e}")
            return 0

    def _dm_round_cards(self, mem, round_id, ch, label):
        """Personal report card to every registered player of this round."""
        sent = 0
        for uid in list(mem.round_players(round_id, ch).keys()):
            card = mem.personal_round_card(uid, round_id, ch, label)
            if not card:
                continue
            try:
                from . import roundshow
                card += roundshow.my_line(mem, uid, round_id, ch, len(self._last_round.get("by_channel", {}).get(ch, [])) or 10)
            except Exception:
                pass
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

    def rewards_promo(self, channels=None):
        """Twice a week in the hub channel: points → real discounts at the centre."""
        from . import rewards
        n = 0
        for ch in channels or getattr(config, "CHAMPION_CHANNELS", ["CURRENT"]):
            try:
                self.tg.send_message(config.channel_chat_id(ch), rewards.promo_text(config.CHANNELS[ch]))
                n += 1
            except TelegramError as e:
                print(f"   [rewards] {ch} failed: {e}")
        return n

    def rewards_housekeeping(self):
        from . import rewards
        n = rewards.expire_stale(Members())
        print(f"[rewards] expired vouchers released: {n}")
        return n

    def weekly_report_cards(self):
        """Sunday night — personal report card DM to every member active this week."""
        from . import growth
        mem = Members()
        sent = 0
        for uid in growth.active_members(mem):
            txt = growth.weekly_report(mem, uid)
            if not txt:
                continue
            try:
                self.tg.send_message(uid, txt)
                sent += 1
            except TelegramError:
                mem.mark_blocked(uid)
            if sent % 20 == 0:
                time.sleep(0 if self.dry else 1.1)
        print(f"[report] {sent} weekly report cards sent")
        return sent

    def referral_board(self, channels=None):
        from . import growth
        txt = growth.referral_board(Members())
        if not txt:
            return 0
        for ch in channels or getattr(config, "CHAMPION_CHANNELS", ["CURRENT"]):
            try:
                self.tg.send_message(config.channel_chat_id(ch), txt)
            except TelegramError as e:
                print(f"   [referral] {ch} failed: {e}")
        return 1

    def challenge_invite(self):
        """13:00 weekdays — DM 'Beat the Topper' invite (button) to active members."""
        from . import growth
        mem = Members()
        data = growth.build_daily_challenge(mem, self.bank)
        if not data:
            print("[challenge] no topper yesterday")
            return 0
        txt = growth.challenge_invite_text(data)
        sent = 0
        for uid in growth.active_members(mem):
            if uid == data["topper"]["uid"]:
                continue
            try:
                self.tg.send_message(uid, txt, buttons=[[("🥊 Challenge", "challenge:go")]])
                sent += 1
            except TelegramError:
                mem.mark_blocked(uid)
            if sent % 20 == 0:
                time.sleep(0 if self.dry else 1.1)
        print(f"[challenge] {sent} invites sent")
        return sent

    def district_league(self, channels=None):
        """Monday morning — weekly District League standings (fair: avg per
        player + participation), season table, promotion/relegation notes."""
        from . import league
        mem = Members()
        text = league.render_week(mem)
        if not text:
            print("[league] nothing this week")
            return 0
        for ch in channels or getattr(config, "CHAMPION_CHANNELS", ["CURRENT"]):
            try:
                self.tg.send_message(config.channel_chat_id(ch), text)
            except TelegramError as e:
                print(f"   [league] {ch} failed: {e}")
        return 1

    def hall_of_fame(self):
        """Last day of month 21:00 — monthly Hall of Fame to hub channel."""
        mem = Members()
        text = mem.monthly_hall_of_fame()
        try:   # league season close: promotion / relegation
            from . import league
            data = league._load()
            up, down = league.promote_relegate(data, datetime.now(config.IST).strftime("%Y%m"))
            if up or down:
                text = (text or "") + ("\n\n🏟 League: ⬆ " + ", ".join(up) + " · ⬇ " + ", ".join(down))
        except Exception as e:
            print(f"   [hof] league note: {e}")
        if not text:
            return 0
        for ch in getattr(config, "CHAMPION_CHANNELS", ["CURRENT"]):
            try:
                self.tg.send_message(config.channel_chat_id(ch), text)
            except TelegramError as e:
                print(f"   [hof] {ch} failed: {e}")
        return 1

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
        try:
            from .hooks import live_line, mystery_opener_line
            ll = live_line(self._members if getattr(self, "_members", None) else Members(), cfg.get("key", ""))
            if ll:
                lines.append(ll)
            lines.append(mystery_opener_line())
        except Exception:
            pass
        lines += [mode_note]
        try:
            from . import gate
            lines.append(gate.alert_block(self._members if getattr(self, "_members", None) else Members()))
        except Exception:
            lines.append("Points & ranks: /quiz in our bot ⭐")
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

    def post_previous_key(self, channels=None):
        """Post the previous round's Q-by-Q key report (from last_round.json)
        exactly once, right before a new round begins. Never raises."""
        try:
            snap = load_json(config.DATA / "last_round.json", {})
        except Exception:
            snap = {}
        if not snap or snap.get("key_posted"):
            return 0
        by_ch = snap.get("by_channel") or {}
        label = snap.get("label") or ""
        posted = 0
        for ch in (channels or config.PUBLIC_CHANNELS):
            qs = by_ch.get(ch) or []
            if not qs:
                continue
            try:
                stats = self._poll_stats_for(qs)
                self.tg.send_message(config.channel_chat_id(ch),
                                     "🔑 Previous round key — గత రౌండ్ సమాధానాలు\n" +
                                     build_round_report(qs, label, config.CHANNELS[ch], stats))
                posted += 1
                self.tg.polite_gap(not self.dry)
                # 🧠 only when MANY got it wrong: the question's own verified
                # explanation, Telugu + English. No lessons, no audio.
                try:
                    from .content import build_missed_explanations
                    mstats = {}
                    rid = snap.get("round_id")
                    if rid:
                        mstats = Members().round_question_stats(rid, ch)
                    expl = build_missed_explanations(qs, stats, mstats, config.CHANNELS[ch])
                    if expl:
                        self.tg.send_message(config.channel_chat_id(ch), expl)
                        self.tg.polite_gap(not self.dry)
                except Exception as e:
                    print(f"   [missed] {ch}: {e}")
            except Exception as e:
                print(f"   [prev_key] {ch}: {e}")
        try:
            snap["key_posted"] = True
            from .store import save_json_atomic
            save_json_atomic(config.DATA / "last_round.json", snap)
        except Exception:
            pass
        return posted

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

    def verify_questions(self, limit=120):
        """API-key audit: solve blind, compare key, audit Telugu; quarantine bad ones."""
        try:
            from .verifier import run
            return run(limit=limit, dry=self.dry)
        except Exception as e:
            print(f"   [verify] error (non-fatal): {e}")
            return {"error": str(e)}

    def harvest_pyq(self):
        """Nightly: download + ingest official previous-paper PDFs (pyq_papers.json)."""
        try:
            from .pyq import harvest
            return harvest(dry=self.dry, limit=6, llm=getattr(self, 'llm', None))
        except Exception as e:
            print(f"   [pyq] error (non-fatal): {e}")
            return {"error": str(e)}

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
        now = datetime.now(config.IST)
        gt = getattr(config, "GRAND_TEST_TIME", "09:00")
        gh, gm = map(int, gt.split(":"))
        is_grand = (now.weekday() == 6 and
                    abs((gh * 60 + gm) - (now.hour * 60 + now.minute) - slot_minutes) <= 1)
        if is_grand:
            n = getattr(config, "GRAND_TEST_QUESTIONS", 25)
        for ch in config.PUBLIC_CHANNELS:
            cfg = config.CHANNELS[ch]
            if is_grand and slot_minutes >= 5:
                msg = (f"🔔 {cfg['emoji']} 🏟 SUNDAY GRAND TEST — {slot_minutes} నిమిషాల్లో\n"
                       f"📝 {n} Q · Sections A→B→C · negative marking −⅓ · double points ⭐\n"
                       f"⏱ 1 min easy · 1.5 min hard — పెన్ను, పేపర్ సిద్ధం. Starts in {slot_minutes} min ✍️")
            elif is_grand:
                msg = (f"🚀 {cfg['emoji']} 🏟 GRAND TEST — 1 నిమిషంలో మొదలు! Section A first. All the best 🔥")
            elif slot_minutes >= 5:
                msg = (f"🔔 {cfg['emoji']} {cfg['subject']} Quiz — {slot_minutes} నిమిషాల్లో\n"
                       f"📋 {n} questions · exam-hall pace · one at a time\n"
                       f"⏱ 1 min easy · 1.5 min hard — పెన్ను, పేపర్ సిద్ధం చేసుకోండి\n"
                       f"Starts in {slot_minutes} min. Be ready ✍️")
            else:
                msg = (f"🚀 {cfg['emoji']} {cfg['subject']} Quiz — 1 నిమిషంలో మొదలు!\n"
                       f"Starting in 1 minute. Q1 arrives at the top of the minute. "
                       f"All the best 🔥")
            btn = None
            try:
                from . import gate
                mem = getattr(self, "_members", None) or Members()
                msg += "\n\n" + gate.alert_block(mem)
                btn = gate.cta_buttons()
            except Exception as e:
                print(f"   [gate] {e}")
            try:
                self.tg.send_message(config.channel_chat_id(ch), msg, buttons=btn)
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
