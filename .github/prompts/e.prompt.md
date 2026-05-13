---
description: "Fetch and display unresolved errors from the project's declared error source, grouped by severity."
agent: "agent"
---
Fetch error signatures:

1. Discover the project's error source (telemetry system path, error log path, crash tracker). If no error source is declared in the project docs, report the absence and stop.

2. Fetch unresolved errors from the discovered source.

3. Display grouped by severity (critical / error / warning). For each group, show: count, most recent occurrence, and representative stack or message.
