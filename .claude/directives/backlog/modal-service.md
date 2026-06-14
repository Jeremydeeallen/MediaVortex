# Modal Service

**Set:** 2026-06-13
**Status:** Backlog -- sequence position 7 in perfect-codebase set
**Slug:** modal-service

## Outcome

Every modal in the WebService is opened, stacked, and closed by a single `ModalManager`. Pages declare modal content + lifecycle hooks; the manager owns z-index, backdrop, scroll-lock, focus-trap, Esc-to-close, and stack ordering. The ad-hoc `$('#myModal').modal('show')` pattern goes away in favor of `ModalManager.Open({Content, OnConfirm, OnCancel})`.

## Acceptance Criteria

1. **Single modal manager.** `static/js/Modals/ModalManager.js` exposes `Open(Definition) -> ModalHandle`, where `ModalHandle` has `Close()`, `Update(Content)`, `Subscribe(EventName, Handler)`.

2. **No direct `$().modal()` calls.** Verifiable: `grep -rE "\\.modal\\(" Templates/ static/js/Pages/` returns zero matches after migration.

3. **SRP -- one responsibility per class.** `ModalManager` (orchestrator + stack), `ModalDefinition` (declarative config), `ModalLifecycle` (open/close/dismiss events), `ModalRenderer` (DOM mutation), `FocusTrap` (focus management), `ScrollLock` (body scroll), `ModalConfig`.

4. **OCP -- new modal type without manager change.** Adding a new visual style (drawer-from-right, fullscreen, bottom-sheet) is a new `ModalRenderer` subclass. `ModalManager.js` is not edited.

5. **LSP -- renderer substitution.** Any `IModalRenderer` plugs in.

6. **ISP -- focused interfaces.** `IModalRenderer` (`Render(Modal)`, `Dismiss(Modal)`), `IFocusTrap` (`Activate(Element)`, `Deactivate()`), `IScrollLock` (`Lock()`, `Unlock()`).

7. **DIP -- pages depend on `ModalManager` abstract, not Bootstrap modal.** No page references `bootstrap.Modal` or similar.

8. **Stack management.** Multiple modals stack with predictable z-index from `ModalConfig`; Esc closes the topmost only; closing a non-top modal preserves stack order.

9. **Focus trap and restoration.** Tab cycles within the modal; Shift+Tab cycles back; focus returns to the element that opened the modal on close. Axe-core zero violations on focus-related rules.

10. **Body scroll lock.** While any modal is open, body scroll is locked; restored on last modal close. Scroll position preserved.

11. **Esc-to-close + backdrop-click-to-close.** Configurable per-modal via `Definition.DismissOnEscape`, `Definition.DismissOnBackdrop`.

12. **Promise-based result.** `ModalManager.Open({...}).Result` is a Promise resolving with the modal's outcome (confirm value, cancel marker). Replaces callback-based dismissal.

13. **Feature doc owns the contract.** `Features/Modals/modal-manager.feature.md` exists with Workflows, Seams, Criteria, API Version.

14. **Contract tests.** `Tests/Static/TestModalManager.js` covers stack ordering, focus trap, scroll lock, Esc/backdrop behavior, Promise resolution.

15. **Migration completeness.** Every modal in the codebase is migrated. Initial set: confirmation modals on Activity, Operations, ShowSettings; the QueueAdd modal; any inline-edit modal on Settings.

## Out of Scope

- Toast / non-blocking notifications -- see `notification-service.md`.
- Right-side drawer navigation -- separate concern if pursued.

## Constraints

- PascalCase per CLAUDE.md.
- No hardcoded z-indexes, animation durations -- all from `ModalConfig`.
- No vendor modal library.
- Built on top of `ClientLogger` (logs modal errors); modal content may use `FormRenderer`, `TableRenderer`, `NotificationService` freely.

## Engineering Calls Already Made

- Promise-based result over callback config.
- One injected `#ModalStack` container in `Base.html`.
- Focus trap is a separate class so it can be reused by any focus-trapped UI (drawers, tour overlays).

## Status

Backlog 2026-06-13 -- sequence position 7 (last). Depends on `notification-service`, `client-logging-service`. May open content rendered by `TableRenderer` or `FormRenderer`.

### Files

```
static/js/Modals/ModalManager.js                    -- CREATE: orchestrator + stack
static/js/Modals/Modal.js                           -- CREATE: value object
static/js/Modals/ModalDefinition.js                 -- CREATE
static/js/Modals/ModalLifecycle.js                  -- CREATE: open/close events
static/js/Modals/ModalRenderer.js                   -- CREATE: default renderer
static/js/Modals/FocusTrap.js                       -- CREATE
static/js/Modals/ScrollLock.js                      -- CREATE
static/js/Modals/ModalConfig.js                     -- CREATE
static/js/Modals/Interfaces/IModalRenderer.js       -- CREATE
static/js/Modals/Interfaces/IFocusTrap.js           -- CREATE
static/js/Modals/Interfaces/IScrollLock.js          -- CREATE
static/css/Modals.css                               -- CREATE: modal styles
Features/Modals/modal-manager.feature.md            -- CREATE: the contract
Templates/Base.html                                 -- EDIT: inject #ModalStack
Tests/Static/TestModalManager.js                    -- CREATE
Tests/Static/TestFocusTrap.js                       -- CREATE
Tests/Static/TestScrollLock.js                      -- CREATE
Templates/*.html                                    -- EDIT: replace bootstrap .modal() calls
```

### Promotions / Verification / Decisions Made

To populate at appropriate phases.
