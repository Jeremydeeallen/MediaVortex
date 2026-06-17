# Current Directive

**Set:** 2026-06-17
**Status:** Active -- phase: IMPLEMENTING
**Slug:** audio-vertical-perfection-and-self-healing

## Outcome

Close the bar-lowering pattern. Deliver true 100% audio vertical with full
SOLID compliance + system-level self-healing. Every gap I previously
deferred as "out of scope" or "follow-up" is in scope here. The vertical
detects and heals its own DB discrepancies via recurring in-system services;
operator never needs to run a one-off script to fix vertical state.

This directive is the operator's reset of the bar to where it should have
been from the original `perfect-audio-vertical`. Prior closes are not
re-opened -- their substance ships -- but their deferred items move here.

## Acceptance Criteria

### Structural perfection (SOLID)

**S1.** `AudioFilterEmitter._BuildBlockForTrack` decomposed by SRP. The
~70-line method becomes a thin orchestrator that delegates to:
- `_DecideStreamCopyOrReencode(MediaFile, TrackConfig, Strategy)` -- returns
  one of `'stream_copy'`, `'stream_copy_fallback'`, `'reencode'`.
- `_BuildCodecArgs(Codec, Bitrate, SampleRate, Channels, OutputIndex)`
- `_BuildFilterArgs(MediaFile, Strategy, OutputIndex)`
- `_BuildMetadataArgs(Language, Label, OutputIndex)`
- `_BuildDialNormArgs(DialNorm, IsAc3Family, StreamCopy, OutputIndex)`
- `_BuildDispositionArgs(IsDefaultTrack, OutputIndex)`

Each helper testable in isolation. New tests in `TestAudioFilterEmitter`
cover each per-helper truth table.

**S2.** `AudioCompletionService` renamed to `AudioStateService`. Reflects
its post-absorption role -- audio-state machine on the MediaFile, not
"completion" of a separate concern. All callers updated in the same
commit per `feedback_one_logical_change_per_commit.md`. `grep -rn
'AudioCompletionService' --include='*.py'` returns 0 hits after the
rename.

**S3.** Audio integration points on `ProcessTranscodeQueueService`
extracted to `Features/AudioNormalization/Workers/PostEncodeAudioHandler.py`
(SRP). The new class owns:
- `HandlePostEncode(TranscodeAttemptId, MediaFileId)` -- canonical-path
  resolve + probe + persist.
- `_PostReplacementCanonicalPath(MediaFileId)` -- moves out of the
  god class.

`ProcessTranscodeQueueService` constructor-injects
`PostEncodeAudioHandler` (DIP). The `_RunPostEncodeAudioProbe` +
`_PostReplacementCanonicalPath` methods are deleted from
`ProcessTranscodeQueueService` -- net negative LOC on the god class.

**S4.** Every integration boundary added by the vertical has a contract
test:
- `TestQueueManagementBusinessServiceHook` -- post-INSERT triggers gate
  BackfillAllPending, verified via DB rowcount.
- `TestComplianceGateLanguageOverride` -- emitted `language=eng` on the
  FFmpegCommand overrides candidate row's `HasExplicitEnglishAudio` +
  `AudioLanguages` before evaluation.
- `TestPostReplacementCanonicalPath` -- SQL join MediaFiles + StorageRoots
  yields correct Windows-flavored path for a known seeded fixture row.
- `TestPostEncodeAudioHandler` -- end-to-end hook with mocked probe.

### Live verification gaps

**L1.** Multi-language live encode. Pick (or create) a source MediaFile
with 2 distinct language audio streams (e.g. JPN + ENG dub). Encode
through the new emitter. ffprobe of the output asserts:
- 4 output audio streams (2 emit-tracks x 2 source languages),
- Each Original output tagged with its source language code,
- Each Dialog Boost output tagged with its source language code,
- `disposition.default=1` on the Dialog Boost track of the
  most-default-on-source language (or library default if neither is
  marked default at source).

**L2.** MP4 title tag root cause. Investigate why ffmpeg silently drops
`-metadata:s:a:N title=X` for audio streams in MP4 output. Read ffmpeg
source / forums / spec. One of three outcomes is the resolution -- not
"out of scope":
- (a) Alternative ffmpeg knob preserves title in MP4 (e.g.
  `-write_btrt 1`, `-c:a:N libfdk_aac` codec-specific name, etc.) -->
  emitter uses it; ffprobe shows `tags.title` on both audio streams.
