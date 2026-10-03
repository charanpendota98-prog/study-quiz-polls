import csv
import io
import json
import time
import zipfile
import base64
import xml.etree.ElementTree as ET
from pathlib import Path
from core import config
from core.store import load_json, save_json_atomic
from core import channel_router, whatsapp_pipeline

BUNDLES_FILE = config.DATA / "channel_bundles.json"


def load_bundles() -> dict:
    default = {
        "bundles": [
            {
                "id": "BUNDLE_POLICE",
                "name": "👮 Police Exam Mega Bundle (TS & AP)",
                "category": "POLICE",
                "target_groups": ["G_POLICE_TS_1", "G_POLICE_AP_1"],
                "target_channels": ["CURRENT"],
                "created_at": "2026-09-28T00:00:00"
            },
            {
                "id": "BUNDLE_ACADEMIC",
                "name": "🎓 Academic & Campus Cluster (B.Tech, Degree & Diploma)",
                "category": "DEGREE",
                "target_groups": ["G_BTECH_ALL_1", "G_DEGREE_ALL_1"],
                "target_channels": ["CAMPUS"],
                "created_at": "2026-09-28T00:00:00"
            },
            {
                "id": "BUNDLE_ALL_TELANGANA",
                "name": "🟪 All Telangana Competitive Groups (33 Districts)",
                "category": "TSPSC",
                "target_groups": [],
                "target_channels": [],
                "created_at": "2026-09-28T00:00:00"
            },
            {
                "id": "BUNDLE_ALL_ANDHRA",
                "name": "🟦 All Andhra Pradesh Competitive Groups (26 Districts)",
                "category": "APPSC",
                "target_groups": [],
                "target_channels": [],
                "created_at": "2026-09-28T00:00:00"
            }
        ]
    }
    return load_json(BUNDLES_FILE, default)


def save_bundles(d: dict):
    save_json_atomic(BUNDLES_FILE, d)


