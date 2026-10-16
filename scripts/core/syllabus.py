#!/usr/bin/env python3
"""
STUDENTUP — 🗺️ PERSONAL SYLLABUS GRAPH

Prathi student ki thana exam syllabus graph + mastery map:
  • exam blueprint (subject weights) + bank topics = syllabus graph
  • student topic stats (answers nunchi) = mastery % per topic/subject
  • plan: weak topics focus, due reviews (spaced repetition), next round
    composition — 40% weak / 30% review / 30% fresh blueprint mix

Bot: /myplan  ·  API: GET /api/syllabus?uid=<id>
"""
from __future__ import annotations

from . import blueprint


def subject_of_topic(topic: str) -> str:
    return blueprint.subject_of({"topic": topic or "", "q_en": ""})


def exam_graph(bank, channel: str) -> dict:
    """channel syllabus: subject -> {weight, topics: {topic: bank_count}}"""
    bp = blueprint.blueprint()
    ch = (bp.get("channels") or {}).get(channel) or {}
    weights = ch.get("weights") or {"gk": 1.0}
    topics = {}
    for q in bank.by_channel(channel):
        s = blueprint.subject_of(q)
        topics.setdefault(s, {})
        t = q.get("topic", "") or "General"
        topics[s][t] = topics[s].get(t, 0) + 1
    return {"channel": channel, "exam": ch.get("exam", channel),
            "weights": weights, "subjects": topics}


def member_mastery(member: dict) -> dict:
    """topic stats -> {topic: {seen, correct, rate}, subject: {...}}"""
    topics = {}
    for t, st in ((member or {}).get("topics") or {}).items():
        total = int(st.get("total", 0))
        corr = int(st.get("correct", 0))
        if total:
            topics[t] = {"seen": total, "correct": corr,
                         "rate": round(corr / total, 2)}
    subjects = {}
    for t, v in topics.items():
        s = subject_of_topic(t)
        agg = subjects.setdefault(s, {"seen": 0, "correct": 0})
        agg["seen"] += v["seen"]
        agg["correct"] += v["correct"]
    for s, agg in subjects.items():
        agg["rate"] = round(agg["correct"] / agg["seen"], 2) if agg["seen"] else None
    return {"topics": topics, "subjects": subjects}


def plan(member: dict, bank, channel: str) -> dict:
    g = exam_graph(bank, channel)
    m = member_mastery(member)
    subj_rows = []
    for s, w in sorted(g["weights"].items(), key=lambda kv: -kv[1]):
        agg = m["subjects"].get(s)
        subj_rows.append({
            "subject": s, "exam_weight": w,
            "mastery": agg["rate"] if agg else None,
            "seen": agg["seen"] if agg else 0,
            "status": ("not started" if not agg else
                       "weak" if agg["rate"] < 0.5 else
                       "growing" if agg["rate"] < 0.75 else "strong"),
        })
    weak = sorted(
        ({"topic": t, **v} for t, v in m["topics"].items() if v["seen"] >= 2),
        key=lambda r: (r["rate"], -r["seen"]))[:3]
    un = {q.get("topic", "") for q in bank.unused(channel)}
    focus = [{"topic": w["topic"], "rate": w["rate"],
              "fresh_available": any(w["topic"].lower() in (u or "").lower()
                                     for u in un)}
             for w in weak]
    # 🛠️ FIX: reviews_due = due-only (mundhu anni cards count ayyevi)
    try:
        from datetime import datetime as _dt
        from . import config as _cfg
        _today = _dt.now(_cfg.IST).strftime("%Y-%m-%d")
    except Exception:
        _today = "9999-12-31"
    due = len([r for r in (member or {}).get("review", [])
               if str(r.get("due", "")) <= _today])
    return {"channel": channel, "exam": g["exam"], "subjects": subj_rows,
            "weak_topics": focus, "reviews_due": due,
            "overall_mastery": (
                round(sum(v["correct"] for v in m["topics"].values())
                      / max(1, sum(v["seen"] for v in m["topics"].values())), 2)
                if m["topics"] else None)}


def compose_personal_round(bank, member: dict, channel: str, n: int = 10) -> list:
    """40% weak-topic fresh · 30% due review · 30% blueprint-fresh mix.
    No-repeat rule from Bank (unused/mark_posted) as usual honoured."""
    m = member_mastery(member)
    weak_topics = [t for t, v in sorted(
        m["topics"].items(), key=lambda kv: kv[1]["rate"]) if v["seen"] >= 2][:4]
    out, used_ids = [], set()

    # 1) weak topics, fresh
    pool = bank.unused(channel)
    want_weak = max(1, int(round(0.4 * n)))
    for wt in weak_topics:
        if len(out) >= want_weak:
            break
        for q in pool:
            if q["id"] in used_ids:
                continue
            if wt in (q.get("topic", "") or "").lower():
                out.append(q)
                used_ids.add(q["id"])
                break

    # 2) due reviews (spaced repetition — re-ask missed questions)
    want_rev = int(round(0.3 * n))
    rev_added = 0
    for r in sorted((member or {}).get("review", []),
                    key=lambda r: r.get("due", "")):
        if rev_added >= want_rev or len(out) >= n:
            break
        q = bank.by_id(r.get("qid", ""))
        if q and q["id"] not in used_ids:
            out.append(q)
            used_ids.add(q["id"])
            rev_added += 1

    # 3) fill with a normal blueprint pick (marks posted itself)
    if len(out) < n:
        for q in bank.pick(channel, n - len(out)) or []:
            if q["id"] not in used_ids:
                out.append(q)
                used_ids.add(q["id"])
    if out:
        try:
            bank.mark_posted(channel, out)
        except Exception:
            pass
    return out[:n]


_ICON = {"weak": "🔴", "growing": "🟡", "strong": "🟢", "not started": "⚪"}


def plan_text(member: dict, bank, channel: str) -> str:
    p = plan(member, bank, channel)
    name = (member or {}).get("name") or "Student"
    L = [f"🗺️ *{name} — Personal Syllabus Plan ({p['exam']})*"]
    if p["overall_mastery"] is not None:
        L.append(f"Overall mastery: *{int(p['overall_mastery'] * 100)}%*")
    L.append("")
    for s in p["subjects"]:
        pct = "—" if s["mastery"] is None else f"{int(s['mastery'] * 100)}%"
        L.append(f"{_ICON[s['status']]} *{s['subject'].title()}* — mastery {pct} "
                 f"(exam weight {int(s['exam_weight'] * 100)}%, {s['seen']} answers)")
    if p["weak_topics"]:
        L.append("")
        L.append("🎯 *Focus topics (weak first):*")
        for w in p["weak_topics"]:
            L.append(f"   • {w['topic'].title()} — {int(w['rate'] * 100)}% correct"
                     + (" · fresh questions ready ✅" if w["fresh_available"] else ""))
    if p["reviews_due"]:
        L.append(f"\n🔁 *{p['reviews_due']} review(s) due* — tappina questions malli vastayi (spaced repetition).")
    L.append("\n/quiz adagandi — mee round ippudu weak topics nunchi ekkuva vasthundi! 🚀")
    return "\n".join(L)


if __name__ == "__main__":
    from .question_bank import Bank
    demo = {"name": "Demo", "topics": {}, "review": []}
    print(plan_text(demo, Bank(), "SSC"))
