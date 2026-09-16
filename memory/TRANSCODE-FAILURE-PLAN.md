# Transcode-Failure Scope: Complete Fix Plan

**Scope opened:** 2026-09-15 -- operator scope-lock covering BUG-0100..0104 (see `memory/BUG-INDEX.md`) + related dependencies BUG-0095, BUG-0072, BUG-0105.

**Scope-lock rule:** work is bounded to these bugs + their named dependencies. No adjacent scope creep. Any newly discovered class of failure lands in `memory/KNOWN-ISSUES.md` as a separate bug and waits its turn; do not silently fold in.

**Principles applied throughout:**
- **KISS** -- one directive per one symptom per one root fix; no bundling
- **fail-loud** (`.claude/rules/fail-loud.md`) -- named exception classes at boundaries; no bare `try/except: continue`
- **db-is-authority** (`.claude/rules/db-is-authority.md`) -- no code-cached rules; `FailureClasses` table is authoritative
- **writer-owns-cascade** where applicable
- **doc-layering** (`.claude/rules/doc-layering.md`) -- Promotions at DELIVERING
- **gui-editable-knobs** (`.claude/rules/gui-editable-knobs.md`) -- operator-tunable rules ship a GUI in the same directive
- **no bandaids** -- each fix targets root cause, not symptom polish
- **one-editor-per-conceptual-unit** -- `FailureClass` column owned by BUG-0095's directive; other directives READ it

---

## Meta-fix: three-bucket failure model

**Today (broken):** attempts land `Success=TRUE` OR `Success=FALSE + retry`. No structured terminal state. Every failed attempt re-enters the queue eventually; unrecoverable-source files burn compute forever.

**Target:** three buckets.

| Bucket | Meaning | Example | Retry policy |
|---|---|---|---|
| Transient | ephemeral / worker crash / GPU OOM | Demucs daemon crash, mid-encode SIGTERM | auto-retry |
| PipelineDefect | code gap or missing filter | BUG-0104 pix_fmt rejection | fix code once, then retry-safe for all peers |
| SourceTerminal | source is fundamentally unrecoverable | BUG-0103 corrupt `-mv.mp4`, BUG-0072 destroyed-by-96k-downmix | **no retry**, operator callout with remediation label |

Discrimination lives in **BUG-0095's** enhanced `FailureClasses` table.

---

## Dependency graph

```
Phase 1 (foundation, must-first)
  └── BUG-0095: FailureClass + Terminal + Remediation + classifier + /FailedJobs surface

Phase 2 (prevent new damage, second)
  └── BUG-0105 (new): TranscodedOutputPlacement pre-swap ffprobe validation

Phase 3 (stop bleeding, parallelizable after Phase 1)
  ├── BUG-0104: VideoSlot pix_fmt normalization filter (pipeline fix)
  ├── BUG-0103: PreEncodeAudioPipeline source-readability preflight
  └── BUG-0102: SubtitleSlot MAX_SUB_SAMPLE_BYTES preflight

Phase 4 (decomposition-driven, after Phase 1)
  ├── BUG-0101: SQL decompose ComplianceGate cluster (automatic once BUG-0095 lands)
  └── BUG-0100: Diagnose validator rule; route as pipeline fix OR Terminal

Phase 5 (recovery ops, operator-driven)
  └── BUG-0072-style regrab via Sonarr / Radarr for Terminal-flagged files
```

**Rule:** each phase's directives close before the next phase opens (for dependent phases). Phase 3 directives can run parallel with each other but NOT before Phase 1 lands. Phase 2 has no dependency on Phase 1 but is second-priority because it stops the vector that creates BUG-0103's damage class.

---

## Per-bug plan

### BUG-0095 -- Failure classification (Phase 1 foundation)

**Directive slug:** `bug-0095-failure-classification`

