#!/usr/bin/env bash
# ============================================================================
# STUDENTUP — SYSTEM HEALTH & DEPLOY VERIFIER
# Runs a comprehensive audit of the live/deploy environment:
# 1. Systemd services status (studentup, studentup-bot, studentup-webhook)
# 2. Environment config (.env, SHEET_ID, BOT_TOKEN, ADMIN_ID)
# 3. Question bank stock (unused vs total per exam channel)
# 4. Google Sheet WebApp CRM connectivity & ping
# 5. Core test suite & pre-deploy validation gate
#
# Usage:
#   bash check.sh
# ============================================================================
set -u

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "================================================================"
echo "⚡ STUDENTUP DEPLOY & SYSTEM HEALTH CHECK"
echo "   Directory : $DIR"
echo "   Timestamp : $(date)"
echo "================================================================"

# ------------------------------------------------------------------
# [1] Systemd Services Check
# ------------------------------------------------------------------
echo ""
echo "[1] Systemd Services"
SERVICES=("studentup" "studentup-bot" "studentup-webhook")
if command -v systemctl >/dev/null 2>&1; then
  for svc in "${SERVICES[@]}"; do
    if systemctl is-active --quiet "$svc" 2>/dev/null; then
      echo "  ✅ $svc: ACTIVE (running)"
    else
      echo "  ⚠️ $svc: INACTIVE / NOT RUNNING"
    fi
  done
else
  echo "  ℹ️ systemctl not found in environment (skipped systemd check)"
fi

# ------------------------------------------------------------------
# [2] Environment & Secret Checks
# ------------------------------------------------------------------
echo ""
echo "[2] Environment Configuration"
ENV_FILE="env/.env"
if [ ! -f "$ENV_FILE" ]; then
  if [ -f "../env/.env" ]; then
    ENV_FILE="../env/.env"
  elif [ -f ".env" ]; then
    ENV_FILE=".env"
  fi
fi

if [ -f "$ENV_FILE" ]; then
  echo "  ✅ .env file found at $ENV_FILE"
  if grep -q "SHEET_ID=PASTE_HERE" "$ENV_FILE" 2>/dev/null; then
    echo "  ❌ SHEET_ID is still placeholder 'PASTE_HERE'!"
  elif grep -q "^SHEET_ID=" "$ENV_FILE" 2>/dev/null; then
    echo "  ✅ SHEET_ID configured"
  else
    echo "  ℹ️ SHEET_ID not set in $ENV_FILE (defaulting to config fallback)"
  fi

  if grep -q "^BOT_TOKEN=..*" "$ENV_FILE" 2>/dev/null; then
    echo "  ✅ BOT_TOKEN configured"
  else
    echo "  ⚠️ BOT_TOKEN not set or empty (dry-run mode)"
  fi
else
  echo "  ⚠️ $ENV_FILE not found (runs with default config & dry-run)"
fi

# ------------------------------------------------------------------
# [3] Python Check & Bank Stock
# ------------------------------------------------------------------
echo ""
echo "[3] Question Bank Stock & Assets"
python3 scripts/check.py

# ------------------------------------------------------------------
# [4] Google Sheet CRM Sync Ping
# ------------------------------------------------------------------
echo ""
echo "[4] Google Sheet CRM Connectivity"
python3 -c "
import sys
sys.path.insert(0, 'scripts')
from core import crm
if not crm.sheet_enabled():
    print('  ⚠️ Sheet WebApp not enabled (set SHEET_WEBAPP_URL in .env)')
else:
    res = crm.ping()
    if res.get('ok'):
        print('  ✅ Sheet WebApp reached successfully! Members recorded:', res.get('members', 0))
    else:
        print('  ❌ Sheet WebApp ping failed:', res.get('error', 'unknown error'))
"

# ------------------------------------------------------------------
# [5] Validation Gate
# ------------------------------------------------------------------
echo ""
echo "[5] Validation Gate & Integrity"
python3 scripts/finalize.py

echo ""
echo "================================================================"
echo "✅ HEALTH-CHECK COMPLETED"
echo "================================================================"
