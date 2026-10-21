# -*- coding: utf-8 -*-
"""🎓 440X: BOT BOARD SUBJECT TESTS — Telegram /boards flow.

The portal already had playable TS/AP board tests (420X), but a
student who lives in Telegram had no way to reach them. This
module is the bot-side remote control for the SAME honest stock:
``/boards`` -> board channel -> subject chips -> an inline-button
test whose questions, answers and explanations are served one at
a time in the chat.

Kept pure (no Telegram imports) so the complete flow is unit
testable; bot.py only checks registration and renders the
``(text, buttons)`` events returned by :func:`dispatch`.

Callback data (all well under Telegram's 64-byte limit)::

    bb:menu
    bb:chan:<channel-index>
    bb:full:<channel-index>
    bb:subj:<channel-index>:<subject-index>
    bb:ans:<run-id>:<question-index>:<choice-index>
    bb:quit:<run-id>

Strictness rules mirror portal 420X: a board test draws ONLY its
own channel's academic stock, a subject test draws ONLY that
subject, and unknown channels/subjects fail honestly instead of
silently falling back to the mixed bank. Every served question
passes the 280X ``poll_safe`` send-time shield (stripped markers,
balanced key position, leak refusal) before it is snapshotted, so
the stored ``answer_index`` always matches the displayed order.
Answers are scored exactly once (repeat/stale taps are refused)
and awarded through ``members.award_answer`` — the same points,
topic stats, brain and FSRS revision pipeline as bot polls.
"""
from __future__ import annotations

import random
import secrets
from collections import Counter

from . import config
from .store import load_json, now_iso, save_json_atomic

STORE_FILE = "board_bot_tests.json"
MAX_QUESTIONS = 10
MAX_RUNS = 100


# ------------------------------------------------------------------ stock
def _channels() -> list:
    """Canonical board channels (single source: portal 420X hub)."""
    from .portal import _ACADEMIC_HUB

    return list(_ACADEMIC_HUB)


def _subject_base(topic) -> str:
    from .portal import _subj_base

    return _subj_base(topic)


def _load_items(items=None) -> list:
    if items is not None:
        return list(items)
    try:
        from .question_bank import load_academic_questions

        return load_academic_questions()
    except Exception:
        return []


def catalog(items=None) -> list:
    """Board channels with honest totals + grouped subject stock."""
    pool = _load_items(items)
    rows = []
    for idx, (chan, label) in enumerate(_channels()):
        own = [q for q in pool if q.get("channel") == chan]
        subs = Counter(_subject_base(q.get("topic")) for q in own)
        subs.pop("", None)
        rows.append({
            "index": idx,
            "channel": chan,
            "label": label,
            "total": len(own),
            "subjects": [
                {"subject": s, "count": n}
                for s, n in sorted(subs.items(),
                                   key=lambda kv: (-kv[1], kv[0].lower()))
            ],
        })
    return rows


def readiness(items=None) -> dict:
    """440X go-live readiness: every board stocked + subject depth."""
    rows = catalog(items)
    return {
        "boards": len(rows),
        "questions": sum(r["total"] for r in rows),
        "subjects": sum(len(r["subjects"]) for r in rows),
        "empty": [r["label"] for r in rows if r["total"] <= 0],
        "ready": bool(rows) and all(r["total"] > 0 and r["subjects"]
                                    for r in rows),
    }


# ------------------------------------------------------------------ menus
def menu_text(items=None) -> str:
    r = readiness(items)
    lines = [
        "🎓 TS & AP Board Tests",
        f"{r['boards']} boards · {r['questions']} questions · "
        f"{r['subjects']} subject tests",
        "",
        "Board pick cheyyandi — subject test leda full board test "
        "ikkade, inline buttons tho play cheyachu.",
        "⤷ Pick a board — play a subject test or the full board "
        "test right here with inline buttons.",
    ]
    if r["empty"]:
        lines.append("⚠️ Stock pending: " + ", ".join(r["empty"]))
    return "\n".join(lines)


def menu_buttons(items=None) -> list:
    rows = catalog(items)
    out, row = [], []
    for r in rows:
        row.append((f"🎓 {r['label']} · {r['total']}Q",
                    f"bb:chan:{r['index']}"))
        if len(row) == 2:
            out.append(row)
            row = []
    if row:
        out.append(row)
    return out


def _row_for(channel, items=None):
    chan = str(channel or "").strip().upper()
    for r in catalog(items):
        if r["channel"] == chan:
            return r
    return None


