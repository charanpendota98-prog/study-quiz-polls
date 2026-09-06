/**
 * ============================================================================
 * STUDENTUP — ONE-CLICK GOOGLE FORM BUILDER
 * ============================================================================
 * This script BUILDS THE ENTIRE registration form automatically — all 33
 * Telangana + 26 Andhra Pradesh districts, every question, validation and the
 * confirmation message. You do NOT add questions by hand.
 *
 * HOW TO RUN (one time, ~3 minutes):
 *  1. Open https://script.google.com  →  New project.
 *  2. Delete any sample code, paste THIS whole file.
 *  3. (Optional) edit BOT_USERNAME below.
 *  4. Click  ▶ Run  → choose function  buildStudentUpForm  →  Authorize
 *     (Google says "unverified" → Advanced → Go to project → Allow).
 *  5. Check the Execution log — it prints the LIVE FORM URL and EDIT URL.
 *     Open the form URL, click SEND, share it everywhere. Done!
 *
 * After this, also paste google_apps_script.gs into the SAME project and add
 * the "on form submit" trigger so each signup pings your Telegram.
 * ============================================================================
 */

var BOT_USERNAME = "DailyQuizPosterbot";   // your quiz bot (shown in the thank-you page)

// ---- Telangana — 33 districts (official) -----------------------------------
var TS_DISTRICTS = [
  "TS · Adilabad", "TS · Bhadradri Kothagudem", "TS · Hyderabad", "TS · Jagtial",
  "TS · Jangaon", "TS · Jayashankar Bhupalpally", "TS · Jogulamba Gadwal",
  "TS · Kamareddy", "TS · Karimnagar", "TS · Khammam", "TS · Komaram Bheem Asifabad",
  "TS · Mahabubabad", "TS · Mahbubnagar", "TS · Mancherial", "TS · Medak", "TS · Medchal–Malkajgiri",
  "TS · Mulugu", "TS · Nagarkurnool", "TS · Nalgonda", "TS · Narayanpet",
  "TS · Nirmal", "TS · Nizamabad", "TS · Peddapalli", "TS · Rajanna Sircilla",
  "TS · Ranga Reddy", "TS · Sangareddy", "TS · Siddipet", "TS · Suryapet",
  "TS · Vikarabad", "TS · Wanaparthy", "TS · Warangal", "TS · Hanamkonda",
  "TS · Yadadri Bhuvanagiri", "TS · Other / not listed"
];

// ---- Andhra Pradesh — 26 districts (official, 2022 reorganisation) ----------
var AP_DISTRICTS = [
  "AP · Alluri Sitharama Raju", "AP · Anakapalli", "AP · Anantapur",
  "AP · Annamayya", "AP · Bapatla", "AP · Chittoor",
  "AP · Dr. B.R. Ambedkar Konaseema", "AP · East Godavari", "AP · Eluru",
  "AP · Guntur", "AP · Kakinada", "AP · Krishna", "AP · Kurnool",
  "AP · Nandyal", "AP · Nellore (Sri Potti Sriramulu)", "AP · NTR",
  "AP · Palnadu", "AP · Parvathipuram Manyam", "AP · Prakasam",
  "AP · Sri Sathya Sai", "AP · Srikakulam", "AP · Tirupati",
  "AP · Visakhapatnam", "AP · Vizianagaram", "AP · West Godavari",
  "AP · YSR Kadapa", "AP · Other / not listed"
];

var ALL_DISTRICTS = TS_DISTRICTS.concat(AP_DISTRICTS);

var EXAM_TARGETS = [
  "TSPSC (Group II/III/IV)",
  "APPSC (Group II/III/IV)",
  "Banking — IBPS / SBI / RRB Clerk-PO",
  "Railway — RRB NTPC / Group D / ALP",
  "Police — Constable / SI (TS & AP)",
  "Defence — NDA / CDS / Agniveer",
  "SSC / UPSC",
  "Current Affairs & GK (all exams)",
  "Other / not sure yet"
];

var EDUCATION = [
  "10th / Intermediate",
  "Diploma / ITI",
  "Degree (BA / BSc / BCom / BBA)",
  "B.Tech / B.E. / Engineering",
  "Post-Graduate (MA / MSc / MCom / MBA)",
  "Working professional",
  "Other"
];

var TARGET_YEAR = ["2026 (exam soon)", "2027", "2028", "Just exploring / building habit"];
var MEDIUM = ["English", "Telugu", "Both (English + Telugu)"];
var STUDY_MODE = ["Self study", "Coaching institute", "College + self study", "Online courses only"];
var HOURS = ["Less than 2 hours", "2–4 hours", "4–6 hours", "6+ hours"];
var UPDATES = ["Yes — WhatsApp", "Yes — Telegram", "Yes — both", "No updates"];
var SOURCE = ["Friend / senior", "YouTube", "Instagram", "WhatsApp group",
              "Telegram search", "Facebook", "Other"];


