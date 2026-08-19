#!/usr/bin/env bash
set -u

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
    exit 0
fi

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
GRAPHIFY="$ROOT/.graphify-venv/bin/graphify"

if [ ! -x "$GRAPHIFY" ]; then
    exit 0
fi

if [ ! -f "$ROOT/graphify-out/graph.json" ]; then
    exit 0
fi

cd "$ROOT" || exit 0

exec "$GRAPHIFY" hook-guard "${1:-search}"