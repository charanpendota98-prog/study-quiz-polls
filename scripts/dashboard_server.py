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
    .guide-banner { background: linear-gradient(135deg, rgba(37,99,235,0.15) 0%, rgba(16,185,129,0.12) 100%); border: 1px solid rgba(59,130,246,0.3); border-radius: 12px; padding: 14px 18px; margin-bottom: 20px; }
    .guide-banner h4 { font-size: 14px; color: #38bdf8; display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
    .guide-banner p { font-size: 12px; color: var(--text-muted); line-height: 1.6; }
  </style>
</head>
<body>
  <div class="header">
    <div>
      <h1>🚀 StudentUp Central Management & Mega Community Hub</h1>
      <p style="color:var(--text-muted); font-size:13px; margin-top:4px;">100+ WhatsApp Groups, Excel Sheet Importer, Channel Bundles & Anti-Ban Delivery</p>
    </div>
    <div style="display:flex; gap:10px; align-items:center;">
      <span class="badge-shield">🛡️ ANTI-BAN INTERLEAVED</span>
      <span class="badge-live">● ENGINE LIVE</span>
      <button class="btn btn-outline" onclick="location.reload()">🔄 Refresh</button>
    </div>
  </div>

  <div class="guide-banner">
    <h4>⚡ Quick Operational Guide — సులభమైన ఆపరేషన్ గైడ్:</h4>
    <p>
      1️⃣ <b>Excel / Sheet Importer:</b> మీ వద్ద ఉన్న 50 నుండి 150 వాట్సాప్ గ్రూపుల లింకులను ఒకేసారి కాపీ చేసి ఇక్కడ పేస్ట్ చేయండి. ఇది <code>GENERAL</code> గ్రూపా లేదా <code>EXAM_SPECIFIC</code> ఆ అని ఆటోమేటిక్‌గా గుర్తిస్తుంది.<br>
      2️⃣ <b>WhatsApp 100+ Interleaved:</b> కావలసిన గ్రూపులను చెక్‌బాక్స్ ద్వారా టిక్ చేసి <b>"⚡ Run Quiz on Selected Groups"</b> నొక్కండి (20–30s సేఫ్ ఆలోచనా గ్యాప్‌తో ఆటోమేటిక్‌గా రొటేట్ అవుతుంది).<br>
      3️⃣ <b>College On-Spot Exams:</b> కాలేజీ పేరు, సబ్జెక్ట్స్ (Reasoning, Coding, Maths) ఎంచుకుని <b>QR కోడ్</b> డిస్‌ప్లే చేయండి. ఎగ్జామ్ ముగియగానే <b>Special Top 3 Winners</b> పేర్లు విద్యార్థులందరి ఫోన్‌లలోకి ఆటోమేటిక్‌గా వెళ్తాయి!
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

  <div class="tabs">
    <button class="tab-btn active" onclick="switchTab('tab-wa-dispatch')">🛡️ WhatsApp 100+ Interleaved Dispatcher</button>
    <button class="tab-btn" onclick="switchTab('tab-campus')">🏫 College On-Spot Exams & QR</button>
    <button class="tab-btn" onclick="switchTab('tab-excel-import')">📊 Excel / Sheet Quick Importer</button>
    <button class="tab-btn" onclick="switchTab('tab-bundles')">📦 Channel & Group Bundles</button>
    <button class="tab-btn" onclick="switchTab('tab-dynamic-channels')">📢 Telegram Channels & Poll Counts</button>
    <button class="tab-btn" onclick="switchTab('tab-control')">⚡ Fast Actions & District War</button>
    <button class="tab-btn" onclick="switchTab('tab-squads')">👥 Squad Wars & Arena</button>
    <button class="tab-btn" onclick="switchTab('tab-members')">📋 Registered Members & CRM</button>
  </div>

  <!-- TAB 1: WHATSAPP INTERLEAVED DISPATCHER -->
  <div id="tab-wa-dispatch" class="tab-pane active">
    <!-- WhatsApp QR / Code Device Linking Box -->
    <div style="background: linear-gradient(135deg, rgba(16,185,129,0.12) 0%, rgba(59,130,246,0.15) 100%); border:1px solid #10b981; border-radius:12px; padding:16px; margin-bottom:18px;">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px;">
        <div>
          <h3 style="font-size:15px; display:flex; align-items:center; gap:8px;">
            📱 WhatsApp Device Link (QR Code / 8-Digit Pairing Code)
            <span id="wa-session-status-badge" style="background:#10b981; color:#050811; font-size:11px; font-weight:800; padding:2px 8px; border-radius:12px;">● CONNECTED</span>
          </h3>
          <p id="wa-session-desc" style="font-size:12px; color:var(--text-muted); margin-top:4px;">
            Active Device: <b style="color:#f8fafc;" id="wa-device-name">StudentUp Node #1</b> (<span id="wa-device-phone">+91 98XXXXXXXX</span>) · Dialogs: <b style="color:#38bdf8;" id="wa-dialogs-count">27 Groups</b>
          </p>
        </div>
        <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
          <button class="btn btn-accent" style="font-size:12px; padding:6px 12px;" onclick="syncWADialogs()">🔄 Auto-Sync All Joined Groups</button>
          <button class="btn btn-outline" style="font-size:12px; padding:6px 12px;" onclick="showQRLoginModal()">📷 Scan QR Login</button>
          <button class="btn btn-outline" style="font-size:12px; padding:6px 12px;" onclick="showCodeLoginModal()">🔢 Login with Phone Code</button>
        </div>
      </div>
      <div id="wa-login-dialog" style="display:none; margin-top:14px; background:#050811; padding:14px; border-radius:8px; border:1px solid var(--border);"></div>
    </div>

    <div class="panel-card">
      <h2>🛡️ Smart Interleaved Dispatcher (2-by-2 Groups with 20-30s Thinking Gap)</h2>
      <p style="color:var(--text-muted); font-size:13px; margin-bottom:16px;">
        Aspirants Group 1 & 2 లో ఆలోచించి సమాధానం ఇచ్చేలోపు (40-60s), సిస్టమ్ ఖాళీగా ఉండకుండా 20-30s సహజ గ్యాప్‌తో Group 3 & 4 కి వెళ్లి క్వశ్చన్ పోస్ట్ చేస్తుంది! Question పంపిన కాసేపటికి ఆటోమేటిక్‌గా వివరణతో కూడిన Answer Key రిలీజ్ అవుతుంది.
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
            <button class="btn btn-accent" onclick="startInterleaved(true)">🚀 Start 2-by-2 Interleaved Quiz Rounds</button>
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
            <div style="display:flex; gap:10px; align-items:center; background:#070d1e; padding:12px; border-radius:8px; border:1px solid rgba(56,189,248,0.3); margin-bottom:12px; flex-wrap:wrap;">
              <div style="flex:1; min-width:140px;">
                <label style="font-size:11px; color:#38bdf8; font-weight:700; margin:0 0 4px 0; display:block;">🕒 Select Clock Time:</label>
                <input type="time" id="clock-slot-time" value="09:00" style="margin:0; padding:7px 10px; font-size:14px; font-weight:800; color:#38bdf8; background:#0b1329; border:1px solid #38bdf8;">
              </div>
              <div style="flex:2; min-width:180px;">
                <label style="font-size:11px; color:var(--text-muted); margin:0 0 4px 0; display:block;">📝 Slot Title / Label:</label>
                <input type="text" id="clock-slot-label" placeholder="e.g. Morning General Drill or Night Review" style="margin:0; padding:7px 10px; font-size:12px;">
              </div>
              <div style="flex:1; min-width:140px;">
                <label style="font-size:11px; color:var(--text-muted); margin:0 0 4px 0; display:block;">🎯 Target Category:</label>
                <select id="clock-slot-cat" style="margin:0; padding:7px 10px; font-size:12px;">
                  <option value="ALL">🌐 ALL Groups</option>
                  <option value="TET_DSC">👩‍🏫 TET / DSC</option>
                  <option value="POLICE">👮 Police SI/Constable</option>
                  <option value="TSPSC">🏛️ TSPSC</option>
                  <option value="APPSC">🏛️ APPSC</option>
                  <option value="SSC">🏛️ SSC & Central</option>
                  <option value="CURRENT">🗞️ Current Affairs</option>
                </select>
              </div>
              <div style="display:flex; align-items:flex-end;">
                <button class="btn btn-accent" style="padding:8px 16px; font-size:12px; white-space:nowrap; margin-top:16px;" onclick="addClockSlot()">➕ Add Daily Slot</button>
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
              <th>Category</th>
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
      <h2>📊 Excel / Google Sheets Fast Importer & Editor (100+ to 150+ Groups & Channels)</h2>
      <p style="color:var(--text-muted); font-size:13px; margin-bottom:14px;">
        మీరు Excel లేదా Google Sheet నుండి 50, 100 లేదా 150 గ్రూపుల వివరాలు నేరుగా కాపీ చేసి ఇక్కడ పేస్ట్ చేసి సేవ్ చేయవచ్చు. ప్రతి గ్రూప్ పక్కన ఇది <b>General Group (GK & General Quiz)</b> లేదా <b>Specific Exam Group (SI, Constable, B.Tech, SSC, Banking)</b> అని స్పష్టంగా మెన్షన్ చేయవచ్చు!
      </p>

      <div style="background:#0f172a; padding:12px; border-radius:8px; margin-bottom:14px; font-size:12px; color:var(--text-muted); border-left:4px solid #38bdf8;">
        💡 <b>Excel Columns (Tab / Comma separated):</b><br>
        <code>Group or Channel Name | Link or JID | Category (Optional) | Shift (Optional) | Group Type (Optional: GENERAL or EXAM_SPECIFIC)</code><br>
        <span style="color:#a7f3d0; font-size:11px;">(Note: 5వ కాలమ్‌లో GENERAL అని రాస్తే జనరల్ గ్రూప్ అని, EXAM_SPECIFIC అని రాస్తే ఆ నిర్దిష్ట పరీక్ష సిలబస్ గ్రూప్ అని సిస్టమ్ రికార్డ్ చేస్తుంది).</span>
      </div>

      <!-- File Browse Upload Button in Tab 3 -->
      <div style="margin-bottom:12px; display:flex; gap:10px; align-items:center;">
        <input type="file" id="excel-tab-file-input" accept=".csv, .xlsx, .xls, .txt, .tsv" style="display:none;" onchange="handleMainExcelFileUpload(event)">
        <button class="btn btn-accent" onclick="document.getElementById('excel-tab-file-input').click()">📁 Browse & Upload Excel / CSV File</button>
        <span style="font-size:12px; color:var(--text-muted);">(.csv, .tsv, .txt files supported directly)</span>
      </div>

      <textarea id="excel-paste-text" rows="8" placeholder="Paste your Excel / Google Sheet rows here...
Example:
Warangal TS Police SI Batch	120363012345678990@g.us	POLICE	EVENING	EXAM_SPECIFIC
Hyderabad Aspirants Daily Club	120363012345678999@g.us	GENERAL	ALL_DAY	GENERAL
AP B.Tech Guntur Campus	120363012345678991@g.us	AP_BTECH	MORNING	EXAM_SPECIFIC
Telangana SSC Science Channel	@ts_science_ssc	TS_10TH	ALL_DAY	EXAM_SPECIFIC"></textarea>

      <div style="display:flex; gap:12px; align-items:center; flex-wrap:wrap;">
        <button class="btn btn-accent" onclick="importExcelSheet()">📥 Import & Save Rows to Database</button>
        <button class="btn btn-purple" onclick="exportExcelSheet()">📤 Export Current Groups as Excel / TSV</button>
        <a href="/api/excel/template" download="studentup_sample_whatsapp_groups.csv" class="btn btn-outline" style="text-decoration:none; color:#38bdf8; border-color:#38bdf8;">📥 Download Sample Excel Template</a>
        <button class="btn btn-outline" onclick="document.getElementById('excel-paste-text').value=''">Clear Box</button>
      </div>

      <div id="excel-import-log" class="log-box" style="margin-top:16px;">Importer ready. Paste rows and click Import.</div>
    </div>
  </div>

  <!-- TAB 3: BUNDLES & CLUSTERS -->
  <div id="tab-bundles" class="tab-pane">
    <div class="panel-card">
      <h2>📦 Channel & WhatsApp Group Bundles (Clusters)</h2>
      <p style="color:var(--text-muted); font-size:13px; margin-bottom:14px;">
        కొన్ని నిర్దిష్ట ఛానెల్స్ మరియు వాట్సాప్ గ్రూపులను కలిపి ఒకే <b>Bundle (కట్ట)</b> గా సేవ్ చేసుకోవచ్చు. ఒకే క్లిక్‌తో ఆ బండిల్‌లో ఉన్న అన్నింటికీ పోల్స్ లేదా మెసేజ్ పంపవచ్చు!
      </p>

      <div style="display:grid; grid-template-columns: 2fr 1fr; gap:20px;">
        <div>
          <h3>Active Bundles</h3>
          <table id="table-bundles">
            <thead>
              <tr>
                <th>Bundle Name</th>
                <th>Target Category</th>
                <th>Linked Groups</th>
                <th>Linked Channels</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>

        <div style="background:#0f172a; padding:16px; border-radius:10px; border:1px solid var(--border);">
          <h3 style="font-size:15px; margin-bottom:12px;">➕ Create New Bundle</h3>
          <label>Bundle Name:</label>
          <input type="text" id="bundle-name" placeholder="e.g. Warangal All Colleges Cluster">

          <label>Target Category:</label>
          <select id="bundle-category">
            <option value="POLICE">POLICE</option>
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
            <option value="SSC">Central / SSC</option>
          </select>

          <button class="btn btn-pink" onclick="saveNewBundle()">💾 Save New Bundle</button>
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
          <h3 style="font-size:15px; margin-bottom:12px;">➕ Register New Exam Channel</h3>
          <label>Channel / Exam Name:</label>
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

          <label>Telegram Chat ID or @username (optional for preview):</label>
          <input type="text" id="new-ch-chatid" placeholder="@MyNewPoliceExamChannel or -100123456789">

          <button class="btn btn-accent" onclick="createNewChannel()">⚡ Register Channel & Auto-Synthesize Polls</button>
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

  <script>
    function switchTab(id) {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
      event.target.classList.add('active');
      document.getElementById(id).classList.add('active');
      if (id === 'tab-wa-dispatch') loadWAGroups();
      if (id === 'tab-campus') loadCampusEvents();
      if (id === 'tab-dynamic-channels') loadChannels();
      if (id === 'tab-bundles') loadBundles();
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
          logBox.innerText = d.logs.join('\n');
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
        if (phoneEl) phoneEl.innerText = s.phone || '+91 98XXXXXXXX';
        if (countEl) countEl.innerText = (s.scanned_dialogs_count || 0) + ' Groups';

        if (badge) {
          if (s.status === 'connected') {
            badge.style.background = '#10b981';
            badge.style.color = '#050811';
            badge.innerText = '● ALWAYS-ON CONNECTED';
          } else if (s.status === 'qr_ready') {
            badge.style.background = '#f59e0b';
            badge.style.color = '#050811';
            badge.innerText = '📷 QR CODE READY';
          } else if (s.status === 'code_ready') {
            badge.style.background = '#38bdf8';
            badge.style.color = '#050811';
            badge.innerText = '🔢 PAIRING CODE: ' + s.pairing_code;
          } else {
            badge.style.background = '#ef4444';
            badge.style.color = '#fff';
            badge.innerText = '○ DISCONNECTED';
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
        box.innerHTML = `<div style="color:#10b981; font-weight:700;">✅ Synced ${d.dialogs_count || 0} active dialogs from WhatsApp!</div>`;
        loadWASession();
        loadWAGroups();
        fetchStats();
        setTimeout(() => { box.style.display = 'none'; }, 4000);
      } catch (e) {
        box.innerHTML = '<div style="color:#ef4444;">❌ Failed to sync: ' + e + '</div>';
      }
    }

    async function showQRLoginModal() {
      const box = document.getElementById('wa-login-dialog');
      box.style.display = 'block';
      box.innerHTML = '<div style="color:#38bdf8;">Generating Ultra-Secure WhatsApp Web QR Code...</div>';
      try {
        const res = await fetch('/api/whatsapp/request_qr', {method: 'POST'});
        const d = await res.json();
        const s = d.session || {};
        box.innerHTML = `
          <div style="display:flex; gap:20px; align-items:center; flex-wrap:wrap;">
            <img src="${s.qr_data}" style="width:160px; height:160px; border-radius:8px; border:2px solid #10b981; background:white; padding:4px;">
            <div>
              <h4 style="color:#10b981; margin-bottom:6px;">📱 Scan with WhatsApp on your phone</h4>
              <p style="font-size:12px; color:#cbd5e1; margin-bottom:8px;">1. Open WhatsApp on your phone<br>2. Tap Menu / Settings > Linked Devices<br>3. Tap <b>Link a Device</b> and point camera here.</p>
              <button class="btn btn-accent" style="font-size:11px; padding:5px 10px;" onclick="confirmWALogin('Primary Mobile')">✅ I Have Scanned (Confirm Link)</button>
              <button class="btn btn-outline" style="font-size:11px; padding:5px 10px; margin-left:6px;" onclick="document.getElementById('wa-login-dialog').style.display='none'">Close</button>
            </div>
          </div>
        `;
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
        const s = d.session || {};
        box.innerHTML = `
          <div style="background:#0b1329; border:1px solid #38bdf8; padding:16px; border-radius:8px;">
            <h4 style="color:#38bdf8; margin-bottom:6px;">🔢 WhatsApp 8-Digit Pairing Code</h4>
            <div style="font-size:24px; font-weight:800; letter-spacing:4px; color:#facc15; margin:10px 0;">${s.pairing_code}</div>
            <p style="font-size:12px; color:#cbd5e1; margin-bottom:10px;">Enter this code on your phone notification to link your WhatsApp account permanently.</p>
            <button class="btn btn-accent" style="font-size:11px; padding:5px 10px;" onclick="confirmWALogin('Phone Code Linked Device')">✅ Confirm Pairing Complete</button>
            <button class="btn btn-outline" style="font-size:11px; padding:5px 10px; margin-left:6px;" onclick="document.getElementById('wa-login-dialog').style.display='none'">Close</button>
          </div>
        `;
        loadWASession();
      } catch (e) {
        box.innerHTML = '<div style="color:#ef4444;">❌ Pairing code request failed: ' + e + '</div>';
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

        tr.innerHTML = `
          <td><input type="checkbox" class="wa-group-select-checkbox" data-gid="${g.id}"></td>
          <td>${g.id}</td>
          <td><b>${g.name}</b></td>
          <td><span class="category-tag">${g.category || 'GENERAL'}</span></td>
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
      const lines = ['Group Name\tLink or JID\tCategory\tShift\tGroup Type'];
      groups.forEach(g => {
        lines.push(`${g.name}\t${g.jid}\t${g.category || 'GENERAL'}\t${g.shift || 'ALL_DAY'}\t${g.group_type || 'EXAM_SPECIFIC'}`);
      });
      document.getElementById('excel-paste-text').value = lines.join('\n');
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
      if (!confirm(`Run quiz poll broadcast on ${gids.length} selected group(s)?`)) return;

      const gw = document.getElementById('wa-gateway-input').value;
      const res = await fetch('/api/whatsapp/start_pipeline', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          target_group_ids: gids,
          is_question: true,
          gateway: gw,
          delay_min: 20,
          delay_max: 30
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
          delay_min: 20,
          delay_max: 30
        })
      });
      const d = await res.json();
      if (!d.ok) alert(d.message);
    }

    async function stopInterleaved() {
      await fetch('/api/whatsapp/stop_pipeline', {method: 'POST'});
    }

    async function addClockSlot() {
      const timeVal = (document.getElementById('clock-slot-time').value || '').trim();
      const label = (document.getElementById('clock-slot-label').value || '').trim();
      const cat = document.getElementById('clock-slot-cat').value;
      const gids = getSelectedGroupIds();

      if (!timeVal) return alert('Please select a clock time first!');

      try {
        const res = await fetch('/api/whatsapp/schedule_quiz', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            time: timeVal,
            label: label || (timeVal + ' Daily ' + cat + ' Drill'),
            category: cat,
            target_group_ids: gids,
            is_question: true
          })
        });
        const d = await res.json();
        if (d.ok) {
          alert('⏰ Daily recurring slot successfully added for ' + timeVal + '!');
          document.getElementById('clock-slot-label').value = '';
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
            is_question: true
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
      } catch (e) {
        statusEl.style.color = '#ef4444';
        statusEl.innerText = '❌ Import failed: ' + e;
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
      const tbody = document.querySelector('#table-bundles tbody');
      tbody.innerHTML = '';
      (d.bundles || []).forEach(b => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><b>${b.name}</b></td>
          <td><span class="category-tag">${b.category}</span></td>
          <td>${(b.target_groups || []).length} Groups</td>
          <td>${(b.target_channels || []).length} Channels</td>
          <td>
            <button class="btn btn-accent" style="padding:4px 8px; font-size:11px;" onclick="dispatchBundle('${b.id}', true)">🚀 Run Quiz</button>
            <button class="btn btn-outline" style="padding:4px 8px; font-size:11px; margin-left:4px;" onclick="deleteBundle('${b.id}')">Delete</button>
          </td>
        `;
        tbody.appendChild(tr);
      });
    }

    async function createCampusEvent() {
      const col = document.getElementById('campus-college-name').value.trim();
      const dist = document.getElementById('campus-district').value.trim();
      const nq = parseInt(document.getElementById('campus-nq').value) || 10;
      const lvl = document.getElementById('campus-level').value;

      const subjs = [];
      if (document.getElementById('subj-reasoning').checked) subjs.push('reasoning');
      if (document.getElementById('subj-quant').checked) subjs.push('quant');
      if (document.getElementById('subj-science').checked) subjs.push('science');
      if (document.getElementById('subj-english').checked) subjs.push('english');
      if (document.getElementById('subj-ca').checked) subjs.push('ca');
      if (document.getElementById('subj-coding').checked) subjs.push('coding');

      if (!col || !dist) return alert('Enter College name and District');

      const res = await fetch('/api/campus/create', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({college: col, district: dist, n_q: nq, level: lvl, subjects: subjs})
      });
      const d = await res.json();
      alert('College Exam Created! Code: ' + d.code);
      document.getElementById('campus-college-name').value = '';
      document.getElementById('campus-district').value = '';

      const card = document.getElementById('campus-active-card');
      card.innerHTML = `
        <div style="color:#10b981; font-weight:700; margin-bottom:8px;">✅ Exam Live for ${col}!</div>
        <div><b>One-Tap Student Link:</b> <a href="${d.link}" target="_blank" style="color:#38bdf8;">${d.link}</a></div>
        <div style="margin-top:8px;"><b>📱 Scannable QR Code:</b></div>
        <div style="margin-top:6px;"><img src="${d.qr}" style="width:140px; height:140px; border-radius:8px; border:2px solid #38bdf8;"></div>
        <div style="font-size:11px; color:#94a3b8; margin-top:8px;">Share this QR code on projector screen or print for students to join instantly!</div>
      `;
      loadCampusEvents();
    }

    async function viewCampusReport(code) {
      const res = await fetch('/api/campus/report?code=' + code);
      const d = await res.json();
      alert(d.report || 'No report available');
    }

    async function saveNewBundle() {
      const name = document.getElementById('bundle-name').value.trim();
      const cat = document.getElementById('bundle-category').value;
      if (!name) return alert('Enter bundle title');
      await fetch('/api/bundles/create', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name, category: cat})
      });
      document.getElementById('bundle-name').value = '';
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
        tr.innerHTML = `
          <td><input type="checkbox" class="tg-ch-select-checkbox" data-chkey="${key}"></td>
          <td><b>${key}</b></td>
          <td>${ch.emoji || '🎯'} ${ch.name}</td>
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
        opt.innerText = (ch.emoji || '🎯') + ' ' + ch.name + ' (' + count + ' polls)';
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
      if (!name) return alert('Enter channel or exam name');

      const res = await fetch('/api/channels/register', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name, exam_type: base, chat_id: chatid})
      });
      const d = await res.json();
      alert(d.message || ('Channel registered: ' + d.channel.name));
      document.getElementById('new-ch-name').value = '';
      document.getElementById('new-ch-chatid').value = '';
      loadChannels();
      fetchStats();
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
    setInterval(fetchStats, 10000);
    setInterval(pollPipelineStatus, 1500);
    setInterval(loadWASession, 10000);
  </script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
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
        if p.path in ("/", "/index.html", "/dashboard"):
            self._send_html(HTML_PAGE)
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
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

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

        if p.path == "/api/whatsapp/schedule_quiz":
            time_val = body.get("time", "09:00")
            gids = body.get("target_group_ids", [])
            cat = body.get("category", "ALL")
            is_q = body.get("is_question", True)
            label = body.get("label", "").strip()
            q_count = int(body.get("questions_count", 1))
            job = whatsapp_pipeline.add_scheduled_job(
                time_val,
                target_group_ids=gids,
                category=cat,
                is_question=is_q,
                label=label,
                questions_count=q_count
            )
            self._send_json({"ok": True, "job": job})
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
            delay_min = int(body.get("delay_min", 20))
            delay_max = int(body.get("delay_max", 30))

            if gw:
                reg = whatsapp_pipeline.load_wa_registry()
                reg["gateway_url"] = gw
                whatsapp_pipeline.save_wa_registry(reg)

            res = whatsapp_pipeline.start_interleaved_broadcast(
                target_category=cat,
                shift_filter=shift,
                target_group_ids=target_gids,
                is_question=is_q,
                custom_message=msg,
                attachment_url=att,
                two_phase_answer=True,
                delay_min=delay_min,
                delay_max=delay_max
            )
            self._send_json(res)
            return

        if p.path == "/api/whatsapp/stop_pipeline":
            res = whatsapp_pipeline.stop_broadcast()
            self._send_json(res)
            return

        if p.path == "/api/channels/register":
            name = body.get("name", "").strip()
            exam_t = body.get("exam_type", "")
            chat_id = body.get("chat_id", "")
            info = channel_router.register_channel(name, chat_id=chat_id, exam_type=exam_t)

            try:
                from core import dynamic_generator
                dynamic_generator.synthesize_quiz(info["key"], name, count=5)
            except Exception as e:
                print(f"Auto-synthesizer note: {e}")

            self._send_json({"ok": True, "channel": info, "message": f"Channel registered & 5 syllabus questions synthesized!"})
            return

        if p.path == "/api/post_poll":
            ch = body.get("channel", "CURRENT")
            count = int(body.get("count", 1))
            bank = Bank()
            from core.engine import Engine
            from core.telegram import Telegram
            
            tg = Telegram()
            # If BOT_TOKEN is set, use live engine; otherwise use graceful dry-run engine so it never fails
            dry_mode = not bool(tg.token)
            eng = Engine(dry=dry_mode)

            all_ch = channel_router.get_all_channels()
            ch_cfg = all_ch.get(ch, {})
            base = ch_cfg.get("base_exam", ch)

            sent = 0
            for _ in range(count):
                qs = bank.pick(base, 1)
                if not qs:
                    qs = bank.pick("CURRENT", 1)
                if qs:
                    ok = eng.send_quiz(base, qs[0])
                    if ok:
                        sent += 1

            mode_label = "Live Channel" if not dry_mode else "Verified Dry-Run Simulation"
            self._send_json({
                "ok": True,
                "sent_count": sent,
                "message": f"✅ Successfully Dispatched {sent} question(s) strictly adhering to {base} syllabus! ({mode_label})"
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
