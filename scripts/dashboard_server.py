#!/usr/bin/env python3
"""
STUDENTUP — FULL CONTROL WEB DASHBOARD & ADVANCED AUTOMATION HUB
Features:
  1. Live Question Bank Inventory & Channel Poll Counts.
  2. Excel / Google Sheets Importer: Direct Paste or Upload 100+ to 150+ WhatsApp Groups & Telegram Channels.
  3. Custom Cluster Bundles: Group specific channels and WhatsApp groups into single-click dispatch bundles.
  4. WhatsApp 100+ Interleaved Anti-Ban Pipeline: 2-by-2 groups with 20-30s natural thinking gaps, two-phase answer key delivery.
  5. TS & AP Academic (B.Tech, Degree, ITI, Open Universities, Diploma, Inter, 10th) & Competitive Channels.
"""
import sys
import os
import json
import time
import base64
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from core import config
from core.members import Members
from core.question_bank import Bank
from core import hooks, districtwar, arena, campus, crm, whatsapp_pipeline, channel_router, bundle_manager
from core.telegram import Telegram

PORT = int(config.env("DASHBOARD_PORT", "5000"))

# =====================================================================
# 🔒 DASHBOARD ACCESS LOCK — only the admin can open this panel.
# Password lives in data/dashboard_auth.json (or env DASHBOARD_PASSWORD).
# Login issues a 30-day HttpOnly cookie token; everything else is 401.
# =====================================================================
import secrets as _secrets

AUTH_FILE = config.DATA / "dashboard_auth.json"
LOGIN_AUDIT_FILE = config.DATA / "login_audit.json"
_START_TS = time.time()


def _log_login_attempt(ip: str, ok: bool):
    """🔐 Security audit: record every login attempt (success & failure)."""
    try:
        d = {"attempts": []}
        if LOGIN_AUDIT_FILE.exists():
            loaded = json.loads(LOGIN_AUDIT_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("attempts"), list):
                d = loaded
        d["attempts"].append({
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "ip": str(ip)[:60],
            "ok": bool(ok),
        })
        d["attempts"] = d["attempts"][-200:]
        LOGIN_AUDIT_FILE.write_text(json.dumps(d, indent=1), encoding="utf-8")
    except Exception:
        pass


def _recent_logins(limit: int = 8) -> list:
    try:
        if LOGIN_AUDIT_FILE.exists():
            d = json.loads(LOGIN_AUDIT_FILE.read_text(encoding="utf-8"))
            return list(reversed(d.get("attempts", [])[-limit:]))
    except Exception:
        pass
    return []
DEFAULT_DASH_PASSWORD = "studentup123"


def _load_auth() -> dict:
    try:
        if AUTH_FILE.exists():
            d = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
            d.setdefault("password", DEFAULT_DASH_PASSWORD)
            d.setdefault("tokens", [])
            return d
    except Exception:
        pass
    d = {"password": DEFAULT_DASH_PASSWORD, "tokens": []}
    _save_auth(d)
    return d


def _save_auth(d: dict):
    try:
        AUTH_FILE.write_text(json.dumps(d, indent=2), encoding="utf-8")
    except Exception:
        pass


def _dash_password() -> str:
    envp = os.environ.get("DASHBOARD_PASSWORD", "").strip()
    return envp if envp else _load_auth().get("password", DEFAULT_DASH_PASSWORD)


