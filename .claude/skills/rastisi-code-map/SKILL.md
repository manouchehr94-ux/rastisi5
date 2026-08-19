---
name: rastisi-code-map
description: Use for RastiSi codebase investigation or modification when locating implementations, tracing Django flows, debugging, understanding architecture, finding dependencies/tests, or estimating change impact. Prefer Graphify graph-first navigation when its graph exists, then verify the actual source.
---

# RastiSi graph-first code navigation

1. If `graphify-out/graph.json` exists, begin with a narrow Graphify query before broad source searches.

2. Prefer exact symbols, feature names, and architectural layers:

   `graphify query "<exact symbol + feature + layer>" --budget 800`

3. If a query returns too many nodes, narrow the question. Do not solve broad queries merely by increasing the token budget.

4. Focus the result when useful:

   `graphify explain "<symbol>"`

   `graphify path "<A>" "<B>"`

   `graphify affected "<symbol>" --depth 2`

5. Then read only the source and test files needed to verify the real implementation.

6. For Django behavior, trace the smallest relevant chain:

   route -> view/form -> service -> model -> template -> tests

7. For RastiSi changes, explicitly verify tenant/store scoping, permissions, domain/subdomain routing, cross-host flows, and production-safe behavior whenever relevant.

8. Graph output is navigation evidence, never final truth. Source code and tests win if they disagree with the graph.

9. Never stage or commit `graphify-out/` or `.graphify-venv/`.

10. If Graphify or its graph is unavailable, continue with normal source navigation. Do not block the task.