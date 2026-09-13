"""TS / AP district master (2026) — used by registration, profiles and the
district-wise leaderboard. Telugu names included for the bot prompts."""
from __future__ import annotations
import re

TS_DISTRICTS = [
    ("Adilabad", "ఆదిలాబాద్"), ("Bhadradri Kothagudem", "భద్రాద్రి కొత్తగూడెం"),
    ("Hanumakonda", "హనుమకొండ"), ("Hyderabad", "హైదరాబాద్"), ("Jagtial", "జగిత్యాల"),
    ("Jangaon", "జనగామ"), ("Jayashankar Bhupalpally", "జయశంకర్ భూపాలపల్లి"),
    ("Jogulamba Gadwal", "జోగులాంబ గద్వాల"), ("Kamareddy", "కామారెడ్డి"),
    ("Karimnagar", "కరీంనగర్"), ("Khammam", "ఖమ్మం"), ("Komaram Bheem Asifabad", "కుమురం భీం ఆసిఫాబాద్"),
    ("Mahabubabad", "మహబూబాబాద్"), ("Mahabubnagar", "మహబూబ్‌నగర్"), ("Mancherial", "మంచిర్యాల"),
    ("Medak", "మెదక్"), ("Medchal-Malkajgiri", "మేడ్చల్-మల్కాజిగిరి"), ("Mulugu", "ములుగు"),
    ("Nagarkurnool", "నాగర్‌కర్నూల్"), ("Nalgonda", "నల్గొండ"), ("Narayanpet", "నారాయణపేట"),
    ("Nirmal", "నిర్మల్"), ("Nizamabad", "నిజామాబాద్"), ("Peddapalli", "పెద్దపల్లి"),
    ("Rajanna Sircilla", "రాజన్న సిరిసిల్ల"), ("Ranga Reddy", "రంగారెడ్డి"), ("Sangareddy", "సంగారెడ్డి"),
    ("Siddipet", "సిద్దిపేట"), ("Suryapet", "సూర్యాపేట"), ("Vikarabad", "వికారాబాద్"),
    ("Wanaparthy", "వనపర్తి"), ("Warangal", "వరంగల్"), ("Yadadri Bhuvanagiri", "యాదాద్రి భువనగిరి"),
]
AP_DISTRICTS = [
    ("Alluri Sitharama Raju", "అల్లూరి సీతారామరాజు"), ("Anakapalli", "అనకాపల్లి"),
    ("Anantapur", "అనంతపురం"), ("Annamayya", "అన్నమయ్య"), ("Bapatla", "బాపట్ల"),
    ("Chittoor", "చిత్తూరు"), ("East Godavari", "తూర్పు గోదావరి"), ("Eluru", "ఏలూరు"),
    ("Guntur", "గుంటూరు"), ("Kakinada", "కాకినాడ"), ("Konaseema", "కోనసీమ"),
    ("Krishna", "కృష్ణా"), ("Kurnool", "కర్నూలు"), ("Nandyal", "నంద్యాల"),
    ("NTR", "ఎన్టీఆర్"), ("Palnadu", "పల్నాడు"), ("Parvathipuram Manyam", "పార్వతీపురం మన్యం"),
    ("Prakasam", "ప్రకాశం"), ("Sri Potti Sriramulu Nellore", "నెల్లూరు"),
    ("Sri Sathya Sai", "శ్రీ సత్యసాయి"), ("Srikakulam", "శ్రీకాకుళం"), ("Tirupati", "తిరుపతి"),
    ("Visakhapatnam", "విశాఖపట్నం"), ("Vizianagaram", "విజయనగరం"),
    ("West Godavari", "పశ్చిమ గోదావరి"), ("YSR Kadapa", "వైఎస్సార్ కడప"),
]
STATES = {"TS": ("Telangana", "తెలంగాణ", TS_DISTRICTS),
          "AP": ("Andhra Pradesh", "ఆంధ్రప్రదేశ్", AP_DISTRICTS)}
