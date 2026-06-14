# Perfect-Codebase Roadmap

**Set:** 2026-06-13
**Purpose:** Sequencing index for the directive set aimed at making the WebService a SOLID-perfect implementation. Not a directive itself -- a reading order.

## The set

| Seq | Directive | Why it sits here |
|---|---|---|
| 1 | `paged-query-core.md` | Backend Repository paging primitive. Precondition for the table renderer's server data source. No frontend coupling. |
| 2 | `ajax-client-service.md` | HTTP wrapper that every subsequent service uses for transport. |
| 3 | `client-logging-service.md` | Every other service routes errors through this. Depends on `ajax-client-service`. |
| 4 | `notification-service.md` | User-facing error / success reporting. Depends on `client-logging-service`. |
| 5 | `table-renderer-service.md` | Solves the immediate 1.5GB memory symptom AND establishes the `IEditor` interface reused by `form-renderer-service`. Depends on 1-4. |
| 6 | `form-renderer-service.md` | Reuses `IEditor` from 5. Depends on 2, 3, 4, 5. |
| 7 | `modal-service.md` | May contain content rendered by 5, 6. Depends on 3, 4. |

## Why this order

- **Backend first (1)**: the table renderer's server data source needs the paging primitive before the frontend gates can be verified.
- **Shared transport before consumers (2)**: every other client service does HTTP. Bringing them up in any other order forces rewrites.
- **Logging before user-facing services (3)**: errors inside the notification or table services need somewhere to go.
- **Notifications before table renderer (4)**: the renderer's inline-edit failure path emits notifications.
- **Table before form (5 -> 6)**: forms reuse the editor abstraction the table directive establishes.
- **Modals last (7)**: most coupled to other services, least blocking.

## Cross-cutting principles applied across all 7

- One class per file. One responsibility per class.
- Interfaces live in `Interfaces/` subfolders. Concretes depend on interfaces, not on each other.
- No hardcoded thresholds / timeouts / sizes -- every magic number is a `*Config.js` value.
- No vendor library substitute for any of these primitives. SOLID purity over pragmatism (explicit operator preference).
- Each directive owns a `*.feature.md` contract with an `**API Version:**` SemVer field.
- Each directive ships contract tests covering its public surface.

## Activation protocol

To activate the next directive in sequence:

```powershell
git mv .claude/directives/backlog/<slug>.md .claude/directive.md
# Edit Status line to: **Status:** Active -- phase: NEEDS_STANDARDS_REVIEW
```

The roadmap file itself (`_perfect-codebase-roadmap.md`) is documentation, not a directive -- it stays in `backlog/` permanently as a reading index.

## Existing in-flight work that comes first

The active directive (`failure-accounting`, currently VERIFYING) closes before activating directive 1 from this set. Do not interleave.
