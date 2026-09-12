"""
CAMPUS — college events, college-vs-college wars, and the on-ground promo loop.

You walk into a college (or 3 colleges of a district) and want, within minutes:
  1. every student registered in the bot with their COLLEGE name attached,
  2. a timed exam (degree-friendly level: easy/medium, common syllabus),
  3. a live result: Top-10 + Rising-5 with names, college-vs-college winner,
  4. the full data (every student, score) sent to you, and
  5. every student pushed to join the Telegram / WhatsApp channels.

Flow
  admin  /campus new <event name> | <district> | <College A> ; <College B> ; …  [| questions] [| level]
         → event code CE-XXXX + one deep link per college
             t.me/<bot>?start=c<CODE>-<n>     (n = college index)
         (print/QR/WhatsApp that link to each college's students)
  student opens the link → bot tags college + district + event, asks ONLY name & phone
         (2 steps, exam/qualification default = "Degree") → "waiting room" message
  admin  /campus start <CODE>         → questions go to every joined student's DM (non-anonymous
                                        quiz polls, one at a time, timer by difficulty, like the war)
  auto   after last Q → result:  Top 10 · Rising 5 · per-college table (avg + participation) ·
                                 college winner · "join channel" CTA; admin gets full CSV + summary
  admin  /campus prize <CODE> <rank> <text>  → DM the gift/note to that rank (optional)
         /campus status <CODE>  /campus list   /campus csv <CODE>
Students keep their account; they are ordinary members afterwards (district set from the event),
so they land in District Wars, offers, etc.  All state: data/campus.json
"""
from __future__ import annotations

import random
import string
from datetime import datetime, timedelta

from . import config
from .store import load_json, save_json_atomic

PATH = config.DATA / "campus.json"
DEFAULT_Q = 15
LEVELS = {"easy": ("easy",), "medium": ("easy", "medium"), "hard": ("easy", "medium", "hard")}
Q_WINDOW = {"easy": 40, "medium": 55, "hard": 70}
GAP_SEC = 4
PTS_CORRECT, PTS_SPEED_MAX = 10, 5
PODIUM = {0: 100, 1: 60, 2: 40}
JOIN_PTS = 25                       # registering via a campus link
COLLEGE_WIN_PTS = 15


def _now():
    return datetime.now(config.IST)


def _load():
    d = load_json(PATH, {}) or {}
    d.setdefault("events", {}); d.setdefault("polls", {}); d.setdefault("by_uid", {})
    return d


def _save(d):
    save_json_atomic(PATH, d)


def _code(existing):
    while True:
        c = "CE-" + "".join(random.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=4))
        if c not in existing:
            return c


# ================================================================== events
def new_event(name, district, colleges, n_q=DEFAULT_Q, level="medium", created_by=""):
    d = _load()
    code = _code(d["events"])
    cols = [c.strip()[:40] for c in colleges if c.strip()][:12]
    if not cols:
        cols = ["General"]
    d["events"][code] = {"code": code, "name": name.strip()[:60], "district": district.strip(), "colleges": cols,
                         "n_q": max(5, min(int(n_q), 30)), "level": level if level in LEVELS else "medium",
                         "state": "open", "created": _now().isoformat(), "by": str(created_by),
                         "players": {}, "questions": [], "qi": 0, "answers": {}, "q_open": None, "q_close": None}
    _save(d)
    return code


def quick_event(college, district, n_q=DEFAULT_Q, level="easy", created_by=""):
    """One college, one command: /go <College> | <district>  → code + link + poster."""
    name = f"{college.strip()[:30]} × StudentUp Challenge"
    return new_event(name, district, [college], n_q, level, created_by)


def join_buttons():
    """Telegram + WhatsApp join buttons (URL buttons)."""
    rows = []
    tg_link = getattr(config, "BRAND_HANDLE", "") or ""
    if tg_link:
        rows.append([("📢 Telegram channel join", "url:" + (tg_link if tg_link.startswith("http") else "https://" + tg_link.lstrip("@")))])
    wa = getattr(config, "WHATSAPP_CHANNEL", "")
    if wa:
        rows.append([("💚 WhatsApp channel join", "url:" + wa)])
    return rows or None