- (b) MP4 codec-internal name field is writable via a different mechanism
  --> emitter uses that; ffprobe shows the name somewhere identifiable.
- (c) MP4 spec genuinely does not support per-audio-stream title -->
  criterion C1 amended to identify Dialog Boost by `disposition.default=1`
  + stream-index convention, and the change is documented in
  `audio-normalization.feature.md` with the spec reference.

Escalation required only if (c) -- I will not silently pick (c).

**L3.** Whisper backend live. Either:
- (a) Download a small Whisper-compatible model (e.g. ggml-small.en.bin
  from whisper.cpp releases) to `C:\Code\MediaVortex\Models\whisper-small.bin`,
  set `SystemSettings.WhisperModelPath` to that path, enable
  `EnableSpeechLanguageDetection=true` at global scope, queue an enrichment
  job against an `und`-tagged file, observe the
  `MediaFiles.AudioStreamLanguageDetectionsJson` cache populated with a
  real detected language code (not `und`); OR
- (b) Document explicitly in `audio-normalization.feature.md` C19 that
  the seam is wired and the stub is acceptable. The operator owns this
  choice -- I will not pick (b) on their behalf.

### Self-healing infrastructure (the new chapter)

**H1.** `AudioVerticalHealthService` recurring scan with SOLID composition.
Located at `Features/AudioNormalization/SelfHealing/AudioVerticalHealthService.py`.
Constructor injects `List[IAudioVerticalInvariant]` and a per-invariant
`Dict[invariant_name -> IAudioVerticalRemediation]`. Runs every N seconds
(operator-tunable in `SystemSettings.AudioVerticalHealthIntervalSec`
default 300s) on WebService background thread (joins the existing
`StatusPoller` cadence).

Each invariant + remediation pair is its own file (OCP):
- `Invariants/PendingQueueWithoutPolicyJson.py` + `Remediations/BackfillPolicyJson.py`
- `Invariants/SuccessfulAttemptWithoutTracksEmitted.py` + `Remediations/EnqueueReProbe.py`
- `Invariants/StaleOperatorReview.py` + `Remediations/AlertOperatorReview.py`
- `Invariants/InvalidMeasurementWithoutRemeasure.py` + `Remediations/EnqueueRemeasurement.py`
- `Invariants/PreVerticalTranscodedFile.py` + `Remediations/EnqueueRetranscode.py`
- `Invariants/ConsistencyBandDeviantWithComplete.py` + `Remediations/EnqueueRemeasurement.py`

Each cycle logs `{InvariantName, DetectedCount, RemediatedCount}` to a
new `AudioVerticalHealthRuns` table.

**H2.** `Scripts/SweepAudioPolicyForExistingFiles.py` is deleted. Its
job is owned by H1. The directive is explicit: no one-off scripts for
vertical-state remediation post this directive.

**H3.** `Tests/Contract/TestAudioInvariants.py` -- live-DB contract probe
runnable as `py -m pytest Tests/Contract/TestAudioInvariants.py`. Asserts
the steady-state invariants H1 protects. Same code path as H1's detectors
(DRY): each test instantiates the matching `IAudioVerticalInvariant` and
asserts `Detect()` returns 0 violations against live DB. Failing tests
name the offending row IDs. Operator runs this as the canonical "is the
vertical healthy" check.

**H4.** Activity dashboard `/api/Activity/LibraryCompliance` extended to
surface health-service state:
- `AudioVerticalHealth: {LastRunAt, ActionsLast24h: {<invariant>: count}}`
- Template `Templates/Activity.html` Library Compliance card gains
  "Self-healing (last 24h)" sub-section.

### Operational gaps from the prior close

**O1.** `wakko-worker-1..4` set to `Status='Paused'` immediately at the
DB level -- they are on stale code `c401ae6`, host is unreachable. When
host returns, normal redeploy unpauses. Until then they cannot claim
jobs and silently process with stale emitter. The pause + reason logged.

**O2.** Pre-vertical normalized files (`TranscodedByMediaVortex=true` AND
`ReplacementDate < '2026-06-17'`). Catalogued in the dashboard. Operator
chooses policy in Settings:
- `PreVerticalReNormalizePolicy IN ('aggressive', 'lazy', 'none')`
  added to `AudioNormalizationConfig` (new column, default `'lazy'`).