def create_bundle(name: str, category: str, group_ids: list, channel_keys: list, bundle_id: str = "") -> dict:
    d = load_bundles()
    b_id = bundle_id or ("BUNDLE_" + str(int(time.time())))
    # Check if updating an existing bundle or creating new
    existing = next((b for b in d.get("bundles", []) if b.get("id") == b_id or b.get("name").strip().lower() == name.strip().lower()), None)
    if existing:
        existing["name"] = name
        existing["category"] = category
        existing["target_groups"] = group_ids or []
        existing["target_channels"] = channel_keys or []
        existing["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        save_bundles(d)
        return existing

    new_b = {
        "id": b_id,
        "name": name,
        "category": category,
        "target_groups": group_ids or [],
        "target_channels": channel_keys or [],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S")
    }
    d.setdefault("bundles", []).append(new_b)
    save_bundles(d)
    return new_b


def get_bundle_by_id(bundle_id: str) -> dict:
    d = load_bundles()
    for b in d.get("bundles", []):
        if b.get("id") == bundle_id:
            return b
    return {}


def check_conflicts(target_group_ids: list = None, target_channel_keys: list = None, time_str: str = "", current_bundle_id: str = "") -> list:
    """
    Check if any selected group or channel is already part of an existing bundle or
    scheduled at the given time slot.
    Returns a list of conflict warning dicts.
    """
    conflicts = []
    g_set = set(target_group_ids or [])
    ch_set = set(target_channel_keys or [])
    clean_time = time_str.strip()
    if clean_time and len(clean_time) == 4 and clean_time[1] == ':':
        clean_time = "0" + clean_time

    # 1. Check against other Bundles
    bundles_data = load_bundles()
    for b in bundles_data.get("bundles", []):
        bid = b.get("id")
        if current_bundle_id and bid == current_bundle_id:
            continue
        b_name = b.get("name", bid)
        overlap_g = g_set.intersection(set(b.get("target_groups") or []))
        overlap_ch = ch_set.intersection(set(b.get("target_channels") or []))
        if overlap_g or overlap_ch:
            conflicts.append({
                "type": "bundle",
                "source": b_name,
                "source_id": bid,
                "conflicting_groups": list(overlap_g),
                "conflicting_channels": list(overlap_ch),
                "message": f"Already configured in bundle '{b_name}'"
            })

    # 2. Check against Active Schedules (especially for time slots)
    schedules = whatsapp_pipeline.load_schedules()
    for sch in schedules:
        if not sch.get("enabled", True):
            continue
        sch_time = sch.get("time", "").strip()
        sch_label = sch.get("label") or f"{sch_time} Drill"
        # If time matches or if checking all active schedule times
        time_matches = (not clean_time) or (sch_time == clean_time)
        if time_matches:
            overlap_g = g_set.intersection(set(sch.get("target_group_ids") or []))
            if overlap_g:
                conflicts.append({
                    "type": "schedule",
                    "source": sch_label,
                    "time": sch_time,
                    "conflicting_groups": list(overlap_g),
                    "message": f"Already scheduled for {sch_time} in '{sch_label}'"
                })

    return conflicts


def delete_bundle(bundle_id: str) -> bool:
    d = load_bundles()
    orig_len = len(d.get("bundles", []))
    d["bundles"] = [b for b in d.get("bundles", []) if b.get("id") != bundle_id]
    if len(d["bundles"]) != orig_len:
        save_bundles(d)
        return True
    return False


def inspect_xlsx_sheets_bytes(xlsx_bytes: bytes) -> list:
    """Inspect an .xlsx workbook and return list of sheet names and row counts."""
    zf = zipfile.ZipFile(io.BytesIO(xlsx_bytes))
    wb_tree = ET.fromstring(zf.read('xl/workbook.xml'))
    wb_ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
             'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
    sheets = []
    for s in wb_tree.findall('.//ns:sheet', wb_ns):
        sname = s.attrib.get('name')
        rid = s.attrib.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id') or s.attrib.get('r:id')
        sheets.append({'name': sname, 'id': rid})

    rels_tree = ET.fromstring(zf.read('xl/_rels/workbook.xml.rels'))
    rel_ns = {'r': 'http://schemas.openxmlformats.org/package/2006/relationships'}
    rid_to_target = {}
    for rel in rels_tree.findall('.//r:Relationship', rel_ns):
        rid_to_target[rel.attrib.get('Id')] = rel.attrib.get('Target')

    s_ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    info = []
    for s in sheets:
        target = rid_to_target.get(s['id'])
        if not target:
            continue
        sheet_path = target.lstrip('/')
        if not sheet_path.startswith('xl/'):
            sheet_path = 'xl/' + sheet_path
        if sheet_path not in zf.namelist():
            continue
        stree = ET.fromstring(zf.read(sheet_path))
        rows = stree.findall('.//ns:row', s_ns)
        info.append({'name': s['name'], 'rows_count': len(rows)})
    return info


def parse_xlsx_sheets_data(xlsx_bytes: bytes, selected_sheets: list = None) -> dict:
    """Parse specified or all sheets from an .xlsx file into rows of cell values."""
    zf = zipfile.ZipFile(io.BytesIO(xlsx_bytes))
    shared_strings = []
    if 'xl/sharedStrings.xml' in zf.namelist():
        stree = ET.fromstring(zf.read('xl/sharedStrings.xml'))
        sns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        for si in stree.findall('.//ns:si', sns):
            txt = ''.join(t.text for t in si.findall('.//ns:t', sns) if t.text)
            shared_strings.append(txt)

    wb_tree = ET.fromstring(zf.read('xl/workbook.xml'))
    wb_ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
             'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
    sheets = []
    for s in wb_tree.findall('.//ns:sheet', wb_ns):
        sname = s.attrib.get('name')
        rid = s.attrib.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id') or s.attrib.get('r:id')
        if selected_sheets is None or sname in selected_sheets:
            sheets.append((sname, rid))

    rels_tree = ET.fromstring(zf.read('xl/_rels/workbook.xml.rels'))
    rel_ns = {'r': 'http://schemas.openxmlformats.org/package/2006/relationships'}
    rid_to_target = {}
    for rel in rels_tree.findall('.//r:Relationship', rel_ns):
        rid_to_target[rel.attrib.get('Id')] = rel.attrib.get('Target')

    s_ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    result = {}
    for sname, rid in sheets:
        target = rid_to_target.get(rid)
        if not target:
            continue
        sheet_path = target.lstrip('/')
        if not sheet_path.startswith('xl/'):
            sheet_path = 'xl/' + sheet_path
        if sheet_path not in zf.namelist():
            continue

        sheet_tree = ET.fromstring(zf.read(sheet_path))
        rows = []
        for row in sheet_tree.findall('.//ns:row', s_ns):
            row_vals = []
            for c in row.findall('.//ns:c', s_ns):
                ctype = c.attrib.get('t')
                inline_t = c.find('.//ns:is/ns:t', s_ns)
                if inline_t is not None and inline_t.text:
                    val = inline_t.text
                else:
                    val_elem = c.find('.//ns:v', s_ns)
                    val = val_elem.text if val_elem is not None and val_elem.text else ''
                    if ctype == 's' and val.isdigit():
                        idx = int(val)
                        val = shared_strings[idx] if idx < len(shared_strings) else val
                row_vals.append(val.strip())
            if any(row_vals):
                rows.append(row_vals)
        result[sname] = rows
    return result


def import_rows_list(rows: list, default_category: str = "") -> dict:
    """Takes row lists and saves to DB. ADVANCED columns (all after col-5 optional):
    [1 Group Name | 2 Link or JID | 3 Category | 4 Shift | 5 Group Type |
     6 Daily Times (08:00+20:30) | 7 Polls Per Slot | 8 Days (0=Always) | 9 Subjects (MATHS+GK)]
    Rows with Daily Times get an automatic daily schedule after import."""
    import re as _re
    added_groups = []
    added_channels = []
    schedules_wanted = []

    for parts in rows:
        if not parts or not parts[0]:
            continue
        name = str(parts[0]).strip()
        if name.lower() in ("name", "title", "group name", "channel name", "group", "group/channel name"):
            continue

        link_or_jid = str(parts[1]).strip() if len(parts) > 1 else ""
        category = str(parts[2]).strip() if len(parts) > 2 and parts[2] else (default_category or channel_router.detect_exam_base(name))
        shift = str(parts[3]).strip().upper() if len(parts) > 3 and str(parts[3]).strip().upper() in ("MORNING", "EVENING", "ALL_DAY") else "ALL_DAY"
        g_type = str(parts[4]).strip().upper() if len(parts) > 4 and parts[4] else ("GENERAL" if "general" in (category.lower() + " " + name.lower()) else "EXAM_SPECIFIC")

        # ---- advanced auto-schedule columns (6-9) ----
        raw_times = str(parts[5]).strip() if len(parts) > 5 else ""
        times = []
        for tok in _re.split(r"[+;/\s]+", raw_times):
            tok = tok.strip()
            if _re.fullmatch(r"\d{1,2}:\d{2}", tok):
                times.append(("0" + tok) if len(tok) == 4 else tok)
        try:
            polls_per_slot = max(1, min(int(float(str(parts[6]).strip())), 20)) if len(parts) > 6 and str(parts[6]).strip() else 5
        except Exception:
            polls_per_slot = 5
        try:
            days = max(0, int(float(str(parts[7]).strip()))) if len(parts) > 7 and str(parts[7]).strip() else 0
        except Exception:
            days = 0
        raw_subj = str(parts[8]).strip().upper() if len(parts) > 8 else ""
        subjects = [s for s in _re.split(r"[+;,/\s]+", raw_subj) if s and s != "ALL"]

        if link_or_jid.startswith("@") or "t.me/" in link_or_jid:
            ch_info = channel_router.register_channel(name, chat_id=link_or_jid, exam_type=category)
            added_channels.append(ch_info)
            continue

        if "chat.whatsapp.com" in link_or_jid:
            # invite link → Quick-Add engine (auto-joins via bridge when connected, dedups by jid)
            qres = whatsapp_pipeline.quick_add_groups(f"{name} | {link_or_jid} | {category}")
            grp = None
            if qres.get("added"):
                a = qres["added"][0]
                reg = whatsapp_pipeline.load_wa_registry()
                grp = next((g for g in reg.get("groups", []) if g.get("jid") == a.get("jid") or g.get("name") == name), None)
            if not grp:
                grp = whatsapp_pipeline.add_group(name, link_or_jid, category=category, shift=shift, group_type=g_type)
            added_groups.append(grp)
        else:
            grp = whatsapp_pipeline.add_group(name, link_or_jid, category=category, shift=shift, group_type=g_type)
            added_groups.append(grp)

        if times and grp and grp.get("id"):
            schedules_wanted.append({
                "gid": grp["id"],
                "times": times,
                "count": polls_per_slot,
                "days": days,
                "subjects": subjects,
                "category": category,
            })

    return {
        "ok": True,
        "imported_groups_count": len(added_groups),
        "imported_channels_count": len(added_channels),
        "groups": added_groups,
        "channels": added_channels,
        "schedules_wanted": schedules_wanted,
    }


def create_schedules_for_imports(schedules_wanted: list, label_prefix: str = "📥 Excel") -> list:
    """Group identical schedule configs together → one job per time slot
    covering all matching groups (clean scheduler, no job spam)."""
    created = []
    buckets = {}
    for s in schedules_wanted or []:
        key = ("+".join(s["times"]), s["count"], s["days"], "+".join(s["subjects"]), s["category"])
        buckets.setdefault(key, []).append(s)
    for (times_key, count, days, subj_key, category), items in buckets.items():
        gids = [s["gid"] for s in items]
        subjects = items[0]["subjects"]
        for t in items[0]["times"]:
            job = whatsapp_pipeline.add_scheduled_job(
                t,
                target_group_ids=gids,
                category=category or "ALL",
                questions_count=count,
                days_duration=days,
                auto_mode=(days == 0),
                subjects=subjects,
                mode="wa",
                label=f"{label_prefix} {t} · {len(gids)} group(s)" + (f" · {subj_key}" if subj_key else "") + (f" · {days}d" if days else " · Always-On"),
            )
            created.append({"id": job["id"], "time": job["time"], "groups": len(gids), "days": days})
    return created


def build_multisheet_xlsx_bytes(sheets: dict) -> bytes:
    """Generic native .xlsx builder (no external libs): {sheet_name: [[row], ...]}."""
    def _esc(v):
        return str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    names = list(sheets.keys())
    ws_xmls = []
    for sname in names:
        rows_xml = []
        for r_idx, row in enumerate(sheets[sname], 1):
            cells = "".join(f'<c t="inlineStr"><is><t xml:space="preserve">{_esc(v)}</t></is></c>' for v in row)
            rows_xml.append(f'<row r="{r_idx}">{cells}</row>')
        ws_xmls.append(
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{"".join(rows_xml)}</sheetData></worksheet>'
        )

    overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{i+1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for i in range(len(names))
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        f'{overrides}</Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )
    sheet_tags = "".join(
        f'<sheet name="{_esc(n)[:31]}" sheetId="{i+1}" r:id="rId{i+1}"/>' for i, n in enumerate(names)
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets>{sheet_tags}</sheets></workbook>'
    )
    wb_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="rId{i+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i+1}.xml"/>'
            for i in range(len(names))
        )
        + '</Relationships>'
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        for i, x in enumerate(ws_xmls):
            z.writestr(f"xl/worksheets/sheet{i+1}.xml", x)
    return buf.getvalue()


TEMPLATE_HEADER = ["Group Name", "Invite Link or JID", "Exam Category", "Shift",
                   "Group Type", "Daily Times", "Polls Per Slot", "Days (0=Always)", "Subjects"]


def build_groups_template_xlsx() -> bytes:
    """📥 BEST-PRACTICE sample workbook: Instructions (Telugu) + 3 exam sheets
    pre-filled with example rows covering every advanced column."""
    instructions = [
        ["📖 StudentUp — WhatsApp Groups Bulk Import & Auto-Schedule Template"],
        [""],
        ["✅ ఎలా వాడాలి:"],
        ["1. పక్క sheets లో (Police_SI_Groups, TET_DSC_Groups, Banking_Groups) మీ groups rows నింపండి."],
        ["2. కావాలంటే కొత్త sheets add చేసుకోండి — sheet పేరు exam పేరుతో పెడితే category auto-detect అవుతుంది."],
        ["3. Dashboard → 📊 Multi-Sheet Excel Importer → file upload → కావాల్సిన sheets select → Import!"],
        ["4. Daily Times column నింపిన ప్రతి group కి ఆటోమేటిక్ డైలీ schedule create అవుతుంది — మీరు ఏమీ చేయక్కర్లేదు!"],
        [""],
        ["📋 Columns గైడ్:"],
        ["Group Name", "గ్రూప్ పేరు (ఉదా: Warangal SI Batch 1)"],
        ["Invite Link or JID", "https://chat.whatsapp.com/XXXX (link అయితే bridge connect అయినప్పుడు auto-join!) లేదా 1203...@g.us"],
        ["Exam Category", "POLICE / TET_DSC / SSC / BANKING / RAILWAY / AP_BTECH / TS_10TH ... లేదా AUTO"],
        ["Shift", "MORNING / EVENING / ALL_DAY"],
        ["Group Type", "EXAM_SPECIFIC లేదా GENERAL"],
        ["Daily Times", "రోజూ ఎన్నిసార్లు+ఎప్పుడు: 08:00+13:00+20:30 (+ తో విడదీయండి; ఖాళీ వదిలేస్తే schedule ఉండదు)"],
        ["Polls Per Slot", "ఒక్కో time కి ఎన్ని polls (1-20, default 5)"],
        ["Days (0=Always)", "ఎన్ని రోజులు నడవాలి — 0 అంటే ఎప్పటికీ (Always-On), 30 అంటే 30 రోజులు"],
        ["Subjects", "MATHS+REASONING+GK+CURRENT+ENGLISH+SCIENCE — ఖాళీ అంటే ALL subjects"],
        [""],
        ["🛡️ WhatsApp sends అన్నీ anti-ban engine (40-60s gaps) తోనే వెళ్తాయి — safe!"],
    ]
    police = [
        TEMPLATE_HEADER,
        ["Warangal SI Batch 1", "https://chat.whatsapp.com/EXAMPLE1AbCdEf", "POLICE", "ALL_DAY", "EXAM_SPECIFIC", "08:00+20:30", "5", "0", "REASONING+GK+CURRENT"],
        ["Hyderabad Constable Daily", "https://chat.whatsapp.com/EXAMPLE2GhIjKl", "POLICE", "EVENING", "EXAM_SPECIFIC", "19:00", "10", "60", "MATHS+REASONING"],
        ["Karimnagar SI Mock Tests", "120363000000000001@g.us", "POLICE", "MORNING", "EXAM_SPECIFIC", "06:30+12:00+21:00", "3", "0", ""],
    ]
    tet = [
        TEMPLATE_HEADER,
        ["TS TET Paper-1 Aspirants", "https://chat.whatsapp.com/EXAMPLE3MnOpQr", "TET_DSC", "ALL_DAY", "EXAM_SPECIFIC", "07:00+18:00", "5", "90", "GK+ENGLISH"],
        ["AP DSC SGT Practice Hub", "120363000000000002@g.us", "TET_DSC", "ALL_DAY", "EXAM_SPECIFIC", "", "", "", ""],
    ]
    banking = [
        TEMPLATE_HEADER,
        ["IBPS PO Speed Maths", "https://chat.whatsapp.com/EXAMPLE4StUvWx", "BANKING", "MORNING", "EXAM_SPECIFIC", "09:00", "5", "45", "MATHS+REASONING+ENGLISH"],
        ["SBI Clerk Current Affairs", "120363000000000003@g.us", "BANKING", "ALL_DAY", "EXAM_SPECIFIC", "08:30+20:00", "5", "0", "CURRENT+GK"],
    ]
    return build_multisheet_xlsx_bytes({
        "📖 Instructions": instructions,
        "Police_SI_Groups": police,
        "TET_DSC_Groups": tet,
        "Banking_Groups": banking,
    })


def import_from_csv_or_excel_text(raw_text: str) -> dict:
    """Parses comma-separated, tab-separated or pipe-separated lines."""
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    rows = []
    for line in lines:
        if "\t" in line:
            parts = [p.strip() for p in line.split("\t")]
        elif "," in line:
            try:
                reader = csv.reader(io.StringIO(line))
                parts = [p.strip() for p in next(reader)]
            except Exception:
                parts = [p.strip() for p in line.split(",")]
        elif "|" in line:
            parts = [p.strip() for p in line.split("|")]
        else:
            parts = [line]
        rows.append(parts)
    res = import_rows_list(rows)
    res["schedules_created"] = create_schedules_for_imports(res.pop("schedules_wanted", []), "📥 Paste")
    return res


def import_from_multisheet_excel(xlsx_bytes: bytes, selected_sheet_names: list = None) -> dict:
    """Reads multiple sheets from an .xlsx file and imports all rows into the database."""
    sheet_data = parse_xlsx_sheets_data(xlsx_bytes, selected_sheet_names)
    total_groups = 0
    total_channels = 0
    all_groups = []
    all_channels = []
    all_schedules = []
    per_sheet = {}

    for sname, rows in sheet_data.items():
        if "instruction" in sname.lower() or "📖" in sname:
            continue  # skip the guide sheet from the sample template
        res = import_rows_list(rows, default_category=channel_router.detect_exam_base(sname))
        sched = create_schedules_for_imports(res.pop("schedules_wanted", []), f"📥 {sname}")
        all_schedules.extend(sched)
        total_groups += res["imported_groups_count"]
        total_channels += res["imported_channels_count"]
        all_groups.extend(res["groups"])
        all_channels.extend(res["channels"])
        per_sheet[sname] = {
            "groups": res["imported_groups_count"],
            "channels": res["imported_channels_count"],
            "schedules": len(sched),
        }

    return {
        "ok": True,
        "sheets_processed": [s for s in sheet_data.keys()],
        "imported_groups_count": total_groups,
        "imported_channels_count": total_channels,
        "schedules_created": all_schedules,
        "per_sheet": per_sheet,
        "groups": all_groups,
        "channels": all_channels
    }


def dispatch_bulk_broadcast(
    message: str,
    attachment_url: str = "",
    attachment_data_b64: str = "",
    attachment_filename: str = "",
    target_group_ids: list = None,
    target_channel_keys: list = None,
    gateway_url: str = ""
) -> dict:
    """
    Sends bulk messages and attachments across selected WhatsApp Groups and Telegram Channels.
    """
    from core.telegram import Telegram
    tg = Telegram()
    results = {
        "ok": True,
        "whatsapp_dispatched": 0,
        "telegram_dispatched": 0,
        "errors": []
    }

    # 1. Telegram Channels Dispatch
    if target_channel_keys:
        ch_reg = channel_router.load_channels()
        custom_chs = channel_router.load_custom_channels().get("channels", {})
        all_chs = dict(ch_reg)
        all_chs.update(custom_chs)

        att_bytes = base64.b64decode(attachment_data_b64) if attachment_data_b64 else None

        for ch_key in target_channel_keys:
            ch = all_chs.get(ch_key)
            if not ch:
                continue
            chat_id = ch.get("chat_id")
            if not chat_id:
                continue
            try:
                if att_bytes:
                    fname = attachment_filename or "document.pdf"
                    if fname.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                        tg.send_photo(chat_id, att_bytes, caption=message[:1000], filename=fname)
                    else:
                        tg.send_document(chat_id, fname, att_bytes, caption=message[:1000])
                elif attachment_url:
                    full_text = f"{message}\n\n📎 Attachment: {attachment_url}" if message else f"📎 Attachment: {attachment_url}"
                    tg.send_message(chat_id, full_text, disable_preview=False)
                else:
                    tg.send_message(chat_id, message, disable_preview=True)
                results["telegram_dispatched"] += 1
            except Exception as e:
                results["errors"].append(f"Telegram {ch_key} ({chat_id}): {e}")

    # 2. WhatsApp Groups Dispatch — runs in a BACKGROUND thread with random
    #    human-like jitter between groups (so 100+ groups never get blasted
    #    in the same second, and the HTTP request returns instantly).
    if target_group_ids:
        import threading
        import random as _random
        import time as _time

        reg = whatsapp_pipeline.load_wa_registry()
        groups = reg.get("groups", [])
        gw = gateway_url or whatsapp_pipeline.EXEC_STATE.get("gateway") or ""
        picked = []
        for gid in target_group_ids:
            grp = next((g for g in groups if g.get("id") == gid), None)
            if grp:
                picked.append(grp)

        real_mode = whatsapp_pipeline.bridge_is_connected()

        def _wa_worker():
            sent, errs = 0, 0
            whatsapp_pipeline._log(f"📨 Bulk message dispatch started → {len(picked)} WhatsApp groups (jitter 6-14s/group).")
            for i, grp in enumerate(picked):
                jid = grp.get("jid") or grp.get("link")
                try:
                    att = attachment_url or (f"data:application/octet-stream;base64,{attachment_data_b64}" if attachment_data_b64 else "")
                    ok, status = whatsapp_pipeline._dispatch_raw(gw, jid, message, attachment=att)
                    if ok:
                        sent += 1
                        whatsapp_pipeline._log(f"   ✅ [{i+1}/{len(picked)}] {grp.get('name')} → {status}")
                    else:
                        errs += 1
                        whatsapp_pipeline._log(f"   ❌ [{i+1}/{len(picked)}] {grp.get('name')} → {status}")
                except Exception as e:
                    errs += 1
                    whatsapp_pipeline._log(f"   ❌ [{i+1}/{len(picked)}] {grp.get('name')} → {e}")
                if i < len(picked) - 1:
                    gap = _random.uniform(6, 14)
                    _time.sleep(gap if real_mode else min(gap, 0.3))
            whatsapp_pipeline._log(f"🏁 Bulk message dispatch finished: {sent} sent, {errs} failed.")

        threading.Thread(target=_wa_worker, daemon=True).start()
        results["whatsapp_queued"] = len(picked)
        results["whatsapp_dispatched"] = len(picked)
        results["whatsapp_note"] = "Queued with 6-14s anti-ban jitter per group — live progress in the Dispatcher log panel."

    return results
