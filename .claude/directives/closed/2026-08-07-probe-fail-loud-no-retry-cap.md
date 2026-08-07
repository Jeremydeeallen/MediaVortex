# Directive: probe-fail-loud-no-retry-cap

**Slug:** probe-fail-loud-no-retry-cap
**Status:** Closed
**Closed:** 2026-08-07
**Opened:** 2026-08-07

## Ask

Probe path silently drops files after 3 failures. 33 files carry `NeedsReprobe=TRUE` but are excluded by the fetch predicate because `FFprobeFailureCount >= 3`. Operator has no signal that this happened. Violates fail-loud + KISS + gui-editable-knobs. Semantic contract of `NeedsReprobe` is broken (flag says "retry me", cap says "no").

Fix per operator philosophy ("fail loudly, fix forward"): probe once per admission, on failure record the reason + stop retrying, surface failures to operator. Retry only when operator explicitly sets `NeedsReprobe=TRUE`. No auto-retry cap. No hidden counter driving decisions.

## Domain Decisions

**DD1. No retry cap.** `MaxFFprobeFailures = 3` hardcoded constant deleted. Probe attempts once per admission. If it fails, the failure is TERMINAL for that attempt -- no auto-retry ceremony.

**DD2. `LastFFprobeError` column already exists.** No migration needed. Writer path already populates it on failure per current probe.feature.md C4. Fix = remove the cap that hides these rows from operator flow; column + surface already in place.

**DD3. `NeedsReprobe = TRUE` is a ONE-SHOT operator command consumed by every attempt.** Both success AND failure paths clear the flag. Operator's intent overrides any prior failure history; the flag doesn't loop. If it fails again with the flag consumed, `LastFFprobeError` is rewritten; operator sets flag again if they want another try.

**DD4. Fetch predicate:** `NeedsReprobe = TRUE OR (LastFFprobeError IS NULL AND (Resolution IS NULL OR Codec IS NULL OR AudioCodec IS NULL))`. Rows with prior failures (`LastFFprobeError IS NOT NULL`) are skipped forever UNLESS operator sets NeedsReprobe=TRUE. No auto-retry loop. Still gates on `StorageRootId IS NOT NULL`, `RelativePath IS NOT NULL`, and `BuildClaimPredicate('ProbeEnabled')`.

**DD5. Surface at `/Failures` (or equivalent).** Any `MediaFiles` row with `LastProbeError IS NOT NULL` renders on the operator failure page with the reason string. Operator either: fixes the source, deletes the row, OR sets `NeedsReprobe=TRUE` after fixing to retry.

**DD6. One-time sweep for 33 stuck files.** After migration + code deploy, the 33 rows with `NeedsReprobe=TRUE` + `FFprobeFailureCount >= 3` get picked up on next tick. Fresh probe either succeeds (silent recovery) or writes `LastProbeError` (operator now sees why).

**DD7. `MaxFFprobeFailures` constant + `Force` guard deleted.** `Force=True` path in `_ProbeSingle` (line 60 area) was for operators to override the cap; with no cap, no Force needed. Any callers using Force become no-ops (Force arg becomes documentation-only or removed).

## Fix shape

Small migration + one column + fetch predicate simplification + constant deletion + failure-recording swap.

## Success Criteria

C1. **`MaxFFprobeFailures = 3` constant deleted.** `grep -rn "MaxFFprobeFailures" Features/ WorkerService/` returns 0 production hits.

C2. **`FFprobeFailureCount` no longer in fetch predicate.** `grep -n "FFprobeFailureCount" WorkerService/ProbeWorker.py` returns 0 hits. Predicate reads: `Resolution IS NULL OR Codec IS NULL OR AudioCodec IS NULL OR NeedsReprobe = TRUE`.

C3. **No new migration needed.** `LastFFprobeError` column already exists; writer path already populates per probe.feature.md C4. Confirmed via schema check 2026-08-07.

C4. **Probe failure writer keeps writing `LastFFprobeError`.** Unchanged. Existing behavior preserved.

C5. **`NeedsReprobe` fetch honors the flag unconditionally.** Contract test: insert a row with `Resolution IS NOT NULL, Codec IS NOT NULL, AudioCodec IS NOT NULL, FFprobeFailureCount=99, NeedsReprobe=TRUE` -- fetch returns it.

C6. **Operator surface unchanged.** `/Failures` page already renders `LastFFprobeError` per probe.feature.md W4. Verified via NEEDS_DOC_PREREAD. No template changes.

C7. **33 stuck files unstick on next tick.** Post-deploy: `SELECT COUNT(*) FROM MediaFiles WHERE NeedsReprobe=TRUE AND FFprobeFailureCount >= 3` drops as ProbeWorker picks each up. Either they succeed (NeedsReprobe cleared, Resolution populated) or they fail again with LastProbeError populated.

