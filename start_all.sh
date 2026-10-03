#!/usr/bin/env bash
# 🚀 StudentUp — ONE COMMAND START (any Linux/Mac/WSL machine)
# Runs Dashboard (:5000) + WhatsApp Bridge (:3900) with auto-restart on crash.
# Usage:  bash start_all.sh        (Ctrl+C stops both)
cd "$(dirname "$0")"

# install bridge deps once
if [ ! -d gateway/node_modules ]; then
  echo "📦 Installing WhatsApp bridge dependencies (first run only)..."
  (cd gateway && npm install --no-audit --no-fund)
fi

echo "🛡️  Starting StudentUp stack — Dashboard :${DASHBOARD_PORT:-5000} | Bridge :${WA_BRIDGE_PORT:-3900}"

run_forever() {
  local name="$1"; shift
  while true; do
    echo "▶️  $name starting..."
    "$@"
    echo "⚠️  $name exited — restarting in 5s..."
    sleep 5
  done
}

trap 'echo; echo "🛑 Stopping StudentUp..."; kill 0' INT TERM

run_forever "Dashboard" python3 scripts/dashboard_server.py &
run_forever "WA-Bridge" node gateway/wa_bridge.js &
wait