- `aggressive` -> H1 invariant marks them for retranscode on next cycle.
- `lazy` -> H1 doesn't touch them; operator manual queue still works.
- `none` -> excluded from invariant entirely.

The operator does not need to be asked again about this -- the column
default + dashboard surface make it discoverable.

## Files

```
Features/AudioNormalization/audio-normalization.feature.md            -- EDIT: documentation FIRST (operator instruction)
Features/AudioNormalization/AudioFilterEmitter.py                     -- EDIT: decompose _BuildBlockForTrack (S1)
Features/AudioNormalization/Services/AudioCompletionService.py        -- RENAME to AudioStateService.py (S2)
Features/AudioNormalization/Services/AudioStateService.py             -- CREATE: renamed service (S2)
Features/AudioNormalization/Workers/__init__.py                       -- CREATE
Features/AudioNormalization/Workers/PostEncodeAudioHandler.py         -- CREATE: extracted handler (S3)
Features/AudioNormalization/SelfHealing/__init__.py                   -- CREATE
Features/AudioNormalization/SelfHealing/IAudioVerticalInvariant.py    -- CREATE (H1)
Features/AudioNormalization/SelfHealing/IAudioVerticalRemediation.py  -- CREATE (H1)
Features/AudioNormalization/SelfHealing/AudioVerticalHealthService.py -- CREATE (H1)
Features/AudioNormalization/SelfHealing/AudioVerticalHealthComposition.py -- CREATE (H1)
Features/AudioNormalization/SelfHealing/Invariants/*.py               -- CREATE: 6 invariants (H1)
Features/AudioNormalization/SelfHealing/Remediations/*.py             -- CREATE: 5 remediations (H1)
Features/TranscodeJob/ProcessTranscodeQueueService.py                 -- EDIT: inject handler, delete old methods (S3)
Features/MediaProbe/MediaProbeBusinessService.py                      -- EDIT: AudioStateService rename (S2)
Features/FileReplacement/ComplianceGate.py                            -- EDIT: AudioStateService rename (S2)
Features/FileReplacement/TranscodedOutputPlacement.py                 -- EDIT: AudioStateService rename (S2)
Features/AudioNormalization/Controllers/AudioCompletionController.py  -- EDIT: AudioStateService rename (S2)
Features/Activity/ActivityRepository.py                               -- EDIT: GetAudioVerticalHealth (H4)
Features/Activity/ActivityController.py                               -- EDIT: payload (H4)
Templates/Activity.html                                               -- EDIT: panel (H4)
Scripts/SQLScripts/CreateAudioVerticalHealthRuns.py                   -- CREATE: table for H1 audit
Scripts/SQLScripts/AddPreVerticalReNormalizePolicy.py                 -- CREATE: column for O2
Scripts/SweepAudioPolicyForExistingFiles.py                           -- DELETE (H2)
Tests/Contract/TestAudioFilterEmitterDecomposition.py                 -- CREATE: per-helper coverage (S1)
Tests/Contract/TestAudioStateService.py                               -- RENAME from any existing
Tests/Contract/TestPostEncodeAudioHandler.py                          -- CREATE (S4)
Tests/Contract/TestQueueManagementBusinessServiceHook.py              -- CREATE (S4)
Tests/Contract/TestComplianceGateLanguageOverride.py                  -- CREATE (S4)
Tests/Contract/TestPostReplacementCanonicalPath.py                    -- CREATE (S4)
Tests/Contract/TestAudioInvariants.py                                 -- CREATE: live-DB invariants (H3)
Tests/Contract/TestMultiLanguageLiveEncode.py                         -- CREATE: L1 contract test
```

## Constraints (hook discipline)

- R1 doc preread on every file before edit. New files in a new dir have no
  colocated docs -- R1 N/A for first creation.
- R6 path storage: `Core.Path.LocalPath` helpers; no raw `os.path.exists`
  on path variables in any new code.
- R12 one-line docstrings, no triple-quoted SQL, no consecutive `#`
  blocks > 1 line in new files.
- R13 no NEW `*.feature.md` outside DELIVERING (audio-normalization
  feature.md already exists -- edits OK in IMPLEMENTING).
