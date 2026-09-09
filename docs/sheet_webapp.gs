/**
 * StudentUp CRM — Google Sheet receiver (Apps Script Web App).
 *
 * Setup:
 *  1. Create a Google Sheet (any name). Extensions → Apps Script → paste this file.
 *  2. Set SECRET below to a long random string. Put the SAME value in .env as SHEET_SECRET.
 *  3. Deploy → New deployment → Web app → Execute as: Me · Who has access: Anyone → Deploy.
 *  4. Copy the /exec URL into .env as SHEET_WEBAPP_URL.
 *
 * Tabs created automatically:
 *  - members : one row per Telegram user (upsert by tg_id) — name, mobile, district, exam, points…
 *  - rounds  : every round's Top-10 (round_id, channel, rank, name, district, score)
 */
var SECRET = "CHANGE-ME-long-random-string";
var MEMBER_COLS = ["tg_id","name","username","mobile","state","district","exam","lang",
  "registered_at","source","points","correct","total","accuracy","streak","best_streak",
  "level","last_active","follow","updated_at"];
var ROUND_COLS = ["ts","round_id","channel","rank","tg_id","name","district","correct","total","points"];

function doPost(e) {
  var out = { ok: false };
  try {
    var body = JSON.parse(e.postData.contents || "{}");
    if (body.secret !== SECRET) { out.error = "bad secret"; return json_(out); }
    var lock = LockService.getScriptLock(); lock.waitLock(20000);
    try {
      if (body.action === "upsert")      { upsert_([body.row], body.ts); }
      else if (body.action === "bulk")   { upsert_(body.rows || [], body.ts); }
      else if (body.action === "round")  { appendRounds_(body.rows || [], body.ts); }
      else { out.error = "unknown action"; return json_(out); }
    } finally { lock.releaseLock(); }
    out.ok = true;
  } catch (err) { out.error = String(err); }
  return json_(out);
}

function doGet() { return json_({ ok: true, service: "studentup-crm" }); }

function sheet_(name, cols) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(name);
  if (!sh) { sh = ss.insertSheet(name); sh.appendRow(cols); sh.setFrozenRows(1); }
  return sh;
}

function upsert_(rows, ts) {
  var sh = sheet_("members", MEMBER_COLS);
  var last = sh.getLastRow();
  var ids = last > 1 ? sh.getRange(2, 1, last - 1, 1).getValues().map(function (r) { return String(r[0]); }) : [];
  rows.forEach(function (row) {
    var vals = MEMBER_COLS.map(function (c) { return c === "updated_at" ? ts : (row[c] === undefined ? "" : row[c]); });
    var idx = ids.indexOf(String(row.tg_id));
    if (idx >= 0) { sh.getRange(idx + 2, 1, 1, MEMBER_COLS.length).setValues([vals]); }
    else { sh.appendRow(vals); ids.push(String(row.tg_id)); }
  });
}

function appendRounds_(rows, ts) {
  var sh = sheet_("rounds", ROUND_COLS);
  var data = rows.map(function (r) { return ROUND_COLS.map(function (c) { return c === "ts" ? ts : (r[c] === undefined ? "" : r[c]); }); });
  if (data.length) sh.getRange(sh.getLastRow() + 1, 1, data.length, ROUND_COLS.length).setValues(data);
}

function json_(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}