def poster_text(code):
    """Plain text you paste into a WhatsApp group / show on the projector / print with any QR app."""
    d = _load()
    e = d["events"].get(code)
    if not e:
        return "Event not found."
    bot = config.BOT_USERNAME or "StudentUpBot"
    link = f"https://t.me/{bot}?start=c{code[3:]}-1"
    return "\n".join([
        f"🎓 {e['name']}",
        f"📍 {e['district']} · {e['n_q']} questions · phone లోనే exam",
        "",
        "1️⃣ ఈ link open చేయండి (లేదా QR scan):",
        f"   {link}",
        "2️⃣ పేరు + phone (30 seconds)",
        "3️⃣ 'Start' అనగానే Q1 వస్తుంది — ప్రతి Q కి timer ⏱",
        "",
        "🏆 Top 10 కి prizes · అందరికీ points (shops/coaching offers) · results పేర్లతో channel లో",
        "",
        f"QR: https://api.qrserver.com/v1/create-qr-code/?size=600x600&data={link}",
    ])

    d = _load()
    e = d["events"].get(code)
    if not e:
        return "Event not found."
    bot = config.BOT_USERNAME or "StudentUpBot"
    lines = [f"🎓 {e['name']} · {e['district']} · {e['n_q']} Q · level {e['level']}", "",
             "College links (print / QR / WhatsApp — students tap → auto college tag):"]
    for i, c in enumerate(e["colleges"], 1):
        lines.append(f"{i}. {c}\n   https://t.me/{bot}?start=c{code[3:]}-{i}")
    lines += ["", f"Start when the hall is ready: /campus start {code}", f"Status: /campus status {code}"]
    return "\n".join(lines)


def parse_start_arg(arg):
    """'cK7P2-2' → ('CE-K7P2', 2) or None."""
    if not arg or not arg.startswith("c") or "-" not in arg:
        return None
    body = arg[1:]
    code, _, idx = body.rpartition("-")
    if not code or not idx.isdigit():
        return None
    return "CE-" + code.upper(), int(idx)


def join(members, uid, code, college_idx, name_hint=""):
    """Deep-link join: tag member with college/event; returns (ok, text, needs_registration)."""
    d = _load()
    e = d["events"].get(code)
    if not e or e["state"] not in ("open",):
        return False, "ఈ event link ఇప్పుడు active లేదు — organiser ని అడగండి.", False
    college = e["colleges"][college_idx - 1] if 1 <= college_idx <= len(e["colleges"]) else e["colleges"][0]
    m = members._get(str(uid))
    m["college"] = college
    m["campus_event"] = code
    if not m.get("district"):
        m["district"] = e["district"]
        from . import districts as D
        m["state_code"] = D.state_of(e["district"]) or "AP"
    e["players"][str(uid)] = {"college": college, "name": m.get("name") or name_hint, "pts": 0, "correct": 0, "answered": 0,
                              "joined": _now().isoformat(), "first": None, "last": None}
    d["by_uid"][str(uid)] = code
    _save(d)
    members.kv.save()
    n_col = sum(1 for p in e["players"].values() if p["college"] == college)
    txt = (f"🎓 {e['name']}\n🏫 మీ college: {college} · మీరు #{n_col} from {college}\n"
           f"👥 Hall లో మొత్తం {len(e['players'])} students ready\n\n")
    if m.get("registered"):
        txt += "✅ మీరు ready! Exam start అయినప్పుడు ప్రశ్నలు ఇక్కడే వస్తాయి — phone ఇక్కడే ఉంచండి 📱"
        return True, txt, False
    txt += "📝 పేరు, phone మాత్రమే ఇవ్వండి (1 నిమిషం) → exam కి ready + %d points 🎁" % JOIN_PTS
    return True, txt, True


def on_registered(members, uid):
    """Called when a campus-tagged member completes registration → name sync + join bonus."""
    d = _load()
    code = d["by_uid"].get(str(uid))
    if not code or code not in d["events"]:
        return None
    e = d["events"][code]
    p = e["players"].get(str(uid))
    m = members._get(str(uid))
    if p:
        p["name"] = m.get("name") or p["name"]
        if not p.get("bonus"):
            p["bonus"] = True
            m["points"] = m.get("points", 0) + JOIN_PTS
            members.kv.save()
    _save(d)
    return e


