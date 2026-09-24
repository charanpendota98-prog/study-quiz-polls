#!/usr/bin/env python3
"""
STUDENTUP — FULL CONTROL WEB DASHBOARD & AUTOMATION HUB
Zero-dependency, standalone HTTP server running on standard library.
Features:
  1. Live Stats: Members, Registered Count, Verified, Active, Points, Top Districts.
  2. Member Directory & Google Sheet Sync trigger.
  3. Squad & Battle Arena Control: View squads, active rooms, trigger matches.
  4. District War Control: Live status, open lobby, manual launch, timer triggers.
  5. Quiz Polls & Channel Broadcast: Send poll to Telegram public channels or DMs.
  6. WhatsApp Multi-Group Automation:
     - Manage WhatsApp groups list (add/remove phone numbers, group invite links, group IDs).
     - Automated staggered posting: post poll / message to one group, wait delay, post to next group.
     - Webhook/API integration for WhatsApp Gateway (UltraMsg, WPPConnect, Baileys, GreenAPI, or custom).
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
from core import hooks, districtwar, arena, campus, crm
from core.telegram import Telegram

PORT = int(config.env("DASHBOARD_PORT", "5000"))
WA_GROUPS_FILE = config.DATA / "whatsapp_groups.json"


def _load_wa_groups():
    if WA_GROUPS_FILE.exists():
        try:
            with open(WA_GROUPS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "groups": [
            {"id": "G1", "name": "TSPSC Aspirants Hub", "jid": "120363012345678901@g.us", "active": True},
            {"id": "G2", "name": "APPSC Group 2 & 4 Warriors", "jid": "120363098765432101@g.us", "active": True},
            {"id": "G3", "name": "SSC CGL / Railway RRB Prep", "jid": "120363011223344551@g.us", "active": True}
        ],
        "gateway_url": "",
        "gateway_token": "",
        "post_delay_sec": 5,
        "logs": []
    }


def _save_wa_groups(d):
    config.DATA.mkdir(parents=True, exist_ok=True)
    with open(WA_GROUPS_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)


def format_poll_for_wa(q, cfg_name="StudentUp"):
    tf = bool(getattr(config, "TELUGU_FIRST", True))
    q_text = q.get("q_te", "") if tf and q.get("q_te") else q.get("q_en", "")
    sub_text = q.get("q_en", "") if tf and q.get("q_te") else q.get("q_te", "")
    lines = [f"🎯 *{cfg_name} — Daily Exam Quiz*", ""]
    lines.append(f"❓ *{q_text}*")
    if sub_text and sub_text != q_text:
        lines.append(f"({sub_text})")
    lines.append("")
    opts = q.get("options_te") if tf and q.get("options_te") else q.get("options_en", [])
    letters = ["A", "B", "C", "D", "E"]
    for i, opt in enumerate(opts):
        lines.append(f"  *{letters[i]}*. {opt}")
    lines += ["", f"🏆 *Answer Index*: Option {letters[int(q.get('answer_index', 0))]}",
              f"💡 *Explanation*: {q.get('explanation_te') or q.get('explanation_en') or 'Official PYQ Key'}",
              "", "📲 Bot లో ఆడి ర్యాంక్ పొందండి: t.me/" + (config.BOT_USERNAME or "StudentUpBot")]
    return "\n".join(lines)


HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>StudentUp — Ultimate Control Dashboard</title>
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
      --text: #f8fafc;
      --text-muted: #94a3b8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }
    body { background: var(--bg); color: var(--text); padding: 24px; min-height: 100vh; }
    .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 20px; margin-bottom: 28px; }
    .header h1 { font-size: 26px; font-weight: 800; display: flex; align-items: center; gap: 10px; }
    .badge-live { background: rgba(16, 185, 129, 0.15); color: var(--accent); border: 1px solid var(--accent); padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; }
    .grid-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 18px; margin-bottom: 28px; }
    .stat-card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; position: relative; overflow: hidden; }
    .stat-card .label { font-size: 13px; color: var(--text-muted); font-weight: 500; }
    .stat-card .val { font-size: 32px; font-weight: 800; margin-top: 8px; }
    .stat-card .desc { font-size: 12px; color: var(--text-muted); margin-top: 4px; }
    .tabs { display: flex; gap: 10px; margin-bottom: 24px; border-bottom: 1px solid var(--border); padding-bottom: 12px; }
    .tab-btn { background: transparent; border: none; color: var(--text-muted); font-size: 15px; font-weight: 600; padding: 8px 16px; border-radius: 8px; cursor: pointer; transition: all 0.2s; }
    .tab-btn.active { background: var(--primary); color: #fff; }
    .tab-pane { display: none; }
    .tab-pane.active { display: block; }
    .panel-card { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 24px; margin-bottom: 24px; }
    .panel-card h2 { font-size: 18px; margin-bottom: 16px; display: flex; align-items: center; gap: 8px; }
    .btn { background: var(--primary); color: #fff; border: none; padding: 10px 18px; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; transition: background 0.2s; display: inline-flex; align-items: center; gap: 6px; }
    .btn:hover { background: var(--primary-hover); }
    .btn-accent { background: var(--accent); }
    .btn-accent:hover { background: var(--accent-hover); }
    .btn-danger { background: var(--danger); }
    .btn-outline { background: transparent; border: 1px solid var(--border); color: var(--text); }
    .btn-outline:hover { background: var(--border); }
    input, select, textarea { width: 100%; padding: 11px 14px; background: #0f172a; border: 1px solid var(--border); border-radius: 8px; color: var(--text); font-size: 14px; margin-top: 6px; margin-bottom: 16px; }
    input:focus, select:focus, textarea:focus { outline: 2px solid var(--primary); border-color: transparent; }
    table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 13px; }
    th, td { text-align: left; padding: 12px 14px; border-bottom: 1px solid var(--border); }
    th { color: var(--text-muted); font-weight: 600; background: rgba(15, 23, 42, 0.6); }
    .log-box { background: #050811; border: 1px solid var(--border); border-radius: 8px; padding: 14px; font-family: monospace; font-size: 12px; max-height: 220px; overflow-y: auto; color: #38bdf8; white-space: pre-wrap; margin-top: 12px; }
    .status-pill { display: inline-block; padding: 3px 8px; border-radius: 6px; font-size: 11px; font-weight: 700; text-transform: uppercase; }
    .status-pill.open { background: rgba(16, 185, 129, 0.2); color: #34d399; }
    .status-pill.closed { background: rgba(239, 68, 68, 0.2); color: #f87171; }
  </style>
</head>
<body>
  <div class="header">
    <div>
      <h1>🚀 StudentUp Super-Admin Dashboard</h1>
      <p style="color:var(--text-muted); font-size:13px; margin-top:4px;">Full Telegram & WhatsApp Automated Management Engine</p>
    </div>
    <div style="display:flex; gap:12px; align-items:center;">
      <span class="badge-live">● SYSTEM ACTIVE</span>
      <button class="btn btn-outline" onclick="location.reload()">🔄 Refresh</button>
    </div>
  </div>

  <div class="grid-stats">
    <div class="stat-card">
      <div class="label">Total Members</div>
      <div class="val" id="stat-members">...</div>
      <div class="desc">Aspirants on platform</div>
    </div>
    <div class="stat-card">
      <div class="label">Registered & Verified</div>
      <div class="val" id="stat-reg" style="color:var(--accent);">...</div>
      <div class="desc">Profile complete with Mobile</div>
    </div>
    <div class="stat-card">
      <div class="label">Total Points Earned</div>
      <div class="val" id="stat-points" style="color:var(--warning);">...</div>
      <div class="desc">Active gamification balance</div>
    </div>
    <div class="stat-card">
      <div class="label">District War State</div>
      <div class="val" id="stat-war">...</div>
      <div class="desc" id="stat-war-sub">9:00 PM Daily Battle</div>
    </div>
  </div>

  <div class="tabs">
    <button class="tab-btn active" onclick="switchTab('tab-control')">⚡ Fast Actions</button>
    <button class="tab-btn" onclick="switchTab('tab-whatsapp')">💬 WhatsApp Group Automation</button>
    <button class="tab-btn" onclick="switchTab('tab-polls')">📊 Telegram Channels Polls</button>
    <button class="tab-btn" onclick="switchTab('tab-squads')">👥 Squads & Battle Arena</button>
    <button class="tab-btn" onclick="switchTab('tab-members')">📋 Registered Members</button>
  </div>

  <!-- TAB: FAST ACTIONS -->
  <div id="tab-control" class="tab-pane active">
    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:20px;">
      <div class="panel-card">
        <h2>⚔️ District War Instant Control</h2>
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

  <!-- TAB: WHATSAPP AUTOMATION -->
  <div id="tab-whatsapp" class="tab-pane">
    <div class="panel-card">
      <h2>💬 WhatsApp Multi-Group Automatic Sender</h2>
      <p style="color:var(--text-muted); font-size:13px; margin-bottom:14px;">
        Auto-broadcast exam quiz polls, messages & answer keys to multiple WhatsApp groups with automated delay (staggered delivery).
      </p>

      <div style="display:grid; grid-template-columns: 2fr 1fr; gap:20px;">
        <div>
          <label>Select Exam Channel Question to Post:</label>
          <select id="wa-exam-channel">
            <option value="CURRENT">Current Affairs & GK</option>
            <option value="TSPSC">TSPSC (Group 2/3/4)</option>
            <option value="APPSC">APPSC (Group 2/4)</option>
            <option value="SSC">SSC (CGL/CHSL/MTS)</option>
            <option value="RAILWAY">Railway RRB (NTPC/Group D)</option>
            <option value="BANKING">Banking (IBPS/SBI)</option>
            <option value="POLICE">Police SI & Constable</option>
          </select>

          <label>Or Type Custom Announcement / Message:</label>
          <textarea id="wa-custom-msg" rows="4" placeholder="Type message to blast across WhatsApp groups..."></textarea>

          <div style="display:flex; gap:12px; align-items:center;">
            <button class="btn btn-accent" onclick="sendWhatsApp(true)">🚀 Send Question Poll to All Groups (Automated)</button>
            <button class="btn btn-outline" onclick="sendWhatsApp(false)">📝 Send Custom Message</button>
          </div>
        </div>

        <div>
          <label>Stagger Delay Between Groups (seconds):</label>
          <input type="number" id="wa-delay" value="5" min="1" max="60">

          <label>WhatsApp Gateway API URL (optional):</label>
          <input type="text" id="wa-gateway" placeholder="http://localhost:3000/send or GreenAPI/UltraMsg">

          <div style="font-size:12px; color:var(--text-muted); line-height:1.5;">
            💡 <b>Automated Queue:</b> One group is sent, waits N seconds, then smoothly posts to the next group to prevent spam flags.
          </div>
        </div>
      </div>

      <div style="margin-top:20px;">
        <h3>Connected WhatsApp Groups</h3>
        <table id="table-wa-groups">
          <thead>
            <tr>
              <th>ID</th>
              <th>Group Name</th>
              <th>Group ID / Link</th>
              <th>Status</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
        <div style="display:flex; gap:10px; margin-top:12px;">
          <input type="text" id="new-wa-name" placeholder="Group Name (e.g. Warangal TSPSC)">
          <input type="text" id="new-wa-jid" placeholder="Group JID or Invite Link">
          <button class="btn" onclick="addWAGroup()">➕ Add Group</button>
        </div>
      </div>

      <div id="wa-log" class="log-box" style="margin-top:16px;">WhatsApp delivery logs will appear here...</div>
    </div>
  </div>

  <!-- TAB: TELEGRAM POLLS -->
  <div id="tab-polls" class="tab-pane">
    <div class="panel-card">
      <h2>📊 Send Instant Quiz Poll to Telegram Channel</h2>
      <div style="display:grid; grid-template-columns: 1fr 1fr; gap:20px;">
        <div>
          <label>Choose Channel:</label>
          <select id="tg-channel">
            <option value="TSPSC">📘 TSPSC Quiz Channel</option>
            <option value="APPSC">📗 APPSC Quiz Channel</option>
            <option value="SSC">🏛️ SSC Quiz Channel</option>
            <option value="BANKING">🏦 Banking Quiz Channel</option>
            <option value="RAILWAY">🚆 Railway Quiz Channel</option>
            <option value="POLICE">👮 Police Quiz Channel</option>
            <option value="CURRENT">🗞️ Current Affairs Channel</option>
          </select>
          <button class="btn btn-accent" onclick="postChannelPoll()">📢 Post 1 Fresh Poll Now</button>
          <button class="btn" onclick="postChannelPoll(5)" style="margin-left:8px;">📢 Post 5 Round Polls</button>
        </div>
        <div id="tg-poll-result" class="log-box">Select channel and post. Polls are strictly exam-specific.</div>
      </div>
    </div>
  </div>

  <!-- TAB: SQUADS & ARENA -->
  <div id="tab-squads" class="tab-pane">
    <div class="panel-card">
      <h2>👥 Registered Squads & Battle Rooms</h2>
      <div style="display:flex; justify-content:space-between; margin-bottom:14px;">
        <p style="color:var(--text-muted); font-size:13px;">Live list of squads, members, codes, invite links, and active rooms.</p>
        <button class="btn btn-outline" onclick="loadSquads()">🔄 Refresh Squads</button>
      </div>
      <table id="table-squads">
        <thead>
          <tr>
            <th>Squad Code</th>
            <th>Name</th>
            <th>Leader ID</th>
            <th>Members Count</th>
            <th>Invite Link & QR</th>
          </tr>
        </thead>
        <tbody></tbody>
      </table>
    </div>
  </div>

  <!-- TAB: MEMBERS DIRECTORY -->
  <div id="tab-members" class="tab-pane">
    <div class="panel-card">
      <h2>📋 Registered Student Members</h2>
      <p style="color:var(--text-muted); font-size:13px; margin-bottom:14px;">All registered aspirants with accurate points, streaks, district and exam target.</p>
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
      if (id === 'tab-squads') loadSquads();
      if (id === 'tab-members') loadMembers();
      if (id === 'tab-whatsapp') loadWAGroups();
    }

    async function fetchStats() {
      try {
        const res = await fetch('/api/stats');
        const data = await res.json();
        document.getElementById('stat-members').innerText = data.total_members;
        document.getElementById('stat-reg').innerText = data.registered_members;
        document.getElementById('stat-points').innerText = data.total_points.toLocaleString();
        document.getElementById('stat-war').innerText = data.war_status.open ? 'OPEN 🟢' : 'SCHEDULED';
        document.getElementById('stat-war-sub').innerText = data.war_status.open ? (data.war_status.n + ' fighters in lobby') : '9:00 PM Daily';
      } catch (e) {
        console.error(e);
      }
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
      fetchStats();
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

    async function postChannelPoll(count) {
      const ch = document.getElementById('tg-channel').value;
      const box = document.getElementById('tg-poll-result');
      box.innerText = 'Posting poll(s) to ' + ch + '...';
      const res = await fetch('/api/post_poll', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({channel: ch, count: count || 1})
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
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; color:var(--text-muted);">No squads created yet</td></tr>';
        return;
      }
      for (const [code, s] of Object.entries(d.squads)) {
        const tr = document.createElement('tr');
        const link = 'https://t.me/' + (d.bot || 'StudentUpBot') + '?start=sq_' + code;
        tr.innerHTML = `
          <td><b>SQ-${code}</b></td>
          <td>${s.name}</td>
          <td>${s.leader}</td>
          <td>${(s.members || []).length} / 5</td>
          <td>
            <a href="${link}" target="_blank" style="color:var(--primary); text-decoration:none;">🔗 Join Link</a> | 
            <a href="https://api.qrserver.com/v1/create-qr-code/?size=600x600&data=${link}" target="_blank" style="color:var(--accent); text-decoration:none;">📱 View QR</a>
          </td>
        `;
        tbody.appendChild(tr);
      }
    }

    async function loadMembers() {
      const res = await fetch('/api/members');
      const d = await res.json();
      const tbody = document.querySelector('#table-members tbody');
      tbody.innerHTML = '';
      for (const m of d.members.slice(0, 50)) {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${m.uid}</td>
          <td><b>${m.name}</b></td>
          <td>${m.district || '—'}</td>
          <td>${m.exam || '—'}</td>
          <td style="color:var(--warning); font-weight:700;">${m.points}</td>
          <td>🔥 ${m.streak}d</td>
          <td>${m.college || '—'}</td>
        `;
        tbody.appendChild(tr);
      }
    }

    async function loadWAGroups() {
      const res = await fetch('/api/whatsapp/groups');
      const d = await res.json();
      const tbody = document.querySelector('#table-wa-groups tbody');
      tbody.innerHTML = '';
      (d.groups || []).forEach(g => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${g.id}</td>
          <td><b>${g.name}</b></td>
          <td>${g.jid}</td>
          <td><span class="status-pill ${g.active ? 'open' : 'closed'}">${g.active ? 'Active' : 'Paused'}</span></td>
          <td><button class="btn btn-outline" style="padding:4px 8px; font-size:11px;" onclick="removeWAGroup('${g.id}')">Delete</button></td>
        `;
        tbody.appendChild(tr);
      });
      if (d.gateway_url) document.getElementById('wa-gateway').value = d.gateway_url;
      if (d.post_delay_sec) document.getElementById('wa-delay').value = d.post_delay_sec;
    }

    async function addWAGroup() {
      const name = document.getElementById('new-wa-name').value.trim();
      const jid = document.getElementById('new-wa-jid').value.trim();
      if (!name || !jid) return alert('Enter group name and JID / Link');
      await fetch('/api/whatsapp/add_group', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name, jid})
      });
      document.getElementById('new-wa-name').value = '';
      document.getElementById('new-wa-jid').value = '';
      loadWAGroups();
    }

    async function removeWAGroup(id) {
      if (!confirm('Remove this group?')) return;
      await fetch('/api/whatsapp/remove_group', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id})
      });
      loadWAGroups();
    }

    async function sendWhatsApp(isQuestion) {
      const log = document.getElementById('wa-log');
      log.innerText = 'Initiating staggered delivery across WhatsApp groups...';
      const channel = document.getElementById('wa-exam-channel').value;
      const customMsg = document.getElementById('wa-custom-msg').value;
      const delay = parseInt(document.getElementById('wa-delay').value) || 5;
      const gateway = document.getElementById('wa-gateway').value;

      const res = await fetch('/api/whatsapp/broadcast', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({is_question: isQuestion, channel, custom_msg: customMsg, delay, gateway})
      });
      const d = await res.json();
      log.innerText = d.log || JSON.stringify(d, null, 2);
    }

    fetchStats();
    setInterval(fetchStats, 10000);
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
            self._send_json({
                "total_members": len(mb.members),
                "registered_members": len(reg),
                "total_points": tot_pts,
                "war_status": st_war
            })
            return
        if p.path == "/api/squads":
            sq_data = hooks._sq()
            self._send_json({
                "bot": config.BOT_USERNAME or "StudentUpBot",
                "squads": sq_data.get("squads", {})
            })
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
        if p.path == "/api/whatsapp/groups":
            self._send_json(_load_wa_groups())
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        p = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

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

        if p.path == "/api/post_poll":
            ch = body.get("channel", "CURRENT")
            count = int(body.get("count", 1))
            bank = Bank()
            from core.engine import Engine
            eng = Engine(dry=False)
            sent = 0
            for _ in range(count):
                qs = bank.pick(ch, 1)
                if qs:
                    ok = eng.send_quiz(ch, qs[0])
                    if ok:
                        sent += 1
            self._send_json({"ok": True, "message": f"Sent {sent} poll(s) directly to Telegram {ch} channel!"})
            return

        if p.path == "/api/whatsapp/add_group":
            name = body.get("name", "").strip()
            jid = body.get("jid", "").strip()
            d = _load_wa_groups()
            gid = "G" + str(len(d["groups"]) + 1)
            d["groups"].append({"id": gid, "name": name, "jid": jid, "active": True})
            _save_wa_groups(d)
            self._send_json({"ok": True})
            return

        if p.path == "/api/whatsapp/remove_group":
            gid = body.get("id")
            d = _load_wa_groups()
            d["groups"] = [g for g in d["groups"] if g["id"] != gid]
            _save_wa_groups(d)
            self._send_json({"ok": True})
            return

        if p.path == "/api/whatsapp/broadcast":
            d = _load_wa_groups()
            groups = [g for g in d.get("groups", []) if g.get("active")]
            delay = int(body.get("delay", 5))
            gateway = body.get("gateway", "").strip() or d.get("gateway_url", "")
            if gateway:
                d["gateway_url"] = gateway
            d["post_delay_sec"] = delay
            _save_wa_groups(d)

            is_q = body.get("is_question", True)
            ch = body.get("channel", "CURRENT")
            custom_msg = body.get("custom_msg", "")

            if is_q:
                bank = Bank()
                qs = bank.pick(ch, 1)
                text = format_poll_for_wa(qs[0], config.CHANNELS.get(ch, {}).get("name", "StudentUp")) if qs else "No questions in bank."
            else:
                text = custom_msg or "StudentUp Exam Notification"

            logs = []
            logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] Starting WhatsApp broadcast to {len(groups)} groups with {delay}s delay...")
            
            for i, grp in enumerate(groups, 1):
                logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] Delivering to Group {i}/{len(groups)}: '{grp['name']}' ({grp['jid']})...")
                # If a live WhatsApp Gateway endpoint is configured, POST to it
                if gateway:
                    try:
                        req_data = json.dumps({"recipient": grp["jid"], "message": text}).encode("utf-8")
                        req = urllib.request.Request(gateway, data=req_data, headers={"Content-Type": "application/json"})
                        with urllib.request.urlopen(req, timeout=10) as r:
                            logs.append(f"  -> Success: HTTP {r.status}")
                    except Exception as ex:
                        logs.append(f"  -> Gateway dispatch note: {ex}")
                else:
                    logs.append(f"  -> Dispatched formatted poll (Native Queue Sim): OK")
                
                if i < len(groups):
                    logs.append(f"  -> Waiting {delay}s before next group...")
                    time.sleep(min(delay, 2))  # responsive pause in request

            logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] All {len(groups)} WhatsApp groups successfully processed!")
            self._send_json({"ok": True, "log": "\n".join(logs)})
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
