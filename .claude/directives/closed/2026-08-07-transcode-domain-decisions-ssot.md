# Directive: transcode-domain-decisions-ssot

**Slug:** transcode-domain-decisions-ssot
**Status:** Closed
**Closed:** 2026-08-07
**Opened:** 2026-08-07
**Sequence:** Phase 1 of 4 (compliance-reason-recompute -> mediavortex-output-terminal -> plan-factory-flags)

## Ask

Domain decisions around Transcode / Remux / Audio shape currently live scattered across `audio-normalization.feature.md`, `work-bucket.feature.md`, `stuck-job-detection.feature.md`, and code comments. No single durable list. Repeat conversations re-derive the same 12 decisions. Fix: one SSoT list in `transcode.flow.md` with pointer lines from siblings.

**Docs only. Zero code change.** Locks intent so Phases 2-4 have a canonical reference.

## Domain Decisions (to be written into transcode.flow.md)

D1. Compliance is per-dimension. Video, Audio, Container each evaluated independently by their own vertical. No dimension short-circuits another.

D2. Slot strategy is driven by per-dimension compliance flags, NOT by ProcessingMode enum. VideoSlot: Reencode if `!videocompliant` else Copy. AudioSlot: Reencode if `!audiocompliant` else Copy. ContainerSlot: Mp4 if `!containercompliant` else Preserve. SubtitleSlot: Preserve always (unless explicit SubtitleFix intent).

D3. `ProcessingMode` is a reporting/priority tag only. Names which vertical drove the admission. Does not decide slot behavior.

D4. `WorkBucket` = generated column from the three compliance flags. Priority: `Unclassified > Compliant > Transcode > Remux > AudioFix`.

D5. Container target = `.mp4` always. MP4 mux writes `handler_name` (not `title`) for track identity -- MP4 spec drops `title` on audio streams.

D6. Audio emission on any Reencode-slot pass = 2 tracks per kept source language: Track 0 (default) = Dialog Boost from Demucs vocals-isolation on the source (once per encode); Track 1+ = Original per source stream, LRA-preserved.

D7. `TranscodedByMediaVortex = TRUE` is a terminal state. We do not re-encode our own outputs. To change encoding, re-acquire source via Sonarr/Radarr -> fresh scan -> new MediaFile row without the flag.

D8. Source file deleted after successful `ProcessFileReplacement` (TranscodedOutputPlacement:220). Once transcode succeeds + MediaFiles row updated, the original .mkv/.mp4 is removed from disk.

D9. Per-stream audio decisions read `Stream.channels` from ffprobe, NOT per-file `MediaFiles.AudioChannels` scalar. Multi-stream files have per-stream truth.

D10. Every Reencode audio pass runs the Demucs pre-encode pipeline (SourceMeasure -> Downmix -> Demucs -> Premix -> LoudnormMeasure). Progress ticks `TranscodeProgress.LastProgressUpdate` per substep.

D11. Emitter operates on source streams as-received. No idempotence heuristic (no "detect existing Boost track"). Idempotence is guaranteed structurally by D2 (audio only re-encoded when NOT audiocompliant) + D7 (our outputs are terminal, so they will not be re-encoded).

D12. Fail-loud everywhere. Probe failure = LastFFprobeError + one-shot NeedsReprobe. No silent retry caps. Stuck-detect = progress-tick staleness, not wall-clock.

## Success Criteria

C1. **`transcode.flow.md` gains `## Domain Decisions` section** with D1-D12 inline (not by reference). Placed after the `## What It Does` / `## Overview` section, before `## Stages`.

C2. **Pointer lines added** in sibling docs at the appropriate structural place:
- `Features/AudioNormalization/audio-normalization.feature.md` -- top-of-file note: "Slot strategy + per-dimension processing decisions live in `transcode.flow.md` Domain Decisions section."
- `Features/WorkBucket/work-bucket.feature.md` -- top-of-file note similar.
- `Features/ServiceControl/stuck-job-detection.feature.md` -- top-of-file note similar.

C3. **No duplication.** Sibling docs point to the SSoT; do not restate the decisions. Existing scattered decision text remains (historical; deletion in later directives when redundancy is proven).

