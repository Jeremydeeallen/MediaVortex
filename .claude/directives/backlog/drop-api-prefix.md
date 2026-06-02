# Backlog Directive: Drop /api URL Prefix

**Filed:** 2026-06-01 (paused mid-IMPLEMENTING when audit revealed near-universal triple-quoted SQL in controllers; pivoted to `flow-docs-as-hub` + `sql-to-repository` chain first)
**Status:** Backlog -- not yet started (carried-forward planning + carved Files list intact from session 2)
**Slug:** drop-api-prefix
**Replaces:** none
**Sequencing:** Runs THIRD in the chain (flow-docs-as-hub -> sql-to-repository -> drop-api-prefix). By then each controller is a thin Repository-caller with no SQL, so the URL rename is mechanically trivial. The deferred set in this directive's Files list (Activity / AudioFixPriorityHints / ClipBuilder / MediaProbe / TeamStatus) becomes empty because `sql-to-repository` will already have un-embedded their SQL, leaving only the prefix rename.

## Outcome

The `/api` URL prefix is gone from MediaVortex. Every Flask blueprint mounts at the root, every HTML template and client-side fetch/ajax/href targets a root path, and a new rule forbids re-introducing `/api/` anywhere. Operator-observable end state: `/Scanning` loads the scanning page directly; the Stats page "Manage" button works without modification; every existing JSON endpoint resolves at its new root-relative path with the same JSON contract; grep for `/api/` across `WebService/`, `Features/`, `Templates/`, `Core/`, `Repositories/`, `Scripts/`, `*.feature.md`, `*.flow.md`, `.claude/rules/`, `CLAUDE.md`, `memory/KNOWN-ISSUES.md` returns zero matches outside of historical archives (`.claude/directives/closed/`, `MEMORY.md` history snapshots).

## Acceptance Criteria

**Scope note (carved 2026-06-01):** 5 SQL-containing controllers + their template URLs are explicitly DEFERRED to the `sql-to-repository` follow-up directive (see Files list). The criteria below treat the deferred set as out-of-scope. The deferred controllers' endpoints continue to serve at `/api/...` until that follow-up directive lands.

The deferred endpoints set is:

```
/api/Activity/*            (ActivityController -- deferred)
/api/AudioFixPriorityHints/* (AudioFixPriorityHintsController -- deferred)
/api/ClipBuilder/*         (ClipBuilderController -- deferred)
/api/MediaProbe/*          (MediaProbeController -- deferred)
/api/TeamStatus/*          (TeamStatusController -- deferred)
```

1. **No `/api` route registrations** outside the deferred set. `Grep` for `url_prefix=['\"]/api` across `WebService/Main.py`, in-scope `Features/*/Controller*.py`, `Core/`, `Repositories/`, `Scripts/` returns matches ONLY for the 5 deferred controllers. Verified: a grep-based audit script enumerates each match and validates it belongs to the deferred set.

2. **No `/api/` literal strings in in-scope code or templates.** `Grep` for `/api/` across the in-scope file set returns only references to the 5 deferred endpoint prefixes. References to `/api/Activity/`, `/api/AudioFixPriorityHints/`, `/api/ClipBuilder/`, `/api/MediaProbe/`, `/api/TeamStatus/` may remain because their backing controllers are deferred. All other `/api/` strings are removed. Historical mentions in `.claude/directives/closed/`, `memory/KNOWN-ISSUES.md` Resolved sections, and memory snapshots are allowed.

3. **Stats page Manage button reaches the Scanning page.** Operator opens `http://10.0.0.7:5000/Stats`, clicks "Manage" in the Continuous File Scanning card, and lands on the scanning page with HTTP 200. No 404, no redirect chain. (`FileScanningController` is in scope.)

4. **Every in-scope previously-`/api`-prefixed JSON endpoint resolves at its new root path.** For each in-scope blueprint, a smoke check returns the same JSON shape as before. Deferred-set endpoints continue serving at `/api/...` until the follow-up directive. Verified by running `py -m pytest Tests/Contract/` to completion with the same pass/fail count as the pre-directive baseline.

5. **No deadlinks in templates.** `Grep` for `href=`, `fetch(`, `$.ajax(`, `$.get(`, `$.post(`, `window.location` in `Templates/*.html` and `static/**/*.js` finds zero URLs that 404 against the running WebService. Smoke script partitions URLs into: in-scope (must resolve at new root) and deferred (must resolve at `/api/...` until follow-up). Both partitions must return HTTP < 400.

6. **New rule file `no-api-prefix.md` exists** under `.claude/rules/` describing the invariant ("Flask blueprints register at the root; `/api/` prefix is forbidden") and is loaded by `CLAUDE.md` (auto-loaded). The rule includes Why, How to apply, and the canonical pattern (`url_prefix='/<Feature>'`).