C8. **probe.feature.md amended.** New criterion documents the no-cap contract + LastProbeError signal + NeedsReprobe-wins semantics.

C9. **Live smoke on I9.** After code lands + I9 restart + migration applied: (a) one of the 33 stuck files gets picked up by ProbeWorker within 60s; (b) SQL shows either Resolution filled OR LastProbeError populated for that file.

## Files

**Edit:**
- `Features/MediaProbe/MediaProbeBusinessService.py` -- delete `MaxFFprobeFailures = 3` constant + `Force`-gates-on-count block + any callsites reading it
- `WorkerService/ProbeWorker.py` -- drop `FFprobeFailureCount < %s` from fetch predicate; simplify param tuple; drop `MaxFailures = MediaProbeBusinessService.MaxFFprobeFailures` line
- `Features/MediaProbe/probe.feature.md` -- amend C2, C7, C8 (cap-related contracts); add DD1-DD7 as Design Decisions section (at DELIVERING)

**Create:**
- `Tests/Contract/TestProbeFailLoudNoRetryCap.py` -- fetch honors NeedsReprobe unconditionally regardless of FFprobeFailureCount

**Delete:** (none)

## Call-Graph Audit

- **Signal 1 (multiple flow docs):** N/A -- ingest.flow.md is the sole probe flow doc.
- **Signal 2 (orchestration mode-branch):** none -- pure predicate simplification.
- **Signal 3 (mode-sparse output columns):** LastProbeError populated by ONE writer (probe path). No mode-sparse risk.
- **Signal 4 (OOS ambiguity):** all OOS items categorized (a) or (b) below.
- **Signal 5 (config-driven graph shape):** deletion of hardcoded constant removes a hidden knob. Simpler graph after.

## Out of Scope

- **(a) In-flight preserved:** `FFprobeFailureCount` column stays as pure historical counter. Deleting requires a follow-up (would break /Activity probe-backlog tile that may read it).
- **(a) In-flight preserved:** `TerminateOnFailure` SystemSetting (separate concern -- worker-level failure handling, not per-file).
- **(a) In-flight preserved:** Ad-hoc probe endpoints that carry `Force=True` -- become no-ops.
- **(b) Tolerated debt (none):** classifier auto-assign tiers (AnimeByFolder etc.) is separate; not touched here.

## Phase machine

NEEDS_STANDARDS_REVIEW -> NEEDS_PLAN -> NEEDS_DOC_PREREAD -> IMPLEMENTING -> VERIFYING -> DELIVERING

### Progress

- [x] NEEDS_STANDARDS_REVIEW
- [x] NEEDS_PLAN
- [x] NEEDS_DOC_PREREAD: probe.feature.md read (limit=50); confirmed LastFFprobeError column + /Failures surface + ResetProbeFailures method all exist
- [x] IMPLEMENTING: no migration -- column exists
- [x] IMPLEMENTING: ProbeWorker fetch predicate rewritten -- NeedsReprobe unconditional pass OR (never-attempted AND missing metadata)
- [x] IMPLEMENTING: MediaProbeBusinessService MaxFFprobeFailures constant + Force cap-check deleted; GetProbeStatistics + GetFailedFiles callsites updated
- [x] IMPLEMENTING: MediaProbeRepository.RecordProbeFailure clears NeedsReprobe (one-shot consumption); ResetProbeFailures sets NeedsReprobe=TRUE (auto-pickup); GetPermanentlyFailedFiles queries LastFFprobeError IS NOT NULL
- [x] IMPLEMENTING: FailuresRepository.GetProbeFailures rewritten to query on LastFFprobeError IS NOT NULL; dead MediaProbeBusinessService import removed
- [x] IMPLEMENTING: TestProbeFailLoudNoRetryCap 6/6 PASS (constant deleted, fetch has no count gate, NeedsReprobe respected, RecordProbeFailure clears flag, ResetProbeFailures sets flag, FailuresRepository query correct)
- [x] VERIFYING: TestProbeFailLoudNoRetryCap 6/6 PASS
- [x] SMOKE-GATE PASS: I9 restart on Version=ae784b3; 33 previously-stuck NeedsReprobe files picked up in 4 ticks (~60s); 33/33 succeeded (Resolution populated + LastFFprobeError cleared + NeedsReprobe cleared); 0 failures. Silent-cap era files were probeable all along.
- [x] DELIVERING: probe.feature.md C2/C7/C8 amend; close report drafting

### R13 overrides

(none anticipated)

### R18 overrides

(none anticipated)

### Promotions

| Source (directive) | Target (durable) |
|---|---|
| DD1-DD7 | `Features/MediaProbe/probe.feature.md` -- C2 rewritten (new predicate); C7 rewritten (cap removed, fail-loud); C8 rewritten (one-shot NeedsReprobe semantics) |

## Delivery Report