C4. **CLAUDE.md `Where everything lives` section** gains one line pointing at the new SSoT: "**Transcode/Remux/Audio shape:** `transcode.flow.md` `## Domain Decisions` (D1-D12)".

## Files

**Edit:**
- `transcode.flow.md` -- add `## Domain Decisions` section with D1-D12
- `Features/AudioNormalization/audio-normalization.feature.md` -- pointer line at top
- `Features/WorkBucket/work-bucket.feature.md` -- pointer line at top
- `Features/ServiceControl/stuck-job-detection.feature.md` -- pointer line at top
- `CLAUDE.md` -- one line under `## Where everything lives`

**Create:** (none)

**Delete:** (none)

## Call-Graph Audit

- **Signal 1:** N/A -- docs only.
- **Signal 2:** N/A.
- **Signal 3:** N/A.
- **Signal 4:** OOS explicitly categorized below.
- **Signal 5:** N/A.

## Out of Scope

- **(a) In-flight preserved:** existing scattered decision text in sibling docs. Redundancy tolerated for one cycle; Phase 4 (`plan-factory-flags`) close will identify + prune redundant restatements.
- **(a) In-flight preserved:** all code -- zero touch this directive.
- **(a) Phases 2-4:** separate directives per operator sequence.

## Phase machine

NEEDS_STANDARDS_REVIEW -> NEEDS_PLAN -> NEEDS_DOC_PREREAD -> IMPLEMENTING -> VERIFYING -> DELIVERING

### Progress

- [x] NEEDS_STANDARDS_REVIEW
- [x] NEEDS_PLAN
- [x] NEEDS_DOC_PREREAD (transcode.flow.md + all 3 sibling *.feature.md files touched this session)
- [x] IMPLEMENTING: transcode.flow.md Domain Decisions section added (12 decisions inline)
- [x] IMPLEMENTING: pointer lines added to audio-normalization.feature.md, work-bucket.feature.md, stuck-job-detection.feature.md
- [x] IMPLEMENTING: CLAUDE.md 'Where everything lives' pointer added
- [x] VERIFYING: manual read-through; no contract test for docs
- [x] SMOKE-GATE: N/A (docs only)
- [x] DELIVERING: close report

### R13 overrides

(none)

### R18 overrides

(none)

### Promotions

| Source (directive) | Target (durable) |
|---|---|
| D1-D12 | `transcode.flow.md` `## Domain Decisions` section (this is the promotion) |

## Delivery Report

**STATUS:** Done

**WHAT SHIPPED:**
- `transcode.flow.md`: new `## Domain Decisions` section after entry-point line; D1-D12 inline
- `Features/AudioNormalization/audio-normalization.feature.md`: SSoT pointer line under slug
- `Features/WorkBucket/work-bucket.feature.md`: SSoT pointer line under slug
- `Features/ServiceControl/stuck-job-detection.feature.md`: SSoT pointer line under slug
- `CLAUDE.md` `## Where everything lives`: one-line pointer at the appropriate structural position

**HOW TO USE IT:** future work on Transcode/Remux/Audio shape references D1-D12 by number. Sibling docs point to the SSoT; do not restate.

**WHAT YOU NEED TO EXECUTE:** nothing. Docs only.

**CRITERIA VERIFICATION:**
- C1: transcode.flow.md `## Domain Decisions` section with D1-D12 present
- C2: pointer lines added to 3 sibling docs
- C3: no duplication introduced; existing scattered decision text stays (deletion deferred to later phases)
- C4: CLAUDE.md pointer added

**DECISIONS I MADE:**
- Inserted Domain Decisions BEFORE `## Stage Overview` so it renders as the first substantive section (frame-setting for readers)
- Kept sibling-doc pointers minimal (one line) -- easy to notice, low cost to maintain

**KNOWN GAPS / DEFERRED:**
- Phases 2-4 open as follow-up directives per operator sequence:
  - Phase 2: `compliance-reason-full-library-recompute`
  - Phase 3: `mediavortex-output-terminal`
  - Phase 4: `plan-factory-driven-by-compliance-flags`
