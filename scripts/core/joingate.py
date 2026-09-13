"""
JOIN GATE — make every member actually join the Telegram channels (verifiable) and the
WhatsApp channel (rewarded), and keep nudging the ones who haven't.

Telegram: bot is admin of the channels → getChatMember(channel, uid) tells us if the user is
          a member. So "✅ Verify" is real: +JOIN_PTS once per channel; hub + own exam channel.
WhatsApp: no API to verify → the WhatsApp channel posts a weekly code ("WA-xxxx") that only
          followers see; /claim WA-xxxx = proof (uses social campaigns, platform "wa").
Gates:    campus full list (/myscore) and Round-Show personal rank card ask for the Telegram
          hub join first (soft gate: shows the buttons + verify, then the content).
Nudges:   weekly (Wed 11:00) DM to registered members who never verified: what they miss +
          buttons. Stops after 3 nudges.
"""
from __future__ import annotations

from datetime import datetime

from . import config

JOIN_PTS = 30
MAX_NUDGES = 3
REQUIRED = ["CURRENT"]          # hub; the member's exam channel is added dynamically


def _now():
    return datetime.now(config.IST)


def channel_url(key):
    cfg = config.CHANNELS.get(key, {})
    u = cfg.get("username", "")
    return f"https://t.me/{u}" if u else ""


def required_for(member):
    from .members import exam_channel
    chans = list(REQUIRED)
    ex = exam_channel(member.get("exam", ""))
    if ex and ex not in chans and ex in config.CHANNELS:
        chans.append(ex)
    return chans


def is_member(tg, key, uid):
    """True if uid is member/admin/creator of channel `key` (bot must be admin there)."""
    try:
        chat = config.channel_chat_id(key)
        if not chat:
            return None
        res = tg._call("getChatMember", {"chat_id": chat, "user_id": int(uid)})
        st = (res or {}).get("result", {}).get("status", "")
        return st in ("member", "administrator", "creator", "restricted")
    except Exception:
        return None


def verify(tg, members, uid):
    """Check all required channels; award once per channel. → (all_joined, text)."""
    m = members._get(str(uid))
    done = m.setdefault("joined_channels", {})
    got, missing, unknown = [], [], []
    for key in required_for(m):
        ok = is_member(tg, key, uid)
        if ok is None:
            unknown.append(key)
        elif ok:
            if not done.get(key):
                done[key] = _now().isoformat()
                m["points"] = m.get("points", 0) + JOIN_PTS
                got.append(key)
        else:
            missing.append(key)
    members.kv.save()
    lines = []
    if got:
        lines.append("🎉 Join verified: " + ", ".join(config.CHANNELS[k]["name"] for k in got) + f" → +{JOIN_PTS * len(got)} pts!")
    if missing:
        lines.append("⏳ ఇంకా join కాలేదు: " + ", ".join(config.CHANNELS[k]["name"] for k in missing) + " — క్రింద button → Join → మళ్ళీ ✅ Verify")
    if unknown and not got and not missing:
        lines.append("⚠️ Verify చేయలేకపోయాం (bot channel admin కాదు) — join చేసి ఉంటే చాలు.")
    if not missing and not unknown and not got:
        lines.append("✅ మీరు అన్ని channels లో ఉన్నారు. Thanks!")
    return (not missing), "\n".join(lines)


def buttons(member):
    rows = []
    for key in required_for(member):
        url = channel_url(key)
        if url:
            rows.append([(f"📢 Join {config.CHANNELS[key]['name']}", "url:" + url)])
    wa = getattr(config, "WHATSAPP_CHANNEL", "")
    if wa:
        rows.append([("💚 WhatsApp channel join", "url:" + wa)])
    rows.append([("✅ Verify — I joined (+%d pts)" % JOIN_PTS, "join:verify")])
    return rows


def hub_text(member):
    ex = required_for(member)
    names = " + ".join(config.CHANNELS[k]["name"] for k in ex)
    return "\n".join([
        "📢 StudentUp channels — ఇక్కడే అన్నీ:",
        f"• {names}: రోజూ quiz rounds, Top-10 పేర్లతో, District War results, offers",
        "• WhatsApp channel: daily highlights + వారానికి ఒక secret code → /claim → points",
        "",
        f"Join → ✅ Verify → ప్రతి channel కి +{JOIN_PTS} pts (ఒక్కసారే)",
        "మీ పేరు Top-10 లో వచ్చినప్పుడు అక్కడే చూసుకోవచ్చు 🏆",
    ])


def joined_all(member):
    done = member.get("joined_channels") or {}
    return all(done.get(k) for k in required_for(member))


def gate_text(member, what="ఇది"):
    return f"🔒 {what} చూడాలంటే ముందు మా channel join అయ్యి ✅ Verify చేయండి (+{JOIN_PTS} pts) 👇"


def nudge_targets(members, now=None):
    """Registered, never verified hub, not blocked, < MAX_NUDGES nudges, last nudge ≥ 6 days ago."""
    now = now or _now()
    out = []
    for uid, m in members.members.items():
        if not m.get("registered") or m.get("dm_blocked") or joined_all(m):
            continue
        if m.get("join_nudges", 0) >= MAX_NUDGES:
            continue
        last = m.get("join_nudged", "")
        try:
            if last and (now - datetime.fromisoformat(last)).days < 6:
                continue
        except Exception:
            pass
        out.append(uid)
    return out


def nudge_text(member):
    n = member.get("join_nudges", 0)
    hooks = ["మీ పేరు Top-10 లో వచ్చినా channel లో లేకపోతే మీరే చూడలేరు 😅",
             "ఈ వారం channel లో మీ జిల్లా వాళ్ళు 3 సార్లు Top-10 లో వచ్చారు — మీరు?",
             "చివరి reminder: join + verify = +%d pts free, తర్వాత అడగము 🙏" % JOIN_PTS]
    return "📢 " + hooks[min(n, len(hooks) - 1)] + "\n\n" + hub_text(member)
