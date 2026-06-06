# Directive (backlog): Query vs Write Split (CQRS-light)

**Slug:** query-vs-write-split
**Prerequisite:** `db-monolith-decompose` + `dbsession-protocol-extract` (Reader/Writer split is most valuable once Repos exist + are Protocol-injected)

## Outcome

Per-aggregate `<X>Reader` and `<X>Writer` (or equivalent split) separate operator-facing reads from worker-facing writes. Reads can cache aggressively (request-scoped or short-TTL); writes stay DB-truth and conflict-safe. Cross-aggregate JOIN methods land in a dedicated `<X>QueryService` (read-only, can span multiple Readers).

After this directive: list endpoints (`/Activity`, `/Scanning`, `/TranscodeQueue`) hit Readers with appropriate caching; worker claim + update paths hit Writers; the N+1 patterns we see today (e.g. `GetMkvCountsByRootFolder`'s 538 COUNT queries) get rewritten into single-query Readers that are testable + observable.

## Acceptance Criteria

1. Per-aggregate split exists: e.g. `MediaFilesReader` (SELECTs only) + `MediaFilesWriter` (INSERT/UPDATE/DELETE). Each is independently constructor-injectable.
2. Cross-aggregate JOIN methods (the `cross-aggregate` flags from `db-monolith-decompose`'s inventory CSV) land in feature-specific `<X>QueryService.py` classes. These compose multiple Readers; they do not write.
3. Reader interfaces are SAFE to cache (idempotent, no side effects). A new `@cached_request_scoped` decorator (or contextvar-based equivalent built on `Core.Path.PathStorageRoots.PrefixMapScope`'s pattern) makes opt-in caching one line.
4. The `/api/RootFolders` N+1 (538 `COUNT(*)` queries) is rewritten into a single Reader method that returns folder + count in one query. Endpoint latency drops below 1s for 1000+ folders.
5. R-rule (or new rule): Writers MUST NOT be passed into endpoints that only read; Readers MUST NOT have side effects. Hook enforces by import + usage analysis or by naming convention.
6. Existing pytest green; new tests cover Reader caching semantics + Writer transactional semantics.

## Out of Scope

- Full event-sourcing CQRS. This is CQRS-LIGHT: same DB, just split interfaces.
- Read-replica routing. The split unlocks it later; this directive doesn't ship the routing.
- Async / pub-sub between Writer and Reader. Direct synchronous shared DB.

## Why this is backlog

The split is most valuable AFTER per-aggregate Repos exist. Order matters: monolith decompose -> protocol extract -> CQRS split. Each step unlocks the next.

## Estimated scope

Large. 20-30 Reader/Writer pairs, the QueryService layer, cache decorator, endpoint sweeps. Probably broken into per-aggregate sub-directives (mirroring `db-monolith-decompose`'s aggregate-at-a-time pattern via a similar GitHub workflow).
