#!/usr/bin/env python3
"""
STUDENTUP — RESILIENCE LAYER  ("scraping fails → content still flows")

Three independent safety nets, all offline-safe and never raising:

1. collect_telegram()   Public Telegram exam channels (t.me/s/<name>) are a
                        second, unrelated content path from the websites. Quiz
                        polls arrive WITHOUT the key, so they are parked in
                        data/answer_pending.json and only released by
                        solve_pending(): two independent LLM passes must agree
                        with confidence >= 0.85. Never guessed, never posted
                        unverified. Text MCQs with keys go straight to the
                        normal collector pipeline.

2. supply_guard()       Measures unused (never-posted) questions per channel
                        vs. the daily need (2 rounds x round size). When the
                        runway drops below RUNWAY_DAYS it escalates, in order:
                          a. solve_pending()  (Telegram polls + parked items)
                          b. pyq.harvest()     (more official-paper PDFs)
                          c. collector.backfill(depth x2)
                          d. generator.top_up()  (curated-template top-up)
                        and notifies the admin with what it did.

3. status_text()        One-line health for /supply in the bot.

State files: data/answer_pending.json (capped), data/supply_state.json.
"""
from __future__ import annotations

import json
from datetime import datetime

from . import config
from .store import load_json, save_json_atomic

PENDING_FILE = config.DATA / "answer_pending.json"
STATE_FILE = config.DATA / "supply_state.json"
PENDING_CAP = 3000
RUNWAY_DAYS = 3           # escalate when < 3 days of unused questions remain
SOLVE_BATCH = 60
MIN_CONF = 0.85


def _now():
    return datetime.now(config.IST).strftime("%Y-%m-%d %H:%M")


# ------------------------------------------------------------------ telegram path
def collect_telegram(dry=False, llm=None, http_get=None, limit_channels=None):
    """Pull curated public Telegram channels. Keyed MCQs -> collector;
    keyless polls -> answer_pending. Returns stats; never raises."""
    stats = {"channels": 0, "keyed": 0, "parked_polls": 0, "pdf_hints": 0, "accepted": 0}
    try:
        from .tgsource import pull_all
        from . import collector
        raws, pdfs, s = pull_all(limit_channels=limit_channels, http_get=http_get, dry=dry)
        stats["channels"] = s["channels"]
        keyed = [r for r in raws if isinstance(r.get("answer_index"), int)]
        polls = [r for r in raws if r.get("answer_pending")]
        stats["keyed"], stats["parked_polls"], stats["pdf_hints"] = \
            len(keyed), len(polls), len(pdfs)
        # keyed text MCQs go through the standard pipeline (dedup, translate, verify)
        for r in keyed:
            lines = [f"Q1. {r['q_en']}"] + \
                    [f"{'ABCD'[i]}) {o}" for i, o in enumerate(r["options_en"])] + \
                    [f"Answer: {'ABCD'[r['answer_index']]}"]
            html_like = "<article>" + "".join(f"<p>{_esc(l)}</p>" for l in lines) + "</article>"
            try:
                res = collector.collect_daily(fixture=(html_like, r.get("title", "telegram"),
                                                       r.get("url", "")), dry=dry, llm=llm,
                                              stamp={"channel_pin": r.get("channel_hint"),
                                                     "source": "scraped", "exam": "",
                                                     "year": 0, "paper": "",
                                                     "paper_url": r.get("url", "")})
                stats["accepted"] += res.get("accepted", 0)
            except Exception:
                continue
        if polls and not dry:
            _park(polls)
        # PDF hints -> scout candidate queue (probed later, never trusted blindly)
        if pdfs and not dry:
            try:
                from . import scout
                c = scout._load_cands()
                for p in pdfs:
                    key = p["msg"]
                    if key not in c["items"]:
                        c["items"][key] = {"channel": p["channel"], "exam_hint": p["title"][:100],
                                           "year": scout._guess_year(p["title"]),
                                           "from": "telegram", "seen": _now(), "status": "hint"}
                scout._save_cands(c)
            except Exception:
                pass
    except Exception as e:
        stats["error"] = str(e)[:160]
    print(f"[telegram] {stats}")
    return stats


