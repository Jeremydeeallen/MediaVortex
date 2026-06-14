# AJAX Client Service

**Set:** 2026-06-13
**Status:** Backlog -- sequence position 2 in perfect-codebase set
**Slug:** ajax-client-service

## Outcome

Every client-side HTTP call in the WebService goes through a single `HttpClient` service with consistent error handling, timeout policy, retry policy, request/response middleware, and instrumentation. Pages call `HttpClient.Get(Url)` / `.Post(Url, Body)` etc. instead of `$.ajax({...})` or `fetch()`. Network errors, timeouts, and 5xx responses are handled in one place; user-facing error messages and client-side logging come from one place.

## Acceptance Criteria

1. **Single HTTP client.** `static/js/Http/HttpClient.js` exposes `Get`, `Post`, `Put`, `Delete`, `Patch`. Returns Promises resolving to a typed `HttpResponse { Success, StatusCode, Data, Message }`. Verifiable: file exists with that public surface.

2. **No direct `$.ajax` / `fetch` in pages.** Verifiable: `grep -rE "\\\$\\.ajax\\(|\\\$\\.get\\(|\\\$\\.post\\(|fetch\\(" Templates/ static/js/Pages/` returns zero matches after migration (excluding `HttpClient.js` itself).

3. **SRP -- one responsibility per class.** `HttpClient` (orchestrator), `RequestPipeline` (request middleware chain), `ResponsePipeline` (response middleware chain), `RetryPolicy`, `TimeoutPolicy`, `ErrorHandler`, `HttpClientConfig` -- each in its own file.

4. **OCP -- new middleware without client change.** Adding a request- or response-middleware (e.g. CSRF token, request ID, payload logging) is a new class implementing the middleware interface, registered with the pipeline. `HttpClient.js` is not edited. Verifiable: add a `RequestIdMiddleware`; `git diff --stat static/js/Http/HttpClient.js` is empty.

5. **LSP -- middleware substitution.** Any middleware implementing the interface composes into the pipeline. Verifiable: contract test composes 3 middlewares in different orders and asserts each runs.

6. **ISP -- focused middleware interfaces.** `IRequestMiddleware` (`Process(Request) -> Request`), `IResponseMiddleware` (`Process(Response) -> Response`), `IErrorMiddleware` (`Process(Error) -> Error | Response`). No god-interface. Verifiable: each interface file <=15 lines.

7. **DIP -- pages depend on `HttpClient` abstract, not concrete.** Pages receive a client instance (or use the singleton); no page constructs `XMLHttpRequest` or imports a vendor HTTP library.

8. **Centralised timeout policy.** Default request timeout is configured in `HttpClientConfig` (no per-page magic numbers). Per-call override via `{Timeout: <ms>}`. Verifiable: `grep -rE "timeout:|setTimeout.*request" Templates/ static/js/Pages/` returns zero matches after migration.

9. **Centralised retry policy.** Idempotent verbs (`GET`, `PUT`, `DELETE`) retry on network failure / 502 / 503 / 504 with exponential backoff; non-idempotent verbs (`POST`, `PATCH`) do not retry by default. Verifiable: contract test simulates a 503 and asserts a `GET` retried, a `POST` did not.

10. **Centralised error handling.** Network errors / 5xx / `Success: False` JSON responses are routed through `ErrorHandler`, which emits a `NotificationService` toast (depends on `notification-service.md`) and a `ClientLogger` entry (depends on `client-logging-service.md`). No raw exception strings reach the user. Verifiable: simulate a 500; toast says "Request failed" not the exception text; `client_logs` table has the structured entry.

11. **Instrumentation.** Every request emits start / success / failure events consumable via `HttpClient.Subscribe(EventName, Handler)`. Verifiable: instrument once, observe per-request lifecycle.

12. **Feature doc owns the contract.** `Features/HttpClient/http-client.feature.md` exists with Workflows, Seams, Criteria, API Version field.

13. **Contract tests.** `Tests/Static/TestHttpClient.js` covers retry policy, timeout policy, middleware composition, error routing.

14. **Migration completeness.** Every page in `Templates/` that makes HTTP calls is migrated. Initial set: every page currently using `$.ajax` / `$.get` / `$.post`. Verifiable: per C2 grep.

## Out of Scope

- Service workers / offline support.
- WebSocket / SSE -- separate transport, separate directive.
- Request body serialization beyond JSON.
- Replacing the Python-side Flask request handling.

## Constraints

- Native `fetch()` under the hood, not jQuery.
- PascalCase per CLAUDE.md.
- No hardcoded timeouts, retry counts, backoff multipliers -- all in `HttpClientConfig`.
- Compatibility with the existing API response shape `{Success, Message, Data}`.

## Engineering Calls Already Made

- `fetch()` over `XMLHttpRequest` -- modern, native, no vendor.
- Promise-based, not callback-based.
- Singleton convenience instance (`HttpClient.Default`) plus constructable for tests with stub config.

## Status

Backlog 2026-06-13 -- sequence position 2.

### Files

```
static/js/Http/HttpClient.js                        -- CREATE: orchestrator
static/js/Http/HttpResponse.js                      -- CREATE: response value object
static/js/Http/HttpRequest.js                       -- CREATE: request value object
static/js/Http/RequestPipeline.js                   -- CREATE
static/js/Http/ResponsePipeline.js                  -- CREATE
static/js/Http/RetryPolicy.js                       -- CREATE
static/js/Http/TimeoutPolicy.js                     -- CREATE
static/js/Http/ErrorHandler.js                      -- CREATE
static/js/Http/HttpClientConfig.js                  -- CREATE: defaults
static/js/Http/Interfaces/IRequestMiddleware.js     -- CREATE
static/js/Http/Interfaces/IResponseMiddleware.js    -- CREATE
static/js/Http/Interfaces/IErrorMiddleware.js       -- CREATE
Features/HttpClient/http-client.feature.md          -- CREATE: the contract
Tests/Static/TestHttpClient.js                      -- CREATE
Tests/Static/TestRetryPolicy.js                     -- CREATE
Tests/Static/TestTimeoutPolicy.js                   -- CREATE
Tests/Static/TestMiddlewareComposition.js           -- CREATE
Templates/*.html                                    -- EDIT: migrate ajax calls page-by-page
```

### Promotions / Verification / Decisions Made

To populate at appropriate phases.
