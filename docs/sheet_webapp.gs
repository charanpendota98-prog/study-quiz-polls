/**
 * ╔══════════════════════════════════════════════════════════════════╗
 * ║  StudentUp CRM — Google Sheet receiver (Apps Script Web App)      ║
 * ║  Paste this WHOLE file. Change only SECRET.                        ║
 * ╚══════════════════════════════════════════════════════════════════╝
 *
 * SETUP (one time):
 *  1. Sheet → Extensions → Apps Script → delete sample code → paste this file → Save (💾)
 *  2. Change SECRET below to any long random text (keep it private).
 *  3. Deploy → New deployment → ⚙ type "Web app"
 *        Description: StudentUp CRM
 *        Execute as : Me
 *        Who has access: Anyone
 *     → Deploy → Authorize (choose your Google account → Advanced → Go to … → Allow)
 *  4. Copy the "Web app URL" (ends with /exec) → bot .env:
 *        SHEET_WEBAPP_URL=<that url>
 *        SHEET_SECRET=<same SECRET as below>
 *  5. Run once from the editor: select "setupSheet" → ▶ Run  (creates tabs + dashboard)
 *     Permission popup: Review permissions → your account → Advanced → Go to … → Allow
 *  6. In Telegram bot: /syncsheet
 *
 *  ⚠ After ANY later code edit: Deploy → Manage deployments → ✏ → Version: New → Deploy
 *    (otherwise the old code keeps running).
 *
 * TABS (auto-created):
 *  📊 Dashboard  — live totals, state/district/exam split, top 10, today's activity
 *  members       — one row per Telegram user (upsert by tg_id)
 *  rounds        — every round's Top-10 (round_id, channel, rank, name, district, score)
 *  daily         — one snapshot row per day (members, active, new) for growth charts
 *  log           — last 500 incoming requests (debugging)
 */

var SECRET = "CHANGE-ME-long-random-string";

var MEMBER_COLS = ["tg_id", "name", "username", "mobile", "state", "district", "exam", "lang",
  "registered_at", "source", "points", "correct", "total", "accuracy", "streak", "best_streak",
  "level", "last_active", "follow", "updated_at"];
var ROUND_COLS = ["ts", "round_id", "channel", "rank", "tg_id", "name", "district", "correct", "total", "points"];
var DAILY_COLS = ["date", "members", "with_mobile", "active_today", "new_today", "ts_members", "ap_members"];
var LOG_COLS = ["ts", "action", "rows", "ok", "error"];

