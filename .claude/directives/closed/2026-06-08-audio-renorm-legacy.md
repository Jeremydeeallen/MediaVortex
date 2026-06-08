# Current Directive

**Set:** 2026-06-08
**Status:** Closed -- no execution -- superseded by `legacy-audio-damage-accounting`
**Slug:** audio-renorm-legacy
**Interrupts:** local-staging (paused at `.claude/directives/paused/2026-06-08-local-staging.md`; resume after the superseding directive closes)

## Closed without execution

This directive proposed an audio-only re-pass on the 8,249 legacy-dynamic-mode files to apply linear-mode loudnorm. Investigation during NEEDS_PLAN review revealed:

1. **The legacy chain was destructive** -- `acompressor=threshold=-15dB:ratio=3:makeup=3dB` followed by `loudnorm=I=-23:LRA=7:TP=-2`. Peaks were limited and dynamic range was compressed irreversibly.
2. **Zero of the 8,249 files have `MediaFiles.KeepSource=TRUE`** -- the original source files have been deleted by `FileReplacement` post-flight in every case. There is no MV-managed original to re-transcode from.
3. **Audio-only re-pass would not fix the damage** -- it would re-normalize the LOUDNESS of already-damaged audio while leaving the compressed dynamic range and limited peaks intact. The CPU spend would buy cosmetic LUFS uniformity, not recovery.
4. **Population skew: 22 movies vs 8,227 TV episodes.** TV source content typically has compressed source LRA (5-8 LU) so the LRA=7 forcing was a small additional touch. Movies took the audible hit but are a small enough batch (22) to be operator-driven case-by-case.

Superseded by `legacy-audio-damage-accounting` -- documents the damage, flags the 22 movies for operator review, and audits the linear-loudnorm enforcement against any remaining dynamic-mode escape hatch.

## Outcome

Re-normalize the **8,249** library files that were loudnormed under the deprecated `dynamic loudnorm + acompressor` chain. Apply the current `linear-loudnorm` policy via an **audio-only re-encode** that preserves the video stream bit-for-bit. Goal: uniform broadcast-grade loudness (-23 LUFS, +/- 1 LUFS) across the entire library under one policy.

A worker with `Workers.AudioRenormEnabled=TRUE` claims rows from a new `AudioRenormQueue` table, runs `ffmpeg -c:v copy -af loudnorm=...:linear=true -c:a <bestmatch>` against the canonical file, replaces it via the existing `.inprogress` rename flow, then updates `MediaFiles.AudioCompletedAt` and clears any legacy dynamic-mode marker. Canary slice (default 100 files) must verify >= 99% land within +/- 1 LUFS of target and zero video corruption before the full 8,149 remainder is authorized.

## Concern

Three concerns motivate this work:

1. **Library policy fragmentation.** `linear-loudnorm.feature.md` declared "Linear is the only mode. No single-pass dynamic fallback." 8,249 of the 12,501 MV-normalized files (66%) were processed under the deprecated dynamic chain between 2025-10-03 and 2026-05-30. Those files have `AudioComplete=TRUE` and stream-copy forever -- they never re-enter the loudnorm path. The library now mixes two normalization policies indefinitely; show-to-show volume jumps (the original problem linear-loudnorm was meant to solve) persist across these legacy files.

2. **Full re-transcode is cost-prohibitive.** 8,249 movies + TV episodes at average ~5 min GPU encode each = ~28 days of solid GPU work. Audio-only re-encode at ~50-100x realtime over the audio stream takes ~1-2 minutes per file -- ~10-15 hours total CPU time, parallelizable across all workers. Audio path is CPU-bound not GPU-bound, so it doesn't compete with new-arrival transcodes.

3. **Reversibility per file is preserved.** The existing `MediaFilesArchive` table holds the original metadata of every file MV has touched. If a renorm pass introduces an audible regression on any file, the operator can identify the affected MediaFileId, restore from archive (if the original source is still on disk), and re-queue. The audio-only re-pass keeps the same `.inprogress -> atomic rename` flow `FileReplacement` already audits.

## Acceptance Criteria

### A. Identification

