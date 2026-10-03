#!/usr/bin/env node
/**
 * STUDENTUP — REAL WHATSAPP GATEWAY BRIDGE (Baileys / WhatsApp Web Multi-Device)
 * ------------------------------------------------------------------------------
 * This replaces the old simulated gateway. It opens a REAL WhatsApp Web session:
 *   • QR login            → scan with WhatsApp > Linked Devices > Link a Device
 *   • Pairing-code login  → 8-char code typed on the phone (no camera needed)
 *   • Auto-reconnect      → session credentials persisted in gateway/auth/
 *   • Group sync          → lists every group the account has actually joined
 *   • Send                → text, media-by-URL (image / pdf / video) and NATIVE
 *                           WhatsApp polls (tappable options, option counts)
 *
 * HTTP API (consumed by scripts/core/whatsapp_pipeline.py):
 *   GET  /status          → { status, phone, device_name, qr_data, pairing_code, ... }
 *   POST /login/qr        → begin QR login, returns QR as data-URL image
 *   POST /login/code      → { phone } begin pairing-code login, returns the code
 *   POST /logout          → unlink device and wipe stored credentials
 *   GET  /groups          → [{ jid, name, participants }]  (real joined groups)
 *   POST /send            → { jid, text?, attachment?, poll:{name, options}? }
 *
 * Run:  cd gateway && npm install && node wa_bridge.js
 * Port: 3900 (override with WA_BRIDGE_PORT)
 */

const http = require('http');
const fs = require('fs');
const path = require('path');
const pino = require('pino');
const QRCode = require('qrcode');
const {
  default: makeWASocket,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  DisconnectReason,
  jidNormalizedUser,
} = require('@whiskeysockets/baileys');

const PORT = parseInt(process.env.WA_BRIDGE_PORT || '3900', 10);
const AUTH_DIR = path.join(__dirname, 'auth');
const logger = pino({ level: process.env.WA_BRIDGE_LOG || 'warn' });

// ---------------------------------------------------------------- state
const state = {
  sock: null,
  status: 'offline',          // offline | connecting | qr_ready | code_ready | connected | logged_out
  qrString: null,
  qrDataUrl: null,
  pairingCode: null,
  pairingPhone: null,
  me: null,                   // { id, name }
  lastError: null,
  connectedAt: null,
  starting: false,
  groupsCache: [],
  groupsCacheAt: 0,
};

function log(msg) {
  console.log(`[${new Date().toISOString().slice(11, 19)}] ${msg}`);
}

// ---------------------------------------------------------------- socket
async function startSock({ wantPairingCode = null } = {}) {
  if (state.starting) return;
  state.starting = true;
  try {
    // Tear down any previous socket quietly
    if (state.sock) {
      try { state.sock.ev.removeAllListeners('connection.update'); } catch (_) {}
      try { state.sock.end(undefined); } catch (_) {}
      state.sock = null;
    }

    state.status = 'connecting';
    state.qrString = null;
    state.qrDataUrl = null;
    state.lastError = null;

    const { state: authState, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    let version;
    try {
      ({ version } = await fetchLatestBaileysVersion());
    } catch (_) {
      version = undefined; // fall back to library default
    }

    const sock = makeWASocket({
      version,
      auth: authState,
      logger,
      printQRInTerminal: false,
      browser: ['StudentUp Dispatch Node', 'Chrome', '120.0'],
      syncFullHistory: false,
      markOnlineOnConnect: false, // keep phone notifications working
    });
    state.sock = sock;

    sock.ev.on('creds.update', saveCreds);

    // Pairing-code flow (no QR camera needed)
    if (wantPairingCode && !authState.creds.registered) {
      setTimeout(async () => {
        try {
          const digits = String(wantPairingCode).replace(/\D/g, '');
          const code = await sock.requestPairingCode(digits);
          state.pairingCode = code.match(/.{1,4}/g).join('-');
          state.pairingPhone = wantPairingCode;
          state.status = 'code_ready';
          log(`Pairing code for +${digits}: ${state.pairingCode}`);
        } catch (e) {
          state.lastError = `pairing code failed: ${e.message || e}`;
          log(state.lastError);
        }
      }, 3500);
    }

    sock.ev.on('connection.update', async (u) => {
      const { connection, lastDisconnect, qr } = u;

      if (qr) {
        state.qrString = qr;
        try {
          state.qrDataUrl = await QRCode.toDataURL(qr, { margin: 1, width: 400 });
        } catch (_) { state.qrDataUrl = null; }
        if (state.status !== 'code_ready') state.status = 'qr_ready';
        log('New login QR generated (scan within ~60s)');
      }

      if (connection === 'open') {
        state.status = 'connected';
        state.qrString = null;
        state.qrDataUrl = null;
        state.pairingCode = null;
        state.connectedAt = new Date().toISOString().replace('T', ' ').slice(0, 16);
        const id = jidNormalizedUser(sock.user?.id || '');
        state.me = { id, name: sock.user?.name || 'WhatsApp Account', phone: '+' + id.split('@')[0].split(':')[0] };
        log(`✅ CONNECTED as ${state.me.phone} (${state.me.name})`);
        refreshGroups().catch(() => {});
      }

      if (connection === 'close') {
        const code = lastDisconnect?.error?.output?.statusCode;
        const loggedOut = code === DisconnectReason.loggedOut || code === 401 || code === 403;
        if (loggedOut) {
          state.status = 'logged_out';
          state.me = null;
          log('Session logged out from phone — wiping stored credentials.');
          try { fs.rmSync(AUTH_DIR, { recursive: true, force: true }); } catch (_) {}
        } else if (code === DisconnectReason.restartRequired) {
          log('Restart required — reconnecting...');
          setTimeout(() => startSock().catch(() => {}), 1200);
        } else if (state.status === 'connected' || hasSavedCreds()) {
          state.status = 'connecting';
          log(`Connection closed (code ${code}) — auto-reconnecting in 4s...`);
          setTimeout(() => startSock().catch(() => {}), 4000);
        } else {
          // QR expired / never scanned
          if (state.status !== 'code_ready') state.status = 'offline';
          state.lastError = `connection closed (code ${code})`;
        }
      }
    });
  } finally {
    state.starting = false;
  }
}

function hasSavedCreds() {
  try { return fs.existsSync(path.join(AUTH_DIR, 'creds.json')); } catch (_) { return false; }
}

async function waitFor(predicate, timeoutMs = 25000, stepMs = 300) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    if (predicate()) return true;
    await new Promise((r) => setTimeout(r, stepMs));
  }
  return predicate();
}