**Root fix (KISS-audited 2026-09-16 -- removed denormalization violation):**
- `TranscodeAttempts.FailureClass TEXT NULL` column (populated by classifier at failure INSERT). NO denormalized Terminal column on `TranscodeAttempts` -- would create two-writer sync tax on config-derived state; violates `db-is-authority.md`.
- `FailureClasses` table: `ClassName TEXT PK`, `Priority INT` (first-match-wins), `ErrorPattern TEXT` (regex), `Terminal BOOL NOT NULL DEFAULT FALSE`, `Remediation TEXT NOT NULL`, `CreatedAt`, `UpdatedAt`. Single source of truth for Terminal.
- One-fn regex classifier fires at `TranscodeAttempts` INSERT when `Success=FALSE`; writes `FailureClass` column only.
- `Core/Database/TerminalFailurePredicate.BuildTerminalGate(MediaFileIdColumn)` -- single SQL-fragment helper mirroring `FailureBudgetPredicate.BuildCapPredicate` shape; every claim/admission query gates via this fragment, JOINing `FailureClasses.Terminal` at query time.
- `/FailedJobs` HTMX page groups by FailureClass with counts + samples + Terminal cards use single `card--terminal` CSS class + static Remediation text from JOIN (no dynamic badge component, no per-row JS).
- `/settings/FailureClasses` GUI tuner (per `gui-editable-knobs.md`).
- Auto-retry / requeue paths JOIN `FailureClasses.Terminal` at gate time and refuse re-queue on Terminal=TRUE.

**Files (existing feature doc + controller + template EXTEND, do not create-new):**
- `Scripts/SQLScripts/AddFailureClassColumn_2026_09_16.py` (new; adds `TranscodeAttempts.FailureClass TEXT NULL`)
- `Scripts/SQLScripts/AddFailureClassesTable_2026_09_16.py` (new; creates `FailureClasses` table incl `Terminal BOOL NOT NULL DEFAULT FALSE` from the start)
- `Scripts/SQLScripts/AddPriorFailureClassAudit_2026_09_16.py` (new; adds `FailureBudgetResets.PriorFailureClass TEXT NULL`)
- `Features/FailureAccounting/Services/FailureClassifier.py` (new)
- `Core/Database/TerminalFailurePredicate.py` (new; single SQL-fragment helper)
- `Features/FailureAccounting/FailedJobsController.py` (EXTEND -- already exists per C7/C8)
- `Features/FailureAccounting/Repositories/FailedJobsRepository.py` (EXTEND -- add Terminal JOIN + FailureClass grouping)
- `Features/FailureAccounting/failure-accounting.feature.md` (EXTEND -- C11 already added; Progress checklist below)
- `Features/FailureAccounting/failure-accounting.flow.md` (EXTEND -- add classifier stage + Terminal-gate seam)
- `Templates/FailedJobs.html` (EXTEND -- add Terminal card section + `card--terminal` CSS)
- `Features/Settings/SettingsController.py` + `Templates/settings.html` (EXTEND -- add Failure Classes CRUD tab)
- `Tests/Contract/TestFailureClassifier.py` (new)
- `Tests/Contract/TestFailureClassTerminal.py` (new -- 5 test cases per C11 Verifiable list)

**Seed rules (Priority ascending):**

| ClassName | Priority | ErrorPattern | Terminal | Remediation |
|---|---|---|---|---|
| `source_unreadable` | 10 | `moov atom not found\|Invalid data found when processing input` | TRUE | Regrab source (Sonarr/Radarr) |
| `source_audio_corrupt_dts` | 20 | `Error while decoding stream.*dca` | TRUE | Regrab source |
| `source_video_corrupt_h264` | 30 | `Error while decoding stream.*h264` | TRUE | Regrab source |
| `subtitle_sample_too_large` | 40 | `mov_text.*Result too large` | FALSE (drop-and-retry) | Auto-drop stream OR choose mkv variant |
| `pix_fmt_unsupported` | 50 | `Impossible to convert between the formats.*yuv4[24]2p16` | FALSE | Pipeline fix pending (BUG-0104) |
| `stereo_downmix_source_unreadable` | 55 | `stereo downmix failed.*moov atom not found` | TRUE | Regrab source |
| `demucs_daemon_down` | 60 | `DemucsDaemonUnavailableError` | FALSE | Restart worker; auto-retry via D13 |
| `loudness_invalid_unrecoverable` | 70 | `ComplianceGateFailed: invalid_loudness_measurement` | FALSE (pending BUG-0100 diagnosis) | See BUG-0100 |
| `ffmpeg_crash_midencode` | 80 | `Segmentation fault\|core dumped` | FALSE | Retry once; escalate if repeats |
| `codec_map_mismatch` | 90 | `Requested output format.*does not accept` | FALSE | Pipeline fix pending |
| `orphan_output` | 100 | `Refusing to overwrite existing` | FALSE | Delete `.inprogress` + retry |
| `unclassified` | 9999 | `.*` (catch-all) | FALSE | Investigate manually |