7. **New R-rule (R17) gates re-introduction mechanically.** `.claude/standards/index.md` lists R17: "Edit/Write that introduces `url_prefix=['\"]/api` or string literal `/api/` in production paths is refused. Override with `# allow: <reason>`." The hook function `Test-R17-NoApiPrefix` is added to `.claude/hooks/pre-edit-standards.ps1` and a trivial Edit attempting to add `url_prefix='/api/Foo'` is refused (verified by an override test or a `pwsh -c` invocation of the hook).

8. **Documentation reflects the new shape.** `CLAUDE.md` "Key patterns" / API response section and the relevant `*.feature.md` / `*.flow.md` files no longer mention `/api/`. The new rule is cross-referenced from `CLAUDE.md`'s "Where everything lives" section.

## Out of Scope

- Renaming any HTML page route (e.g. `/Stats` stays `/Stats`).
- Changing JSON response shape, status codes, or method verbs of any endpoint.
- Reorganizing blueprint code structure beyond the `url_prefix` change.
- Moving the two HTML-page-under-`/api` routes (`FileScanning /Scanning`, `QualityTesting render_template`) -- they get their `url_prefix` updated like any other; the cleanup of "HTML pages serving from feature blueprints" is a separate concern.
- Migrating to HTMX, SPA, or any other request shape.
- Removing JSON endpoints or merging blueprints.

## Constraints