// ---------------------------------------------------------------- groups
async function refreshGroups() {
  if (!state.sock || state.status !== 'connected') return [];
  const map = await state.sock.groupFetchAllParticipating();
  state.groupsCache = Object.values(map).map((g) => ({
    jid: g.id,
    name: g.subject || g.id,
    participants: (g.participants || []).length,
    is_community: !!g.isCommunity,
    announce: !!g.announce,
  }));
  state.groupsCacheAt = Date.now();
  return state.groupsCache;
}

// ---------------------------------------------------------------- sending
const IMG_EXT = /\.(jpe?g|png|webp)(\?|$)/i;
const VID_EXT = /\.(mp4|mov|mkv|webm)(\?|$)/i;
const AUD_EXT = /\.(mp3|ogg|m4a|aac|opus)(\?|$)/i;

async function sendPayload(body) {
  if (!state.sock || state.status !== 'connected') {
    throw new Error('WhatsApp not connected — login first (QR / pairing code)');
  }
  const jid = String(body.jid || body.recipient || '').trim();
  if (!jid) throw new Error('missing jid');

  const results = [];

  // 1. Native tappable WhatsApp poll
  if (body.poll && Array.isArray(body.poll.options) && body.poll.options.length >= 2) {
    const name = String(body.poll.name || 'Quiz').slice(0, 255);
    const values = body.poll.options.map((o) => String(o).slice(0, 100)).slice(0, 12);
    await state.sock.sendMessage(jid, {
      poll: { name, values, selectableCount: 1 },
    });
    results.push('poll');
  }

  // 2. Media attachment by URL (image / video / audio / document)
  if (body.attachment) {
    const url = String(body.attachment).trim();
    const caption = body.poll ? undefined : (body.text || body.message || undefined);
    let msg;
    if (IMG_EXT.test(url)) msg = { image: { url }, caption };
    else if (VID_EXT.test(url)) msg = { video: { url }, caption };
    else if (AUD_EXT.test(url)) msg = { audio: { url }, mimetype: 'audio/mpeg' };
    else {
      const fileName = decodeURIComponent(url.split('/').pop().split('?')[0] || 'document.pdf');
      msg = { document: { url }, fileName, caption, mimetype: fileName.toLowerCase().endsWith('.pdf') ? 'application/pdf' : undefined };
    }
    await state.sock.sendMessage(jid, msg);
    results.push('attachment');
    if (!caption && !body.poll && (body.text || body.message)) {
      await state.sock.sendMessage(jid, { text: String(body.text || body.message) });
      results.push('text');
    }
  } else if (!body.poll && (body.text || body.message)) {
    // 3. Plain text
    await state.sock.sendMessage(jid, { text: String(body.text || body.message) });
    results.push('text');
  } else if (body.poll && (body.text || body.message) && body.send_text_too) {
    await state.sock.sendMessage(jid, { text: String(body.text || body.message) });
    results.push('text');
  }

  if (!results.length) throw new Error('nothing to send (need text, attachment or poll)');
  return results;
}

