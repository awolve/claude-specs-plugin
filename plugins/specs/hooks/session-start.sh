#!/bin/bash
# Pull latest specs on session start (runs async, won't block startup)
set -euo pipefail

PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

python3 "${PLUGIN_ROOT}/scripts/sync.py" pull 2>&1 || {
    echo "specs-plugin: pull failed (network down or not configured)" >&2
}
