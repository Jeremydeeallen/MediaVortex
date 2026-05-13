---
description: "Comprehensive startup performance audit. Identifies duplicate work, unnecessary delays, ordering issues, and optimization opportunities in application launch."
agent: "agent"
---
# Startup Flow Audit

Comprehensive startup performance audit. Identifies duplicate work, unnecessary delays, ordering issues, and optimization opportunities.

## Phase 1: Map the Entry Points

Identify every initialization trigger in order:
1. Process entry -- main(), bootstrap, server start
2. Framework callbacks -- lifecycle methods, dependency injection, module init
3. First render -- initial view/route/response ready for the user
4. Fully interactive -- all background work complete

For each: is it sync or async? What does it block?

## Phase 2: Trace Every Operation

For each operation between process start and fully interactive:

```
| Operation | Trigger | Sync/Async | Depends On | Duration | Blocks UI? |
```

Classify as: Critical path / Required background / Deferrable

## Phase 3: Build the Waterfall

Create an ASCII timeline showing execution order, parallel vs sequential, critical path, and idle gaps.

## Phase 4: Identify Problems

Check for:
- **Duplicate work**: same data fetched from multiple sources, same function called from multiple paths
- **Wrong timing**: blocking operations that could be async, work before dependencies ready
- **Every-resume work**: operations that should only run once, no freshness checks
- **Missing guards**: no "already initialized" check, no debounce on rapid triggers
