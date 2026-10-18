"""
Business Pulse — growth funnel, referral engine & monetization planner.

Everything here is computed from the REAL stores (members.json referral
fields that bot /invite already maintains, partners.json voucher economy)
— no invented numbers. The only "future" numbers are the planner's, and
those are clearly a what-if: admin sets price + expected conversion,
Pulse multiplies by the real active-member base.

  funnel      registered → activated (answered ≥1) → active today / 7d
  referrals   joins via /invite links, activated referrals, top referrers
              with tiers (🥉3 · 🥈10 · 🥇25 — same tiers as core.growth)
  economy     partners / offers / vouchers (held = pending at shop,
              used = redeemed), points in circulation
  planner     paying_est = active base × conversion% · MRR = paying × ₹

Entry points never raise; CLI:  python3 -m core.pulse
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from . import config
from .store import load_json, save_json_atomic

SETTINGS_FILE = config.DATA / "pulse_settings.json"
DEFAULT_SETTINGS = {"price_inr": 149, "conversion_pct": 5,
                    "plan_name": "StudentUp Pro"}
TIERS = ((25, "🥇 Ambassador"), (10, "🥈 Recruiter"), (3, "🥉 Connector"))


def _tier(n: int) -> str:
    for need, name in TIERS:
        if n >= need:
            return name
    return ""


def _pct(a: int, b: int) -> float:
    return round(100.0 * a / b, 1) if b else 0.0


# ------------------------------------------------------------------ funnel
def funnel_from(members_map, now=None) -> dict:
    """Pure funnel + referral math from a members {uid: member} mapping."""
    now = now or datetime.now(config.IST)
    today = now.strftime("%Y-%m-%d")
    cut7 = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    reg = [(str(u), m) for u, m in (members_map or {}).items()
           if isinstance(m, dict) and m.get("registered")]
    n = len(reg)

    def answered(m):
        return int(m.get("total", 0) or 0) > 0

    activated = sum(1 for _, m in reg if answered(m))
    active_today = sum(1 for _, m in reg if m.get("last_active") == today)
    active_7d = sum(1 for _, m in reg
                    if str(m.get("last_active", "")) >= cut7 and m.get("last_active"))
    referred = [(u, m) for u, m in reg if m.get("referred_by")]
    referred_active = sum(1 for _, m in referred if answered(m))
    total_ref = sum(int(m.get("referrals", 0) or 0) for _, m in reg)
    total_ref_act = sum(int(m.get("ref_activated", 0) or 0) for _, m in reg)

    top = sorted(reg, key=lambda kv: int(kv[1].get("referrals", 0) or 0),
                 reverse=True)
    top_referrers = [{
        "uid": u,
        "name": m.get("name") or m.get("username") or "Student",
        "district": m.get("district", ""),
        "referrals": int(m.get("referrals", 0) or 0),
        "activated": int(m.get("ref_activated", 0) or 0),
        "tier": _tier(int(m.get("referrals", 0) or 0)),
    } for u, m in top if int(m.get("referrals", 0) or 0) > 0][:8]

    return {
        "registered": n,
        "activated": activated,
        "activation_pct": _pct(activated, n),
        "active_today": active_today,
        "active_7d": active_7d,
        "active_7d_pct": _pct(active_7d, n),
        "referred_members": len(referred),
        "referral_share_pct": _pct(len(referred), n),
        "referred_activated": referred_active,
        "total_referrals": total_ref,
        "total_referral_activated": total_ref_act,
        "referrers": sum(1 for _, m in reg if int(m.get("referrals", 0) or 0) > 0),
        "top_referrers": top_referrers,
        "total_points": sum(int(m.get("points", 0) or 0) for _, m in reg),
        "total_answers": sum(int(m.get("total", 0) or 0) for _, m in reg),
    }


def economy_from(partners_d, members_map=None) -> dict:
    """Partner-offer economy from partners.json (+ points circulation)."""
    d = partners_d if isinstance(partners_d, dict) else {}
    vouchers = [v for v in (d.get("vouchers") or {}).values()
                if isinstance(v, dict)]
    reg = [m for m in (members_map or {}).values()
           if isinstance(m, dict) and m.get("registered")]
    return {
        "partners": len(d.get("partners") or {}),
        "offers": len(d.get("offers") or {}),
        "vouchers_held": sum(1 for v in vouchers if v.get("status") == "held"),
        "vouchers_used": sum(1 for v in vouchers if v.get("status") == "used"),
        "points_held_at_shops": sum(int(v.get("pts", 0) or 0) for v in vouchers
                                     if v.get("status") == "held"),
        "points_in_circulation": sum(int(m.get("points", 0) or 0) for m in reg),
        "points_redeemed": sum(int(m.get("points_redeemed", 0) or 0) for m in reg),
    }


# ------------------------------------------------------------------ planner
def _spath(data_dir=None) -> Path:
    return (Path(data_dir) / "pulse_settings.json") if data_dir else SETTINGS_FILE


def load_settings(data_dir=None) -> dict:
    s = dict(DEFAULT_SETTINGS)
    try:
        raw = load_json(_spath(data_dir), {})
        if isinstance(raw, dict):
            s.update({k: raw[k] for k in s if k in raw})
    except Exception:
        pass
    s["price_inr"] = max(0, min(100000, int(s.get("price_inr", 149) or 0)))
    s["conversion_pct"] = max(0, min(100, float(s.get("conversion_pct", 5) or 0)))
    return s


def save_settings(price_inr=None, conversion_pct=None, plan_name=None,
                  data_dir=None) -> dict:
    s = load_settings(data_dir)
    if price_inr is not None:
        s["price_inr"] = max(0, min(100000, int(price_inr)))
    if conversion_pct is not None:
        s["conversion_pct"] = max(0, min(100, float(conversion_pct)))
    if plan_name:
        s["plan_name"] = str(plan_name)[:40]
    try:
        save_json_atomic(_spath(data_dir), s)
    except Exception:
        pass
    return s


def planner(funnel: dict, settings: dict) -> dict:
    """What-if projection — clearly labelled, real base × admin assumptions."""
    base = int(funnel.get("active_7d", 0)) or int(funnel.get("registered", 0))
    paying = round(base * float(settings["conversion_pct"]) / 100.0)
    mrr = paying * int(settings["price_inr"])
    return {
        **settings,
        "base_members": base,
        "base_label": ("last-7-days active members" if funnel.get("active_7d")
                       else "registered members (no 7d activity yet)"),
        "paying_est": paying,
        "mrr_inr": mrr,
        "arr_inr": mrr * 12,
    }


def growth_score(funnel: dict) -> int:
    """0-100: activation 40 · 7d activity 30 · referral share 30."""
    s = (0.4 * min(100.0, float(funnel.get("activation_pct", 0)))
         + 0.3 * min(100.0, float(funnel.get("active_7d_pct", 0)))
         + 0.3 * min(100.0, float(funnel.get("referral_share_pct", 0)) * 2))
    return round(s)


# ------------------------------------------------------------------ report
def report(data_dir=None, now=None) -> dict:
    dd = Path(data_dir) if data_dir else config.DATA
    members_d = load_json(dd / "members.json", {})
    members_map = members_d.get("members", {}) if isinstance(members_d, dict) else {}
    funnel = funnel_from(members_map, now=now)
    settings = load_settings(data_dir)
    return {
        "ok": True,
        "generated_at": (now or datetime.now(config.IST)).strftime("%Y-%m-%d %H:%M"),
        "growth_score": growth_score(funnel),
        "funnel": funnel,
        "economy": economy_from(load_json(dd / "partners.json", {}), members_map),
        "planner": planner(funnel, settings),
    }


def text_report(rep: dict) -> str:
    f, e, p = rep["funnel"], rep["economy"], rep["planner"]
    L = [f"📈 STUDENTUP BUSINESS PULSE — {rep['generated_at']}  ·  Growth score {rep['growth_score']}/100",
         f"👥 Funnel: {f['registered']} registered → {f['activated']} activated ({f['activation_pct']}%)"
         f" → {f['active_7d']} active/7d · {f['active_today']} today",
         f"📣 Referrals: {f['referred_members']} joins ({f['referral_share_pct']}% of members)"
         f" · {f['total_referral_activated']} activated · {f['referrers']} referrers",
         f"🏪 Economy: {e['partners']} partners · {e['offers']} offers · "
         f"{e['vouchers_used']} redeemed · {e['vouchers_held']} pending at shops",
         f"💰 Planner ({p['plan_name']} ₹{p['price_inr']} × {p['conversion_pct']}% of "
         f"{p['base_members']}): ~{p['paying_est']} paying → ₹{p['mrr_inr']:,}/mo (₹{p['arr_inr']:,}/yr)"]
    if f["top_referrers"]:
        L.append("🏆 Top referrers: " + " · ".join(
            f"{t['name']} ({t['referrals']})" for t in f["top_referrers"][:3]))
    return "\n".join(L)


if __name__ == "__main__":
    print(text_report(report()))
