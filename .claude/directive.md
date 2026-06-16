# Current Directive

**Set:** 2026-06-07
**Status:** Active -- phase: NEEDS_PLAN
**Slug:** quality-floor-lift

## Outcome

Treat VMAF as a feedback signal rather than a one-shot gate. When a transcode lands below the data-driven gate (`PostTranscodeGateConfig.VmafAutoReplaceMinThreshold`, currently 88), compute the *minimum* knob adjustment to close the gap based on the prior attempt, re-queue with that one adjustment, and bound the retry chain by `PostTranscodeGateConfig.MaxRequeueAttempts` (default 3). After exhaustion, flag the MediaFile into `ProblemFiles` with `ErrorType='QualityFloorFailed'`; surface it on a new `/Activity` Quality Review card; do not auto re-queue further. Generalize today's SVT-AV1-only CRF-down adjustment to also handle NVENC VBR (bitrate-up), with the regime selected from the prior attempt's `Profiles.RateControlMode`. The default re-queue encoder for the floor-lift policy is NVENC VBR (operator-configurable via `PostTranscodeGateConfig.DefaultRequeueProfileName`).

## Concern

Three structural gaps motivate this:

1. **The VMAF<80 cutoff is hardcoded** in `Features/TranscodeJob/AdaptiveQualityService.CalculateAdjustedCRF` lines 81-87. The cluster gate moved to 88 in `PostTranscodeGateConfig`. Attempts landing at VMAF 82-87 are "failed" by the disposition gate but "skip retranscode" by the adjustment helper -- so they either re-queue at the same CRF (no progress) or sit non-compliant.
2. **No NVENC adjustment path.** `AdaptiveQualityService` only does CRF-down. NVENC profiles are rate-anchored (`-rc vbr -b:v X -maxrate:v Y -bufsize:v Z`). A failed NVENC attempt has no defined "next attempt with bigger budget."
3. **Unbounded re-queue.** Today's `Requeue` disposition has no attempt-count discipline. A file that can't reach VMAF 88 at any knob setting (already-compressed source, codec mismatch, content libvmaf scores poorly per BUG-0026) re-queues indefinitely; operator never sees the "give up and review" signal.

Combined with the floor-lift policy (NVENC as the default encoder for the bulk of the library, 720p floor for big-screen-destined content), the system needs a coherent VMAF-driven adjustment loop with a bounded retry budget and a review handoff.

## Acceptance Criteria

### A. Gate threshold is data-driven (no hardcoded 80 / 88)

C1. `AdaptiveQualityService.CalculateAdjustedCRF` reads the gate threshold from `PostTranscodeGateConfig.VmafAutoReplaceMinThreshold` per call (db-is-authority -- no Python cache). When VMAF >= gate, returns the previous CRF unchanged + logs at info. Verifiable: change the threshold from 88 to 90 via SQL; the next re-queue decision honors 90 within one disposition cycle.

C2. The hardcoded `VMAFScore < 80` ceiling in `CalculateAdjustedCRF` is removed. Adjustment table is anchored relative to the configured gate, not the literal 80. Verifiable: with gate=88, an attempt at VMAF 82 produces an adjustment (not "should not retranscode") with proportionally smaller step than VMAF 60.

### B. NVENC VBR adjustment path

C3. New `AdaptiveQualityService.CalculateAdjustedNvencBudget(PreviousBitrateKbps, PreviousMaxrateKbps, VMAFScore, GateThreshold, SourceBitrateKbps) -> (NewBitrateKbps, NewMaxrateKbps)`. Adjustment is proportional to the VMAF gap: bitrate bump ~= 10% per VMAF point under the gate, clamped to `min(SourceBitrateKbps, ProfileThresholds.MaxBitrateKbps)`. Maxrate scales with bitrate at the same ratio the prior attempt used. Verifiable: VMAF=80, gate=88, source=4000 kbps, previous=600/1200 -> new ~960/1920 (60% bump); VMAF=86, gate=88 -> ~720/1440 (20% bump); VMAF=87, gate=88 -> ~660/1320 (10% bump).

C4. The dispatch between CRF-down (CPU/SVT-AV1) and bitrate-up (NVENC VBR) is driven by the prior attempt's `Profiles.RateControlMode`, not by codec string or profile name. New top-level `ComputeNextAttemptKnobs(MediaFileId)` reads the prior attempt + profile, dispatches to the right adjustment helper. Verifiable: a Profile with `RateControlMode='cq'` invokes `CalculateAdjustedCRF`; `RateControlMode='vbr'` invokes `CalculateAdjustedNvencBudget`.

### C. Attempt chain is the source of truth; one knob per re-queue

