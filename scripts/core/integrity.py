# -*- coding: utf-8 -*-
"""
🕵️ EXAM INTEGRITY — Live exam answer-pattern analysis (100X layer)

Per-student question/option shuffle valla direct copying kashtam,
kaani iddaru students OKKE wrong pattern ni follow aithe (e.g. okka
phone nunchi chusi rasedi groups) adhi data lo kanipistundi. Ee
module alanti patterns ni flag chestundi — proof ga kakunda
organiser review kosam signal ga.

Rules (deterministic, conservative — takkuva data unte flag cheyyam):
  • Shared-wrong overlap: iddaru ≥8 answers ichi, ≥4 wrong answers
    SAME question lo SAME wrong option choose chesi, wrong-pattern
    similarity ≥ 0.75 unte → collusion suspect pair.
  • Speed: exam ayipoyina tarvatha, anni answers < 2.5 sec/question
    average tho (joined→finish) unte → speed suspect (bot/guess ring
    review kosam matrame flag; auto-punish cheyyam).
"""
MIN_ANSWERS = 8
MIN_SHARED_WRONG = 4
SIM_THRESHOLD = 0.75


def _wrong_map(answers: dict, qs: list) -> dict:
    out = {}
    for idx, orig in (answers or {}).items():
        try:
            i = int(idx)
            q = qs[i]
        except Exception:
            continue
        if int(orig) != int(q.get("answer_index", -1)):
            out[i] = int(orig)
    return out


def analyze(entries: dict, qs: list) -> dict:
    """entries: {uid: {answers:{idx:orig}, joined_at, finished_at?}} —
    portal exam entries shape. Returns flags (empty = clean)."""
    entries = entries or {}
    wrongs, counts = {}, {}
    for uid, ent in entries.items():
        ans = (ent or {}).get("answers") or {}
        counts[str(uid)] = len(ans)
        wrong_map_result = _wrong_map(ans, qs or [])
        wrongs[str(uid)] = wrong_map_result
    pairs = []
    uids = [u for u in wrongs if counts.get(u, 0) >= MIN_ANSWERS]
    for i, a in enumerate(uids):
        for b in uids[i + 1:]:
            wa, wb = wrongs[a], wrongs[b]
            shared = [k for k in wa if k in wb and wa[k] == wb[k]]
            denom = max(1, min(len(wa), len(wb)))
            sim = len(shared) / denom
            if len(shared) >= MIN_SHARED_WRONG and sim >= SIM_THRESHOLD:
                pairs.append({"a": a, "b": b,
                              "shared_wrong": len(shared),
                              "similarity": round(sim, 2)})
    pairs.sort(key=lambda p: -p["similarity"])
    speed = []
    for uid, ent in entries.items():
        try:
            from datetime import datetime
            j = datetime.fromisoformat(str(ent.get("joined_at")))
            f = datetime.fromisoformat(str(ent.get("finished_at") or
                                           ent.get("last_answer_at") or ""))
            secs = (f - j).total_seconds()
            n_ans = len((ent or {}).get("answers") or {})
            if n_ans >= MIN_ANSWERS and 0 < secs < n_ans * 2.5:
                speed.append(str(uid))
        except Exception:
            continue
    return {"pairs": pairs, "speed_suspects": speed,
            "flagged_pairs": len(pairs), "students_checked": len(uids),
            "clean": not pairs and not speed}


def report_for_exam(exam_id: str) -> dict:
    """Portal store nunchi exam teesi analyze chestundi."""
    try:
        from . import portal
        d = portal._load()
        e = (d.get("exams") or {}).get(str(exam_id or ""))
        if not e:
            return {"error": "exam not found", "pairs": [],
                    "speed_suspects": [], "clean": True}
        rep = analyze(e.get("entries") or {}, e.get("qs") or [])
        rep["exam_id"] = e.get("id")
        rep["title"] = e.get("title", "")
        return rep
    except Exception as ex:
        return {"error": str(ex), "pairs": [], "speed_suspects": [],
                "clean": True}