- Blueprint name (Flask's `Blueprint('<name>', ...)` first arg) MUST NOT change -- `url_for('Activity.GetCurrentJobs')` and similar internal references depend on the name.
- For each blueprint currently at `/api/<Feature>`, the new prefix is `/<Feature>` (preserve the path segment under the new root). For the two blueprints currently at bare `/api` (`FileScanning`, `profiles`), the new prefix is `/FileScanning` and `/Profiles` respectively -- this lifts them out of the junk-drawer and matches the per-feature convention.
- WebService must restart cleanly between phases. I (the user, on I9) own service start/stop -- but the directive's implementer can request restarts inline; do not punt restarts as operator action items.
- No new `*.feature.md` / `*.flow.md` files outside DELIVERING (R13). Edits to existing feature docs are fine to update `/api/...` references.

## Escalation Defaults

- Tradeoff between minimal-diff and idiomatic-Flask shape -> idiomatic (per-feature `url_prefix='/<Feature>'`, no bare-root blueprints).
- Risk tolerance: medium. Surface is large (every page) but per-change reversibility is high.
- If a blueprint move surfaces a hidden caller (e.g. an external script that hits `/api/...`), file and escalate -- do not silently break it.

## Engineering Calls Already Made

- Bare-`/api` blueprints (`FileScanning`, `profiles`) get per-feature prefixes (`/FileScanning`, `/Profiles`) rather than bare-root mounts. Bare-root would re-create the namespace collision the directive exists to clean up.
- Rule lives in `.claude/rules/no-api-prefix.md` (auto-loaded), not `.claude/rules-details/`. The invariant is short, project-wide, and needs to surface during planning -- per `doc-layering.md` cache discipline, that justifies always-loaded placement.
- Mechanical enforcement (R17) is added alongside the human-readable rule. The hook is the first line of defense; the rule explains why.

## Status

Active 2026-06-01 -- phase: VERIFYING -- SESSION-OUT-OF-CONTEXT handoff.

### Session 1 outcome (2026-06-01)

- Standards review complete (all 12 `.claude/rules/*.md` + `.claude/standards/index.md` Read).
- Criteria approved by operator.
- NEEDS_DOC_PREREAD complete: every colocated `*.feature.md` / `*.flow.md` for the directive's ## Files list was Read (~50 docs, ~150k tokens — full reads when partial reads would have satisfied R1; this is the post-mortem finding driving the planned `flow-docs-as-hub` follow-up directive).
- Implementation NOT executed. Reason: R15 (directive anchor above every def/class in any file in ## Files) combined with R12 (no preexisting docstring tolerance) creates per-file anchor/override overhead that does not fit the remaining context budget after the full doc preread.

### Implementation handoff for session 2

A fresh session can resume from this point. The work is mechanical:

1. **Main.py mount-time prefixes** (3 changes at `_register_blueprints`):
   - `SQLQueriesBlueprint, url_prefix='/api/SQLQueries'` -> `url_prefix='/SQLQueries'`
   - `ServiceStatusBlueprint, url_prefix='/api'` -> `url_prefix='/ServiceStatus'`
   - `FailureTrackingBlueprint, url_prefix='/api/FailureTracking'` -> `url_prefix='/FailureTracking'`

2. **Main.py error handlers** (~3 sites): replace `request.path.startswith('/api/')` with an Accept-header / endpoint-based JSON detection (suggested: `request.endpoint and '.' in request.endpoint` -> JSON, else fall through to HTML error page).

3. **Controllers with own url_prefix** (16 files): change `url_prefix='/api/<X>'` to `url_prefix='/<X>'`. Bare `/api` prefixes become `/FileScanning` (FileScanningController) and `/Profiles` (ProfileController).

4. **QualityTestController.py** has hardcoded `/api/QualityTest/...` in route decorators (no Blueprint url_prefix). Each route literal needs the `/api` prefix dropped.

5. **Templates** (`Templates/*.html`): bulk replace `'/api/<X>/...'` -> `'/<X>/...'`. Same for `static/**/*.js` and `Scripts/run_e2e_test.py` / `Scripts/SmokeTestScan.py` / `Tests/Contract/Test*.py`.

6. **New rule + R17 hook + standards index**: `.claude/rules/no-api-prefix.md`, R17 row in `.claude/standards/index.md`, `Test-R17-NoApiPrefix` in `.claude/hooks/pre-edit-standards.ps1`.

7. **CLAUDE.md** cross-reference to new rule.

8. **Feature/flow doc `/api/` text references** — grep + replace.

9. **`Scripts/SmokeUrls.py`** new smoke script per criterion 5.

### Recommended pre-session adjustment for session 2

Before session 2 resumes, recommend:

- **Narrow the ## Files list** to only the bare `/api` files (FileScanningController + ProfileController) plus Main.py + Templates + the rule/hook/index/CLAUDE.md set. The other 14 controllers are mechanical one-line edits; consider taking them through a follow-up sweep with smaller Files lists per session, OR loosen R15 enforcement for purely-mechanical one-line changes (separate directive).

- **Pre-stage allowed-override notes** at the top of Main.py for R12/R15 if going whole-hog.

- Alternatively: pivot scope to first land the `flow-docs-as-hub` directive (the post-mortem fix), which will make the R1/R15 friction structurally smaller for THIS directive when it resumes.

The planning, criteria, Files list, and engineering calls in this directive doc are the durable artifacts of session 1 and remain valid for the resumed work.

### Files (carved 2026-06-01, session 2 -- SQL-containing controllers DEFERRED)

**Scope carve rationale:** R12 was updated 2026-06-01 to refuse triple-quoted SQL and mandate Repository placement for business-logic SQL. Several controllers in the original Files list embed inline triple-quoted SQL (Activity, AudioFixPriorityHints, ClipBuilder, MediaProbe, TeamStatus). Pulling those through this directive would entangle a mechanical URL refactor with an architecture extraction that needs `.claude/rules/sql-architecture.md` written first. Those controllers are DEFERRED to a separate directive (proposed slug: `sql-to-repository`) that owns the architecture pass.

**In scope (mechanical url_prefix-only edits):**

```
WebService/Main.py                                              -- EDIT: mount-time prefixes for SQLQueries / ServiceStatus / FailureTracking blueprints; error-handler /api/ checks
Features/AudioCompletion/AudioCompletionController.py           -- EDIT: url_prefix '/api/AudioCompletion' -> '/AudioCompletion'
Features/FileReplacement/FileReplacementController.py           -- EDIT: url_prefix '/api/FileReplacement' -> '/FileReplacement'
Features/FileScanning/FileScanningController.py                 -- EDIT: url_prefix '/api' -> '/FileScanning'
Features/Optimization/OptimizationController.py                 -- EDIT: url_prefix '/api/Optimization' -> '/Optimization'
Features/Profiles/ProfileController.py                          -- EDIT: url_prefix '/api' -> '/Profiles'
Features/QualityTesting/QualityTestController.py                -- EDIT: hardcoded /api/QualityTest/ in route decorators
Features/ServiceControl/ServiceControlController.py             -- EDIT: url_prefix '/api/ServiceControl' -> '/ServiceControl'
Features/ShowSettings/ShowSettingsController.py                 -- EDIT: url_prefix '/api/ShowSettings' -> '/ShowSettings'
Features/SystemSettings/SystemSettingsController.py             -- EDIT: url_prefix '/api/SystemSettings' -> '/SystemSettings'
Features/TranscodeJob/TranscodeJobController.py                 -- EDIT: url_prefix '/api/Transcode' -> '/Transcode'
Features/TranscodeQueue/TranscodeQueueController.py             -- EDIT: url_prefix '/api/TranscodeQueue' -> '/TranscodeQueue'
Features/TranscodeQueue/QueueResetController.py                 -- EDIT: url_prefix '/api/QueueReset' -> '/QueueReset'
Templates/Base.html                                             -- EDIT: nav + fetch URLs
Templates/Stats.html                                            -- EDIT: every /api/ string; Manage button -> /FileScanning/Scanning
Templates/Activity.html                                         -- EDIT: /api/Activity/* -> /Activity/* (consumer of deferred controller; URL update only)
Templates/TranscodeQueue.html                                   -- EDIT: /api/TranscodeQueue/* and /api/QueueReset/* -> root
Templates/Queue.html                                            -- EDIT: queue page fetch URLs
Templates/Home.html                                             -- EDIT: any /api/ references
Templates/Settings.html                                         -- EDIT: /api/SystemSettings/*, /api/Profiles/*, /api/FileScanning/*, /api/TeamStatus/* -> root
Templates/ShowSettings.html                                     -- EDIT: /api/ShowSettings/* + /api/AudioFixPriorityHints/* -> root
Templates/FileScanning.html                                     -- EDIT: /api/FileScanning/* + /api/Scan/* -> root
Templates/ClipBuilder.html                                      -- EDIT: /api/ClipBuilder/* -> /ClipBuilder/*
Templates/Operations.html                                       -- EDIT: any /api/ references
Templates/SQLQueries.html                                       -- EDIT: any /api/ references
Templates/Optimization.html                                     -- EDIT: any /api/ references
Templates/Status.html                                           -- EDIT: any /api/ references
Templates/VmafCompare.html                                      -- EDIT: any /api/ references
Static/js/DeleteViewModel.js                                    -- EDIT: any /api/ references
Scripts/run_e2e_test.py                                         -- EDIT: any /api/ references
Scripts/SmokeTestScan.py                                        -- EDIT: any /api/ references
Tests/Contract/TestTranscodeStart.py                            -- EDIT: any /api/ references
Tests/Contract/TestTranscodeStatus.py                           -- EDIT: any /api/ references
Tests/Contract/TestQueueGet.py                                  -- EDIT: any /api/ references
.claude/rules/no-api-prefix.md                                  -- CREATE: new invariant rule (auto-loaded)
.claude/standards/index.md                                      -- EDIT: add R17 row
.claude/hooks/pre-edit-standards.ps1                            -- EDIT: add Test-R17-NoApiPrefix
CLAUDE.md                                                       -- EDIT: cross-reference new rule; verify no /api in patterns
Features/*/[*.feature.md, *.flow.md]                            -- EDIT: any /api/ references in doc bodies (text-only; the deferred controllers' docs get URL updates but no code change)
Scripts/SmokeUrls.py                                            -- CREATE: smoke script for criterion 5
```

**DEFERRED (handled by `sql-to-repository` follow-up directive):**

```
Features/Activity/ActivityController.py                              -- DEFER: inline triple-quoted SQL; needs Repository extraction
Features/TranscodeQueue/AudioFixPriorityHintsController.py           -- DEFER: inline ExecuteQuery; needs Repository extraction
Features/ClipBuilder/ClipBuilderController.py                        -- DEFER: _EnsureTables CREATE TABLE inline; needs Repository extraction
Features/MediaProbe/MediaProbeController.py                          -- DEFER: _BuildReprobeWhere assembles WHERE inline; needs Repository extraction
Features/TeamStatus/TeamStatusController.py                          -- DEFER: inline SELECT / GROUP BY; needs Repository extraction
```

The URL prefix change for the deferred controllers will be applied as a one-line edit at the SAME time their SQL is extracted in the follow-up directive. Until then, those endpoints continue to serve at `/api/...` -- they'll be the last `/api/` references in the codebase, and the smoke check (criterion 5) accounts for that by partitioning known-deferred URLs separately.

### Promotions

Populated at DELIVERING. Anticipated:

| Source artifact | Target file | Commit |
|---|---|---|
| New `no-api-prefix.md` rule | `.claude/rules/no-api-prefix.md` (new file -- R13 relaxes at DELIVERING) | TBD |
| R17 row + hook function | `.claude/standards/index.md` + `.claude/hooks/pre-edit-standards.ps1` | TBD |
| CLAUDE.md cross-reference to new rule | `CLAUDE.md` "Where everything lives" | TBD |
| Smoke script for URL coverage | `Scripts/SmokeUrls.py` (new -- treated as operator tooling, not a feature/flow doc; not gated by R13) | TBD |

### Verification

Populated at VERIFYING. One entry per criterion, with command output / SQL result / smoke-script output as evidence.

### Decisions Made

Populated during IMPLEMENTING as engineering calls under ambiguity arise.
