/**
 * ╔══════════════════════════════════════════════════════════════════╗
 * ║  StudentUp CRM v2 — Google Sheet receiver (Apps Script Web App)   ║
 * ║  Paste this WHOLE file. Change only SECRET.                        ║
 * ╚══════════════════════════════════════════════════════════════════╝
 *
 * SETUP (one time, ~3 minutes):
 *  1. Create a Google Sheet → Extensions → Apps Script → delete sample code → paste this file → Save
 *  2. Change SECRET below to any long random text.
 *  3. Select function "setupSheet" → ▶ Run → allow permissions (creates all tabs + dashboard)
 *  4. Deploy → New deployment → type "Web app" → Execute as: Me · Who has access: Anyone → Deploy
 *  5. Copy the Web app URL (…/exec) → bot .env:
 *        SHEET_WEBAPP_URL=<url>
 *        SHEET_SECRET=<same SECRET>
 *  6. In the bot: /sheet  → "Sync all now"
 *
 *  ⚠ After ANY later code edit: Deploy → Manage deployments → ✏ → Version: New → Deploy.
 *
 * HOW DATA FLOWS (all automatic, from the bot):
 *  • members   — upsert on every registration/points change; full resync nightly 23:30 (writes are by
 *                COLUMN NAME, so you may reorder/add columns; missing headers are appended automatically)
 *  • rounds    — Top-10 of every quiz round (round_id, channel, rank, name, district, score)
 *  • campus    — every college event: one row per student (event, college, rank, score, %)
 *  • colleges  — one row per college (students, tests, avg %, ambassador) refreshed nightly
 *  • partners  — offers + voucher counts (redeemed / pending) refreshed nightly
 *  • campaigns — every /msg campaign with delivery numbers
 *  • daily     — one snapshot row per day (members, active, new, TS/AP, answers) — sent by the bot 23:35
 *  • log       — last 500 requests
 *  📊 Dashboard — live formulas over the tabs above.
 */

var SECRET = "CHANGE-ME-long-random-string";

var TABS = {
  members: ["tg_id", "name", "username", "mobile", "state", "district", "qualification", "mandal", "exam", "lang",
    "registered_at", "source", "points", "correct", "total", "accuracy", "streak", "best_streak", "level",
    "last_active", "follow", "college", "branch", "year", "campus_event", "tests", "best_pct", "last_pct",
    "referred_by", "referrals", "verified_channels", "coach_streak", "badges", "ambassador", "dm_blocked", "updated_at"],
  rounds: ["ts", "round_id", "channel", "rank", "tg_id", "name", "district", "correct", "total", "points"],
  campus: ["ts", "event", "college", "district", "rank", "tg_id", "name", "phone", "branch", "year", "correct", "total", "pct", "points"],
  colleges: ["college", "district", "students", "with_phone", "tests", "avg_last_pct", "improved", "ambassador", "last_event", "updated_at"],
  partners: ["partner_id", "name", "type", "district", "mandal", "status", "offers", "vouchers_issued", "redeemed", "pending", "plan", "updated_at"],
  campaigns: ["ts", "by", "audience", "total", "sent", "blocked", "failed", "text"],
  daily: ["date", "members", "with_mobile", "active_today", "new_today", "ts_members", "ap_members", "answers_today", "rounds_today", "colleges", "partners"],
  requests: ["ts", "req_id", "tg_id", "name", "college", "district", "status", "event_code", "created_at"],
  log: ["ts", "action", "rows", "ok", "error"]
};
var KEYS = { members: "tg_id", colleges: "college", partners: "partner_id" };   // upsert keys

// ─────────────────────────────────────────────────────────── HTTP entry points
function doPost(e) {
  var out = { ok: false }, body = {}, n = 0;
  try {
    body = JSON.parse((e && e.postData && e.postData.contents) || "{}");
    if (body.secret !== SECRET) { out.error = "bad secret"; log_(body.action, 0, false, out.error); return json_(out); }
    var lock = LockService.getScriptLock(); lock.waitLock(28000);
    try {
      switch (body.action) {
        case "upsert":  n = upsert_("members", [body.row], body.ts); break;
        case "bulk":    n = upsert_("members", body.rows || [], body.ts); break;
        case "round":   n = append_("rounds", body.rows || [], body.ts, true); break;
        case "campus":  n = append_("campus", body.rows || [], body.ts, true); break;
        case "colleges": n = upsert_("colleges", body.rows || [], body.ts); break;
        case "partners": n = upsert_("partners", body.rows || [], body.ts); break;
        case "campaign": n = append_("campaigns", [body.row], body.ts, false); break;
        case "request":  n = append_("requests", [body.row], body.ts, false); break;
        case "daily":   n = daily_(body.row); break;
        case "ping":    n = 0; break;
        default: throw new Error("unknown action: " + body.action);
      }
      out.ok = true; out.rows = n;
    } finally { lock.releaseLock(); }
  } catch (err) { out.error = String(err); }
  log_(body.action, n, out.ok, out.error || "");
  return json_(out);
}

function doGet() {
  var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("members");
  return json_({ ok: true, service: "studentup-crm", version: 2, members: sh ? Math.max(sh.getLastRow() - 1, 0) : 0 });
}

