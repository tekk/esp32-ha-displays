#!/usr/bin/env bash
# Monthly catalog update – see build/update.py. Example: build/update.sh --dry-run
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 build/update.py "$@"
