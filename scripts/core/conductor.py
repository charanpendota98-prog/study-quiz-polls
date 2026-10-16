"""
Exam Conductor — owner oka screen lo exam schedule chesthe, time ki
automatic ga launch ayye orchestration layer.

Engines already unnayi (grandtest / districtwar / campus) — Conductor
vాటిని re-invent cheyyadu, oka unified event store + due-time launcher
matrame:

  📝 grand   Engine.run_grand_test(channels=[ch]) — background thread lo
             (bot loop block avvakunda), settle/results engine deve chesthundi
  ⚔️ war     districtwar.manual_launch(minutes) — lobby open, bot tick
             start_war fire chesthundi (file-state, cross-process safe)
  🏫 campus  create chesinappude campus event + code (share cheyyochu),
             due time ki campus.start() — players <2 unte honest fail

Events: data/exam_events.json · status: scheduled → live → done,
failed (reason tho — fake success eppudu ledu), cancelled.
Bot loop prathi tick lo conductor.tick() pilusthundi; dashboard
"Launch now" kuda ade path vaduthundi.

CLI:  python3 -m core.conductor
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta

from . import config
from .store import load_json, save_json_atomic

EVENTS_FILE = config.DATA / "exam_events.json"

KINDS = {
    "grand": {"label": "📝 Grand Test (Sunday-style mock)", "duration": 90, "nq": 25},
    "war": {"label": "⚔️ District War", "duration": 30, "nq": 0},
    "campus": {"label": "🏫 Campus Exam (join code tho)", "duration": 60, "nq": 20},
}


def _now(now=None):
    return now or datetime.now(config.IST)


def _parse_dt(s, now=None):
    """'2026-10-20T19:00' / '2026-10-20 19:00' → aware IST datetime."""
    txt = str(s or "").strip().replace(" ", "T")
    if not txt:
        raise ValueError("starts_at kavali (date + time)")
    try:
        dt = datetime.fromisoformat(txt)
    except Exception:
        raise ValueError(f"starts_at ardam kaledu: {s!r} (e.g. 2026-10-20T19:00)")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=config.IST)
    return dt


def _load() -> dict:
    d = load_json(EVENTS_FILE, {})
    if not isinstance(d, dict) or not isinstance(d.get("events"), list):
        return {"events": []}
    return d


def _save(d):
    d["events"] = d["events"][-100:]
    save_json_atomic(EVENTS_FILE, d)


# ------------------------------------------------------------------- CRUD
def create_event(title, kind, starts_at, channel="CURRENT", duration_min=None,
                 n_questions=None, lobby_min=5, campus_name="", district="",
                 created_by="dashboard", now=None) -> dict:
    """Schedule a kottha exam event. Bad input → ValueError (honest)."""
    kind = str(kind or "").strip().lower()
    if kind not in KINDS:
        raise ValueError(f"kind tappu: {kind!r} (grand / war / campus)")
    dt = _parse_dt(starts_at, now)
    ch = str(channel or "CURRENT").strip().upper() or "CURRENT"
    if kind == "grand" and ch not in getattr(config, "CHANNELS", {}):
        raise ValueError(f"channel ledu: {ch}")
    meta = KINDS[kind]
    ev = {
        "id": "EV-" + uuid.uuid4().hex[:8].upper(),
        "title": str(title or meta["label"]).strip()[:80] or meta["label"],
        "kind": kind,
        "channel": ch,
        "starts_at": dt.isoformat(timespec="minutes"),
        "duration_min": max(5, min(600, int(duration_min or meta["duration"]))),
        "n_questions": max(0, min(200, int(n_questions or meta["nq"]))),
        "lobby_min": max(1, min(60, int(lobby_min or 5))),
        "campus_name": str(campus_name or "").strip()[:60],
        "district": str(district or "").strip()[:40],
        "status": "scheduled",
        "created_at": _now(now).isoformat(timespec="seconds"),
        "created_by": str(created_by)[:30],
        "engine_ref": "",
        "launched_at": "",
        "error": "",
        "note": "",
    }
    if kind == "campus":
        # 🏫 event + join code ippude create — owner code ni mundu share
        # cheyyochu; exam matram due time ki start avuthundi.
        try:
            from . import campus as _campus
            code = _campus.new_event(
                ev["campus_name"] or ev["title"], ev["district"] or "TS/AP",
                [ev["campus_name"] or "General"],
                n_q=max(5, min(30, ev["n_questions"] or 20)),
                created_by=ev["created_by"], shuffle=True)
            ev["engine_ref"] = code
            ev["note"] = f"Join code: {code} — students bot lo /campus {code} tho join avutharu"
        except Exception as e:
            raise ValueError(f"campus event create avvaledu: {e}")
    d = _load()
    d["events"].append(ev)
    _save(d)
    return ev


def list_events(now=None) -> list:
    now = _now(now)
    out = []
    for ev in reversed(_load()["events"]):
        e = dict(ev)
        try:
            dt = _parse_dt(e["starts_at"])
            e["starts_in_min"] = round((dt - now).total_seconds() / 60)
        except Exception:
            e["starts_in_min"] = None
        out.append(e)
    return out


def get_event(eid: str):
    for ev in _load()["events"]:
        if ev.get("id") == eid:
            return ev
    return None


def _update(eid: str, **kw):
    d = _load()
    for ev in d["events"]:
        if ev.get("id") == eid:
            ev.update(kw)
            _save(d)
            return ev
    return None


def cancel_event(eid: str) -> bool:
    ev = get_event(eid)
    if not ev or ev.get("status") not in ("scheduled", "live"):
        return False
    _update(eid, status="cancelled")
    return True


def due_events(now=None) -> list:
    now = _now(now)
    out = []
    for ev in _load()["events"]:
        if ev.get("status") != "scheduled":
            continue
        try:
            if _parse_dt(ev["starts_at"]) <= now:
                out.append(ev)
        except Exception:
            continue
    return out


# ------------------------------------------------------------------ launch
def launch_event(ev, bank=None, members=None, tg=None, engine_factory=None,
                 now=None) -> tuple:
    """Oka event ni ippudu launch chesthundi. (ok, message) — honest."""
    now = _now(now)
    kind = ev.get("kind")
    try:
        if kind == "war":
            from . import districtwar
            ok, txt = districtwar.manual_launch(
                members, tg, bank=bank, minutes=int(ev.get("lobby_min", 5)),
                now=now, force=True)
            if ok:
                _update(ev["id"], status="live", launched_at=now.isoformat(timespec="seconds"),
                        note=f"Lobby open — war {ev.get('lobby_min', 5)} min lo start")
            return ok, txt
        if kind == "campus":
            from . import campus as _campus
            code = ev.get("engine_ref", "")
            if not code:
                return False, "campus join code ledu (event create fail?)"
            ok, txt = _campus.start(bank, members, tg, code, now=now)
            if ok:
                _update(ev["id"], status="live",
                        launched_at=now.isoformat(timespec="seconds"))
            return ok, txt
        if kind == "grand":
            if engine_factory is None:
                return False, "grand test engine unavailable ee process lo"
            ch = ev.get("channel", "CURRENT")

            def _run():
                try:
                    eng = engine_factory()
                    eng.run_grand_test(channels=[ch])
                    _update(ev["id"], status="done",
                            note="Grand test complete — results channel lo settle ayyayi")
                except Exception as e:
                    _update(ev["id"], status="failed", error=str(e)[:200])

            _update(ev["id"], status="live",
                    launched_at=now.isoformat(timespec="seconds"),
                    note=f"Grand test {ch} lo run avuthundi (background)")
            threading.Thread(target=_run, daemon=True,
                             name=f"conductor-{ev['id']}").start()
            return True, f"📝 Grand Test {ch} lo start ayyindi"
        return False, f"unknown kind {kind!r}"
    except Exception as e:
        return False, str(e)[:200]


def tick(now=None, bank=None, members=None, tg=None, engine_factory=None) -> dict:
    """Bot loop nunchi: due events launch + live events auto-finish."""
    now = _now(now)
    launched, failed, finished = [], [], []
    for ev in due_events(now):
        ok, msg = launch_event(ev, bank=bank, members=members, tg=tg,
                               engine_factory=engine_factory, now=now)
        if ok:
            launched.append(ev["id"])
        else:
            _update(ev["id"], status="failed", error=str(msg)[:200])
            failed.append({"id": ev["id"], "error": str(msg)[:200]})
    # ⏰ live events: duration ayipothe done ga mark (war/campus finishing
    # engine side; ikkada status bookkeeping matrame)
    for ev in _load()["events"]:
        if ev.get("status") != "live" or ev.get("kind") == "grand":
            continue    # grand thread completion lone done avuthundi
        try:
            # finish clock LAUNCH nunchi — late launch ayina event ni
            # ventane done anavaddu (war lobby + duration add chestham)
            base = _parse_dt(ev.get("launched_at") or ev["starts_at"])
            end = base + timedelta(
                minutes=int(ev.get("duration_min", 30))
                + (int(ev.get("lobby_min", 0)) if ev.get("kind") == "war" else 0))
            if now >= end:
                _update(ev["id"], status="done", note="Duration complete")
                finished.append(ev["id"])
        except Exception:
            continue
    return {"launched": launched, "failed": failed, "finished": finished}


def result_text(ev, members=None) -> str:
    """Event tarvata emi jarigindo — kind-specific honest summary."""
    ev = ev if isinstance(ev, dict) else (get_event(str(ev)) or {})
    if not ev:
        return "event dorakaledu"
    head = (f"{KINDS.get(ev.get('kind'), {}).get('label', ev.get('kind'))} — "
            f"{ev.get('title')} · status: {ev.get('status')}")
    try:
        if ev.get("kind") == "war" and members is not None:
            from . import districtwar
            return head + "\n" + districtwar.owner_status(members)
        if ev.get("kind") == "campus" and ev.get("engine_ref"):
            from . import campus as _campus
            d = _campus._load()
            e = d.get("events", {}).get(ev["engine_ref"], {})
            return (head + f"\n🏫 Code {ev['engine_ref']} · state {e.get('state', '?')} · "
                    f"{len(e.get('players', {}))} students joined · "
                    f"Q{e.get('qi', 0)}/{len(e.get('questions', []))}")
        if ev.get("kind") == "grand":
            return (head + f"\n📝 {ev.get('channel')} channel lo round settle ayyindi — "
                    "top-10 + answer key channel lone post ayyayi (engine results).")
    except Exception as e:
        return head + f"\n(result fetch error: {e})"
    return head + ("\n" + ev.get("note", "") if ev.get("note") else "")


if __name__ == "__main__":
    evs = list_events()
    print(f"🎓 EXAM CONDUCTOR — {len(evs)} events")
    for e in evs[:10]:
        print(f"  [{e['status']}] {e['id']} {KINDS.get(e['kind'], {}).get('label', e['kind'])}"
              f" · {e['title']} · {e['starts_at']} · starts_in {e['starts_in_min']} min")