// ─────────────────────────────────────────────────────────── HTTP entry points
function doPost(e) {
  var out = { ok: false }, body = {}, n = 0;
  try {
    body = JSON.parse((e && e.postData && e.postData.contents) || "{}");
    if (body.secret !== SECRET) { out.error = "bad secret"; log_(body.action, 0, false, out.error); return json_(out); }
    var lock = LockService.getScriptLock(); lock.waitLock(25000);
    try {
      switch (body.action) {
        case "upsert": n = upsert_([body.row], body.ts); break;
        case "bulk":   n = upsert_(body.rows || [], body.ts); break;
        case "round":  n = appendRounds_(body.rows || [], body.ts); break;
        case "ping":   n = 0; break;
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
  return json_({ ok: true, service: "studentup-crm", members: sh ? Math.max(sh.getLastRow() - 1, 0) : 0 });
}

// ─────────────────────────────────────────────────────────── one-time setup
function setupSheet() {
  sheet_("members", MEMBER_COLS);
  sheet_("rounds", ROUND_COLS);
  sheet_("daily", DAILY_COLS);
  sheet_("log", LOG_COLS);
  buildDashboard_();
  Logger.log("StudentUp CRM ready ✅  Now deploy as Web app and set SHEET_WEBAPP_URL in .env");
}

// OPTIONAL (later): nightly growth snapshot — add via ⏰ Triggers menu:
//   function: dailySnapshot · event: Time-driven · Day timer · 11pm–midnight.
// (Kept out of setupSheet so first-run needs only the Sheets permission.)

// ─────────────────────────────────────────────────────────── writers
function sheet_(name, cols) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(name);
  if (!sh) {
    sh = ss.insertSheet(name);
    sh.appendRow(cols);
    sh.setFrozenRows(1);
    sh.getRange(1, 1, 1, cols.length).setFontWeight("bold").setBackground("#1a73e8").setFontColor("#ffffff");
    sh.autoResizeColumns(1, cols.length);
  }
  return sh;
}

function upsert_(rows, ts) {
  if (!rows.length) return 0;
  var sh = sheet_("members", MEMBER_COLS);
  var last = sh.getLastRow();
  var ids = last > 1 ? sh.getRange(2, 1, last - 1, 1).getValues().map(function (r) { return String(r[0]); }) : [];
  var appendBuf = [];
  rows.forEach(function (row) {
    var vals = MEMBER_COLS.map(function (c) {
      if (c === "updated_at") return ts;
      if (c === "mobile" || c === "tg_id") return row[c] === undefined || row[c] === "" ? "" : "'" + row[c]; // keep as text (no 9.8E+09)
      return row[c] === undefined ? "" : row[c];
    });
    var idx = ids.indexOf(String(row.tg_id));
    if (idx >= 0) sh.getRange(idx + 2, 1, 1, MEMBER_COLS.length).setValues([vals]);
    else { appendBuf.push(vals); ids.push(String(row.tg_id)); }
  });
  if (appendBuf.length) sh.getRange(sh.getLastRow() + 1, 1, appendBuf.length, MEMBER_COLS.length).setValues(appendBuf);
  return rows.length;
}

function appendRounds_(rows, ts) {
  if (!rows.length) return 0;
  var sh = sheet_("rounds", ROUND_COLS);
  var data = rows.map(function (r) {
    return ROUND_COLS.map(function (c) { return c === "ts" ? ts : (c === "tg_id" ? "'" + (r[c] || "") : (r[c] === undefined ? "" : r[c])); });
  });
  sh.getRange(sh.getLastRow() + 1, 1, data.length, ROUND_COLS.length).setValues(data);
  // medal colours for rank 1-3
  data.forEach(function (r, i) {
    var col = r[3] === 1 ? "#fff3b0" : r[3] === 2 ? "#e8eaed" : r[3] === 3 ? "#f6d1b1" : null;
    if (col) sh.getRange(sh.getLastRow() - data.length + 1 + i, 1, 1, ROUND_COLS.length).setBackground(col);
  });
  return rows.length;
}

function log_(action, n, ok, err) {
  try {
    var sh = sheet_("log", LOG_COLS);
    sh.appendRow([new Date(), action || "", n, ok, err]);
    var extra = sh.getLastRow() - 501;
    if (extra > 0) sh.deleteRows(2, extra);
  } catch (e) { /* never break the request because of logging */ }
}

// ─────────────────────────────────────────────────────────── daily snapshot
function dailySnapshot() {
  var sh = sheet_("daily", DAILY_COLS);
  var m = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("members");
  if (!m || m.getLastRow() < 2) return;
  var vals = m.getRange(2, 1, m.getLastRow() - 1, MEMBER_COLS.length).getValues();
  var today = Utilities.formatDate(new Date(), "Asia/Kolkata", "yyyy-MM-dd");
  var c = { members: vals.length, mobile: 0, active: 0, newm: 0, ts: 0, ap: 0 };
  vals.forEach(function (r) {
    if (r[3]) c.mobile++;
    if (String(r[17]) === today) c.active++;
    if (String(r[8]).slice(0, 10) === today) c.newm++;
    if (r[4] === "Telangana") c.ts++;
    if (r[4] === "Andhra Pradesh") c.ap++;
  });
  sh.appendRow([today, c.members, c.mobile, c.active, c.newm, c.ts, c.ap]);
}

// ─────────────────────────────────────────────────────────── dashboard
function buildDashboard_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var d = ss.getSheetByName("📊 Dashboard") || ss.insertSheet("📊 Dashboard", 0);
  d.clear();
  var M = "members!";
  var rows = [
    ["StudentUp CRM — Live Dashboard", "", "", ""],
    ["Total registered", "=COUNTA(" + M + "A2:A)", "With mobile", "=COUNTIF(" + M + "D2:D,\"<>\")"],
    ["Telangana", "=COUNTIF(" + M + "E2:E,\"Telangana\")", "Andhra Pradesh", "=COUNTIF(" + M + "E2:E,\"Andhra Pradesh\")"],
    ["Active today", "=COUNTIF(" + M + "R2:R,TEXT(TODAY(),\"yyyy-mm-dd\"))", "New today", "=COUNTIF(" + M + "I2:I,TEXT(TODAY(),\"yyyy-mm-dd\")&\"*\")"],
    ["Avg accuracy %", "=IFERROR(ROUND(AVERAGEIF(" + M + "M2:M,\">0\"," + M + "N2:N),1),0)", "Rounds logged", "=IFERROR(COUNTUNIQUE(rounds!B2:B),0)"],
    ["", "", "", ""],
    ["Top districts", "Members", "Exam targets", "Members"],
    ["=IFERROR(QUERY(" + M + "F2:F,\"select F, count(F) where F<>'' group by F order by count(F) desc limit 15 label count(F) ''\",0),\"—\")", "",
     "=IFERROR(QUERY(" + M + "G2:G,\"select G, count(G) where G<>'' group by G order by count(G) desc limit 15 label count(G) ''\",0),\"—\")", ""]
  ];
  d.getRange(1, 1, rows.length, 4).setValues(rows);
  d.getRange("A1").setFontSize(16).setFontWeight("bold");
  d.getRange("A2:A5").setFontWeight("bold"); d.getRange("C2:C5").setFontWeight("bold");
  d.getRange("A7:D7").setFontWeight("bold").setBackground("#1a73e8").setFontColor("#ffffff");
  d.getRange("F7:J7").setValues([["Top 10 players", "District", "Points", "Accuracy %", "Streak"]])
    .setFontWeight("bold").setBackground("#1a73e8").setFontColor("#ffffff");
  d.getRange("F8").setFormula("=IFERROR(QUERY(" + M + "B2:R,\"select B, F, K, N, O where B<>'' order by K desc limit 10 label B '', F '', K '', N '', O ''\",0),\"—\")");
  d.getRange("F19:J19").setValues([["Latest round winners", "Channel", "Rank", "District", "Score"]])
    .setFontWeight("bold").setBackground("#34a853").setFontColor("#ffffff");
  d.getRange("F20").setFormula("=IFERROR(QUERY(rounds!A2:J,\"select F, C, D, G, H where D<=3 order by A desc limit 15 label F '', C '', D '', G '', H ''\",0),\"—\")");
  d.setColumnWidths(1, 10, 150);
  d.setFrozenRows(1);
}

// ─────────────────────────────────────────────────────────── util
function json_(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}