def _esc(s):
    import html
    return html.escape(str(s))


def _park(polls):
    d = load_json(PENDING_FILE, {"items": []})
    items = d.get("items", [])
    seen = {(i["q_en"].strip().lower()) for i in items}
    for p in polls:
        k = p["q_en"].strip().lower()
        if k in seen:
            continue
        items.append({"q_en": p["q_en"], "options_en": p["options_en"],
                      "channel": p.get("channel_hint", "CURRENT"), "url": p.get("url", ""),
                      "title": p.get("title", ""), "seen": _now(), "tries": 0,
                      "crowd_index": p.get("crowd_index"), "voters": p.get("voters", 0)})
        seen.add(k)
    items = items[-PENDING_CAP:]
    save_json_atomic(PENDING_FILE, {"count": len(items), "items": items})


# ------------------------------------------------------------------ solving
def solve_pending(limit=SOLVE_BATCH, llm=None, dry=False):
    """Two independent solves must agree (conf >= MIN_CONF) → question enters
    the normal pipeline with the agreed key. Otherwise stays parked (max 3
    tries, then dropped). Offline (no LLM) → no-op."""
    stats = {"tried": 0, "solved": 0, "disagree": 0, "dropped": 0, "llm": False}
    try:
        if llm is None:
            from .llm import LLM
            c = LLM()
            llm = c if c.available() else None
        if llm is None:
            print("[solve] no LLM key — polls stay parked")
            return stats
        stats["llm"] = True
        from .verifier import _solve
        from . import collector
        d = load_json(PENDING_FILE, {"items": []})
        items = d.get("items", [])
        keep = []
        for it in items:
            if stats["tried"] >= limit:
                keep.append(it)
                continue
            stats["tried"] += 1
            q = {"q_en": it["q_en"], "options_en": it["options_en"]}
            try:
                a = _solve(llm, q)
                b = _solve(llm, q)
            except Exception:
                a = b = None
            crowd = it.get("crowd_index")
            agree = a and b and a["answer_index"] == b["answer_index"] and \
                min(a["confidence"], b["confidence"]) >= MIN_CONF and \
                not ({"ambiguous", "multiple_correct", "no_correct"} & set(a["flags"] + b["flags"]))
            # crowd prior (hundreds of aspirants' votes): if it clearly disagrees with both models,
            # do not release — park for another try (models can slip on very recent CA).
            if agree and crowd is not None and crowd != a["answer_index"]:
                agree = False
                stats["crowd_veto"] = stats.get("crowd_veto", 0) + 1
            if agree:
                lines = [f"Q1. {it['q_en']}"] + \
                        [f"{'ABCD'[i]}) {o}" for i, o in enumerate(it["options_en"])] + \
                        [f"Answer: {'ABCD'[a['answer_index']]}"]
                if a.get("reason"):
                    lines.append(f"Explanation: {a['reason']}")
                html_like = "<article>" + "".join(f"<p>{_esc(l)}</p>" for l in lines) + "</article>"
                if not dry:
                    try:
                        collector.collect_daily(fixture=(html_like, it.get("title", "telegram"),
                                                         it.get("url", "")), llm=llm,
                                                stamp={"channel_pin": it.get("channel"),
                                                       "source": "scraped", "exam": "", "year": 0,
                                                       "paper": "", "paper_url": it.get("url", "")})
                    except Exception:
                        pass
                stats["solved"] += 1
            else:
                it["tries"] = it.get("tries", 0) + 1
                stats["disagree"] += 1
                if it["tries"] < 3:
                    keep.append(it)
                else:
                    stats["dropped"] += 1
        if not dry:
            save_json_atomic(PENDING_FILE, {"count": len(keep), "items": keep})
    except Exception as e:
        stats["error"] = str(e)[:160]
    print(f"[solve] {stats}")
    return stats


