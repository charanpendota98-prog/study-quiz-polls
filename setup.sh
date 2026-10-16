#!/usr/bin/env bash
# STUDENTUP — one-command easy setup:  bash setup.sh [--quick|--full]
set -u
cd "$(dirname "$0")"
exec python3 scripts/setup.py "$@"