C1. `Scripts/SQLScripts/IdentifyLegacyDynamicLoudnorm.py` outputs the legacy-dynamic-mode target set: `MediaFiles.AudioComplete=TRUE` AND `AudioCorruptReason IS NULL` AND `AudioCompletedAt IS NOT NULL` AND the most-recent successful loudnorm-bearing `TranscodeAttempts` row for that MediaFile has `FfpmpegCommand` matching `%loudnorm%` AND NOT `%linear=true%`. Counts within +/- 1% of 8,249 at directive open. Verifiable: run script, total matches the pre-flight count, ten random sample rows pass manual inspection (legacy attempt is dynamic mode, no linear pass since).

### B. Schema

C2. `Workers` gains `AudioRenormEnabled BOOLEAN NOT NULL DEFAULT FALSE` via idempotent migration `Scripts/SQLScripts/AddAudioRenormSchema.py`. Re-runnable; no-op on second run. Verifiable: `\d Workers` shows the column with the correct default.

C3. Same migration creates `AudioRenormQueue (Id BIGSERIAL PRIMARY KEY, MediaFileId BIGINT NOT NULL REFERENCES MediaFiles(Id), Status TEXT NOT NULL DEFAULT 'Pending', CreatedAt TIMESTAMP NOT NULL DEFAULT NOW(), ClaimedAt TIMESTAMP NULL, ClaimedBy TEXT NULL, CompletedAt TIMESTAMP NULL, ErrorMessage TEXT NULL, UNIQUE(MediaFileId))`. UNIQUE(MediaFileId) guarantees idempotent enqueue. Verifiable: `\d AudioRenormQueue` shows the columns; second insert of same MediaFileId raises constraint violation.

### C. Command shape

C4. `Models/CommandBuilder.py` gets `_BuildAudioRenormShape(MediaFile, Job, Context) -> Dict[str, str]` that emits: `ffmpeg -i <canonical_input> -map 0:v:0 -map 0:a:0 -c:v copy -c:a <BuildAudioCodecArgs result> -af <BuildAudioFilters linear-mode result> -f mp4 -movflags +faststart -y <basename>-mv.mp4.inprogress`. Zero NVENC args, zero `-vf` filter, zero pix_fmt args, zero scale filter. Audio codec args delegate to existing `BuildAudioCodecArgs`; audio filter args delegate to existing `BuildAudioFilters` (which already returns linear-mode loudnorm per `linear-loudnorm.feature.md`). Verifiable: `Tests/Contract/TestAudioRenormShape.py::test_shape` asserts `-c:v copy` present, `-c:v av1_nvenc/hevc_nvenc/libsvtav1` absent, `loudnorm` + `linear=true` both present.

C5. **Video bit-preservation invariant.** Post-encode, the output's video stream MUST be byte-identical to the input's video stream. Verifiable: `Tests/Contract/TestAudioRenormShape.py::test_video_preservation` runs one real audio-renorm against a fixture file, then compares `ffmpeg -i <input> -map 0:v:0 -c copy -f md5 -` against the same expression on the output. MD5 equal -> pass; any difference -> fail loudly.

C6. **Linear loudnorm lands within tolerance.** Post-encode of a fixture file with known-off-target source LUFS (-18.0 or louder), the output measured via `ffmpeg -af ebur128` lands within +/- 1 LUFS of -23. Verifiable: `Tests/Contract/TestAudioRenormShape.py::test_loudnorm_lands` runs ebur128 on the output and asserts.

### D. Capability + claim

C7. `Features/TranscodeQueue/TranscodeQueueRepository.py` gets `ClaimNextPendingAudioRenormJob(WorkerName)` that returns one Pending row iff `Workers.Status='Online'` AND `Workers.AudioRenormEnabled=TRUE`. Routes through `Core.Database.WorkerCapabilityPredicate.BuildClaimPredicate` for the capability gate (`.claude/rules/db-is-authority.md`). Verifiable: `Tests/Contract/TestClaimAuthority.py::test_audio_renorm_authority` exercises the two-state truth table and the mid-flight toggle case (UPDATE Workers SET AudioRenormEnabled=FALSE between claim calls; second call returns None within one query).

### E. Orchestration

