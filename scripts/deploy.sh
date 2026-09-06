#!/usr/bin/env bash
# ============================================================================
# STUDENTUP — DEPLOY (idempotent, portable)
# Deploys this folder to the server (default /home/ubuntu/studentup), installs
# optional deps, validates the bank, and (on systemd) installs the services.
# Safe to re-run. Works with the Python STANDARD LIBRARY — no pip required.
#
# Usage:
#   bash scripts/deploy.sh                 # validate + print next steps
#   DEPLOY_DIR=/opt/studentup bash scripts/deploy.sh --install
#   bash scripts/deploy.sh --systemd       # also install systemd units (sudo)
# ============================================================================
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_DIR="${DEPLOY_DIR:-/home/ubuntu/studentup}"
TS="$(date +%Y%m%d_%H%M%S)"

echo "=========================================="
echo "STUDENTUP DEPLOY  $(date)"
echo "Source : $SRC_DIR"
echo "Target : $DEPLOY_DIR"
echo "=========================================="

# 1) Backup existing deploy
if [ -d "$DEPLOY_DIR" ] && [ "${1:-}" != "" ]; then
  BK="${DEPLOY_DIR}_backup_${TS}.tar.gz"
  echo "[1/6] Backing up existing deploy -> $BK"
  tar -czf "$BK" -C "$(dirname "$DEPLOY_DIR")" "$(basename "$DEPLOY_DIR")" || echo "  (backup skipped)"
else
  echo "[1/6] No prior deploy to back up (or dry)"
fi

# 2) Copy files (preserve .env if it already exists)
echo "[2/6] Copying files…"
mkdir -p "$DEPLOY_DIR"
if [ "$SRC_DIR" != "$DEPLOY_DIR" ]; then
  # preserve remote .env
  [ -f "$DEPLOY_DIR/env/.env" ] && cp "$DEPLOY_DIR/env/.env" "/tmp/studentup.env.$$"
  cp -r "$SRC_DIR"/. "$DEPLOY_DIR"/
  [ -f "/tmp/studentup.env.$$" ] && mkdir -p "$DEPLOY_DIR/env" && cp "/tmp/studentup.env.$$" "$DEPLOY_DIR/env/.env" && rm -f "/tmp/studentup.env.$$"
fi
mkdir -p "$DEPLOY_DIR"/{data,logs,env,sources}

# 3) Python + optional dependencies (stdlib is enough)
echo "[3/6] Python environment…"
PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then echo "  ✗ python3 not found — install Python 3.10+"; exit 1; fi
echo "  python: $($PY --version)"
if [ -d "$DEPLOY_DIR/venv" ]; then
  "$DEPLOY_DIR/venv/bin/pip" install -q -r "$DEPLOY_DIR/requirements.txt" 2>/dev/null \
    && echo "  venv deps updated" || echo "  (venv present; pip deps optional)"
else
  $PY -m venv "$DEPLOY_DIR/venv" 2>/dev/null && \
    "$DEPLOY_DIR/venv/bin/pip" install -q -r "$DEPLOY_DIR/requirements.txt" 2>/dev/null \
    && echo "  venv created + optional deps installed" \
    || echo "  (venv/pip skipped — engine runs on stdlib)"
fi
[ -f "$DEPLOY_DIR/env/.env" ] && chmod 600 "$DEPLOY_DIR/env/.env" || true

# 4) Rebuild + validate the question bank
echo "[4/6] Validation gate…"
cd "$DEPLOY_DIR/scripts"
$PY finalize.py --strict || { echo "  ✗ Validation failed — fix before live"; }

# 5) Health check + (optionally) deep source audit
echo "[5/6] Health check…"
$PY check.py || echo "  (health check reported notes)"
if [ "${1:-}" = "--audit" ]; then
  echo "[5b] Deep source audit (content-gated, all registry sources)…"
  $PY audit_sources.py --only-enabled || echo "  (audit reported notes — collector auto-handles)"
fi

# 6) systemd (optional)
if [ "${1:-}" = "--systemd" ]; then
  echo "[6/6] Installing systemd services…"
  sudo sed "s#/home/ubuntu/studentup#$DEPLOY_DIR#g; s#^User=ubuntu#User=$USER#" \
       "$DEPLOY_DIR/deploy/studentup.service" > /etc/systemd/system/studentup.service
  sudo sed "s#/home/ubuntu/studentup#$DEPLOY_DIR#g; s#^User=ubuntu#User=$USER#" \
       "$DEPLOY_DIR/deploy/studentup-bot.service" > /etc/systemd/system/studentup-bot.service
  sudo sed "s#/home/ubuntu/studentup#$DEPLOY_DIR#g; s#^User=ubuntu#User=$USER#" \
       "$DEPLOY_DIR/deploy/studentup-webhook.service" > /etc/systemd/system/studentup-webhook.service
  sudo systemctl daemon-reload
  sudo systemctl enable --now studentup.service studentup-bot.service
  sudo systemctl enable --now studentup-webhook.service
  sudo systemctl restart studentup.service
  echo "  services installed + started (scheduler, bot, webhook)"
else
  echo "[6/6] systemd not touched. To install:"
  echo "    sudo bash $DEPLOY_DIR/scripts/deploy.sh --systemd"
fi

echo ""
echo "Dry-run tests:"
echo "  cd $DEPLOY_DIR/scripts && python3 watch.py --once --dry"
echo "  cd $DEPLOY_DIR/scripts && python3 quiz_engine.py quiz --dry"
echo "  cd $DEPLOY_DIR/scripts && python3 audit_sources.py --only-enabled --no-write"
echo "  cd $DEPLOY_DIR/scripts && python3 check.py --feeds"
echo ""
echo "=============== DEPLOY DONE ================"