# ------------------------------------------------------------------ supply guard
def runway(bank=None):
    """{channel: (unused, days_left)} using the bot's used-store."""
    try:
        from .question_bank import load_bank
        qs = bank if bank is not None else load_bank()
    except Exception:
        qs = bank or []
    used = load_json(config.STORE_USED, {})
    per_day = 2 * int(getattr(config, "POLLS_PER_SLOT", 10))
    out = {}
    for ch in getattr(config, "PUBLIC_CHANNELS", list(getattr(config, "CHANNELS", {}))):
        ids = {str(i) for i in used.get(ch, [])}
        unused = sum(1 for q in qs if q.get("channel") == ch and str(q.get("id")) not in ids)
        out[ch] = (unused, round(unused / per_day, 1) if per_day else 99)
    return out


def supply_guard(dry=False, notify=None, actions=None):
    """Escalate until every channel has >= RUNWAY_DAYS of unused questions.
    `actions` may override the escalation callables (tests)."""
    st = load_json(STATE_FILE, {"runs": []})
    rw = runway()
    low = [ch for ch, (_, days) in rw.items() if days < RUNWAY_DAYS]
    report = {"low_before": low, "did": [], "low_after": low}
    if not low:
        _record(st, report, dry)
        return report
    acts = actions or _default_actions()
    for name, fn in acts:
        try:
            r = fn()
            report["did"].append({name: r if isinstance(r, (int, str, dict)) else str(r)[:80]})
        except Exception as e:
            report["did"].append({name: f"error {str(e)[:80]}"})
        rw = runway()
        report["low_after"] = [ch for ch, (_, d) in rw.items() if d < RUNWAY_DAYS]
        if not report["low_after"]:
            break
    _record(st, report, dry)
    if notify:
        try:
            notify("📦 Supply guard: low=" + ",".join(report["low_before"]) +
                   f" → after={','.join(report['low_after']) or 'all OK'} · steps={len(report['did'])}")
        except Exception:
            pass
    print(f"[supply] {report}")
    return report


def _default_actions():
    def a():
        return solve_pending()
    def b():
        from .pyq import harvest
        return harvest(limit=8)
    def c():
        from .collector import backfill
        return backfill()
    def d():
        from .generator import top_up
        added, errs = top_up()
        return {"added": len(added), "rejected": len(errs)}
    return [("solve_pending", a), ("pyq_harvest", b), ("backfill", c), ("top_up", d)]


def _record(st, report, dry):
    st["runs"] = (st.get("runs") or [])[-30:] + [{"on": _now(), **report}]
    st["last_runway"] = {k: v for k, v in runway().items()}
    if not dry:
        save_json_atomic(STATE_FILE, st)


def status_text():
    rw = runway()
    pend = load_json(PENDING_FILE, {"items": []}).get("items", [])
    lines = ["📦 Supply runway (unused questions → days):"]
    for ch, (n, d) in sorted(rw.items(), key=lambda kv: kv[1][1]):
        flag = "🔴" if d < RUNWAY_DAYS else ("🟡" if d < 2 * RUNWAY_DAYS else "🟢")
        lines.append(f"  {flag} {ch}: {n} → {d} d")
    lines.append(f"  ⏳ Telegram polls awaiting double-solve: {len(pend)}")
    try:
        from .tgsource import status_text as tg
        lines.append("  " + tg())
    except Exception:
        pass
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    a = sys.argv[1:]
    if not a or a[0] == "status":
        print(status_text())
    elif a[0] == "telegram":
        collect_telegram(dry="--dry" in a)
    elif a[0] == "solve":
        solve_pending(dry="--dry" in a)
    elif a[0] == "guard":
        supply_guard(dry="--dry" in a)
    else:
        print(__doc__)