def _compose(bank, e):
    """Degree-friendly common syllabus: GK, reasoning, aptitude, English, CA — no-repeat via bank."""
    from .districtwar import _subject
    from .blueprint import difficulty_of
    allowed = LEVELS[e["level"]]
    want = {"gk": 0.35, "reasoning": 0.25, "quant": 0.15, "english": 0.1, "ca": 0.15}
    n = e["n_q"]
    chosen, seen = [], set()
    order = ["SSC", "RAILWAY", "POLICE", "TSPSC", "APPSC", "BANKING", "DEFENCE", "CURRENT"]
    pools = {}
    for ch in order:
        try:
            pools[ch] = [q for q in bank.unused(ch) if difficulty_of(q) in allowed]
        except Exception:
            pools[ch] = []
    for subj, frac in want.items():
        k = max(1, round(n * frac))
        cands = []
        for ch in order:
            for q in pools[ch]:
                if q["id"] in seen:
                    continue
                if (subj == "ca" and ch == "CURRENT") or (subj != "ca" and _subject(q) == subj):
                    cands.append(q)
        random.shuffle(cands)
        for q in cands[:k]:
            chosen.append(q); seen.add(q["id"])
    for ch in order:
        for q in pools[ch]:
            if len(chosen) >= n:
                break
            if q["id"] not in seen:
                chosen.append(q); seen.add(q["id"])
    chosen = chosen[:n]
    by_ch = {}
    for q in chosen:
        by_ch.setdefault(q.get("channel", "CURRENT"), []).append(q)
    for ch, qs in by_ch.items():
        try:
            bank.mark_posted(ch, qs)
        except Exception:
            pass
    rank = {"easy": 0, "medium": 1, "hard": 2}
    chosen.sort(key=lambda q: rank.get(difficulty_of(q), 1))
    return [{"id": q["id"], "q_en": q.get("q_en", ""), "q_te": q.get("q_te", ""), "options_en": q.get("options_en", []),
             "options_te": q.get("options_te", []), "answer_index": int(q["answer_index"]),
             "window": Q_WINDOW.get(difficulty_of(q), 55), "channel": q.get("channel", "")} for q in chosen]


def start(bank, members, tg, code, now=None):
    now = now or _now()
    d = _load()
    e = d["events"].get(code)
    if not e:
        return False, "event not found"
    if e["state"] != "open":
        return False, f"event is {e['state']}"
    ready = {u: p for u, p in e["players"].items() if (members.members.get(u) or {}).get("registered")}
    if len(ready) < 2:
        return False, f"only {len(ready)} registered students joined"
    qs = _compose(bank, e)
    if len(qs) < 5:
        return False, f"not enough questions ({len(qs)})"
    e["players"] = ready
    e["questions"] = qs
    e["state"] = "question"; e["qi"] = 0; e["answers"] = {}
    e["started"] = now.isoformat()
    d["polls"] = {k: v for k, v in d["polls"].items() if v[0] != code}
    _save(d)
    _open_question(tg, d, e, 0, now)
    return True, {"players": len(ready), "questions": len(qs)}


def _open_question(tg, d, e, qi, now):
    from .content import build_question_text, build_options
    q = e["questions"][qi]
    cfg = {"emoji": "🎓", "name": e["name"], "name_te": e["name"], "subject": e["name"][:30], "hashtag": "#Campus"}
    tf = bool(getattr(config, "TELUGU_FIRST", True))
    text = build_question_text(q, cfg, telugu_first=tf, position=f"Q {qi + 1}/{len(e['questions'])}")
    opts = build_options(q, telugu_first=tf)
    e["qi"] = qi; e["state"] = "question"
    e["q_open"] = now.isoformat(); e["q_close"] = (now + timedelta(seconds=q["window"])).isoformat()
    for uid, p in e["players"].items():
        if p.get("blocked"):
            continue
        payload = {"chat_id": uid, "question": f"⏱ {q['window']}s · {text}"[:300],
                   "options": [{"text": o} for o in opts], "type": "quiz", "is_anonymous": False,
                   "correct_option_id": q["answer_index"], "open_period": q["window"]}
        try:
            res = tg._call("sendPoll", payload)
            pid = (res or {}).get("result", {}).get("poll", {}).get("id")
            if pid:
                d["polls"][str(pid)] = [e["code"], qi, uid]
        except Exception as ex:
            if "blocked" in str(ex).lower() or "chat not found" in str(ex).lower():
                p["blocked"] = True
    _save(d)


