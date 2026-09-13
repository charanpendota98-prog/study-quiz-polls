#!/usr/bin/env python3
"""
STUDENTUP — TELEGRAM BOT API CLIENT
Stdlib-only (urllib) with automatic fallback to `requests` if present.
- sendQuiz  (native quiz poll, correct_option_index => instant feedback)
- sendMessage (bilingual text / digest / jobs / reminders)
- getUpdates (poll-answer listener for leaderboard)
- Exponential-backoff retry on 429 / 5xx; hard-fail on 400/401/403.
- DRY mode: logs the payload instead of posting (safe for tests / sandbox).
"""
from __future__ import annotations

import json
import time
import random
import urllib.request
import urllib.parse
import urllib.error
from typing import Optional

from . import config

try:
    import requests  # optional
    _HAS_REQUESTS = True
except Exception:
    _HAS_REQUESTS = False

API = "https://api.telegram.org/bot{token}/{method}"


class TelegramError(RuntimeError):
    pass


class Telegram:
    def __init__(self, token: str = "", dry: Optional[bool] = None):
        self.token = token or config.BOT_TOKEN
        self.dry = config.DRY if dry is None else dry
        self.session = requests.Session() if _HAS_REQUESTS else None
        self._offset = None

    # ------------------------------------------------------------------ core
    def _call(self, method: str, payload: dict, timeout: int = 30):
        # Dry run short-circuits BEFORE requiring a token (sandbox/CI safe).
        if self.dry:
            print(f"   [DRY] {method} -> {payload.get('chat_id')} :: "
                  f"{str(payload.get('question') or payload.get('text'))[:80]!r}")
            res = {"message_id": -1, **payload}
            if method == "sendPoll":              # fake poll id so DM-mirroring/score chain is testable
                import uuid
                res["poll"] = {"id": "dry-" + uuid.uuid4().hex[:12]}
            return {"ok": True, "dry": True, "result": res}
        if not self.token:
            raise TelegramError("BOT_TOKEN not set (put it in env/.env)")
        url = API.format(token=self.token, method=method)
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}

        if False:
            preview = {k: (v if k != "options" else v) for k, v in payload.items()}
            print(f"   [DRY] {method} -> {payload.get('chat_id')} :: "
                  f"{str(payload.get('question') or payload.get('text'))[:70]!r}")
            return {"ok": True, "dry": True, "result": {"message_id": -1, **payload}}

        backoff = 2
        for attempt in range(5):
            try:
                if self.session:
                    r = self.session.post(url, data=data, headers=headers, timeout=timeout)
                    code, body = r.status_code, r.text
                else:
                    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
                    with urllib.request.urlopen(req, timeout=timeout) as resp:
                        code, body = resp.status, resp.read().decode("utf-8")
                try:
                    parsed = json.loads(body)
                except json.JSONDecodeError:
                    parsed = {"ok": False, "description": body[:200]}
                if code == 200 and parsed.get("ok"):
                    return parsed
                desc = str(parsed.get("description", body))
                # Fatal client errors — don't retry
                if code in (400, 401, 403, 404) or "chat not found" in desc.lower() \
                        or "unauthorized" in desc.lower() or "not enough rights" in desc.lower() \
                        or "need administrator" in desc.lower():
                    raise TelegramError(f"{method} fatal {code}: {desc}")
                # Retry on 429 / 5xx
                wait = backoff
                ra = (parsed.get("parameters") or {}).get("retry_after") if isinstance(parsed, dict) else None
                if isinstance(ra, (int, float)) and ra > 0:
                    wait = min(float(ra) + 0.5, 60)
                elif "retry_after" in desc.lower():
                    try:
                        wait = float(desc.split("retry_after")[1].split()[0].strip(":()"))
                    except Exception:
                        pass
                print(f"   [retry {attempt+1}] {method} {code}: {desc[:120]} (sleep {wait}s)")
                time.sleep(wait)
                backoff = min(backoff * 2, 30)
            except urllib.error.URLError as e:
                if attempt == 4:
                    raise TelegramError(f"{method} network error: {e}")
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)
        raise TelegramError(f"{method} failed after retries")

    # ------------------------------------------------------------- high-level
    def send_quiz(self, chat_id: str, question: str, options: list,
                  correct_index: int, explanation: str = "",
                  open_period=None, with_explanation: bool = True) -> dict:
        """Native Telegram quiz poll.

        Instant mode (default): correct_option_id + explanation → Telegram
        shows ✅/❌ immediately after the user votes.
        Delayed mode: still sets correct_option_id (so Telegram marks right/
        wrong) but omits explanation; Engine posts a full answer-key later.
        """
        if len(options) < 2:
            raise TelegramError("quiz needs >=2 options")
        payload = {
            "chat_id": chat_id,
            "question": question,
            "options": [{"text": o} for o in options],
            "type": "quiz",
            "is_anonymous": True,
            "allows_multiple_answers": False,
            "correct_option_id": int(correct_index),
        }
        # open_period → Telegram auto-closes and REVEALS the key to everyone.
        # Only set when POLL_AUTO_CLOSE is explicitly on.
        if open_period and getattr(config, "POLL_AUTO_CLOSE", False):
            payload["open_period"] = int(open_period)
        if with_explanation and explanation.strip():
            payload["explanation"] = explanation[:config.TG_POLL_EXPLANATION_MAX]
        return self._call("sendPoll", payload)

    def answer_callback(self, callback_id: str, text: str = "") -> dict:
        return self._call("answerCallbackQuery", {"callback_query_id": callback_id, "text": text[:200]})

    def send_photo(self, chat_id: str, data: bytes, caption: str = "", filename: str = "card.png") -> dict:
        """Upload a PNG (rank card) via multipart/form-data — stdlib only."""
        if self.dry:
            print(f"   [DRY] sendPhoto -> {chat_id} :: {filename} ({len(data)} bytes)")
            return {"ok": True, "result": {}}
        import uuid, urllib.request
        boundary = "----StudentUp" + uuid.uuid4().hex
        parts = []
        for k, v in (("chat_id", str(chat_id)), ("caption", caption[:1000])):
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
        parts.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; "
                      f"filename=\"{filename}\"\r\nContent-Type: image/png\r\n\r\n").encode() + data + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        req = urllib.request.Request(API.format(token=self.token, method="sendPhoto"), data=b"".join(parts),
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            raise TelegramError(f"sendPhoto: {e}")

    def download_file(self, file_id: str, max_bytes: int = 2_000_000) -> bytes:
        """getFile + fetch bytes (small text/json uploads)."""
        if self.dry:
            return b""
        res = self._call("getFile", {"file_id": file_id})
        path = (res.get("result") or {}).get("file_path")
        if not path:
            raise TelegramError("getFile: no file_path")
        import urllib.request
        url = f"https://api.telegram.org/file/bot{self.token}/{path}"
        with urllib.request.urlopen(url, timeout=60) as r:
            return r.read(max_bytes)

    def send_document(self, chat_id: str, filename: str, data: bytes, caption: str = "") -> dict:
        """Upload a small file (CSV export) via multipart/form-data — stdlib only."""
        if self.dry:
            print(f"   [DRY] sendDocument -> {chat_id} :: {filename} ({len(data)} bytes)")
            return {"ok": True, "result": {}}
        import uuid
        boundary = "----StudentUp" + uuid.uuid4().hex
        parts = []
        for k, v in (("chat_id", str(chat_id)), ("caption", caption[:1000])):
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
        parts.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; "
                      f"filename=\"{filename}\"\r\nContent-Type: "
                      f"{'application/pdf' if filename.lower().endswith('.pdf') else 'application/octet-stream'}\r\n\r\n").encode() + data + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        body = b"".join(parts)
        import urllib.request
        req = urllib.request.Request(API.format(token=self.token, method="sendDocument"), data=body,
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))

    def send_message(self, chat_id: str, text: str, disable_preview: bool = True,
                     parse_mode: str = "", buttons=None) -> dict:
        """buttons: list of rows, each row a list of (label, callback_data)."""
        payload = {"chat_id": chat_id, "text": text[:config.TG_MSG_MAX],
                   "disable_web_page_preview": disable_preview}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if buttons:
            payload["reply_markup"] = {"inline_keyboard": [
                [({"text": lab, "url": str(cb)[4:]} if str(cb).startswith("url:") else
                  {"text": lab, "callback_data": str(cb)[:64]}) for lab, cb in row] for row in buttons]}
        return self._call("sendMessage", payload)

    def get_updates(self, timeout: int = 0):
        payload = {"timeout": timeout, "allowed_updates": ["poll_answer", "poll", "message", "callback_query"]}
        if self._offset is not None:
            payload["offset"] = self._offset
        try:
            res = self._call("getUpdates", payload, timeout=timeout + 10)
        except TelegramError:
            return []
        out = res.get("result", [])
        if out:
            self._offset = out[-1]["update_id"] + 1
        return out

    def admin_notify(self, text: str):
        if config.ADMIN_ID:
            try:
                self.send_message(config.ADMIN_ID, "⚠️ " + text)
            except TelegramError as e:
                print(f"   [admin notify failed] {e}")

    @staticmethod
    def polite_gap(active=False):
        """2.2–3.2s gap between polls — never faster (Telegram spam-flag safety).

        In dry runs we skip the real sleep so tests run fast (caller passes the
        client's dry state via `active` = actually posting).
        """
        if not active:
            return
        time.sleep(random.uniform(config.POLL_GAP_MIN, config.POLL_GAP_MAX))
