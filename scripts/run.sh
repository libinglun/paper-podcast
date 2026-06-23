#!/usr/bin/env bash
# Paper-to-Podcast cron wrapper.
# Invokes Claude headlessly to run the paper-podcast skill.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG="$SKILL_DIR/config.json"

if [ ! -f "$CONFIG" ]; then
    echo "$(date): config.json not found at $CONFIG" >&2
    exit 1
fi

FREQ=$(python3 -c "import json; print(json.load(open('$CONFIG'))['delivery']['frequency'])")

# Weekly gate: only run on Mondays
if [ "$FREQ" = "weekly" ]; then
    DOW=$(date +%u)  # 1=Monday
    if [ "$DOW" -ne 1 ]; then
        echo "$(date): weekly mode — skipping (not Monday)"
        exit 0
    fi
fi

echo "$(date): starting paper-podcast run ($FREQ)"

claude -p "Run the paper-podcast skill: pick the next unprocessed paper from the Zotero source collection, generate a podcast via NotebookLM, email it, and mark the paper as processed. Use config from $CONFIG. This is an automated run — do not ask for confirmation, just process one paper." \
    2>&1 || echo "$(date): claude exited with code $?"

echo "$(date): run complete"