def subject_text(channel, items=None) -> str:
    r = _row_for(channel, items)
    if not r:
        return ("⚠️ Aa board channel ledu. /boards nunchi valid board "
                "pick cheyyandi.")
    lines = [
        f"🎓 {r['label']} — {r['total']} questions",
        "",
        "Subject test pick cheyyandi, leda motham board test:",
        "⤷ Pick a subject test, or take the full board test:",
    ]
    if not r["subjects"]:
        lines.append("⚠️ Ee board ki inka subject stock ledu.")
    return "\n".join(lines)


def subject_buttons(channel, items=None) -> list:
    r = _row_for(channel, items)
    if not r:
        return [[("🎓 Boards", "bb:menu")]]
    out = [[(f"📚 Full Board Test · {r['total']}Q",
             f"bb:full:{r['index']}")]]
    row = []
    for sidx, s in enumerate(r["subjects"]):
        row.append((f"{s['subject']} · {s['count']}",
                    f"bb:subj:{r['index']}:{sidx}"))
        if len(row) == 2:
            out.append(row)
            row = []
    if row:
        out.append(row)
    out.append([("⬅️ Boards", "bb:menu")])
    return out


# ------------------------------------------------------------------ runs
def _store_path():
    # config.DATA is read at call time so tests can patch it.
    return config.DATA / STORE_FILE


def _load_runs() -> dict:
    d = load_json(_store_path(), {})
    runs = d.get("runs") if isinstance(d, dict) else None
    return runs if isinstance(runs, dict) else {}


def _save_runs(runs: dict) -> None:
    while len(runs) > MAX_RUNS:
        runs.pop(next(iter(runs)), None)
    save_json_atomic(_store_path(), {"runs": runs})


def _snapshot(q: dict) -> dict:
    return {
        "id": q.get("id") or "",
        "channel": q.get("channel") or "",
        "topic": q.get("topic") or "general",
        "q_en": q.get("q_en") or "",
        "q_te": q.get("q_te") or "",
        "options_en": list(q.get("options_en") or []),
        "options_te": list(q.get("options_te") or []),
        "answer_index": int(q.get("answer_index") or 0),
        "explanation_en": (q.get("explanation_en")
                           or q.get("explanation") or ""),
        "explanation_te": q.get("explanation_te") or "",
    }


def start_run(uid, channel, subject="", items=None, seed=""):
    """Start a strict board/subject run. Returns ``(ok, run|error)``."""
    row = _row_for(channel, items)
    if row is None:
        return False, ("Board test kosam valid board channel ivvandi "
                       "(TS_10TH / AP_INTER / TS_BTECH ...).")
    pool = [q for q in _load_items(items)
            if q.get("channel") == row["channel"]]
    subject = str(subject or "").strip()
    if subject:
        pool = [q for q in pool
                if _subject_base(q.get("topic")).lower()
                == subject.lower()]
        if not pool:
            return False, (f"{row['label']} {subject} ki inka board "
                           "questions levu — vere subject try cheyyandi.")
    if not pool:
        return False, (f"{row['label']} ki inka board questions levu — "
                       "stock vachaka malli try cheyyandi.")

    run_id = "BB-" + secrets.token_hex(4)
    rng = random.Random(seed or secrets.token_hex(8))
    candidates = list(pool)
    rng.shuffle(candidates)
    try:
        from .content import poll_safe
    except Exception:
        poll_safe = None
    picked = []
    for q in candidates:
        safe = poll_safe(q, seed=f"bb:{run_id}:{q.get('id') or ''}:{uid}") \
            if poll_safe else q
        if safe is None:
            continue
        picked.append(_snapshot(safe))
        if len(picked) >= MAX_QUESTIONS:
            break
    if not picked:
        return False, ("Ee test kosam safe questions ready ga levu — "
                       "malli try cheyyandi.")

    sidx = -1
    if subject:
        sidx = next((i for i, s in enumerate(row["subjects"])
                     if s["subject"].lower() == subject.lower()), -1)
    run = {
        "run_id": run_id,
        "uid": str(uid),
        "channel": row["channel"],
        "label": row["label"],
        "subject": subject,
        "channel_index": row["index"],
        "subject_index": sidx,
        "idx": 0,
        "answers": {},
        "correct": 0,
        "done": False,
        "abandoned": False,
        "created": now_iso(),
        "qs": picked,
    }
    runs = _load_runs()
    runs[run_id] = run
    _save_runs(runs)
    return True, run


def get_run(run_id):
    return _load_runs().get(str(run_id or ""))


def _telugu_first() -> bool:
    return bool(getattr(config, "TELUGU_FIRST", True))


