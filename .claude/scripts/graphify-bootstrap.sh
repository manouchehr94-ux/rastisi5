#!/usr/bin/env bash
set -u

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
    exit 0
fi

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
VENV="$ROOT/.graphify-venv"
GRAPHIFY="$VENV/bin/graphify"
LOG="/tmp/rastisi-graphify-bootstrap.log"

cd "$ROOT" || exit 0

if [ ! -x "$GRAPHIFY" ]; then
    rm -rf "$VENV"

    if command -v uv >/dev/null 2>&1; then
        uv venv "$VENV" >"$LOG" 2>&1 || true
        uv pip install --python "$VENV/bin/python" "graphifyy==0.9.46" >>"$LOG" 2>&1 || true
    else
        python3 -m venv "$VENV" >"$LOG" 2>&1 || true
        "$VENV/bin/python" -m pip install "graphifyy==0.9.46" >>"$LOG" 2>&1 || true
    fi
fi

if [ ! -x "$GRAPHIFY" ]; then
    printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"Graphify is unavailable. Continue with normal source navigation."}}'
    exit 0
fi

if [ -f "$ROOT/graphify-out/graph.json" ]; then
    "$GRAPHIFY" update "$ROOT" >>"$LOG" 2>&1 || true
else
    "$GRAPHIFY" extract "$ROOT" --code-only >>"$LOG" 2>&1 || true
fi

if [ -f "$ROOT/graphify-out/graph.json" ]; then
    printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"RastiSi Graphify graph is ready. Prefer narrow graph queries before broad source exploration, then verify actual source and tests."}}'
else
    printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"Graphify graph could not be built. Continue normally and do not block the task."}}'
fi

exit 0