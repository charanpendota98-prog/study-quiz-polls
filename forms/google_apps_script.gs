/**
 * STUDENTUP — Google Form → Telegram auto-notification (and optional auto-register)
 *
 * SETUP (one time, ~5 minutes):
 *  1. Open your Google Form responses SHEET (Responses sheet).
 *  2. Menu: Extensions → Apps Script.
 *  3. Paste this whole file, fill in BOT_TOKEN and ADMIN_CHAT_ID below.
 *  4. Save. Triggers (clock icon on left) → Add Trigger:
 *       Function: onFormSubmit
 *       Event source: From spreadsheet
 *       Event type:  On form submit
 *  5. Authorize when prompted. Done — every new registration pings Telegram.
 *
 * ADMIN_CHAT_ID = your numeric Telegram id (message @userinfobot to get it),
 *                 OR a group/channel id like -1001234567890.
 */

var BOT_TOKEN    = "PUT_YOUR_BOTFATHER_TOKEN_HERE";
var ADMIN_CHAT_ID = "PUT_YOUR_TELEGRAM_ID_HERE";   // e.g. 123456789
var BOT_USERNAME  = "DailyQuizPosterbot";          // shown in the CTA

function onFormSubmit(e) {
  try {
    var items = e.namedValues || {};
    function pick(keys) {
      for (var i = 0; i < keys.length; i++) {
        for (var k in items) {
          if (k.toLowerCase().indexOf(keys[i]) !== -1) {
            return (items[k] || []).join(", ");
          }
        }
      }
      return "";
    }

    var name    = pick(["name", "పేరు"]);
    var phone   = pick(["mobile", "phone", "whatsapp", "మొబైల్"]);
    var tg      = pick(["telegram", "టెలిగ్రామ్"]);
    var state   = pick(["state", "రాష్ట్రం"]);
    var district= pick(["district", "జిల్లా"]);
    var exam    = pick(["exam target", "లక్ష్యం", "target"]);
    var lang    = pick(["language", "మాధ్యమం", "medium"]);
    var stage   = pick(["stage", "preparation"]);

    var msg =
      "🆕 *New StudentUp registration!*\n" +
      "👤 " + name + "\n" +
      "🎯 " + exam + "  |  Stage: " + stage + "\n" +
      "📍 " + district + ", " + state + "  |  🗣 " + lang + "\n" +
      "📱 " + phone + "\n" +
      "✈️ Telegram: " + (tg || "(not given)") + "\n" +
      "\nTotal responses now: " + (e.range ? e.range.getRow() - 1 : "?");

    sendTelegram(msg);

    // Optional: auto-open the bot /start for users who gave a username is not
    // possible server-side, but we log the Telegram handle for points linking.
    Logger.log("Registered: " + name + " / " + tg);
  } catch (err) {
    Logger.log("onFormSubmit error: " + err);
  }
}

function sendTelegram(text) {
  var url = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage";
  var payload = {
    chat_id: ADMIN_CHAT_ID,
    text: text,
    parse_mode: "Markdown",
    disable_web_page_preview: true
  };
  var options = {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify(payload)
  };
  UrlFetchApp.fetch(url, options);
}

/**
 * Optional helper — test notification (run this manually once to verify).
 */
function testNotification() {
  sendTelegram("✅ StudentUp Form ↔ Telegram link is working!");
}
