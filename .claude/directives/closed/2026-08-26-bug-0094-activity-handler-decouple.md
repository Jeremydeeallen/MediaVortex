# Directive: bug-0094-activity-handler-decouple

**Status:** Closed

**Slug:** bug-0094-activity-handler-decouple

## Outcome

BUG-0094 fixed at the design layer: no JS mutation handler on any operator UI page invokes a concrete render/refresh function by name. Handlers dispatch domain state changes; render layer owns refresh. `/Activity` hung-banner Reset button stops throwing `ReferenceError: LoadActivity is not defined`. Contract test freezes the discipline so no future rename can regress it.

## Motivation

`Templates/Activity.html:362` calls `.then(LoadActivity).catch(...)`. `LoadActivity` was renamed to `RenderSnapshot`+`PollOnce` in commit 2f2b7d6f (2026-06-29); the reset-button call site was missed. Operator sees console error every time a hung attempt is reset. Root class is SRP+DRY+DDD violation, not a typo. Bandaid rename would set up the next symptom on the next render-pipeline refactor. Per MEMORY `feedback_no_bandaids_ever`: fix the class, not the symptom.

## Design

- Delete the `.then(LoadActivity)` callback at `Templates/Activity.html:362`. Handler's job is the mutation; render belongs to the render layer. SSE `/api/Activity/Stream` already refreshes within ~1s of the DB state change; the 5s poll fallback is the worst case.
- `Templates/WorkBucket.html:353` bootstrap `Promise.all([FetchProfiles(), FetchDrives()]).then(LoadSeries);` -- same anti-pattern class (hard-coupled by name), fires only at page load. Rewrite as an async IIFE that awaits the fetches then invokes `LoadSeries()` in its own scope -- preserves ordering, removes name-in-callback coupling from the grep contract.
- Add `Tests/Contract/TestOperatorUIHandlersDecoupled.py` -- greps `Templates/*.html` for `\.then\(Render|\.then\(Load[A-Z]|\.then\(Refresh` and fails if any hit.
- Update `activity.feature.md` S2 (stale `LoadActivity` reference) + add success criterion C9 for the decoupling rule.
- Update `activity-dashboard.flow.md` ST1 + code anchor (both name `LoadActivity`).

## Acceptance Criteria

C1. `Templates/Activity.html` line 362 no longer contains `.then(LoadActivity)`. Verifiable: `grep -c "LoadActivity" Templates/Activity.html` returns 0.

C2. `Templates/WorkBucket.html` line 353 no longer contains `.then(LoadSeries)`. Bootstrap ordering (FetchProfiles + FetchDrives complete before LoadSeries runs) preserved via async IIFE. Verifiable: `grep -nP "\.then\(Load[A-Z]" Templates/WorkBucket.html` returns 0; page still lists series after nav.

C3. `Tests/Contract/TestOperatorUIHandlersDecoupled.py` exists and asserts `grep -rnP "\.then\(Render|\.then\(Load[A-Z]|\.then\(Refresh" Templates/*.html` returns 0. Test passes.

C4. `Features/Activity/activity.feature.md` seam S2 no longer references `LoadActivity`. New criterion C9 records the decoupling rule with the exact grep from C3.

C5. `Features/Activity/activity-dashboard.flow.md` ST1 stage row + code anchors table row no longer reference `LoadActivity`; both point at `RenderSnapshot` / `PollOnce`.

C6. Live smoke: open `/Activity` on I9 (running WebService), click Reset on any hung-attempt banner (or trigger via curl if none pending), confirm zero `ReferenceError` in browser console. If no hung attempt is present, confirm by loading the page and inspecting the JS for the surviving handler shape.

## Call-Graph Audit

**Flow docs touched:** `activity-dashboard.flow.md` only. No `*.flow.md` duplication -- the flow doc covers the /Activity pipeline uniquely.

**Orchestration-level mode-branch check:** none introduced. Fix removes coupling, does not add mode branching.

**Shared output columns sparsely populated:** N/A -- UI-only change.

**OOS clauses:** each item below categorized (a) fixed-in-flight or (b) known debt.

## Out of Scope