// ---------------------------------------------------------------- http api
function json(res, code, obj) {
  const data = JSON.stringify(obj);
  res.writeHead(code, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
  res.end(data);
}

function statusPayload() {
  return {
    ok: true,
    status: state.status,
    connected: state.status === 'connected',
    phone: state.me ? state.me.phone : (state.pairingPhone || null),
    device_name: state.me ? `${state.me.name} (Real WhatsApp Web)` : 'StudentUp Dispatch Node',
    qr_data: state.qrDataUrl,
    pairing_code: state.pairingCode,
    connected_at: state.connectedAt,
    groups_count: state.groupsCache.length,
    has_saved_session: hasSavedCreds(),
    last_error: state.lastError,
  };
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  let body = {};
  if (req.method === 'POST') {
    body = await new Promise((resolve) => {
      let raw = '';
      req.on('data', (c) => { raw += c; if (raw.length > 5e6) req.destroy(); });
      req.on('end', () => { try { resolve(raw ? JSON.parse(raw) : {}); } catch (_) { resolve({}); } });
    });
  }

  try {
    // ---- status
    if (url.pathname === '/status') return json(res, 200, statusPayload());

    // ---- QR login
    if (url.pathname === '/login/qr' && req.method === 'POST') {
      if (state.status === 'connected') return json(res, 200, statusPayload());
      await startSock();
      await waitFor(() => state.qrDataUrl || state.status === 'connected', 30000);
      return json(res, 200, statusPayload());
    }

    // ---- pairing-code login
    if (url.pathname === '/login/code' && req.method === 'POST') {
      if (state.status === 'connected') return json(res, 200, statusPayload());
      const phone = String(body.phone || '').trim();
      if (!phone.replace(/\D/g, '')) return json(res, 400, { ok: false, error: 'phone number required' });
      state.pairingCode = null;
      await startSock({ wantPairingCode: phone });
      await waitFor(() => state.pairingCode || state.status === 'connected', 30000);
      return json(res, 200, statusPayload());
    }

    // ---- logout
    if (url.pathname === '/logout' && req.method === 'POST') {
      try { if (state.sock) await state.sock.logout(); } catch (_) {}
      try { fs.rmSync(AUTH_DIR, { recursive: true, force: true }); } catch (_) {}
      state.status = 'offline';
      state.me = null;
      state.groupsCache = [];
      return json(res, 200, { ok: true, status: 'offline' });
    }

    // ---- groups
    if (url.pathname === '/groups') {
      if (state.status !== 'connected') {
        return json(res, 409, { ok: false, error: 'not connected', status: state.status });
      }
      const fresh = url.searchParams.get('fresh') === '1' || Date.now() - state.groupsCacheAt > 60000;
      const groups = fresh ? await refreshGroups() : state.groupsCache;
      return json(res, 200, { ok: true, groups, count: groups.length });
    }

    // ---- auto-join a group via invite link (paste link → bot joins itself)
    if (url.pathname === '/join' && req.method === 'POST') {
      if (!state.sock || state.status !== 'connected') {
        return json(res, 409, { ok: false, error: 'not connected — login first' });
      }
      const link = String(body.link || '').trim();
      const m = link.match(/chat\.whatsapp\.com\/(?:invite\/)?([A-Za-z0-9]+)/);
      if (!m) return json(res, 400, { ok: false, error: 'invalid WhatsApp invite link' });
      try {
        const jid = await state.sock.groupAcceptInvite(m[1]);
        let name = jid, participants = 0;
        try {
          const meta = await state.sock.groupMetadata(jid);
          name = meta.subject || jid;
          participants = (meta.participants || []).length;
        } catch (_) {}
        refreshGroups().catch(() => {});
        return json(res, 200, { ok: true, jid, name, participants, joined: true });
      } catch (e) {
        const msg = String(e.message || e);
        // already a member → try to resolve the group info from invite
        if (/already|conflict|409/i.test(msg)) {
          try {
            const info = await state.sock.groupGetInviteInfo(m[1]);
            return json(res, 200, { ok: true, jid: info.id, name: info.subject || info.id, participants: info.size || 0, joined: false, note: 'already a member' });
          } catch (_) {}
        }
        return json(res, 500, { ok: false, error: msg });
      }
    }

    // ---- send
    if (url.pathname === '/send' && req.method === 'POST') {
      const sent = await sendPayload(body);
      return json(res, 200, { ok: true, sent });
    }

    return json(res, 404, { ok: false, error: 'unknown endpoint' });
  } catch (e) {
    return json(res, 500, { ok: false, error: String(e.message || e) });
  }
});

server.listen(PORT, '0.0.0.0', () => {
  log(`🛡️  StudentUp WhatsApp Bridge listening on :${PORT}`);
  if (hasSavedCreds()) {
    log('Saved session found — auto-reconnecting...');
    startSock().catch((e) => log(`startup error: ${e.message || e}`));
  } else {
    log('No saved session. POST /login/qr or /login/code to link WhatsApp.');
  }
});