function buildStudentUpForm() {
  var form = FormApp.create("StudentUp — FREE Daily Quiz Registration (TS & AP)")
    .setDescription(
      "Join thousands of Telangana & Andhra Pradesh aspirants practising FREE " +
      "daily bilingual (English + Telugu) quiz polls for TSPSC, APPSC, Banking, " +
      "Railway, Police, Defence & Current Affairs.\n\n" +
      "⤷ TSPSC, APPSC, బ్యాంక్, రైల్వే, పోలీస్, డిఫెన్స్ అభ్యర్థుల కోసం ప్రతిరోజూ " +
      "ఉచిత బైలింగ్వల్ క్విజ్. రిజిస్టర్ చేసుకోండి — మీకు తగ్గ ప్రశ్నలు, ఉద్యోగ " +
      "అప్‌డేట్స్, వీక్లీ లీడర్‌బోర్డ్, పాయింట్లు & ర్యాంకులు!\n\n" +
      "Takes under 60 seconds. ⏱")
    .setCollectEmail(true)
    .setAcceptingResponses(true);

  form.setConfirmationMessage(
    "🎉 Welcome to StudentUp, future officer!\n\n" +
    "👉 NOW open Telegram, search @" + BOT_USERNAME + " and press START.\n" +
    "   Send /register then /quiz to earn points, levels & your rank 🏆\n\n" +
    "⤷ టెలిగ్రామ్‌లో @" + BOT_USERNAME + " ఓపెన్ చేసి /register, తర్వాత /quiz ఆడండి!");

  function header(title) {
    return form.addSectionHeaderItem().setTitle(title);
  }

  // ---- 1) Basic details ----------------------------------------------------
  header("👤 1. Your details / మీ వివరాలు");

  form.addTextItem()
    .setTitle("Full name / పూర్తి పేరు")
    .setRequired(true);

  var phone = form.addTextItem()
    .setTitle("WhatsApp / Mobile number / మొబైల్ నంబర్")
    .setHelpText("10-digit Indian mobile number (e.g. 9876543210)")
    .setRequired(true);
  phone.setValidation(FormApp.createTextValidation()
    .setHelpText("Please enter a valid 10-digit mobile number (e.g. 9876543210)")
    .requireTextMatchesPattern("^[6-9]\\d{9}$")
    .build());

  var tg = form.addTextItem()
    .setTitle("Telegram username or numeric ID / టెలిగ్రామ్")
    .setHelpText("e.g. @yourname  (open Telegram → Settings → Username). This links your quiz POINTS & rank.")
    .setRequired(true);
  tg.setValidation(FormApp.createTextValidation()
    .setHelpText("Enter your @username (e.g. @charan) or your numeric Telegram id")
    .requireTextMatchesPattern("^@?[A-Za-z0-9_]{4,32}$|^\\d{5,15}$")
    .build());

  // ---- 2) Location ---------------------------------------------------------
  header("📍 2. Where are you from? / మీరు ఎక్కడి నుండి?");

  form.addMultipleChoiceItem()
    .setTitle("State / రాష్ట్రం")
    .setChoiceValues(["Telangana", "Andhra Pradesh", "Other state"])
    .setRequired(true);

  form.addListItem()
    .setTitle("District / జిల్లా  (type to search)")
    .setHelpText("TS = Telangana, AP = Andhra Pradesh")
    .setChoiceValues(ALL_DISTRICTS)
    .setRequired(true);

  // ---- 3) Study / exam -----------------------------------------------------
  header("📚 3. Your preparation / మీ చదువు");

  form.addListItem()
    .setTitle("Which exam are you preparing for? / మీరు ఏ పరీక్షకు చదువుతున్నారు?")
    .setChoiceValues(EXAM_TARGETS)
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle("Your current education level / మీ చదువు")
    .setChoiceValues(EDUCATION)
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle("When is your target exam? / లక్ష్య పరీక్ష ఎప్పుడు?")
    .setChoiceValues(TARGET_YEAR)
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle("Medium of preparation / మాధ్యమం")
    .setChoiceValues(MEDIUM)
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle("How do you study? / ఎలా చదువుతున్నారు?")
    .setChoiceValues(STUDY_MODE)
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle("How many hours do you study daily? / రోజుకు ఎన్ని గంటలు?")
    .setChoiceValues(HOURS)
    .setRequired(false);

  // ---- 4) Updates & feedback ----------------------------------------------
  header("🔔 4. Updates & feedback");

  form.addMultipleChoiceItem()
    .setTitle("Add me to FREE daily quiz & job updates / ఉచిత అప్‌డేట్స్")
    .setChoiceValues(UPDATES)
    .setRequired(true);

  form.addListItem()
    .setTitle("How did you find StudentUp? / ఎలా తెలిసింది?")
    .setChoiceValues(SOURCE)
    .setRequired(false);

  form.addParagraphTextItem()
    .setTitle("Any suggestion, or what do you need most? / మీ సూచన?")
    .setHelpText("Optional — tell us what quizzes/material you want most.")
    .setRequired(false);

  // ---- result --------------------------------------------------------------
  Logger.log("============================================================");
  Logger.log("✅ STUDENTUP FORM CREATED!");
  Logger.log("LIVE FORM (share this): " + form.getPublishedUrl());
  Logger.log("EDIT URL (owner only)  : " + form.getEditUrl());
  Logger.log("Districts loaded: " + TS_DISTRICTS.length + " TS + " + AP_DISTRICTS.length + " AP");
  Logger.log("============================================================");
  Logger.log('NEXT: paste google_apps_script.gs into this project and add the');
  Logger.log('"On form submit" trigger so new signups ping your Telegram.');

  return form;
}