def record_answer(poll_id, uid, chosen):
    try:
        d = _load()
        meta = d["polls"].get(str(poll_id))
        if not meta:
            return False
        code, qi, owner = meta
        e = d["events"].get(code)
        if not e or owner != str(uid) or e["state"] != "question" or e["qi"] != qi:
            return True
        ans = e["answers"].setdefault(str(qi), {})
        if str(uid) in ans:
            return True
        q = e["questions"][qi]; p = e["players"][str(uid)]
        elapsed = (_now() - datetime.fromisoformat(e["q_open"])).total_seconds()
        if int(chosen) == q["answer_index"]:
            pts = PTS_CORRECT + int(round(PTS_SPEED_MAX * max(0, 1 - elapsed / max(q["window"], 1))))
            p["correct"] += 1
        else:
            pts = 0
        p["pts"] += pts; p["answered"] += 1
        p["first"] = p["first"] or _now().isoformat(); p["last"] = _now().isoformat()
        ans[str(uid)] = pts
        _save(d)
        return True
    except Exception as ex:
        print(f"   [campus] answer note: {ex}")
        return False


def tick(tg, members, now=None):
    """Advance all live campus events; True while any is live."""
    now = now or _now()
    d = _load()
    live = False
    for e in list(d["events"].values()):
        if e["state"] not in ("question", "gap"):
            continue
        live = True
        if e["state"] == "question":
            all_in = len(e["answers"].get(str(e["qi"]), {})) >= sum(1 for p in e["players"].values() if not p.get("blocked"))
            if now >= datetime.fromisoformat(e["q_close"]) or all_in:
                e["state"] = "gap"; e["q_open"] = (now + timedelta(seconds=GAP_SEC)).isoformat()
                _save(d)
        elif e["state"] == "gap" and now >= datetime.fromisoformat(e["q_open"]):
            nxt = e["qi"] + 1
            if nxt >= len(e["questions"]):
                _finish(tg, members, d, e, now)
            else:
                _open_question(tg, d, e, nxt, now)
    return live


# ================================================================== results
def college_table(e):
    agg = {}
    for p in e["players"].values():
        if p["answered"] == 0:
            continue
        a = agg.setdefault(p["college"], {"pts": 0, "n": 0, "correct": 0, "top": ("", -1)})
        a["pts"] += p["pts"]; a["n"] += 1; a["correct"] += p["correct"]
        if p["pts"] > a["top"][1]:
            a["top"] = (p["name"], p["pts"])
    rows = []
    for c, a in agg.items():
        avg = a["pts"] / a["n"]
        rows.append({"college": c, "score": round(avg + min(a["n"], 30) * 0.5, 1), "avg": round(avg, 1), "n": a["n"],
                     "acc": round(100 * a["correct"] / max(a["n"] * len(e["questions"]), 1)), "top": a["top"]})
    rows.sort(key=lambda r: (-r["score"], -r["n"]))
    return rows


def ranking(e):
    rows = [(u, p) for u, p in e["players"].items() if p["answered"]]
    rows.sort(key=lambda kv: (-kv[1]["pts"], -kv[1]["correct"], kv[1]["last"] or "z"))
    return rows