_ALIASES = {"hyd": "Hyderabad", "vizag": "Visakhapatnam", "vskp": "Visakhapatnam",
            "nellore": "Sri Potti Sriramulu Nellore", "kadapa": "YSR Kadapa", "cuddapah": "YSR Kadapa",
            "puttaparthi": "Sri Sathya Sai", "vijayawada": "NTR", "bezawada": "NTR",
            "rajahmundry": "East Godavari", "amalapuram": "Konaseema", "rangareddy": "Ranga Reddy",
            "medchal": "Medchal-Malkajgiri", "malkajgiri": "Medchal-Malkajgiri", "secunderabad": "Hyderabad",
            "bhupalpally": "Jayashankar Bhupalpally", "gadwal": "Jogulamba Gadwal", "asifabad": "Komaram Bheem Asifabad",
            "kothagudem": "Bhadradri Kothagudem", "sircilla": "Rajanna Sircilla", "bhuvanagiri": "Yadadri Bhuvanagiri",
            "warangal urban": "Hanumakonda", "warangal rural": "Warangal", "machilipatnam": "Krishna",
            "narasaraopet": "Palnadu", "ongole": "Prakasam", "araku": "Alluri Sitharama Raju"}


def state_list_text() -> str:
    return "  1. Telangana / తెలంగాణ\n  2. Andhra Pradesh / ఆంధ్రప్రదేశ్\n  3. Other / ఇతర"


def match_state(text: str):
    t = (text or "").strip().lower()
    if t in ("1", "ts", "tg", "telangana", "తెలంగాణ") or "telangana" in t or "తెలంగాణ" in t:
        return "TS"
    if t in ("2", "ap", "andhra", "andhra pradesh", "ఆంధ్ర") or "andhra" in t or "ఆంధ్ర" in t:
        return "AP"
    if t in ("3", "other", "others", "ఇతర"):
        return "OTHER"
    return None


def district_list_text(state: str) -> str:
    _, _, rows = STATES[state]
    pre = "T" if state == "TS" else ("A" if state == "AP" else "")
    return "\n".join(f"  {pre}{i+1}. {en} / {te}" for i, (en, te) in enumerate(rows))


def match_district(state: str, text: str):
    """Number, English or Telugu name, or alias -> canonical English name."""
    if state not in STATES:
        return None
    rows = STATES[state][2]
    t = (text or "").strip()
    if t.isdigit() and 1 <= int(t) <= len(rows):
        return rows[int(t) - 1][0]
    low = t.lower()
    for en, te in rows:
        if low == en.lower() or t == te:
            return en
    for en, te in rows:
        if (len(low) >= 4 and low in en.lower()) or (t and t in te):
            return en
    for k, v in _ALIASES.items():
        if k in low and any(v == en for en, _ in rows):
            return v
    return None


def telugu_name(district: str) -> str:
    for _, _, rows in STATES.values():
        for en, te in rows:
            if en == district:
                return te
    return district


def match_any_district(text):
    """Match against BOTH states. Accepts 'T12'/'A5' list codes, numbers are
    ambiguous so plain digits try TS then AP. Returns (state_code, district)."""
    t = (text or "").strip()
    low = t.lower()
    if len(low) >= 2 and low[0] in "ta" and low[1:].isdigit():
        code = "TS" if low[0] == "t" else "AP"
        d = match_district(code, low[1:])
        return (code, d) if d else (None, None)
    for code in ("TS", "AP"):
        d = match_district(code, t)
        if d:
            return code, d
    return None, None


def sorted_districts(state: str):
    """Alphabetical (English) list of (en, te) for a state."""
    if state not in STATES:
        return []
    return sorted(STATES[state][2], key=lambda r: r[0].lower())


def state_of(district: str) -> str:
    """'TS' | 'AP' | '' for a district name."""
    for code, (_en, _te, lst) in STATES.items():
        if any((d[0] if isinstance(d, tuple) else d) == district for d in lst):
            return code
    return ""
