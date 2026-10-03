# 🚀 StudentUp — FINAL DEPLOY GUIDE v4 (Dashboard + WhatsApp Bridge)

> Server: **80.225.205.135** · User: `ubuntu` · Key: `C:\Users\Charan\Downloads\ssh-key-2026-08-23.key`
> Zip: **`studentup_deploy_v4.zip`** (Arena workspace → Downloads folder నుంచి తీసుకోండి)
>
> కొత్త stack లో **2 services** నడుస్తాయి:
> 1. 📊 **Dashboard** — port **5000** (polls, auto-pilot, analytics, security అన్నీ ఇక్కడే)
> 2. 💚 **WhatsApp Bridge** — port **3900** (real Baileys engine, QR login)

---

## Step 1 — Zip ని server కి పంపండి (PowerShell లో, SSH కాదు)

```powershell
scp -i C:\Users\Charan\Downloads\ssh-key-2026-08-23.key C:\Users\Charan\Downloads\studentup_deploy_v4.zip ubuntu@80.225.205.135:~/
```

## Step 2 — Server లోకి SSH అవ్వండి

```powershell
ssh -i C:\Users\Charan\Downloads\ssh-key-2026-08-23.key ubuntu@80.225.205.135
```

## Step 3 — Server లో ఈ block మొత్తం ఒకేసారి paste చేయండి

```bash
# ---- STUDENTUP v4 ONE-PASTE INSTALL ----
cd ~
# పాత env/.env (BOT_TOKEN తో) భద్రంగా పక్కన పెట్టడం
[ -f ~/studentup/env/.env ] && cp ~/studentup/env/.env ~/env_backup_dotenv
# పాత data (groups, schedules, members) భద్రం
[ -d ~/studentup/data ] && cp -r ~/studentup/data ~/data_backup_old

rm -rf studentup && mkdir studentup
unzip -o ~/studentup_deploy_v4.zip -d studentup
cd studentup

# env + data restore
[ -f ~/env_backup_dotenv ] && mkdir -p env && cp ~/env_backup_dotenv env/.env
[ -d ~/data_backup_old ] && cp -rn ~/data_backup_old/* data/ 2>/dev/null || true

# Node 18+ & bridge deps
node -v || { curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt-get install -y nodejs; }
cd gateway && npm install --no-audit --no-fund && cd ..

# పాత services ఆపడం (ఏవి ఉన్నా సరే)
sudo systemctl stop studentup studentup-bot studentup-webhook studentup-dashboard studentup-bridge 2>/dev/null || true
sudo systemctl disable studentup studentup-bot studentup-webhook 2>/dev/null || true

# కొత్త 2 services install
sudo cp deploy/studentup-dashboard.service deploy/studentup-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now studentup-dashboard studentup-bridge

# Firewall లో dashboard port open (Oracle అయితే cloud console లో కూడా 5000 open చేయాలి)
sudo iptables -I INPUT -p tcp --dport 5000 -j ACCEPT 2>/dev/null || true

sleep 3
systemctl status studentup-dashboard --no-pager | head -5
systemctl status studentup-bridge --no-pager | head -5
echo "✅ DONE! Dashboard: http://80.225.205.135:5000"
# ---- END ----
```

## Step 4 — First-time setup (browser లో)

1. **http://80.225.205.135:5000** open చేయండి → password login (default `studentup123` — వెంటనే 🔑 button తో మార్చండి!)
2. **BOT_TOKEN లేకపోతే**: server లో `nano ~/studentup/env/.env` → `BOT_TOKEN=123456:ABC...` పెట్టి → `sudo systemctl restart studentup-dashboard` → Telegram **LIVE** ✅
3. **WhatsApp link**: Dashboard → WhatsApp tab → **Scan QR Login** → phone తో scan → bridge CONNECTED ✅
4. **🛡️ IP Lock** (optional but best): header → IP Lock → Add My Current IP → Save & Turn ON
5. **🤖 Auto-Pilot ON**: Channels tab → targets select → 🚀 1-Click Daily Plan — అంతే, రోజూ ఆటోమేటిక్!

---

## రోజువారీ Commands (అవసరమైతే)

```bash
# Status చూడటం
sudo systemctl status studentup-dashboard studentup-bridge --no-pager

# Logs లైవ్ గా
journalctl -u studentup-dashboard -f
journalctl -u studentup-bridge -f

# Restart
sudo systemctl restart studentup-dashboard studentup-bridge
```

## Update వచ్చినప్పుడు (కొత్త zip తో)

Step 1 → Step 3 మళ్ళీ run చేయండి — అంతే. env/.env + data ఆటోమేటిక్ గా carry అవుతాయి.

## VPS లేని వాళ్ళకి / Testing కి (ఏ Linux/Mac అయినా)

```bash
cd studentup && bash start_all.sh    # రెండు services ఒకే command, crash అయితే auto-restart
```

## 🚨 Troubleshooting

| సమస్య | పరిష్కారం |
|---|---|
| Dashboard open అవ్వట్లేదు | Oracle/AWS console → Security List లో TCP 5000 ingress add చేయండి |
| IP Lock వల్ల lockout | `env/.env` లో `DISABLE_IP_LOCK=1` → restart → lock OFF చేసి → line తీసేయండి |
| Telegram DRY-RUN అనే వస్తోంది | `env/.env` లో BOT_TOKEN సరిగ్గా ఉందా చూడండి → restart |
| WhatsApp disconnect అయింది | Dashboard → WhatsApp tab → మళ్ళీ QR scan |
| Password మర్చిపోయారు | server లో `rm ~/studentup/data/dashboard_auth.json` → restart → default `studentup123` |