def _finish(tg, members, d, e, now):
    e["state"] = "done"; e["finished"] = now.isoformat()
    rows = ranking(e)
    cols = college_table(e)
    for i, (u, p) in enumerate(rows):
        m = members._get(u)
        bonus = PODIUM.get(i, 0)
        if cols and p["college"] == cols[0]["college"]:
            bonus += COLLEGE_WIN_PTS
        m["points"] = m.get("points", 0) + p["pts"] // 2 + bonus     # half of exam pts + podium
        m["campus_events"] = m.get("campus_events", 0) + 1
        p["rank"] = i + 1
    members.kv.save()
    _save(d)
    text = render_result(e, rows, cols)
    btns = join_buttons()
    for u, p in rows:
        me = f"\n\n🫵 మీరు: #{p['rank']}/{len(rows)} · {p['pts']} pts · {p['correct']}/{len(e['questions'])} ✅ · {p['college']}"
        try:
            tg.send_message(u, text + me, buttons=btns)
        except Exception:
            pass
    # auto public post to hub channels (names → students go looking for themselves → join)
    try:
        pub = channel_post_from(e)
        for ch in getattr(config, "CHAMPION_CHANNELS", ["CURRENT"]):
            try:
                tg.send_message(config.channel_chat_id(ch), pub)
            except Exception:
                pass
        e["posted"] = True
    except Exception as ex:
        print(f"   [campus] post note: {ex}")
    # organiser: summary + CSV
    summary = text + "\n\n📎 Full data: /campus csv " + e["code"]
    for aid in ([e.get("by")] if e.get("by") else []) + list(getattr(config, "STAFF_IDS", [])):
        if not aid:
            continue
        try:
            tg.send_message(aid, summary)
        except Exception:
            pass
    e["_post"] = text
    _save(d)


def render_result(e, rows, cols, limit=10):
    n_q = len(e["questions"])
    medals = ["🥇", "🥈", "🥉"] + [f"{i}." for i in range(4, limit + 1)]
    lines = [f"🎓 {e['name']} — RESULT · {e['district']}", f"👥 {len(rows)} students · {n_q} Q", ""]
    if len(cols) >= 2:
        lines.append("🏫 COLLEGE vs COLLEGE")
        lead = cols[0]["score"]
        for i, c in enumerate(cols[:6]):
            bar = "█" * max(1, int(8 * c["score"] / max(lead, 1)))
            lines.append(f"{medals[i]} {c['college']} {bar} {c['score']:g} · {c['n']}👥 · 🎯{c['acc']}% · ⭐{c['top'][0][:12]}")
        lines += [f"🏆 WINNER: {cols[0]['college']} 🎉 (+{COLLEGE_WIN_PTS} pts each)", ""]
    lines.append("🏆 TOP 10")
    for i, (u, p) in enumerate(rows[:limit]):
        b = f" 🎁+{PODIUM[i]}" if i in PODIUM else ""
        lines.append(f"{medals[i]} {p['name'][:20]} · {p['college'][:14]} — {p['pts']} pts ({p['correct']}/{n_q}){b}")
    if len(rows) > limit:
        lines += ["", f"🌱 RISING 5 (rank {limit + 1}–{len(rows)})"]
        for u, p in rows[limit:limit + 5]:
            lines.append(f"• {p['name'][:20]} · {p['college'][:14]} — {p['correct']}/{n_q} ✅")
    avg = sum(p["correct"] for _, p in rows) / max(len(rows), 1)
    lines += ["", f"📈 Average {avg:.1f}/{n_q} · scoring: ✅ +10 + speed ≤5 · podium +100/+60/+40", "",
              "📢 మీ పేరు మా channel లో post అవుతుంది — join అయ్యి చూడండి & రోజూ ఆడండి:",
              f"   Telegram: {getattr(config, 'BRAND_HANDLE', 't.me/StudentUpQuiz')}",
              (f"   WhatsApp: {config.WHATSAPP_CHANNEL}" if getattr(config, "WHATSAPP_CHANNEL", "") else "").rstrip(),
              "🎁 Points ఇప్పటికే మీ wallet లో (/wallet) → applications discount, materials, మీ జిల్లా offers (/offers)",
              "⚔️ రోజూ 9 PM District War · /quiz any time"]
    return "\n".join(l for l in lines if l is not None)


def channel_post(code):
    d = _load()
    e = d["events"].get(code)
    if not e or e["state"] != "done":
        return None
    return channel_post_from(e)


