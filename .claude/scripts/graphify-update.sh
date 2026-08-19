#!/usr/bin/env bash
set -u

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
    exit 0
fi

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
GRAPHIFY="$ROOT/.graphify-venv/bin/graphify"
LOG="/tmp/rastisi-graphify-update.log"

if [ ! -x "$GRAPHIFY" ]; then
    exit 0
fi

if [ ! -f "$ROOT/graphify-out/graph.json" ]; then
    exit 0
fi

cd "$ROOT" || exit 0

"$GRAPHIFY" update "$ROOT" >"$LOG" 2>&1 || true

exit 0