LOGIN_PAGE = """<!DOCTYPE html>
<html lang="te">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🔒 StudentUp — Admin Login</title>
<style>
  body { margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
         background:radial-gradient(circle at 30% 20%, #0f2040 0%, #050811 70%);
         font-family:'Segoe UI', system-ui, sans-serif; color:#e2e8f0; }
  .card { background:#0b1329; border:1px solid #1e3a5f; border-radius:16px; padding:36px 32px;
          width:min(380px, 90vw); box-shadow:0 20px 60px rgba(0,0,0,0.6); text-align:center; }
  .lock { font-size:46px; margin-bottom:10px; }
  h1 { font-size:20px; margin:0 0 6px; color:#38bdf8; }
  p  { font-size:13px; color:#94a3b8; margin:0 0 20px; line-height:1.6; }
  input { width:100%; box-sizing:border-box; padding:12px 14px; font-size:16px; letter-spacing:2px;
          background:#050811; color:#f8fafc; border:1px solid #1e3a5f; border-radius:10px; outline:none; text-align:center; }
  input:focus { border-color:#38bdf8; }
  button { width:100%; margin-top:14px; padding:12px; font-size:15px; font-weight:800; border:none;
           border-radius:10px; background:linear-gradient(90deg, #10b981, #38bdf8); color:#050811; cursor:pointer; }
  button:hover { filter:brightness(1.1); }
  .err { color:#f87171; font-size:13px; font-weight:700; min-height:18px; margin-top:12px; }
  .hint { margin-top:18px; font-size:11px; color:#475569; }
</style>
</head>
<body>
  <div class="card">
    <div class="lock">🔒</div>
    <h1>StudentUp Admin Panel</h1>
    <p>ఈ డాష్‌బోర్డ్ లాక్ చేయబడింది.<br>Admin password ఎంటర్ చేస్తేనే లోపలికి వెళ్ళగలరు.</p>
    <input type="password" id="pw" placeholder="Admin Password" autofocus
           onkeydown="if(event.key==='Enter')doLogin()">
    <button onclick="doLogin()">🔓 Unlock Dashboard</button>
    <div class="err" id="err"></div>
    <div class="hint">Default password: <b>studentup123</b> — login అయ్యాక 🔑 బటన్‌తో వెంటనే మార్చుకోండి!</div>
  </div>
<script>
async function doLogin() {
  const pw = document.getElementById('pw').value;
  const err = document.getElementById('err');
  err.innerText = '';
  try {
    const r = await fetch('/api/auth/login', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({password: pw})});
    const d = await r.json();
    if (d.ok) { location.href = '/'; }
    else { err.innerText = '❌ తప్పు పాస్‌వర్డ్! Wrong password.'; document.getElementById('pw').value=''; }
  } catch(e) { err.innerText = '❌ Server error: ' + e; }
}
</script>
</body>
</html>"""

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>StudentUp — Ultimate Control, Excel Importer & Bundle Hub</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #0b0f19;
      --card: #131b2e;
      --border: #22304d;
      --primary: #3b82f6;
      --primary-hover: #2563eb;
      --accent: #10b981;
      --accent-hover: #059669;
      --danger: #ef4444;
      --warning: #f59e0b;
      --purple: #8b5cf6;
      --pink: #ec4899;
      --text: #f8fafc;
      --text-muted: #94a3b8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }
    body { background: var(--bg); color: var(--text); padding: 24px; min-height: 100vh; }
    .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 18px; margin-bottom: 22px; }
    .header h1 { font-size: 24px; font-weight: 800; display: flex; align-items: center; gap: 10px; }
    .badge-live { background: rgba(16, 185, 129, 0.15); color: var(--accent); border: 1px solid var(--accent); padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; }
    .badge-shield { background: rgba(139, 92, 246, 0.15); color: var(--purple); border: 1px solid var(--purple); padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; }
    .grid-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 22px; }
    .stat-card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }
    .stat-card .label { font-size: 12px; color: var(--text-muted); font-weight: 500; }
    .stat-card .val { font-size: 28px; font-weight: 800; margin-top: 5px; }
    .stat-card .desc { font-size: 11px; color: var(--text-muted); margin-top: 3px; }
    .tabs { display: flex; gap: 8px; margin-bottom: 20px; border-bottom: 1px solid var(--border); padding-bottom: 10px; overflow-x: auto; }
    .tab-btn { background: transparent; border: none; color: var(--text-muted); font-size: 14px; font-weight: 600; padding: 8px 16px; border-radius: 8px; cursor: pointer; transition: all 0.2s; white-space: nowrap; }
    .tab-btn.active { background: var(--primary); color: #fff; }
    .tab-pane { display: none; }
    .tab-pane.active { display: block; }
    .panel-card { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 22px; margin-bottom: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.25); }
    .panel-card h2 { font-size: 18px; margin-bottom: 14px; display: flex; align-items: center; gap: 8px; }
    .btn { background: var(--primary); color: #fff; border: none; padding: 9px 15px; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; transition: all 0.2s ease; display: inline-flex; align-items: center; gap: 6px; box-shadow: 0 2px 4px rgba(0,0,0,0.15); }
    .btn:hover { background: var(--primary-hover); transform: translateY(-1px); }
    .btn:active { transform: translateY(0); }
    .btn-accent { background: var(--accent); }
    .btn-accent:hover { background: var(--accent-hover); }
    .btn-purple { background: var(--purple); }
    .btn-pink { background: var(--pink); }
    .btn-danger { background: var(--danger); }
    .btn-outline { background: rgba(255,255,255,0.03); border: 1px solid var(--border); color: var(--text); }
    .btn-outline:hover { background: rgba(255,255,255,0.08); border-color: rgba(255,255,255,0.2); }
    input, select, textarea { width: 100%; padding: 10px 13px; background: #0f172a; border: 1px solid var(--border); border-radius: 8px; color: var(--text); font-size: 13px; margin-top: 6px; margin-bottom: 14px; transition: border-color 0.2s; }
    input:focus, select:focus, textarea:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px rgba(59,130,246,0.25); }
    table { width: 100%; border-collapse: separate; border-spacing: 0; margin-top: 12px; font-size: 13px; border-radius: 8px; overflow: hidden; border: 1px solid var(--border); }
    th, td { text-align: left; padding: 11px 14px; border-bottom: 1px solid var(--border); }
    th { color: var(--text-muted); font-weight: 600; background: #0c1322; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
    tbody tr:hover { background: rgba(255,255,255,0.02); }
    tbody tr:last-child td { border-bottom: none; }
    .log-box { background: #050811; border: 1px solid var(--border); border-radius: 8px; padding: 14px; font-family: monospace; font-size: 12px; max-height: 240px; overflow-y: auto; color: #38bdf8; white-space: pre-wrap; margin-top: 12px; line-height: 1.6; }
    .status-pill { display: inline-block; padding: 3px 8px; border-radius: 6px; font-size: 11px; font-weight: 700; text-transform: uppercase; }
    .status-pill.open { background: rgba(16, 185, 129, 0.2); color: #34d399; }
    .status-pill.closed { background: rgba(239, 68, 68, 0.2); color: #f87171; }
    .category-tag { background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); padding: 3px 7px; border-radius: 4px; font-size: 11px; font-weight: 600; }
    .shift-tag { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); padding: 3px 7px; border-radius: 4px; font-size: 11px; font-weight: 600; }
    .progress-bar-container { width: 100%; background: #1e293b; border-radius: 9999px; height: 10px; overflow: hidden; margin-top: 10px; margin-bottom: 10px; }
    .progress-bar { height: 100%; background: linear-gradient(90deg, var(--primary), var(--accent)); width: 0%; transition: width 0.3s; }
    /* ---------- 📱 MOBILE / TABLET RESPONSIVE (operate from phone) ---------- */
    @media (max-width: 920px) {
      body { padding: 12px; }
      .header { flex-direction: column; align-items: stretch; gap: 10px; padding-bottom: 12px; margin-bottom: 14px; }
      .header h1 { font-size: 18px; }
      .grid-stats { grid-template-columns: repeat(2, 1fr); gap: 8px; margin-bottom: 14px; }
      .stat-card { padding: 10px 12px; }
      .stat-card .val { font-size: 20px; }
      .stat-card .desc { display: none; }
      .tabs { gap: 4px; padding-bottom: 6px; -webkit-overflow-scrolling: touch; scrollbar-width: thin; }
      .tab-btn { font-size: 12px; padding: 8px 10px; }
      .panel-card { padding: 12px !important; }
      table { display: block; overflow-x: auto; white-space: nowrap; font-size: 11px; }
      #wa-login-number-badge { font-size: 16px !important; padding: 5px 12px !important; }
      .btn { min-height: 38px; }
      input, select, textarea { font-size: 16px !important; } /* stops mobile auto-zoom */
      .hist-grid { grid-template-columns: 1fr !important; }
    }
    @media (max-width: 520px) {
      .grid-stats { grid-template-columns: repeat(2, 1fr); }
      .header h1 { font-size: 16px; }
    }
  </style>
</head>
<body>
  <div class="header">
    <div>
      <h1>🚀 StudentUp Control Hub</h1>
      <p style="color:var(--text-muted); font-size:12px; margin-top:4px;">WhatsApp + Telegram Bulk Delivery · Anti-Ban Engine</p>
    </div>
    <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
      <span class="badge-shield">🛡️ ANTI-BAN INTERLEAVED</span>
      <span class="badge-live">● ENGINE LIVE</span>
      <button class="btn btn-outline" onclick="location.reload()">🔄 Refresh</button>
      <button class="btn btn-outline" style="border-color:#f59e0b; color:#f59e0b;" onclick="changeDashPassword()" title="Change admin password">🔑 Password</button>
      <button class="btn btn-outline" style="border-color:#34d399; color:#34d399;" onclick="toggleIpLockPanel()" title="Allow only specific IP addresses">🛡️ IP Lock</button>
      <button class="btn btn-outline" style="border-color:#ef4444; color:#ef4444;" onclick="dashLogout()" title="Lock the dashboard">🔒 Lock / Logout</button>
    </div>
  </div>

  <!-- 🛡️ IP ALLOWLIST PANEL (2nd security layer on top of password) -->
  <div id="ip-lock-panel" style="display:none; background:#0f172a; border:1px solid #34d399; border-radius:12px; padding:18px; margin-bottom:18px;">
    <h3 style="font-size:15px; margin-bottom:6px;">🛡️ IP Allowlist — కొన్ని IP ల నుంచే dashboard open అవ్వాలి</h3>
    <p style="color:var(--text-muted); font-size:12px; margin-bottom:10px;">
      Password తో పాటు రెండో security layer. Lock ON అయితే, list లో ఉన్న IP ల నుంచి మాత్రమే login page కూడా కనిపిస్తుంది — మిగతా వాళ్ళకి 403 Access Denied.
    </p>
    <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-bottom:10px;">
      <span id="ip-lock-status" style="font-weight:800; font-size:13px;">...</span>
      <span style="font-size:12px; color:#94a3b8;">Your current IP: <b id="ip-lock-myip" style="color:#fbbf24;">...</b></span>
      <button class="btn btn-outline" style="font-size:11px; padding:4px 10px;" onclick="addMyIpToList()">➕ Add My Current IP</button>
    </div>
    <label>Allowed IPs (one per line — formats: <code>49.37.12.34</code> exact · <code>49.37.</code> prefix/range · <code>49.37.0.0/16</code> CIDR):</label>
    <textarea id="ip-allow-list" rows="4" style="width:100%; font-family:monospace; font-size:13px;" placeholder="49.37.12.34"></textarea>
    <div style="display:flex; gap:10px; margin-top:10px; flex-wrap:wrap;">
      <button class="btn btn-accent" onclick="saveIpLock(true)">🛡️ Save & Turn ON</button>
      <button class="btn btn-outline" style="border-color:#ef4444; color:#ef4444;" onclick="saveIpLock(false)">🔓 Turn OFF (password only)</button>
    </div>
    <div id="ip-lock-result" style="font-size:12px; margin-top:8px;"></div>
    <div id="login-audit" style="font-size:11px; margin-top:10px;"></div>
    <p style="color:#64748b; font-size:11px; margin-top:8px;">
      💡 Mobile data IP మారుతూ ఉంటుంది — exact IP బదులు prefix (ఉదా: <code>49.37.</code>) వాడితే safe. 🚨 Lockout అయితే: server ని <code>DISABLE_IP_LOCK=1</code> env తో restart చేయండి (sandbox/local నుంచి ఎప్పుడూ access ఉంటుంది).
    </p>
  </div>

  <div class="grid-stats">
    <div class="stat-card">
      <div class="label">Total Syllabus Polls Available</div>
      <div class="val" id="stat-polls-count" style="color:#38bdf8;">...</div>
      <div class="desc">Active question inventory</div>
    </div>
    <div class="stat-card">
      <div class="label">WhatsApp Groups Active</div>
      <div class="val" id="stat-wa-count" style="color:#60a5fa;">...</div>
      <div class="desc">100+ groups safe queue</div>
    </div>
    <div class="stat-card">
      <div class="label">Telegram Channels</div>
      <div class="val" id="stat-tg-count" style="color:var(--purple);">...</div>
      <div class="desc">TS & AP live channels</div>
    </div>
    <div class="stat-card">
      <div class="label">Custom Bundles</div>
      <div class="val" id="stat-bundle-count" style="color:var(--pink);">...</div>
      <div class="desc">Cluster groups & channels</div>
    </div>
    <div class="stat-card">
      <div class="label">Total Points Earned</div>
      <div class="val" id="stat-points" style="color:var(--warning);">...</div>
      <div class="desc">Active student balance</div>
    </div>
  </div>

  <!-- Global WhatsApp Device Connectivity Header -->
  <div style="background: linear-gradient(135deg, rgba(16,185,129,0.12) 0%, rgba(59,130,246,0.15) 100%); border:1px solid #10b981; border-radius:12px; padding:14px 18px; margin-bottom:18px;">
    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px;">
      <div>
        <h3 style="font-size:14px; display:flex; align-items:center; gap:8px;">
          📱 WhatsApp Gateway Node & Anti-Ban Protection
          <span id="wa-session-status-badge" style="background:#10b981; color:#050811; font-size:11px; font-weight:800; padding:2px 8px; border-radius:12px;">● CONNECTED</span>
          <span style="background:rgba(59,130,246,0.2); color:#60a5fa; border:1px solid #3b82f6; border-radius:12px; padding:2px 8px; font-size:11px; font-weight:700;">🛡️ 100x Anti-Ban Active</span>
        </h3>
        <div id="wa-logged-in-card" style="display:flex; align-items:center; gap:14px; flex-wrap:wrap; margin-top:8px; background:#050811; border:1px solid #1e293b; border-radius:10px; padding:10px 14px;">
          <div id="wa-login-number-badge" style="font-family:'Consolas', monospace; font-size:20px; font-weight:800; letter-spacing:1px; color:#64748b; background:#0b1329; border:2px dashed #334155; border-radius:10px; padding:6px 16px;">
            📵 NOT LINKED
          </div>
          <div style="font-size:12px; color:var(--text-muted); line-height:1.7;">
            <div>👤 Device: <b style="color:#f8fafc;" id="wa-device-name">—</b> <span id="wa-connected-since" style="color:#64748b;"></span></div>
            <div>💬 Synced Groups: <b style="color:#38bdf8;" id="wa-dialogs-count">0 Groups</b> · 🛡️ Anti-Ban: <b style="color:#10b981;">40-60s Jitter + 5-Poll Rotation + 60-90s Batch Rest</b></div>
          </div>
          <span id="wa-device-phone" style="display:none;"></span>
        </div>

        <!-- ⏱️ GLOBAL SMART GAP ENGINE: no time restrictions, user-controlled pacing everywhere -->
        <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-top:8px; background:#050811; border:1px solid #1e293b; border-radius:10px; padding:8px 14px;">
          <b style="font-size:12px; color:#f59e0b;">⏱️ Anti-Ban Gap Engine:</b>
          <select id="global-gap-preset" onchange="applyGapPreset(this.value)" style="margin:0; padding:5px 8px; font-size:12px; background:#0b1329; border:1px solid #f59e0b; color:#f8fafc; border-radius:6px;">
            <option value="20,35">⚡ Fast — 20-35s</option>
            <option value="40,60" selected>🛡️ Normal — 40-60s</option>
            <option value="90,150">🐢 Long — 1.5-2.5 min</option>
            <option value="180,300">🧘 Extra Long — 3-5 min</option>
            <option value="300,600">🌙 Marathon — 5-10 min</option>
            <option value="custom">⚙️ Custom</option>
          </select>
          <span style="font-size:11px; color:var(--text-muted);">Gap:</span>
          <input type="number" id="gap-min" value="40" min="3" style="width:64px; margin:0; padding:5px 6px; font-size:12px; text-align:center;" oninput="saveGapSettings()">
          <span style="font-size:11px; color:var(--text-muted);">–</span>
          <input type="number" id="gap-max" value="60" min="5" style="width:64px; margin:0; padding:5px 6px; font-size:12px; text-align:center;" oninput="saveGapSettings()">
          <span style="font-size:11px; color:var(--text-muted);">sec/poll</span>
          <span style="font-size:11px; color:#10b981; font-weight:700;">⏰ No time limits — మీ ఇష్టం వచ్చినప్పుడు పంపండి (day/night anytime)</span>
        </div>
      </div>
      <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
        <button class="btn btn-accent" style="font-size:12px; padding:6px 12px;" onclick="syncWADialogs()">🔄 Auto-Sync Joined Groups</button>
        <button class="btn btn-outline" style="font-size:12px; padding:6px 12px;" onclick="showQRLoginModal()">📷 Scan QR Login</button>
        <button class="btn btn-outline" style="font-size:12px; padding:6px 12px;" onclick="showCodeLoginModal()">🔢 Login with Code</button>
        <button class="btn btn-outline" style="font-size:12px; padding:6px 12px; border-color:#ef4444; color:#ef4444;" onclick="logoutWASession()">🚪 Unlink Device</button>
      </div>
    </div>
    <div id="wa-login-dialog" style="display:none; margin-top:14px; background:#050811; padding:14px; border-radius:8px; border:1px solid var(--border);"></div>
  </div>

  <div class="tabs">
    <button class="tab-btn active" onclick="switchTab('tab-bulk-broadcast')">🚀 Bulk Messages & Channels Hub</button>
    <button class="tab-btn" onclick="switchTab('tab-wa-dispatch')">🛡️ WhatsApp 100+ Interleaved Dispatcher</button>
    <button class="tab-btn" onclick="switchTab('tab-bundles')">📦 Custom Saved Bundles</button>
    <button class="tab-btn" onclick="switchTab('tab-excel-import')">📊 Multi-Sheet Excel Importer</button>
    <button class="tab-btn" onclick="switchTab('tab-campus')">🏫 College On-Spot Exams & QR</button>
    <button class="tab-btn" onclick="switchTab('tab-dynamic-channels')">📢 Telegram Channels & Poll Counts</button>
    <button class="tab-btn" onclick="switchTab('tab-control')">⚡ Fast Actions & District War</button>
    <button class="tab-btn" onclick="switchTab('tab-squads')">👥 Squad Wars & Arena</button>
    <button class="tab-btn" onclick="switchTab('tab-members')">📋 Registered Members & CRM</button>
    <button class="tab-btn" onclick="switchTab('tab-history')">📊 History & Analytics</button>
  </div>

  <!-- TAB 1: WHATSAPP INTERLEAVED DISPATCHER -->
  <div id="tab-wa-dispatch" class="tab-pane">
    

    <div class="panel-card">
      <h2>🛡️ Advanced WhatsApp Anti-Ban Dispatcher (5 Polls/Group, 40-60s Jitter, 60-90s Batch Rest)</h2>
      <p style="color:var(--text-muted); font-size:13px; margin-bottom:16px;">
        ఖాతా పూర్తి భద్రత కోసం: ప్రతి గ్రూపులో <b>5 ప్రశ్నలు</b> పూర్తయ్యే వరకు <b>40-60 సెకన్ల</b> రాండమ్ గ్యాప్‌తో పోస్ట్ అవుతాయి. ప్రతి 5 గ్రూపుల తర్వాత <b>60-90 సెకన్ల</b> కూల్‌డౌన్ పాజ్ తీసుకుంటుంది. మొదటి 5 గ్రూపులకు ఇంగ్లీష్ మొదటి లైన్, తర్వాతి 5 గ్రూపులకు తెలుగు మొదటి లైన్ క్రమంలో ఆటోమేటిక్ బైలింగ్వల్ రోటేషన్ ఉంటుంది.
      </p>

      <div style="display:grid; grid-template-columns: 2fr 1fr; gap:20px;">
        <div>
          <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px;">
            <div>
              <label>🎯 Exam Category Filter:</label>
              <select id="wa-target-category">
                <option value="ALL">🌐 ALL Categories & Groups (100+ Mode)</option>
                <optgroup label="🎓 Telangana (TS) Student Communities">
                  <option value="TS_BTECH">💻 TS B.Tech (JNTUH/OU/Placements)</option>
                  <option value="TS_DEGREE">🎓 TS Degree (B.Com/B.Sc/B.A)</option>
                  <option value="TS_DIPLOMA">⚙️ TS Diploma & POLYCET</option>
                  <option value="TS_INTER">📘 TS Intermediate (MPC/BiPC)</option>
                  <option value="TS_10TH">🎒 TS 10th Class Board (SSC)</option>
                  <option value="TSPSC">🏛️ TSPSC State & TS Districts</option>
                </optgroup>
                <optgroup label="🌊 Andhra Pradesh (AP) Student Communities">
                  <option value="AP_BTECH">💻 AP B.Tech (JNTUK/JNTUA/Placements)</option>
                  <option value="AP_DEGREE">🎓 AP Degree (AU/SVU/ANU)</option>
                  <option value="AP_DIPLOMA">⚙️ AP Diploma & POLYCET</option>
                  <option value="AP_INTER">📘 AP Intermediate (BIEAP/EAPCET)</option>
                  <option value="AP_10TH">🎒 AP 10th Class Board (BSEAP)</option>
                  <option value="APPSC">🏛️ APPSC State & AP Districts</option>
                </optgroup>
                <optgroup label="🔧 Technical, Open Distance & Govt Exams">
                  <option value="TET_DSC">👩‍🏫 TS & AP TET / DSC (Teachers, SGT, TRT)</option>
                  <option value="ITI_ALL">🔧 TS & AP ITI (Electrician/Fitter/NCVT)</option>
                  <option value="OPEN_UNIV">🏛️ Open Universities (BRAOU/IGNOU/Distance)</option>
                  <option value="POLICE">👮 Police Exams (SI / Constable)</option>
                  <option value="SSC">🏛️ Central Jobs & SSC (CGL, CHSL, MTS)</option>
                  <option value="RAILWAY">🚆 Railway RRB (NTPC, Group D)</option>
                  <option value="BANKING">🏦 Banking Aspirants (SBI, IBPS)</option>
                </optgroup>
              </select>
            </div>
            <div>
              <label>⏰ Time / Shift Filter:</label>
              <select id="wa-target-shift">
                <option value="ALL">☀️/🌙 All Shifts (Morning + Evening)</option>
                <option value="MORNING">🌅 Morning Shift (07:00 AM - 12:00 PM)</option>
                <option value="EVENING">🌆 Evening Shift (05:00 PM - 10:00 PM)</option>
              </select>
            </div>
          </div>

          <label>Optional: Central Announcement or Message Text (Leave blank to send auto-built exam polls):</label>
          <textarea id="wa-broadcast-msg" rows="3" placeholder="Enter custom update or study notification..."></textarea>

          <label>Optional Photo / Poster URL (Posts image along with text):</label>
          <input type="text" id="wa-attachment-url" placeholder="https://example.com/daily-current-affairs-poster.jpg">

          <div style="display:flex; gap:10px; margin-top:8px; flex-wrap:wrap;">
            <button class="btn btn-accent" onclick="startInterleaved(true)">🚀 Start 5-Poll Anti-Ban Quiz Rounds</button>
            <button class="btn btn-purple" onclick="startInterleaved(false)">📢 Send Custom Announcement</button>
            <button class="btn btn-outline" onclick="scheduleQuizModal()">⏰ Schedule Daily Timed Quiz</button>
            <button class="btn btn-danger" onclick="stopInterleaved()">🛑 Stop Pipeline</button>
          </div>

          <div class="schedule-control-card" style="margin-top:16px; background:#0b1329; border:1px solid #38bdf8; border-radius:10px; padding:16px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; flex-wrap:wrap; gap:8px;">
              <div>
                <h3 style="font-size:14px; color:#38bdf8; display:flex; align-items:center; gap:6px;">
                  ⏰ 24x7 Multi-Slot Daily Autonomous Quiz Scheduler
                  <span style="background:#10b981; color:#050811; font-size:10px; font-weight:800; padding:2px 7px; border-radius:12px;">● ALWAYS-ON DAEMON</span>
                </h3>
                <div style="font-size:12px; color:var(--text-muted); margin-top:2px;">
                  రోజులో మీరు ఎన్ని సార్లైనా (ఉదయం, మధ్యాహ్నం, సాయంత్రం, రాత్రి) క్లాక్‌లో టైమ్ ఎంచుకుని సెట్ చేయవచ్చు. కంప్యూటర్ లేదా బ్రౌజర్ ఆఫ్ చేసినా సర్వరే ఆటోమేటిక్‌గా రన్ చేస్తుంది!
                </div>
              </div>
            </div>

            <!-- Instant Time Picker Bar (HTML5 Native Clock Picker) -->
            <div style="background:#070d1e; padding:14px; border-radius:8px; border:1px solid rgba(56,189,248,0.3); margin-bottom:12px;">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; flex-wrap:wrap; gap:8px;">
                <div style="font-size:13px; font-weight:800; color:#38bdf8;">⏰ Advanced Daily Recurring Quiz Scheduler & Auto-Continuous Engine</div>
                <div style="display:flex; gap:8px; align-items:center;">
                  <label style="font-size:12px; color:#a7f3d0; font-weight:700; cursor:pointer; display:flex; align-items:center; gap:5px;">
                    <input type="checkbox" id="sched-auto-continuous" checked onchange="toggleContinuousMode(this.checked)">
                    <span>⚡ Auto Continuous Mode (Daily non-stop without re-scheduling)</span>
                  </label>
                </div>
              </div>

              <!-- Real-time conflict warning banner inside Scheduler -->
              <div id="sched-conflict-alert" style="display:none; background:#7f1d1d; border:1px solid #ef4444; color:#fecaca; padding:8px 12px; border-radius:6px; font-size:12px; margin-bottom:10px;">
                ⚠️ <b>Conflict Alert:</b> <span id="sched-conflict-msg"></span>
              </div>

              <div style="display:flex; gap:10px; align-items:flex-end; flex-wrap:wrap;">
                <div style="flex:1; min-width:130px;">
                  <label style="font-size:11px; color:#38bdf8; font-weight:700; margin:0 0 4px 0; display:block;">🕒 Primary Time:</label>
                  <input type="time" id="clock-slot-time" value="09:00" style="margin:0; padding:7px 10px; font-size:14px; font-weight:800; color:#38bdf8; background:#0b1329; border:1px solid #38bdf8;" onchange="checkSchedulerConflictLive()">
                </div>
                <div style="flex:2; min-width:170px;">
                  <label style="font-size:11px; color:#a7f3d0; font-weight:700; margin:0 0 4px 0; display:block;">🕒 Extra Daily Times (Multiple times per day):</label>
                  <input type="text" id="clock-extra-times" placeholder="e.g. 13:00, 18:30, 21:00" style="margin:0; padding:7px 10px; font-size:12px;" onchange="checkSchedulerConflictLive()">
                </div>
                <div style="flex:2; min-width:170px;">
                  <label style="font-size:11px; color:var(--text-muted); margin:0 0 4px 0; display:block;">📝 Slot Label / Purpose:</label>
                  <input type="text" id="clock-slot-label" placeholder="e.g. Daily Grand Practice Drill" style="margin:0; padding:7px 10px; font-size:12px;">
                </div>
                <div style="flex:1; min-width:140px;">
                  <label style="font-size:11px; color:var(--text-muted); margin:0 0 4px 0; display:block;">🎯 Target Exam:</label>
                  <select id="clock-slot-cat" style="margin:0; padding:7px 10px; font-size:12px;">
                    <option value="ALL">🌐 ALL Groups</option>
                    <option value="POLICE">👮 Police SI/Constable</option>
                    <option value="TSPSC">🏛️ TSPSC State</option>
                    <option value="APPSC">🏛️ APPSC State</option>
                    <option value="SSC">🏛️ SSC & Central</option>
                    <option value="TET_DSC">👩‍🏫 TET / DSC</option>
                    <option value="TS_BTECH">💻 TS B.Tech</option>
                    <option value="AP_BTECH">💻 AP B.Tech</option>
                    <option value="CURRENT">🗞️ Current Affairs</option>
                  </select>
                </div>
                <div id="sched-duration-container" style="flex:1; min-width:130px; display:none;">
                  <label style="font-size:11px; color:#f59e0b; margin:0 0 4px 0; display:block;">📅 Duration (Days):</label>
                  <input type="number" id="sched-days-duration" value="7" min="1" max="365" style="margin:0; padding:7px 10px; font-size:12px;">
                </div>
                <div style="display:flex; align-items:flex-end;">
                  <button class="btn btn-accent" style="padding:8px 16px; font-size:12px; white-space:nowrap;" onclick="addClockSlot()">➕ Add Daily Slot(s)</button>
                </div>
              </div>
            </div>

            <!-- Active Scheduled Jobs List -->
            <div id="wa-schedules-container" style="background:#050811; padding:12px; border-radius:8px; border:1px solid rgba(255,255,255,0.08);">
              <div id="wa-schedules-list" style="font-size:12px;"></div>
            </div>
          </div>

          <div style="margin-top:14px;">
            <div style="display:flex; justify-content:space-between; font-size:12px; color:var(--text-muted);">
              <span id="pipeline-status-text">Status: Idle</span>
              <span id="pipeline-progress-text">0 / 0 Groups</span>
            </div>
            <div class="progress-bar-container">
              <div id="pipeline-progress-bar" class="progress-bar"></div>
            </div>
          </div>
        </div>

        <div style="background:#0f172a; border:1px solid var(--border); border-radius:10px; padding:16px;">
          <h3 style="font-size:14px; margin-bottom:12px; color:#38bdf8;">⚙️ Interleaved Anti-Ban Setup</h3>
          <div style="font-size:12px; line-height:1.7; color:var(--text-muted);">
            ✔ <b>2-by-2 Group Rotation:</b> Rotates across groups while students contemplate answers.<br>
            ✔ <b>Random 20–30s Human Delays:</b> Zero robotic pattern.<br>
            ✔ <b>Two-Phase Delivery:</b> Question first, Answer Key after delay.<br>
            ✔ <b>Invisible Hash Markers:</b> Dynamic zero-width characters in each post.<br>
            ✔ <b>Exam Segregation:</b> Police questions never leak to Banking/SSC groups.<br>
          </div>
          <div style="margin-top:14px;">
            <label style="font-size:12px;">WhatsApp Webhook / Gateway Endpoint (Optional):</label>
            <input type="text" id="wa-gateway-input" placeholder="http://localhost:3000/send or GreenAPI/UltraMsg">
          </div>
        </div>
      </div>

      <div style="margin-top:24px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <div>
            <h3 style="margin-bottom:4px;">📋 Managed WhatsApp Groups Directory</h3>
            <span style="font-size:12px; color:var(--text-muted);">Select specific groups or search by keyword to dispatch quizzes instantly</span>
          </div>
          <div style="display:flex; gap:8px; align-items:center;">
            <input type="text" id="wa-search-box" placeholder="🔍 Search groups..." onkeyup="filterWAGroups()" style="width:170px; margin:0; padding:6px 10px; font-size:12px;">
            <button class="btn btn-purple" style="font-size:12px; padding:6px 12px;" onclick="dispatchSelectedGroups()">⚡ Run Quiz on Selected</button>
            <button class="btn btn-outline" style="font-size:12px; padding:6px 12px;" onclick="selectAllGroups(true)">Select All</button>
            <button class="btn btn-outline" style="font-size:12px; padding:6px 12px;" onclick="selectAllGroups(false)">Clear</button>
            <button class="btn btn-outline" style="font-size:12px; padding:6px 12px;" onclick="loadWAGroups()">🔄 Refresh</button>
          </div>
        </div>
        <table id="table-wa-groups">
          <thead>
            <tr>
              <th style="width:30px;"><input type="checkbox" id="wa-select-all" onchange="selectAllGroups(this.checked)"></th>
              <th>ID</th>
              <th>Group Title</th>
              <th>Assigned Exam Category</th>
              <th>Group Type</th>
              <th>Shift</th>
              <th>JID / Link</th>
              <th>Status</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>

        <div style="display:flex; gap:10px; margin-top:16px; background:#0f172a; padding:12px; border-radius:8px; flex-wrap:wrap; align-items:center;">
          <input type="text" id="new-wa-title" placeholder="Group Title (e.g. Warangal TS Police SI Batch)" style="flex:2; min-width:200px; margin:0;">
          <input type="text" id="new-wa-jid" placeholder="Group JID or Invite link" style="flex:2; min-width:200px; margin:0;">
          <select id="new-wa-category" style="width:160px; margin:0;">
            <option value="AUTO">🤖 Auto Category</option>
            <option value="GENERAL">🌐 General Group</option>
            <option value="TET_DSC">👩‍🏫 TS & AP TET / DSC</option>
            <option value="AP_BTECH">AP B.Tech</option>
            <option value="AP_DEGREE">AP Degree</option>
            <option value="AP_DIPLOMA">AP Diploma</option>
            <option value="AP_INTER">AP Intermediate</option>
            <option value="AP_10TH">AP 10th Class</option>
            <option value="TS_BTECH">TS B.Tech</option>
            <option value="TS_DEGREE">TS Degree</option>
            <option value="TS_DIPLOMA">TS Diploma</option>
            <option value="TS_INTER">TS Intermediate</option>
            <option value="TS_10TH">TS 10th Class</option>
            <option value="ITI_ALL">TS & AP ITI</option>
            <option value="OPEN_UNIV">Open Universities</option>
            <option value="POLICE">POLICE</option>
            <option value="SSC">SSC / Central</option>
            <option value="RAILWAY">RAILWAY</option>
            <option value="BANKING">BANKING</option>
            <option value="TSPSC">TSPSC / TS Districts</option>
            <option value="APPSC">APPSC / AP Districts</option>
          </select>
          <select id="new-wa-grouptype" style="width:160px; margin:0;">
            <option value="EXAM_SPECIFIC">🎯 Specific Exam Group</option>
            <option value="GENERAL">🌐 General Group</option>
          </select>
          <select id="new-wa-shift" style="width:130px; margin:0;">
            <option value="ALL_DAY">All-Day</option>
            <option value="MORNING">Morning Shift</option>
            <option value="EVENING">Evening Shift</option>
          </select>
          <button class="btn btn-accent" style="white-space:nowrap;" onclick="addNewWAGroup()">➕ Connect Group</button>
        </div>

        <!-- In-Tab Direct Excel / CSV File Uploader & Quick Paste Card -->
        <div style="margin-top:16px; background:#070d1e; border:1px solid #38bdf8; border-radius:10px; padding:16px;">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:10px;">
            <div>
              <h4 style="color:#38bdf8; font-size:14px; display:flex; align-items:center; gap:6px;">
                📊 Excel & CSV File Direct Uploader / Bulk Paste (50+ to 150+ Groups)
              </h4>
              <p style="font-size:12px; color:var(--text-muted); margin-top:2px;">
                మీ దగ్గర ఉన్న <b>.xlsx, .xls, లేదా .csv</b> ఫైల్‌ను నేరుగా బ్రౌజ్ చేసి అప్‌లోడ్ చేయండి, లేదా క్రింద ఉన్న బాక్స్‌లో నేరుగా కాపీ-పేస్ట్ చేయండి!
              </p>
            </div>
            <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
              <a href="/api/excel/template" download="studentup_sample_whatsapp_groups.csv" class="btn btn-outline" style="font-size:12px; padding:6px 14px; text-decoration:none; color:#38bdf8; border-color:#38bdf8;">📥 Download Sample Excel Template</a>
              <input type="file" id="wa-excel-file-input" accept=".csv, .xlsx, .xls, .txt, .tsv" style="display:none;" onchange="handleExcelFileUpload(event)">
              <button class="btn btn-accent" style="font-size:12px; padding:6px 14px;" onclick="document.getElementById('wa-excel-file-input').click()">📁 Choose Excel / CSV File</button>
              <button class="btn btn-purple" style="font-size:12px; padding:6px 14px;" onclick="importInTabExcel()">📥 Import Pasted Rows</button>
            </div>
          </div>
          <textarea id="wa-direct-excel-paste" rows="4" placeholder="Or directly paste rows from Excel / Google Sheets here (Columns: Group Name | Link or JID | Category | Shift | Group Type)..." style="margin-bottom:8px; font-size:12px;"></textarea>
          <div id="wa-excel-status-log" style="font-size:11px; color:#10b981; font-weight:600;"></div>
        </div>
      </div>

      <div id="wa-log-box" class="log-box" style="margin-top:16px;">WhatsApp Interleaved Dispatcher ready.</div>
    </div>
  </div>

  <!-- TAB 2: COLLEGE ON-SPOT EXAMS & QR -->
  <div id="tab-campus" class="tab-pane">
    <div class="panel-card">
      <h2>🏫 College On-Spot Exam Launcher & Dynamic QR Generator</h2>
      <p style="color:var(--text-muted); font-size:13px; margin-bottom:14px;">
        ఏ కాలేజీకి వెళ్లినా సరే, అక్కడికక్కడే 1 నిమిషంలో కాలేజ్ పేరుతో ప్రత్యేక ఆన్-స్పాట్ టెస్ట్ లాంచ్ చేయవచ్చు! విద్యార్థులు స్కాన్ చేసి నేరుగా పేరు, మొబైల్ ఇచ్చి టెస్ట్ రాస్తారు. టెస్ట్ ముగియగానే పూర్తి మార్కుల రిపోర్ట్ ప్రిన్సిపాల్ / HOD కోసం రెడీ అవుతుంది.
      </p>

      <div style="display:grid; grid-template-columns: 1fr 1fr; gap:20px;">
        <div style="background:#0f172a; padding:18px; border-radius:10px; border:1px solid var(--border);">
          <h3 style="font-size:15px; margin-bottom:12px; color:#38bdf8;">➕ Launch New College Exam Event</h3>
          <label>College Name (e.g. SR Engineering College or Kakatiya Univ):</label>
          <input type="text" id="campus-college-name" placeholder="Enter College Name">

          <label>District:</label>
          <input type="text" id="campus-district" placeholder="e.g. Warangal, Visakhapatnam, Hyderabad, Guntur">

          <div style="display:grid; grid-template-columns: 1fr 1fr; gap:10px;">
            <div>
              <label>Number of Questions:</label>
              <select id="campus-nq">
                <option value="5">5 Questions (Fast 5-Min Test)</option>
                <option value="10" selected>10 Questions (Standard 10-Min Test)</option>
                <option value="15">15 Questions (15-Min Test)</option>
                <option value="20">20 Questions (Grand Challenge)</option>
              </select>
            </div>
            <div>
              <label>Difficulty Level:</label>
              <select id="campus-level">
                <option value="easy">Easy (Engaging GK/Tech/Science)</option>
                <option value="medium">Medium (Competitive Level)</option>
                <option value="hard">Hard (Advanced / GATE)</option>
              </select>
            </div>
          </div>

          <label style="margin-top:6px;">Select Subjects to Include in Exam:</label>
          <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px; font-size:12px; margin-bottom:12px; background:#050811; padding:10px; border-radius:8px; border:1px solid var(--border);">
            <label><input type="checkbox" id="subj-reasoning" checked> 🧩 Reasoning & Logic Puzzles</label>
            <label><input type="checkbox" id="subj-quant" checked> 🔢 Quantitative Aptitude / Maths</label>
            <label><input type="checkbox" id="subj-science" checked> 🔬 General Science & Tech</label>
            <label><input type="checkbox" id="subj-english" checked> 📖 General English & Vocabulary</label>
            <label><input type="checkbox" id="subj-ca" checked> 🗞️ Current Affairs & GK</label>
            <label><input type="checkbox" id="subj-coding"> 💻 Coding & Computer Science</label>
          </div>

          <button class="btn btn-accent" style="margin-top:4px;" onclick="createCampusEvent()">🚀 Generate College Exam Link & QR Code</button>
        </div>

        <div>
          <h3 style="font-size:15px; margin-bottom:12px;">📱 Active College Exam Link & Poster</h3>
          <div id="campus-active-card" style="background:#050811; border:1px solid var(--border); border-radius:8px; padding:14px; font-size:13px; line-height:1.6; min-height:180px;">
            Create or select a college event to view its live student registration link, QR Code and principal scorecard.
          </div>
        </div>
      </div>

      <div style="margin-top:24px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <h3>🏫 Active College Exam Sessions</h3>
          <button class="btn btn-outline" onclick="loadCampusEvents()">🔄 Refresh Sessions</button>
        </div>
        <table id="table-campus">
          <thead>
            <tr>
              <th>Event Code</th>
              <th>College Name</th>
              <th>District</th>
              <th>Questions</th>
              <th>Participants</th>
              <th>Status</th>
              <th>Action & Principal Report</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- TAB 3: EXCEL / SHEET IMPORTER & MANAGER -->
  <div id="tab-excel-import" class="tab-pane">
    <div class="panel-card">
      <h2>📊 Advanced Multi-Sheet Excel & Google Sheets Importer (100+ to 250+ Groups & Channels)</h2>
      <p style="color:var(--text-muted); font-size:13px; margin-bottom:14px;">
        ఒకే Excel వర్క్‌బుక్ లోని వేర్వేరు షీట్లను (Multi-Sheet: ఉదా: <i>Police_SI, TET_DSC, TSPSC_APPSC, BTech_Campus, General_Aptitude</i>) అప్‌లోడ్ చేసి, ఏ షీట్ కావాలో టిక్ చేసుకుని (Selective Multiple Sheets) ఒక్క క్లిక్‌తో డేటాబేస్‌లోకి ఇంపోర్ట్ చేసుకోవచ్చు!
      </p>

      <div style="background:#0f172a; padding:12px; border-radius:8px; margin-bottom:14px; font-size:12px; color:var(--text-muted); border-left:4px solid #38bdf8;">
        💡 <b>Excel Columns (Tab / Comma separated / .xlsx):</b><br>
        <code>Group or Channel Name | Link or JID | Category (Optional) | Shift (Optional) | Group Type (Optional: GENERAL or EXAM_SPECIFIC)</code><br>
        <span style="color:#a7f3d0; font-size:11px;">(Note: 5వ కాలమ్‌లో GENERAL అని రాస్తే జనరల్ గ్రూప్ అని, EXAM_SPECIFIC అని రాస్తే ఆ నిర్దిష్ట పరీక్ష సిలబస్ గ్రూప్ అని సిస్టమ్ రికార్డ్ చేస్తుంది).</span>
      </div>

      <!-- File Browse Upload with Multi-Sheet Inspector -->
      <div style="background:rgba(30,41,59,0.7); border:1px solid #334155; border-radius:10px; padding:16px; margin-bottom:16px;">
        <h4 style="margin-bottom:8px; font-size:14px; color:#38bdf8;">📁 Step 1: Upload Excel File (.xlsx, .xls, .csv, .tsv)</h4>
        <div style="display:flex; gap:12px; align-items:center; flex-wrap:wrap;">
          <input type="file" id="excel-tab-file-input" accept=".csv, .xlsx, .xls, .txt, .tsv" style="display:none;" onchange="handleMainExcelFileUpload(event)">
          <button class="btn btn-accent" onclick="document.getElementById('excel-tab-file-input').click()">📂 Choose Excel / CSV File</button>
          <span id="selected-file-label" style="font-size:13px; color:var(--text-muted);">No file selected yet</span>
          <a href="/api/excel/template" download="studentup_sample_whatsapp_groups.csv" class="btn btn-outline" style="text-decoration:none; color:#38bdf8; border-color:#38bdf8; margin-left:auto;">📥 Download Sample Template</a>
        </div>

        <!-- Multi-Sheet Selection Checkbox Panel (Appears when .xlsx uploaded) -->
        <div id="multisheet-panel" style="display:none; margin-top:16px; padding:14px; background:#0b1120; border:1px solid #3b82f6; border-radius:8px;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
            <b style="color:#60a5fa; font-size:13px;">📑 Detected Multiple Sheets in Workbook (Select sheets to import):</b>
            <div>
              <button class="btn btn-outline" style="padding:3px 8px; font-size:11px;" onclick="selectAllSheets(true)">Select All</button>
              <button class="btn btn-outline" style="padding:3px 8px; font-size:11px;" onclick="selectAllSheets(false)">Deselect All</button>
            </div>
          </div>
          <div id="multisheet-checkboxes" style="display:grid; grid-template-columns:repeat(auto-fill, minmax(200px, 1fr)); gap:10px;"></div>
          <div style="margin-top:12px;">
            <button class="btn btn-accent" onclick="importSelectedExcelSheets()">📥 Import Selected Sheets Only</button>
          </div>
        </div>
      </div>

      <h4 style="margin-bottom:6px; font-size:13px; color:var(--text-muted);">లేదా డైరెక్ట్‌గా Google Sheets / Excel Rows ఇక్కడ పేస్ట్ చేయండి:</h4>
      <textarea id="excel-paste-text" rows="7" placeholder="Paste your Excel / Google Sheet rows here...
Example:
Warangal TS Police SI Batch	120363012345678990@g.us	POLICE	EVENING	EXAM_SPECIFIC
Hyderabad Aspirants Daily Club	120363012345678999@g.us	GENERAL	ALL_DAY	GENERAL
AP B.Tech Guntur Campus	120363012345678991@g.us	AP_BTECH	MORNING	EXAM_SPECIFIC
Telangana SSC Science Channel	@ts_science_ssc	TS_10TH	ALL_DAY	EXAM_SPECIFIC"></textarea>

      <div style="display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin-top:10px;">
        <button class="btn btn-accent" onclick="importExcelSheet()">📥 Import Pasted Rows</button>
        <button class="btn btn-purple" onclick="exportExcelSheet()">📤 Export Current Groups as Excel / TSV</button>
        <button class="btn btn-outline" onclick="document.getElementById('excel-paste-text').value=''">Clear Box</button>
      </div>

      <div id="excel-import-log" class="log-box" style="margin-top:16px;">Importer ready. Upload .xlsx file or paste rows.</div>
    </div>
  </div>

  <!-- TAB: BULK BROADCAST & ATTACHMENTS (GROUPS & CHANNELS) -->
  <div id="tab-bulk-broadcast" class="tab-pane active">
    <div class="panel-card">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:12px;">
        <h2>🚀 Bulk Message & Live Dispatcher (WhatsApp Groups + Telegram Channels)</h2>
        <div style="display:flex; gap:8px; align-items:center;">
          <span style="background:rgba(59,130,246,0.2); color:#60a5fa; border:1px solid #3b82f6; border-radius:20px; padding:3px 12px; font-size:12px; font-weight:700;">Simultaneous Multi-Target Gateway</span>
          <button class="btn btn-purple" style="padding:5px 12px; font-size:12px;" onclick="switchTab('tab-bundles')">📦 Manage & Create Bundles</button>
        </div>
      </div>
      <p style="color:var(--text-muted); font-size:13px; margin-bottom:16px;">
        ఒకేసారి అన్ని WhatsApp గ్రూపులకు మరియు Telegram ఛానెళ్లకు అధికారిక నోటిఫికేషన్లు, మెటీరియల్స్, స్టడీ PDFలు, పోస్టర్లు లేదా ప్రైవేట్ లింక్‌లను బల్క్‌గా డిస్పాచ్ చేయండి!
      </p>

      <!-- Real-time conflict warning banner for Bulk Dispatch -->
      <div id="bulk-conflict-alert" style="display:none; background:#7f1d1d; border:1px solid #ef4444; color:#fecaca; padding:10px 14px; border-radius:8px; font-size:12px; margin-bottom:14px;">
        ⚠️ <b>Schedule / Bundle Conflict Detected:</b> <span id="bulk-conflict-msg"></span>
      </div>

      <!-- Quick Bundle Preset Loader -->
      <div style="background:#0b1329; border:1px solid #38bdf8; border-radius:8px; padding:12px; margin-bottom:16px; display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:10px;">
        <div style="display:flex; align-items:center; gap:8px;">
          <span style="font-size:14px;">⚡</span>
          <b style="color:#38bdf8; font-size:13px;">Quick-Load Custom Bundle:</b>
          <select id="bulk-bundle-selector" style="margin:0; padding:6px 10px; font-size:12px; background:#0f172a; border:1px solid #38bdf8; color:white; border-radius:6px; min-width:240px;" onchange="applySelectedBundle(this.value)">
            <option value="">-- Choose a Saved Group Bundle --</option>
          </select>
        </div>
        <div style="display:flex; gap:8px;">
          <button class="btn btn-outline" style="padding:4px 10px; font-size:11px;" onclick="loadBulkTargets()">🔄 Reload Targets</button>
          <button class="btn btn-purple" style="padding:4px 10px; font-size:11px;" onclick="switchTab('tab-excel-import')">📊 Upload Groups Excel / CSV</button>
        </div>
      </div>

      <!-- ➕ QUICK ADD NEW GROUPS: paste invite links → bot auto-joins & registers -->
      <div style="background:#0b1329; border:1px solid #10b981; border-radius:10px; padding:12px; margin-bottom:16px;">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:8px;">
          <h4 style="font-size:13px; color:#10b981; margin:0;">➕ Quick Add New Groups (Invite Links paste చేస్తే చాలు — bot దే auto-join అవుతుంది!)</h4>
          <span style="font-size:10px; color:var(--text-muted);">Formats: link only · Name | link · Name | link | CATEGORY</span>
        </div>
        <div style="display:flex; gap:8px; flex-wrap:wrap; align-items:flex-start;">
          <textarea id="quick-add-links" rows="2" placeholder="https://chat.whatsapp.com/XXXXXXXX
Warangal Police SI Batch | https://chat.whatsapp.com/YYYYYYYY | POLICE" style="flex:1; min-width:250px; margin:0; font-size:12px;"></textarea>
          <button class="btn btn-accent" style="padding:10px 16px; font-size:13px; font-weight:700; white-space:nowrap;" onclick="quickAddGroups()">➕ Add & Auto-Join</button>
        </div>
        <div id="quick-add-result" style="font-size:12px; margin-top:6px;"></div>
      </div>

      <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(320px, 1fr)); gap:18px; margin-bottom:18px;">
        <!-- Left Column: Message & Attachment Composer -->
        <div style="background:#0f172a; border:1px solid #1e293b; border-radius:10px; padding:16px;">
          <h3 style="font-size:14px; color:#38bdf8; margin-bottom:10px;">✍️ 1. Message & Media Composer</h3>
          
          <label style="font-size:12px; color:var(--text-muted); display:block; margin-bottom:4px;">Broadcasting Message / Caption:</label>
          <textarea id="bulk-broadcast-msg" rows="6" placeholder="Type your broadcast message or alert here...
e.g.
📢 Mega Grand Mock Test Live Now!
హాల్ టికెట్ & పూర్తి సిలబస్ కోసం క్రింది లింక్ ఓపెన్ చేయండి.
All candidates must join today before 9:00 PM!"></textarea>

          <label style="font-size:12px; color:var(--text-muted); display:block; margin-top:10px; margin-bottom:4px;">📎 File Attachment (PDF, Images, Posters):</label>
          <div style="display:flex; gap:8px; align-items:center; margin-bottom:8px;">
            <input type="file" id="bulk-attachment-file" style="display:none;" onchange="handleBulkAttachmentSelect(event)">
            <button class="btn btn-outline" style="padding:6px 12px; font-size:12px;" onclick="document.getElementById('bulk-attachment-file').click()">📁 Choose File</button>
            <span id="bulk-file-name" style="font-size:12px; color:#a7f3d0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:220px;">No file selected</span>
            <button id="bulk-clear-file-btn" class="btn btn-outline" style="display:none; padding:3px 6px; font-size:10px; color:#ef4444;" onclick="clearBulkAttachment()">✕</button>
          </div>

          <label style="font-size:12px; color:var(--text-muted); display:block; margin-top:8px; margin-bottom:4px;">లేదా Direct Attachment / Image / Video URL:</label>
          <input type="text" id="bulk-attachment-url" placeholder="https://example.com/materials/test_schedule.pdf">

          <div style="margin-top:16px; display:flex; flex-direction:column; gap:8px;">
            <button class="btn btn-accent" style="width:100%; padding:12px; font-size:14px; font-weight:800;" onclick="sendBulkBroadcast()">🚀 Send Bulk Message to Selected Targets</button>
          </div>

          <!-- 🎯 TOP-LEVEL EXAM POLL BUILDER: subjects + count + difficulty-free smart pick -->
          <div style="margin-top:14px; background:#0b1329; border:1px solid #8b5cf6; border-radius:10px; padding:12px;">
            <h4 style="font-size:13px; color:#a78bfa; margin-bottom:8px;">🎯 Exam Poll Builder (Subject-Wise)</h4>
            <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-bottom:8px;">
              <span style="font-size:11px; color:var(--text-muted);">Polls/group:</span>
              <select id="poll-count-select" style="margin:0; padding:4px 8px; font-size:12px; width:70px;">
                <option value="3">3</option>
                <option value="5" selected>5</option>
                <option value="10">10</option>
                <option value="15">15</option>
              </select>
              <span style="font-size:11px; color:var(--text-muted);">Subjects (ఏవీ టిక్ చేయకపోతే = All):</span>
            </div>
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:4px; font-size:12px; margin-bottom:10px;">
              <label style="cursor:pointer;"><input type="checkbox" class="poll-subj" value="MATHS"> 🔢 Maths / Aptitude</label>
              <label style="cursor:pointer;"><input type="checkbox" class="poll-subj" value="REASONING"> 🧩 Reasoning</label>
              <label style="cursor:pointer;"><input type="checkbox" class="poll-subj" value="GK"> 📚 GK / History / Polity</label>
              <label style="cursor:pointer;"><input type="checkbox" class="poll-subj" value="CURRENT"> 🗞️ Current Affairs</label>
              <label style="cursor:pointer;"><input type="checkbox" class="poll-subj" value="ENGLISH"> 📖 English</label>
              <label style="cursor:pointer;"><input type="checkbox" class="poll-subj" value="SCIENCE"> 🔬 Science & Tech</label>
            </div>
            <button class="btn btn-purple" style="width:100%; padding:10px; font-size:13px; font-weight:700;" onclick="sendBulkQuizPollsToTargets()">🎯 Send Exam Polls to Selected Targets</button>
            <div style="font-size:10px; color:var(--text-muted); margin-top:6px;">💬 WhatsApp: anti-ban gap engine · 📢 Telegram: instant (official Bot API — no ban risk, no gaps)</div>
          </div>
        </div>

        <!-- Right Column: Select Targets (Channels + Groups) with search filters -->
        <div style="background:#0f172a; border:1px solid #1e293b; border-radius:10px; padding:16px; max-height:520px; display:flex; flex-direction:column;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; flex-wrap:wrap; gap:6px;">
            <h3 style="font-size:14px; color:#a7f3d0; margin:0;">🎯 2. Select Delivery Targets</h3>
            <span id="bulk-selected-count-badge" style="font-size:11px; font-weight:700; color:#38bdf8;">0 selected</span>
          </div>

          <!-- Target Filter Search Box -->
          <div style="display:flex; gap:6px; margin-bottom:8px;">
            <input type="text" id="bulk-target-search" placeholder="🔍 Search groups & channels..." style="margin:0; padding:5px 8px; font-size:12px;" onkeyup="filterBulkTargetList()">
            <select id="bulk-cat-filter" style="margin:0; padding:5px 8px; font-size:11px; width:130px;" onchange="filterBulkTargetList()">
              <option value="ALL">All Categories</option>
              <option value="POLICE">POLICE</option>
              <option value="TSPSC">TSPSC</option>
              <option value="APPSC">APPSC</option>
              <option value="SSC">SSC</option>
              <option value="TET_DSC">TET / DSC</option>
              <option value="TS_BTECH">TS B.Tech</option>
              <option value="AP_BTECH">AP B.Tech</option>
              <option value="GENERAL">GENERAL</option>
            </select>
          </div>
          
          <div style="display:flex; gap:6px; margin-bottom:10px; flex-wrap:wrap;">
            <button class="btn btn-outline" style="padding:3px 7px; font-size:11px;" onclick="toggleAllBulkTargets(true)">Select All</button>
            <button class="btn btn-outline" style="padding:3px 7px; font-size:11px;" onclick="toggleAllBulkTargets(false)">Clear All</button>
            <button class="btn btn-outline" style="padding:3px 7px; font-size:11px;" onclick="selectBulkChannelsOnly()">Channels Only</button>
            <button class="btn btn-outline" style="padding:3px 7px; font-size:11px;" onclick="selectBulkWAGroupsOnly()">WhatsApp Only</button>
            <button class="btn btn-outline" style="padding:3px 7px; font-size:11px; border-color:#10b981; color:#10b981;" onclick="selectVisibleBulkTargets(true)">✅ Select Visible</button>
            <button class="btn btn-outline" style="padding:3px 7px; font-size:11px; border-color:#f59e0b; color:#f59e0b;" onclick="selectVisibleBulkTargets(false)">✖ Unselect Visible</button>
          </div>

          <div style="overflow-y:auto; flex:1; padding-right:6px;">
            <div style="font-size:12px; font-weight:700; color:#38bdf8; margin-bottom:6px; border-bottom:1px solid #1e293b; padding-bottom:4px;">
              📢 Telegram Channels (<span id="bulk-channels-count">0</span>):
            </div>
            <div id="bulk-channels-list" style="margin-bottom:14px; display:flex; flex-direction:column; gap:4px;"></div>

            <div style="font-size:12px; font-weight:700; color:#10b981; margin-bottom:6px; border-bottom:1px solid #1e293b; padding-bottom:4px;">
              💬 WhatsApp Groups (<span id="bulk-groups-count">0</span>):
            </div>
            <div id="bulk-groups-list" style="display:flex; flex-direction:column; gap:4px;"></div>
          </div>
        </div>
      </div>

      <div id="bulk-broadcast-log" class="log-box">Ready. Compose your message, choose targets, and hit Send!</div>
    </div>
  </div>

  <div id="tab-bundles" class="tab-pane">
    <div class="panel-card">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:12px;">
        <h2>📦 Channel & WhatsApp Group Bundles (Custom Saved Clusters)</h2>
        <button class="btn btn-outline" style="padding:6px 12px; font-size:12px;" onclick="switchTab('tab-bulk-broadcast')">🚀 Open Bulk Dispatcher</button>
      </div>
      <p style="color:var(--text-muted); font-size:13px; margin-bottom:14px;">
        మీకు నచ్చిన WhatsApp గ్రూపులను మరియు Telegram ఛానెళ్లను కలిపి ఒకే <b>Custom Bundle (కట్ట)</b> గా పేరు పెట్టి సేవ్ చేసుకోండి. భవిష్యత్తులో ఆ పేరును ఎంచుకోగానే అందరూ ఆటోమేటిక్‌గా సెలెక్ట్ అవుతారు!
      </p>

      <div style="display:grid; grid-template-columns: 1fr 1fr; gap:20px;">
        <!-- Left: Active Bundles List -->
        <div>
          <h3 style="font-size:15px; margin-bottom:10px;">📋 Saved Bundles</h3>
          <table id="table-bundles">
            <thead>
              <tr>
                <th>Bundle Name</th>
                <th>Category</th>
                <th>Target Groups & Channels</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>

        <!-- Right: Interactive Bundle Creator with Searchable Checkbox List -->
        <div style="background:#0f172a; padding:16px; border-radius:10px; border:1px solid var(--border); display:flex; flex-direction:column;">
          <h3 style="font-size:15px; margin-bottom:10px; color:#ec4899;">➕ Create / Edit Custom Bundle</h3>
          
          <label style="font-size:12px; color:var(--text-muted);">Bundle Name / Title:</label>
          <input type="text" id="bundle-name" placeholder="e.g. Warangal All Degree & B.Tech Cluster" style="margin-bottom:8px;">

          <div style="display:flex; gap:10px; margin-bottom:8px;">
            <div style="flex:1;">
              <label style="font-size:12px; color:var(--text-muted);">Default Exam Syllabus:</label>
              <select id="bundle-category" style="margin:0;">
                <option value="GENERAL">🌐 General Exam Prep</option>
                <option value="POLICE">👮 Police (SI/Constable)</option>
                <option value="TSPSC">🏛️ TSPSC State</option>
                <option value="APPSC">🏛️ APPSC State</option>
                <option value="SSC">🏛️ Central / SSC</option>
                <option value="RAILWAY">🚆 Railway RRB</option>
                <option value="BANKING">🏦 Banking</option>
                <option value="TET_DSC">👩‍🏫 TET / DSC</option>
                <option value="TS_BTECH">TS B.Tech</option>
                <option value="AP_BTECH">AP B.Tech</option>
                <option value="TS_DEGREE">TS Degree</option>
                <option value="AP_DEGREE">AP Degree</option>
                <option value="TS_INTER">TS Intermediate</option>
                <option value="AP_INTER">AP Intermediate</option>
                <option value="TS_10TH">TS 10th Class</option>
                <option value="AP_10TH">AP 10th Class</option>
                <option value="ITI_ALL">TS & AP ITI</option>
                <option value="OPEN_UNIV">Open Universities</option>
              </select>
            </div>
          </div>

          <label style="font-size:12px; color:#38bdf8; font-weight:700; margin-top:6px; margin-bottom:4px;">
            Select WhatsApp Groups & Channels for this Bundle:
          </label>
          
          <div style="display:flex; gap:6px; margin-bottom:6px;">
            <input type="text" id="bundle-member-search" placeholder="🔍 Filter groups to add..." style="margin:0; padding:4px 8px; font-size:11px;" onkeyup="filterBundleCreatorList()">
            <button class="btn btn-outline" style="padding:3px 6px; font-size:10px;" onclick="toggleBundleCreatorItems(true)">Check All</button>
            <button class="btn btn-outline" style="padding:3px 6px; font-size:10px;" onclick="toggleBundleCreatorItems(false)">Uncheck</button>
          </div>

          <div id="bundle-creator-members" style="height:220px; overflow-y:auto; background:#070d1e; border:1px solid #1e293b; border-radius:6px; padding:8px; margin-bottom:12px; display:flex; flex-direction:column; gap:4px;">
            <div style="color:var(--text-muted); font-size:11px; text-align:center; padding:10px;">Loading groups and channels...</div>
          </div>

          <button class="btn btn-pink" style="padding:10px; font-weight:800;" onclick="saveNewBundle()">💾 Save Custom Bundle</button>
        </div>
      </div>
    </div>
  </div>

  <!-- TAB 4: TELEGRAM CHANNELS & POLL COUNTS -->
  <div id="tab-dynamic-channels" class="tab-pane">
    <div class="panel-card">
      <h2>📢 Telegram Channels & Real-Time Question Counts</h2>
      <p style="color:var(--text-muted); font-size:13px; margin-bottom:16px;">
        ప్రతి ఛానల్‌లో ఎన్ని ప్రశ్నలు సిద్ధంగా ఉన్నాయో లైవ్‌గా చూడండి. కొత్త ఛానల్ యాడ్ చేసినప్పుడు AI ఆటోమేటిక్‌గా సిలబస్ అర్థం చేసుకుని క్వశ్చన్స్ బిల్డ్ చేస్తుంది.
      </p>

      <div style="display:grid; grid-template-columns: 1fr 1fr; gap:20px;">
        <div style="background:#0f172a; padding:18px; border-radius:10px; border:1px solid var(--border);">
          <h3 style="font-size:15px; margin-bottom:12px;">➕ Register Telegram Channel <u>or Group</u></h3>

          <!-- 🔍 one-click: bot ని add చేసిన groups/channels auto-register -->
          <div style="background:#0b1329; border:1px solid #10b981; border-radius:8px; padding:10px; margin-bottom:12px;">
            <div style="font-size:12px; color:#a7f3d0; margin-bottom:6px;">💡 <b>Easy way:</b> మీ Telegram <b>group</b> లో bot ని add చేయండి (member/admin గా) → ఈ button నొక్కండి — అన్నీ ఆటోమేటిక్‌గా register అవుతాయి!</div>
            <button class="btn btn-accent" style="font-size:12px; padding:6px 14px;" onclick="detectNewTelegramChats()">🔍 Auto-Detect Bot Groups & Channels</button>
            <div id="tg-detect-result" style="font-size:12px; margin-top:6px;"></div>
          </div>

          <label>Type:</label>
          <select id="new-ch-type">
            <option value="channel">📢 Channel (broadcast)</option>
            <option value="group">💬 Group / Supergroup (bot must be member)</option>
          </select>

          <label>Channel / Group / Exam Name:</label>
          <input type="text" id="new-ch-name" placeholder="e.g. TS Police Sub Inspector 2026">

          <label>Exam Category (or Auto-Detect):</label>
          <select id="new-ch-base">
            <option value="AUTO">🤖 Auto-Detect (AP B.Tech, AP Degree, TS, ITI, Police, etc.)</option>
            <option value="TET_DSC">👩‍🏫 TS & AP TET / DSC (Teachers, SGT, School Assistant)</option>
            <option value="AP_BTECH">AP B.Tech (JNTUK, JNTUA, Engineering & Placements)</option>
            <option value="AP_DEGREE">AP Degree (AU, SVU, ANU B.Com, B.Sc, B.A)</option>
            <option value="AP_DIPLOMA">AP Diploma & POLYCET / ECET (SBTET)</option>
            <option value="AP_INTER">AP Intermediate (BIEAP MPC/BiPC & EAPCET)</option>
            <option value="AP_10TH">AP 10th Class Board (BSEAP SSC)</option>
            <option value="TS_BTECH">TS B.Tech (Engineering / Coding / CRT Placements)</option>
            <option value="TS_DEGREE">TS Degree (B.Com, B.Sc, B.A, ICET)</option>
            <option value="TS_DIPLOMA">TS Diploma & POLYCET / ECET</option>
            <option value="TS_INTER">TS Intermediate (MPC/BiPC/CEC)</option>
            <option value="TS_10TH">TS 10th Class Board (SSC)</option>
            <option value="ITI_ALL">TS & AP ITI (Electrician / Fitter / NCVT / Apprentice)</option>
            <option value="OPEN_UNIV">Open Universities (BRAOU / IGNOU / Distance Education)</option>
            <option value="POLICE">Police Exams (SI / Constable / APSP / TSSP)</option>
            <option value="SSC">SSC Exams (CGL / CHSL / MTS / GD)</option>
            <option value="RAILWAY">Railway RRB (NTPC / Group D / ALP)</option>
            <option value="BANKING">Banking (IBPS PO / SBI Clerk / RRB)</option>
            <option value="TSPSC">TSPSC / TS Districts</option>
            <option value="APPSC">APPSC / AP Districts</option>
            <option value="DEFENCE">Defence (NDA, CDS, AFCAT)</option>
            <option value="CURRENT">Current Affairs & Daily GK</option>
          </select>

          <label>Telegram Chat ID or @username (groups కి usually -100... id):</label>
          <input type="text" id="new-ch-chatid" placeholder="@MyChannel or -100123456789 (group id)">

          <button class="btn btn-accent" onclick="createNewChannel()">⚡ Register & Auto-Synthesize Polls</button>
        </div>

        <div>
          <h3 style="font-size:15px; margin-bottom:12px;">📢 Instant Telegram Poll Broadcaster</h3>
          <label>Choose Channel to Post Poll:</label>
          <select id="post-poll-channel"></select>

          <div style="display:flex; gap:10px; margin-top:8px;">
            <button class="btn btn-accent" onclick="sendChannelPoll(1)">📢 Post 1 Exam-Specific Poll</button>
            <button class="btn btn-outline" onclick="sendChannelPoll(5)">📢 Post 5 Round Polls</button>
          </div>
          <div id="tg-poll-log" class="log-box" style="margin-top:14px;">Select channel and dispatch.</div>
        </div>
      </div>

      <div style="margin-top:24px;">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:12px;">
          <div>
            <h3 style="margin-bottom:4px;">Active Channels & Real-Time Question Counts</h3>
            <span style="font-size:12px; color:var(--text-muted);">Select specific channels or search by exam to dispatch customized quiz rounds instantly</span>
          </div>
          <div style="display:flex; gap:8px; align-items:center;">
            <input type="text" id="ch-search-box" placeholder="🔍 Search channels..." onkeyup="filterTGChannels()" style="width:170px; margin:0; padding:6px 10px; font-size:12px;">
            <button class="btn btn-accent" style="font-size:12px; padding:6px 12px;" onclick="dispatchSelectedChannels()">🚀 Post Quiz to Selected</button>
            <button class="btn btn-outline" style="font-size:12px; padding:6px 12px;" onclick="selectAllChannels(true)">Select All</button>
            <button class="btn btn-outline" style="font-size:12px; padding:6px 12px;" onclick="selectAllChannels(false)">Clear</button>
            <button class="btn btn-outline" style="font-size:12px; padding:6px 12px;" onclick="loadChannels()">🔄 Refresh</button>
          </div>
        </div>
        <table id="table-channels">
          <thead>
            <tr>
              <th style="width:30px;"><input type="checkbox" id="ch-select-all" onchange="selectAllChannels(this.checked)"></th>
              <th>Channel Key</th>
              <th>Channel Title</th>
              <th>Syllabus Category</th>
              <th>Available Polls Count</th>
              <th>Chat Target</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>

      <!-- 🤖 TELEGRAM AUTO-PILOT: daily hands-free poll posting -->
      <div style="background:#0b1329; border:1px solid #a78bfa; border-radius:10px; padding:16px; margin-top:16px;">
        <h3 style="font-size:15px; margin-bottom:4px;">🤖 Telegram Auto-Pilot — రోజూ ఆటోమేటిక్ Polls (Zero Effort)</h3>
        <p style="color:var(--text-muted); font-size:12px; margin-bottom:10px;">
          పై table లో channels/groups select చేసి, times పెట్టి ON చేయండి — ప్రతి రోజు ఆ time కి ఆటోమేటిక్‌గా polls post అవుతాయి (instant, no gaps — official Bot API).
        </p>
        <div style="display:flex; gap:10px; flex-wrap:wrap; align-items:flex-end;">
          <div>
            <label style="font-size:11px;">Daily Times (comma sep):</label>
            <input type="text" id="tg-ap-times" placeholder="08:00, 13:00, 20:30" style="width:180px; margin:0; padding:7px 10px; font-size:13px;">
          </div>
          <div>
            <label style="font-size:11px;">Polls per slot:</label>
            <select id="tg-ap-count" style="margin:0; padding:7px 10px; width:90px;">
              <option value="1">1</option><option value="3">3</option><option value="5" selected>5</option><option value="10">10</option>
            </select>
          </div>
          <button class="btn btn-accent" onclick="createTgAutopilot()">🤖 Start Auto-Pilot (Selected Targets)</button>
          <button class="btn btn-outline" style="border-color:#fbbf24; color:#fbbf24;" onclick="oneClickDailyPlan()" title="08:00 + 13:00 + 20:30 slots, all targets">🚀 1-Click Daily Plan</button>
        </div>
        <div style="margin-top:8px; font-size:12px; color:#94a3b8;">
          Subjects (optional):
          <label style="display:inline; font-size:12px;"><input type="checkbox" class="tg-ap-subj" value="MATHS"> ➗ Maths</label>
          <label style="display:inline; font-size:12px;"><input type="checkbox" class="tg-ap-subj" value="REASONING"> 🧠 Reasoning</label>
          <label style="display:inline; font-size:12px;"><input type="checkbox" class="tg-ap-subj" value="GK"> 🌍 GK</label>
          <label style="display:inline; font-size:12px;"><input type="checkbox" class="tg-ap-subj" value="CURRENT"> 📰 Current</label>
          <label style="display:inline; font-size:12px;"><input type="checkbox" class="tg-ap-subj" value="ENGLISH"> 🔤 English</label>
          <label style="display:inline; font-size:12px;"><input type="checkbox" class="tg-ap-subj" value="SCIENCE"> 🔬 Science</label>
        </div>
        <div id="tg-ap-result" style="font-size:12px; margin-top:8px;"></div>
        <div id="tg-ap-jobs" style="font-size:12px; margin-top:10px;"></div>
      </div>

      <!-- 🔍 QUESTION FINDER: search whole bank, preview, hand-pick & send -->
      <div style="background:#0b1329; border:1px solid #38bdf8; border-radius:10px; padding:16px; margin-top:16px;">
        <h3 style="font-size:15px; margin-bottom:4px;">🔍 Question Finder — ఏ Question అయినా వెతికి, నచ్చింది పంపండి</h3>
        <p style="color:var(--text-muted); font-size:12px; margin-bottom:10px;">
          Topic, పదం, లేదా channel పేరుతో search చేయండి (ఉదా: "blood relation", "percentage", "constitution"). నచ్చిన question పక్కన 📤 నొక్కితే — పైన select చేసిన channel కి instant గా వెళ్తుంది.
        </p>
        <div style="display:flex; gap:10px; flex-wrap:wrap; align-items:center;">
          <input type="text" id="qf-search" placeholder="🔍 e.g. blood relation, GDP, article 21..." style="flex:1; min-width:220px; margin:0; padding:8px 12px; font-size:13px;" onkeyup="qfDebounced()">
          <span style="font-size:11px; color:#94a3b8;">Send target: <b style="color:#38bdf8;">పైన "Choose Channel" select</b></span>
        </div>
        <div id="qf-results" style="margin-top:10px; max-height:300px; overflow-y:auto; font-size:12px;"></div>
      </div>
    </div>
  </div>

  <!-- TAB 5: FAST ACTIONS & DISTRICT WAR -->
  <div id="tab-control" class="tab-pane">
    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:20px;">
      <div class="panel-card">
        <h2>⚔️ District War Instant Controller</h2>
        <p style="color:var(--text-muted); font-size:13px; margin-bottom:14px;">
          Lobby status, countdown and manual launch trigger for all TS & AP districts.
        </p>
        <div style="display:flex; gap:10px; margin-bottom:16px;">
          <button class="btn btn-accent" onclick="triggerWar('now', 5)">⚔️ Launch War Now (5 min Lobby)</button>
          <button class="btn btn-outline" onclick="triggerWar('status')">🔍 Check Status</button>
        </div>
        <div id="war-result" class="log-box">War controller ready.</div>
      </div>

      <div class="panel-card">
        <h2>📊 Google Sheet Sync & CRM</h2>
        <p style="color:var(--text-muted); font-size:13px; margin-bottom:14px;">
          Push all registered members, colleges, test results and daily analytics directly to Google Sheet.
        </p>
        <div style="display:flex; gap:10px; margin-bottom:16px;">
          <button class="btn" onclick="syncSheet('sync')">📤 Push All Members to Sheet</button>
          <button class="btn btn-outline" onclick="syncSheet('flush')">📦 Flush Queue</button>
        </div>
        <div id="sheet-result" class="log-box">Google Sheet CRM ready.</div>
      </div>
    </div>
  </div>

  <!-- TAB 6: SQUADS & ARENA -->
  <div id="tab-squads" class="tab-pane">
    <div class="panel-card">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:14px;">
        <div>
          <h2>👥 Registered Squads, War Battle Room & Instant Join QR</h2>
          <p style="color:var(--text-muted); font-size:13px; margin-top:2px;">
            Generate new Squads with dynamic Telegram one-tap Join Links & scannable QR Codes directly from the Dashboard.
          </p>
        </div>
        <button class="btn btn-outline" onclick="loadSquads()">🔄 Refresh Squads</button>
      </div>

      <!-- Quick Create & Quick Join Bar -->
      <div style="display:grid; grid-template-columns: 1.5fr 1fr; gap:16px; margin-bottom:18px;">
        <div style="background:#0f172a; border:1px solid var(--border); border-radius:10px; padding:16px;">
          <h3 style="font-size:14px; margin-bottom:10px; color:#38bdf8;">➕ Quick Create New Squad</h3>
          <div style="display:flex; gap:10px; flex-wrap:wrap;">
            <input type="text" id="new-squad-name" placeholder="Squad Name (e.g. Warangal Tigers or JNTUK CSE Warriors)" style="flex:2; min-width:180px; margin:0;">
            <input type="text" id="new-squad-leader" placeholder="Leader Name / Telegram ID (e.g. Charan or 999123)" style="flex:1.2; min-width:150px; margin:0;">
            <button class="btn btn-accent" style="white-space:nowrap;" onclick="createDashboardSquad()">🚀 Create Squad & Generate QR</button>
          </div>
        </div>

        <div style="background:#0f172a; border:1px solid var(--border); border-radius:10px; padding:16px;">
          <h3 style="font-size:14px; margin-bottom:10px; color:#10b981;">🤝 Quick Add Student to Squad</h3>
          <div style="display:flex; gap:8px;">
            <input type="text" id="join-squad-code" placeholder="Squad Code (e.g. DJLC)" style="width:120px; margin:0; text-transform:uppercase;">
            <input type="text" id="join-squad-uid" placeholder="Student Mobile / TG ID" style="flex:1; margin:0;">
            <button class="btn btn-accent" style="white-space:nowrap;" onclick="addStudentToSquad()">➕ Join Member</button>
          </div>
          <div id="join-squad-log" style="font-size:11px; margin-top:6px; font-weight:600;"></div>
        </div>
      </div>

      <!-- Active Squads Table with Interactive Modal / QR Popup -->
      <table id="table-squads">
        <thead>
          <tr>
            <th>Squad Code</th>
            <th>Squad Name</th>
            <th>Leader</th>
            <th>Members Count</th>
            <th>Active Members</th>
            <th>One-Tap Join Link & Interactive Scannable QR</th>
          </tr>
        </thead>
        <tbody></tbody>
      </table>

      <!-- Dynamic Squad Modal Card -->
      <div id="squad-active-modal" style="display:none; margin-top:16px; background:#070d1e; border:1px solid #38bdf8; border-radius:10px; padding:18px;"></div>
    </div>
  </div>

  <!-- TAB 7: MEMBERS DIRECTORY -->
  <div id="tab-members" class="tab-pane">
    <div class="panel-card">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:14px;">
        <div>
          <h2>📋 Registered Student Members & Instant Registration</h2>
          <p style="color:var(--text-muted); font-size:13px; margin-top:2px;">All registered aspirants with accurate points, streaks, district and exam target.</p>
        </div>
        <div style="display:flex; gap:8px;">
          <button class="btn btn-outline" onclick="loadMembers()">🔄 Refresh Directory</button>
        </div>
      </div>

      <!-- Quick Add / Register Student Form -->
      <div style="background:#0f172a; border:1px solid var(--border); border-radius:10px; padding:14px; margin-bottom:16px;">
        <h3 style="font-size:14px; margin-bottom:10px; color:#38bdf8;">➕ Quick Register New Student & Award Initial Points</h3>
        <div style="display:flex; gap:10px; flex-wrap:wrap;">
          <input type="text" id="reg-student-uid" placeholder="Telegram ID / Mobile (e.g. 9848012345)" style="flex:1; min-width:160px; margin:0;">
          <input type="text" id="reg-student-name" placeholder="Student Full Name (e.g. Charan Reddy)" style="flex:1.5; min-width:180px; margin:0;">
          <select id="reg-student-dist" style="flex:1; min-width:140px; margin:0;">
            <option value="Warangal">Warangal</option>
            <option value="Hyderabad">Hyderabad</option>
            <option value="Karimnagar">Karimnagar</option>
            <option value="Guntur">Guntur</option>
            <option value="Visakhapatnam">Visakhapatnam</option>
            <option value="Vijayawada">Vijayawada</option>
            <option value="Khammam">Khammam</option>
            <option value="Nalgonda">Nalgonda</option>
            <option value="Tirupati">Tirupati</option>
          </select>
          <select id="reg-student-exam" style="flex:1; min-width:130px; margin:0;">
            <option value="POLICE">POLICE SI/PC</option>
            <option value="TET_DSC">TET / DSC</option>
            <option value="TSPSC">TSPSC Group 1-4</option>
            <option value="APPSC">APPSC Group 1-4</option>
            <option value="SSC">SSC / Railway</option>
            <option value="TS_BTECH">B.Tech / Engineering</option>
          </select>
          <input type="number" id="reg-student-pts" placeholder="Bonus Points (e.g. 50)" value="50" style="width:100px; margin:0;">
          <button class="btn btn-accent" style="white-space:nowrap;" onclick="quickRegisterStudent()">✅ Register Student</button>
        </div>
        <div id="reg-student-log" style="font-size:12px; margin-top:8px; font-weight:600;"></div>
      </div>

      <table id="table-members">
        <thead>
          <tr>
            <th>TG ID</th>
            <th>Name</th>
            <th>District</th>
            <th>Target Exam</th>
            <th>Points</th>
            <th>Streak</th>
            <th>College</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody></tbody>
      </table>
    </div>
  </div>

  <!-- TAB: 📊 BROADCAST HISTORY & ANALYTICS -->
  <div id="tab-history" class="tab-pane">
    <div class="panel-card">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
        <div>
          <h2>📊 Broadcast History & Analytics</h2>
          <p style="color:var(--text-muted); font-size:13px;">ప్రతి poll dispatch (Telegram instant / WhatsApp anti-ban / Auto-Pilot) ఇక్కడ record అవుతుంది.</p>
        </div>
        <div style="display:flex; gap:8px; flex-wrap:wrap;">
          <button class="btn btn-outline" style="font-size:12px; padding:6px 12px;" onclick="downloadBackup()">💾 Full Backup (.zip)</button>
          <button class="btn btn-outline" style="font-size:12px; padding:6px 12px;" onclick="exportHistoryCSV()">📥 Export CSV</button>
          <button class="btn btn-outline" style="font-size:12px; padding:6px 12px;" onclick="loadHistory()">🔄 Refresh</button>
        </div>
      </div>

      <!-- 🩺 MISSION CONTROL: whole system health at a glance -->
      <div style="background:#0b1329; border:1px solid #38bdf8; border-radius:10px; padding:14px; margin-top:14px;">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
          <h3 style="font-size:14px;">🩺 Mission Control — System Health</h3>
          <span id="health-uptime" style="font-size:11px; color:#64748b;"></span>
        </div>
        <div id="health-badges" style="display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; font-size:12px;"></div>
        <div id="health-bank" style="margin-top:10px; font-size:12px;"></div>
      </div>

      <div class="grid-stats" style="margin-top:14px;">
        <div class="stat-card">
          <div class="label">Today's Polls Sent</div>
          <div class="val" id="hist-today" style="color:#38bdf8;">...</div>
          <div class="desc"><span id="hist-today-ev">...</span> dispatch events</div>
        </div>
        <div class="stat-card">
          <div class="label">Last 7 Days Polls</div>
          <div class="val" id="hist-week" style="color:#34d399;">...</div>
          <div class="desc"><span id="hist-week-ev">...</span> dispatch events</div>
        </div>
        <div class="stat-card">
          <div class="label">📢 Telegram vs 💚 WhatsApp (7d)</div>
          <div class="val" id="hist-split" style="color:#a78bfa; font-size:20px;">...</div>
          <div class="desc">polls by platform</div>
        </div>
        <div class="stat-card">
          <div class="label">🏆 Top Target (7d)</div>
          <div class="val" id="hist-top" style="color:#fbbf24; font-size:16px;">...</div>
          <div class="desc">most polls received</div>
        </div>
      </div>

      <div style="display:grid; grid-template-columns: 2fr 1fr; gap:16px; margin-top:16px;" class="hist-grid">
        <div style="background:#0f172a; border:1px solid var(--border); border-radius:10px; padding:14px;">
          <h3 style="font-size:14px; margin-bottom:8px;">🕒 Recent Dispatches</h3>
          <div id="hist-table-wrap" style="max-height:420px; overflow-y:auto;">
            <table id="table-history">
              <thead><tr><th>Time</th><th>Platform</th><th>Target</th><th>Polls</th><th>Subjects</th><th>Mode</th></tr></thead>
              <tbody></tbody>
            </table>
          </div>
        </div>
        <div style="background:#0f172a; border:1px solid var(--border); border-radius:10px; padding:14px;">
          <h3 style="font-size:14px; margin-bottom:8px;">🏆 Top Targets (7 days)</h3>
          <div id="hist-top-list" style="font-size:12px;"></div>
        </div>
      </div>
    </div>
  </div>

  <script>
    function switchTab(id, btnElem) {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

      if (btnElem) {
        btnElem.classList.add('active');
      } else {
        const matchingBtn = Array.from(document.querySelectorAll('.tab-btn')).find(b => {
          const onclickAttr = b.getAttribute('onclick') || '';
          return onclickAttr.includes("'" + id + "'") || onclickAttr.includes('"' + id + '"');
        });
        if (matchingBtn) matchingBtn.classList.add('active');
      }

      const targetPane = document.getElementById(id);
      if (targetPane) targetPane.classList.add('active');

      if (id === 'tab-wa-dispatch') loadWAGroups();
      if (id === 'tab-campus') loadCampusEvents();
      if (id === 'tab-dynamic-channels') { loadChannels(); loadTgAutopilotJobs(); }
      if (id === 'tab-history') { loadHistory(); loadHealth(); }
      if (id === 'tab-bundles') loadBundles();
      if (id === 'tab-bulk-broadcast') loadBulkTargets();
      if (id === 'tab-squads') loadSquads();
      if (id === 'tab-members') loadMembers();
    }

    async function fetchStats() {
      try {
        const res = await fetch('/api/stats');
        const data = await res.json();
        document.getElementById('stat-polls-count').innerText = (data.total_questions || '0') + ' Polls';
        document.getElementById('stat-wa-count').innerText = data.wa_groups_count || '0';
        document.getElementById('stat-tg-count').innerText = data.channels_count || '0';
        document.getElementById('stat-bundle-count').innerText = data.bundles_count || '0';
        document.getElementById('stat-points').innerText = data.total_points.toLocaleString();
      } catch (e) {
        console.error(e);
      }
    }

    async function pollPipelineStatus() {
      try {
        const res = await fetch('/api/whatsapp/pipeline_status');
        const d = await res.json();
        const statText = document.getElementById('pipeline-status-text');
        const progText = document.getElementById('pipeline-progress-text');
        const bar = document.getElementById('pipeline-progress-bar');
        const logBox = document.getElementById('wa-log-box');

        if (d.running) {
          statText.innerHTML = '🟢 <b>RUNNING:</b> ' + (d.current_group ? ('Posting in ' + d.current_group) : 'Rotating pairs...');
          const pct = d.total > 0 ? Math.round((d.progress / d.total) * 100) : 0;
          bar.style.width = pct + '%';
          progText.innerText = d.progress + ' / ' + d.total + ' Groups (' + pct + '%)';
        } else {
          statText.innerText = 'Status: Idle';
        }
        if (d.logs && d.logs.length > 0) {
          logBox.innerText = d.logs.join('\\n');
          logBox.scrollTop = logBox.scrollHeight;
        }
      } catch (e) {
        console.error(e);
      }
    }

    async function loadWASession() {
      try {
        const res = await fetch('/api/whatsapp/session');
        const s = await res.json();
        const badge = document.getElementById('wa-session-status-badge');
        const desc = document.getElementById('wa-session-desc');
        const nameEl = document.getElementById('wa-device-name');
        const phoneEl = document.getElementById('wa-device-phone');
        const countEl = document.getElementById('wa-dialogs-count');

        if (nameEl) nameEl.innerText = s.device_name || 'Dispatch Node #1';
        if (phoneEl) phoneEl.innerText = s.phone || '';
        if (countEl) countEl.innerText = (s.scanned_dialogs_count || s.bridge_groups_count || 0) + ' Groups';

        // 🪪 Big neat "which number is logged in" badge
        const numBadge = document.getElementById('wa-login-number-badge');
        const sinceEl = document.getElementById('wa-connected-since');
        if (numBadge) {
          if (s.status === 'connected' && s.phone) {
            numBadge.innerText = '✅ ' + s.phone;
            numBadge.style.color = '#10b981';
            numBadge.style.border = '2px solid #10b981';
            numBadge.style.background = 'rgba(16,185,129,0.08)';
            numBadge.title = 'This WhatsApp number is linked & sending';
            if (sinceEl) sinceEl.innerText = s.connected_at ? ('· 🔗 Linked since ' + s.connected_at) : '';
          } else if (s.status === 'qr_ready' || s.status === 'code_ready' || s.status === 'connecting') {
            numBadge.innerText = '⏳ LINKING...';
            numBadge.style.color = '#f59e0b';
            numBadge.style.border = '2px dashed #f59e0b';
            numBadge.style.background = 'rgba(245,158,11,0.08)';
            if (sinceEl) sinceEl.innerText = '';
          } else {
            numBadge.innerText = '📵 NOT LINKED';
            numBadge.style.color = '#64748b';
            numBadge.style.border = '2px dashed #334155';
            numBadge.style.background = '#0b1329';
            if (sinceEl) sinceEl.innerText = '';
          }
        }

        if (badge) {
          if (s.status === 'connected') {
            badge.style.background = '#10b981';
            badge.style.color = '#050811';
            badge.innerText = '● REAL WHATSAPP CONNECTED';
          } else if (s.status === 'qr_ready') {
            badge.style.background = '#f59e0b';
            badge.style.color = '#050811';
            badge.innerText = '📷 QR CODE READY — SCAN NOW';
          } else if (s.status === 'code_ready') {
            badge.style.background = '#38bdf8';
            badge.style.color = '#050811';
            badge.innerText = '🔢 PAIRING CODE: ' + s.pairing_code;
          } else if (s.status === 'connecting') {
            badge.style.background = '#6366f1';
            badge.style.color = '#fff';
            badge.innerText = '⏳ CONNECTING TO WHATSAPP...';
          } else if (s.status === 'bridge_offline') {
            badge.style.background = '#ef4444';
            badge.style.color = '#fff';
            badge.innerText = '⚠️ BRIDGE OFFLINE (run: node gateway/wa_bridge.js)';
          } else {
            badge.style.background = '#ef4444';
            badge.style.color = '#fff';
            badge.innerText = '○ NOT LINKED — SCAN QR TO LOGIN';
          }
        }
      } catch (e) {
        console.error(e);
      }
    }

    async function syncWADialogs() {
      const box = document.getElementById('wa-login-dialog');
      box.style.display = 'block';
      box.innerHTML = '<div style="color:#38bdf8;">🔄 Scanning active WhatsApp account for all joined groups & channels...</div>';
      try {
        const res = await fetch('/api/whatsapp/sync_dialogs', {method: 'POST'});
        const d = await res.json();
        if (d.ok === false) {
          box.innerHTML = `<div style="color:#ef4444; font-weight:700;">❌ ${d.error || 'Sync failed — connect WhatsApp first (Scan QR Login).'}</div>`;
          return;
        }
        box.innerHTML = `<div style="color:#10b981; font-weight:700;">✅ Synced ${d.dialogs_count || 0} REAL joined groups from your WhatsApp! (${d.added || 0} new, ${d.updated || 0} updated)</div>`;
        loadWASession();
        loadWAGroups();
        fetchStats();
        await loadBulkTargets();
        setTimeout(() => { box.style.display = 'none'; }, 5000);
      } catch (e) {
        box.innerHTML = '<div style="color:#ef4444;">❌ Failed to sync: ' + e + '</div>';
      }
    }

    let waLoginPoller = null;

    function stopWALoginPoller() {
      if (waLoginPoller) { clearInterval(waLoginPoller); waLoginPoller = null; }
    }

    function closeWALoginDialog() {
      stopWALoginPoller();
      const box = document.getElementById('wa-login-dialog');
      if (box) box.style.display = 'none';
    }

    // Poll the REAL session status every 2.5s until the phone actually links.
    function startWALoginPoller(mode) {
      stopWALoginPoller();
      waLoginPoller = setInterval(async () => {
        try {
          const res = await fetch('/api/whatsapp/session');
          const s = await res.json();
          loadWASession();
          const box = document.getElementById('wa-login-dialog');
          if (!box) return;
          if (s.status === 'connected') {
            stopWALoginPoller();
            box.innerHTML = `<div style="color:#10b981; font-weight:700;">🎉 REAL WhatsApp Linked Successfully! Device: ${s.device_name || ''} ${s.phone || ''}<br><span style="font-size:12px; color:#cbd5e1;">Auto-syncing your joined groups now...</span></div>`;
            loadWAGroups();
            fetchStats();
            try { await fetch('/api/whatsapp/sync_dialogs', {method: 'POST'}); } catch (_) {}
            loadWAGroups();
            setTimeout(() => { box.style.display = 'none'; }, 5000);
          } else if (mode === 'qr' && s.status === 'qr_ready' && s.qr_data) {
            const img = document.getElementById('wa-live-qr-img');
            if (img && img.src !== s.qr_data) img.src = s.qr_data;  // QR auto-refreshes every ~60s
            else if (!img) showQRLoginModal();  // QR arrived after "not ready" screen
          } else if (mode === 'code' && s.status === 'code_ready' && s.pairing_code) {
            const codeEl = document.getElementById('wa-live-pairing-code');
            if (codeEl && codeEl.innerText !== s.pairing_code) codeEl.innerText = s.pairing_code;
          } else if (s.status === 'offline' && s.last_error) {
            stopWALoginPoller();
            box.innerHTML = `<div style="color:#ef4444; font-weight:700;">❌ Could not reach WhatsApp servers from this machine.</div>
              <div style="font-size:12px; color:#cbd5e1; margin-top:6px;">Detail: ${s.last_error}<br>
              Check the server's internet access / firewall (web.whatsapp.com must be reachable), then retry.</div>
              <button class="btn btn-accent" style="font-size:11px; padding:5px 10px; margin-top:8px;" onclick="showQRLoginModal()">🔄 Retry QR Login</button>`;
          }
        } catch (e) { /* keep polling */ }
      }, 2500);
    }

    async function showQRLoginModal() {
      const box = document.getElementById('wa-login-dialog');
      box.style.display = 'block';
      box.innerHTML = '<div style="color:#38bdf8;">🔐 Opening REAL WhatsApp Web session & generating live QR... (takes ~5-10s)</div>';
      try {
        const res = await fetch('/api/whatsapp/request_qr', {method: 'POST'});
        const d = await res.json();
        const s = d.session || d || {};
        if (s.status === 'bridge_offline') {
          box.innerHTML = `<div style="color:#ef4444; font-weight:700;">⚠️ WhatsApp Bridge is not running!</div>
            <div style="font-size:12px; color:#cbd5e1; margin-top:6px;">Start it in a terminal, then try again:<br>
            <code style="color:#facc15;">cd gateway && npm install && node wa_bridge.js</code></div>`;
          return;
        }
        if (s.status === 'connected') {
          box.innerHTML = '<div style="color:#10b981; font-weight:700;">✅ Already connected to a REAL WhatsApp session!</div>';
          loadWASession();
          setTimeout(() => { box.style.display = 'none'; }, 3000);
          return;
        }
        if (!s.qr_data) {
          if (s.status === 'offline' && s.last_error) {
            box.innerHTML = `<div style="color:#ef4444; font-weight:700;">❌ Could not reach WhatsApp servers from this machine.</div>
              <div style="font-size:12px; color:#cbd5e1; margin-top:6px;">Detail: ${s.last_error}<br>
              This server's network must allow <b>web.whatsapp.com</b>. Run the bridge on your own PC / VPS with open internet, then retry.</div>
              <button class="btn btn-accent" style="font-size:11px; padding:5px 10px; margin-top:8px;" onclick="showQRLoginModal()">🔄 Retry QR Login</button>`;
            return;
          }
          box.innerHTML = '<div style="color:#f59e0b;">⏳ QR not ready yet (' + (s.status || 'connecting') + '). Waiting for WhatsApp servers...</div>';
          startWALoginPoller('qr');
          return;
        }
        box.innerHTML = `
          <div style="display:flex; gap:20px; align-items:center; flex-wrap:wrap;">
            <img id="wa-live-qr-img" src="${s.qr_data}" style="width:200px; height:200px; border-radius:8px; border:2px solid #10b981; background:white; padding:4px;">
            <div>
              <h4 style="color:#10b981; margin-bottom:6px;">📱 Scan with WhatsApp — this is a REAL login QR</h4>
              <p style="font-size:12px; color:#cbd5e1; margin-bottom:8px;">1. Open WhatsApp on your phone<br>2. Tap Menu / Settings &gt; <b>Linked Devices</b><br>3. Tap <b>Link a Device</b> and scan this code.<br><span style="color:#f59e0b;">QR auto-refreshes; connection is detected automatically — no button needed.</span></p>
              <div id="wa-qr-wait-status" style="font-size:12px; color:#38bdf8; margin-bottom:8px;">⏳ Waiting for your phone to scan...</div>
              <button class="btn btn-outline" style="font-size:11px; padding:5px 10px;" onclick="closeWALoginDialog()">Close</button>
            </div>
          </div>
        `;
        startWALoginPoller('qr');
        loadWASession();
      } catch (e) {
        box.innerHTML = '<div style="color:#ef4444;">❌ QR Request failed: ' + e + '</div>';
      }
    }

    async function showCodeLoginModal() {
      const phone = prompt('Enter WhatsApp Phone Number with Country Code (e.g. +91 9876543210):');
      if (!phone) return;
      const box = document.getElementById('wa-login-dialog');
      box.style.display = 'block';
      box.innerHTML = '<div style="color:#38bdf8;">Requesting 8-digit Pairing Code from WhatsApp...</div>';
      try {
        const res = await fetch('/api/whatsapp/request_code', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({phone})
        });
        const d = await res.json();
        const s = d.session || d || {};
        if (s.status === 'bridge_offline') {
          box.innerHTML = `<div style="color:#ef4444; font-weight:700;">⚠️ WhatsApp Bridge is not running!</div>
            <div style="font-size:12px; color:#cbd5e1; margin-top:6px;">Start it in a terminal, then try again:<br>
            <code style="color:#facc15;">cd gateway && npm install && node wa_bridge.js</code></div>`;
          return;
        }
        if (!s.pairing_code) {
          box.innerHTML = '<div style="color:#f59e0b;">⏳ Requesting real pairing code from WhatsApp servers... keep this open.</div>';
          startWALoginPoller('code');
          return;
        }
        box.innerHTML = `
          <div style="background:#0b1329; border:1px solid #38bdf8; padding:16px; border-radius:8px;">
            <h4 style="color:#38bdf8; margin-bottom:6px;">🔢 REAL WhatsApp Pairing Code</h4>
            <div id="wa-live-pairing-code" style="font-size:24px; font-weight:800; letter-spacing:4px; color:#facc15; margin:10px 0;">${s.pairing_code}</div>
            <p style="font-size:12px; color:#cbd5e1; margin-bottom:10px;">On your phone: WhatsApp &gt; <b>Linked Devices</b> &gt; <b>Link a Device</b> &gt; <b>Link with phone number instead</b> — then type this code. Connection is detected automatically.</p>
            <button class="btn btn-outline" style="font-size:11px; padding:5px 10px;" onclick="closeWALoginDialog()">Close</button>
          </div>
        `;
        startWALoginPoller('code');
        loadWASession();
      } catch (e) {
        box.innerHTML = '<div style="color:#ef4444;">❌ Pairing code request failed: ' + e + '</div>';
      }
    }

    // ---------- ⏱️ GLOBAL SMART GAP ENGINE (saved in browser, applies everywhere) ----------
    function applyGapPreset(val) {
      if (val === 'custom') return;
      const [mn, mx] = val.split(',').map(Number);
      document.getElementById('gap-min').value = mn;
      document.getElementById('gap-max').value = mx;
      saveGapSettings();
    }

    function getGapMin() {
      const v = parseInt(document.getElementById('gap-min')?.value || '40', 10);
      return isNaN(v) || v < 3 ? 3 : v;
    }

    function getGapMax() {
      const mn = getGapMin();
      const v = parseInt(document.getElementById('gap-max')?.value || '60', 10);
      return isNaN(v) || v <= mn ? mn + 5 : v;
    }

    function gapLabel() {
      const mn = getGapMin(), mx = getGapMax();
      const fmt = s => s >= 60 ? (s / 60).toFixed(s % 60 ? 1 : 0) + ' min' : s + 's';
      return `${fmt(mn)}–${fmt(mx)}`;
    }

    function saveGapSettings() {
      try {
        localStorage.setItem('su_gap', JSON.stringify({
          min: getGapMin(), max: getGapMax(),
          preset: document.getElementById('global-gap-preset')?.value || '40,60'
        }));
      } catch (e) {}
    }

    function loadGapSettings() {
      try {
        const s = JSON.parse(localStorage.getItem('su_gap') || 'null');
        if (!s) return;
        const presetEl = document.getElementById('global-gap-preset');
        if (presetEl && s.preset) presetEl.value = s.preset;
        if (s.min) document.getElementById('gap-min').value = s.min;
        if (s.max) document.getElementById('gap-max').value = s.max;
      } catch (e) {}
    }

    async function dashLogout() {
      if (!confirm('Lock the dashboard? మళ్ళీ open చేయాలంటే password అడుగుతుంది.')) return;
      try { await fetch('/api/auth/logout', {method:'POST'}); } catch (e) {}
      location.href = '/';
    }

    // ================= 📊 BROADCAST HISTORY & ANALYTICS =================
    async function loadHistory() {
      try {
        const r = await fetch('/api/history');
        const d = await r.json();
        const s = d.summary || {};
        document.getElementById('hist-today').innerText = s.today_polls ?? 0;
        document.getElementById('hist-today-ev').innerText = s.today_events ?? 0;
        document.getElementById('hist-week').innerText = s.week_polls ?? 0;
        document.getElementById('hist-week-ev').innerText = s.week_events ?? 0;
        const bk = s.by_kind || {};
        document.getElementById('hist-split').innerText = (bk.telegram || 0) + ' / ' + (bk.whatsapp || 0);
        const tops = s.top_targets || [];
        document.getElementById('hist-top').innerText = tops.length ? tops[0].target : '—';
        document.getElementById('hist-top-list').innerHTML = tops.length
          ? tops.map((t, i) => `<div style="display:flex; justify-content:space-between; padding:5px 6px; border-radius:6px; background:${i===0?'rgba(251,191,36,0.08)':'transparent'};"><span>${i+1}. ${t.target}</span><b style="color:#38bdf8;">${t.count}</b></div>`).join('')
          : '<span style="color:#64748b;">No dispatches yet — ఏదైనా poll పంపండి!</span>';
        const tbody = document.querySelector('#table-history tbody');
        tbody.innerHTML = '';
        (d.history || []).forEach(e => {
          const tr = document.createElement('tr');
          const kindBadge = e.kind === 'telegram' ? '📢 Telegram' : (e.kind === 'whatsapp' ? '💚 WhatsApp' : '🤖 ' + e.kind);
          tr.innerHTML = `
            <td style="font-family:monospace; font-size:11px;">${e.ts}</td>
            <td>${kindBadge}</td>
            <td>${e.target}</td>
            <td style="color:#38bdf8; font-weight:700;">${e.count}</td>
            <td style="font-size:11px;">${(e.subjects||[]).join(', ') || 'ALL'}</td>
            <td style="font-size:11px;">${e.dry ? '<span style="color:#f59e0b;">DRY-RUN</span>' : '<span style="color:#34d399;">LIVE</span>'}${e.note ? ' · ' + e.note : ''}</td>
          `;
          tbody.appendChild(tr);
        });
        if (!(d.history || []).length) {
          tbody.innerHTML = '<tr><td colspan="6" style="color:#64748b;">ఇంకా dispatches లేవు.</td></tr>';
        }
      } catch (e) { console.error('history load:', e); }
    }

    // ================= 🩺 MISSION CONTROL (SYSTEM HEALTH) =================
    async function loadHealth() {
      try {
        const r = await fetch('/api/health');
        const d = await r.json();
        document.getElementById('health-uptime').innerText = 'server uptime: ' + d.uptime_min + ' min';
        const b = (ok, onTxt, offTxt, offColor) =>
          `<span style="padding:4px 10px; border-radius:14px; font-weight:800; background:${ok ? 'rgba(52,211,153,0.12)' : 'rgba(245,158,11,0.10)'}; color:${ok ? '#34d399' : (offColor || '#f59e0b')}; border:1px solid ${ok ? '#34d399' : (offColor || '#f59e0b')};">${ok ? onTxt : offTxt}</span>`;
        document.getElementById('health-badges').innerHTML =
          b(d.telegram_live, '📢 Telegram: LIVE', '📢 Telegram: DRY-RUN (BOT_TOKEN set చేయండి)') +
          b(d.whatsapp_connected, '💚 WhatsApp: CONNECTED', '💚 WhatsApp: NOT LINKED (QR scan)') +
          b(d.scheduler_running, '⏰ Scheduler: RUNNING', '⏰ Scheduler: OFF', '#f87171') +
          b(d.autopilot_slots > 0, '🤖 Auto-Pilot: ' + d.autopilot_slots + ' slot(s) ON', '🤖 Auto-Pilot: no slots') +
          b(d.ip_lock_on, '🛡️ IP Lock: ON', '🛡️ IP Lock: OFF (password only)') +
          b(true, '📊 7-Day Polls: ' + d.week_polls, '') +
          b(!!(d.last_backup && d.last_backup.exists), '🗄️ Auto-Backup: ' + ((d.last_backup||{}).file || ''), '🗄️ Auto-Backup: pending (daily)');
        const low = d.low_stock || [];
        let bankHtml = `<b style="color:#38bdf8;">🧮 Question Bank:</b> ${d.total_fresh} fresh / ${d.total_questions} total`;
        if (low.length) {
          bankHtml += ` · <span style="color:#f59e0b;">⚠️ Low stock (${low.length}):</span> ` +
            low.map(r => `${r.channel} (${r.unused})`).join(', ') +
            ` <button class="btn btn-accent" style="font-size:11px; padding:3px 10px; margin-left:6px;" onclick="runBankTopup()">⚡ Auto Top-Up Now</button>`;
        } else {
          bankHtml += ' · <span style="color:#34d399;">✅ అన్ని channels కి fresh stock బాగుంది</span>';
        }
        bankHtml += '<span id="topup-result" style="margin-left:8px;"></span>';
        document.getElementById('health-bank').innerHTML = bankHtml;
      } catch (e) { console.error('health:', e); }
    }

    async function runBankTopup() {
      const el = document.getElementById('topup-result');
      el.innerHTML = '<span style="color:#fbbf24;">⚡ Generating fresh questions...</span>';
      try {
        const r = await fetch('/api/bank/topup', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
        const d = await r.json();
        el.innerHTML = d.ok ? '<span style="color:#34d399;">✅ ' + d.message + '</span>'
                            : '<span style="color:#f87171;">❌ ' + (d.error || 'failed') + '</span>';
        if (d.ok) { fetchStats(); setTimeout(loadHealth, 1200); }
      } catch (e) { el.innerHTML = '<span style="color:#f87171;">❌ ' + e + '</span>'; }
    }

    function downloadBackup() {
      window.location.href = '/api/backup';
    }

    async function exportHistoryCSV() {
      try {
        const r = await fetch('/api/history');
        const d = await r.json();
        const rows = [['Time','Platform','Target','Polls','Subjects','Mode','Note']];
        (d.history || []).forEach(e => rows.push([
          e.ts, e.kind, e.target, e.count, (e.subjects||[]).join('+') || 'ALL', e.dry ? 'DRY-RUN' : 'LIVE', e.note || ''
        ]));
        const csv = rows.map(r2 => r2.map(c => '"' + String(c).replace(/"/g, '""') + '"').join(',')).join('\\n');
        const blob = new Blob(['\\ufeff' + csv], {type: 'text/csv;charset=utf-8'});
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'broadcast_history.csv';
        a.click();
        URL.revokeObjectURL(a.href);
      } catch (e) { alert('Export failed: ' + e); }
    }

    // ================= 🔍 QUESTION FINDER =================
    let _qfTimer = null;
    function qfDebounced() {
      clearTimeout(_qfTimer);
      _qfTimer = setTimeout(searchQuestions, 350);
    }

    async function searchQuestions() {
      const term = document.getElementById('qf-search').value.trim();
      const box = document.getElementById('qf-results');
      if (!term) { box.innerHTML = ''; return; }
      box.innerHTML = '<span style="color:#fbbf24;">Searching...</span>';
      try {
        const r = await fetch('/api/questions/search?q=' + encodeURIComponent(term) + '&limit=30');
        const d = await r.json();
        if (!d.results || !d.results.length) {
          box.innerHTML = '<span style="color:#64748b;">"' + term + '" కి matches లేవు — వేరే పదం try చేయండి.</span>';
          return;
        }
        box.innerHTML = d.results.map(q => `
          <div style="display:flex; align-items:center; gap:8px; padding:7px 9px; border-radius:6px; background:#050811; margin-bottom:5px; flex-wrap:wrap;">
            <span style="flex:1; min-width:200px;">${q.q_en || '(Telugu-only question)'}</span>
            <span class="category-tag" style="font-size:10px;">${q.channel}</span>
            <span style="font-size:10px; color:#94a3b8;">${q.topic}</span>
            <span style="font-size:10px; color:${q.fresh ? '#34d399' : '#f59e0b'};">${q.fresh ? '✨ FRESH' : '♻️ sent before'}</span>
            <button class="btn btn-accent" style="font-size:10px; padding:3px 10px;" onclick="sendPickedQuestion('${q.id}')">📤 Send</button>
          </div>`).join('');
      } catch (e) { box.innerHTML = '<span style="color:#f87171;">❌ ' + e + '</span>'; }
    }

    async function sendPickedQuestion(qid) {
      const ch = document.getElementById('post-poll-channel').value;
      if (!ch) return alert('పైన "Choose Channel to Post Poll" select చేయండి');
      try {
        const r = await fetch('/api/questions/send', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({qid, channel: ch})
        });
        const d = await r.json();
        alert(d.ok ? '✅ ' + d.message : '❌ ' + (d.error || 'failed'));
      } catch (e) { alert('❌ ' + e); }
    }

    // ================= 🤖 TELEGRAM AUTO-PILOT =================
    async function oneClickDailyPlan() {
      // 🚀 zero-thinking setup: select ALL targets + 3 classic daily slots
      let channels = getSelectedChannelKeys();
      if (!channels.length) { selectAllChannels(true); channels = getSelectedChannelKeys(); }
      if (!channels.length) return alert('ముందు కనీసం ఒక channel/group register చేయండి');
      if (!confirm('🚀 Daily Plan: 08:00 + 13:00 + 20:30 కి ' + channels.length + ' target(s) × 5 polls auto-post అవుతాయి. OK?')) return;
      const box = document.getElementById('tg-ap-result');
      box.innerHTML = '<span style="color:#fbbf24;">Creating daily plan...</span>';
      try {
        const r = await fetch('/api/telegram/schedule', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({times: '08:00, 13:00, 20:30', channels, count: 5, subjects: []})
        });
        const d = await r.json();
        box.innerHTML = d.ok ? '<span style="color:#34d399;">✅ ' + d.message + '</span>'
                             : '<span style="color:#f87171;">❌ ' + (d.error || 'Failed') + '</span>';
        if (d.ok) loadTgAutopilotJobs();
      } catch (e) { box.innerHTML = '<span style="color:#f87171;">❌ ' + e + '</span>'; }
    }

    async function createTgAutopilot() {
      const box = document.getElementById('tg-ap-result');
      const times = document.getElementById('tg-ap-times').value.trim();
      const count = document.getElementById('tg-ap-count').value;
      const channels = getSelectedChannelKeys();
      const subjects = Array.from(document.querySelectorAll('.tg-ap-subj:checked')).map(c => c.value);
      if (!times) return alert('Times ఇవ్వండి — ఉదా: 08:00, 20:30');
      if (!channels.length) return alert('పై table లో కనీసం ఒక channel/group select చేయండి (checkbox)');
      box.innerHTML = '<span style="color:#fbbf24;">Creating auto-pilot slots...</span>';
      try {
        const r = await fetch('/api/telegram/schedule', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({times, channels, count: parseInt(count), subjects})
        });
        const d = await r.json();
        box.innerHTML = d.ok ? '<span style="color:#34d399;">✅ ' + d.message + '</span>'
                             : '<span style="color:#f87171;">❌ ' + (d.error || 'Failed') + '</span>';
        if (d.ok) { document.getElementById('tg-ap-times').value = ''; loadTgAutopilotJobs(); }
      } catch (e) { box.innerHTML = '<span style="color:#f87171;">❌ ' + e + '</span>'; }
    }

    async function loadTgAutopilotJobs() {
      const wrap = document.getElementById('tg-ap-jobs');
      if (!wrap) return;
      try {
        const r = await fetch('/api/whatsapp/schedules');
        const d = await r.json();
        const jobs = (d.jobs || d.schedules || []).filter(j => j.mode === 'tg');
        if (!jobs.length) { wrap.innerHTML = '<span style="color:#64748b;">No Telegram auto-pilot slots yet.</span>'; return; }
        wrap.innerHTML = '<div style="font-weight:800; color:#a78bfa; margin-bottom:6px;">🤖 Active Auto-Pilot Slots:</div>' + jobs.map(j => `
          <div style="display:flex; align-items:center; gap:8px; padding:6px 8px; border-radius:6px; background:#050811; margin-bottom:5px; flex-wrap:wrap;">
            <b style="color:#38bdf8;">${j.time}</b>
            <span style="flex:1;">${j.label}</span>
            <span style="font-size:11px; color:${j.enabled ? '#34d399' : '#f59e0b'};">${j.enabled ? '● ON' : '○ PAUSED'}</span>
            <span style="font-size:11px; color:#64748b;">runs: ${j.total_dispatches || 0}${j.last_run ? ' · last: ' + j.last_run : ''}</span>
            <button class="btn btn-outline" style="font-size:10px; padding:2px 8px;" onclick="toggleTgApJob('${j.id}')">${j.enabled ? '⏸ Pause' : '▶ Resume'}</button>
            <button class="btn btn-outline" style="font-size:10px; padding:2px 8px; border-color:#ef4444; color:#ef4444;" onclick="deleteTgApJob('${j.id}')">🗑</button>
          </div>`).join('');
      } catch (e) { wrap.innerHTML = ''; }
    }

    async function toggleTgApJob(id) {
      await fetch('/api/whatsapp/toggle_schedule', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({id: id})});
      loadTgAutopilotJobs();
    }

    async function deleteTgApJob(id) {
      if (!confirm('ఈ Auto-Pilot slot ని delete చేయాలా?')) return;
      await fetch('/api/whatsapp/delete_schedule', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({id: id})});
      loadTgAutopilotJobs();
    }

    function toggleIpLockPanel() {
      const p = document.getElementById('ip-lock-panel');
      const show = p.style.display === 'none';
      p.style.display = show ? 'block' : 'none';
      if (show) loadIpLock();
    }

    async function loadIpLock() {
      try {
        const r = await fetch('/api/security');
        const d = await r.json();
        document.getElementById('ip-lock-myip').innerText = d.your_ip || '?';
        document.getElementById('ip-allow-list').value = (d.allowed_ips || []).join('\\n');
        const st = document.getElementById('ip-lock-status');
        if (d.ip_lock_enabled) {
          st.innerText = '🛡️ IP LOCK: ON';
          st.style.color = '#34d399';
        } else {
          st.innerText = '🔓 IP LOCK: OFF';
          st.style.color = '#f59e0b';
        }
        const la = document.getElementById('login-audit');
        const rec = d.recent_logins || [];
        if (la) {
          la.innerHTML = rec.length
            ? '<b style="color:#94a3b8;">🔐 Recent login attempts:</b> ' +
              rec.map(a => `<span style="margin-left:8px; color:${a.ok ? '#34d399' : '#f87171'};">${a.ok ? '✅' : '❌'} ${a.ip} <span style="color:#64748b;">(${a.ts})</span></span>`).join('')
            : '';
        }
      } catch (e) {
        document.getElementById('ip-lock-result').innerHTML = '<span style="color:#f87171;">❌ ' + e + '</span>';
      }
    }

    function addMyIpToList() {
      const my = document.getElementById('ip-lock-myip').innerText;
      if (!my || my === '?' || my === '...') return alert('Current IP ఇంకా load అవ్వలేదు');
      const ta = document.getElementById('ip-allow-list');
      const lines = ta.value.split('\\n').map(s => s.trim()).filter(Boolean);
      if (lines.indexOf(my) === -1) lines.push(my);
      ta.value = lines.join('\\n');
    }

    async function saveIpLock(enable) {
      const box = document.getElementById('ip-lock-result');
      const lines = document.getElementById('ip-allow-list').value.split('\\n').map(s => s.trim()).filter(Boolean);
      if (enable && lines.length === 0) return alert('కనీసం ఒక IP ఇవ్వండి — లేదా "Add My Current IP" నొక్కండి');
      if (enable && !confirm('🛡️ IP Lock ON చేయాలా? List లో లేని IP ల నుంచి dashboard open అవ్వదు (మీ current IP safety కోసం auto-add అవుతుంది).')) return;
      box.innerHTML = '<span style="color:#fbbf24;">Saving...</span>';
      try {
        const r = await fetch('/api/security/update', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ip_lock_enabled: enable, allowed_ips: lines})
        });
        const d = await r.json();
        if (!d.ok) { box.innerHTML = '<span style="color:#f87171;">❌ ' + (d.error || 'Failed') + '</span>'; return; }
        box.innerHTML = '<span style="color:#34d399;">✅ ' + (d.message || 'Saved') + (d.note ? ' · ⚠️ ' + d.note : '') + '</span>';
        loadIpLock();
      } catch (e) {
        box.innerHTML = '<span style="color:#f87171;">❌ ' + e + '</span>';
      }
    }

    async function changeDashPassword() {
      const oldP = prompt('ప్రస్తుత (current) password:');
      if (oldP === null) return;
      const newP = prompt('కొత్త (new) password (min 6 chars):');
      if (!newP) return;
      try {
        const r = await fetch('/api/auth/change_password', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({old: oldP, new: newP})
        });
        const d = await r.json();
        alert(d.ok ? '✅ Password changed! మిగతా devices అన్నీ logout అయ్యాయి.' : '❌ ' + (d.error || 'Failed'));
      } catch (e) { alert('❌ ' + e); }
    }

    async function logoutWASession() {
      if (!confirm('Unlink this WhatsApp device and wipe the saved session?')) return;
      const box = document.getElementById('wa-login-dialog');
      box.style.display = 'block';
      box.innerHTML = '<div style="color:#f59e0b;">🚪 Unlinking device from WhatsApp...</div>';
      try {
        await fetch('/api/whatsapp/logout', {method: 'POST'});
        box.innerHTML = '<div style="color:#10b981;">✅ Device unlinked. Use Scan QR Login to connect again.</div>';
        loadWASession();
        setTimeout(() => { box.style.display = 'none'; }, 4000);
      } catch (e) {
        box.innerHTML = '<div style="color:#ef4444;">❌ Logout failed: ' + e + '</div>';
      }
    }

    async function confirmWALogin(devName) {
      try {
        await fetch('/api/whatsapp/confirm_login', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({device_name: devName || 'Primary WhatsApp Phone'})
        });
        const box = document.getElementById('wa-login-dialog');
        box.innerHTML = '<div style="color:#10b981; font-weight:700;">🎉 WhatsApp Connected Successfully & Saved to Disk!</div>';
        loadWASession();
        loadWAGroups();
        fetchStats();
        setTimeout(() => { box.style.display = 'none'; }, 2500);
      } catch (e) {
        alert('Failed: ' + e);
      }
    }

    const ALL_EXAM_CATEGORIES = [
      {code: 'GENERAL', label: '🌐 General (Aptitude/GK)'},
      {code: 'POLICE', label: '👮 Police (SI / Constable)'},
      {code: 'TSPSC', label: '🏛️ TSPSC State & Districts'},
      {code: 'APPSC', label: '🏛️ APPSC State & Districts'},
      {code: 'SSC', label: '🏛️ SSC (CGL / CHSL / MTS)'},
      {code: 'RAILWAY', label: '🚆 Railway RRB'},
      {code: 'BANKING', label: '🏦 Banking (IBPS/SBI)'},
      {code: 'TET_DSC', label: '👩‍🏫 TET / DSC'},
      {code: 'TS_BTECH', label: '💻 TS B.Tech (Engineering)'},
      {code: 'AP_BTECH', label: '💻 AP B.Tech (Engineering)'},
      {code: 'TS_DEGREE', label: '🎓 TS Degree'},
      {code: 'AP_DEGREE', label: '🎓 AP Degree'},
      {code: 'TS_DIPLOMA', label: '⚙️ TS Diploma & POLYCET'},
      {code: 'AP_DIPLOMA', label: '⚙️ AP Diploma & POLYCET'},
      {code: 'TS_INTER', label: '📘 TS Intermediate'},
      {code: 'AP_INTER', label: '📘 AP Intermediate'},
      {code: 'TS_10TH', label: '🎒 TS 10th Class'},
      {code: 'AP_10TH', label: '🎒 AP 10th Class'},
      {code: 'ITI_ALL', label: '🔧 ITI Trade'},
      {code: 'OPEN_UNIV', label: '🏛️ Open University'}
    ];

    async function updateGroupExamCategory(gid, newCat) {
      try {
        const res = await fetch('/api/whatsapp/update_group', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({id: gid, updates: {category: newCat}})
        });
        const d = await res.json();
        if (d.ok) {
          const pill = document.getElementById('save-indicator-' + gid);
          if (pill) {
            pill.style.display = 'inline';
            setTimeout(() => { pill.style.display = 'none'; }, 2000);
          }
        }
      } catch (e) {
        alert('Failed to update category: ' + e);
      }
    }

    async function loadWAGroups() {
      const res = await fetch('/api/whatsapp/groups');
      const d = await res.json();
      const tbody = document.querySelector('#table-wa-groups tbody');
      tbody.innerHTML = '';
      (d.groups || []).forEach(g => {
        const tr = document.createElement('tr');
        const gType = g.group_type || 'EXAM_SPECIFIC';
        const typeBadge = gType === 'GENERAL'
          ? '<span style="background:#0284c7; color:white; padding:2px 7px; border-radius:12px; font-size:10px; font-weight:700;">🌐 GENERAL</span>'
          : '<span style="background:#059669; color:white; padding:2px 7px; border-radius:12px; font-size:10px; font-weight:700;">🎯 EXAM-SPECIFIC</span>';

        const catOpts = ALL_EXAM_CATEGORIES.map(c => 
          `<option value="${c.code}" ${g.category === c.code ? 'selected' : ''}>${c.label}</option>`
        ).join('');

        tr.innerHTML = `
          <td><input type="checkbox" class="wa-group-select-checkbox" data-gid="${g.id}"></td>
          <td>${g.id}</td>
          <td><b>${g.name}</b></td>
          <td>
            <div style="display:flex; align-items:center; gap:6px;">
              <select style="margin:0; padding:4px 8px; font-size:11px; background:#0f172a; border:1px solid #38bdf8; color:#f8fafc; border-radius:6px; font-weight:600;" onchange="updateGroupExamCategory('${g.id}', this.value)">
                ${catOpts}
              </select>
              <span id="save-indicator-${g.id}" style="display:none; color:#10b981; font-size:11px; font-weight:700;">✓ Saved</span>
            </div>
          </td>
          <td>${typeBadge}</td>
          <td><span class="shift-tag">${g.shift || 'ALL_DAY'}</span></td>
          <td style="font-family:monospace; font-size:12px;">${g.jid}</td>
          <td><span class="status-pill ${g.active ? 'open' : 'closed'}">${g.active ? 'Active' : 'Paused'}</span></td>
          <td><button class="btn btn-outline" style="padding:4px 8px; font-size:11px;" onclick="deleteWAGroup('${g.id}')">Delete</button></td>
        `;
        tbody.appendChild(tr);
      });
      if (d.gateway_url) document.getElementById('wa-gateway-input').value = d.gateway_url;
    }

    function filterWAGroups() {
      const q = (document.getElementById('wa-search-box').value || '').toLowerCase();
      const rows = document.querySelectorAll('#table-wa-groups tbody tr');
      rows.forEach(r => {
        const text = r.innerText.toLowerCase();
        r.style.display = text.includes(q) ? '' : 'none';
      });
    }

    async function exportExcelSheet() {
      const res = await fetch('/api/whatsapp/groups');
      const d = await res.json();
      const groups = d.groups || [];
      const lines = ['Group Name\\tLink or JID\\tCategory\\tShift\\tGroup Type'];
      groups.forEach(g => {
        lines.push(`${g.name}\\t${g.jid}\\t${g.category || 'GENERAL'}\\t${g.shift || 'ALL_DAY'}\\t${g.group_type || 'EXAM_SPECIFIC'}`);
      });
      document.getElementById('excel-paste-text').value = lines.join('\\n');
      document.getElementById('excel-import-log').innerText = `📋 Exported ${groups.length} groups to text box! You can copy/edit them directly and click Save.`;
    }

    async function addNewWAGroup() {
      const name = document.getElementById('new-wa-title').value.trim();
      const jid = document.getElementById('new-wa-jid').value.trim();
      const category = document.getElementById('new-wa-category').value;
      const gType = document.getElementById('new-wa-grouptype').value;
      const shift = document.getElementById('new-wa-shift').value;
      if (!name || !jid) return alert('Enter group name and JID / Link');
      await fetch('/api/whatsapp/add_group', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name, jid, category, shift, group_type: gType})
      });
      document.getElementById('new-wa-title').value = '';
      document.getElementById('new-wa-jid').value = '';
      loadWAGroups();
      fetchStats();
    }

    function selectAllGroups(checked) {
      const cbs = document.querySelectorAll('.wa-group-select-checkbox');
      cbs.forEach(cb => cb.checked = checked);
      const master = document.getElementById('wa-select-all');
      if (master) master.checked = checked;
    }

    function getSelectedGroupIds() {
      const cbs = document.querySelectorAll('.wa-group-select-checkbox:checked');
      return Array.from(cbs).map(cb => cb.getAttribute('data-gid'));
    }

    async function dispatchSelectedGroups() {
      const gids = getSelectedGroupIds();
      if (!gids || gids.length === 0) {
        return alert('Please select at least 1 WhatsApp group using the checkboxes to dispatch!');
      }
      if (!confirm(`Run 5-poll anti-ban broadcast on ${gids.length} selected group(s)?\\n(${gapLabel()} gaps between polls, batch rest after every 5 groups)`)) return;

      const gw = document.getElementById('wa-gateway-input').value;
      const res = await fetch('/api/whatsapp/start_pipeline', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          target_group_ids: gids,
          is_question: true,
          gateway: gw,
          delay_min: getGapMin(),
          delay_max: getGapMax(),
          questions_count: 5
        })
      });
      const d = await res.json();
      if (!d.ok) alert(d.message);
      else alert(`🚀 Broadcast started for ${gids.length} selected groups!`);
    }

    async function deleteWAGroup(id) {
      if (!confirm('Remove this group?')) return;
      await fetch('/api/whatsapp/remove_group', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id})
      });
      loadWAGroups();
      fetchStats();
    }

    async function startInterleaved(isQuestion) {
      const cat = document.getElementById('wa-target-category').value;
      const shift = document.getElementById('wa-target-shift').value;
      const msg = document.getElementById('wa-broadcast-msg').value;
      const att = document.getElementById('wa-attachment-url').value;
      const gw = document.getElementById('wa-gateway-input').value;

      const res = await fetch('/api/whatsapp/start_pipeline', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          category: cat,
          shift: shift,
          is_question: isQuestion,
          custom_msg: msg,
          attachment: att,
          gateway: gw,
          delay_min: getGapMin(),
          delay_max: getGapMax(),
          questions_count: 5
        })
      });
      const d = await res.json();
      if (!d.ok) alert(d.message);
    }

    async function stopInterleaved() {
      await fetch('/api/whatsapp/stop_pipeline', {method: 'POST'});
    }

    function toggleContinuousMode(isContinuous) {
      const durContainer = document.getElementById('sched-duration-container');
      if (durContainer) {
        durContainer.style.display = isContinuous ? 'none' : 'block';
      }
    }

    async function checkSchedulerConflictLive() {
      const timeVal = (document.getElementById('clock-slot-time').value || '').trim();
      const extraTimes = (document.getElementById('clock-extra-times').value || '')
        .split(',')
        .map(t => t.trim())
        .filter(t => t.length > 0);
      const allTimes = [timeVal, ...extraTimes];
      const gids = getSelectedGroupIds();

      const alertBox = document.getElementById('sched-conflict-alert');
      const msgBox = document.getElementById('sched-conflict-msg');
      if (!alertBox || !msgBox) return;

      if (gids.length === 0 || allTimes.length === 0) {
        alertBox.style.display = 'none';
        return;
      }

      for (const t of allTimes) {
        try {
          const res = await fetch('/api/whatsapp/check_conflicts', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({target_group_ids: gids, time: t})
          });
          const d = await res.json();
          if (d.has_conflicts) {
            const conflictMsgs = d.conflicts.map(c => c.message).join('; ');
            msgBox.innerHTML = `Group collision detected for <b>${t}</b>: ${conflictMsgs}`;
            alertBox.style.display = 'block';
            return;
          }
        } catch (e) {
          console.error(e);
        }
      }
      alertBox.style.display = 'none';
    }

    async function addClockSlot() {
      const timeVal = (document.getElementById('clock-slot-time').value || '').trim();
      const extraTimesRaw = (document.getElementById('clock-extra-times').value || '').trim();
      const label = (document.getElementById('clock-slot-label').value || '').trim();
      const cat = document.getElementById('clock-slot-cat').value;
      const isAuto = document.getElementById('sched-auto-continuous').checked;
      const daysDur = isAuto ? 0 : parseInt(document.getElementById('sched-days-duration').value || '7');
      const gids = getSelectedGroupIds();

      if (!timeVal) return alert('Please select a clock time first!');

      const extraTimes = extraTimesRaw ? extraTimesRaw.split(',').map(s => s.trim()).filter(Boolean) : [];
      const allTimes = [timeVal, ...extraTimes];

      // Collision Check before submitting
      try {
        for (const t of allTimes) {
          const cRes = await fetch('/api/whatsapp/check_conflicts', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({target_group_ids: gids, time: t})
          });
          const cData = await cRes.json();
          if (cData.has_conflicts) {
            const warn = cData.conflicts.map(c => c.message).join('\\n');
            const proceed = confirm(`⚠️ Group Conflict Warning for ${t}:\\n${warn}\\n\\nDo you still want to proceed and save this schedule?`);
            if (!proceed) return;
          }
        }
      } catch (e) {
        console.error('Conflict check error:', e);
      }

      try {
        const res = await fetch('/api/whatsapp/schedule_quiz', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            time: timeVal,
            times: allTimes,
            label: label || (timeVal + ' Daily ' + cat + ' Drill'),
            category: cat,
            target_group_ids: gids,
            is_question: true,
            auto_mode: isAuto,
            days_duration: daysDur
          })
        });
        const d = await res.json();
        if (d.ok) {
          alert(`⏰ Successfully scheduled ${allTimes.length} daily recurring slot(s): ${allTimes.join(', ')}!\\nMode: ${isAuto ? 'Auto Continuous (Always-On)' : daysDur + ' Days'}`);
          document.getElementById('clock-slot-label').value = '';
          document.getElementById('clock-extra-times').value = '';
          const alertBox = document.getElementById('sched-conflict-alert');
          if (alertBox) alertBox.style.display = 'none';
          loadSchedules();
        }
      } catch (e) {
        alert('Failed to schedule: ' + e);
      }
    }

    async function scheduleQuizModal() {
      const timeVal = prompt('Enter Daily Quiz Dispatch Time (HH:MM 24-hr format, e.g. 08:30, 13:00, 18:30, 21:00):', '10:00');
      if (!timeVal) return;
      const label = prompt('Slot Label or Title (e.g. Morning General English / Evening Police Practice):', 'Daily Scheduled Drill');
      const cat = document.getElementById('wa-target-category').value;
      const gids = getSelectedGroupIds();

      try {
        const res = await fetch('/api/whatsapp/schedule_quiz', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            time: timeVal.trim(),
            label: label || 'Daily Scheduled Drill',
            category: cat,
            target_group_ids: gids,
            is_question: true,
            auto_mode: true
          })
        });
        const d = await res.json();
        if (d.ok) {
          alert('⏰ Daily recurring slot added for ' + timeVal + ' (' + (label || 'Drill') + ')!');
          loadSchedules();
        }
      } catch (e) {
        alert('Failed to schedule: ' + e);
      }
    }

    async function toggleScheduleJob(id) {
      try {
        await fetch('/api/whatsapp/toggle_schedule', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({id})
        });
        loadSchedules();
      } catch (e) {
        alert('Error: ' + e);
      }
    }

    async function loadSchedules() {
      try {
        const res = await fetch('/api/whatsapp/schedules');
        const d = await res.json();
        const listEl = document.getElementById('wa-schedules-list');
        if (!listEl) return;

        const jobs = d.jobs || [];
        if (jobs.length === 0) {
          listEl.innerHTML = '<div style="color:var(--text-muted); text-align:center; padding:10px;">No daily recurring slots configured yet. Click "Add New Daily Quiz Slot" above!</div>';
          return;
        }

        listEl.innerHTML = jobs.map(j => {
          const isEn = j.enabled !== false;
          const statusBadge = isEn 
            ? '<span style="background:#10b981; color:#050811; font-weight:800; font-size:10px; padding:2px 6px; border-radius:10px;">● ACTIVE</span>'
            : '<span style="background:#64748b; color:white; font-weight:800; font-size:10px; padding:2px 6px; border-radius:10px;">○ PAUSED</span>';

          const modeBadge = j.auto_mode || (!j.days_duration && !j.end_date)
            ? '<span style="background:#0284c7; color:white; font-size:10px; font-weight:700; padding:1px 6px; border-radius:8px;">🔄 AUTO-CONTINUOUS</span>'
            : `<span style="background:#d97706; color:white; font-size:10px; font-weight:700; padding:1px 6px; border-radius:8px;">📅 Until ${j.end_date || (j.days_duration + 'd')}</span>`;

          const targetLabel = (j.target_group_ids && j.target_group_ids.length > 0)
            ? `${j.target_group_ids.length} Selected Groups`
            : `All ${j.category || 'General'} Groups`;

          return `
            <div style="display:flex; justify-content:space-between; align-items:center; padding:8px 0; border-bottom:1px solid rgba(255,255,255,0.06); flex-wrap:wrap; gap:8px;">
              <div>
                <div style="display:flex; align-items:center; gap:8px;">
                  <span style="font-size:15px; font-weight:800; color:#38bdf8; font-family:monospace;">${j.time}</span>
                  <b>${j.label || 'Daily Exam Drill'}</b>
                  ${statusBadge}
                  ${modeBadge}
                </div>
                <div style="font-size:11px; color:var(--text-muted); margin-top:3px;">
                  Category: <span class="category-tag">${j.category || 'ALL'}</span> · Target: <b>${targetLabel}</b> · Dispatches: <b>${j.total_dispatches || 0} times</b>
                </div>
              </div>
              <div style="display:flex; gap:6px;">
                <button class="btn btn-outline" style="padding:3px 8px; font-size:11px;" onclick="toggleScheduleJob('${j.id}')">${isEn ? '⏸ Pause' : '▶ Enable'}</button>
                <button class="btn btn-outline" style="padding:3px 8px; font-size:11px; color:#ef4444;" onclick="deleteScheduleJob('${j.id}')">🗑 Delete</button>
              </div>
            </div>
          `;
        }).join('');
      } catch (e) {
        console.error(e);
      }
    }

    async function deleteScheduleJob(id) {
      if (!confirm('Cancel this scheduled quiz?')) return;
      try {
        await fetch('/api/whatsapp/delete_schedule', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({id})
        });
        loadSchedules();
      } catch (e) {
        alert('Error: ' + e);
      }
    }

    let uploadedExcelBase64 = '';
    let uploadedExcelSheets = [];
    let bulkAttachmentBase64 = '';
    let bulkAttachmentFileName = '';

    function handleMainExcelFileUpload(event) {
      const file = event.target.files[0];
      if (!file) return;
      document.getElementById('selected-file-label').innerText = file.name + ' (' + Math.round(file.size / 1024) + ' KB)';
      
      const isXlsx = file.name.toLowerCase().endsWith('.xlsx') || file.name.toLowerCase().endsWith('.xls');
      if (isXlsx) {
        const reader = new FileReader();
        reader.onload = async function(e) {
          const arrayBuffer = e.target.result;
          const bytes = new Uint8Array(arrayBuffer);
          let binary = '';
          for (let i = 0; i < bytes.byteLength; i++) {
            binary += String.fromCharCode(bytes[i]);
          }
          uploadedExcelBase64 = btoa(binary);
          await inspectUploadedExcel(uploadedExcelBase64, file.name);
        };
        reader.readAsArrayBuffer(file);
      } else {
        const reader = new FileReader();
        reader.onload = async function(e) {
          const text = e.target.result;
          document.getElementById('excel-paste-text').value = text;
          await importExcelSheet();
        };
        reader.readAsText(file);
      }
    }

    async function inspectUploadedExcel(b64, fname) {
      const log = document.getElementById('excel-import-log');
      log.innerText = 'Inspecting workbook sheets in ' + fname + '...';
      try {
        const res = await fetch('/api/excel/inspect', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({file_b64: b64, filename: fname})
        });
        const d = await res.json();
        if (!d.ok) {
          log.innerText = '❌ Failed to inspect excel: ' + (d.error || 'Unknown error');
          return;
        }
        uploadedExcelSheets = d.sheets || [];
        const panel = document.getElementById('multisheet-panel');
        const container = document.getElementById('multisheet-checkboxes');
        container.innerHTML = '';
        
        uploadedExcelSheets.forEach(s => {
          const div = document.createElement('div');
          div.style = 'display:flex; align-items:center; gap:8px; background:#1e293b; padding:8px 12px; border-radius:6px;';
          div.innerHTML = `
            <input type="checkbox" class="excel-sheet-check" id="sheet-chk-${s.name}" value="${s.name}" checked>
            <label for="sheet-chk-${s.name}" style="font-size:12px; font-weight:600; cursor:pointer;">
              📄 ${s.name} <span style="color:#a7f3d0; font-size:11px;">(${s.rows_count} rows)</span>
            </label>
          `;
          container.appendChild(div);
        });
        panel.style.display = 'block';
        log.innerText = `✅ Found ${uploadedExcelSheets.length} sheet(s) in workbook! Select the sheets you want to import below.`;
      } catch (e) {
        log.innerText = '❌ Error reading sheets: ' + e;
      }
    }

    function selectAllSheets(val) {
      document.querySelectorAll('.excel-sheet-check').forEach(c => c.checked = val);
    }

    async function importSelectedExcelSheets() {
      const selected = Array.from(document.querySelectorAll('.excel-sheet-check:checked')).map(c => c.value);
      if (selected.length === 0) return alert('Please select at least one sheet to import!');
      const log = document.getElementById('excel-import-log');
      log.innerText = `Importing ${selected.length} sheet(s) into database...`;

      try {
        const res = await fetch('/api/excel/import_selected', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({file_b64: uploadedExcelBase64, sheets: selected})
        });
        const d = await res.json();
        if (d.ok) {
          log.innerHTML = `<span style="color:#10b981; font-weight:700;">✅ Success! Imported ${d.imported_groups_count} WhatsApp Groups and ${d.imported_channels_count} Telegram Channels across ${d.sheets_processed.length} sheets!</span>`;
          fetchStats();
          loadWAGroups();
          loadChannels();
          await loadBulkTargets();
          toggleAllBulkTargets(true);  // auto-select everything incl. newly imported
        } else {
          log.innerText = '❌ Import failed: ' + (d.error || 'Unknown error');
        }
      } catch (e) {
        log.innerText = '❌ Request failed: ' + e;
      }
    }

    function handleBulkAttachmentSelect(event) {
      const file = event.target.files[0];
      if (!file) return;
      bulkAttachmentFileName = file.name;
      document.getElementById('bulk-file-name').innerText = file.name;
      document.getElementById('bulk-clear-file-btn').style.display = 'inline-block';

      const reader = new FileReader();
      reader.onload = function(e) {
        const arrayBuffer = e.target.result;
        const bytes = new Uint8Array(arrayBuffer);
        let binary = '';
        for (let i = 0; i < bytes.byteLength; i++) {
          binary += String.fromCharCode(bytes[i]);
        }
        bulkAttachmentBase64 = btoa(binary);
      };
      reader.readAsArrayBuffer(file);
    }

    function clearBulkAttachment() {
      bulkAttachmentBase64 = '';
      bulkAttachmentFileName = '';
      document.getElementById('bulk-attachment-file').value = '';
      document.getElementById('bulk-file-name').innerText = 'No file selected';
      document.getElementById('bulk-clear-file-btn').style.display = 'none';
    }

    let cachedBulkChannels = [];
    let cachedBulkGroups = [];
    let cachedBundles = [];

    async function quickAddGroups() {
      const txt = document.getElementById('quick-add-links').value.trim();
      const out = document.getElementById('quick-add-result');
      if (!txt) return alert('WhatsApp invite links paste చేయండి (ఒక్కో line కి ఒకటి)!');
      out.innerHTML = '<span style="color:#38bdf8;">⏳ Adding groups... (bridge connected అయితే bot auto-join అవుతుంది, కొన్ని సెకన్లు పడుతుంది)</span>';
      try {
        const res = await fetch('/api/whatsapp/quick_add', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({text: txt})
        });
        const d = await res.json();
        if (!d.ok && d.error) { out.innerHTML = '<span style="color:#ef4444;">❌ ' + d.error + '</span>'; return; }
        let html = `<span style="color:#10b981; font-weight:700;">✅ ${d.added.length} group(s) added` +
                   (d.joined ? ` · 🤝 ${d.joined} auto-joined via invite link!` : '') + '</span>';
        d.added.forEach(g => {
          html += `<div style="color:#a7f3d0;">&nbsp;&nbsp;💬 ${g.name} <span style="color:#64748b;">[${g.category}]${g.joined ? ' · ✓JOINED' : ''}${g.participants ? ' · 👥 ' + g.participants : ''}</span></div>`;
        });
        (d.failed || []).forEach(f => {
          html += `<div style="color:#f87171;">&nbsp;&nbsp;⚠️ ${f.line.slice(0, 60)} → ${f.error}</div>`;
        });
        out.innerHTML = html;
        if (d.added.length) {
          document.getElementById('quick-add-links').value = '';
          loadWAGroups();
          fetchStats();
          await loadBulkTargets();  // new groups auto-selected by the sticky engine
        }
      } catch (e) {
        out.innerHTML = '<span style="color:#ef4444;">❌ ' + e + '</span>';
      }
    }

    async function loadBulkTargets() {
      try {
        const [chRes, waRes, bRes] = await Promise.all([
          fetch('/api/channels'),
          fetch('/api/whatsapp/groups'),
          fetch('/api/bundles')
        ]);
        const chData = await chRes.json();
        const waData = await waRes.json();
        const bData = await bRes.json();

        cachedBulkChannels = Object.entries(chData.channels || {});
        cachedBulkGroups = waData.groups || [];
        cachedBundles = bData.bundles || [];

        // Populate Bundle Presets Dropdown
        const bSel = document.getElementById('bulk-bundle-selector');
        if (bSel) {
          bSel.innerHTML = '<option value="">-- Choose a Saved Group Bundle --</option>' +
            cachedBundles.map(b => `<option value="${b.id}">${b.name} (${(b.target_groups||[]).length} Groups, ${(b.target_channels||[]).length} Channels)</option>`).join('');
        }

        renderBulkTargetsList();
        populateBundleCreatorMembers();
      } catch (e) {
        console.error('Error loading bulk targets:', e);
      }
    }

    // ------- STICKY SELECTION ENGINE: search/filter చేసినా selection పోదు -------
    let bulkSelCh = null;   // Set of selected Telegram channel keys
    let bulkSelWa = null;   // Set of selected WhatsApp group ids

    function initBulkSelection() {
      if (bulkSelCh !== null && bulkSelWa !== null) { autoSelectNewBulkItems(); return; }
      // restore last selection from this browser; default = everything selected
      try {
        const saved = JSON.parse(localStorage.getItem('su_bulk_sel') || 'null');
        if (saved && Array.isArray(saved.ch) && Array.isArray(saved.wa)) {
          bulkSelCh = new Set(saved.ch);
          bulkSelWa = new Set(saved.wa);
          autoSelectNewBulkItems();
          return;
        }
      } catch (e) {}
      bulkSelCh = new Set(cachedBulkChannels.map(([k]) => k));
      bulkSelWa = new Set(cachedBulkGroups.map(g => g.id));
      persistBulkSelection();
    }

    // Any group/channel seen for the FIRST time (new sync/import) is auto-selected
    function autoSelectNewBulkItems() {
      let known = {ch: [], wa: []};
      try { known = JSON.parse(localStorage.getItem('su_bulk_known') || '{"ch":[],"wa":[]}'); } catch (e) {}
      const knownCh = new Set(known.ch || []), knownWa = new Set(known.wa || []);
      let changed = false;
      cachedBulkChannels.forEach(([k]) => { if (!knownCh.has(k)) { bulkSelCh.add(k); knownCh.add(k); changed = true; } });
      cachedBulkGroups.forEach(g => { if (!knownWa.has(g.id)) { bulkSelWa.add(g.id); knownWa.add(g.id); changed = true; } });
      if (changed) {
        try { localStorage.setItem('su_bulk_known', JSON.stringify({ch: [...knownCh], wa: [...knownWa]})); } catch (e) {}
        persistBulkSelection();
      }
    }

    function persistBulkSelection() {
      try {
        localStorage.setItem('su_bulk_sel', JSON.stringify({ch: [...bulkSelCh], wa: [...bulkSelWa]}));
      } catch (e) {}
    }

    function toggleBulkSel(kind, key, on) {
      const set = kind === 'ch' ? bulkSelCh : bulkSelWa;
      if (on) set.add(key); else set.delete(key);
      persistBulkSelection();
      updateBulkSelectedBadge();
      checkBulkConflictsLive();
    }

    function getVisibleBulkItems() {
      const q = (document.getElementById('bulk-target-search')?.value || '').toLowerCase();
      const cat = document.getElementById('bulk-cat-filter')?.value || 'ALL';
      const ch = cachedBulkChannels.filter(([key, c]) => {
        const nameMatch = c.name.toLowerCase().includes(q) || key.toLowerCase().includes(q);
        const catMatch = cat === 'ALL' || (c.exam_type && c.exam_type.toUpperCase().includes(cat)) || (c.name.toUpperCase().includes(cat));
        return nameMatch && catMatch;
      });
      const wa = cachedBulkGroups.filter(g => {
        const nameMatch = g.name.toLowerCase().includes(q) || (g.jid || '').toLowerCase().includes(q);
        const catMatch = cat === 'ALL' || (g.category && g.category.toUpperCase() === cat.toUpperCase());
        return nameMatch && catMatch;
      });
      return {ch, wa};
    }

    function renderBulkTargetsList() {
      const chList = document.getElementById('bulk-channels-list');
      const waList = document.getElementById('bulk-groups-list');
      if (!chList || !waList) return;
      initBulkSelection();

      const vis = getVisibleBulkItems();
      chList.innerHTML = '';
      waList.innerHTML = '';

      vis.ch.forEach(([key, ch]) => {
        const sel = bulkSelCh.has(key);
        const div = document.createElement('div');
        div.className = 'bulk-target-item';
        div.style = `display:flex; align-items:center; gap:8px; font-size:12px; padding:5px 8px; border-radius:6px; cursor:pointer; border:1px solid ${sel ? 'rgba(56,189,248,0.4)' : 'transparent'}; background:${sel ? 'rgba(56,189,248,0.08)' : 'transparent'};`;
        div.innerHTML = `
          <input type="checkbox" class="bulk-target-ch" value="${key}" ${sel ? 'checked' : ''} style="pointer-events:none;">
          <span style="flex:1;">${ch.chat_type === 'group' ? '💬' : '📢'} <b>${ch.name}</b> ${ch.chat_type === 'group' ? '<span style="color:#6ee7b7; font-size:9px; font-weight:800;">TG GROUP</span>' : ''} <span style="color:#64748b;">(${ch.chat_id || key})</span></span>
        `;
        div.onclick = () => {
          const cb = div.querySelector('input');
          cb.checked = !cb.checked;
          toggleBulkSel('ch', key, cb.checked);
          div.style.background = cb.checked ? 'rgba(56,189,248,0.08)' : 'transparent';
          div.style.border = cb.checked ? '1px solid rgba(56,189,248,0.4)' : '1px solid transparent';
        };
        chList.appendChild(div);
      });
      document.getElementById('bulk-channels-count').innerText = vis.ch.length;

      vis.wa.forEach(g => {
        const sel = bulkSelWa.has(g.id);
        const div = document.createElement('div');
        div.className = 'bulk-target-item';
        div.style = `display:flex; align-items:center; gap:8px; font-size:12px; padding:5px 8px; border-radius:6px; cursor:pointer; border:1px solid ${sel ? 'rgba(16,185,129,0.4)' : 'transparent'}; background:${sel ? 'rgba(16,185,129,0.08)' : 'transparent'};`;
        const members = g.participants ? ` <span style="color:#64748b; font-size:10px;">👥 ${g.participants}</span>` : '';
        const realTag = g.real ? ' <span style="color:#10b981; font-size:9px; font-weight:800;" title="Synced from real WhatsApp">✓REAL</span>' : '';
        div.innerHTML = `
          <input type="checkbox" class="bulk-target-wa" value="${g.id}" ${sel ? 'checked' : ''} style="pointer-events:none;">
          <span style="flex:1;">💬 <b>${g.name}</b> <span style="color:#10b981; font-size:10px; font-weight:700;">[${g.category || 'GENERAL'}]</span>${members}${realTag}</span>
        `;
        div.onclick = () => {
          const cb = div.querySelector('input');
          cb.checked = !cb.checked;
          toggleBulkSel('wa', g.id, cb.checked);
          div.style.background = cb.checked ? 'rgba(16,185,129,0.08)' : 'transparent';
          div.style.border = cb.checked ? '1px solid rgba(16,185,129,0.4)' : '1px solid transparent';
        };
        waList.appendChild(div);
      });
      document.getElementById('bulk-groups-count').innerText = vis.wa.length;
      updateBulkSelectedBadge();
    }

    function filterBulkTargetList() {
      renderBulkTargetsList();
    }

    function updateBulkSelectedBadge() {
      initBulkSelection();
      // prune ids that no longer exist
      const chKeys = new Set(cachedBulkChannels.map(([k]) => k));
      const waIds = new Set(cachedBulkGroups.map(g => g.id));
      bulkSelCh.forEach(k => { if (!chKeys.has(k)) bulkSelCh.delete(k); });
      bulkSelWa.forEach(k => { if (!waIds.has(k)) bulkSelWa.delete(k); });
      const badge = document.getElementById('bulk-selected-count-badge');
      if (badge) badge.innerText = `✅ ${bulkSelCh.size + bulkSelWa.size} selected (${bulkSelCh.size} Ch, ${bulkSelWa.size} Grp)`;
    }

    function selectVisibleBulkTargets(on) {
      const vis = getVisibleBulkItems();
      vis.ch.forEach(([key]) => { if (on) bulkSelCh.add(key); else bulkSelCh.delete(key); });
      vis.wa.forEach(g => { if (on) bulkSelWa.add(g.id); else bulkSelWa.delete(g.id); });
      persistBulkSelection();
      renderBulkTargetsList();
      checkBulkConflictsLive();
    }

    function applySelectedBundle(bundleId) {
      if (!bundleId) return;
      const b = cachedBundles.find(x => x.id === bundleId);
      if (!b) return;

      initBulkSelection();
      bulkSelWa = new Set(b.target_groups || []);
      bulkSelCh = new Set(b.target_channels || []);
      persistBulkSelection();
      renderBulkTargetsList();
      checkBulkConflictsLive(bundleId);
    }

    async function checkBulkConflictsLive(activeBundleId = '') {
      const waGids = (initBulkSelection(), [...bulkSelWa]);
      const chKeys = (initBulkSelection(), [...bulkSelCh]);
      const alertBox = document.getElementById('bulk-conflict-alert');
      const msgBox = document.getElementById('bulk-conflict-msg');
      if (!alertBox || !msgBox) return;

      if (waGids.length === 0 && chKeys.length === 0) {
        alertBox.style.display = 'none';
        return;
      }

      try {
        const res = await fetch('/api/whatsapp/check_conflicts', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            target_group_ids: waGids,
            target_channel_keys: chKeys,
            bundle_id: activeBundleId
          })
        });
        const d = await res.json();
        if (d.has_conflicts) {
          const warnText = d.conflicts.map(c => `${c.message} (${(c.conflicting_groups||[]).length} items)`).join('; ');
          msgBox.innerHTML = warnText;
          alertBox.style.display = 'block';
        } else {
          alertBox.style.display = 'none';
        }
      } catch (e) {
        console.error(e);
      }
    }

    function toggleAllBulkTargets(val) {
      initBulkSelection();
      bulkSelCh = val ? new Set(cachedBulkChannels.map(([k]) => k)) : new Set();
      bulkSelWa = val ? new Set(cachedBulkGroups.map(g => g.id)) : new Set();
      persistBulkSelection();
      renderBulkTargetsList();
      checkBulkConflictsLive();
    }

    function selectBulkChannelsOnly() {
      initBulkSelection();
      bulkSelCh = new Set(cachedBulkChannels.map(([k]) => k));
      bulkSelWa = new Set();
      persistBulkSelection();
      renderBulkTargetsList();
      checkBulkConflictsLive();
    }

    function selectBulkWAGroupsOnly() {
      initBulkSelection();
      bulkSelCh = new Set();
      bulkSelWa = new Set(cachedBulkGroups.map(g => g.id));
      persistBulkSelection();
      renderBulkTargetsList();
      checkBulkConflictsLive();
    }

    async function sendBulkQuizPollsToTargets() {
      const chKeys = (initBulkSelection(), [...bulkSelCh]);
      const waGids = (initBulkSelection(), [...bulkSelWa]);
      const pollCount = parseInt(document.getElementById('poll-count-select')?.value || '5', 10);
      const pollSubjects = Array.from(document.querySelectorAll('.poll-subj:checked')).map(c => c.value);

      if (chKeys.length === 0 && waGids.length === 0) {
        return alert('Please select at least one Telegram Channel or WhatsApp Group target!');
      }

      // Check collision before quiz dispatch
      try {
        const cRes = await fetch('/api/whatsapp/check_conflicts', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({target_group_ids: waGids, target_channel_keys: chKeys})
        });
        const cData = await cRes.json();
        if (cData.has_conflicts) {
          const warn = cData.conflicts.map(c => c.message).join('\\n');
          const cont = confirm(`⚠️ Targets Conflict Notice:\\n${warn}\\n\\nDo you want to proceed anyway?`);
          if (!cont) return;
        }
      } catch (e) {
        console.error(e);
      }

      const subjLabel = pollSubjects.length ? pollSubjects.join(', ') : 'All Subjects';
      if (!confirm(`🚀 Launch ${pollCount}-poll quiz dispatch?\n• Subjects: ${subjLabel}\n• ${chKeys.length} Telegram Channels (instant) + ${waGids.length} WhatsApp Groups (${gapLabel()} gaps)`)) return;

      const log = document.getElementById('bulk-broadcast-log');
      log.innerText = `Starting live quiz rounds on selected targets...`;

      // 1. Dispatch Telegram Channels
      if (chKeys.length > 0) {
        for (const k of chKeys) {
          try {
            await fetch('/api/post_poll', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({channel: k, count: pollCount, subjects: pollSubjects})
            });
          } catch (e) {
            console.error('Channel post error:', e);
          }
        }
      }

      // 2. Dispatch WhatsApp Groups via Anti-Ban Engine
      if (waGids.length > 0) {
        try {
          const gw = document.getElementById('wa-gateway-input')?.value || '';
          await fetch('/api/whatsapp/start_pipeline', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              target_group_ids: waGids,
              is_question: true,
              gateway: gw,
              delay_min: getGapMin(),
              delay_max: getGapMax(),
              questions_count: pollCount,
              subjects: pollSubjects
            })
          });
        } catch (e) {
          console.error('WhatsApp dispatch error:', e);
        }
      }

      log.innerText = `✅ ${pollCount}-Poll Exam Rounds (${subjLabel}) → ${chKeys.length} Channels (instant) + ${waGids.length} WhatsApp Groups (anti-ban queue)!`;
      alert(`✅ Exam Polls launched! ${chKeys.length} Channels + ${waGids.length} Groups · Subjects: ${subjLabel}`);
    }

    async function sendBulkBroadcast() {
      const msg = document.getElementById('bulk-broadcast-msg').value.trim();
      const attUrl = document.getElementById('bulk-attachment-url').value.trim();
      const log = document.getElementById('bulk-broadcast-log');

      if (!msg && !attUrl && !bulkAttachmentBase64) {
        return alert('Please write a message or attach a file/URL to broadcast!');
      }

      const chKeys = (initBulkSelection(), [...bulkSelCh]);
      const waGids = (initBulkSelection(), [...bulkSelWa]);

      if (chKeys.length === 0 && waGids.length === 0) {
        return alert('Please select at least one Channel or WhatsApp Group target!');
      }

      // Check collision before dispatching
      try {
        const cRes = await fetch('/api/whatsapp/check_conflicts', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({target_group_ids: waGids, target_channel_keys: chKeys})
        });
        const cData = await cRes.json();
        if (cData.has_conflicts) {
          const warn = cData.conflicts.map(c => c.message).join('\\n');
          const cont = confirm(`⚠️ Targets Conflict Notice:\\n${warn}\\n\\nDo you want to proceed with dispatch anyway?`);
          if (!cont) return;
        }
      } catch (e) {
        console.error(e);
      }

      if (!confirm(`Confirm dispatch to ${chKeys.length} Telegram Channels and ${waGids.length} WhatsApp Groups?`)) return;

      log.innerText = `Dispatching across ${chKeys.length} channels and ${waGids.length} groups...`;

      try {
        const res = await fetch('/api/broadcast/dispatch', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            message: msg,
            attachment_url: attUrl,
            attachment_data_b64: bulkAttachmentBase64,
            attachment_filename: bulkAttachmentFileName,
            target_channel_keys: chKeys,
            target_group_ids: waGids
          })
        });
        const d = await res.json();
        let logTxt = `✅ Broadcast Launched!\\n• Telegram Channels Dispatched: ${d.telegram_dispatched}\\n• WhatsApp Groups Queued: ${d.whatsapp_dispatched}`;
        if (d.whatsapp_note) logTxt += `\\nℹ️ ${d.whatsapp_note}`;
        if (d.errors && d.errors.length > 0) {
          logTxt += `\\n⚠️ Notes/Errors (${d.errors.length}):\\n` + d.errors.slice(0, 5).join('\\n');
        }
        log.innerText = logTxt;
        alert(`Dispatched successfully to ${d.telegram_dispatched} Channels and ${d.whatsapp_dispatched} WhatsApp Groups!`);
      } catch (e) {
        log.innerText = '❌ Broadcast failed: ' + e;
      }
    }

    async function importExcelSheet() {
      const raw = document.getElementById('excel-paste-text').value.trim();
      const log = document.getElementById('excel-import-log');
      if (!raw) return alert('Paste your Excel or Google Sheet lines first');
      log.innerText = 'Importing rows into database...';
      const res = await fetch('/api/excel/import', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({raw_text: raw})
      });
      const d = await res.json();
      log.innerText = '✅ Success! Imported ' + d.imported_groups_count + ' WhatsApp Groups and ' + d.imported_channels_count + ' Telegram Channels.';
      fetchStats();
      loadWAGroups();
    }

    function handleExcelFileUpload(event) {
      const file = event.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = async function(e) {
        const text = e.target.result;
        document.getElementById('wa-direct-excel-paste').value = text;
        await importInTabExcel();
      };
      reader.readAsText(file);
    }

    function handleMainExcelFileUpload(event) {
      const file = event.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = async function(e) {
        const text = e.target.result;
        document.getElementById('excel-paste-text').value = text;
        await importExcelSheet();
      };
      reader.readAsText(file);
    }

    async function importInTabExcel() {
      const raw = document.getElementById('wa-direct-excel-paste').value.trim();
      const statusEl = document.getElementById('wa-excel-status-log');
      if (!raw) return alert('Paste your Excel / CSV rows or choose a file first!');
      statusEl.style.color = '#38bdf8';
      statusEl.innerText = 'Importing rows into WhatsApp database...';

      try {
        const res = await fetch('/api/excel/import', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({raw_text: raw})
        });
        const d = await res.json();
        statusEl.style.color = '#10b981';
        statusEl.innerText = `✅ Successfully imported ${d.imported_groups_count || 0} WhatsApp Groups!`;
        document.getElementById('wa-direct-excel-paste').value = '';
        fetchStats();
        loadWAGroups();
        await loadBulkTargets();
      } catch (e) {
        statusEl.style.color = '#ef4444';
        statusEl.innerText = '❌ Import failed: ' + e;
      }
    }

    async function createCampusEvent() {
      const college = document.getElementById('campus-college-name').value.trim();
      const district = document.getElementById('campus-district').value.trim();
      if (!college) return alert('College name ఎంటర్ చేయండి!');
      if (!district) return alert('District ఎంటర్ చేయండి!');
      const nq = parseInt(document.getElementById('campus-nq').value || '10', 10);
      const level = document.getElementById('campus-level').value || 'easy';
      const subjects = [];
      if (document.getElementById('subj-reasoning')?.checked) subjects.push('reasoning');
      if (document.getElementById('subj-quant')?.checked) subjects.push('quant');
      if (document.getElementById('subj-science')?.checked) subjects.push('science');
      if (document.getElementById('subj-english')?.checked) subjects.push('english');
      if (document.getElementById('subj-ca')?.checked) subjects.push('ca');
      if (document.getElementById('subj-coding')?.checked) subjects.push('coding');
      if (subjects.length === 0) return alert('కనీసం ఒక subject select చేయండి!');

      const card = document.getElementById('campus-active-card');
      card.innerHTML = '<div style="color:#38bdf8;">⏳ Generating exam, link & QR...</div>';
      try {
        const res = await fetch('/api/campus/create', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({college, district, n_q: nq, level, subjects})
        });
        const d = await res.json();
        if (!d.ok) { card.innerHTML = '<div style="color:#ef4444;">❌ ' + (d.error || 'Failed') + '</div>'; return; }
        card.innerHTML = `
          <div style="display:flex; gap:16px; align-items:center; flex-wrap:wrap;">
            <img src="${d.qr}" style="width:150px; height:150px; border-radius:8px; background:white; padding:5px; border:2px solid #10b981;">
            <div style="flex:1; min-width:200px;">
              <div style="font-size:14px; font-weight:800; color:#10b981;">✅ ${d.college} — Exam Ready!</div>
              <div style="margin:6px 0; font-size:12px;">Code: <b style="color:#facc15;">${d.code}</b></div>
              <div style="font-size:11px; word-break:break-all; color:#38bdf8;">${d.link}</div>
              <div style="display:flex; gap:6px; margin-top:8px; flex-wrap:wrap;">
                <button class="btn btn-accent" style="padding:4px 10px; font-size:11px;" onclick="navigator.clipboard.writeText('${d.link}').then(()=>alert('✅ Link copied!'))">📋 Copy Link</button>
                <a href="${d.qr}" target="_blank" class="btn btn-outline" style="padding:4px 10px; font-size:11px; text-decoration:none;">🖼️ Full-Size QR</a>
                <a href="https://wa.me/?text=${encodeURIComponent('🏫 ' + d.college + ' Exam! Join: ' + d.link)}" target="_blank" class="btn btn-purple" style="padding:4px 10px; font-size:11px; text-decoration:none;">📲 Share on WhatsApp</a>
              </div>
            </div>
          </div>`;
        loadCampusEvents();
      } catch (e) {
        card.innerHTML = '<div style="color:#ef4444;">❌ ' + e + '</div>';
      }
    }

    async function viewCampusReport(code) {
      const card = document.getElementById('campus-active-card');
      card.innerHTML = '<div style="color:#38bdf8;">⏳ Loading report for ' + code + '...</div>';
      try {
        const res = await fetch('/api/campus/report?code=' + encodeURIComponent(code));
        const d = await res.json();
        const rep = d.report;
        if (!rep) { card.innerHTML = '<div style="color:#ef4444;">❌ Report not found for ' + code + '</div>'; return; }
        const players = rep.players || rep.top_players || [];
        let rows = players.slice(0, 15).map((pl, i) =>
          `<tr><td style="padding:3px 8px;">${i + 1}</td><td style="padding:3px 8px;"><b>${pl.name || pl.user || '—'}</b></td><td style="padding:3px 8px; color:#38bdf8;">${pl.score ?? pl.points ?? 0}</td></tr>`).join('');
        card.innerHTML = `
          <div style="font-size:14px; font-weight:800; color:#38bdf8;">📋 ${rep.name || code} — Principal Report</div>
          <div style="font-size:12px; color:var(--text-muted); margin:6px 0;">District: ${rep.district || '—'} · Students: <b style="color:#10b981;">${rep.players_count ?? players.length}</b> · Status: ${rep.state || '—'}</div>
          ${rows ? `<table style="width:100%; font-size:12px; border-collapse:collapse; margin-top:6px;"><thead><tr style="color:#64748b;"><th style="text-align:left; padding:3px 8px;">#</th><th style="text-align:left; padding:3px 8px;">Student</th><th style="text-align:left; padding:3px 8px;">Score</th></tr></thead><tbody>${rows}</tbody></table>` : '<div style="font-size:12px; color:#64748b; margin-top:8px;">ఇంకా students join అవ్వలేదు — QR scan చేయగానే ఇక్కడ కనిపిస్తారు.</div>'}`;
      } catch (e) {
        card.innerHTML = '<div style="color:#ef4444;">❌ ' + e + '</div>';
      }
    }

    async function loadCampusEvents() {
      const res = await fetch('/api/campus/list');
      const d = await res.json();
      const tbody = document.querySelector('#table-campus tbody');
      tbody.innerHTML = '';
      (d.events || []).forEach(e => {
        const tr = document.createElement('tr');
        const link = 'https://t.me/' + (d.bot || 'StudentUpBot') + '?start=c' + e.code.replace('CE-', '') + '-1';
        tr.innerHTML = `
          <td><b>${e.code}</b></td>
          <td><b>${e.name}</b></td>
          <td>${e.district}</td>
          <td>${e.n_q} Qs (${e.level})</td>
          <td style="color:#38bdf8; font-weight:700;">${e.players_count} Students</td>
          <td><span class="status-pill ${e.state === 'open' ? 'open' : 'closed'}">${e.state}</span></td>
          <td>
            <a href="${link}" target="_blank" class="btn btn-outline" style="padding:3px 7px; font-size:11px; text-decoration:none;">🔗 Link</a>
            <button class="btn btn-accent" style="padding:3px 7px; font-size:11px; margin-left:4px;" onclick="viewCampusReport('${e.code}')">📋 Report</button>
          </td>
        `;
        tbody.appendChild(tr);
      });
    }

    async function loadBundles() {
      const res = await fetch('/api/bundles');
      const d = await res.json();
      cachedBundles = d.bundles || [];
      const tbody = document.querySelector('#table-bundles tbody');
      if (tbody) {
        tbody.innerHTML = '';
        cachedBundles.forEach(b => {
          const tr = document.createElement('tr');
          const groupCount = (b.target_groups || []).length;
          const chanCount = (b.target_channels || []).length;
          tr.innerHTML = `
            <td><b>${b.name}</b></td>
            <td><span class="category-tag">${b.category}</span></td>
            <td>
              <span style="color:#10b981; font-weight:700;">${groupCount} Groups</span> · 
              <span style="color:#38bdf8; font-weight:700;">${chanCount} Channels</span>
            </td>
            <td>
              <button class="btn btn-purple" style="padding:4px 8px; font-size:11px;" onclick="loadBundleToBulkDispatcher('${b.id}')">🚀 Select in Dispatcher</button>
              <button class="btn btn-outline" style="padding:4px 8px; font-size:11px; margin-left:4px; color:#ef4444;" onclick="deleteBundle('${b.id}')">Delete</button>
            </td>
          `;
          tbody.appendChild(tr);
        });
      }

      // Update bundle dropdown in bulk broadcast tab
      const bSel = document.getElementById('bulk-bundle-selector');
      if (bSel) {
        bSel.innerHTML = '<option value="">-- Choose a Saved Group Bundle --</option>' +
          cachedBundles.map(b => `<option value="${b.id}">${b.name} (${(b.target_groups||[]).length} Groups, ${(b.target_channels||[]).length} Channels)</option>`).join('');
      }

      populateBundleCreatorMembers();
    }

    function populateBundleCreatorMembers() {
      const cont = document.getElementById('bundle-creator-members');
      if (!cont) return;

      const q = (document.getElementById('bundle-member-search')?.value || '').toLowerCase();
      cont.innerHTML = '';

      if (cachedBulkGroups.length === 0 && cachedBulkChannels.length === 0) {
        cont.innerHTML = '<div style="color:var(--text-muted); font-size:11px; text-align:center; padding:10px;">No groups or channels loaded yet.</div>';
        return;
      }

      // Channels section
      cachedBulkChannels.forEach(([key, ch]) => {
        if (q && !ch.name.toLowerCase().includes(q) && !key.toLowerCase().includes(q)) return;
        const div = document.createElement('div');
        div.className = 'bundle-creator-item';
        div.style = 'display:flex; align-items:center; gap:6px; font-size:11px;';
        div.innerHTML = `
          <input type="checkbox" class="bundle-new-ch" value="${key}">
          <span>📢 <b>${ch.name}</b> <span style="color:#64748b;">(TG Channel)</span></span>
        `;
        cont.appendChild(div);
      });

      // Groups section
      cachedBulkGroups.forEach(g => {
        if (q && !g.name.toLowerCase().includes(q) && !(g.jid||'').toLowerCase().includes(q)) return;
        const div = document.createElement('div');
        div.className = 'bundle-creator-item';
        div.style = 'display:flex; align-items:center; gap:6px; font-size:11px;';
        div.innerHTML = `
          <input type="checkbox" class="bundle-new-wa" value="${g.id}">
          <span>💬 <b>${g.name}</b> <span style="color:#10b981; font-weight:700;">[${g.category || 'GENERAL'}]</span></span>
        `;
        cont.appendChild(div);
      });
    }

    function filterBundleCreatorList() {
      populateBundleCreatorMembers();
    }

    function toggleBundleCreatorItems(val) {
      document.querySelectorAll('.bundle-new-ch, .bundle-new-wa').forEach(c => c.checked = val);
    }

    function loadBundleToBulkDispatcher(bid) {
      switchTab('tab-bulk-broadcast');
      const bSel = document.getElementById('bulk-bundle-selector');
      if (bSel) {
        bSel.value = bid;
        applySelectedBundle(bid);
      }
    }

    async function saveNewBundle() {
      const name = document.getElementById('bundle-name').value.trim();
      const cat = document.getElementById('bundle-category').value;
      if (!name) return alert('Enter bundle title');

      const waGids = Array.from(document.querySelectorAll('.bundle-new-wa:checked')).map(c => c.value);
      const chKeys = Array.from(document.querySelectorAll('.bundle-new-ch:checked')).map(c => c.value);

      if (waGids.length === 0 && chKeys.length === 0) {
        return alert('Please select at least one WhatsApp Group or Telegram Channel to include in this bundle!');
      }

      // Conflict warning before bundle creation
      try {
        const cRes = await fetch('/api/whatsapp/check_conflicts', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({target_group_ids: waGids, target_channel_keys: chKeys})
        });
        const cData = await cRes.json();
        if (cData.has_conflicts) {
          const warn = cData.conflicts.map(c => c.message).join('\\n');
          const ok = confirm(`⚠️ Bundle Overlap Notice:\\n${warn}\\n\\nDo you want to save this bundle anyway?`);
          if (!ok) return;
        }
      } catch (e) {
        console.error(e);
      }

      await fetch('/api/bundles/create', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          name: name,
          category: cat,
          group_ids: waGids,
          channel_keys: chKeys
        })
      });

      alert(`✅ Bundle '${name}' created successfully with ${waGids.length} groups and ${chKeys.length} channels!`);
      document.getElementById('bundle-name').value = '';
      toggleBundleCreatorItems(false);
      loadBundles();
      fetchStats();
    }

    async function deleteBundle(bid) {
      if (!confirm('Delete this bundle?')) return;
      await fetch('/api/bundles/delete', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id: bid})
      });
      loadBundles();
      fetchStats();
    }

    async function dispatchBundle(bid, isQuestion) {
      alert('Launching round across bundle: ' + bid);
      switchTab('tab-wa-dispatch');
      startInterleaved(isQuestion);
    }

    function filterTGChannels() {
      const q = (document.getElementById('ch-search-box').value || '').toLowerCase();
      const rows = document.querySelectorAll('#table-channels tbody tr');
      rows.forEach(r => {
        const text = r.innerText.toLowerCase();
        r.style.display = text.includes(q) ? '' : 'none';
      });
    }

    async function loadChannels() {
      const res = await fetch('/api/channels');
      const d = await res.json();
      const tbody = document.querySelector('#table-channels tbody');
      const select = document.getElementById('post-poll-channel');
      tbody.innerHTML = '';
      select.innerHTML = '';
      const counts = d.question_counts || {};

      for (const [key, ch] of Object.entries(d.channels || {})) {
        const count = counts[ch.base_exam || key] || counts[key] || 0;
        const tr = document.createElement('tr');
        const typeBadge = ch.chat_type === 'group'
          ? '<span style="background:#064e3b; color:#6ee7b7; font-size:10px; padding:1px 6px; border-radius:8px; margin-left:4px;">💬 GROUP</span>'
          : '<span style="background:#1e3a5f; color:#7dd3fc; font-size:10px; padding:1px 6px; border-radius:8px; margin-left:4px;">📢 CHANNEL</span>';
        tr.innerHTML = `
          <td><input type="checkbox" class="tg-ch-select-checkbox" data-chkey="${key}"></td>
          <td><b>${key}</b></td>
          <td>${ch.emoji || '🎯'} ${ch.name} ${typeBadge}</td>
          <td><span class="category-tag">${ch.base_exam || key}</span></td>
          <td style="color:#38bdf8; font-weight:700;">${count} Questions</td>
          <td style="font-family:monospace;">${ch.chat_id || ch.username || '—'}</td>
          <td>
            <button class="btn btn-outline" style="padding:3px 7px; font-size:11px;" onclick="quickPostChannel('${key}')">⚡ Post Quiz</button>
          </td>
        `;
        tbody.appendChild(tr);

        const opt = document.createElement('option');
        opt.value = key;
        opt.innerText = (ch.chat_type === 'group' ? '💬 ' : '📢 ') + (ch.emoji || '🎯') + ' ' + ch.name + ' (' + count + ' polls)';
        select.appendChild(opt);
      }
    }

    function selectAllChannels(checked) {
      const cbs = document.querySelectorAll('.tg-ch-select-checkbox');
      cbs.forEach(cb => cb.checked = checked);
      const master = document.getElementById('ch-select-all');
      if (master) master.checked = checked;
    }

    function getSelectedChannelKeys() {
      const cbs = document.querySelectorAll('.tg-ch-select-checkbox:checked');
      return Array.from(cbs).map(cb => cb.getAttribute('data-chkey'));
    }

    async function quickPostChannel(key) {
      const log = document.getElementById('tg-poll-log');
      log.innerText = 'Posting 1 poll to ' + key + '...';
      const res = await fetch('/api/post_poll', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({channel: key, count: 1})
      });
      const d = await res.json();
      log.innerText = d.message || 'Poll dispatched!';
      loadChannels();
      fetchStats();
    }

    async function dispatchSelectedChannels() {
      const keys = getSelectedChannelKeys();
      if (!keys || keys.length === 0) {
        return alert('Please select at least 1 channel using the checkboxes!');
      }
      if (!confirm(`Post exam quiz polls to ${keys.length} selected channel(s)?`)) return;

      const log = document.getElementById('tg-poll-log');
      log.innerText = `Dispatching polls across ${keys.length} channels...`;
      let okCount = 0;
      for (const k of keys) {
        const res = await fetch('/api/post_poll', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({channel: k, count: 1})
        });
        const d = await res.json();
        if (d.ok) okCount++;
      }
      log.innerText = `✅ Successfully posted polls across ${okCount} / ${keys.length} channels!`;
      alert(`✅ Successfully posted polls across ${okCount} channels!`);
      loadChannels();
      fetchStats();
    }

    async function createNewChannel() {
      const name = document.getElementById('new-ch-name').value.trim();
      const base = document.getElementById('new-ch-base').value;
      const chatid = document.getElementById('new-ch-chatid').value.trim();
      const chtype = (document.getElementById('new-ch-type') || {value:'channel'}).value;
      if (!name) return alert('Enter channel or exam name');

      const res = await fetch('/api/channels/register', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name, exam_type: base, chat_id: chatid, chat_type: chtype})
      });
      const d = await res.json();
      alert(d.message || ((chtype === 'group' ? 'Group' : 'Channel') + ' registered: ' + d.channel.name));
      document.getElementById('new-ch-name').value = '';
      document.getElementById('new-ch-chatid').value = '';
      loadChannels();
      fetchStats();
    }

    async function detectNewTelegramChats() {
      const box = document.getElementById('tg-detect-result');
      box.innerHTML = '<span style="color:#fbbf24;">🔍 Scanning Telegram for groups/channels where bot was added...</span>';
      try {
        const res = await fetch('/api/channels/detect_new', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: '{}'
        });
        const d = await res.json();
        if (!d.ok) {
          box.innerHTML = '<span style="color:#f87171;">❌ ' + (d.error || 'Detection failed') + '</span>';
          return;
        }
        if (!d.added || d.added.length === 0) {
          box.innerHTML = '<span style="color:#94a3b8;">Scanned ' + (d.scanned || 0) + ' chat(s) — కొత్తవి ఏమీ లేవు. ' + (d.note || '') + '</span>';
          return;
        }
        box.innerHTML = '<span style="color:#34d399;">✅ ' + d.added.length + ' కొత్త target(s) registered: ' +
          d.added.map(function(a){ return (a.chat_type === 'group' ? '💬 ' : '📢 ') + a.name; }).join(', ') + '</span>';
        loadChannels();
        fetchStats();
      } catch (e) {
        box.innerHTML = '<span style="color:#f87171;">❌ ' + e + '</span>';
      }
    }

    async function sendChannelPoll(count) {
      const ch = document.getElementById('post-poll-channel').value;
      const log = document.getElementById('tg-poll-log');
      log.innerText = 'Generating and posting ' + count + ' poll(s) for ' + ch + '...';
      const res = await fetch('/api/post_poll', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({channel: ch, count: count || 1})
      });
      const d = await res.json();
      log.innerText = d.message || JSON.stringify(d);
    }

    async function triggerWar(act, mins) {
      const box = document.getElementById('war-result');
      box.innerText = 'Triggering War ' + act + '...';
      const res = await fetch('/api/war', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({act, mins: mins || 5})
      });
      const d = await res.json();
      box.innerText = d.message || JSON.stringify(d);
    }

    async function syncSheet(act) {
      const box = document.getElementById('sheet-result');
      box.innerText = 'Syncing Google Sheet...';
      const res = await fetch('/api/sheet', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({act})
      });
      const d = await res.json();
      box.innerText = d.message || JSON.stringify(d);
    }

    async function loadSquads() {
      const res = await fetch('/api/squads');
      const d = await res.json();
      const tbody = document.querySelector('#table-squads tbody');
      tbody.innerHTML = '';
      if (!d.squads || Object.keys(d.squads).length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--text-muted); padding:16px;">No squads created yet. Click "Create Squad" above!</td></tr>';
        return;
      }
      for (const [code, s] of Object.entries(d.squads)) {
        const tr = document.createElement('tr');
        const link = 'https://t.me/' + (d.bot || 'StudentUpBot') + '?start=sq_' + code;
        const qrUrl = 'https://api.qrserver.com/v1/create-qr-code/?size=600x600&data=' + encodeURIComponent(link);
        const memCount = (s.members || []).length;
        const membersList = (s.members || []).join(', ') || s.leader;

        tr.innerHTML = `
          <td><b style="color:#38bdf8; font-size:14px;">SQ-${code}</b></td>
          <td><b>${s.name}</b></td>
          <td>${s.leader}</td>
          <td><span style="font-weight:700; color:${memCount >= 5 ? '#10b981' : '#f59e0b'};">${memCount} / 10 Members</span></td>
          <td style="font-size:11px; color:var(--text-muted); max-width:200px; overflow:hidden; text-overflow:ellipsis;">${membersList}</td>
          <td>
            <a href="${link}" target="_blank" class="btn btn-outline" style="padding:3px 8px; font-size:11px; text-decoration:none;">🔗 Join Link</a>
            <button class="btn btn-accent" style="padding:3px 8px; font-size:11px; margin-left:4px;" onclick="viewSquadModal('${code}', '${s.name.replace(/'/g, "\\'")}', '${link}', '${qrUrl}', '${s.leader}')">📱 View Scannable QR</button>
          </td>
        `;
        tbody.appendChild(tr);
      }
    }

    function viewSquadModal(code, name, link, qr, leader) {
      const modal = document.getElementById('squad-active-modal');
      modal.style.display = 'block';
      modal.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:12px;">
          <div>
            <h3 style="color:#38bdf8; font-size:16px;">👥 Squad: ${name} (Code: SQ-${code})</h3>
            <div style="font-size:12px; color:var(--text-muted); margin-top:2px;">Leader: <b>${leader}</b> · Live One-Tap Telegram Join Link & Projector QR Code</div>
          </div>
          <button class="btn btn-outline" style="padding:4px 10px; font-size:11px;" onclick="document.getElementById('squad-active-modal').style.display='none'">✕ Close</button>
        </div>
        <div style="display:flex; gap:20px; align-items:center; flex-wrap:wrap; background:#050811; padding:16px; border-radius:8px; border:1px solid rgba(255,255,255,0.06);">
          <img src="${qr}" style="width:160px; height:160px; border-radius:8px; border:2px solid #38bdf8; background:white; padding:4px;">
          <div>
            <div style="font-size:13px; margin-bottom:8px;"><b>One-Tap Student Link:</b> <a href="${link}" target="_blank" style="color:#10b981;">${link}</a></div>
            <div style="font-size:12px; color:var(--text-muted); line-height:1.6; max-width:400px;">
              ఈ QR కోడ్ లేదా లింక్‌ను వాట్సాప్ గ్రూపులలో లేదా కాలేజీ ప్రొజెక్టర్‌పై షేర్ చేయండి. విద్యార్థులు ఒక్క ట్యాప్‌తో మీ స్క్వాడ్‌లో చేరవచ్చు!
            </div>
          </div>
        </div>
      `;
      modal.scrollIntoView({behavior: 'smooth'});
    }

    async function addStudentToSquad() {
      const code = (document.getElementById('join-squad-code').value || '').trim().toUpperCase();
      const uid = (document.getElementById('join-squad-uid').value || '').trim();
      const log = document.getElementById('join-squad-log');
      if (!code || !uid) return alert('Enter Squad Code and Student Mobile / Telegram ID');

      try {
        const res = await fetch('/api/squads/join', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({code, uid})
        });
        const d = await res.json();
        if (d.ok) {
          log.style.color = '#10b981';
          log.innerText = `✅ Added ${uid} to Squad SQ-${code}!`;
          document.getElementById('join-squad-uid').value = '';
          loadSquads();
        } else {
          log.style.color = '#ef4444';
          log.innerText = '❌ Failed: ' + (d.message || 'Error');
        }
      } catch (e) {
        log.style.color = '#ef4444';
        log.innerText = '❌ Error: ' + e;
      }
    }

    async function loadMembers() {
      const res = await fetch('/api/members');
      const d = await res.json();
      const tbody = document.querySelector('#table-members tbody');
      tbody.innerHTML = '';
      if (!d.members || d.members.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color:var(--text-muted); padding:16px;">No registered members yet. Use the Quick Register box above!</td></tr>';
        return;
      }
      for (const m of d.members.slice(0, 100)) {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td style="font-family:monospace;">${m.uid}</td>
          <td><b>${m.name}</b></td>
          <td>${m.district || '—'}</td>
          <td><span class="category-tag">${m.exam || '—'}</span></td>
          <td style="color:var(--warning); font-weight:800; font-size:14px;">🏆 ${m.points}</td>
          <td>🔥 ${m.streak || 1}d</td>
          <td>${m.college || '—'}</td>
          <td>
            <button class="btn btn-outline" style="padding:2px 7px; font-size:11px;" onclick="addStudentPoints('${m.uid}', 10)">+10 Pts</button>
            <button class="btn btn-outline" style="padding:2px 7px; font-size:11px;" onclick="addStudentPoints('${m.uid}', 50)">+50 Pts</button>
          </td>
        `;
        tbody.appendChild(tr);
      }
    }

    async function quickRegisterStudent() {
      const uid = document.getElementById('reg-student-uid').value.trim();
      const name = document.getElementById('reg-student-name').value.trim();
      const dist = document.getElementById('reg-student-dist').value;
      const exam = document.getElementById('reg-student-exam').value;
      const pts = parseInt(document.getElementById('reg-student-pts').value) || 50;
      const log = document.getElementById('reg-student-log');

      if (!uid || !name) return alert('Enter Telegram ID / Mobile and Student Name');

      try {
        const res = await fetch('/api/members/register', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({uid, name, district: dist, exam, points: pts})
        });
        const d = await res.json();
        if (d.ok) {
          log.style.color = '#10b981';
          log.innerText = `✅ Registered ${name}! Awarded ${pts} initial points.`;
          document.getElementById('reg-student-uid').value = '';
          document.getElementById('reg-student-name').value = '';
          loadMembers();
          fetchStats();
        }
      } catch (e) {
        log.style.color = '#ef4444';
        log.innerText = '❌ Failed: ' + e;
      }
    }

    async function addStudentPoints(uid, pts) {
      try {
        const res = await fetch('/api/members/add_points', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({uid, points: pts})
        });
        const d = await res.json();
        if (d.ok) {
          loadMembers();
          fetchStats();
        }
      } catch (e) {
        alert('Error: ' + e);
      }
    }

    async function createDashboardSquad() {
      const name = document.getElementById('new-squad-name').value.trim();
      const leader = document.getElementById('new-squad-leader').value.trim();
      if (!name) return alert('Enter Squad Name');
      try {
        const res = await fetch('/api/squads/create', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({name, leader: leader || 'Admin'})
        });
        const d = await res.json();
        if (d.ok) {
          alert('🎉 Squad Created! Code: SQ-' + d.code);
          document.getElementById('new-squad-name').value = '';
          document.getElementById('new-squad-leader').value = '';
          loadSquads();
        } else {
          alert('Failed to create squad: ' + (d.message || 'Unknown error'));
        }
      } catch (e) {
        alert('Error: ' + e);
      }
    }

    fetchStats();
    loadWASession();
    loadWAGroups();
    loadSchedules();
    loadChannels();
    loadBundles();
    loadGapSettings();
    loadBulkTargets();
    setInterval(fetchStats, 10000);
    setInterval(pollPipelineStatus, 1500);
    setInterval(loadWASession, 10000);
  </script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    # ---------------- 🔒 access lock helpers ----------------
    def _cookie_token(self) -> str:
        raw = self.headers.get("Cookie", "") or ""
        for part in raw.split(";"):
            k, _, v = part.strip().partition("=")
            if k == "su_auth":
                return v.strip()
        return ""

    def _authed(self) -> bool:
        tok = self._cookie_token()
        return bool(tok) and tok in _load_auth().get("tokens", [])

    # ---------------- 🛡️ IP ALLOWLIST (2nd security layer) ----------------
    def _client_ip(self) -> str:
        """Real visitor IP. Behind the preview proxy the trusted proxy APPENDS
        the real client IP to X-Forwarded-For — so take the LAST entry
        (first entries can be spoofed by the client)."""
        xff = (self.headers.get("X-Forwarded-For", "") or "").strip()
        if xff:
            return xff.split(",")[-1].strip()
        return self.client_address[0]

    def _ip_allowed(self) -> bool:
        if os.environ.get("DISABLE_IP_LOCK") == "1":
            return True  # emergency override: restart server with DISABLE_IP_LOCK=1
        sec = _load_auth()
        if not sec.get("ip_lock_enabled"):
            return True
        allowed = [str(a).strip() for a in (sec.get("allowed_ips") or []) if str(a).strip()]
        if not allowed:
            return True
        # sandbox-local failsafe: direct loopback requests (no proxy header) always pass
        xff = (self.headers.get("X-Forwarded-For", "") or "").strip()
        if not xff and self.client_address[0] in ("127.0.0.1", "::1", "localhost"):
            return True
        ip = self._client_ip()
        import ipaddress
        try:
            ipobj = ipaddress.ip_address(ip)
        except ValueError:
            ipobj = None
        for e in allowed:
            if e == ip:
                return True
            if (e.endswith(".") or e.endswith(":")) and ip.startswith(e):
                return True  # prefix rule e.g. "49.37." matches whole mobile range
            if "/" in e and ipobj is not None:
                try:
                    if ipobj in ipaddress.ip_network(e, strict=False):
                        return True
                except ValueError:
                    pass
        return False

    def _deny_ip(self, is_api: bool):
        ip = self._client_ip()
        if is_api:
            self._send_json({"ok": False, "error": f"access denied — your IP {ip} is not in the allowlist"}, code=403)
            return
        body = ("<!DOCTYPE html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
                "<title>403 — Access Denied</title></head>"
                "<body style='background:#0b1220; color:#e2e8f0; font-family:sans-serif; display:flex; align-items:center; justify-content:center; height:100vh; margin:0;'>"
                "<div style='text-align:center; max-width:420px; padding:24px;'>"
                "<div style='font-size:52px;'>🛡️</div>"
                "<h2 style='color:#f87171;'>Access Denied</h2>"
                f"<p style='color:#94a3b8;'>Your IP <b style='color:#fbbf24;'>{ip}</b> is not in the admin allowlist.</p>"
                "<p style='color:#64748b; font-size:13px;'>ఈ dashboard కొన్ని IP addresses కి మాత్రమే open అవుతుంది. Admin ని సంప్రదించండి.</p>"
                "</div></body></html>").encode("utf-8")
        self.send_response(403)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


    def _deny(self, is_api: bool):
        if is_api:
            self._send_json({"ok": False, "error": "unauthorized — login required"}, code=401)
        else:
            body = LOGIN_PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def _issue_login_cookie(self):
        auth = _load_auth()
        tok = _secrets.token_hex(24)
        auth.setdefault("tokens", []).append(tok)
        auth["tokens"] = auth["tokens"][-25:]  # keep last 25 sessions
        _save_auth(auth)
        body = json.dumps({"ok": True}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Set-Cookie", f"su_auth={tok}; Path=/; Max-Age=2592000; HttpOnly; SameSite=Lax")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)

        # 🛡️ IP allowlist — checked BEFORE everything (even the login page)
        if not self._ip_allowed():
            self._deny_ip(is_api=p.path.startswith("/api/"))
            return

        # 🔒 Access lock: everything requires login except the login page itself
        if p.path == "/login":
            self._deny(is_api=False)
            return
        if not self._authed():
            self._deny(is_api=p.path.startswith("/api/"))
            return

        if p.path in ("/", "/index.html", "/dashboard"):
            self._send_html(HTML_PAGE)
            return

        if p.path == "/api/history":
            from core import broadcast_log
            self._send_json({
                "ok": True,
                "summary": broadcast_log.get_summary(),
                "history": broadcast_log.get_history(limit=80),
            })
            return

        if p.path == "/api/health":
            # 🩺 MISSION CONTROL: whole-system health in one call
            from core.telegram import Telegram
            from core import broadcast_log
            jobs = whatsapp_pipeline.get_scheduled_jobs()
            enabled_jobs = [j for j in jobs if j.get("enabled")]
            bank = Bank()
            stats = bank.stats()
            # only channels that actually have questions, sorted by fresh stock
            stock = sorted(
                [{"channel": ch, **st} for ch, st in stats.items() if st.get("total", 0) > 0],
                key=lambda r: r["unused"],
            )
            low = [r for r in stock if r["unused"] < 15]
            up_min = int((time.time() - _START_TS) // 60)
            sec = _load_auth()
            self._send_json({
                "ok": True,
                "telegram_live": bool(Telegram().token),
                "whatsapp_connected": whatsapp_pipeline.bridge_is_connected(),
                "scheduler_running": bool(getattr(whatsapp_pipeline, "_SCHEDULER_RUNNING", False)),
                "autopilot_slots": len([j for j in enabled_jobs if j.get("mode") == "tg"]),
                "wa_slots": len([j for j in enabled_jobs if j.get("mode", "wa") != "tg"]),
                "total_fresh": sum(r["unused"] for r in stock),
                "total_questions": sum(r["total"] for r in stock),
                "low_stock": low[:10],
                "stock": stock,
                "ip_lock_on": bool(sec.get("ip_lock_enabled")),
                "uptime_min": up_min,
                "week_polls": broadcast_log.get_summary().get("week_polls", 0),
                "last_backup": __import__("core.backup", fromlist=["backup"]).last_backup_info(),
            })
            return

        if p.path == "/api/questions/search":
            # 🔍 QUESTION FINDER: live search across the whole bank
            qs = urllib.parse.parse_qs(p.query)
            term = (qs.get("q", [""])[0] or "").strip().lower()
            limit = min(int(qs.get("limit", ["30"])[0] or 30), 100)
            bank = Bank()
            results = []
            for q in bank.questions:
                if term:
                    hay = " ".join([
                        str(q.get("q_en", "")), str(q.get("q_te", "")),
                        str(q.get("topic", "")), str(q.get("channel", "")),
                        str(q.get("id", "")),
                    ]).lower()
                    if term not in hay:
                        continue
                ch = q.get("channel", "CURRENT")
                results.append({
                    "id": q.get("id"),
                    "channel": ch,
                    "topic": q.get("topic", ""),
                    "q_en": str(q.get("q_en", ""))[:160],
                    "options": len(q.get("options_en", []) or []),
                    "fresh": q.get("id") not in set(bank.used.get(ch, [])),
                })
                if len(results) >= limit:
                    break
            self._send_json({"ok": True, "count": len(results), "results": results})
            return

        if p.path == "/api/backup":
            # 💾 ONE-CLICK FULL BACKUP: every data json/csv zipped & downloaded
            import io, zipfile
            buf = io.BytesIO()
            added = 0
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for f in sorted(config.DATA.glob("*")):
                    if f.is_file() and f.suffix.lower() in (".json", ".csv", ".xlsx") and f.stat().st_size < 8_000_000:
                        try:
                            z.write(f, f"studentup_backup/{f.name}")
                            added += 1
                        except Exception:
                            pass
            data = buf.getvalue()
            fname = "studentup_backup_" + datetime.now().strftime("%Y%m%d_%H%M") + ".zip"
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if p.path == "/api/security":
            sec = _load_auth()
            self._send_json({
                "ok": True,
                "ip_lock_enabled": bool(sec.get("ip_lock_enabled")),
                "allowed_ips": sec.get("allowed_ips", []),
                "your_ip": self._client_ip(),
                "recent_logins": _recent_logins(8),
            })
            return

        if p.path == "/api/stats":
            mb = Members()
            st_war = districtwar.lobby_status()
            reg = [m for m in mb.members.values() if m.get("registered")]
            tot_pts = sum(m.get("points", 0) for m in mb.members.values())
            wa = whatsapp_pipeline.load_wa_registry()
            all_ch = channel_router.get_all_channels()
            bundles = bundle_manager.load_bundles().get("bundles", [])
            bank = Bank()

            self._send_json({
                "total_members": len(mb.members),
                "registered_members": len(reg),
                "total_points": tot_pts,
                "war_status": st_war,
                "wa_groups_count": len(wa.get("groups", [])),
                "channels_count": len(all_ch),
                "bundles_count": len(bundles),
                "total_questions": len(bank.questions)
            })
            return

        if p.path == "/api/whatsapp/groups":
            self._send_json(whatsapp_pipeline.load_wa_registry())
            return

        if p.path == "/api/whatsapp/session":
            self._send_json(whatsapp_pipeline.get_session_info())
            return

        if p.path == "/api/whatsapp/schedules":
            self._send_json({"jobs": whatsapp_pipeline.get_scheduled_jobs()})
            return

        if p.path == "/api/whatsapp/pipeline_status":
            self._send_json(whatsapp_pipeline.get_broadcast_status())
            return

        if p.path == "/api/channels":
            bank = Bank()
            counts = {}
            for q in bank.questions:
                c = q.get("channel", "UNKNOWN")
                counts[c] = counts.get(c, 0) + 1

            self._send_json({
                "channels": channel_router.get_all_channels(),
                "question_counts": counts
            })
            return

        if p.path == "/api/campus/list":
            d = campus._load()
            events = []
            for c, e in d.get("events", {}).items():
                events.append({
                    "code": c,
                    "name": e.get("name", ""),
                    "district": e.get("district", ""),
                    "colleges": e.get("colleges", []),
                    "n_q": e.get("n_q", 10),
                    "level": e.get("level", "easy"),
                    "state": e.get("state", "open"),
                    "players_count": len(e.get("players", {}))
                })
            self._send_json({
                "bot": config.BOT_USERNAME or "StudentUpBot",
                "events": events
            })
            return

        if p.path == "/api/campus/report":
            query = urllib.parse.parse_qs(p.query)
            code = query.get("code", [""])[0]
            rep = campus.college_report(code)
            self._send_json({"ok": True, "report": rep})
            return

        if p.path == "/api/bundles":
            self._send_json(bundle_manager.load_bundles())
            return

        if p.path == "/api/squads":
            sq_data = hooks._sq()
            self._send_json({
                "bot": config.BOT_USERNAME or "StudentUpBot",
                "squads": sq_data.get("squads", {})
            })
            return

        if p.path == "/api/excel/template":
            tmpl_path = config.DATA / "sample_whatsapp_groups_template.csv"
            if not tmpl_path.exists():
                sample_data = (
                    "Group Name,Link or JID,Category,Shift,Group Type\n"
                    "Warangal TS Police SI & Constable Batch,https://chat.whatsapp.com/sample_police_warangal,POLICE,MORNING,EXAM_SPECIFIC\n"
                    "Guntur AP DSC SGT Aspirants 2026,https://chat.whatsapp.com/sample_dsc_guntur,TET_DSC,ALL_DAY,EXAM_SPECIFIC\n"
                    "Telangana Group 1 2 3 State Service Hub,https://chat.whatsapp.com/sample_tspsc_state,TSPSC,ALL_DAY,EXAM_SPECIFIC\n"
                    "Andhra Pradesh APPSC Group 2 & 4 Warriors,https://chat.whatsapp.com/sample_appsc_state,APPSC,ALL_DAY,EXAM_SPECIFIC\n"
                    "TS 10th Class SSC Board 2026 Toppers,https://chat.whatsapp.com/sample_ts_10th,TS_10TH,ALL_DAY,EXAM_SPECIFIC\n"
                    "AP 10th Class BSEAP Board Exam Prep,https://chat.whatsapp.com/sample_ap_10th,AP_10TH,ALL_DAY,EXAM_SPECIFIC\n"
                    "TS Intermediate MPC & BiPC Study Circle,https://chat.whatsapp.com/sample_ts_inter,TS_INTER,MORNING,EXAM_SPECIFIC\n"
                    "AP Intermediate BIEAP & EAPCET Network,https://chat.whatsapp.com/sample_ap_inter,AP_INTER,MORNING,EXAM_SPECIFIC\n"
                    "TS Diploma SBTET & POLYCET Circle,https://chat.whatsapp.com/sample_ts_diploma,TS_DIPLOMA,ALL_DAY,EXAM_SPECIFIC\n"
                    "AP Diploma SBTET Polytechnic & ECET Hub,https://chat.whatsapp.com/sample_ap_diploma,AP_DIPLOMA,ALL_DAY,EXAM_SPECIFIC\n"
                    "TS Degree Colleges (B.Com/B.Sc/B.A) Forum,https://chat.whatsapp.com/sample_ts_degree,TS_DEGREE,EVENING,EXAM_SPECIFIC\n"
                    "AP Degree Colleges AU & SVU Students Union,https://chat.whatsapp.com/sample_ap_degree,AP_DEGREE,EVENING,EXAM_SPECIFIC\n"
                    "TS B.Tech Engineering & Placement Hub,https://chat.whatsapp.com/sample_ts_btech,TS_BTECH,EVENING,EXAM_SPECIFIC\n"
                    "AP B.Tech JNTUK & JNTUA Placements,https://chat.whatsapp.com/sample_ap_btech,AP_BTECH,EVENING,EXAM_SPECIFIC\n"
                    "TS & AP ITI Electrician & Fitter Forum,https://chat.whatsapp.com/sample_iti_students,ITI_ALL,ALL_DAY,EXAM_SPECIFIC\n"
                    "Dr BR Ambedkar Open University BRAOU Network,https://chat.whatsapp.com/sample_braou_univ,OPEN_UNIV,ALL_DAY,EXAM_SPECIFIC\n"
                    "SSC CGL / CHSL / MTS Central Exam Prep,https://chat.whatsapp.com/sample_ssc_central,SSC,MORNING,EXAM_SPECIFIC\n"
                    "Railway RRB NTPC & Group D Warriors,https://chat.whatsapp.com/sample_rrb_railway,RAILWAY,MORNING,EXAM_SPECIFIC\n"
                    "State Bank SBI PO & IBPS Clerk Circle,https://chat.whatsapp.com/sample_banking_sbi,BANKING,MORNING,EXAM_SPECIFIC\n"
                    "Telangana & AP General Study Circle,https://chat.whatsapp.com/sample_general_circle,CURRENT,ALL_DAY,GENERAL\n"
                )
                tmpl_path.write_text(sample_data, encoding="utf-8")
            
            content = tmpl_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="studentup_sample_whatsapp_groups.csv"')
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        if p.path == "/api/members":
            mb = Members()
            arr = []
            for uid, m in sorted(mb.members.items(), key=lambda kv: -kv[1].get("points", 0)):
                arr.append({
                    "uid": uid,
                    "name": m.get("name") or "Player",
                    "district": m.get("district", ""),
                    "exam": m.get("exam", ""),
                    "points": m.get("points", 0),
                    "streak": m.get("streak", 0),
                    "college": m.get("college", "")
                })
            self._send_json({"members": arr})
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        p = urllib.parse.urlparse(self.path)

        # 🛡️ IP allowlist — checked BEFORE everything (even login attempts)
        if not self._ip_allowed():
            self._deny_ip(is_api=True)
            return

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

        # 🔒 Access lock
        if p.path == "/api/auth/login":
            pw = str(body.get("password", ""))
            if pw and pw == _dash_password():
                _log_login_attempt(self._client_ip(), True)
                self._issue_login_cookie()
            else:
                _log_login_attempt(self._client_ip(), False)
                time.sleep(1.2)  # slow brute-force attempts
                self._send_json({"ok": False, "error": "wrong password"}, code=401)
            return
        if not self._authed():
            self._send_json({"ok": False, "error": "unauthorized — login required"}, code=401)
            return

        if p.path == "/api/auth/logout":
            auth = _load_auth()
            tok = self._cookie_token()
            auth["tokens"] = [t for t in auth.get("tokens", []) if t != tok]
            _save_auth(auth)
            self._send_json({"ok": True, "message": "logged out"})
            return

        if p.path == "/api/auth/change_password":
            old = str(body.get("old", ""))
            new = str(body.get("new", "")).strip()
            if old != _dash_password():
                self._send_json({"ok": False, "error": "current password is wrong"})
                return
            if len(new) < 6:
                self._send_json({"ok": False, "error": "new password must be at least 6 characters"})
                return
            auth = _load_auth()
            auth["password"] = new
            auth["tokens"] = [self._cookie_token()]  # kick every other session
            _save_auth(auth)
            self._send_json({"ok": True, "message": "password changed — other sessions logged out"})
            return

        if p.path == "/api/security/update":
            enabled = bool(body.get("ip_lock_enabled"))
            raw_ips = body.get("allowed_ips", [])
            if isinstance(raw_ips, str):
                raw_ips = raw_ips.replace(",", " ").split()
            ips, bad = [], []
            import ipaddress
            for e in raw_ips:
                e = str(e).strip()
                if not e:
                    continue
                valid = False
                try:
                    ipaddress.ip_address(e)
                    valid = True
                except ValueError:
                    if "/" in e:
                        try:
                            ipaddress.ip_network(e, strict=False)
                            valid = True
                        except ValueError:
                            pass
                    elif e.endswith(".") or e.endswith(":"):
                        valid = True  # prefix rule like "49.37."
                if valid:
                    if e not in ips:
                        ips.append(e)
                else:
                    bad.append(e)
            if bad:
                self._send_json({"ok": False, "error": "Invalid entries: " + ", ".join(bad) + " — valid formats: 49.37.12.34 | 49.37. | 49.37.0.0/16"})
                return

            note = ""
            my_ip = self._client_ip()
            if enabled and ips:
                # 🚨 LOCKOUT GUARD: never let the admin lock THEMSELVES out.
                xff = (self.headers.get("X-Forwarded-For", "") or "").strip()
                is_local = (not xff) and self.client_address[0] in ("127.0.0.1", "::1")
                if not is_local:
                    try:
                        ipobj = ipaddress.ip_address(my_ip)
                    except ValueError:
                        ipobj = None
                    matched = any(
                        e == my_ip
                        or ((e.endswith(".") or e.endswith(":")) and my_ip.startswith(e))
                        or ("/" in e and ipobj is not None and ipobj in ipaddress.ip_network(e, strict=False))
                        for e in ips
                    )
                    if not matched:
                        ips.append(my_ip)
                        note = f"మీ current IP {my_ip} list లో లేదు — lockout కాకుండా auto-add చేశాం."
            if enabled and not ips:
                enabled = False
                note = "Allowlist ఖాళీగా ఉంది — lock OFF చేశాం (ఖాళీ list తో అందరూ block అవుతారు)."

            auth = _load_auth()
            auth["ip_lock_enabled"] = enabled
            auth["allowed_ips"] = ips
            _save_auth(auth)
            self._send_json({"ok": True, "ip_lock_enabled": enabled, "allowed_ips": ips,
                             "your_ip": my_ip, "note": note,
                             "message": ("🛡️ IP Lock ON — only " + str(len(ips)) + " allowed IP rule(s)") if enabled else "🔓 IP Lock OFF — password-only protection"})
            return

        if p.path == "/api/members/register":
            uid = str(body.get("uid", "")).strip()
            name = body.get("name", "").strip()
            district = body.get("district", "Warangal").strip()
            exam = body.get("exam", "POLICE").strip()
            pts = int(body.get("points", 50))
            
            mb = Members()
            m = mb.register(uid, name=name, exam=exam, district=district)
            m["points"] = m.get("points", 0) + pts
            mb.kv.save()
            self._send_json({"ok": True, "uid": uid, "points": m["points"]})
            return

        if p.path == "/api/members/add_points":
            uid = str(body.get("uid", "")).strip()
            pts = int(body.get("points", 10))
            mb = Members()
            if uid in mb.members:
                mb.members[uid]["points"] = mb.members[uid].get("points", 0) + pts
                mb.kv.save()
                self._send_json({"ok": True, "uid": uid, "points": mb.members[uid]["points"]})
            else:
                self._send_json({"ok": False, "message": "User not found"})
            return

        if p.path == "/api/campus/create":
            college = body.get("college", "College").strip()
            district = body.get("district", "District").strip()
            nq = int(body.get("n_q", 10))
            lvl = body.get("level", "easy")
            subjs = body.get("subjects", ["reasoning", "quant", "science", "english", "ca"])
            code = campus.quick_event(college, district, n_q=nq, level=lvl, subjects=subjs)

            bot = getattr(config, "BOT_USERNAME", "") or "StudentUpBot"
            link = f"https://t.me/{bot}?start=c{code.replace('CE-', '')}-1"
            qr = f"https://api.qrserver.com/v1/create-qr-code/?size=600x600&data={link}"

            self._send_json({
                "ok": True,
                "code": code,
                "college": college,
                "link": link,
                "qr": qr
            })
            return

        if p.path == "/api/squads/create":
            name = body.get("name", "Squad").strip()
            leader = body.get("leader", "Admin").strip()
            # Generate 4-letter squad code
            import random, string
            letters = string.ascii_uppercase
            sq_data = hooks._sq()
            code = "".join(random.choice(letters) for _ in range(4))
            while code in sq_data.get("squads", {}):
                code = "".join(random.choice(letters) for _ in range(4))

            sq_data.setdefault("squads", {})[code] = {
                "code": code,
                "name": name,
                "leader": leader,
                "members": [leader],
                "created": datetime.now().isoformat()
            }
            sq_data.setdefault("by_uid", {})[leader] = code
            hooks.save_json_atomic(hooks.SQUADS_PATH, sq_data)

            bot = getattr(config, "BOT_USERNAME", "") or "StudentUpBot"
            link = f"https://t.me/{bot}?start=sq_{code}"
            qr = f"https://api.qrserver.com/v1/create-qr-code/?size=600x600&data={link}"

            self._send_json({
                "ok": True,
                "code": code,
                "name": name,
                "link": link,
                "qr": qr
            })
            return

        if p.path == "/api/squads/join":
            code = body.get("code", "").strip().upper()
            uid = str(body.get("uid", "")).strip()
            sq_data = hooks._sq()
            
            clean_code = code.replace("SQ-", "").strip()
            if clean_code not in sq_data.get("squads", {}):
                self._send_json({"ok": False, "message": f"Squad SQ-{clean_code} not found"})
                return

            sq = sq_data["squads"][clean_code]
            if uid not in sq.get("members", []):
                sq.setdefault("members", []).append(uid)
                sq_data.setdefault("by_uid", {})[uid] = clean_code
                hooks.save_json_atomic(hooks.SQUADS_PATH, sq_data)

            self._send_json({
                "ok": True,
                "code": clean_code,
                "name": sq["name"],
                "members_count": len(sq["members"]),
                "members": sq["members"]
            })
            return

        if p.path == "/api/excel/inspect":
            b64 = body.get("file_b64", "")
            fname = body.get("filename", "workbook.xlsx")
            if not b64:
                self._send_json({"ok": False, "error": "No file data received"})
                return
            try:
                raw_bytes = base64.b64decode(b64)
                sheets_info = bundle_manager.inspect_xlsx_sheets_bytes(raw_bytes)
                self._send_json({"ok": True, "filename": fname, "sheets": sheets_info})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)})
            return

        if p.path == "/api/excel/import_selected":
            b64 = body.get("file_b64", "")
            sel_sheets = body.get("sheets", [])
            if not b64 or not sel_sheets:
                self._send_json({"ok": False, "error": "Missing file or selected sheets"})
                return
            try:
                raw_bytes = base64.b64decode(b64)
                res = bundle_manager.import_from_multisheet_excel(raw_bytes, sel_sheets)
                self._send_json(res)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)})
            return

        if p.path == "/api/broadcast/dispatch":
            msg = body.get("message", "")
            att_url = body.get("attachment_url", "")
            att_b64 = body.get("attachment_data_b64", "")
            att_fname = body.get("attachment_filename", "")
            ch_keys = body.get("target_channel_keys", [])
            g_ids = body.get("target_group_ids", [])
            gw = body.get("gateway_url", "")

            res = bundle_manager.dispatch_bulk_broadcast(
                message=msg,
                attachment_url=att_url,
                attachment_data_b64=att_b64,
                attachment_filename=att_fname,
                target_group_ids=g_ids,
                target_channel_keys=ch_keys,
                gateway_url=gw
            )
            self._send_json(res)
            return

        if p.path == "/api/excel/import":
            raw_text = body.get("raw_text", "")
            res = bundle_manager.import_from_csv_or_excel_text(raw_text)
            self._send_json(res)
            return

        if p.path == "/api/bundles/create":
            name = body.get("name", "Cluster Bundle")
            cat = body.get("category", "POLICE")
            gids = body.get("group_ids", [])
            ch_keys = body.get("channel_keys", [])
            b = bundle_manager.create_bundle(name, cat, gids, ch_keys)
            self._send_json({"ok": True, "bundle": b})
            return

        if p.path == "/api/bundles/delete":
            bid = body.get("id")
            ok = bundle_manager.delete_bundle(bid)
            self._send_json({"ok": ok})
            return

        if p.path == "/api/whatsapp/request_qr":
            info = whatsapp_pipeline.request_login_qr()
            self._send_json({"ok": True, "session": info})
            return

        if p.path == "/api/whatsapp/request_code":
            phone = body.get("phone", "")
            info = whatsapp_pipeline.request_pairing_code(phone)
            self._send_json({"ok": True, "session": info})
            return

        if p.path == "/api/whatsapp/confirm_login":
            dev = body.get("device_name", "Primary WhatsApp Phone")
            info = whatsapp_pipeline.confirm_session_connected(dev)
            self._send_json({"ok": True, "session": info})
            return

        if p.path == "/api/whatsapp/sync_dialogs":
            res = whatsapp_pipeline.sync_dialogs_from_session()
            self._send_json(res)
            return

        if p.path == "/api/whatsapp/quick_add":
            raw = body.get("text", "")
            if not raw.strip():
                self._send_json({"ok": False, "error": "no links given"})
                return
            res = whatsapp_pipeline.quick_add_groups(raw)
            self._send_json(res)
            return

        if p.path == "/api/whatsapp/logout":
            res = whatsapp_pipeline.logout_session()
            self._send_json({"ok": True, "session": res})
            return

        if p.path == "/api/whatsapp/schedule_quiz":
            time_val = body.get("time", "09:00")
            gids = body.get("target_group_ids", [])
            cat = body.get("category", "ALL")
            is_q = body.get("is_question", True)
            label = body.get("label", "").strip()
            q_count = int(body.get("questions_count", 1))
            days_dur = int(body.get("days_duration", 0))
            auto_mode = bool(body.get("auto_mode", True))
            end_date = body.get("end_date", "")

            # Support multiple times in one schedule call if times array passed
            times = body.get("times") or [time_val]
            created_jobs = []
            for t_item in times:
                t_str = str(t_item).strip()
                if not t_str:
                    continue
                job = whatsapp_pipeline.add_scheduled_job(
                    t_str,
                    target_group_ids=gids,
                    category=cat,
                    is_question=is_q,
                    label=label or f"{t_str} Daily {cat} Drill",
                    questions_count=q_count,
                    days_duration=days_dur,
                    auto_mode=auto_mode,
                    end_date=end_date
                )
                created_jobs.append(job)

            self._send_json({"ok": True, "jobs": created_jobs, "job": created_jobs[0] if created_jobs else None})
            return

        if p.path == "/api/whatsapp/check_conflicts" or p.path == "/api/bundles/check_conflicts":
            gids = body.get("target_group_ids", [])
            ch_keys = body.get("target_channel_keys", [])
            time_val = body.get("time", "")
            bid = body.get("bundle_id", "")
            conflicts = bundle_manager.check_conflicts(gids, ch_keys, time_str=time_val, current_bundle_id=bid)
            self._send_json({"ok": True, "conflicts": conflicts, "has_conflicts": len(conflicts) > 0})
            return

        if p.path == "/api/whatsapp/toggle_schedule":
            jid = body.get("id")
            updated = whatsapp_pipeline.toggle_scheduled_job(jid)
            self._send_json({"ok": bool(updated), "job": updated})
            return

        if p.path == "/api/whatsapp/delete_schedule":
            jid = body.get("id")
            ok = whatsapp_pipeline.delete_scheduled_job(jid)
            self._send_json({"ok": ok})
            return

        if p.path == "/api/whatsapp/add_group":
            name = body.get("name", "").strip()
            jid = body.get("jid", "").strip()
            cat = body.get("category", "AUTO")
            shift = body.get("shift", "ALL_DAY")
            g_type = body.get("group_type", "EXAM_SPECIFIC")
            new_g = whatsapp_pipeline.add_group(name, jid, cat, shift, group_type=g_type)
            self._send_json({"ok": True, "group": new_g})
            return

        if p.path == "/api/whatsapp/update_group":
            gid = body.get("id")
            updates = body.get("updates", {})
            updated = whatsapp_pipeline.update_group(gid, updates)
            self._send_json({"ok": bool(updated), "group": updated})
            return

        if p.path == "/api/whatsapp/remove_group":
            gid = body.get("id")
            ok = whatsapp_pipeline.remove_group(gid)
            self._send_json({"ok": ok})
            return

        if p.path == "/api/whatsapp/start_pipeline":
            cat = body.get("category", "ALL")
            shift = body.get("shift", "ALL")
            target_gids = body.get("target_group_ids", None)
            is_q = body.get("is_question", True)
            msg = body.get("custom_msg", "")
            att = body.get("attachment", "")
            gw = body.get("gateway", "").strip()
            delay_min = int(body.get("delay_min", 40))
            delay_max = int(body.get("delay_max", 60))
            q_count = int(body.get("questions_count", 5))
            subjects = body.get("subjects", None)

            if gw:
                reg = whatsapp_pipeline.load_wa_registry()
                reg["gateway_url"] = gw
                whatsapp_pipeline.save_wa_registry(reg)

            res = whatsapp_pipeline.start_interleaved_broadcast(
                target_category=cat,
                shift_filter=shift,
                target_group_ids=target_gids,
                is_question=is_q,
                questions_per_group=q_count,
                custom_message=msg,
                attachment_url=att,
                two_phase_answer=True,
                delay_min=delay_min,
                delay_max=delay_max,
                subjects=subjects
            )
            self._send_json(res)
            return

        if p.path == "/api/whatsapp/stop_pipeline":
            res = whatsapp_pipeline.stop_broadcast()
            self._send_json(res)
            return

        if p.path == "/api/questions/send":
            # 🔍→📤 send ONE hand-picked question to any channel/group instantly
            qid = str(body.get("qid", "")).strip()
            ch = str(body.get("channel", "")).strip()
            if not qid or not ch:
                self._send_json({"ok": False, "error": "qid మరియు channel రెండూ కావాలి"})
                return
            from core.engine import Engine
            from core.telegram import Telegram
            from core import broadcast_log
            bank = Bank()
            q = next((x for x in bank.questions if x.get("id") == qid), None)
            if not q:
                self._send_json({"ok": False, "error": f"question {qid} కనపడలేదు"})
                return
            dry = not bool(Telegram().token)
            eng = Engine(dry=dry)
            send_key = ch if ch in config.CHANNELS else "CURRENT"
            ok = eng.send_quiz(send_key, q)
            if ok and not dry:
                try:
                    bank.mark_posted(q.get("channel", "CURRENT"), [q])
                except Exception:
                    pass
            all_ch = channel_router.get_all_channels()
            label = all_ch.get(ch, {}).get("name", ch)
            broadcast_log.log_event("telegram", "🎯 " + label, 1 if ok else 0,
                                    dry=dry, note="hand-picked: " + qid)
            self._send_json({
                "ok": bool(ok),
                "message": (f"🎯 Hand-picked question '{qid}' → {label} " +
                            ("[Live]" if not dry else "[Dry-Run — BOT_TOKEN set చేయండి]")) if ok else "send failed",
            })
            return

        if p.path == "/api/bank/topup":
            # ⚡ AUTO TOP-UP: refill thin channels with freshly generated questions
            try:
                from core.generator import top_up
                added, errs = top_up(per_channel_min=25)
                self._send_json({
                    "ok": True,
                    "added": len(added or []),
                    "rejected": len(errs or []),
                    "message": f"⚡ {len(added or [])} కొత్త fresh questions add అయ్యాయి! ({len(errs or [])} rejected by quality gate)",
                })
            except Exception as e:
                self._send_json({"ok": False, "error": f"top-up failed: {e}"})
            return

        if p.path == "/api/telegram/schedule":
            # 🤖 Telegram Auto-Pilot: daily auto-posts to chosen channels/groups
            times = body.get("times", [])
            if isinstance(times, str):
                times = [t.strip() for t in times.replace(",", " ").split() if t.strip()]
            channels = body.get("channels", [])
            count = max(1, min(int(body.get("count", 1) or 1), 20))
            subjects = body.get("subjects", []) or []
            if not times:
                self._send_json({"ok": False, "error": "కనీసం ఒక time ఇవ్వండి (ఉదా: 08:00)"})
                return
            if not channels:
                self._send_json({"ok": False, "error": "టేబుల్‌లో కనీసం ఒక channel/group select చేయండి"})
                return
            created = []
            for t in times:
                job = whatsapp_pipeline.add_scheduled_job(
                    t,
                    label=f"🤖 TG Auto-Pilot {t} · {len(channels)} target(s)" + (f" · {'+'.join(subjects)}" if subjects else ""),
                    questions_count=count,
                    telegram_channels=channels,
                    subjects=subjects,
                    mode="tg",
                )
                created.append({"id": job["id"], "time": job["time"]})
            self._send_json({
                "ok": True,
                "created": created,
                "message": f"🤖 Auto-Pilot ON: {len(created)} daily slot(s) × {len(channels)} Telegram target(s) × {count} poll(s) — posts are instant, no gaps.",
            })
            return

        if p.path == "/api/channels/detect_new":
            res = channel_router.detect_new_bot_chats()
            self._send_json(res)
            return

        if p.path == "/api/channels/register":
            name = body.get("name", "").strip()
            exam_t = body.get("exam_type", "")
            chat_id = body.get("chat_id", "")
            chat_type = body.get("chat_type", "channel")
            info = channel_router.register_channel(name, chat_id=chat_id, exam_type=exam_t, chat_type=chat_type)

            try:
                from core import dynamic_generator
                dynamic_generator.synthesize_quiz(info["key"], name, count=5)
            except Exception as e:
                print(f"Auto-synthesizer note: {e}")

            self._send_json({"ok": True, "channel": info, "message": f"Channel registered & 5 syllabus questions synthesized!"})
            return

        if p.path == "/api/post_poll":
            # 🚀 Shared dispatcher: correct chat targeting (custom groups get
            # their OWN chat), no-repeat rotation, history logging — Telegram
            # sends stay instant (official Bot API, no gaps).
            from core import poll_dispatch
            ch = body.get("channel", "CURRENT")
            count = int(body.get("count", 1))
            subjects = body.get("subjects", None)
            res = poll_dispatch.post_channel_polls(ch, count=count, subjects=subjects, source="dashboard")
            self._send_json({
                "ok": res.get("ok", False),
                "sent_count": res.get("sent", 0),
                "message": res.get("message", ""),
            })
            return

        if p.path == "/api/squads/create":
            name = body.get("name", "Dashboard Squad").strip()
            leader = body.get("leader", "Admin").strip()
            sq_data = hooks._sq()
            alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
            code = "".join(random.choice(alphabet) for _ in range(4))
            while code in sq_data.get("squads", {}):
                code = "".join(random.choice(alphabet) for _ in range(4))
            
            sq_data.setdefault("squads", {})[code] = {
                "code": code,
                "name": name,
                "leader": leader,
                "members": [leader],
                "created": datetime.now().isoformat()
            }
            hooks.save_json_atomic(hooks.SQUADS_PATH, sq_data)
            bot = getattr(config, "BOT_USERNAME", "") or "StudentUpBot"
            squad_link = f"https://t.me/{bot}?start=sq_{code}"
            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=600x600&data={squad_link}"
            self._send_json({"ok": True, "code": code, "name": name, "link": squad_link, "qr": qr_url})
            return

        if p.path == "/api/war":
            act = body.get("act", "status")
            mins = int(body.get("mins", 5))
            mb = Members()
            tg = Telegram()
            bank = Bank()
            if act == "now":
                ok, txt = districtwar.manual_launch(mb, tg, bank=bank, minutes=mins)
                self._send_json({"ok": ok, "message": txt})
            else:
                txt = districtwar.owner_status(mb)
                self._send_json({"ok": True, "message": txt})
            return

        if p.path == "/api/sheet":
            act = body.get("act", "sync")
            mb = Members()
            if act == "sync":
                n = mb.sync_sheet_all()
                self._send_json({"ok": True, "message": f"Successfully synced {n} members to Google Sheet!"})
            else:
                q = crm.flush_queue()
                self._send_json({"ok": True, "message": f"Flushed {q} queued items to Google Sheet."})
            return

        self.send_response(404)
        self.end_headers()


def start_server(port=PORT):
    srv = ThreadingHTTPServer(("0.0.0.0", port), DashboardHandler)
    print(f"🚀 StudentUp Control Dashboard running at http://0.0.0.0:{port}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")


if __name__ == "__main__":
    start_server()