C8. `Scripts/AudioRenormalize.py` accepts `--canary N` (default 100), `--all`, `--dry-run`, and `--report` flags. `--dry-run` prints planned AudioRenormQueue inserts without executing. `--canary` inserts N random MediaFileIds from the legacy target set into AudioRenormQueue, ON CONFLICT DO NOTHING. `--all` inserts the remaining (legacy set MINUS already-queued) into AudioRenormQueue. `--report` prints current queue status: Pending/Claimed/Completed/Failed counts plus the canary's measured-LUFS distribution. Verifiable: dry-run on the live DB matches live-run count; live-run twice produces the same final queue state.

C9. Worker processes an AudioRenormQueue Pending row end-to-end: claim -> run audio-renorm command -> on ffmpeg success + size-sanity verification, atomic-rename `.inprogress` over the canonical file (existing `FileReplacement` machinery) -> `UPDATE MediaFiles SET AudioCompletedAt=NOW(), AudioCorruptReason=NULL WHERE Id=<MfId>` -> `UPDATE AudioRenormQueue SET Status='Completed', CompletedAt=NOW()`. On ffmpeg failure or size mismatch, leave canonical file untouched, write Status='Failed' with ErrorMessage, no MediaFiles update. Verifiable: integration smoke on 5 canary files reports 5 Completed rows; one synthetic-failure injection produces one Failed row with intelligible error.

### F. Canary gate

C10. After --canary 100 completes, the canary report (run by operator before --all is authorized) MUST show: >= 99% of completed rows have post-encode integrated LUFS within +/- 1 LUFS of -23 (measured via standalone ebur128 audit script), AND zero rows fail the C5 video-preservation check (re-verified for the 100), AND < 1% Failed rows (operator investigates any Failed). If any gate fails, `--all` is refused until the failure mode is understood. Verifiable: `Scripts/AudioRenormCanaryReport.py` exits 0 (gate pass) or 1 (gate fail) with structured output.

### G. Flow doc + operator surface

C11. `transcode.flow.md` Stage 5 (`ST6`) gets a new "Audio renorm shape (legacy)" subsection alongside the existing remux + subtitle-fix shapes. Names the trigger (AudioRenormQueue Pending row claimed), the command shape (C4 reference), the C5/C6 invariants, and the post-flight bookkeeping (C9 reference). The `## Seams` table gains one row for the AudioRenormQueue producer (Scripts/AudioRenormalize.py) -> consumer (worker loop) seam. Verifiable: `git diff transcode.flow.md` shows the additions; no annotation lines (R14 clean).

C12. `/Activity` page shows an "Audio Renorm" tile next to the existing Transcode and Quality queues, displaying `AudioRenormQueue.Pending` count + `AudioRenormQueue.Claimed` count + completion-rate-per-hour for the last 24h. No new UI controls -- the queue is operator-driven via the script. Verifiable: visual check; HTML element with id `audio-renorm-queue-tile` present with the three counts wired.

## Out of Scope

- **The 23,270 files with AudioComplete=FALSE.** They will get linear loudnorm naturally on their next encode via the existing transcode pipeline. No directive action needed.
- **The 3,508 NULL-state files.** Handled by the existing probe + DeriveCompletionFlags path. Out of band.
- **Files marked `already_at_target_loudness` (3,172) or `below_bitrate_floor` (6,988).** Correctly excluded by C1's targeting query because their `AudioCorruptReason` is not NULL. No work to do.
- **Per-worker UI toggle for AudioRenormEnabled.** Set via SQL (`UPDATE Workers SET AudioRenormEnabled=TRUE WHERE WorkerName='X'`) for v1. Future directive can add /Activity modal control if operator finds the SQL toggle painful.
- **Auto-enrollment of new dynamic-mode files going forward.** `linear-loudnorm.feature.md` already mandates linear-only, so the dynamic-mode population is closed -- no new entrants. If a new dynamic-mode encode somehow ships, it's a bug in the linear-loudnorm enforcement, not this directive's concern.
- **Audio re-measurement before queuing.** Not measure-then-decide; just renorm every targeted file. Loudnorm on an already-near-target file is mathematically a small fixed gain (no audible artifact in linear mode), so re-renorming files that drifted slightly off target is harmless. Measure-first would add a probe pass per file at marginal savings.
- **Staging the audio-renorm jobs.** Audio-only ffmpeg reads the source linearly (no random seeks), output is small (~150 MB), and total wall time per file is ~1-2 min -- well below the SMB-handle-drop window observed in `local-staging.feature.md` C9-C12. Run on canonical paths. If a host shows SMB drops on this workload, it can opt-in to local-staging in a follow-up.
- **Per-attempt video bit-identity audit on the full 8,149.** C5 is enforced once via the contract test fixture; the 100-file canary re-verifies; the 8,149 remainder trusts the invariant (the contract test is the proof, not per-file re-checks). If a bug snuck past the contract test, the canary catches it before --all.

