# Notification Service

**Set:** 2026-06-13
**Status:** Backlog -- sequence position 4 in perfect-codebase set
**Slug:** notification-service

## Outcome

Every transient user-facing message (success toast, error toast, warning banner, confirmation prompt) is rendered by a single `NotificationService`. Pages call `NotificationService.Show({Level, Message})`; the service owns position, stacking, timing, dismissal, and ARIA `aria-live` announcement. The hand-rolled `ShowNotification(...)` reimplementation in every template goes away.

## Acceptance Criteria

1. **Single notification service.** `static/js/Notifications/NotificationService.js` exposes `ShowSuccess`, `ShowInfo`, `ShowWarning`, `ShowError`, `ShowConfirm` (returns Promise resolving Yes/No). All return a `NotificationHandle` for programmatic dismissal.

2. **No per-page notification implementations.** Verifiable: `grep -rE "function ShowNotification\\(|function ShowToast\\(" Templates/` returns zero matches after migration.

3. **SRP -- one responsibility per class.** `NotificationService` (orchestrator + API surface), `NotificationQueue` (queue + stack mgmt), `NotificationRenderer` (DOM mutation only), `NotificationDismiss` (timeout / click / manual dismissal strategy), `NotificationConfig` -- each in its own file.

4. **OCP -- new notification type without service change.** Adding a new visual style (banner, modal-style, slide-in-from-bottom) is a new `NotificationRenderer` subclass registered with the service. Verifiable: add a `BannerRenderer`; `git diff --stat static/js/Notifications/NotificationService.js` is empty.

5. **LSP -- renderer substitution.** Any `INotificationRenderer` plugs in. Verifiable: contract test substitutes a `StubRenderer` and asserts notification lifecycle events fire.

6. **ISP -- focused interfaces.** `INotificationRenderer` (`Render(Notification)`, `Dismiss(Notification)`), `IDismissStrategy` (`AttachTo(Notification)`). No god-interface.

7. **DIP -- pages depend on `NotificationService` abstract, not Bootstrap toast / vendor lib.** No page references `bootstrap.Toast` or similar.

8. **Stacking and z-index.** Multiple notifications stack predictably (newest on top by default; configurable). Z-index from `NotificationConfig`, no magic numbers in CSS.

9. **Dismissal strategies.** Configurable per-notification: timeout-only, click-only, manual-only, timeout-or-click. Default by level: Success/Info auto-dismiss after `NotificationConfig.DefaultTimeoutMs`; Warning/Error stay until clicked.

10. **Accessibility.** Each notification is in an `aria-live` region; Warning/Error use `assertive`, Success/Info use `polite`. Role is `status` for non-error, `alert` for error. Verifiable: axe-core reports zero violations.

11. **ConfirmDialog.** `ShowConfirm({Title, Message, ConfirmLabel, CancelLabel})` returns a Promise; replaces ad-hoc `window.confirm` and bespoke confirmation modals.

12. **Feature doc owns the contract.** `Features/Notifications/notifications.feature.md` exists with Workflows, Seams, Criteria, API Version.

13. **Contract tests.** `Tests/Static/TestNotificationService.js` covers stacking order, dismissal strategies, level-based defaults, confirm Promise resolution.

14. **Migration completeness.** Every page that currently calls a local `ShowNotification(...)` is migrated.

## Out of Scope

- In-app messaging / inbox.
- Push notifications.
- Email notifications -- server-side concern.

## Constraints

- PascalCase per CLAUDE.md.
- No hardcoded timeouts, z-indexes, animation durations -- all from `NotificationConfig`.
- No vendor toast library.
- Built on top of `HttpClient` and `ClientLogger` (dependencies).

## Engineering Calls Already Made

- Promise-based `ShowConfirm` over callback-based.
- Stack newest-on-top default; configurable per-call.
- One DOM container (`#NotificationStack`) injected once into `Base.html`.

## Status

Backlog 2026-06-13 -- sequence position 4. Depends on `client-logging-service` (for error reporting from within the service itself).

### Files

```
static/js/Notifications/NotificationService.js          -- CREATE: orchestrator
static/js/Notifications/NotificationQueue.js            -- CREATE
static/js/Notifications/NotificationRenderer.js         -- CREATE: default renderer
static/js/Notifications/NotificationDismiss.js          -- CREATE: dismissal strategies
static/js/Notifications/Notification.js                 -- CREATE: value object
static/js/Notifications/NotificationLevel.js            -- CREATE: enum
static/js/Notifications/NotificationConfig.js           -- CREATE
static/js/Notifications/ConfirmDialog.js                -- CREATE
static/js/Notifications/Interfaces/INotificationRenderer.js -- CREATE
static/js/Notifications/Interfaces/IDismissStrategy.js      -- CREATE
static/css/Notifications.css                            -- CREATE: notification styles
Features/Notifications/notifications.feature.md         -- CREATE: the contract
Templates/Base.html                                     -- EDIT: inject #NotificationStack container
Tests/Static/TestNotificationService.js                 -- CREATE
Tests/Static/TestNotificationQueue.js                   -- CREATE
Templates/*.html                                        -- EDIT: replace local ShowNotification calls
```

### Promotions / Verification / Decisions Made

To populate at appropriate phases.
