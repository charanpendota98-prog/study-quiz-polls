"""
Feature Flags — top-company-style controlled rollouts / kill switches.

Defaults live in code (safe: current behaviour), admin overrides persist
in data/feature_flags.json and take effect immediately — no restart, no
redeploy. Every flag here is wired into a REAL decision point:

  item_intel_quarantine   verifier.postable — suspect-key questions block
  personal_coach_rounds   autopilot coach DM — personal syllabus rounds
  pyq_floor               blueprint — prathi round ≥40% PYQ guarantee
  wa_retry_queue          whatsapp_pipeline — failed-send retry queue

enabled() never raises and fails OPEN to the code default (a broken flag
file must never change product behaviour). CLI: python3 -m core.flags
"""
from __future__ import annotations

from . import config
from .store import load_json, save_json_atomic

FLAGS_FILE = config.DATA / "feature_flags.json"

DEFAULTS = {
    "item_intel_quarantine": {
        "default": True,
        "label": "🧠 Item Intel auto-quarantine",
        "desc": "Students andaru fail ayye (suspect wrong-key) questions ni automatic ga posting nunchi block chesthundi.",
    },
    "personal_coach_rounds": {
        "default": True,
        "label": "🗺️ Personal coach rounds",
        "desc": "07:30 coach DM lo prathi student ki weak-topics + due-review personal round (off = common adaptive round).",
    },
    "pyq_floor": {
        "default": True,
        "label": "📜 PYQ floor (≥40%)",
        "desc": "Prathi composed round lo kammi 40% previous-exam questions guarantee (pool allow chesinanta varaku).",
    },
    "channel_reaction_polls": {
        "default": False,
        "label": "👍 Telegram reaction text-polls (OFF — direct polls)",
        "desc": "Default: Telegram channel/group anni DIRECT native polls (owner rule). Emoji 👍❤️😂😮 text-polls ONLY WhatsApp Channel ke (akkada direct poll option ledu). Ee switch ON chesthe matrame Telegram kuda reaction style ki maruthundi.",
    },
    "smart_rounds": {
        "default": True,
        "label": "🧠 Smart Rounds (weak-topic focus)",
        "desc": "Channel rounds lo students weak ga unna topics mida ekkuva questions automatic ga vasthayi (item-intel data nunchi, PYQ floor safe). Data inka lekapothe normal pick ye jaruguthundi.",
    },
    "wa_retry_queue": {
        "default": True,
        "label": "🔁 WhatsApp retry queue",
        "desc": "Fail ayina WhatsApp sends ni persistent queue lo vesi backoff tho malli try chesthundi.",
    },
    "syllabus_tracker": {
        "default": True,
        "label": "🗺️ Syllabus Tracker (portal)",
        "desc": "Portal lo student ki subject-wise syllabus coverage + mastery map chupisthundi (kill switch).",
    },
    "negative_mocks": {
        "default": True,
        "label": "🏁 Negative-marking mocks",
        "desc": "Portal mocks lo real-exam negative marking simulator (0/-0.25/-0.5/-1) allow chesthundi.",
    },
    "adaptive_mock": {
        "default": True,
        "label": "🧠 Adaptive Mock (Brain-composed)",
        "desc": "Mock tests Brain compose tho (weak topics + revision + level zone) tayaru avuthayi.",
    },
    "sprint_mode": {
        "default": True,
        "label": "🔥 Sprint Mode (exam <=14d)",
        "desc": "Exam daggara padithe intensive sprint plan card chupisthundi.",
    },
    "grand_mock": {
        "default": True,
        "label": "🏛️ Grand Mock (50Q full simulation)",
        "desc": "Portal lo full-length 50-question grand mock tests allow chesthundi.",
    },
    "sectional_tests": {
        "default": True,
        "label": "🧩 Sectional Tests",
        "desc": "Subject-wise (GK/Quant/Reasoning/English) sectional practice allow chesthundi.",
    },
    "daily_challenge": {
        "default": True,
        "label": "🏆 Challenge of the Day",
        "desc": "Portal home lo roju okka tough PYQ challenge (bonus points) chupisthundi.",
    },
    "similar_followup": {
        "default": True,
        "label": "🔗 Similar-question follow-up",
        "desc": "Practice lo wrong answer ki same-topic similar question try cheyyisthundi.",
    },
    "revenge_mode": {
        "default": True,
        "label": "😤 Revenge Mode practice",
        "desc": "Last attempt lo tappu chesina questions ne malli practice cheyyinche mode.",
    },
    "focus_timer": {
        "default": True,
        "label": "⏱️ Focus Timer (study sessions)",
        "desc": "Portal lo pomodoro focus timer + study minutes logging (daily/weekly focus stats).",
    },
    "goal_hub": {
        "default": True,
        "label": "🎓 Exam-wise Goal Hub",
        "desc": "Portal lo exam-wise hub: goal PYQ stock, repeat topics, mee best score, next best action.",
    },
    "mistake_notebook": {
        "default": True,
        "label": "📕 Mistake Notebook download",
        "desc": "Student tappu chesina questions anni okka downloadable notebook (correct answer + explanation).",
    },
    "exam_pyq_mocks": {
        "default": True,
        "label": "📜 Exam PYQ Mocks (exam-separate)",
        "desc": "Prathi exam ki aa exam previous-paper questions matrame vache strict PYQ mock tests.",
    },
    "blueprint_mocks": {
        "default": True,
        "label": "🧩 Blueprint Mocks (exam pattern)",
        "desc": "Real exam blueprint pattern (subject quotas + difficulty ramp + PYQ-first) tho compose ayye mock tests.",
    },
}


def _overrides() -> dict:
    try:
        d = load_json(FLAGS_FILE, {})
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def enabled(name: str) -> bool:
    """Current effective value. Unknown flag → True (fail-open)."""
    try:
        ov = _overrides()
        if name in ov:
            return bool(ov[name])
        meta = DEFAULTS.get(name)
        return bool(meta["default"]) if meta else True
    except Exception:
        meta = DEFAULTS.get(name)
        return bool(meta["default"]) if meta else True


def all_flags() -> list:
    ov = _overrides()
    out = []
    for name, meta in DEFAULTS.items():
        out.append({
            "name": name,
            "label": meta["label"],
            "desc": meta["desc"],
            "default": bool(meta["default"]),
            "enabled": bool(ov[name]) if name in ov else bool(meta["default"]),
            "overridden": name in ov,
        })
    return out


def set_flag(name: str, value: bool) -> bool:
    """Persist an override. False if the flag name is unknown."""
    if name not in DEFAULTS:
        return False
    try:
        ov = _overrides()
        ov[name] = bool(value)
        save_json_atomic(FLAGS_FILE, ov)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    for f in all_flags():
        print(f"{'🟢' if f['enabled'] else '🔴'} {f['name']}: {f['label']}"
              f"{'  (override)' if f['overridden'] else ''}")