**Tests:**
- `TestFailureClassifier`: each rule's regex matches expected input; classifier picks lowest-priority-first-match
- `TestTerminalNoRetry`: attempt with Terminal=TRUE + `TranscodeQueue` auto-requeue call → no new queue row inserted
- `TestFailedJobsPage`: `/FailedJobs` returns 200 with per-class counts

**Doc updates:**
- `failure-accounting.feature.md` (new; owns FailureClass + FailureClasses + classifier + Terminal contract)
- `failure-classification.flow.md` (new; ST1 Insert -> ST2 Classify -> ST3 Write row -> ST4 Surface)

**Blockers / gates:** none.

**I9 smoke:** synthetic failure INSERT (each seed rule) → verify correct FailureClass assigned + Terminal flag respected.

---

### BUG-0105 -- FileReplacement pre-swap ffprobe validation (Phase 2)

**Directive slug:** `bug-0105-output-readability-before-swap`

**Root fix:** `TranscodedOutputPlacement.Execute` MUST ffprobe the transcoded `.inprogress` before renaming to `-mv.mp4` AND before replacing source `.mkv`. Unreadable output (missing moov, zero streams, ffprobe non-zero exit) → refuse swap, roll back rename, attempt lands `Success=FALSE, FailureClass=source_unreadable` (via BUG-0095 classifier), `.inprogress` file either kept for post-mortem or deleted (operator policy in `SystemSettings`).

**Files:**
- `Features/FileReplacement/TranscodedOutputPlacement.py` (+ `_ValidateOutputReadable` helper)
- `Features/FileReplacement/file-replacement.feature.md` (new criterion + Seams row)
- `Tests/Contract/TestOutputReadabilityBeforeSwap.py`

**Anti-bandaid discipline:**
- NO `try/except: continue` around `_ValidateOutputReadable`; raise propagates per `fail-loud.md`
- NO silent skip if ffprobe unavailable; that's a FATAL deploy misconfig

**Blockers / gates:** BUG-0095 lands FIRST so the `source_unreadable` FailureClass row exists for classifier lookup.

**I9 smoke:** truncate an `.inprogress` to first 100 bytes → run `Execute` → verify swap refused + `MediaFile.FilePath` unchanged + `.inprogress` state per policy.

---

### BUG-0104 -- VideoSlot pix_fmt normalization (Phase 3)

**Directive slug:** `bug-0104-video-pixfmt-normalize`

**Root fix:** VideoSlot emit-reencode path prepends `-vf format=<encoder-supported>` (or `-pix_fmt <encoder-supported>` output-side) when source pix_fmt not in encoder's accepted set. Per-codec constant map keyed on `Profile.VideoCodec` + source bit depth:

| Encoder | 8-bit target | 10-bit target |
|---|---|---|
| `av1_nvenc` / `hevc_nvenc` | `nv12` | `p010le` |
| `av1_qsv` / `hevc_qsv` | `nv12` | `p010le` |
| `libaom-av1` / `libx265` | `yuv420p` | `yuv420p10le` |
| `libsvtav1` | `yuv420p` | `yuv420p10le` |