## Constraints

- **db-is-authority** (`.claude/rules/db-is-authority.md`): every `ClaimNextPendingAudioRenormJob` call reads `Workers.AudioRenormEnabled` + `Status` fresh. No Python cache. Operator can flip the flag mid-flight and the next claim honors it.
- **R3**: no `self._cached_*` in new code. CommandBuilder shape is stateless per call.
- **R10 + R19**: the new claim path lands in `Features/TranscodeQueue/TranscodeQueueRepository.py` only (no other module emits `Claim*` queries against AudioRenormQueue).
- **R11**: migration uses `ADD COLUMN IF NOT EXISTS` + `CREATE TABLE IF NOT EXISTS`. Re-runnable.
- **R12**: new code uses single-line SQL strings + one-line docstrings. Edits to existing triple-quoted SQL stay out of the edit region.
- **R14**: `transcode.flow.md` Stage 5 update REPLACES content in place. No `(extended for audio-renorm-legacy YYYY-MM-DD)` annotation lines.
- **R15**: every new and every edited def/class in the `### Files` list gets `# directive: audio-renorm-legacy | # see audio-renorm-legacy.C<N>`. If a function already carries another active or closed directive's anchor (e.g. `CreateTemporaryFilePath` carries `local-staging.C4`), use the comma-separated convention per BUG-0045: `# directive: local-staging, audio-renorm-legacy | # see local-staging.C4, audio-renorm-legacy.C9`.
- **Cross-feature contract:** `audio-completion.feature.md` gains a new Workflow row at DELIVERING ("Renormalize legacy dynamic-mode file") referencing this directive's Promotions.

## Engineering Calls Already Made

