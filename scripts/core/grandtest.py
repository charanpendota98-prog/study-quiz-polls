"""
Sunday Grand Test — weekly real-exam-style mock built from the week.

Composition (per channel, default 25 Q):
  * ~60 % REVISION  — questions posted Mon–Sat of this week, ranked by how
    many players got them WRONG (the toughest ones come back), so the test
    rewards people who followed the daily rounds and revised.
  * ~40 % FRESH     — never-posted questions, hard/medium-weighted, picked
    through the normal no-repeat bank (so they are consumed exactly once).
  * Ordered like a real paper: Section A (easy) → Section B (medium) →
    Section C (hard); each question keeps its difficulty timer.

Scoring (real-exam style): +1 correct, −⅓ wrong (negative marking),
unattempted 0.  Points: every correct answer is worth DOUBLE on Sunday and
the podium bonus is 🥇+100 · 🥈+60 · 🥉+40 · district topper +25.

All state lives in data/week_rounds.json (rolling log of posted question
ids per day per channel, capped at 14 days).
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from . import config
from .store import load_json, save_json_atomic

WEEK_LOG = config.DATA / "week_rounds.json"
WEEK_LOG_DAYS = 35          # keeps a month for the Monthly Mega Test (still tiny: ids only)
GRAND_Q = int(getattr(config, "GRAND_TEST_QUESTIONS", 25) or 25)
REVISION_SHARE = 0.6
NEG_MARK = 1.0 / 3.0
PODIUM = (100, 60, 40)
DISTRICT_TOP_BONUS = 25
GRAND_PREFIX = "G"          # round_id prefix so the bot / reports can tell
MEGA_Q = int(getattr(config, "MEGA_TEST_QUESTIONS", 50) or 50)
MEGA_PODIUM = (300, 200, 120)


def is_last_sunday(now=None) -> bool:
    import calendar
    now = now or datetime.now(config.IST)
    last = calendar.monthrange(now.year, now.month)[1]
    return now.weekday() == 6 and now.day + 7 > last


def mega_teaser(cfg, when=None) -> str:
    now = when or datetime.now(config.IST)
    t = getattr(config, "GRAND_TEST_TIME", "09:00")
    return "\n".join([
        f"{cfg['emoji']} 🏆 రేపు MONTHLY MEGA TEST — {now.strftime('%B')} Final · {t} AM",
        f"📝 {MEGA_Q} Q · ఈ నెల మొత్తం toughest questions + కొత్తవి · negative marking",
        f"⭐ correct ×3 points · 🥇+{MEGA_PODIUM[0]} 🥈+{MEGA_PODIUM[1]} 🥉+{MEGA_PODIUM[2]} · Hall of Fame entry 🏛",
        "నెల మొత్తం revise చేసుకోండి — ఇది నెల final 🔥",
    ])


# ----------------------------------------------------------------- week log
def log_round(channel: str, qids, when=None) -> None:
    """Append today's posted question ids for a channel (called by the engine
    after every daily round). Rolling 14-day window — never grows."""
    now = when or datetime.now(config.IST)
    day = now.strftime("%Y-%m-%d")
    data = load_json(WEEK_LOG, {})
    d = data.setdefault(day, {})
    lst = d.setdefault(channel, [])
    for q in qids:
        if q not in lst:
            lst.append(q)
    cutoff = (now - timedelta(days=WEEK_LOG_DAYS)).strftime("%Y-%m-%d")
    for k in [k for k in data if k < cutoff]:
        data.pop(k, None)
    save_json_atomic(WEEK_LOG, data)


def week_qids(channel: str, days: int = 6, now=None):
    """Question ids posted to `channel` in the previous `days` days
    (excluding today), oldest first, de-duplicated."""
    now = now or datetime.now(config.IST)
    data = load_json(WEEK_LOG, {})
    out, seen = [], set()
    for i in range(days, 0, -1):
        day = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        for q in data.get(day, {}).get(channel, []):
            if q not in seen:
                seen.add(q)
                out.append(q)
    return out


# ------------------------------------------------------------- composition
def _difficulty(q):
    try:
        from .blueprint import difficulty_of
        return difficulty_of(q)
    except Exception:
        return (q.get("difficulty") or "medium").lower()


def _order_like_paper(qs):
    rank = {"easy": 0, "medium": 1, "hard": 2}
    return sorted(qs, key=lambda q: rank.get(_difficulty(q), 1))


def compose_grand_test(bank, channel: str, n: int = GRAND_Q, lb=None,
                       now=None, rng=None, days: int = 6):
    """Return (questions, meta). Revision questions are re-asked on purpose
    (this is the weekly revision test); fresh ones go through bank.pick so
    the permanent no-repeat store still applies to them."""
    rng = rng or random.Random(f"{channel}|{(now or datetime.now(config.IST)).date()}")
    n_rev_target = int(round(n * REVISION_SHARE))
    week_ids = week_qids(channel, days=days, now=now)
    if not week_ids:                       # first week: fall back to recent history
        used = getattr(bank, "used", {}).get(channel, [])
        week_ids = list(dict.fromkeys(used[-6 * config.POLLS_PER_SLOT * 2:]))
    pool = [bank.by_id(qid) for qid in week_ids]
    pool = [q for q in pool if q]
    # rank: lowest correct-% first (most people missed it), then hard first
    stats = {}
    if lb is not None:
        try:
            stats = lb.stats_by_qid(set(q["id"] for q in pool))
        except Exception:
            stats = {}

    def miss_rate(q):
        s = stats.get(q["id"])
        if not s or not s.get("total"):
            return 0.5
        return 1.0 - s["correct"] / s["total"]

    hard_rank = {"hard": 0, "medium": 1, "easy": 2}
    pool.sort(key=lambda q: (-miss_rate(q), hard_rank.get(_difficulty(q), 1), rng.random()))
    # topic diversity among revision picks
    revision, topics = [], {}
    for q in pool:
        if len(revision) >= n_rev_target:
            break
        t = q.get("topic", "")
        if topics.get(t, 0) >= 3:
            continue
        topics[t] = topics.get(t, 0) + 1
        revision.append(q)
    n_fresh = n - len(revision)
    fresh = []
    if n_fresh > 0:
        try:
            fresh = bank.pick(channel, n_fresh)
        except Exception as e:
            print(f"   [grand] {channel}: fresh pick note: {e}")
            fresh = []
    qs = _order_like_paper(revision + fresh)
    for q in qs:
        q = q  # keep original dicts; tag lightly for the opener/report
    rev_ids = {q["id"] for q in revision}
    for q in qs:
        q["_grand_revision"] = q["id"] in rev_ids
    meta = {"revision": len(revision), "fresh": len(fresh), "total": len(qs),
            "sections": {d: sum(1 for q in qs if _difficulty(q) == d)
                         for d in ("easy", "medium", "hard")}}
    return qs, meta


# ------------------------------------------------------------------ scoring
def marks(correct: int, total: int) -> float:
    wrong = max(0, total - correct)
    return round(correct - NEG_MARK * wrong, 2)


def grand_rows(members, round_id: str, channel: str, limit: int = 10):
    """Ranked rows with negative-marking score. Returns (rows, n_players)."""
    rows, n = members.round_top(round_id, channel, limit=10_000)
    for r in rows:
        r["marks"] = marks(r["correct"], r["total"])
        r["wrong"] = max(0, r["total"] - r["correct"])
    rows.sort(key=lambda r: (-r["marks"], -r["correct"], r["last"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows[:limit], n, rows


def settle_grand(members, round_id: str, channel: str, mega: bool = False):
    """Sunday bonuses: double points per correct, big podium, district top.
    Mega (monthly): triple points, bigger podium, mega_wins for Hall of Fame."""
    top, n, all_rows = grand_rows(members, round_id, channel)
    if not all_rows:
        return {}
    awarded, seen_d = {}, set()
    podium = MEGA_PODIUM if mega else PODIUM
    for r in all_rows:
        m = members._get(r["uid"])
        bonus = r["correct"] * (2 if mega else 1)   # ×3 / ×2 incl. the +1 already given
        i = r["rank"] - 1
        if i < len(podium) and n >= 3:
            bonus += podium[i]
            if i == 0:
                key = "mega_wins" if mega else "grand_wins"
                m[key] = m.get(key, 0) + 1
        d = r.get("district")
        if d and d not in seen_d:
            seen_d.add(d)
            if sum(1 for x in all_rows if x.get("district") == d) >= 2:
                bonus += DISTRICT_TOP_BONUS
        if bonus:
            m["points"] = m.get("points", 0) + bonus
            awarded[r["uid"]] = bonus
    try:
        members.kv.save()
    except Exception:
        pass
    return awarded


def render_grand_top(members, round_id: str, channel: str, cfg=None, n_q: int = GRAND_Q,
                     limit: int = 10, when=None, mega: bool = False):
    from . import districts as D
    top, n_players, all_rows = grand_rows(members, round_id, channel, limit)
    if not top:
        return ""
    now = when or datetime.now(config.IST)
    head = f"{cfg['emoji']} " if cfg else ""
    medals = ["🥇", "🥈", "🥉"] + [f"{i}." for i in range(4, limit + 1)]
    title = (f"🏆 MONTHLY MEGA TEST — {now.strftime('%B')} FINAL RESULT" if mega
             else f"🏟 SUNDAY GRAND TEST — RESULT · {now.strftime('%d %b %Y')}")
    lines = [f"{head}{title}",
             f"📝 {n_q} Q · +1 correct · −⅓ wrong (negative marking) · 👥 {n_players} appeared",
             ""]
    dist_count, dist_marks = {}, {}
    for i, r in enumerate(top):
        d = r.get("district", "")
        dte = D.telugu_name(d) if d else ""
        place = f" · {d} ({dte})" if d and dte and dte != d else (f" · {d}" if d else "")
        lines.append(f"{medals[i]} {r['name'][:24]}{place} — {r['marks']:g}/{n_q} "
                     f"({r['correct']}✅ {r['wrong']}❌)")
    for r in all_rows:
        d = r.get("district")
        if d:
            dist_count[d] = dist_count.get(d, 0) + 1
            dist_marks[d] = dist_marks.get(d, 0.0) + r["marks"]
    # cut-offs like a real notification
    scores = sorted((r["marks"] for r in all_rows), reverse=True)
    if len(scores) >= 5:
        k10 = max(1, len(scores) // 10)
        k50 = max(1, len(scores) // 2)
        lines += ["", f"📊 Cut-off — Top 10%: {scores[k10 - 1]:g} · Top 50%: {scores[k50 - 1]:g} · "
                      f"Average: {sum(scores) / len(scores):.1f}"]
    if dist_count:
        best = sorted(((dist_marks[d] / dist_count[d], dist_count[d], d) for d in dist_count
                       if dist_count[d] >= 2), reverse=True)
        if best:
            avg, cnt, d = best[0]
            lines.append(f"👑 District of the week: {d} ({D.telugu_name(d)}) — avg {avg:.1f} · {cnt} players")
        top_d = sorted(dist_count.items(), key=lambda kv: -kv[1])[:5]
        lines.append("📍 " + " · ".join(f"{d} {c}" for d, c in top_d))
    bonus_line = (f"🎁 Mega bonus: correct ×3 pts · 🥇+{MEGA_PODIUM[0]} 🥈+{MEGA_PODIUM[1]} 🥉+{MEGA_PODIUM[2]} · "
                  f"district topper +25 · 🏛 Hall of Fame" if mega else
                  "🎁 Sunday bonus: correct ×2 pts · 🥇+100 🥈+60 🥉+40 · district topper +25")
    lines += ["", bonus_line,
              "మీ పేరు + జిల్లా ఇక్కడ రావాలంటే → bot లో /start, ఒక్కసారి register 📝"]
    return "\n".join(lines)


def opener(cfg, meta, total_secs_text: str, mega: bool = False) -> str:
    sec = meta.get("sections", {})
    head = (f"{cfg['emoji']} 🏆 MONTHLY MEGA TEST — {cfg['subject']} · నెల final" if mega
            else f"{cfg['emoji']} 🏟 SUNDAY GRAND TEST — {cfg['subject']}")
    span = "ఈ నెల" if mega else "ఈ వారం"
    pts = (f"⭐ Mega: correct ×3 points · 🥇+{MEGA_PODIUM[0]} 🥈+{MEGA_PODIUM[1]} 🥉+{MEGA_PODIUM[2]}" if mega
           else "⭐ Sunday: correct ×2 points · 🥇+100 🥈+60 🥉+40")
    return "\n".join([
        head,
        f"📝 {meta['total']} ప్రశ్నలు · {meta['revision']} {span} revision (toughest ones) · {meta['fresh']} కొత్తవి",
        f"📑 Section A easy {sec.get('easy', 0)} → B medium {sec.get('medium', 0)} → C hard {sec.get('hard', 0)}",
        f"⏱ ఒక్కో ప్రశ్న 1–1.5 నిమిషాలు · మొత్తం ≈ {total_secs_text}",
        "🧮 Marking: +1 correct · −⅓ wrong · skip = 0 (real exam style)",
        pts,
        "మీరు answer చేసిన తర్వాతే ✅/❌ కనిపిస్తుంది — key shows only after YOU answer",
        "All the best — పెన్ను, పేపర్ సిద్ధం ✍️",
    ])


def teaser(cfg, when=None) -> str:
    now = when or datetime.now(config.IST)
    day = (now + timedelta(days=1)).strftime("%d %b")
    t = getattr(config, "GRAND_TEST_TIME", "09:00")
    return "\n".join([
        f"{cfg['emoji']} 🏟 రేపు SUNDAY GRAND TEST — {day} · {t} AM",
        f"📝 {GRAND_Q} Q · ఈ వారం toughest questions revision + కొత్తవి · negative marking",
        "⭐ Double points · 🥇+100 🥈+60 🥉+40 · District of the week 👑",
        "ఈ వారం rounds ఒకసారి revise చేసుకోండి — Top-10 లో మీ పేరు + జిల్లా రావాలి 🔥",
    ])
