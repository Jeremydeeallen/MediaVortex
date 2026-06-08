# Current Directive

**Set:** 2026-06-08
**Status:** Active -- phase: IMPLEMENTING
**Slug:** legacy-audio-damage-accounting
**Interrupts:** local-staging (paused at `.claude/directives/paused/2026-06-08-local-staging.md`; resume by un-pausing after this closes)

## Outcome

Honestly account for the audio damage inflicted on 8,249 library files by the legacy `acompressor + dynamic loudnorm` chain (active 2025-10-03 -> 2026-05-30). Produce an operator-actionable report flagging the **22 affected movies** for external re-acquisition. Accept the 8,227 TV episodes as historical loss (small per-file damage; gone-original; not worth bulk attention). Install a mechanical regression guard preventing any future re-emergence of dynamic-mode loudnorm.

No library re-encode. No audio re-pass on damaged files (per closed `audio-renorm-legacy` finding: a re-pass would normalize loudness of already-damaged audio without recovering dynamic range or peak fidelity).

## Concern

Three motivations:

1. **Inventory honesty.** 8,249 library files (16.7% of audio-bearing files) have permanently-degraded audio. The current `MediaFiles.AudioComplete=TRUE` flag treats them as compliant -- they stream-copy in every future encode -- but the underlying audio is missing dynamic range and limited peaks. Operator decisions (replay quality, re-acquisition priority, future quality benchmarks) need this fact written down where it can be referenced, not buried in commit history.

2. **The 22 movies are operator-actionable.** TV-series content typically ships with already-compressed source LRA (5-8 LU), so the LRA=7 forcing in the legacy chain added little additional damage -- accepting them as historical loss is the right call. Movies are the audibly-damaged subset (24 films + 70mm Blurays with native LRA 12-20+ LU got hit hard by `acompressor ratio=3` + LRA=7 forcing). 22 is a small enough batch that an operator can re-acquire externally (Sonarr/Radarr re-grab, manual rip, or accept-the-loss case by case).

3. **Linear-policy enforcement is the load-bearing forward guarantee.** `linear-loudnorm.feature.md` declares "Linear is the only mode. No single-pass dynamic fallback." That contract is currently asserted by code path inspection (no mechanical test). A regression that re-introduces dynamic-mode under any condition (a fallback branch, a config flag, a deprecated profile) would silently damage every new library addition the same way the legacy chain damaged these 8,249 files. The contract needs a contract test, not just a feature-doc paragraph.

## Acceptance Criteria

### A. Identification + operator-facing report

C1. `Scripts/IdentifyLegacyDamagedMovies.py` outputs `Reports/LegacyAudioDamagedMovies.csv` (new `Reports/` directory). One row per movie in the legacy set with columns: `MediaFileId`, `Filename`, `CanonicalPath`, `LegacyAttemptDate`, `LegacyProfile`, `SourceIntegratedLufs`, `AudioCodec`, `AudioBitrateKbps`, `AudioChannels`, `DurationMinutes`. Rows sorted by `AudioBitrateKbps DESC` (high-bitrate originals are higher-confidence damage candidates). Targeting logic: most-recent loudnorm-bearing attempt is dynamic-mode (no `linear=true`), no linear pass since, `mediafiles.filename !~ 'S[0-9]+E[0-9]+'` AND `mediafiles.seasonid IS NULL`. Counts 22 +/- 1 at directive open. Verifiable: run script, CSV row count matches, ten random rows pass manual inspection.

### B. KNOWN-ISSUES entry

C2. `memory/KNOWN-ISSUES.md` gains a new `BUG-NNNN` entry under `## Active` with five structured fields: `**What happened:**` (legacy chain shape verbatim + active window 2025-10-03 to 2026-05-30); `**Scope:**` (8,249 files; 22 movies + 8,227 TV; population closed at 2026-05-25 linear-mode transition); `**Damage profile:**` (acompressor reduced peaks above -15dB at 3:1 ratio with 3dB makeup; loudnorm LRA=7 forced 7-LU envelope; no mathematical inverse from the encoded output); `**Affected file list:**` (pointer to `Reports/LegacyAudioDamagedMovies.csv` for the 22 movies); `**Why not remediated:**` (zero KeepSource=TRUE; full re-transcode impossible without external re-acquisition; audio-only re-pass does not recover damage). Verifiable: entry exists with all five fields; BUG ID referenced from CSV header.

### C. Regression guard (mechanical)

C3. `Tests/Contract/TestLinearLoudnormEnforcement.py::test_no_dynamic_fallback` constructs a `MediaFile` mock with off-target loudness (`SourceIntegratedLufs=-20.0`), invokes `CommandBuilder.BuildAudioFilters`, and asserts the result satisfies (i) `loudnorm=` present, (ii) `linear=true` present in the same chain, OR the call raises a named deferral exception. Asserts the ABSENCE of `acompressor=` in any output. Verifiable: test passes against fixed code; reverting BuildAudioFilters to dynamic-fallback reproduces failure.