C5. Re-queue admission writes the adjusted knobs onto the new `TranscodeQueue` row as overrides: new nullable columns `OverrideCRF INTEGER NULL`, `OverrideBitrateKbps INTEGER NULL`, `OverrideMaxrateKbps INTEGER NULL`. `CommandBuilder` honors these overrides when present; otherwise falls back to `ProfileThresholds` (today's behavior). Verifiable: queue a row with `OverrideCRF=24` for a CRF36 profile; the resulting ffmpeg command emits `-crf 24`, not 36.

C6. **Adjust ONE knob per re-queue.** The next attempt differs from the previous attempt in exactly the dimension the adjustment is computed for -- CRF, or bitrate budget -- nothing else (no resolution, codec, or audio change). Verifiable: byte-compare the `FfpmpegCommand` strings of two consecutive attempts on the same MediaFile; the diff is bounded to the adjustment knob's value (and `.inprogress` filename suffix).

### D. Retry budget + review handoff

C7. New `PostTranscodeGateConfig.MaxRequeueAttempts INTEGER NOT NULL DEFAULT 3` column added via idempotent migration. Verifiable: `\d PostTranscodeGateConfig` shows the column; running the migration twice is a no-op.

C8. `PostTranscodeDispositionService` counts prior failed attempts on the same MediaFile (from `TranscodeAttempts.Success=TRUE AND VMAF < Gate`). When count >= `MaxRequeueAttempts`, disposition returns `Discard` with reason `QualityFloorExhausted` instead of `Requeue`. The MediaFile is inserted into `ProblemFiles` with `ErrorType='QualityFloorFailed'`, `ErrorMessage` recording the final VMAF + the knob chain (e.g. `"VMAF 82.1 after 3 attempts: CRF 36/32/28; gate=88"`). Verifiable: a synthetic MediaFile that fails three times produces exactly one `ProblemFiles` row, no fourth queue row, and the operator sees it on the new `/Activity` Quality Review card.

C9. **Flagged files do NOT auto re-queue.** Once a MediaFile has a `ProblemFiles ErrorType='QualityFloorFailed'` row, `QueueManagementBusinessService` queue-admission paths refuse to add it to `TranscodeQueue` until the operator clears the flag. Verifiable: insert a synthetic flag row; trigger PopulateQueue; the file is excluded. Clear the row; the file is admitted on the next PopulateQueue.

### E. Operator review surface

C10. `/Activity` page renders a "Quality Review" card listing `ProblemFiles ErrorType='QualityFloorFailed'` rows. Each row shows: file path, attempt count, last VMAF score, last profile name, last regime (`CRF=N` or `VBR=Xk/Yk`). Three operator actions per row: **Accept** (clear ProblemFiles + mark MediaFile compliant-by-operator-override), **Re-queue manually** (clear ProblemFiles + admit to queue with operator-supplied profile), **Drop** (clear ProblemFiles + revert MediaFile to pre-attempt state via MediaFilesArchive when present). Verifiable: each button triggers the expected DB state transition.

C11. Backed by three endpoints: `POST /api/Activity/QualityReview/<mediaFileId>/Accept`, `.../Requeue` (JSON body `{"ProfileName": "..."}`), `.../Drop`. Standard `{Success/Message/Data}` envelope. Verifiable: curl each endpoint with synthetic data; observe expected DB state.

### F. NVENC escalation when CRF floors out

C12. New `PostTranscodeGateConfig.DefaultRequeueProfileName TEXT NULL` column. When the prior attempt was CRF (SVT-AV1) and `PreviousCRF` has hit `MinCRF=15` floor without crossing the gate, the next attempt re-queues under `DefaultRequeueProfileName` (if set) -- typically a NVENC VBR profile with a higher bitrate ceiling. Verifiable: configure `DefaultRequeueProfileName='NVENC AV1 P7 CANARY VBR -720p'`; a synthetic CRF=15 / VMAF=82 attempt re-queues under the NVENC profile, not the original.

C13. Default `DefaultRequeueProfileName` is left NULL by the migration -- operator opts in. The criterion only requires the mechanism exists; the operator's library calibration decides whether to set it. Verifiable: post-migration `SELECT DefaultRequeueProfileName FROM PostTranscodeGateConfig` returns NULL; setting it via UPDATE persists and the next decision honors it.

### G. Observability

C14. Per-disposition log entry (`Logs.FunctionName='DecidePostTranscodeDisposition'`) includes: `MediaFileId`, `AttemptCount`, `VMAF`, `Gate`, `Disposition`, `Reason`, `NextRegime` (`cq`/`vbr`/`review`/`discard`), `NextKnob` (`CRF=24` / `bitrate=960k` / `N/A`). One row per decision. Verifiable: query `Logs` for the latest disposition on a known MediaFile; all eight fields appear.

C15. `/SQLQueries` saved card: "Files in Quality Review (top 50 by last VMAF gap)" -- joins `ProblemFiles ErrorType='QualityFloorFailed'` to the latest `TranscodeAttempts` row to show the worst offenders by `(gate - last_vmaf)`. Verifiable: card renders without error against a populated test set.

## Out of Scope

- Jellyfin playback telemetry integration (separate directive `/n jellyfin-playback-telemetry` -- composes well but is independent of the floor lift mechanics).
- Source-quality classification (master/healthy/compressed) at admission. Adjacent and complementary; the floor lift works without it.
- Per-content-class VMAF gate (animation 78, drama 82, sports 86). The gate stays cluster-wide here; per-class is a follow-up once `SourceQualityClass` exists.
- Ladder-rung outputs (per-item 720p + 480p companion encodes). Separate design; the floor lift produces a single output per source.
- Replacing AdaptiveQualityService -- the file stays, gets extended; not a rewrite.
- BUG-0026 (VMAF bimodal on held-frame animation). Cross-linked as a known reason a MediaFile might land in QualityReview; the fix is its own work.
- 480p-output cleanup for the existing library. Separate operator-driven re-queue using the new mechanism; the directive ships the mechanism, not the cleanup batch.

## Constraints

- **db-is-authority** (`.claude/rules/db-is-authority.md`): every read of `VmafAutoReplaceMinThreshold` / `MaxRequeueAttempts` / `DefaultRequeueProfileName` is fresh per call. No `self._cached_*` in `AdaptiveQualityService` or `PostTranscodeDispositionService`.
- **R10**: any new `Claim*` function continues to call `BuildClaimPredicate` + `BuildAllowedProfilesPredicate` (no new claim paths planned, but if one is added, it routes through the helpers).
- **R11**: migration uses `ADD COLUMN IF NOT EXISTS`. Re-runnable.
- **R12 edit-region trap**: `AdaptiveQualityService` has preexisting multi-line docstrings; my edits stay outside those regions or stay one-liner. New functions get one-line docstrings max.
- **R15**: every edited def/class in `### Files` gets `# directive: quality-floor-lift | # see quality-floor-lift.C<N>` directly above. Note: `# see` target points at this directive's criterion ID until DELIVERING, then re-anchors to the promoted feature doc's identical IDs.
- **R19**: any `Claim*` edit lands in `Features/TranscodeQueue/TranscodeQueueRepository.py` (already true).
- **One-knob-per-requeue invariant (C6)** is the load-bearing design property. Asserted in `CommandBuilder` + verified by contract test.

## Escalation Defaults

- **Schema column additions** -> Claude executes (`ADD COLUMN IF NOT EXISTS` is reversible).
- **Live WebService restart** -> Claude owns on I9 dev workstation per memory.
- **Risk tolerance**: low on the retry-budget logic (governs whether files get touched at all); medium on the NVENC adjustment formula (gets refined as observation data accrues).

## Engineering Calls Already Made

- **NVENC VBR is the default re-queue regime** when escalation is needed (after CRF floor) and as the default for fresh re-queues when `DefaultRequeueProfileName` is set. Rationale (from prior session conversation): NVENC speed + maxrate-cap is the right tool for the bulk of the library; SVT-AV1 reserved for grain-heavy masters. Operator opts in by setting the column.
- **Override columns on TranscodeQueue, not a separate AttemptPlan table.** Smaller blast radius -- one nullable column triplet, CommandBuilder branches on presence. Refactor to a richer plan model is YAGNI until the override set grows past 3-4 knobs.
- **Bound retry by *attempts*, not by *time* or *quality delta*.** Simpler operator mental model. A file that has tried 3 times and still misses by 0.5 VMAF is a review case the same as one that misses by 10 -- both need a human call.
- **ProblemFiles is the review queue.** Existing table, existing infrastructure. New `ErrorType='QualityFloorFailed'` distinguishes from disk-orphan / silent-audio rows. Cleared by operator action; no auto-clear.
- **Cluster-wide gate stays cluster-wide.** Per-content-class gates are correct but premature -- requires source classification, which is a separate directive. The data-driven gate column makes the per-class extension a column-shape change later, not a code change.
- **Adjustment math is `+10% bitrate per VMAF point under gate, clamp to source`.** The math is a design call exposed in C3. Subject to refinement based on observed outcomes; the *shape* (proportional to gap, clamped to source ceiling) is the load-bearing piece.
- **No worktree.** Land on `main` directly per session preference; six-ish commits split by criterion group.

## Status

Active 2026-06-07 -- phase: NEEDS_PLAN. Directive doc just opened; criteria + Files list written. Awaiting operator approval before phase advance to NEEDS_DOC_PREREAD.

### Files

| # | File | Action | Anchor (`# directive: quality-floor-lift \| # see quality-floor-lift.<ID>`) | R-rule notes |
|---|---|---|---|---|
| 1 | `Scripts/SQLScripts/AddQualityFloorLiftColumns.py` | NEW | `C1` on `Run()` | R11: idempotent `ADD COLUMN IF NOT EXISTS` for 5 columns (3 on TranscodeQueue, 2 on PostTranscodeGateConfig). R12: single-line ALTER strings, no module docstring. |
| 2 | `Features/TranscodeJob/AdaptiveQualityService.py` | EDIT (data-driven gate, remove cutoff) + ADD `CalculateAdjustedNvencBudget`, `ComputeNextAttemptKnobs` | `C1`/`C2` on `CalculateAdjustedCRF`; `C3` on `CalculateAdjustedNvencBudget`; `C4` on `ComputeNextAttemptKnobs` | R3: no `self._cached_gate_threshold`; reads `PostTranscodeGateConfig` per call. R12: existing multi-line docstrings preexisting (edit-region scoped). |
| 3 | `Features/QualityTesting/PostTranscodeDispositionService.py` | EDIT | `C8` on the disposition decision function (likely `DecidePostTranscodeDisposition` or sibling) | R12: edit-region; new branch single-line conditional. |
| 4 | `Features/TranscodeQueue/QueueManagementBusinessService.py` | EDIT (admission exclusion) | `C9` on the populate-queue helper | R9: any new LIKE uses EscapeLikePattern. R12: edit-region. |
| 5 | `Features/TranscodeQueue/TranscodeQueueRepository.py` | EDIT (persist + read overrides) | `C5` on `SaveTranscodeQueueItem` / `ClaimNextPendingTranscodeJob` returning the override columns | R10: claim still calls `BuildClaimPredicate` + `BuildAllowedProfilesPredicate`. R19: stays in TranscodeQueueRepository. |
| 6 | `Models/CommandBuilder.py` | EDIT (honor overrides, assert one-knob) | `C5`/`C6` on the function that emits `-crf` / `-b:v` / `-maxrate:v` | R12: existing structure preexisting; new branch is single-line conditionals. |
| 7 | `Features/Activity/ActivityController.py` | EDIT (Quality Review GET) + ADD three POST endpoints | `C10` on the GET handler; `C11` on each POST handler | R12: one-line docstrings. R9 for any LIKE. |
| 8 | `Templates/Activity.html` | EDIT (Quality Review card + Re-queue modal) | N/A (HTML; R15 does not apply) | R1: colocated `*.feature.md` preread satisfied via `Features/Activity/` ancestors (already read this session). |
| 9 | `Features/ProblemFiles/ProblemFilesRepository.py` | EDIT (read/write `ErrorType='QualityFloorFailed'`) | `C8` / `C9` on the relevant methods | R12: edit-region. |
| 10 | `transcode.flow.md` | EDIT (S3/S4 seam rows + retry-budget prose) | N/A (flow doc; R15 does not apply) | R14: no annotation lines -- replace S3/S4 content in place. |
| 11 | `Tests/Contract/TestQualityFloorLift.py` | NEW | `C1`-`C13` distributed across `test_*` functions | R8: under `Tests/Contract/`. R12: one-line docstrings on each test. |
| 12 | `memory/KNOWN-ISSUES.md` | EDIT (cross-link BUG-0026 to QualityFloorFailed) | N/A (memory) | Tiny edit -- one-line note under BUG-0026 mentioning the new ErrorType. |

### Promotions

(Populated at DELIVERING. The criteria block above promotes to a new `Features/QualityTesting/quality-floor-lift.feature.md` per R13.)

| Source artifact | Target file | Commit |
|---|---|---|
| `## Acceptance Criteria` C1-C15 | `Features/QualityTesting/quality-floor-lift.feature.md` Success Criteria | TBD |
| S3/S4 seam updates + retry-budget prose | `transcode.flow.md` | TBD |
| BUG-0026 cross-link | `memory/KNOWN-ISSUES.md` | TBD |

### Verification

(Populated at VERIFYING; one entry per acceptance criterion.)

### Decisions Made

(Populated during execution as ambiguities surface. Pre-populated decisions live in `## Engineering Calls Already Made` above.)
