# RastiSi repository guidance

- For RastiSi codebase investigation, debugging, architecture tracing, dependency analysis, impact analysis, and locating implementation/tests, use the `rastisi-code-map` skill.
- When `graphify-out/graph.json` exists, prefer narrow Graphify queries before broad Grep/Glob/Read scans.
- Graphify is a navigation map, not the source of truth. Verify relevant source files and tests before editing.
- Never commit `graphify-out/` or `.graphify-venv/`.
- Preserve tenant isolation, Store scoping, permissions, and cross-host/domain behavior.
- The canonical Git remote is `rastisi5`. Do not push to legacy `origin` unless explicitly requested.