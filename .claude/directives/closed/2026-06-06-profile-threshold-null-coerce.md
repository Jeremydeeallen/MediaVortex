# Current Directive

**Set:** 2026-06-06
**Status:** Active -- phase: DELIVERING
**Slug:** profile-threshold-null-coerce

## Outcome

The cogs-modal Save (`PATCH /api/profiles/<id>/knobs`) tolerates a blank text field on the same-resolution source threshold row (e.g. the 480p row of a `>480p` profile leaves `TranscodeDownTo` empty) without violating the `text NOT NULL DEFAULT ''` constraint. Today, the controller writes a literal `null` and PostgreSQL refuses the UPDATE. The fix is one bug at the controller boundary; the existing `SaveThreshold` path already coerces correctly.

## Acceptance Criteria

C1. `PATCH /api/profiles/<id>/knobs` coerces `null` to the column default for the two `text NOT NULL` columns in the `THRESHOLD_COLS` whitelist (`TranscodeDownTo` -> `''`, `ContainerType` -> `'mp4'`). Verifiable: POST with `{"Thresholds":[{"Id":231,"TranscodeDownTo":null}]}` no longer raises; the row's `transcodedownto` ends up at `''` (empty string). Profile 53's 480p row saves cleanly via the UI.

## Status

Active 2026-06-06 -- phase: NEEDS_PLAN. One-line controller fix.

### Files

| # | File | Action | Anchor |
|---|---|---|---|
| 1 | `Features/Profiles/ProfileController.py` | EDIT `patch_profile_knobs` -- add a coercion pass before the UPDATE | `# directive: profile-threshold-null-coerce \| # see profile-threshold-null-coerce.C1` (anchored at the inner closure `def patch_profile_knobs(profile_id):` line) |

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| `TEXT_NOT_NULL_DEFAULTS` coercion in patch_profile_knobs | `Features/Profiles/ProfileController.py` (controller boundary) | this directive's commit |

No durable doc updates required -- the fix preserves existing API contract; no new column, no new endpoint, no seam change. Profiles.feature.md is unaffected.

### Verification

| Criterion | Evidence | Status |
|---|---|---|
| C1 | Live PATCH `{"Thresholds":[{"Id":231,"TranscodeDownTo":null}]}` to `/api/profiles/53/knobs` returned `success=true, threshold_updates=1` (was 500 before fix). Post-PATCH DB state: row 231 has `transcodedownto=''` (empty), `containertype='mp4'` -- both coerced from `null` to their column defaults. Operator can now save the SVT-AV1 P6 FG8 CRF36 >480 profile's 480p row from the cogs modal. | PASS |
