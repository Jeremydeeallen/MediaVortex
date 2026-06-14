# Client Logging Service

**Set:** 2026-06-13
**Status:** Backlog -- sequence position 3 in perfect-codebase set
**Slug:** client-logging-service

## Outcome

Every page logs through a single `ClientLogger` service that batches, formats, and transports log entries to `/api/ClientLog`. Log level, batching window, and transport are configured once. Errors caught anywhere in client code -- in pages, in the `HttpClient`, in the `TableRenderer` -- route through this service. No page does `console.log` for production telemetry; no page calls `/api/ClientLog` directly.

## Acceptance Criteria

1. **Single client logger.** `static/js/Logging/ClientLogger.js` exposes `Debug`, `Info`, `Warn`, `Error`, each accepting `(Message, Context, ClassName, MethodName)` to mirror the Python `LoggingService` shape.

2. **No direct `/api/ClientLog` calls.** Pages do not POST to the endpoint; they call `ClientLogger.Error(...)`. Verifiable: `grep -rE "/api/ClientLog" Templates/ static/js/Pages/` returns zero matches after migration (only `ClientLogger.js` contains it).

3. **SRP -- one responsibility per class.** `ClientLogger` (orchestrator), `LogBatcher` (queue + flush window), `LogFormatter` (entry shape), `LogTransport` (network), `LogLevel` (enum), `ClientLoggerConfig` -- each in its own file.

4. **OCP -- new transport without logger change.** Adding a new transport (e.g. localStorage fallback when offline) is a new class implementing `ILogTransport`. `ClientLogger.js` is not edited. Verifiable: add a `LocalStorageTransport`; `git diff --stat static/js/Logging/ClientLogger.js` is empty.

5. **LSP -- transport substitution.** Any `ILogTransport` plugs in. Verifiable: contract test substitutes a `StubTransport` and asserts entries arrive in order.

6. **ISP -- focused interfaces.** `ILogTransport` (`Send(Entries)`), `ILogFormatter` (`Format(Entry)`), `ILogBatcher` (`Add(Entry)`, `Flush()`). No god-interface.

7. **DIP -- pages depend on `ClientLogger` abstract, not the endpoint.** No page constructs an HTTP request to log; no page imports a vendor logging library.

8. **Batching.** Default flush window 5s OR queue depth 50, whichever first. `flush()` on `beforeunload`. Verifiable: contract test queues 49 entries, asserts no transport call; queues 1 more, asserts one batched POST.

9. **Level filtering.** `Debug` and `Info` filtered out by default in production config; `Warn` and `Error` always shipped. Verifiable: per-level test against config.

10. **Error capture wiring.** Unhandled errors (`window.onerror`, `unhandledrejection`) route through `ClientLogger.Error` with stack + URL + user agent. Verifiable: throw an uncaught error in a test page; `client_logs` row exists with stack.

11. **No PII leakage.** A `LogScrubber` middleware redacts known sensitive substrings before transport (email-shaped, credential-shaped patterns). Configurable patterns. Verifiable: contract test feeds an email-shaped string; transported entry has `<redacted>`.

12. **Feature doc owns the contract.** `Features/ClientLogger/client-logger.feature.md` exists with Workflows, Seams, Criteria, API Version.

13. **Contract tests.** `Tests/Static/TestClientLogger.js` covers batching boundaries, level filtering, transport failure handling, scrubber redaction.

14. **Migration completeness.** Every page that currently logs through ad-hoc `console.error` or direct POSTs to `/api/ClientLog` is migrated.

## Out of Scope

- Server-side `LoggingService` -- already exists.
- Log aggregation / dashboards.
- Performance tracing (timing API). Separate concern, separate directive if pursued.

## Constraints

- PascalCase per CLAUDE.md.
- No hardcoded flush window / batch size / level filter -- all from `ClientLoggerConfig`.
- Uses `HttpClient` from `ajax-client-service.md` as the underlying transport (dependency).
- Singleton convenience instance (`ClientLogger.Default`) plus constructable for tests.

## Engineering Calls Already Made

- Mirror Python `LoggingService` method shape so client logs and server logs read uniformly.
- Batched POSTs over per-call POSTs (network cost).
- `beforeunload` flush over service-worker queueing (simpler, sufficient for dev tool).

## Status

Backlog 2026-06-13 -- sequence position 3. Depends on `ajax-client-service`.

### Files

```
static/js/Logging/ClientLogger.js                   -- CREATE: orchestrator
static/js/Logging/LogLevel.js                       -- CREATE: enum
static/js/Logging/LogEntry.js                       -- CREATE: value object
static/js/Logging/LogBatcher.js                     -- CREATE
static/js/Logging/LogFormatter.js                   -- CREATE
static/js/Logging/LogTransport.js                   -- CREATE: HTTP transport via HttpClient
static/js/Logging/LogScrubber.js                    -- CREATE
static/js/Logging/ClientLoggerConfig.js             -- CREATE
static/js/Logging/Interfaces/ILogTransport.js       -- CREATE
static/js/Logging/Interfaces/ILogFormatter.js       -- CREATE
static/js/Logging/Interfaces/ILogBatcher.js         -- CREATE
Features/ClientLogger/client-logger.feature.md      -- CREATE: the contract
Tests/Static/TestClientLogger.js                    -- CREATE
Tests/Static/TestLogBatcher.js                      -- CREATE
Tests/Static/TestLogScrubber.js                     -- CREATE
Templates/*.html                                    -- EDIT: migrate ad-hoc logging page-by-page
```

### Promotions / Verification / Decisions Made

To populate at appropriate phases.