**Files:**
- `Features/TranscodeJob/Emit/Slots/VideoSlot.py` (+ constant `ENCODER_PIXFMT_MAP`)
- `Features/TranscodeJob/Emit/Slots/video-slot.feature.md` (add criterion + Seams row for pix_fmt normalization)
- `Tests/Contract/TestVideoSlotPixFmtNormalization.py`

**Anti-bandaid:** preserve source bit depth for HDR-relevant sources; DO NOT drop unconditionally to 8-bit.

**Blockers / gates:** BUG-0095 (FailureClass `pix_fmt_unsupported` for tracking legacy failures pre-fix); no hard dependency, but landing after BUG-0095 lets the classifier count "was pix_fmt_unsupported, now zero occurrences" as directive-close evidence.

**I9 smoke:** 10-bit 4:2:2 source (attempt 93324's MediaFileId 703875) → transcode succeeds; ffprobe output shows target pix_fmt matches encoder capability.

---

### BUG-0103 -- Pre-encode source-readability preflight (Phase 3)

**Directive slug:** `bug-0103-source-readability-preflight`

**Root fix:** `PreEncodeAudioPipeline._RunDemucsChain` first substep = `_ProbeSourceReadable(SourceFilePath)` runs `ffprobe -show_format` (cheap; no decode). Non-zero exit → `raise SourceUnreadableError(f"source unreadable: {path}: {stderr_tail}")`. `AudioPreEncodeFacade.Prepare` propagates raise. `JobProcessor.Process` catches + sets `MediaFiles.AdmissionDeferReason='source_unreadable'` + attempt lands `Success=FALSE, ErrorMessage=<SourceUnreadableError body>`. BUG-0095 classifier tags `FailureClass='source_unreadable'` with `Terminal=TRUE`. **NOT** via D13 Copy fallback -- Copy would spawn a second ffmpeg on the same unreadable file and crash identically. Copy fallback is for Demucs-daemon failures, not source-integrity failures.

**Files:**
- `Features/AudioNormalization/Services/PreEncodeAudioPipeline.py` (+ `_ProbeSourceReadable` helper + `SourceUnreadableError` class)
- `Features/AudioNormalization/Services/AudioPreEncodeFacade.py` (propagation path)
- `Features/TranscodeJob/Worker/JobProcessor.py` (catch + route; distinguish from `DemucsDaemonUnavailableError`)
- `Features/AudioNormalization/audio-normalization.feature.md` (add Seams row S13; extend C6 "operator_review_pending" contract to enumerate `source_unreadable` reason)
- `Features/AudioNormalization/audio-normalization.flow.md` (ST2 substep prepend before (a) SourceMeasure)
- `Tests/Contract/TestPreEncodeSourceReadability.py`

**Anti-bandaid discipline:**
- Original entry suggested "enrich exception message" -- REJECTED after operator pushback 2026-09-15; enrichment is observability, not fix.
- Fix is preflight + terminal routing, NOT a wider `try/except` around Demucs.

**Blockers / gates:** BUG-0095 lands FIRST for the classifier row. BUG-0105 lands to close the corruption inflow.

**I9 smoke:** truncate a test file to zero moov → enqueue → attempt fails with `SourceUnreadableError`, MediaFile has `AdmissionDeferReason='source_unreadable'`, FailureClass row is `source_unreadable` + Terminal=TRUE, no new TranscodeQueue row inserted on next tick.

---

### BUG-0102 -- Subtitle sample-size preflight (Phase 3)

**Directive slug:** `bug-0102-subtitle-sample-size-preflight`

**Root fix:** `SubtitleSlot` preflight ffprobe measures max sample size per subtitle stream (`ffprobe -show_packets -select_streams s:<idx> -show_entries packet=size -of csv`). For each stream, if max sample size > `MAX_SUB_SAMPLE_BYTES` (constant = 2000; configurable via `SystemSettings.SubtitleMaxSampleBytes` per `gui-editable-knobs.md`) AND target container = mp4 → **drop** that subtitle stream + log `SubtitleStreamDropped(stream_idx=<n>, max_bytes=<m>, threshold=2000, reason=mov_text_overflow)`. All streams drop → attempt still succeeds with zero subtitle streams (log + operator visible via `/Activity` per-attempt detail).

**Optional operator-policy path:** `SystemSettings.SubtitleOverflowPolicy IN ('drop', 'terminal')`. `terminal` routes to `FailureClass='subtitle_uncroppable'` with Terminal=TRUE + Remediation="choose mkv variant". `drop` is the default per KISS.

**Files:**
- `Features/TranscodeJob/Emit/Slots/SubtitleSlot.py` (+ `_MaxSampleBytesPerStream` helper)
- `Features/TranscodeJob/Emit/Slots/subtitle-slot.feature.md` (add criterion + Seams row; extend BUG-0090's TEXT_SUB_CODECS whitelist with MAX_SUB_SAMPLE_BYTES clause)
- `Scripts/SQLScripts/AddSubtitleOverflowSettings_2026_09_XX.py` (`SubtitleMaxSampleBytes`, `SubtitleOverflowPolicy`)
- `Templates/settings.html` (Subtitle tab additions)
- `Tests/Contract/TestSubtitleSampleSizePreflight.py`

**Anti-bandaid:** dropping loses operator content, but oversized mov_text in mp4 is IMPOSSIBLE by container spec -- the loss is intrinsic. Log + surface, don't hide.

**Blockers / gates:** BUG-0095 for FailureClass row IF operator picks `terminal` policy. No blocker for default `drop` path.

**I9 smoke:** source with karaoke-style long subtitle line (Attack on Titan S03E18 confirmed offender from earlier smoke) → transcode succeeds with subtitle stream dropped + log line emitted.

---

### BUG-0101 -- ComplianceGate cluster decomposition (Phase 4)

**Directive slug:** `bug-0101-compliance-gate-decompose`

**Root fix:** after BUG-0095 lands, decomposition is automatic on new failures. One-shot backfill script classifies existing rows.

- Script: `Scripts/SQLScripts/ClassifyExistingComplianceGateFailures.py` -- iterates `TranscodeAttempts WHERE Success=FALSE AND FailureClass IS NULL AND ErrorMessage ILIKE '%ComplianceGateFailed:%'`, runs classifier, writes FailureClass column
- After backfill, `/FailedJobs` renders each sub-cause with count. Operator picks top-1 for its own directive.

**Files:** one script + optional new seed rules in `FailureClasses` if backfill reveals unmatched sub-causes.

**Blockers / gates:** BUG-0095.

**Directive close criterion:** backfill run + top-3 sub-causes each have a FailureClass row + `/FailedJobs` renders the breakdown. Each downstream sub-cause opens as its own directive.

---

### BUG-0100 -- Doctor Who invalid_loudness_measurement diagnosis (Phase 4)

**Directive slug:** `bug-0100-loudness-validator-diagnose`

**Root fix:** step 1 = diagnose. Read `Features/AudioNormalization/LoudnessMeasurementValidator.IsValid` + `Features/Compliance/ComplianceGate.Evaluate` audio-loudness branch. Enumerate every reject reason. Identify which one fires for MediaFileId 709363.

Step 2 branches:

**(A) Stale-snapshot bug:** gate reads pre-remeasure column values, misses fresh writes. Fix per `db-is-authority.md`: no `_cached_*` on validator; fresh DB read per call. Pipeline fix (`FailureClass=Transient after fix`).

**(B) Real quality rule fires legitimately:** e.g. Original LRA=3.1 below hard `MinValidLoudnessRangeLU` floor. Route to `AdmissionDeferReason='operator_review_pending'` per C6 + `FailureClass='loudness_below_measurement_floor'` Terminal=TRUE. Remediation: "source is content-classified low-dynamic-range; accept-untranscoded OR flag for source-quality bypass policy."

**Files (contingent on branch):**
- `Features/AudioNormalization/LoudnessMeasurementValidator.py`
- `Features/Compliance/ComplianceGate.py`
- `Features/AudioNormalization/audio-normalization.feature.md` (C6 extension)
- `Tests/Contract/TestLoudnessValidatorRules.py`

**Anti-bandaid discipline:** do NOT lower the threshold to make Doctor Who pass. Understand which rule fires, then either fix the real bug OR route legitimately.

**Blockers / gates:** BUG-0095 for Terminal routing if step-2 goes branch (B).

**I9 smoke:** synthetic MediaFile with the exact SourceIntegratedLufs / LRA / TP / Threshold values of 709363 → invoke `LoudnessMeasurementValidator.IsValid` → assert which rule returns invalid → matches production behavior. Then apply fix + assert opposite result.

---

### Phase 5 -- Recovery ops

**Not a code directive.** Operator-driven work.

After Phase 3 lands, known damaged files surface via:
```sql
SELECT DISTINCT mf.Id, mf.FileName, ta.FailureClass, fc.Remediation
FROM MediaFiles mf
JOIN TranscodeAttempts ta ON ta.MediaFileId = mf.Id
JOIN FailureClasses fc ON fc.ClassName = ta.FailureClass
WHERE fc.Terminal = TRUE
  AND ta.AttemptDate > NOW() - INTERVAL '30 days'
ORDER BY ta.AttemptDate DESC
```

**Tools:**
- Skill `mediavortex-sonarr-refresh` for Sonarr series
- Skill `mediavortex-analyze-transcode` per file for pre-regrab audit
- `Scripts/ArrRescanAndSearchSeries.py` for bulk operations
- Manual delete of corrupt `-mv.mp4` + un-monitor + re-monitor for Sonarr grab

Operator drives the regrab decisions; assistant executes SQL + Sonarr API calls when requested.

---

## Sequencing rules

1. **Dialog-boost-emission-integrity directive** (currently at DELIVERING) closes BEFORE Phase 1 opens. One directive at a time.
2. **Each phase's directives close before the next dependent phase opens.** Phase 3 directives may run in parallel with each other but not before Phase 1 lands.
3. **Every directive ships:** contract test(s), feature/flow doc updates (Promotions at DELIVERING per `doc-layering.md`), I9 smoke gate (per `ceo-mode.md` VERIFYING→DELIVERING), NO bandaids, NO scope creep.
4. **Directive close authority:** operator, per `ceo-mode.md` + `feedback_never_close_until_operator_agrees`. Delivery report lists Decisions, Gaps, Deferred; operator approves close.

---

## Progress tracking

| Bug | Directive slug | Phase | Status |
|---|---|---|---|
| BUG-0095 | `bug-0095-failure-classification` | 1 | **DELIVERING 2026-09-16** -- C10 + C11 shipped: migrations live, classifier auto-invoked at UpdateTranscodeAttempt dispatcher, Terminal gate at 6 admission sites + AddJobToQueue envelope, Reset extended with PriorFailureClass audit, /FailedJobs Terminal decoration, /api/FailureClasses CRUD, flow doc extended (ST1.5 + ST3.5 + S6 + S7), 25/25 contract tests pass, 839 recent failures backfill-classified (25 Terminal-flagged MediaFiles = Phase 5 regrab worklist), operator flip live-verified. Awaiting operator close approval. |
| BUG-0105 | `bug-0105-output-readability-before-swap` | 2 | not started |
| BUG-0104 | `bug-0104-video-pixfmt-normalize` | 3 | not started |
| BUG-0103 | `bug-0103-source-readability-preflight` | 3 | not started |
| BUG-0102 | `bug-0102-subtitle-sample-size-preflight` | 3 | not started |
| BUG-0101 | `bug-0101-compliance-gate-decompose` | 4 | not started (blocked on 0095) |
| BUG-0100 | `bug-0100-loudness-validator-diagnose` | 4 | not started (blocked on 0095) |
| BUG-0072-style recovery | (ops, no directive) | 5 | ongoing after Phase 3 |

**Update this section as each directive advances / closes.**