// ─────────────────────────────────────────────────────────── one-time setup
function setupSheet() {
  Object.keys(TABS).forEach(function (t) { sheet_(t, TABS[t]); });
  buildDashboard_();
  Logger.log("StudentUp CRM v2 ready ✅  Deploy as Web app and set SHEET_WEBAPP_URL in .env");
}

// ─────────────────────────────────────────────────────────── sheet helpers
function sheet_(name, cols) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(name);
  if (!sh) {
    sh = ss.insertSheet(name);
    sh.appendRow(cols);
    sh.setFrozenRows(1);
    sh.getRange(1, 1, 1, cols.length).setFontWeight("bold").setBackground("#1a73e8").setFontColor("#ffffff");
  }
  return sh;
}

/** header map {name: 1-based col}; appends any missing expected columns at the end (never shifts existing). */
function headers_(sh, cols) {
  var lastCol = Math.max(sh.getLastColumn(), 1);
  var hdr = sh.getRange(1, 1, 1, lastCol).getValues()[0].map(String);
  var missing = cols.filter(function (c) { return hdr.indexOf(c) < 0; });
  if (missing.length) {
    sh.getRange(1, hdr.length + 1, 1, missing.length).setValues([missing])
      .setFontWeight("bold").setBackground("#1a73e8").setFontColor("#ffffff");
    hdr = hdr.concat(missing);
  }
  var map = {};
  hdr.forEach(function (h, i) { if (h) map[h] = i + 1; });
  return { map: map, width: hdr.length, hdr: hdr };
}

function cell_(c, v, ts) {
  if (c === "updated_at" || c === "ts") return ts || new Date();
  if (v === undefined || v === null) return "";
  if (c === "mobile" || c === "tg_id" || c === "phone") return v === "" ? "" : "'" + v;   // keep as text
  if (Array.isArray(v)) return v.join(",");
  return v;
}