C4. `Tests/Contract/TestLinearLoudnormEnforcement.py::test_audit_loudnorm_emitters` walks the Python tree for every `loudnorm=` emitter (filename + line number) and asserts each emission either contains `linear=true` in the same string literal OR is in the explicit deferral-test whitelist. Verifiable: test passes against fixed code; adding any new dynamic-mode `loudnorm=` string fails the test.

### D. Production linear-or-refused contract (close the escape hatches)

C5. **`CommandBuilder.BuildAudioFilters` ungainable-peak branch refuses instead of falling back.** When `PredictedPeak > TargetTp`, the function raises `RuntimeError` with a message naming the MediaFileId, the source-LUFS, the predicted peak, and the deferral reason `ungainable_peak`. Removes the existing `f"{Common},alimiter=..."` dynamic-fallback emission entirely. Verifiable: `Tests/Contract/TestLinearLoudnormEnforcement.py::test_ungainable_peak_refuses` passes a mock with a known-clipping source (e.g. `SourceTruePeakDbtp=-3` + `SourceIntegratedLufs=-30` so gain pushes peak above -2 dBTP) and asserts the RuntimeError is raised; existing happy-path test (gainable peak) still passes.

C6. **`Features/QueueManagement/QueueManagementBusinessService.py` admission gate refuses ungainable-peak files upstream.** The same peak-math used by `BuildAudioFilters` runs at admission time; ungainable-peak files get `AdmissionDeferReason='ungainable_peak'` and never reach the encode queue. Verifiable: contract test queues a synthetic ungainable-peak MediaFile; admission returns the deferral; the file does not appear in the next `ClaimNextPendingTranscodeJob` result. Defense-in-depth: C5's RuntimeError exists for the case where this gate is bypassed.

### E. Eliminate hardcoded legacy chains in non-transcode emitters

C7. `Features/ClipBuilder/ClipBuilderBusinessService.py` line 54: hardcoded `-af loudnorm=I=-23:LRA=7:TP=-2` removed. Clips are transient test/preview artifacts -- loudness consistency is not load-bearing for VMAF (which measures video) or operator preview. Verifiable: `grep -n 'loudnorm' Features/ClipBuilder/` returns zero matches; ClipBuilder run smoke produces valid clips.

C8. Four smoke benchmarking scripts have hardcoded `loudnorm=I=-23:LRA=7:TP=-2` removed: `Scripts/Smoke/EncodeAndVmaf.py`, `Scripts/Smoke/FourKEncodingABC.py`, `Scripts/Smoke/NewGirlEncodingABC.py`, `Scripts/Smoke/NewGirlEncodingABC_VarianceBoost.py`. These are operator-run encode-quality benchmarks; loudnorm in them was a copy-paste artifact, not load-bearing for the benchmark's question. Verifiable: `grep -rn 'loudnorm' Scripts/Smoke/` returns zero matches.

## Out of Scope

- **External re-acquisition of the 22 movies.** Operator-driven via Sonarr/Radarr/manual. This directive flags them; the operator decides what to acquire and when.
- **Any treatment of the 8,227 TV episodes.** Accepted historical loss. Damage profile (small additional LRA forcing on already-compressed source) is acceptable; per-episode external re-acquisition is operator-prohibitive.
- **Restoring the audio-renorm-legacy infrastructure** (CommandBuilder shape, dedicated queue, capability flag). The closed directive's investigation showed re-pass doesn't recover damage; the infrastructure has no immediate use case.
- **Auto-flagging future new-arrival audio damage.** Linear-only enforcement is the prevention mechanism (C3 + C4). If damage somehow ships post-2026-05-25, that's a separate bug-shaped directive.
- **A UI surface for the 22-movie report.** CSV in `Reports/` is sufficient; no `/Activity` integration. Operator opens the CSV directly.
- **Reset of `AudioComplete` on the damaged files.** They stay marked complete. Stream-copy is the correct go-forward behavior for them -- re-encoding wouldn't fix the damage, only burn CPU. The KNOWN-ISSUES entry is the honest accounting.

## Constraints

- **R8**: contract test lives under `Tests/Contract/`.
- **R9**: any LIKE in the identification script uses `EscapeLikePattern` (paths contain `%`/`_`/`!`).
- **R12**: single-line docstrings; single-line SQL strings.
- **R15**: every new and edited def/class in the `### Files` list gets `# directive: legacy-audio-damage-accounting | # see legacy-audio-damage-accounting.C<N>`.
- **No code change in production audio-filter code unless C3/C4 audit finds an escape hatch.** If found, the fix lands in this directive; if not, this directive is documentation + tests only.
- **Cross-feature contract**: `linear-loudnorm.feature.md` `## Status` section gets a one-line pointer to `Tests/Contract/TestLinearLoudnormEnforcement.py` at DELIVERING so the contract test is discoverable from the feature doc.

## Engineering Calls Already Made