def question_view(run):
    """Render the current question as a ``(text, buttons)`` event."""
    if not run or run.get("done"):
        return None
    qs = run.get("qs") or []
    idx = int(run.get("idx") or 0)
    if not (0 <= idx < len(qs)):
        return None
    q = qs[idx]
    tf = _telugu_first()
    head = (f"🎓 {run.get('label') or run.get('channel')} — "
            f"{run.get('subject') or 'Full Board Test'}")
    lines = [head, f"Question {idx + 1}/{len(qs)} · {q.get('topic') or ''}",
             ""]
    en = str(q.get("q_en") or "").strip()
    te = str(q.get("q_te") or "").lstrip("⤷").strip()
    if tf:
        lines += [x for x in (te, en) if x]
    else:
        lines += [x for x in (en, te) if x]
    try:
        from .content import build_options

        options = build_options(q, telugu_first=tf)
    except Exception:
        options = [str(o) for o in (q.get("options_en") or [])]
    buttons = [[(opt, f"bb:ans:{run['run_id']}:{idx}:{choice}")]
               for choice, opt in enumerate(options)]
    buttons.append([("⏹ Quit test", f"bb:quit:{run['run_id']}")])
    return "\n".join(lines), buttons


def _answer_texts(q: dict):
    ai = int(q.get("answer_index") or 0)
    en = q.get("options_en") or []
    te = q.get("options_te") or []
    return (str(en[ai]) if 0 <= ai < len(en) else "",
            str(te[ai]).lstrip("⤷").strip() if 0 <= ai < len(te) else "")


def answer_run(members, uid, run_id, qidx, choice, username=""):
    """Score one tap exactly once. Returns ``(ok, result|error)``."""
    try:
        qidx = int(qidx)
        choice = int(choice)
    except (TypeError, ValueError):
        return False, "Invalid answer."
    runs = _load_runs()
    run = runs.get(str(run_id or ""))
    if not run:
        return False, "Test session dorakaledu — /boards nunchi malli start cheyyandi."
    if str(run.get("uid")) != str(uid):
        return False, "Ee test meedi kadu — mee own test /boards nunchi start cheyyandi."
    total = len(run.get("qs") or [])
    if run.get("done"):
        return True, {"already_done": True, "done": True,
                      "score": run.get("correct", 0), "total_q": total}
    if str(qidx) in (run.get("answers") or {}):
        return True, {"already": True, "done": False,
                      "score": run.get("correct", 0), "total_q": total}
    if qidx != int(run.get("idx") or 0) or not (0 <= qidx < total):
        return False, "Ee question ippudu active ga ledu — kindi current question answer cheyyandi."

    q = run["qs"][qidx]
    if not (0 <= choice < len(q.get("options_en") or [])):
        return False, "Invalid option."
    correct = choice == int(q.get("answer_index") or 0)
    run.setdefault("answers", {})[str(qidx)] = choice
    run["correct"] = int(run.get("correct") or 0) + int(correct)
    run["idx"] = qidx + 1
    run["done"] = run["idx"] >= total

    award = {}
    if members is not None:
        try:
            award = members.award_answer(
                uid, username=username, correct=correct,
                topic=q.get("topic", ""), qid=q.get("id", "")) or {}
        except Exception:
            award = {}
    runs[str(run_id)] = run
    _save_runs(runs)

    ans_en, ans_te = _answer_texts(q)
    return True, {
        "correct": correct,
        "answer_index": int(q.get("answer_index") or 0),
        "answer_en": ans_en,
        "answer_te": ans_te,
        "explanation_en": q.get("explanation_en") or "",
        "explanation_te": q.get("explanation_te") or "",
        "score": run["correct"],
        "answered": len(run["answers"]),
        "total_q": total,
        "done": run["done"],
        "earned": award.get("earned", 0),
        "points": award.get("points"),
        "locked": award.get("locked", 0),
        "run": run,
    }


def feedback_text(run, result: dict) -> str:
    if result.get("correct"):
        lines = ["✅ Correct!"]
        if result.get("earned"):
            lines[0] += f" +{result['earned']} pts"
    else:
        lines = ["❌ Not this time."]
        ans = result.get("answer_te") or result.get("answer_en") or ""
        en = result.get("answer_en") or ""
        if ans:
            lines.append(f"✅ Correct answer: {ans}"
                         + (f" — {en}" if en and en != ans else ""))
    expl = str(result.get("explanation_te")
               or result.get("explanation_en") or "").strip()
    if expl:
        lines.append(f"💡 {expl}")
    lines.append(f"Score: {result.get('score', 0)}/{result.get('total_q', 0)}")
    if result.get("locked"):
        lines.append(f"🔒 {result['locked']} pts locked — registration "
                     "complete chesthe unlock avuthayi.")
    if result.get("done"):
        lines += ["", summary_text(run)]
    return "\n".join(lines)