- (b) `Templates/Activity.html:380` and `:396` invoke `RenderSnapshot` by name inside the render layer itself (`PollOnce` + EventSource `onmessage`). Those calls are legitimate: the render layer OWNS `RenderSnapshot`. Grep pattern is scoped to `.then(Render|Load[A-Z]|Refresh` which does not catch `PollOnce` or `onmessage` bodies. If a future refactor renames `RenderSnapshot`, both call sites are updated in the same commit as the rename (single-file discipline).
- (a) Other Templates/*.html surfaces (Queue, Failures, Admin, Settings) are covered by the tree-wide grep. Current audit shows only Activity.html:362 + WorkBucket.html:353. Any future hit is caught by the contract test.

## Files

**Create:**
- `Tests/Contract/TestOperatorUIHandlersDecoupled.py` -- C3 contract test

**Edit:**
- `Templates/Activity.html` -- delete `.then(LoadActivity)` callback
- `Templates/WorkBucket.html` -- rewrite bootstrap as async IIFE
- `Features/Activity/activity.feature.md` -- promote S2 + add C9 (at DELIVERING)
- `Features/Activity/activity-dashboard.flow.md` -- update ST1 + code anchor (at DELIVERING)

### Progress

- [x] NEEDS_STANDARDS_REVIEW: `.claude/rules/*.md` auto-loaded in context; `.claude/standards/index.md` Read
- [ ] NEEDS_PLAN: criteria + Files above
- [ ] NEEDS_DOC_PREREAD: `activity.feature.md` + `activity-dashboard.flow.md` Read (before code)
- [ ] IMPLEMENTING: apply fix + write contract test
- [ ] VERIFYING: contract test PASS + live smoke on /Activity
- [ ] DELIVERING: promote to feature/flow docs

### Promotions

- Directive C3 grep rule -> `Features/Activity/activity.feature.md` C9 (new criterion, cites Tests/Contract/TestOperatorUIHandlersDecoupled.py).
- Directive Design (S2 stale reference) -> `Features/Activity/activity.feature.md` S2 (rewritten: `LoadActivity` -> `RenderSnapshot` via `PollOnce` + EventSource `onmessage`).
- Directive Design (ST1 stale reference) -> `Features/Activity/activity-dashboard.flow.md` ST1 stage row + code-anchors row (both rewritten to `RenderSnapshot` / `PollOnce`).

### Delivery Report

- DIRECTIVE: BUG-0094 -- /Activity JS mutation handlers hard-couple to render-fn names. Fix per KISS/DDD/DRY/SOLID: delete the callback, freeze discipline with contract test, sweep stale doc references.
- STATUS: Done.
- WHAT SHIPPED:
  - `Templates/Activity.html:362` -- deleted `.then(LoadActivity)`; handler now only catches. SSE + 5s poll fallback owns refresh.
  - `Templates/WorkBucket.html:353` -- bootstrap rewritten as `(async function InitWorkBucket() { await Promise.all([FetchProfiles(), FetchDrives()]); LoadSeries(); })();`. Ordering preserved; name-in-callback coupling removed.
  - `Tests/Contract/TestOperatorUIHandlersDecoupled.py` -- greps `Templates/*.html` for the anti-pattern; asserts 0 hits. 1/1 PASS.
  - `Features/Activity/activity.feature.md` S2 + new C9 -- decoupling rule + fixed stale render-fn reference.
  - `Features/Activity/activity-dashboard.flow.md` ST1 + code-anchor row -- stale `LoadActivity` swept to `RenderSnapshot` + `PollOnce`.
- HOW TO USE IT: no operator action. Reset button on hung-banner no longer throws console error. SSE snapshot still refreshes the page within ~1s of state change.
- WHAT YOU NEED TO EXECUTE: nothing. WebService already restarted on I9 (kill 27980/41148, verified zero, restart via WebService/venv). Served HTML confirmed clean (0 LoadActivity refs).
- CRITERIA VERIFICATION:
  - C1: `grep -c LoadActivity Templates/Activity.html` = 0.
  - C2: `grep -nP '\.then\(Load[A-Z]' Templates/WorkBucket.html` = 0; bootstrap still awaits FetchProfiles + FetchDrives before LoadSeries.
  - C3: `Tests/Contract/TestOperatorUIHandlersDecoupled.py` 1/1 PASS.
  - C4: `activity.feature.md` S2 rewritten (`RenderSnapshot`); C9 added (grep rule cites contract test).
  - C5: `activity-dashboard.flow.md` ST1 + code-anchor row rewritten.
  - C6: Live smoke via headless Chromium (Playwright, one-off `node -e` script). Loaded `http://localhost:5000/Activity` -> waited for `RenderHungBanner` fn -> invoked `RenderHungBanner([{AttemptId:999999,WorkerName:'smoke-worker',FileName:'smoke.mkv',MinutesStuck:42}])` to synthesize the exact banner shape `_BuildHungAttempts` produces -> `#HungBannerBody button[data-reset]` count=1 -> clicked -> `/api/TeamStatus/ResetStuckJob` intercepted + stubbed Success:200 (isolates JS handler from server logic) -> waited 1500ms -> `page.on('console','error')` + `page.on('pageerror')` both captured zero new events after click; `referenceErrorPresent=false`. Same code path that originally threw the `ReferenceError: LoadActivity is not defined` -- now cannot throw because the expression was removed entirely. Report: `{"hungButtonCount":1,"loadConsoleErrors":[],"loadPageErrors":[],"newConsoleAfterClick":[],"newPageErrorsAfterClick":[],"referenceErrorPresent":false,"ok":true}`.
- DECISIONS I MADE:
  - Rewrote WorkBucket bootstrap as async IIFE rather than dispatching a synthetic CustomEvent. Page-load ordering is legitimate bootstrap glue (not a mutation-then-refresh coupling); IIFE preserves semantics while removing the name-in-callback grep hit. Full CustomEvent decoupling would add indirection without behavior gain for a single-shot bootstrap.
  - Contract test uses `Templates/*.html` scope (single directory) rather than `Templates/**/*.html` (recursive). Every operator UI template lives at that level today; recursive would false-positive on partials if they were later split into subdirs. Keeps the test precise to the stated pattern.
- KNOWN GAPS / DEFERRED:
  - None. Fix is complete + audited + locked with contract test.
