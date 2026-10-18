#!/usr/bin/env python3
"""
STUDENTUP — 🎯 VISION MISSION CONTROL

Mana vision ni oka chotane, numbers tho chupisthundi:
  "TS/AP aspirant prathivadu — prathi roju, thana exam ki saripoye
   previous-exam (PYQ) + fresh questions bilingual polls ga, Telegram
   mariyu WhatsApp lo, miss avvakunda, rank tho patu."

Pillars (anni existing data stores nunche compute avuthaayi — invent
cheyavu):
  📚 Content   — bank, unused/channel, PYQ share, sources live, papers
  📡 Reach     — TG channels, WA active groups, members, districts
  🎯 Engage    — points earn chesina students, 7d lo pampina polls
  🗓️ Coverage  — schedules (WA/TG), schedule leni channels/groups (gaps)
  🛡️ Health    — 0-100 score + "next actions" (priority order lo)

CLI:  python3 -m core.vision
API:  GET /api/vision  (dashboard header lone Vision card)
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from . import config
from .store import load_json


def _data(data_dir):
    return Path(data_dir) if data_dir else config.DATA


def _load(data_dir, name, default):
    return load_json(_data(data_dir) / name, default)


def vision_report(data_dir=None, now=None) -> dict:
    now = now or datetime.now()
    dd = _data(data_dir)
    actions = []   # (priority, text) — takkuva priority number = first

    # ---------------- 📚 Content ----------------
    bank = _load(dd, "question_bank.json", {})
    qs = bank if isinstance(bank, list) else bank.get("questions", []) or []
    used = _load(dd, "used_questions.json", {})
    public = list(getattr(config, "PUBLIC_CHANNELS", []))
    unused, pyq_unused = {}, {}
    for ch in public:
        pool = [q for q in qs if q.get("channel") == ch]
        u = set(used.get(ch, []))
        un = [q for q in pool if q.get("id") not in u]
        unused[ch] = len(un)
        pyq_unused[ch] = sum(1 for q in un if q.get("source") == "pyq")
    pyq_total = sum(1 for q in qs if q.get("source") == "pyq")
    min_unused = min(unused.values()) if unused else 0
    min_ch = min(unused, key=unused.get) if unused else "-"
    if min_unused < 50:
        actions.append((1, f"📉 {min_ch} lo unused stock {min_unused} matrame — collector/supply-guard meeda bharam paduthondi; sources audit chudandi"))
    reg = _load(dd, "collector_sources.json", {})
    srcs = reg.get("sources", []) if isinstance(reg, dict) else []
    live_src = sum(1 for s in srcs if s.get("enabled"))
    cand_src = sum(1 for s in srcs if not s.get("enabled") and s.get("auto_enable_if_live"))
    if cand_src > 150:
        actions.append((4, f"🔎 {cand_src} source candidates audit kosam wait chesthunnayi — 04:45 audit pass ayinavi matrame live avuthaayi"))
    papers = _load(dd, "pyq_papers.json", {}).get("papers", [])
    pstate = _load(dd, "pyq_state.json", {})
    done_papers = sum(1 for pp in papers
                      if pstate.get(pp.get("url") or pp.get("index"), {}).get("status") == "done")
    if papers and done_papers < len(papers):
        actions.append((3, f"📜 PYQ papers {done_papers}/{len(papers)} harvested — 02:15 + 13:45 runs lo rojuki ~24 drain avuthaayi, scheduler run avuthundo check cheyyandi"))
    # 🧠 item intelligence: real answers tho quality auto-fix
    item_stats = _load(dd, "item_stats.json", {})
    suspect_n = easy_n = 0
    for _qid, _rec in (item_stats.items() if isinstance(item_stats, dict) else []):
        if not isinstance(_rec, dict):
            continue
        _a = int(_rec.get("a", 0))
        if _a:
            _r = int(_rec.get("c", 0)) / _a
            if _a >= 15 and _r <= 0.18:
                suspect_n += 1
            elif _a >= 25 and _r >= 0.95:
                easy_n += 1
    if suspect_n:
        actions.append((2, f"🧠 {suspect_n} questions ni students andaru fail avuthunnaru (suspect wrong key) — item intelligence quarantine chesindi, bank lo verify cheyyandi"))

    content = {
        "item_suspects": suspect_n, "item_too_easy": easy_n,
        "bank_questions": len(qs),
        "pyq_questions": pyq_total,
        "pyq_share_pct": round(100 * pyq_total / max(1, len(qs))),
        "unused_by_channel": unused,
        "pyq_unused_by_channel": pyq_unused,
        "min_unused": min_unused, "min_channel": min_ch,
        "sources_total": len(srcs), "sources_live": live_src,
        "sources_candidates": cand_src,
        "pyq_papers": f"{done_papers}/{len(papers)}",
        "pyq_discovered": sum(1 for pp in papers
                              if str(pp.get("via", "")).startswith("index")),
    }

    # ---------------- 📡 Reach ----------------
    wa = _load(dd, "whatsapp_groups.json", {})
    wa_groups = [g for g in wa.get("groups", []) if g.get("active", True)]
    members_d = _load(dd, "members.json", {})
    members = members_d.get("members", {}) if isinstance(members_d, dict) else {}
    reg_members = [m for m in members.values() if m.get("registered")]
    districts = {str(m.get("district")) for m in reg_members if m.get("district")}
    reach = {
        "telegram_channels": len(public),
        "whatsapp_groups": len(wa_groups),
        "members_registered": len(reg_members),
        "districts": len(districts),
    }
    if not wa_groups:
        actions.append((2, "💚 WhatsApp groups okkati kuda active ledu — Excel/Manual setup tho add cheyyandi leda QR scan chesi sync cheyyandi"))
    if not reg_members:
        actions.append((5, "👥 Registered members leru — channels lo join link + /start promotion cheyyandi"))

    # ---------------- 🎯 Engagement ----------------
    hist = _load(dd, "broadcast_history.json", {})
    evs = hist.get("events", []) if isinstance(hist, dict) else []
    cut = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    week = [e for e in evs if str(e.get("date", "")) >= cut]
    week_live = [e for e in week if not e.get("dry")]
    live_counts = {}  # schedules coverage by target key
    engage = {
        "week_polls_sent": sum(int(e.get("count", 0)) for e in week_live),
        "week_dry_polls": sum(int(e.get("count", 0)) for e in week if e.get("dry")),
        "students_with_points": sum(1 for m in reg_members if int(m.get("points", 0) or 0) > 0),
        "total_points": sum(int(m.get("points", 0) or 0) for m in reg_members),
    }
    if week and engage["week_polls_sent"] == 0:
        actions.append((1, "🚨 Last 7 days lo LIVE polls okkati kuda vellaledu (dry matrame) — BOT_TOKEN/bridge check chesi scheduler start cheyyandi"))

    # ---------------- 📈 Growth (Business Pulse) ----------------
    try:
        from . import pulse as _pulse
        growth = _pulse.funnel_from(members)
    except Exception:
        growth = {}
    if growth.get("registered", 0) >= 10 and growth.get("total_referrals", 0) == 0:
        actions.append((3, "📣 Members unnaru kani referral joins 0 — /invite loop push cheyyandi (prathi member link bot lo undi, +20 pts/friend)"))
    if growth.get("registered", 0) >= 10 and growth.get("activation_pct", 0) < 30:
        actions.append((4, f"🎯 Activation {growth.get('activation_pct', 0)}% matrame — register ayyi first answer veyyani vallaki coach DM/report card push cheyyandi"))

    # ---------------- 🗓️ Coverage ----------------
    sched = _load(dd, "whatsapp_schedules.json", {})
    jobs = [j for j in (sched.get("jobs", []) if isinstance(sched, dict) else [])
            if j.get("enabled", True)]
    tg_covered = set()
    wa_covered = set()
    for j in jobs:
        tg_covered.update(j.get("telegram_channels") or [])
        wa_covered.update(j.get("target_group_ids") or [])
    # quiz slots in core config count as channel coverage (main rounds)
    gap_channels = [c for c in public if c not in tg_covered]
    gap_groups = [g.get("name") for g in wa_groups
                  if g.get("id") not in wa_covered and jobs]
    coverage = {
        "active_schedules": len(jobs),
        "wa_jobs": sum(1 for j in jobs if j.get("mode", "wa") == "wa"),
        "tg_jobs": sum(1 for j in jobs if j.get("mode") == "tg"),
        "both_jobs": sum(1 for j in jobs if j.get("mode") == "both"),
        "channels_without_autopilot": gap_channels,
        "groups_without_schedule": gap_groups[:12],
    }
    if gap_channels:
        actions.append((3, f"📢 {len(gap_channels)} channels ki Telegram Auto-Pilot schedule ledu ({', '.join(gap_channels[:4])}…) — Dashboard → Telegram tab lo slots set cheyyandi (core quiz slots matram saripovu)"))
    if not jobs:
        actions.append((2, "🗓️ Okka active schedule kuda ledu — Excel/Manual setup tho timings set cheyyandi, lekapote prathi roju manual ga post cheyyalsi vasthundi"))

    # ---------------- 🏢 Ops (metrics + flags) ----------------
    ops = {}
    try:
        from . import flags as _fl, metrics as _mx
        _snap = _mx.snapshot()
        ops = {"delivery": _snap.get("delivery", {}),
               "answers_24h": int(_snap.get("last_24h", {}).get("answers", 0)),
               "flags_off": [f["name"] for f in _fl.all_flags() if not f["enabled"]]}
        _d = ops["delivery"]
        if (_d.get("success_pct") is not None
                and (_d.get("sent", 0) + _d.get("failed", 0)) >= 20
                and _d["success_pct"] < 80):
            actions.append((2, f"📉 WhatsApp delivery success {_d['success_pct']}% matrame — bridge/gateway quality chudandi (Pro Ops tab lo details)"))
    except Exception:
        ops = {}

    # ---------------- 🛡️ Health score ----------------
    s_content = max(0, min(30, min_unused / 3))                     # stock depth
    s_pyq = 15 * (content["pyq_share_pct"] / 100) / 0.4 if len(qs) else 0
    s_pyq = max(0, min(15, s_pyq))
    s_cov = 25 * (1 - (len(gap_channels) / max(1, len(public)))) if public else 0
    if not jobs:
        s_cov = min(s_cov, 5)
    s_engage = 15 if engage["week_polls_sent"] > 0 else (5 if week else 0)
    s_src = 15 * (live_src / max(1, len(srcs))) if srcs else 0
    s_src = min(15, s_src * 2)          # ~50%+ live registry = full marks
    score = round(s_content + s_pyq + s_cov + s_engage + s_src)
    grade = ("S" if score >= 90 else "A" if score >= 75 else "B" if score >= 60
             else "C" if score >= 40 else "D")
    actions.sort(key=lambda x: x[0])

    # next collector slots today
    try:
        from . import config as _c
        now_hm = now.strftime("%H:%M")
        nxt = [t for t, v in sorted(_c.SCHEDULE.items())
               if v[0] in ("collect", "audit", "pyq") and t > now_hm][:3]
    except Exception:
        nxt = []
    return {
        "generated_at": now.strftime("%Y-%m-%d %H:%M"),
        "score": score, "grade": grade,
        "vision": "Prathi TS/AP aspirant ki — prathi roju, thana exam PYQ + "
                  "fresh bilingual polls, Telegram & WhatsApp lo, rank tho.",
        "pillars": {"content": content, "reach": reach,
                    "engagement": engage, "coverage": coverage,
                    "growth": growth},
        "ops": ops,
        "next_collections_today": nxt,
        "actions": [a[1] for a in actions][:7],
    }


def format_text(rep: dict) -> str:
    c, r, e, cov = (rep["pillars"]["content"], rep["pillars"]["reach"],
                    rep["pillars"]["engagement"], rep["pillars"]["coverage"])
    L = [f"🎯 STUDENTUP VISION — Score {rep['score']}/100 ({rep['grade']}) · {rep['generated_at']}",
         f"   {rep['vision']}", "",
         f"📚 Content : bank {c['bank_questions']} · PYQ {c['pyq_questions']} ({c['pyq_share_pct']}%) · "
         f"weakest stock {c['min_channel']}={c['min_unused']} · sources live {c['sources_live']}/{c['sources_total']} "
         f"(+{c['sources_candidates']} audit-waiting) · papers {c['pyq_papers']}",
         f"📡 Reach   : {r['telegram_channels']} TG channels · {r['whatsapp_groups']} WA groups · "
         f"{r['members_registered']} members · {r['districts']} districts",
         f"🎯 Engage  : last 7d LIVE polls {e['week_polls_sent']} (dry {e['week_dry_polls']}) · "
         f"{e['students_with_points']} students with points ({e['total_points']} pts)",
         f"🗓️ Coverage: {cov['active_schedules']} schedules (WA {cov['wa_jobs']} · TG {cov['tg_jobs']} · both {cov['both_jobs']}) · "
         f"channels w/o autopilot: {len(cov['channels_without_autopilot'])}",
         f"⏭️ Next collections today: {', '.join(rep['next_collections_today']) or '—'}", "",
         "👉 Next actions:"]
    L += [f"   {i}. {a}" for i, a in enumerate(rep["actions"], 1)] or ["   ✅ Anni pillars healthy!"]
    return "\n".join(L)


if __name__ == "__main__":
    print(format_text(vision_report()))