/** upsert rows by key column; one read of the key column, batched writes. */
function upsert_(tab, rows, ts) {
  if (!rows.length) return 0;
  var cols = TABS[tab], key = KEYS[tab];
  var sh = sheet_(tab, cols);
  var H = headers_(sh, cols);
  var last = sh.getLastRow();
  var keyCol = H.map[key];
  var index = {};
  if (last > 1) {
    sh.getRange(2, keyCol, last - 1, 1).getValues().forEach(function (r, i) {
      var k = String(r[0]).replace(/^'/, ""); if (k) index[k] = i + 2;
    });
  }
  var appendBuf = [];
  rows.forEach(function (row) {
    var line = new Array(H.width).fill("");
    Object.keys(H.map).forEach(function (c) { line[H.map[c] - 1] = cell_(c, row[c], ts); });
    var k = String(row[key] === undefined ? "" : row[key]);
    if (index[k]) sh.getRange(index[k], 1, 1, H.width).setValues([line]);
    else { appendBuf.push(line); index[k] = last + appendBuf.length; }
  });
  if (appendBuf.length) sh.getRange(last + 1, 1, appendBuf.length, H.width).setValues(appendBuf);
  return rows.length;
}

function append_(tab, rows, ts, medals) {
  if (!rows.length) return 0;
  var cols = TABS[tab];
  var sh = sheet_(tab, cols);
  var H = headers_(sh, cols);
  var data = rows.map(function (r) {
    var line = new Array(H.width).fill("");
    Object.keys(H.map).forEach(function (c) { line[H.map[c] - 1] = cell_(c, r[c], ts); });
    return line;
  });
  var start = sh.getLastRow() + 1;
  sh.getRange(start, 1, data.length, H.width).setValues(data);
  if (medals && H.map.rank) {
    var rc = H.map.rank - 1;
    data.forEach(function (r, i) {
      var col = r[rc] === 1 ? "#fff3b0" : r[rc] === 2 ? "#e8eaed" : r[rc] === 3 ? "#f6d1b1" : null;
      if (col) sh.getRange(start + i, 1, 1, H.width).setBackground(col);
    });
  }
  // keep the big append-only tabs bounded (oldest rows trimmed beyond 20k)
  var extra = sh.getLastRow() - 20001;
  if (extra > 0) sh.deleteRows(2, extra);
  return rows.length;
}

function daily_(row) {
  var sh = sheet_("daily", TABS.daily);
  var H = headers_(sh, TABS.daily);
  var last = sh.getLastRow();
  var line = new Array(H.width).fill("");
  Object.keys(H.map).forEach(function (c) { line[H.map[c] - 1] = cell_(c, row[c]); });
  // one row per date: overwrite today's row if it exists
  if (last > 1) {
    var dates = sh.getRange(2, H.map.date, last - 1, 1).getValues().map(function (r) { return String(r[0]); });
    var i = dates.indexOf(String(row.date));
    if (i >= 0) { sh.getRange(i + 2, 1, 1, H.width).setValues([line]); return 1; }
  }
  sh.getRange(last + 1, 1, 1, H.width).setValues([line]);
  return 1;
}

function log_(action, n, ok, err) {
  try {
    var sh = sheet_("log", TABS.log);
    sh.appendRow([new Date(), action || "", n, ok, err]);
    var extra = sh.getLastRow() - 501;
    if (extra > 0) sh.deleteRows(2, extra);
  } catch (e) { /* never break the request because of logging */ }
}

// ─────────────────────────────────────────────────────────── dashboard (formulas find columns by NAME)
function col_(tab, name) {   // A1 column letter for a header name, via MATCH at runtime → robust to reordering
  return "INDEX(" + tab + "!A:ZZ,0,MATCH(\"" + name + "\"," + tab + "!1:1,0))";
}
function buildDashboard_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var d = ss.getSheetByName("📊 Dashboard") || ss.insertSheet("📊 Dashboard", 0);
  d.clear();
  var M = function (n) { return col_("members", n); };
  var today = "TEXT(TODAY(),\"yyyy-mm-dd\")";
  var rows = [
    ["StudentUp CRM — Live Dashboard", "", "", ""],
    ["Total registered", "=COUNTA(" + M("tg_id") + ")-1", "With mobile", "=COUNTIF(" + M("mobile") + ",\"<>\")-1"],
    ["Telangana", "=COUNTIF(" + M("state") + ",\"Telangana\")", "Andhra Pradesh", "=COUNTIF(" + M("state") + ",\"Andhra Pradesh\")"],
    ["Active today", "=COUNTIF(" + M("last_active") + "," + today + ")", "New today", "=COUNTIF(" + M("registered_at") + "," + today + "&\"*\")"],
    ["Avg accuracy %", "=IFERROR(ROUND(AVERAGEIF(" + M("total") + ",\">0\"," + M("accuracy") + "),1),0)", "Rounds logged", "=IFERROR(COUNTUNIQUE(rounds!B2:B),0)"],
    ["Campus students", "=COUNTIF(" + M("college") + ",\"<>\")-1", "Colleges", "=IFERROR(COUNTA(colleges!A2:A),0)"],
    ["Verified channel joins", "=COUNTIF(" + M("verified_channels") + ",\">0\")", "Blocked bot", "=COUNTIF(" + M("dm_blocked") + ",TRUE)"],
    ["", "", "", ""],
    ["Top districts", "Members", "Exam targets", "Members"],
    ["=IFERROR(QUERY({" + M("district") + "},\"select Col1, count(Col1) where Col1<>'' and Col1<>'district' group by Col1 order by count(Col1) desc limit 15 label count(Col1) ''\",0),\"—\")", "",
     "=IFERROR(QUERY({" + M("exam") + "},\"select Col1, count(Col1) where Col1<>'' and Col1<>'exam' group by Col1 order by count(Col1) desc limit 15 label count(Col1) ''\",0),\"—\")", ""]
  ];
  d.getRange(1, 1, rows.length, 4).setValues(rows);
  d.getRange("A1").setFontSize(16).setFontWeight("bold");
  d.getRange("A2:A7").setFontWeight("bold"); d.getRange("C2:C7").setFontWeight("bold");
  d.getRange("A9:D9").setFontWeight("bold").setBackground("#1a73e8").setFontColor("#ffffff");
  d.getRange("F9:J9").setValues([["Top 10 players", "District", "Points", "Accuracy %", "Streak"]])
    .setFontWeight("bold").setBackground("#1a73e8").setFontColor("#ffffff");
  d.getRange("F10").setFormula("=IFERROR(QUERY({" + M("name") + "," + M("district") + "," + M("points") + "," + M("accuracy") + "," + M("streak") + "},\"select Col1,Col2,Col3,Col4,Col5 where Col1<>'' and Col1<>'name' order by Col3 desc limit 10 label Col1 '',Col2 '',Col3 '',Col4 '',Col5 ''\",0),\"—\")");
  d.getRange("L9:N9").setValues([["Colleges", "Students", "Avg last %"]]).setFontWeight("bold").setBackground("#1a73e8").setFontColor("#ffffff");
  d.getRange("L10").setFormula("=IFERROR(QUERY(colleges!A2:F,\"select A, C, F where A<>'' order by C desc limit 15 label A '', C '', F ''\",0),\"—\")");
  d.getRange("F22:J22").setValues([["Latest round winners", "Channel", "Rank", "District", "Score"]])
    .setFontWeight("bold").setBackground("#34a853").setFontColor("#ffffff");
  d.getRange("F23").setFormula("=IFERROR(QUERY(rounds!A2:J,\"select F, C, D, G, H where D<=3 order by A desc limit 15 label F '', C '', D '', G '', H ''\",0),\"—\")");
  d.getRange("L22:N22").setValues([["Growth (last 14 days)", "Members", "Active"]]).setFontWeight("bold").setBackground("#34a853").setFontColor("#ffffff");
  d.getRange("L23").setFormula("=IFERROR(QUERY(daily!A2:D,\"select A, B, D order by A desc limit 14 label A '', B '', D ''\",0),\"—\")");
  d.setColumnWidths(1, 14, 150);
  d.setFrozenRows(1);
}

// ─────────────────────────────────────────────────────────── util
function json_(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}