- **Audio-only re-pass (not full re-transcode).** Reasons: 50-100x cheaper than full transcode (~10-15h CPU vs ~28d GPU), preserves the existing video output exactly (C5 invariant), reversible per-file via MediaFilesArchive.
- **Separate `AudioRenormQueue` table (not reuse TranscodeQueue).** Different lifecycle, different worker capability, different command shape, different failure semantics. Smaller blast radius; the existing transcode claim path doesn't need to learn about audio-renorm semantics.
- **Per-worker capability flag, not auto-enroll.** Operator decides which workers do renorm work. Likely a CPU-rich worker (wakko-1 / dot-1 on larry's LXC 218) since this is CPU-bound, not GPU-bound. I9-2024 stays GPU-pinned for NVENC jobs.
- **Canary-then-all flow with explicit operator authorization between phases.** Even at 50-100x realtime, 8,249 files is meaningful. C10 gate enforces that the canary measurably succeeded before the remaining 8,149 are queued. Operator authorizes the --all run; the script doesn't auto-promote.
- **Output replaces canonical file via existing FileReplacement `.inprogress` flow.** No new replacement code path; reuse the audited, atomic rename + MediaFilesArchive write that today's transcode-success path uses.
- **Post-renorm bookkeeping clears AudioCorruptReason.** Files marked by clause (c) of DeriveCompletionFlags have NULL reason; legacy files do too. Clearing maintains the invariant "if AudioComplete=TRUE and reason=NULL, the most-recent loudnorm-bearing attempt is linear-mode."
- **No re-measurement before queuing.** Renorming an already-compliant file with linear-mode loudnorm produces a near-zero fixed gain -- no audible artifact. The marginal CPU savings of measure-first don't justify the added complexity.
- **No worktree -- land on `main`.** Matches session preference for this project.

## Status

Active 2026-06-08 -- phase: NEEDS_PLAN. Directive just opened; criteria + Files list written. Awaiting operator approval before phase advance.

### Files

| # | File | Action | Anchor (`# directive: audio-renorm-legacy \| # see audio-renorm-legacy.<ID>`) | R-rule notes |
|---|---|---|---|---|
| 1 | `Scripts/SQLScripts/AddAudioRenormSchema.py` | NEW | `C2`/`C3` on `Run()` | R11: idempotent `ADD COLUMN IF NOT EXISTS` for Workers + `CREATE TABLE IF NOT EXISTS` for AudioRenormQueue. R12: single-line SQL strings. |
| 2 | `Scripts/SQLScripts/IdentifyLegacyDynamicLoudnorm.py` | NEW | `C1` on `Main()` | R12: one-line docstring. Outputs row count + sample rows + writes CSV. |
| 3 | `Models/CommandBuilder.py` | EDIT (add `_BuildAudioRenormShape`) | `C4`/`C5`/`C6` on `_BuildAudioRenormShape` | R12: one-line docstring. R3: stateless. R6: input/output paths via `Core.PathStorage`. |
| 4 | `Features/TranscodeQueue/TranscodeQueueRepository.py` | EDIT (add `ClaimNextPendingAudioRenormJob` + `EnqueueAudioRenormJob` + `MarkAudioRenormCompleted` + `MarkAudioRenormFailed`) | `C7` on each new method | R3: stateless query wrappers. R10/R19: claim path lives here. Routes through `WorkerCapabilityPredicate.BuildClaimPredicate('AudioRenormEnabled')`. |
| 5 | `Core/Database/WorkerCapabilityPredicate.py` | EDIT (whitelist `'AudioRenormEnabled'` capability column) | `C7` on the whitelist constant | R12: one-line constant addition. |
| 6 | `Features/TranscodeJob/ProcessTranscodeQueueService.py` | EDIT (worker loop dispatches AudioRenormQueue claims to a new processing path) | `C9` on the dispatch + processing function | R3: no cache. R12: edit-region only. Comma-separated anchor with prior directives' anchors. |
| 7 | `Scripts/AudioRenormalize.py` | NEW | `C8` on `Main()`, `C10` on `RunCanaryGate()` | R12: one-line docstring. Idempotent ON CONFLICT DO NOTHING insert. |
| 8 | `Scripts/AudioRenormCanaryReport.py` | NEW | `C10` on `Main()` | R12: one-line docstring. Exits 0 on gate pass, 1 on fail. |
| 9 | `Features/TeamStatus/TeamStatusController.py` | EDIT (extend `/api/TeamStatus` payload with `AudioRenormQueue` counts) | `C12` on the payload extension | R12: edit-region only. |
| 10 | `Templates/Activity.html` | EDIT (add AudioRenorm tile) | N/A (HTML; R15 does not apply) | Follows existing Transcode + Quality queue tile patterns. |
| 11 | `transcode.flow.md` | EDIT (Stage 5 audio-renorm subsection + Seams row) | N/A (flow doc; R15 does not apply) | R14: replace in place; no annotation lines. |
| 12 | `Tests/Contract/TestAudioRenormShape.py` | NEW | `C4`/`C5`/`C6` distributed across `test_*` functions | R8: under `Tests/Contract/`. R12: one-line docstrings. |
| 13 | `Tests/Contract/TestClaimAuthority.py` | EDIT (add `test_audio_renorm_authority`) | `C7` on the new test function | R12: one-line docstring. |
| 14 | `memory/KNOWN-ISSUES.md` | EDIT (cross-link `linear-loudnorm.feature.md` from the legacy-dynamic-mode population note) | N/A (memory) | One-line note describing the closed-population + how this directive remediates. |

### Hook Conformance Pre-Flight

Accepted code-anchor syntax: **`# directive: audio-renorm-legacy | # see audio-renorm-legacy.C<N>`** -- second `#` after the pipe is required.

Easy-to-forget rules:
- **R3 + db-is-authority**: Workers.AudioRenormEnabled is read fresh on every claim. No `self._cached_*` anywhere.
- **R12 edit-region trap**: edits to existing triple-quoted SQL in `ProcessTranscodeQueueService.py` keep the triple-quoted block OUT of the edit region.
- **R14**: `transcode.flow.md` Stage 5 update REPLACES content in place. No annotation lines.
- **R15**: every new and every edited def/class in the `### Files` list gets the two-anchor line. For shared functions touched by another directive, use comma-separated convention per BUG-0045.
- **R19**: AudioRenormQueue claim queries live only in `TranscodeQueueRepository.py`.

### Promotions

(populated at DELIVERING)

### Verification

(populated at VERIFYING)
