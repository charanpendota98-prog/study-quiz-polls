#!/usr/bin/env python3
"""
STUDENTUP — FULL CONTROL WEB DASHBOARD & ADVANCED AUTOMATION HUB
Features:
  1. Dynamic Channel Manager:
     - Add any new Telegram Channel / Exam name.
     - Auto-configures syllabus subjects, exam blueprint, and builds fresh polls automatically.
  2. WhatsApp 100+ / 150+ Groups Anti-Ban Engine:
     - Group categories (POLICE, CENTRAL, SSC, RAILWAY, BANKING, TSPSC, APPSC).
     - Automated targeted delivery: Police groups get Police polls, Central get Central/SSC/RRB polls, etc.
     - Anti-Ban protection: Zero-width invisible text jitter (unique hash per group), human-like randomized delays (4-12s), safety pauses.
     - Central broadcast with image/attachment & rich text.
  3. Live Metrics, District Wars, Squad Arena & Google Sheet CRM Sync.
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
from core import hooks, districtwar, arena, campus, crm, whatsapp_bot, channel_router
from core.telegram import Telegram

PORT = int(config.env("DASHBOARD_PORT", "5000"))

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>StudentUp — Ultimate Control & WhatsApp Anti-Ban Hub</title>
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
      --text: #f8fafc;
      --text-muted: #94a3b8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }
    body { background: var(--bg); color: var(--text); padding: 24px; min-height: 100vh; }
    .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 20px; margin-bottom: 24px; }
    .header h1 { font-size: 24px; font-weight: 800; display: flex; align-items: center; gap: 10px; }
    .badge-live { background: rgba(16, 185, 129, 0.15); color: var(--accent); border: 1px solid var(--accent); padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; }
    .badge-shield { background: rgba(139, 92, 246, 0.15); color: var(--purple); border: 1px solid var(--purple); padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; }
    .grid-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
    .stat-card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 18px; }
    .stat-card .label { font-size: 13px; color: var(--text-muted); font-weight: 500; }
    .stat-card .val { font-size: 30px; font-weight: 800; margin-top: 6px; }
    .stat-card .desc { font-size: 12px; color: var(--text-muted); margin-top: 4px; }
    .tabs { display: flex; gap: 8px; margin-bottom: 20px; border-bottom: 1px solid var(--border); padding-bottom: 10px; overflow-x: auto; }
    .tab-btn { background: transparent; border: none; color: var(--text-muted); font-size: 14px; font-weight: 600; padding: 8px 16px; border-radius: 8px; cursor: pointer; transition: all 0.2s; white-space: nowrap; }
    .tab-btn.active { background: var(--primary); color: #fff; }
    .tab-pane { display: none; }
    .tab-pane.active { display: block; }
    .panel-card { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 22px; margin-bottom: 20px; }
    .panel-card h2 { font-size: 18px; margin-bottom: 14px; display: flex; align-items: center; gap: 8px; }
    .btn { background: var(--primary); color: #fff; border: none; padding: 10px 16px; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; transition: background 0.2s; display: inline-flex; align-items: center; gap: 6px; }
    .btn:hover { background: var(--primary-hover); }
    .btn-accent { background: var(--accent); }
    .btn-accent:hover { background: var(--accent-hover); }
    .btn-purple { background: var(--purple); }
    .btn-danger { background: var(--danger); }
    .btn-outline { background: transparent; border: 1px solid var(--border); color: var(--text); }
    .btn-outline:hover { background: var(--border); }
    input, select, textarea { width: 100%; padding: 10px 14px; background: #0f172a; border: 1px solid var(--border); border-radius: 8px; color: var(--text); font-size: 13px; margin-top: 6px; margin-bottom: 14px; }
    input:focus, select:focus, textarea:focus { outline: 2px solid var(--primary); border-color: transparent; }
    table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 13px; }
    th, td { text-align: left; padding: 11px 13px; border-bottom: 1px solid var(--border); }
    th { color: var(--text-muted); font-weight: 600; background: rgba(15, 23, 42, 0.6); }
    .log-box { background: #050811; border: 1px solid var(--border); border-radius: 8px; padding: 14px; font-family: monospace; font-size: 12px; max-height: 240px; overflow-y: auto; color: #38bdf8; white-space: pre-wrap; margin-top: 12px; }
    .status-pill { display: inline-block; padding: 3px 8px; border-radius: 6px; font-size: 11px; font-weight: 700; text-transform: uppercase; }
    .status-pill.open { background: rgba(16, 185, 129, 0.2); color: #34d399; }
    .status-pill.closed { background: rgba(239, 68, 68, 0.2); color: #f87171; }
    .category-tag { background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); padding: 3px 7px; border-radius: 4px; font-size: 11px; font-weight: 600; }
  </style>
</head>
<body>
  <div class="header">
    <div>
      <h1>🚀 StudentUp Central Management & Anti-Ban Hub</h1>
      <p style="color:var(--text-muted); font-size:13px; margin-top:4px;">100+ WhatsApp Groups Anti-Ban Dispatcher & Dynamic Channels Controller</p>
    </div>
    <div style="display:flex; gap:10px; align-items:center;">
      <span class="badge-shield">🛡️ ANTI-BAN STEALTH ON</span>
      <span class="badge-live">● ENGINE LIVE</span>
      <button class="btn btn-outline" onclick="location.reload()">🔄 Refresh</button>
    </div>
  </div>

  <div class="grid-stats">
    <div class="stat-card">
      <div class="label">WhatsApp Groups Active</div>
      <div class="val" id="stat-wa-count" style="color:#60a5fa;">...</div>
      <div class="desc">100+ groups safe queue</div>
    </div>
    <div class="stat-card">
      <div class="label">Telegram Channels</div>
      <div class="val" id="stat-tg-count" style="color:var(--purple);">...</div>
      <div class="desc">Live exam channels</div>
    </div>
    <div class="stat-card">
      <div class="label">Registered Students</div>
      <div class="val" id="stat-reg" style="color:var(--accent);">...</div>
      <div class="desc">Verified profiles in CRM</div>
    </div>
    <div class="stat-card">
      <div class="label">Total Points Earned</div>
      <div class="val" id="stat-points" style="color:var(--warning);">...</div>
      <div class="desc">Active gamification balance</div>
    </div>
  </div>

  <div class="tabs">
    <button class="tab-btn active" onclick="switchTab('tab-wa-dispatch')">🛡️ WhatsApp 100+ Anti-Ban Dispatcher</button>
    <button class="tab-btn" onclick="switchTab('tab-dynamic-channels')">📢 Telegram Channels & Dynamic Builder</button>
    <button class="tab-btn" onclick="switchTab('tab-control')">⚡ Fast Actions & District War</button>
    <button class="tab-btn" onclick="switchTab('tab-squads')">👥 Squad Wars & Arena</button>
    <button class="tab-btn" onclick="switchTab('tab-members')">📋 Registered Members & CRM</button>
  </div>

  <!-- TAB 1: WHATSAPP ANTI-BAN DISPATCHER -->
  <div id="tab-wa-dispatch" class="tab-pane active">
    <div class="panel-card">
      <h2>🛡️ Multi-Group Targeted Dispatcher (Anti-Ban & Stealth)</h2>
      <p style="color:var(--text-muted); font-size:13px; margin-bottom:16px;">
        Auto-matches exam syllabus: <b>Police groups receive Police polls</b>, <b>Central/SSC/RRB receive Central polls</b>, and <b>Banking groups receive Banking polls</b>. Invisible zero-width text alters every post hash so WhatsApp anti-spam algorithms cannot detect mass broadcasts.
      </p>

      <div style="display:grid; grid-template-columns: 2fr 1fr; gap:20px;">
        <div>
          <label>Target Group Category Filter:</label>
          <select id="wa-target-category">
            <option value="ALL">🌐 Broadcast to ALL Connected Groups (100+ Mode)</option>
            <option value="POLICE">👮 Police Exam Groups (TS Police SI, AP Police Constable)</option>
            <option value="SSC">🏛️ Central Jobs & SSC Groups (CGL, CHSL, MTS)</option>
            <option value="RAILWAY">🚆 Railway RRB Groups (NTPC, Group D, ALP)</option>
            <option value="BANKING">🏦 Banking Aspirants Groups (SBI, IBPS PO/Clerk)</option>
            <option value="TSPSC">📘 TSPSC Groups (Telangana Group 2, 3, 4)</option>
            <option value="APPSC">📗 APPSC Groups (Andhra Group 2, 4)</option>
          </select>

          <label>Optional: Central Announcement or Message Text (Leave blank to send auto-built exam polls):</label>
          <textarea id="wa-broadcast-msg" rows="4" placeholder="Enter custom update or study notification..."></textarea>

          <label>Optional Image / Attachment URL (Posts photo along with text):</label>
          <input type="text" id="wa-attachment-url" placeholder="https://example.com/daily-current-affairs-poster.jpg">

          <div style="display:flex; gap:10px; margin-top:8px;">
            <button class="btn btn-accent" onclick="runWABroadcast(true)">🚀 Send Syllabus Quiz Polls (Category-Matched)</button>
            <button class="btn btn-purple" onclick="runWABroadcast(false)">📢 Send Custom Announcement with Anti-Ban</button>
          </div>
        </div>

        <div style="background:#0f172a; border:1px solid var(--border); border-radius:10px; padding:16px;">
          <h3 style="font-size:14px; margin-bottom:12px; color:#38bdf8;">⚙️ Anti-Ban Safeguards</h3>
          <div style="font-size:12px; line-height:1.7; color:var(--text-muted);">
            ✔ <b>Zero-Width Hash Jitter:</b> Unique binary string per group.<br>
            ✔ <b>Dynamic Delay:</b> 4 to 12s randomized human intervals.<br>
            ✔ <b>Smart Safety Pauses:</b> Automatic rest periods every 15 groups.<br>
            ✔ <b>Exam Isolation:</b> Police groups only get Police polls.<br>
          </div>
          <div style="margin-top:14px;">
            <label style="font-size:12px;">WhatsApp Webhook / Gateway Endpoint (Optional):</label>
            <input type="text" id="wa-gateway-input" placeholder="http://localhost:3000/send or GreenAPI/UltraMsg">
          </div>
        </div>
      </div>

      <div style="margin-top:24px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <h3>📋 Managed WhatsApp Groups Directory</h3>
          <button class="btn btn-outline" onclick="loadWAGroups()">🔄 Refresh Groups</button>
        </div>
        <table id="table-wa-groups">
          <thead>
            <tr>
              <th>ID</th>
              <th>Group Title</th>
              <th>Category</th>
              <th>JID / Link</th>
              <th>Status</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>

        <div style="display:flex; gap:10px; margin-top:16px; background:#0f172a; padding:12px; border-radius:8px;">
          <input type="text" id="new-wa-title" placeholder="Group Title (e.g. Hyderabad TS Police SI Prep)">
          <input type="text" id="new-wa-jid" placeholder="Group JID or Invite link">
          <select id="new-wa-category" style="width:200px;">
            <option value="AUTO">🤖 Auto-Detect from Name</option>
            <option value="POLICE">POLICE</option>
            <option value="SSC">SSC / Central</option>
            <option value="RAILWAY">RAILWAY</option>
            <option value="BANKING">BANKING</option>
            <option value="TSPSC">TSPSC</option>
            <option value="APPSC">APPSC</option>
            <option value="CURRENT">Current Affairs</option>
          </select>
          <button class="btn btn-accent" style="white-space:nowrap;" onclick="addNewWAGroup()">➕ Connect Group</button>
        </div>
      </div>

      <div id="wa-log-box" class="log-box" style="margin-top:16px;">WhatsApp Anti-Ban Dispatch status ready.</div>
    </div>
  </div>

  <!-- TAB 2: DYNAMIC CHANNELS & EXAM BUILDER -->
  <div id="tab-dynamic-channels" class="tab-pane">
    <div class="panel-card">
      <h2>📢 Telegram Channels & Dynamic Exam Builder</h2>
      <p style="color:var(--text-muted); font-size:13px; margin-bottom:16px;">
        Add any new Telegram Channel or Exam name. The system automatically builds syllabus subjects, question pool, and delivers exam-accurate polls without manual coding.
      </p>

      <div style="display:grid; grid-template-columns: 1fr 1fr; gap:20px;">
        <div style="background:#0f172a; padding:18px; border-radius:10px; border:1px solid var(--border);">
          <h3 style="font-size:15px; margin-bottom:12px;">➕ Register New Exam Channel</h3>
          <label>Channel / Exam Name:</label>
          <input type="text" id="new-ch-name" placeholder="e.g. TS Police Sub Inspector 2026">

          <label>Exam Category (or Auto-Detect):</label>
          <select id="new-ch-base">
            <option value="AUTO">🤖 Auto-Detect (SI/Constable -> POLICE, CGL -> SSC, etc.)</option>
            <option value="POLICE">Police Exams (SI / Constable / APSP / TSSP)</option>
            <option value="SSC">SSC Exams (CGL / CHSL / MTS / GD)</option>
            <option value="RAILWAY">Railway RRB (NTPC / Group D / ALP)</option>
            <option value="BANKING">Banking (IBPS PO / SBI Clerk / RRB)</option>
            <option value="TSPSC">TSPSC (Group 2, 3, 4)</option>
            <option value="APPSC">APPSC (Group 2, 4)</option>
            <option value="DEFENCE">Defence (NDA, CDS, AFCAT)</option>
            <option value="CURRENT">Current Affairs & Daily GK</option>
          </select>

          <label>Telegram Chat ID or @username (optional for preview):</label>
          <input type="text" id="new-ch-chatid" placeholder="@MyNewPoliceExamChannel or -100123456789">

          <button class="btn btn-accent" onclick="createNewChannel()">⚡ Register Channel & Auto-Build Polls</button>
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
        <h3>Active Telegram Channels Registry</h3>
        <table id="table-channels">
          <thead>
            <tr>
              <th>Channel Key</th>
              <th>Channel Title</th>
              <th>Base Exam Syllabus</th>
              <th>Audience</th>
              <th>Chat Target</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- TAB 3: FAST ACTIONS & DISTRICT WAR -->
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

  <!-- TAB 4: SQUADS & ARENA -->
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

  <!-- TAB 5: MEMBERS DIRECTORY -->
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
      if (id === 'tab-wa-dispatch') loadWAGroups();
      if (id === 'tab-dynamic-channels') loadChannels();
      if (id === 'tab-squads') loadSquads();
      if (id === 'tab-members') loadMembers();
    }

    async function fetchStats() {
      try {
        const res = await fetch('/api/stats');
        const data = await res.json();
        document.getElementById('stat-wa-count').innerText = data.wa_groups_count || '0';
        document.getElementById('stat-tg-count').innerText = data.channels_count || '0';
        document.getElementById('stat-reg').innerText = data.registered_members;
        document.getElementById('stat-points').innerText = data.total_points.toLocaleString();
      } catch (e) {
        console.error(e);
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
          <td><span class="category-tag">${g.category || 'GENERAL'}</span></td>
          <td style="font-family:monospace; font-size:12px;">${g.jid}</td>
          <td><span class="status-pill ${g.active ? 'open' : 'closed'}">${g.active ? 'Active' : 'Paused'}</span></td>
          <td><button class="btn btn-outline" style="padding:4px 8px; font-size:11px;" onclick="deleteWAGroup('${g.id}')">Delete</button></td>
        `;
        tbody.appendChild(tr);
      });
      if (d.gateway_url) document.getElementById('wa-gateway-input').value = d.gateway_url;
    }

    async function addNewWAGroup() {
      const name = document.getElementById('new-wa-title').value.trim();
      const jid = document.getElementById('new-wa-jid').value.trim();
      const category = document.getElementById('new-wa-category').value;
      if (!name || !jid) return alert('Enter group name and JID / Link');
      await fetch('/api/whatsapp/add_group', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name, jid, category})
      });
      document.getElementById('new-wa-title').value = '';
      document.getElementById('new-wa-jid').value = '';
      loadWAGroups();
      fetchStats();
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

    async function runWABroadcast(isQuestion) {
      const log = document.getElementById('wa-log-box');
      const cat = document.getElementById('wa-target-category').value;
      const msg = document.getElementById('wa-broadcast-msg').value;
      const att = document.getElementById('wa-attachment-url').value;
      const gateway = document.getElementById('wa-gateway-input').value;

      log.innerText = 'Starting Anti-Ban broadcast across category: ' + cat + '...';
      const res = await fetch('/api/whatsapp/broadcast', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          is_question: isQuestion,
          category: cat,
          custom_msg: msg,
          attachment: att,
          gateway: gateway
        })
      });
      const d = await res.json();
      log.innerText = d.log || JSON.stringify(d, null, 2);
    }

    async function loadChannels() {
      const res = await fetch('/api/channels');
      const d = await res.json();
      const tbody = document.querySelector('#table-channels tbody');
      const select = document.getElementById('post-poll-channel');
      tbody.innerHTML = '';
      select.innerHTML = '';
      for (const [key, ch] of Object.entries(d.channels || {})) {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><b>${key}</b></td>
          <td>${ch.emoji || '🎯'} ${ch.name}</td>
          <td><span class="category-tag">${ch.base_exam || key}</span></td>
          <td style="color:var(--text-muted);">${ch.audience || '—'}</td>
          <td style="font-family:monospace;">${ch.chat_id || ch.username || '—'}</td>
        `;
        tbody.appendChild(tr);

        const opt = document.createElement('option');
        opt.value = key;
        opt.innerText = (ch.emoji || '🎯') + ' ' + ch.name + ' (' + (ch.base_exam || key) + ')';
        select.appendChild(opt);
      }
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
      alert('Channel registered: ' + d.channel.name + ' (Syllabus: ' + d.channel.base_exam + ')');
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

    fetchStats();
    loadWAGroups();
    loadChannels();
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
            wa = whatsapp_bot.load_wa_registry()
            all_ch = channel_router.get_all_channels()
            self._send_json({
                "total_members": len(mb.members),
                "registered_members": len(reg),
                "total_points": tot_pts,
                "war_status": st_war,
                "wa_groups_count": len(wa.get("groups", [])),
                "channels_count": len(all_ch)
            })
            return

        if p.path == "/api/whatsapp/groups":
            self._send_json(whatsapp_bot.load_wa_registry())
            return

        if p.path == "/api/channels":
            self._send_json({"channels": channel_router.get_all_channels()})
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

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        p = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

        if p.path == "/api/whatsapp/add_group":
            name = body.get("name", "").strip()
            jid = body.get("jid", "").strip()
            cat = body.get("category", "AUTO")
            new_g = whatsapp_bot.add_group(name, jid, cat)
            self._send_json({"ok": True, "group": new_g})
            return

        if p.path == "/api/whatsapp/remove_group":
            gid = body.get("id")
            ok = whatsapp_bot.remove_group(gid)
            self._send_json({"ok": ok})
            return

        if p.path == "/api/whatsapp/broadcast":
            cat = body.get("category", "ALL")
            is_q = body.get("is_question", True)
            msg = body.get("custom_msg", "")
            att = body.get("attachment", "")
            gw = body.get("gateway", "").strip()
            if gw:
                reg = whatsapp_bot.load_wa_registry()
                reg["gateway_url"] = gw
                whatsapp_bot.save_wa_registry(reg)

            res = whatsapp_bot.broadcast(
                target_category=cat,
                is_question=is_q,
                custom_message=msg,
                attachment_url=att
            )
            self._send_json(res)
            return

        if p.path == "/api/channels/register":
            name = body.get("name", "").strip()
            exam_t = body.get("exam_type", "")
            chat_id = body.get("chat_id", "")
            info = channel_router.register_channel(name, chat_id=chat_id, exam_type=exam_t)
            self._send_json({"ok": True, "channel": info})
            return

        if p.path == "/api/post_poll":
            ch = body.get("channel", "CURRENT")
            count = int(body.get("count", 1))
            bank = Bank()
            from core.engine import Engine
            eng = Engine(dry=False)

            # Map to base exam if custom channel
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
            self._send_json({"ok": True, "message": f"Dispatched {sent} question(s) strictly adhering to {base} syllabus!"})
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
