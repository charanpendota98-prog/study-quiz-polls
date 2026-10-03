# 📱 StudentUp REAL WhatsApp Gateway Bridge (Baileys)

ఇది **నిజమైన WhatsApp Web session** — ఇక fake/simulation కాదు.
Dashboard లో 📷 Scan QR Login నొక్కినప్పుడు వచ్చే QR ఇప్పుడు **అసలు WhatsApp login QR**.
ఫోన్‌తో scan చేస్తే device నిజంగా link అవుతుంది, మీ groups నిజంగా sync అవుతాయి,
polls/messages నిజంగా groups కి వెళ్తాయి.

## 🚀 ఎలా స్టార్ట్ చేయాలి (How to run)

**Terminal 1 — WhatsApp bridge:**
```bash
cd gateway
npm install          # first time only
node wa_bridge.js    # runs on port 3900
```

**Terminal 2 — Dashboard:**
```bash
python3 scripts/dashboard_server.py   # runs on port 5000
```

తర్వాత browser లో dashboard open చేసి:
1. **📷 Scan QR Login** నొక్కండి → నిజమైన QR వస్తుంది (5–10 సెకన్లు పడుతుంది)
2. ఫోన్‌లో **WhatsApp → Linked Devices → Link a Device** → QR scan చేయండి
3. Scan అవ్వగానే dashboard **ఆటోమేటిక్‌గా** `● REAL WHATSAPP CONNECTED` చూపిస్తుంది
   (ఏ confirm button నొక్కాల్సిన అవసరం లేదు)
4. **🔄 Auto-Sync Joined Groups** → మీరు జాయిన్ అయిన అసలు groups అన్నీ లోడ్ అవుతాయి
5. ఇప్పుడు **🚀 Send Bulk Message** / **🎯 Send 5 Exam Polls** నిజంగా deliver అవుతాయి
   — exam polls **native tappable WhatsApp polls** గా వెళ్తాయి (ఓట్ల count కనిపిస్తుంది)

### 🔢 QR బదులు Pairing Code తో login
**🔢 Login with Code** నొక్కి మీ నంబర్ ఇవ్వండి (ఉదా: `+91 9876543210`).
ఫోన్‌లో: WhatsApp → Linked Devices → Link a Device → **Link with phone number instead**
→ వచ్చిన code టైప్ చేయండి.

## ⚠️ ముఖ్య గమనికలు (Important)

- **Internet open గా ఉండాలి**: bridge నడిచే machine నుంచి `web.whatsapp.com`
  కి కనెక్ట్ అవ్వగలగాలి. కొన్ని cloud sandboxes / college networks / corporate
  firewalls దీన్ని బ్లాక్ చేస్తాయి — అప్పుడు dashboard లో
  "Could not reach WhatsApp servers" అని స్పష్టంగా చూపిస్తుంది.
  మీ సొంత PC / VPS లో run చేయండి.
- Session `gateway/auth/` లో save అవుతుంది → మళ్లీ restart చేసినా **auto-reconnect**
  అవుతుంది, మళ్లీ QR scan అక్కర్లేదు. (ఈ folder ని ఎవరితోనూ share చేయవద్దు — ఇది మీ
  WhatsApp key! `.gitignore` లో already add చేశాం.)
- **🚪 Unlink Device** button తో session ని完全 remove చేయవచ్చు.
- Bridge connect అయి ఉంటేనే **full anti-ban delays** (40–60s jitter, 60–90s batch
  rest) apply అవుతాయి. Bridge లేకపోతే DRY-RUN mode (ఏదీ send అవ్వదు, honest గా
  "NOT SENT" అని log చూపిస్తుంది).
- WhatsApp unofficial automation వాడటం వల్ల number ban అయ్యే రిస్క్ ఎప్పుడూ ఉంటుంది.
  కొత్త/తక్కువ-విలువ నంబర్‌తో టెస్ట్ చేయండి, volumes నెమ్మదిగా పెంచండి.

## HTTP API (port 3900)

| Endpoint | Method | Purpose |
|---|---|---|
| `/status` | GET | session status, QR data-URL, pairing code |
| `/login/qr` | POST | start QR login |
| `/login/code` | POST `{phone}` | start pairing-code login |
| `/logout` | POST | unlink + wipe credentials |
| `/groups?fresh=1` | GET | real joined groups |
| `/send` | POST `{jid, text?, attachment?, poll?}` | send text / media URL / native poll |

Override port: `WA_BRIDGE_PORT=3901 node wa_bridge.js` and set
`WA_BRIDGE_URL=http://127.0.0.1:3901` before starting the dashboard.
