#!/bin/bash
# After Write/Edit, check if the file is a spec and push if so
set -euo pipefail

PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Read tool use JSON from stdin and pass to sync script
python3 "${PLUGIN_ROOT}/scripts/sync.py" post-tool-use 2>&1 || {
    echo "specs-plugin: post-tool-use hook failed" >&2
}
