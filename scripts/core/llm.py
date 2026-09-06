#!/usr/bin/env python3
"""
STUDENTUP — MULTI-PROVIDER LLM ROTATOR
Uses EVERY key in env/.env, never wastes one.
Provider order: Groq (workhorse) -> DeepSeek -> OpenAI -> Gemini (all keys).
On 429 / 5xx / timeout -> next key / next provider (exponential backoff).
If ALL providers fail -> caller falls back gracefully (English-only / offline gen).
Stdlib HTTP (urllib); `requests` used if available.
"""
from __future__ import annotations

import os
import json
import time
import urllib.request
import urllib.error

from . import config

try:
    import requests
    _HAS_REQ = True
except Exception:
    _HAS_REQ = False

GROQ_MODEL = "openai/gpt-oss-120b"
DEEPSEEK_MODEL = "deepseek-chat"
OPENAI_MODEL = "gpt-4o-mini"
GEMINI_MODEL = "gemini-2.5-flash"
DIFY_API = "https://api.dify.ai/v1/chat-messages"


def _collect(prefixes, single=()):
    keys = []
    for single_name in single:
        v = os.environ.get(single_name, "")
        if v and v not in keys:
            keys.append(v)
    for k, v in os.environ.items():
        for p in prefixes:
            if k.startswith(p) and v and v not in keys:
                keys.append(v)
    return keys


class LLM:
    def __init__(self):
        config.load_env()
        e = os.environ
        # Every key family is accepted; collection de-duplicates, so
        # GEMINI_KEY_1 and GEMINI_API_KEY_1 holding the same value count once.
        self.groq = _collect(("GROQ_KEY_", "GROQ_API_KEY_"),
                             ("GROQ_KEY", "GROQ_API_KEY"))
        self.deepseek = _collect(("DEEPSEEK_KEY_", "DEEPSEEK_API_KEY_"),
                                 ("DEEPSEEK_KEY", "DEEPSEEK_API_KEY"))
        self.openai = _collect(("OPENAI_KEY_", "OPENAI_API_KEY_"),
                               ("OPENAI_KEY", "OPENAI_API_KEY"))
        self.gemini = _collect(("GEMINI_KEY_", "GEMINI_API_KEY_"),
                               ("GEMINI_KEY", "GEMINI_API_KEY"))
        self.dify = _collect(("DIFY_",), ("DIFY_APP_TOKEN", "DIFY_TOKEN",))
        self.health = {}

    def available(self) -> bool:
        return bool(self.groq or self.deepseek or self.openai
                    or self.gemini or self.dify)

    # ------------------------------------------------------------- HTTP post
    def _post_json(self, url: str, headers: dict, body: dict, timeout: int = 45):
        data = json.dumps(body).encode("utf-8")
        if _HAS_REQ:
            r = requests.post(url, headers=headers, data=data, timeout=timeout)
            return r.status_code, r.text
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8")

    def _track(self, tag, ok, err=""):
        h = self.health.setdefault(tag, {"ok": 0, "fail": 0, "err": ""})
        h["ok" if ok else "fail"] += 1
        if err:
            h["err"] = err[:120]

    # -------------------------------------------------------- provider calls
    def _groq(self, key, system, user):
        url = "https://api.groq.com/openai/v1/chat/completions"
        code, text = self._post_json(url, {"Authorization": f"Bearer {key}",
                                           "Content-Type": "application/json"},
                                     {"model": GROQ_MODEL, "temperature": 0.7,
                                      "messages": [{"role": "system", "content": system},
                                                   {"role": "user", "content": user}]})
        if code == 200:
            return json.loads(text)["choices"][0]["message"]["content"]
        raise RuntimeError(f"groq {code}: {text[:160]}")

    def _deepseek(self, key, system, user):
        url = "https://api.deepseek.com/chat/completions"
        code, text = self._post_json(url, {"Authorization": f"Bearer {key}",
                                           "Content-Type": "application/json"},
                                     {"model": DEEPSEEK_MODEL, "temperature": 0.7,
                                      "messages": [{"role": "system", "content": system},
                                                   {"role": "user", "content": user}]})
        if code == 200:
            return json.loads(text)["choices"][0]["message"]["content"]
        raise RuntimeError(f"deepseek {code}: {text[:160]}")

    def _openai(self, key, system, user):
        url = "https://api.openai.com/v1/chat/completions"
        code, text = self._post_json(url, {"Authorization": f"Bearer {key}",
                                           "Content-Type": "application/json"},
                                     {"model": OPENAI_MODEL, "temperature": 0.7,
                                      "messages": [{"role": "system", "content": system},
                                                   {"role": "user", "content": user}]})
        if code == 200:
            return json.loads(text)["choices"][0]["message"]["content"]
        raise RuntimeError(f"openai {code}: {text[:160]}")

    def _gemini(self, key, system, user):
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{GEMINI_MODEL}:generateContent?key={key}")
        code, text = self._post_json(url, {"Content-Type": "application/json"},
                                     {"contents": [{"parts": [{"text": system + "\n\n" + user}]}],
                                      "generationConfig": {"temperature": 0.7}})
        if code == 200:
            d = json.loads(text)
            return d["candidates"][0]["content"]["parts"][0]["text"]
        raise RuntimeError(f"gemini {code}: {text[:160]}")

    def _dify(self, key, system, user):
        """Dify app token — blocking chat-messages endpoint (extra provider)."""
        code, text = self._post_json(DIFY_API, {"Authorization": f"Bearer {key}",
                                                "Content-Type": "application/json"},
                                     {"inputs": {}, "query": system + "\n\n" + user,
                                      "response_mode": "blocking",
                                      "conversation_id": "",
                                      "user": "studentup-bot"})
        if code == 200:
            return json.loads(text).get("answer", "")
        raise RuntimeError(f"dify {code}: {text[:160]}")

    # ------------------------------------------------------------- public chat
    def chat(self, system: str, user: str, retries_per_key: int = 1):
        """Try every provider/key in order. Return text, or None if all fail."""
        chain = ([("groq", k, self._groq) for k in self.groq] +
                 [("deepseek", k, self._deepseek) for k in self.deepseek] +
                 [("openai", k, self._openai) for k in self.openai] +
                 [("gemini", k, self._gemini) for k in self.gemini] +
                 [("dify", k, self._dify) for k in self.dify])
        last_err = None
        for name, key, fn in chain:
            tag = f"{name}:{key[-6:]}"
            for _ in range(retries_per_key):
                try:
                    out = fn(key, system, user)
                    if out and out.strip():
                        self._track(tag, True)
                        return out.strip()
                except Exception as e:
                    last_err = str(e)
                    self._track(tag, False, str(e))
                    time.sleep(1.2)
        print(f"   [LLM] all providers failed ({len(chain)} keys): {last_err}")
        return None

    def health_report(self) -> str:
        lines = [f"LLM keys — Groq:{len(self.groq)} DeepSeek:{len(self.deepseek)} "
                 f"OpenAI:{len(self.openai)} Gemini:{len(self.gemini)} "
                 f"Dify:{len(self.dify)}"]
        for tag, h in sorted(self.health.items()):
            status = "OK" if h["ok"] and not h["fail"] else ("DEGRADED" if h["fail"] else "idle")
            lines.append(f"  {tag} {status} ok={h['ok']} fail={h['fail']} {h['err']}")
        return "\n".join(lines)


if __name__ == "__main__":
    llm = LLM()
    print(llm.health_report())
    if llm.available():
        r = llm.chat("You are a helpful tutor.", "Say 'StudentUp ready' in one short line.")
        print("CHAT =>", r)