def channel_post_from(e):
    """Short public version for the hub channel (names of Top 10 + winner college)."""
    rows = ranking(e); cols = college_table(e)
    lines = [f"🎓 CAMPUS EVENT — {e['name']} · {e['district']}", f"👥 {len(rows)} students competed", ""]
    if len(cols) >= 2:
        lines.append(f"🏆 College winner: {cols[0]['college']} ({cols[0]['n']} students · {cols[0]['acc']}%)")
    lines.append("🏅 Top 10:")
    for i, (u, p) in enumerate(rows[:10]):
        lines.append(f"{'🥇🥈🥉'[i] if i < 3 else str(i + 1) + '.'} {p['name'][:18]} · {p['college'][:14]} — {p['correct']}/{len(e['questions'])}")
    lines += ["", f"📋 Full list ({len(rows)} students) → bot లో /myscore",
              "మీ college లో కూడా కావాలా? → bot లో /campus  · Students: /start → రోజూ quiz + District War ⚔️"]
    return "\n".join(lines)


def my_score(members, uid):
    """/myscore — student's own campus results + full list of their event (names+college+score)."""
    d = _load()
    code = d["by_uid"].get(str(uid))
    e = d["events"].get(code) if code else None
    if not e:
        return "మీరు ఇంకా ఏ campus event లో ఆడలేదు."
    if e["state"] != "done":
        return f"🎓 {e['name']} — {e['state']} · result వచ్చాక ఇక్కడ చూడండి."
    rows = ranking(e)
    p = e["players"].get(str(uid))
    lines = [f"🎓 {e['name']} — full list ({len(rows)})"]
    if p and p.get("rank"):
        lines.append(f"🫵 మీరు #{p['rank']} · {p['pts']} pts · {p['correct']}/{len(e['questions'])}")
    lines.append("")
    for u, q in rows[:60]:
        lines.append(f"{q['rank']}. {q['name'][:18]} · {q['college'][:12]} — {q['correct']}/{len(e['questions'])}")
    if len(rows) > 60:
        lines.append(f"… +{len(rows) - 60}")
    lines += ["", "రోజూ ఆడండి → /quiz · 9 PM District War ⚔️ · points → /offers"]
    return "\n".join(lines)


def csv_text(code):
    d = _load()
    e = d["events"].get(code)
    if not e:
        return None
    out = ["rank,name,college,phone,uid,correct,total_q,points,answered"]
    rows = ranking(e) if e["state"] == "done" else sorted(e["players"].items())
    for i, (u, p) in enumerate(rows, 1):
        out.append(f"{p.get('rank', i)},{p['name']},{p['college']},{p.get('phone', '')},{u},{p['correct']},{len(e['questions']) or e['n_q']},{p['pts']},{p['answered']}")
    return "\n".join(out)


def status_text(members, code):
    d = _load()
    e = d["events"].get(code)
    if not e:
        return "Event not found."
    reg = sum(1 for u in e["players"] if (members.members.get(u) or {}).get("registered"))
    per = {}
    for p in e["players"].values():
        per[p["college"]] = per.get(p["college"], 0) + 1
    lines = [f"🎓 {e['code']} {e['name']} · {e['district']} · state: {e['state']}",
             f"👥 joined {len(e['players'])} · registered {reg}" + (f" · Q{e['qi'] + 1}/{len(e['questions'])}" if e["state"] in ("question", "gap") else "")]
    lines += [f"  🏫 {c}: {n}" for c, n in sorted(per.items(), key=lambda x: -x[1])]
    if e["state"] == "open":
        lines.append(f"\nStart: /campus start {code}")
    return "\n".join(lines)


def list_text():
    d = _load()
    if not d["events"]:
        return "No campus events. /campus new <name> | <district> | <College A> ; <College B> [| questions] [| easy/medium/hard]"
    lines = ["🎓 Campus events:"]
    for e in sorted(d["events"].values(), key=lambda x: x["created"], reverse=True)[:15]:
        lines.append(f"{e['code']} {e['name'][:24]} · {e['district']} · {len(e['players'])}👥 · {e['state']} · {e['created'][:10]}")
    return "\n".join(lines)


def waiting_room_ping(tg, members, code):
    """Optional: nudge joined students right before start."""
    d = _load()
    e = d["events"].get(code)
    if not e:
        return 0
    n = 0
    for u in e["players"]:
        try:
            tg.send_message(u, f"⏳ {e['name']} — 1 నిమిషంలో start! Phone ఇక్కడే ఉంచండి. Q1 వస్తోంది… 📱"); n += 1
        except Exception:
            pass
    return n