- **CSV (not JSON, not in-DB-only) for the 22-movie report.** Operator opens it in Excel/Sheets/Numbers; sorts, filters, annotates with "acquired YYYY-MM-DD"; no need to build any UI. Hidden bonus: it's a checked-in artifact, so the next operator (or claude) can see exactly which files were flagged at directive close.
- **`Reports/` is a new top-level directory.** Out of the code tree; clearly an artifact; gitignored sub-files are NOT okay here -- the report IS the deliverable.
- **No bulk-action automation.** 22 movies x 1-2 min operator decision each = ~30-45 min of operator work, one-time. Building Sonarr/Radarr integration to automate would cost more than the operator save.
- **TV episodes accepted as historical loss.** Source LRA on TV content is typically 5-8 LU; forcing to 7 LU added minimal additional compression. The per-file damage on each TV episode is small enough to be undetectable in normal viewing; bulk re-acquisition of 8,227 episodes is operator-prohibitive.
- **Contract test is the only forward guarantee that matters.** Documenting in a feature doc is necessary but insufficient; a mechanical test that fails when dynamic-mode reappears is what actually prevents regression. C4's "grep the tree for every `loudnorm=` emitter" is the durable form of "no silent fallback."
- **No worktree -- land on `main`.** Matches session preference.
- **No restoration of `audio-renorm-legacy` artifacts.** That directive is closed without execution. If a future operational need surfaces (e.g., a new linear-mode policy parameter change requires bulk re-renorm), reconsider then. The `_BuildAudioRenormShape` primitive can be added in a single small directive if/when justified.

## Status

Active 2026-06-08 -- phase: NEEDS_PLAN. Directive just opened; criteria + Files list written. Awaiting operator approval before phase advance.

### Files

| # | File | Action | Anchor (`# directive: legacy-audio-damage-accounting \| # see legacy-audio-damage-accounting.<ID>`) | R-rule notes |
|---|---|---|---|---|
| 1 | `Scripts/IdentifyLegacyDamagedMovies.py` | NEW | `C1` on `Main()` | R12: one-line docstring. R9: EscapeLikePattern on any LIKE in the targeting query. |
| 2 | `Reports/LegacyAudioDamagedMovies.csv` | NEW (generated artifact) | N/A (CSV; R15 does not apply) | Operator-facing deliverable. Header row includes BUG-NNNN context pointer. |
| 3 | `Tests/Contract/TestLinearLoudnormEnforcement.py` | NEW | `C3` on `test_no_dynamic_fallback`, `C4` on `test_audit_loudnorm_emitters`, `C5` on `test_ungainable_peak_refuses` | R8: under `Tests/Contract/`. R12: one-line docstrings. |
| 4 | `memory/KNOWN-ISSUES.md` | EDIT (add `BUG-NNNN` entry) | N/A (memory) | Five-field structured entry. |
| 5 | `Features/LoudnessAnalysis/linear-loudnorm.feature.md` | EDIT (Status section pointer to contract test) | N/A (feature doc; R15 does not apply) | R14: one-line pointer, no annotation/dating prose. |
| 6 | `Models/CommandBuilder.py` | EDIT (`BuildAudioFilters` ungainable-peak branch raises RuntimeError) | `C5` on `BuildAudioFilters` (comma-separated with existing `mv-suffix-greedy-collapse` anchor) | R12: edit-region only; one-line replacement of the dynamic-fallback block. |
| 7 | `Features/TranscodeQueue/QueueManagementBusinessService.py` | EDIT (admission gate adds ungainable-peak refusal) | `C6` on the admission predicate function | R12: edit-region only. R3: stateless. |
| 8 | `Features/ClipBuilder/ClipBuilderBusinessService.py` | EDIT (remove `-af loudnorm=...` at line 54) | `C7` on `ExtractAndConcatenate` | R12: edit-region only. |
| 9 | `Scripts/Smoke/EncodeAndVmaf.py` | EDIT (remove `-af loudnorm=...`) | `C8` on the encode call site | R12: edit-region only. |
| 10 | `Scripts/Smoke/FourKEncodingABC.py` | EDIT (remove `-af loudnorm=...`) | `C8` on the encode call site | R12: edit-region only. |
| 11 | `Scripts/Smoke/NewGirlEncodingABC.py` | EDIT (remove `-af loudnorm=...`) | `C8` on the encode call site | R12: edit-region only. |
| 12 | `Scripts/Smoke/NewGirlEncodingABC_VarianceBoost.py` | EDIT (remove `-af loudnorm=...`) | `C8` on the encode call site | R12: edit-region only. |

### Hook Conformance Pre-Flight

Accepted code-anchor syntax: **`# directive: legacy-audio-damage-accounting | # see legacy-audio-damage-accounting.C<N>`** -- second `#` after the pipe is required.

Easy-to-forget rules:
- **R12**: single-line docstrings only. The identification script has one docstring at module level + one per function; all single-line.
- **R14**: linear-loudnorm.feature.md edit REPLACES one Status-section line; no `(added by legacy-audio-damage-accounting 2026-06-08)` annotation.
- **R15**: applies to script `Main()` and test `test_*` functions.
- **No claim-query edits** (R10/R19 don't apply this directive).

### Promotions

(populated at DELIVERING)

### Verification

(populated at VERIFYING)