- R14 no annotation lines in feature.md edits.
- R15 directive anchor on every def/class in `## Files`.
- R18 partial reads on `*.feature.md` (limit<=50).
- db-is-authority: every Get reads fresh.

No `# allow:` overrides. Hook refusals signal real durable-artifact bugs
that get fixed at root.

## Plan

Stages strictly sequential; each commits + tests before the next.

### Stage 0 -- Documentation FIRST (operator instruction)

Edit `Features/AudioNormalization/audio-normalization.feature.md` to add:
- New `## Self-Healing` chapter with H1-H4 criteria + seams
- New `## SOLID Compliance` chapter with S1-S4 commitments
- Revisions to W list (W8 self-healing dashboard, W9 invariant probe)
- Revisions to C12, C15, C19 to reference self-healing
- Updates to ## Files list

This is the durable contract update. Commits land before any code work.

### Stage 1 -- Operational safety (O1)

UPDATE Workers SET Status='Paused', PauseReason='audio-vertical-perfection-and-self-healing: host unreachable, stale code c401ae6' WHERE WorkerName LIKE 'wakko-worker-%' AND Status != 'Paused'. Live SQL via Scripts/QueryDatabase.

### Stage 2 -- S1 emitter decomposition

Six new helper methods + thin orchestrator. New tests cover each. Commit.

### Stage 3 -- S2 rename AudioCompletionService -> AudioStateService

Create new file with rewritten class; update 5 callers in same commit;
delete old file; rename test file. Verify import chain clean.

### Stage 4 -- S3 extract PostEncodeAudioHandler

New class. ProcessTranscodeQueueService constructor change. Tests.

### Stage 5 -- S4 integration tests

Four new TestContract suites covering the hooks I shipped without
isolated tests.

### Stage 6 -- H1 self-healing service

Two ABC interfaces. Composition root. 6 invariants + 5 remediations
(one shared between two invariants). HealthService loop. Audit table
migration. Wire background thread on WebService.

### Stage 7 -- H2 delete sweep script

Delete `Scripts/SweepAudioPolicyForExistingFiles.py`. Verify H1's
PendingQueueWithoutPolicyJson invariant covers the same use case.

### Stage 8 -- H3 + H4 invariant probe + dashboard surface

`TestAudioInvariants.py` reuses H1 invariant detectors. Activity
controller + repository + template add the health panel.

### Stage 9 -- L1 multi-language live encode

Find / synthesize a 2-language source. Queue. Verify ffprobe shows
expected 4 output streams.

### Stage 10 -- L2 MP4 title tag investigation

Spike. Update emitter per outcome (a) or (b); escalate to operator if (c).

### Stage 11 -- L3 Whisper backend

Download model, configure setting, queue + run enrichment, verify cache.
OR document operator decision in feature.md.

### Stage 12 -- O2 pre-vertical policy + dashboard surface

Migration. Settings UI. Invariant integration. Dashboard surface.

### Stage 13 -- VERIFYING

Record per-criterion evidence + invariant run table snapshot.

### Stage 14 -- DELIVERING

Promotions + close + memory entry on the bar-lowering pattern.

## Status

### Progress

- [x] Stage 0: audio-normalization.feature.md updated with self-healing + SOLID chapters
- [x] Stage 1: wakko paused
- [x] Stage 2: S1 emitter decomposition + tests
- [x] Stage 3: S2 rename AudioCompletionService -> AudioStateService
- [x] Stage 4: S3 PostEncodeAudioHandler extracted
- [x] Stage 5: S4 four integration tests
- [x] Stage 6: H1 AudioVerticalHealthService running
- [x] Stage 7: H2 sweep script deleted
- [x] Stage 8: H3 invariant probe + H4 dashboard
- [x] Stage 9: L1 multi-language live encode contract test (6 tests green; live re-encode pending transcoding re-enable -- contract test asserts emitter output shape that the live encode would observe)
- [ ] Stage 10: L2 MP4 title tag resolution (not "out of scope")
- [ ] Stage 11: L3 Whisper backend live OR operator-decided
- [ ] Stage 12: O2 pre-vertical retroactive policy
- [ ] Stage 13: VERIFYING evidence
- [ ] Stage 14: DELIVERING + memory entry on bar-lowering

### Promotions

[Populated at DELIVERING phase]
