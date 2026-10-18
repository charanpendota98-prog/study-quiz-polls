# -*- coding: utf-8 -*-
"""✨ Smart Day Planner — one-click intelligent dispatch plan.

Advanced lopala, easy bayata: students eppudu active ga untaro
(metrics.hour_profile) + prathi channel lo students ekkada weak ga unnaro
(item_intel.channel_topic_rates) kalipi, eeroju dispatch plan propose
chestundi. Apply ante existing daily scheduled jobs create avthayi.
Weak-topic targeting Smart Rounds engine lonae jaruguthundi kabatti,
plan lo topics advisory matrame — subjects force cheyyamu (empty-pool
risk lekunda).

NOTE: imports anni lazy — channel_router import chesthe custom channels
config Loki mount avthayi, adhi vere modules/tests ni disturb cheyyakudadhu."""

DEFAULT_SLOTS = ["07:00", "10:30", "13:00", "17:30", "20:30"]


def _best_slots(n=5):
    """Most-active hours first, sensible defaults fill the rest."""
    try:
        from . import metrics
        prof = metrics.hour_profile() or {}
    except Exception:
        prof = {}
    ranked = sorted((h for h, c in prof.items() if c > 0), key=lambda h: -prof[h])
    slots = [f"{h:02d}:00" for h in ranked[:n]]
    for s in DEFAULT_SLOTS:
        if len(slots) >= n:
            break
        if s not in slots:
            slots.append(s)
    return slots[:n] or list(DEFAULT_SLOTS)


def _weak(channel, fn=None):
    if fn is None:
        from . import item_intel
        fn = item_intel.channel_topic_rates
    try:
        rates = fn(channel) or {}
    except Exception:
        rates = {}
    weak = sorted((t for t, v in rates.items() if v.get("rate", 1) < 0.6),
                  key=lambda t: rates[t].get("rate", 1))
    return weak[:2]


def today_plan(max_items=6, channels=None, rates_fn=None, slots=None):
    """Propose today's Telegram dispatch plan: [{time, channels, name,
    count, topics, reason}]. Pure/read-only — nothing is scheduled yet."""
    if channels is None:
        from . import channel_router
        channels = list(channel_router.get_all_channels().items())
    slots = slots or _best_slots()
    items = []
    for i, (key, info) in enumerate(list(channels)[:max_items]):
        weak = _weak(key, rates_fn)
        name = (info or {}).get("name", key)
        if weak:
            reason = f"Students weak: {', '.join(weak)} — Smart Rounds ee topics focus chesthayi"
        else:
            reason = "General revision — fresh question rotation"
        items.append({"time": slots[i % len(slots)], "mode": "tg",
                      "channels": [key], "name": name, "count": 5,
                      "topics": weak, "reason": reason})
    # 📱 WhatsApp item (active groups unte) — scheduler WA leg safety
    # stack + 60–80s gaps tho velthundi
    try:
        from . import whatsapp_pipeline as _wp
        _reg = _wp.load_wa_registry()
        wa_groups = [g for g in _reg.get("groups", []) if g.get("active")][:8]
    except Exception:
        wa_groups = []
    if wa_groups:
        items.append({"time": slots[0], "mode": "wa",
                      "target_group_ids": [g.get("id") for g in wa_groups if g.get("id")],
                      "name": f"WhatsApp Groups ({len(wa_groups)})", "count": 5,
                      "topics": [],
                      "reason": "WhatsApp groups — 60–80s anti-ban gaps + full safety stack automatic"})
    return {"items": items, "slots": slots,
            "note": "Apply chesthe daily Telegram scheduled jobs create avthayi. "
                    "WhatsApp kosam WhatsApp Dispatcher vadandi — 60–80s gaps automatic."}


def apply_plan(items, add_fn=None):
    """Create the scheduled jobs. Returns created job ids."""
    if add_fn is None:
        from . import whatsapp_pipeline
        add_fn = whatsapp_pipeline.add_scheduled_job
    created = []
    for it in list(items or [])[:12]:
        count = max(1, min(int(it.get("count", 5) or 5), 20))
        label = f"✨ Smart Plan {it.get('time', '')} · {it.get('name', '')}".strip()
        if it.get("mode") == "wa":
            gids = [g for g in (it.get("target_group_ids") or []) if g]
            if not gids:
                continue
            job = add_fn(str(it.get("time", "07:00")), label=label,
                         questions_count=count, target_group_ids=gids,
                         subjects=[], mode="wa")
        else:
            chans = [c for c in (it.get("channels") or []) if c]
            if not chans:
                continue
            job = add_fn(str(it.get("time", "07:00")), label=label,
                         questions_count=count,
                         telegram_channels=chans, subjects=[], mode="tg")
        created.append((job or {}).get("id", ""))
    return [c for c in created if c]