def summary_text(run) -> str:
    total = len(run.get("qs") or [])
    answered = len(run.get("answers") or {})
    score = int(run.get("correct") or 0)
    pct = round(100 * score / total) if total else 0
    title = (f"{run.get('label') or run.get('channel')} — "
             f"{run.get('subject') or 'Full Board Test'}")
    if run.get("abandoned"):
        head = "⏹ Test stopped"
    elif answered >= total:
        head = "🏁 Test complete!"
    else:
        head = "🎓 Board test"
    lines = [head, title, f"Score: {score}/{total} ({pct}%)"]
    if answered < total:
        lines.append(f"Answered: {answered}/{total}")
    lines.append("⤷ /boards nunchi inko subject test play cheyachu.")
    return "\n".join(lines)


def completion_buttons(run) -> list:
    if int(run.get("subject_index", -1)) >= 0:
        retry = f"bb:subj:{run.get('channel_index')}:{run.get('subject_index')}"
        retry_label = "🔁 Same subject again"
    else:
        retry = f"bb:full:{run.get('channel_index')}"
        retry_label = "🔁 Full board again"
    return [[(retry_label, retry)],
            [("🎓 Boards", "bb:menu")]]


def quit_run(uid, run_id):
    runs = _load_runs()
    run = runs.get(str(run_id or ""))
    if not run or str(run.get("uid")) != str(uid):
        return None
    if not run.get("done"):
        run["done"] = True
        run["abandoned"] = True
        runs[str(run_id)] = run
        _save_runs(runs)
    return run


# ------------------------------------------------------------------ dispatch
def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _start_events(uid, channel, subject, items=None):
    ok, res = start_run(uid, channel, subject=subject, items=items)
    if not ok:
        return [(str(res), [[("🎓 Boards", "bb:menu")]])]
    view = question_view(res)
    intro = (f"🎓 {res['label']} — {subject or 'Full Board Test'} "
             f"start ayindi: {len(res['qs'])} questions.\n"
             "⤷ Answer each one with the buttons — points, topic "
             "stats and revision queue update automatically.")
    return [(intro, None), view] if view else [(intro, None)]


def dispatch(members, uid, value, username="", items=None) -> list:
    """Bot callback dispatch -> ``[(text, buttons|None), ...]``."""
    parts = str(value or "").split(":")
    action = parts[0] if parts else ""

    if action in ("", "menu"):
        return [(menu_text(items), menu_buttons(items))]

    if action == "chan" and len(parts) == 2:
        idx = _int_or_none(parts[1])
        chans = _channels()
        if idx is None or not (0 <= idx < len(chans)):
            return [("⚠️ Invalid board.", menu_buttons(items))]
        chan = chans[idx][0]
        return [(subject_text(chan, items), subject_buttons(chan, items))]

    if action == "full" and len(parts) == 2:
        idx = _int_or_none(parts[1])
        chans = _channels()
        if idx is None or not (0 <= idx < len(chans)):
            return [("⚠️ Invalid board.", menu_buttons(items))]
        return _start_events(uid, chans[idx][0], "", items=items)

    if action == "subj" and len(parts) == 3:
        idx = _int_or_none(parts[1])
        sidx = _int_or_none(parts[2])
        chans = _channels()
        if idx is None or not (0 <= idx < len(chans)):
            return [("⚠️ Invalid board.", menu_buttons(items))]
        row = _row_for(chans[idx][0], items)
        if row is None or sidx is None \
                or not (0 <= sidx < len(row["subjects"])):
            return [("⚠️ Invalid subject.", menu_buttons(items))]
        return _start_events(uid, row["channel"],
                             row["subjects"][sidx]["subject"], items=items)

    if action == "ans" and len(parts) == 4:
        ok, res = answer_run(members, uid, parts[1], parts[2], parts[3],
                             username=username)
        if not ok:
            return [(f"⚠️ {res}", None)]
        run = get_run(parts[1])
        if res.get("already_done"):
            return [("🏁 Ee test already complete ayindi.",
                     completion_buttons(run) if run else menu_buttons(items))]
        if res.get("already"):
            events = [("ℹ️ Ee question ki already answer icharu — "
                       "current question kindi undi.", None)]
            view = question_view(run) if run else None
            if view:
                events.append(view)
            return events
        run = res.get("run") or run
        if res.get("done"):
            return [(feedback_text(run, res), completion_buttons(run))]
        events = [(feedback_text(run, res), None)]
        view = question_view(run)
        if view:
            events.append(view)
        return events

    if action == "quit" and len(parts) == 2:
        run = quit_run(uid, parts[1])
        if not run:
            return [("⚠️ Test session dorakaledu.", menu_buttons(items))]
        return [(summary_text(run), completion_buttons(run))]

    return [("⚠️ Invalid board test button.", menu_buttons(items))]