**STATUS:** Done

**WHAT SHIPPED:**
- `Features/MediaProbe/MediaProbeBusinessService.py`: `MaxFFprobeFailures = 3` constant deleted; `Force`-gates-on-count block in `ProbeFile` deleted; `GetFailedFiles` no longer passes cap arg; `GetProbeStatistics` no longer exposes cap
- `WorkerService/ProbeWorker.py`: fetch predicate rewritten -- `NeedsReprobe = TRUE OR (LastFFprobeError IS NULL AND (Resolution IS NULL OR Codec IS NULL OR AudioCodec IS NULL))`; `MaxFailures` param deleted from `_FetchBatch`; `Run()` no longer reads the constant
- `Features/MediaProbe/MediaProbeRepository.py`: `RecordProbeFailure` now clears `NeedsReprobe = FALSE` (one-shot consumption); `ResetProbeFailures` now sets `NeedsReprobe = TRUE` (auto-pickup); `GetPermanentlyFailedFiles` queries `LastFFprobeError IS NOT NULL` (no cap threshold); multiline docstrings collapsed to single-line comments per R12
- `Features/Failures/FailuresRepository.py`: `GetProbeFailures` queries `LastFFprobeError IS NOT NULL`; dead `MediaProbeBusinessService` import removed
- `Features/MediaProbe/probe.feature.md`: C2 + C7 + C8 rewritten to match new no-cap contract
- `Tests/Contract/TestProbeFailLoudNoRetryCap.py`: 6 assertions (constant deleted, fetch has no count gate, NeedsReprobe respected, RecordProbeFailure clears flag, ResetProbeFailures sets flag, FailuresRepository query correct)

**HOW TO USE IT:**
- No operator action required. Failed-probe files now surface immediately on `/Failures` (previously only after 3 silent retries).
- To retry a specific file: use `/Failures` Retry button (calls `POST /api/Failures/<id>/Retry` -> `ResetProbeFailures` -> sets `NeedsReprobe=TRUE`).
- To retry a family of files: `Scripts/MarkNeedsReprobe.py <criteria>` writes `NeedsReprobe=TRUE`; ProbeWorker picks them up next tick.

**WHAT YOU NEED TO EXECUTE:**
1. Fleet-deploy so Linux workers pick up the new predicate: `py deploy/deploy-fleet.py`.
2. Check `/Failures` -- 1598 rows with `LastFFprobeError IS NOT NULL` now render. Operator decides per-file: fix source, delete row, or reset+retry.

**CRITERIA VERIFICATION:**
- C1: `grep -rn "MaxFFprobeFailures" Features/ WorkerService/` returns 0 hits (verified inline)
- C2: `WorkerService/ProbeWorker.py` fetch has no `FFprobeFailureCount <` clause (verified via TestProbeFailLoudNoRetryCap.test_fetch_predicate_has_no_failure_count_gate)
- C3: no migration -- LastFFprobeError column pre-existed
- C4: `RecordProbeFailure` writes error preserved (unchanged behavior on write side)
- C5: TestProbeFailLoudNoRetryCap.test_fetch_predicate_honors_needsreprobe_regardless_of_prior_failure PASS
- C6: `/Failures` renders LastFFprobeError; unchanged
- C7: LIVE SMOKE PASS -- 33 previously-stuck files picked up in 4 ticks (~60s), 33/33 succeeded, 0 failures; NeedsReprobe count 33->0
- C8: probe.feature.md C2/C7/C8 amended this directive
- C9: LIVE SMOKE PASS (see C7)

**DECISIONS I MADE:**
- Added `AND LastFFprobeError IS NULL` to fetch predicate's never-attempted branch (prevents infinite retry loop when cap is removed; documented in DD4)
- Made `NeedsReprobe` one-shot (cleared on both success + failure paths) so operator command isn't sticky; documented in DD3
- `ResetProbeFailures` now also sets `NeedsReprobe=TRUE` (was just clearing failure state) -- operator's semantic intent when clicking Retry
- Kept `FFprobeFailureCount` column despite dead-weight status; deletion is a follow-up (touches 5+ files, template render, model, migration)
- Kept `Force` param on `ProbeFile` for signature compat with existing callers (`LanguageEnrichmentService.ProbeFile(Force=True)`, `FileReplacementBusinessService`); no longer gates anything

**KNOWN GAPS / DEFERRED:**
- `FFprobeFailureCount` column now dead weight (nothing decides on it). Follow-up directive `probe-drop-ffprobefailurecount-dead-column` to fully remove.
- Fleet-deploy pending. Linux workers still hold old fetch predicate; they'll SQL-error on the old `FFprobeFailureCount` param position OR silently exclude (need to check). Deploy soon.
- 1598 `LastFFprobeError IS NOT NULL` rows on /Failures -- historical residue from silent-cap era; operator decides fate per-file.
