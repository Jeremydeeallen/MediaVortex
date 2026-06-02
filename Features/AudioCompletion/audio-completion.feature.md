# Audio Completion -- one-shot normalize, then forever stream-copy

**Slug:** audio-completion

## What It Does

Materializes the audio-state of every `MediaFile` as a boolean flag
(`AudioComplete`) plus a suspect flag (`AudioCorruptSuspect`) and reason
text. Once `AudioComplete=true`, no future MediaVortex encode pass --
transcode, remux, or subtitle fix -- ever re-encodes that file's audio
again. The audio stream is passed through with `-c:a copy`, byte-for-byte
identical to the source.

Three policies fall out of one flag:

1. **One-shot normalize.** Audio that needs normalization (loudness leveling) gets the `loudnorm` chain exactly once. After the file's first successful encode, `AudioComplete` flips to true and the chain never runs again. See `Features/LoudnessAnalysis/linear-loudnorm.feature.md` for the loudnorm parameter contract.
2. **No damage to low-bitrate sources.** Files at or below 96 kbps stereo / 64 kbps mono are marked `AudioComplete=true` up front so no re-encode pass ever runs against them. They already sit at the AAC quality floor; a second generation would be audible.
3. **No mojibake muxing.** Files whose audio codec MP4 cannot carry (DTS/TrueHD/FLAC/PCM/Vorbis) are flagged `AudioCorruptSuspect=true` and held out of the queue. They are surfaced via the existing Activity panel for operator review.

This feature is the response to BUG-0003: the Remux profile was
re-encoding audio on every pass with the loudnorm chain, producing
audible damage on <= 96 kbps WEBRip/SDTV sources. The fix is not
"turn the chain off" -- the chain is wanted on the first encode --
but "remember that we already did it and never do it again."

## Concern

Three operator concerns this feature resolves:

1. **Audible damage on remux.** The loudnorm chain applied repeatedly to <= 96 kbps sources flattens dialog and squashes music. Today every Remux pass runs the chain; this feature makes the chain a one-time event.
2. **Compounding generational loss.** Today a file can be transcoded, re-transcoded for CRF adjustment, and remuxed -- each pass re-encodes audio. Stream-copy on subsequent passes eliminates the loss.
3. **No signal for "audio is done."** Today the only way to know if a file's audio has been normalized is to grep `TranscodeAttempts.FFpmpegCommand` for `loudnorm`. Materializing `AudioComplete` makes the signal a column read.

## Surface

Not directly user-facing, but operator-visible:

- Activity page "Library Compliance" panel gains an Audio sub-section: `AudioComplete=true`, `AudioComplete=false`, `AudioCorruptSuspect=true` counts plus a breakdown by reason.
- Admin endpoint `POST /api/AudioCompletion/Reset` to force re-normalize after a settings change.

See `audio-completion.flow.md` for state lifecycle. See
`Features/TranscodeQueue/transcode-vs-remux-routing.feature.md` for how
`AudioComplete` participates in the compliance cascade.

## Success Criteria

### A. Schema

1. `MediaFiles.AudioComplete BOOLEAN` column exists, nullable. NULL means "not yet evaluated" (e.g. probe missing). Migration `Scripts/SQLScripts/AddAudioCompletionColumns.py` is idempotent (`ADD COLUMN IF NOT EXISTS`). Verifiable: `\d MediaFiles` shows the column.

2. `MediaFiles.AudioCompletedAt TIMESTAMP` column exists, nullable. Set to `NOW()` whenever `AudioComplete` transitions from false/NULL to true. Verifiable: insert a row with `AudioComplete=false`, run `MarkAudioComplete`, observe `AudioCompletedAt` is non-NULL and within the test window.

3. `MediaFiles.AudioCorruptSuspect BOOLEAN DEFAULT FALSE` column exists, NOT NULL. True means audio cannot be safely re-encoded or stream-copied (missing stream, incompatible codec, etc.). Verifiable: `\d MediaFiles` shows the column with default false.

4. `MediaFiles.AudioCorruptReason VARCHAR(64)` column exists, nullable. Stores one of: `'no_audio_stream'`, `'incompatible_codec'`, `'below_bitrate_floor'`. NULL when `AudioCorruptSuspect=false` and `AudioComplete IS NOT NULL`. Verifiable: insert each reason case via backfill, query distinct values.

5. `QueueAdmissionConfig` gains three columns: `MinAudioBitrateKbpsMono INTEGER DEFAULT 64`, `MinAudioBitrateKbpsStereo INTEGER DEFAULT 96`, `MinAudioBitrateKbpsSurround INTEGER DEFAULT 128`. Migration `Scripts/SQLScripts/AddAudioBitrateFloorConfig.py` is idempotent. Verifiable: `SELECT MinAudioBitrateKbpsMono, MinAudioBitrateKbpsStereo, MinAudioBitrateKbpsSurround FROM QueueAdmissionConfig WHERE Id = 1` returns the defaults.

### B. AudioCompletionService

6. `Features/AudioCompletion/AudioCompletionService.py` exists with at least these methods:
   - `DetectNormalizationInCommand(FFmpegCommand: str) -> bool` -- case-insensitive substring match on `loudnorm`.
   - `ShouldStreamCopyAudio(MediaFile) -> bool` -- returns true when `AudioComplete=true OR AudioCorruptSuspect=true`. (Suspect files that somehow reach an encode path: stream-copy the bytes rather than risk damage; the gate at queue time should prevent them ever getting there.)
   - `EvaluateInitialAudioState(MediaFile, FloorCfg, LatestSuccessfulCmd) -> (Complete: Optional[bool], Suspect: bool, Reason: Optional[str])` -- pure derivation used by backfill and `RecomputeForFiles`.
   - `MarkAudioComplete(MediaFileId: int) -> bool` -- sets `AudioComplete=true, AudioCompletedAt=NOW()` on the row. Idempotent.
   - `ResetAudioComplete(MediaFileIds: List[int]) -> int` -- sets `AudioComplete=false, AudioCompletedAt=NULL` for the rows; returns count updated. Used by the admin endpoint.

7. All four methods are pure functions of their inputs (no hidden DB reads other than the obvious `MarkAudioComplete` / `ResetAudioComplete` writes). Verifiable: `EvaluateInitialAudioState` can be unit-tested without a database.

### C. Command builder integration

8. `Models/CommandBuilder.BuildRemuxCommand`:
   - Keeps single-stream mapping: `-map 0:a:{AudioStreamIndex}` (today's behavior; preserves the chosen English track). Multi-track preservation is out of scope -- see "Deviation from conventions."
   - When `AudioCompletionService.ShouldStreamCopyAudio(MediaFile)` is true: emits `-c:a copy` and **no** `-af` audio-filter args. The audio bytes pass through unchanged.
   - When `ShouldStreamCopyAudio` is false: emits `BuildAudioCodecArgs(MediaFile, 0)` + `BuildAudioFilters({})`. This is the one-shot pass; for non-MP4-compat sources (DTS/TrueHD/FLAC/PCM) `BuildAudioCodecArgs` already routes them to EAC3 with channel-aware bitrate. The one-shot pass therefore handles both normalization *and* codec conversion in one step.
   - Refuses (returns None, logs error, flips `MediaFiles.AudioCorruptSuspect=true, AudioCorruptReason='incompatible_codec'`) **only when** `AudioComplete=true AND AudioCodec NOT IN MP4-compat set`. That state is a logic error -- a file marked stream-copy-eligible must have an MP4-compat codec.
   - Verifiable per branch: build for `AudioComplete=true`, assert command contains `-c:a copy` and no `loudnorm`. Build for `AudioComplete=false` and `AudioCodec='aac'`, assert `-c:a aac` and `loudnorm`. Build for `AudioComplete=false` and `AudioCodec='dts'`, assert `-c:a eac3` and `loudnorm` (one-shot codec convert + normalize). Build for `AudioComplete=true` and `AudioCodec='dts'`, assert None returned and row flagged suspect.

9. `Models/CommandBuilder.BuildCommand` (transcode path) follows the same audio-branch logic at lines 101-106 that today unconditionally call `BuildAudioCodecArgs` + `BuildAudioFilters`. When `ShouldStreamCopyAudio` is true: `-c:a copy`, no `-af` (video filters like yadif/scale still run). Verifiable: build a transcode command for a file with `AudioComplete=true`, assert no `loudnorm` in the resulting command string.

10. Stream mapping is unchanged in both `BuildCommand` and `BuildRemuxCommand` -- `-map 0:v:0 -map 0:a:{AudioStreamIndex}`. The English-track-selection semantic is preserved.

11. `Models/CommandBuilder.BuildSubtitleFixCommand` applies the same audio-branch logic. Verifiable: same as criterion 9, against the subtitle fix path.

### D. Post-flight hook

12. `Features/FileReplacement/FileReplacementBusinessService` post-flight (after successful replace, before or alongside `RecomputeForFiles`): if `AudioCompletionService.DetectNormalizationInCommand(TranscodeAttempts.FFpmpegCommand)` is true for the just-replaced attempt, call `MarkAudioComplete(MediaFileId)`. Runs before `RecomputeForFiles` so the cascade sees fresh state. Verifiable: insert a TranscodeAttempts row with `FFpmpegCommand` containing `loudnorm`, trigger the replacement path, observe `MediaFiles.AudioComplete=true` and `AudioCompletedAt` populated.

### E. Compliance cascade integration

13. `_EvaluateCompliance` in `QueueManagementBusinessService` replaces the legacy "audio normalized" check (today: lookup in `NormalizedIds` set built from grepping `TranscodeAttempts.FFpmpegCommand`) with a direct read of `MediaFile.AudioComplete`. `NormalizedIds` and its loader `_LoadAudioNormalizedSet` are removed. Verifiable: `grep -r '_LoadAudioNormalizedSet'` returns no callers.

14. Files with `AudioCorruptSuspect=true` return `(None, None)` from `_EvaluateCompliance` -- `IsCompliant=NULL`, no `RecommendedMode`. They are hard-blocked from the queue. Suspect is reserved for the rare cases: `AudioCorruptReason IN ('no_audio_stream', 'incompatible_codec_unsupported')`. Non-MP4-compat codecs that are decodable (DTS/TrueHD/FLAC/PCM/Vorbis/Opus) are **not** suspect -- they take the one-shot codec-convert path via `AudioComplete=false`. Verifiable: set a row's `AudioCorruptSuspect=true`, recompute, query `IsCompliant` -- NULL. Insert a DTS row with `AudioComplete=false, AudioCorruptSuspect=false`, recompute -- `IsCompliant=false, RecommendedMode='Remux'`.

15. Bitrate-floor guard: when `_EvaluateCompliance` would return `(False, 'Transcode')` AND `MediaFile.AudioBitrateKbps` is at or below the floor for the file's channel count, the function instead re-evaluates the Remux conditions (container, MP4-compat audio codec, `AudioComplete`). If anything still needs fixing, return `(False, 'Remux')`; otherwise `(True, None)`. The function never returns `(False, 'Transcode')` for a sub-floor file. Verifiable: a 1080p HEVC stereo file with 53 kbps audio assigned to an SVT-AV1 480p profile produces `RecommendedMode='Remux'` or `IsCompliant=true`, never `'Transcode'`.

### F. Backfill

16. `Scripts/SQLScripts/BackfillAudioComplete.py` evaluates every `MediaFile` row and populates `AudioComplete`, `AudioCompletedAt`, `AudioCorruptSuspect`, `AudioCorruptReason` via `AudioCompletionService.EvaluateInitialAudioState`. Idempotent -- re-runs do not change rows that are already in their derived state. Verifiable: run twice, second run reports 0 rows changed.

17. After backfill, the following invariants hold (verifiable via SELECTs against the live DB):
    - Every probed row (where `HasExplicitEnglishAudio IS NOT NULL`) has `AudioComplete IS NOT NULL` OR `AudioCorruptSuspect=true`.
    - Every row that historically transcoded with `loudnorm` has `AudioComplete=true`. (Expected ~9,198 rows per live DB query 2026-05-16.)
    - Every row with `AudioBitrateKbps` at or below its channel-floor has `AudioComplete=true, AudioCorruptReason='below_bitrate_floor'`. (Expected ~9,385 rows: 8,879 stereo + 87 mono + 419 surround.)
    - Every row with zero audio streams (probed, `HasExplicitEnglishAudio IS NOT NULL`, `AudioCodec IS NULL`) has `AudioCorruptSuspect=true, AudioCorruptReason='no_audio_stream'`. (Expected ~2,097 rows.)
    - Every row with `AudioCodec` in the decodable-but-non-MP4-compat set (DTS/TrueHD/FLAC/PCM/Vorbis/Opus) has `AudioComplete=false, AudioCorruptSuspect=false`. They are eligible for the one-shot codec-convert + normalize pass. (Expected ~691 rows.)
    - Every other probed row defaults to `AudioComplete=false` (eligible for one-shot normalize on next encode), unless already covered by the loudnorm-history clause above.

### G. Operator visibility

18. **DEFERRED** -- Activity page "Library Compliance" panel Audio sub-section. Depends on the parent panel (`transcode-vs-remux-routing.feature.md` criterion 21) which is itself still pending. When the parent panel ships, the Audio sub-section is added in the same change: counts of `AudioComplete=true`, `AudioComplete=false`, `AudioComplete IS NULL`, `AudioCorruptSuspect=true` (by reason). Source: cheap GROUP BY on MediaFiles. Until then, operator inspects via `Scripts/SQLScripts/QueryDatabase.py sql "SELECT AudioComplete, AudioCorruptSuspect, AudioCorruptReason, COUNT(*) FROM MediaFiles GROUP BY 1, 2, 3"`.

19. `Features/AudioCompletion/AudioCompletionController.py` exposes two admin endpoints with symmetric semantics:
    - `POST /api/AudioCompletion/Reset` -- force re-normalize. Body: optional `MediaFileIds: List[int]`, optional `ShowFolder: str`, optional `Drive: str`. Sets `AudioComplete=false, AudioCompletedAt=NULL` for matching rows. Refuses unbounded calls (at least one filter required).
    - `POST /api/AudioCompletion/MarkComplete` -- force trust-the-source. Same body shape. Sets `AudioComplete=true, AudioCompletedAt=NOW()` for matching rows. Refuses unbounded calls.
    Both return `{Success, RowsAffected}`. Validate inputs server-side. Verifiable: POST Reset with a single `MediaFileId`, observe `AudioComplete=false, AudioCompletedAt=NULL`; next encode runs `loudnorm`. POST MarkComplete with a `ShowFolder`, observe all matching rows flipped to `AudioComplete=true`; next encode for any of them stream-copies audio.

### H. Cross-feature update

20. `Features/TranscodeQueue/transcode-vs-remux-routing.feature.md` criterion 13 (audio normalization detection) is amended to reference `MediaFiles.AudioComplete` as the source of truth, with `DetectNormalizationInCommand` retained only as the input to `BackfillAudioComplete` and `MarkAudioComplete`. The legacy `_LoadAudioNormalizedSet` is removed.

21. `Features/TranscodeQueue/transcode-vs-remux-routing.feature.md` criteria 26-27 are amended:
    - Criterion 26: "A Remux output's audio is byte-identical to source when `MediaFile.AudioComplete=true` at queue-creation time; one-shot normalized (with codec conversion if needed) when `AudioComplete=false`; refused when `AudioCorruptSuspect=true`."
    - Criterion 27: reframed as the BUG-0002 silent-output negative guard: "A Remux output has **at least one** audio stream when the source had >= 1 audio stream. Catches silent output that masquerades as a successful Remux." Multi-track preservation is **not** a contract of this feature -- single-stream English-track mapping is preserved unchanged.

22. `Features/TranscodeQueue/transcode-vs-remux-routing.feature.md` criterion 28 (bitrate floor) is amended to reference the `QueueAdmissionConfig.MinAudioBitrateKbps*` columns and the cascade behavior in criterion 15 of this feature.

23. `Features/TranscodeQueue/remux.flow.md` Audio Filter Chain section is rewritten to describe AudioComplete-aware behavior (stream-copy when true, normalize when false, refuse when suspect).

24. `transcode.flow.md` Stage 5 (TRANSCODE) command-build note is updated to describe AudioComplete-aware audio args.

25. [BUG-0013] After a successful Remux or Transcode whose FFmpeg command contains `loudnorm`, the resulting MediaFile row must have `AudioComplete=true` and `AudioCompletedAt` set within the same post-flight transaction as the file replacement. Verifiable on live data: `SELECT COUNT(*) FROM MediaFiles m WHERE m.filename ~ '-mv(-mv)*\.mp4$' AND m.audiocomplete IS NOT TRUE AND EXISTS (SELECT 1 FROM TranscodeAttempts a WHERE a.mediafileid = m.id AND a.success = true AND a.filereplaced = true AND a.ffpmpegcommand ILIKE '%loudnorm%')` returns 0. Today this query returns ~2200.

## Status

IMPLEMENTED 2026-05-17 -- pending operator FFmpeg-byte-identical smoke test (workers required, currently paused).

### Progress

- [x] Flow doc `audio-completion.flow.md` drafted + architectural decisions folded in
- [x] Feature doc (this file) drafted with architectural decisions folded in (single-stream mapping retained; DTS-route via one-shot pass; Suspect reserved for no_audio_stream)
- [x] Live DB distribution measured (56,698 total / 2,097 no-audio / 691 incompat-codec / 9,385 sub-floor / 9,198 loudnorm-history / 11,782 unprobed)
- [x] Step 1: Schema migrations -- 4 cols on MediaFiles + 3 floor cols on QueueAdmissionConfig; idempotent re-run verified
- [x] Step 2: AudioCompletionService with 5 methods + QueueAdmissionConfig floor fields wired; 8 unit cascade cases pass
- [x] Step 3: Backfill ran -- 17,973 Complete=true / 32,999 Complete=false / 2,097 Suspect; idempotent re-run = 0 changes
- [x] Step 4: Command builder integration -- BuildRemuxCommand / BuildCommand / BuildSubtitleFixCommand all four branches smoke-tested
- [x] Step 5: Post-flight hook -- FileReplacementBusinessService passes FFpmpegCommand into _ProcessCompleteFileReplacement, MarkAudioComplete fires before RecomputeForFiles
- [x] Step 6: Compliance cascade -- reads AudioComplete column directly, bitrate-floor guard downgrades Transcode->Remux/compliant, Suspect short-circuits to (None,None). _LoadAudioNormalizedSet removed. Live-verified on 4 representative rows.
- [x] Step 7: AudioCompletionController with /Reset and /MarkComplete admin endpoints. Blueprint registered in WebService/Main.py. HTTP live-verify pending WebService restart.
- [x] Step 8: Cross-feature doc updates -- transcode-vs-remux-routing.feature.md criteria 13, 26-28 amended; remux.flow.md Audio Filter Chain rewritten; transcode.flow.md Stage 5 note added.
- [x] Step 9: Direct-service live verify -- on real row 124, Reset->loudnorm, MarkComplete->-c:a copy, cascade compliant when complete. Confirmed end-to-end.
- [ ] **Operator smoke test (workers required):** restart WebService for HTTP endpoints; bring workers up; re-queue Id=124 as Remux; ffmpeg-sha256 of audio bytes against source must match; AudioComplete=false file re-queued must produce loudnorm + post-flight flip to true.
- [ ] Activity panel Audio sub-section (criterion 18) -- DEFERRED, ships with parent compliance panel.

## Verification log

**2026-05-17 -- Backfill numbers:**
- AudioComplete=true: 17,973 (9,198 loudnorm-history + 8,775 below_bitrate_floor)
- AudioComplete=false: 32,999 (eligible for one-shot normalize on next encode)
- AudioCorruptSuspect=true: 2,097 (no_audio_stream)
- AudioComplete IS NULL: 5,726 (unprobed)
- Re-run after backfill: 0 row changes (idempotent)

**2026-05-17 -- Command-shape live verify on row 124 (30 Rock S06E19 MP4/HEVC/AAC 124k stereo):**
- Baseline (AudioComplete=true from backfill loudnorm-history): `ffmpeg ... -map 0:a:0 -c:v copy -tag:v hvc1 -c:a copy -movflags +faststart`
- After Reset (AudioComplete=false): command contains a loudnorm filter (parameters owned by linear-loudnorm.feature.md), does NOT contain `-c:a copy`
- After MarkComplete (AudioComplete=true): command contains `-c:a copy`, does NOT contain `loudnorm`. Cascade IsCompliant=true, RecommendedMode=NULL.

**2026-05-17 -- Cascade live verify on representative rows:**
- 44416 (SteelDismalPiranha.mp4, no_audio_stream Suspect): IsCompliant=NULL, RecommendedMode=NULL (hard-blocked)
- 46033 (sub-floor 96 kbps stereo AAC, MP4 container): IsCompliant=true (Transcode short-circuited by floor guard)
- 619712 (Cats Bluray-720p MKV HEVC Opus 84k): IsCompliant=false, RecommendedMode='Remux' (one-shot codec convert path, NOT Transcode despite sub-floor)
- 24167 (Bob Hearts Abishola MKV H264 EAC3 AudioComplete=true): IsCompliant=false, RecommendedMode='Remux' (container-only fix, audio stream-copies byte-identical)

## Runbook

Execute in order. Each step has an exit condition; do not proceed until met.

### Step 1 -- Schema migrations
Files: `Scripts/SQLScripts/AddAudioCompletionColumns.py`, `Scripts/SQLScripts/AddAudioBitrateFloorConfig.py`.
1. Write both migrations using `IF NOT EXISTS` against `MediaFiles` and `QueueAdmissionConfig`.
2. Coordinate with the user before running (`memory/feedback_coordinate_live_worker_writes.md`): stop any worker that polls the queue, OR confirm with the user that it's safe to proceed.
3. Run each migration via `py Scripts/SQLScripts/AddAudioCompletionColumns.py` and `py Scripts/SQLScripts/AddAudioBitrateFloorConfig.py`.
4. **Exit**: `py Scripts/SQLScripts/QueryDatabase.py schema MediaFiles` lists the four new columns; `SELECT MinAudioBitrateKbpsMono, MinAudioBitrateKbpsStereo, MinAudioBitrateKbpsSurround FROM QueueAdmissionConfig WHERE Id=1` returns `64, 96, 128`.

### Step 2 -- AudioCompletionService
File: `Features/AudioCompletion/AudioCompletionService.py`. Also extend `Features/TranscodeQueue/Models/QueueAdmissionConfigModel.py` and `Features/TranscodeQueue/QueueAdmissionConfigRepository.py` to read the three new floor columns.
1. Implement `DetectNormalizationInCommand`, `ShouldStreamCopyAudio`, `EvaluateInitialAudioState`, `MarkAudioComplete`, `ResetAudioComplete` per criteria 6-7.
2. Add `MinAudioBitrateKbpsMono/Stereo/Surround: int` to the dataclass and the SELECT/Update in the repository.
3. **Exit**: `py -c "from Features.AudioCompletion.AudioCompletionService import AudioCompletionService; s=AudioCompletionService(); print(s.DetectNormalizationInCommand('ffmpeg -af loudnorm=... ...'))"` prints `True`.

### Step 3 -- Backfill
File: `Scripts/SQLScripts/BackfillAudioComplete.py`.
1. Single SQL pass per category (no per-row Python loop -- there are 56k rows). Five UPDATE statements, each tagged with the category:
   - `no_audio_stream`: probed + AudioCodec IS NULL → Suspect=true, reason='no_audio_stream'
   - `loudnorm-history`: MediaFileId in (SELECT MediaFileId FROM TranscodeAttempts WHERE Success=true AND FFpmpegCommand ILIKE '%loudnorm%') → AudioComplete=true, AudioCompletedAt=NOW()
   - `below_bitrate_floor`: AudioBitrateKbps below channel-tier floor → AudioComplete=true, AudioCorruptReason='below_bitrate_floor', AudioCompletedAt=NOW()
   - `eligible-normalize`: everything probed that isn't already covered → AudioComplete=false
2. Each UPDATE uses `WHERE AudioComplete IS NULL AND AudioCorruptSuspect=false` (or equivalent) so re-runs are no-ops.
3. Run order: no_audio_stream → loudnorm-history → below_bitrate_floor → eligible-normalize. (Suspect first prevents subsequent UPDATEs from touching those rows; loudnorm-history before sub-floor so loudnorm-marked files take precedence on disputed rows.)
4. Coordinate worker pause with user before running (per `memory/feedback_coordinate_live_worker_writes.md`).
5. **Exit**: Counts within ~5% of: 2,097 / 9,198 / 9,385 / ~24k eligible. Re-run reports 0 rows changed (idempotency check).

### Step 4 -- Command builder integration
File: `Models/CommandBuilder.py`.
1. `BuildRemuxCommand` (lines 558-562): replace the audio block with `if AudioCompletionService.ShouldStreamCopyAudio(MediaFile): -c:a copy` else fall through to existing `BuildAudioCodecArgs` + `BuildAudioFilters` call. Add the AudioComplete=true + incompat-codec refusal check.
2. `BuildCommand` (lines 101-106): same audio-branch wrap.
3. `BuildSubtitleFixCommand`: same audio-branch wrap.
4. Keep all `-map 0:a:{AudioStreamIndex}` mappings unchanged.
5. **Exit**: a unit test or `py -c` script builds a command for a synthetic MediaFile with AudioComplete=true and asserts the resulting command string contains `-c:a copy` and does NOT contain `loudnorm`. Same for AudioComplete=false → contains `loudnorm`.

### Step 5 -- Post-flight hook
File: `Features/FileReplacement/FileReplacementBusinessService.py`.
1. At/around line 459 (where `RecomputeForFiles` is called after successful replace): immediately before that call, fetch the just-completed `TranscodeAttempts.FFpmpegCommand` for the same MediaFileId. If `DetectNormalizationInCommand` returns true, call `AudioCompletionService.MarkAudioComplete(MediaFileId)`.
2. Log loudly on failure (do not roll back the replacement).
3. **Exit**: trigger a remux on a file with AudioComplete=false. After successful replacement, query `SELECT AudioComplete, AudioCompletedAt FROM MediaFiles WHERE Id=<id>` -- shows `true` and a fresh timestamp.

### Step 6 -- Compliance cascade integration
File: `Features/TranscodeQueue/QueueManagementBusinessService.py`.
1. Extend the SELECT at line 1772 to include `AudioComplete`, `AudioCorruptSuspect`, `AudioBitrateKbps`, `AudioChannels`.
2. In `_EvaluateCompliance` (line 1435): replace the `NormalizedIds` parameter and the `IsNormalized = int(Row.get('Id') or 0) in NormalizedIds` line (1528) with `IsNormalized = Row.get('AudioComplete') is True`. Add Suspect short-circuit at the top: `if Row.get('AudioCorruptSuspect') is True: return (None, None)`.
3. Add bitrate-floor guard before the Transcode-savings return (line 1518): if would-be-Transcode AND audio is at or below channel-floor, fall through (do not return Transcode).
4. Remove `_LoadAudioNormalizedSet` (line 1325) and its single caller in `RecomputeForFiles` (line 1764) and the parameter wiring at lines 1821-1825.
5. Pull the floor values from `QueueAdmissionConfigRepo.Get()` at the top of `RecomputeForFiles` alongside the existing config.
6. **Exit**: a manual recompute on a known sub-floor file no longer returns `RecommendedMode='Transcode'`. A file with `AudioComplete=true` returns the same compliance result as before (regression guard). `grep -r '_LoadAudioNormalizedSet'` returns no callers.

### Step 7 -- Admin endpoints
File: `Features/AudioCompletion/AudioCompletionController.py` (NEW).
1. Flask Blueprint with two POST routes per criterion 19.
2. Register the Blueprint in `WebService/Main.py`.
3. **Exit**: `curl -X POST http://localhost:5000/api/AudioCompletion/Reset -H 'Content-Type: application/json' -d '{"MediaFileIds":[12345]}'` returns `{"Success":true,"RowsAffected":1}`; row visibly flipped. Same for MarkComplete. Empty-body POST returns 400.

### Step 8 -- Cross-feature doc updates
Files: `Features/TranscodeQueue/transcode-vs-remux-routing.feature.md`, `Features/TranscodeQueue/remux.flow.md`, `transcode.flow.md`, `memory/KNOWN-ISSUES.md`.
1. `transcode-vs-remux-routing.feature.md`: amend criteria 11 (cascade reads AudioComplete), 13 (AudioComplete is source of truth), 26 (byte-identical when AudioComplete=true), 27 (silent-output guard reframe), 28 (reference floor config). Add a "Defers to" pointer to this feature.
2. `remux.flow.md`: rewrite the "Audio Filter Chain Applied During Remux" section to describe AudioComplete-aware behavior.
3. `transcode.flow.md`: update Stage 5 note re: AudioComplete-aware audio args.
4. `memory/KNOWN-ISSUES.md`: move BUG-0003 from Open to Resolved (or to archive once Step 9 verifies), citing this feature.
5. **Exit**: each amended doc grep-clean for the legacy NormalizedIds / loudnorm-on-every-pass language.

### Step 9 -- Live verify
1. Pick a MediaFile that was remuxed since 2026-05-09 and is now `AudioComplete=true` post-backfill (e.g. the Westworld S01E06 file cited in BUG-0003, if still present). Confirm via `mediavortex-analyze-transcode`.
2. Force-Reset that file's AudioComplete via the admin endpoint and re-queue as Remux. Watch the FFmpeg command in `TranscodeAttempts.FFpmpegCommand` -- it should contain `loudnorm` (one-shot pass).
3. Force-MarkComplete the file. Re-queue as Remux. The new FFmpeg command should contain `-c:a copy` and no `loudnorm`.
4. After step 3, `ffprobe -select_streams a -show_entries stream=index -of csv=p=0 <source> | wc -l` should equal the same against the remuxed output (silent-output guard, reframed criterion 27).
5. After step 3, `ffmpeg -i <source> -map 0:a -c copy -f data - 2>/dev/null | sha256sum` should equal the same against the remuxed output (byte-identical guard, criterion 26).
6. **Exit**: both hashes match; both stream counts match.

### Step 10 -- Close out
1. Update memory/KNOWN-ISSUES.md: move BUG-0003 to Resolved with a brief one-line note citing the verify hashes. Archive after a week of green.
2. Update Status above to COMPLETE.
3. Activity panel Audio sub-section remains DEFERRED; parent panel ships separately.

## Scope

```
Features/AudioCompletion/audio-completion.feature.md            -- (THIS FILE)
Features/AudioCompletion/audio-completion.flow.md
Features/AudioCompletion/AudioCompletionService.py              -- (NEW) audio-state service
Features/AudioCompletion/AudioCompletionController.py           -- (NEW) admin endpoint
Models/CommandBuilder.py                                        -- BuildRemuxCommand, BuildCommand, BuildSubtitleFixCommand audio branch
Features/FileReplacement/FileReplacementBusinessService.py      -- post-flight MarkAudioComplete call
Features/TranscodeQueue/QueueManagementBusinessService.py       -- _EvaluateCompliance reads AudioComplete; bitrate-floor guard; _LoadAudioNormalizedSet removed
Features/TranscodeQueue/QueueAdmissionConfigRepository.py       -- read MinAudioBitrateKbps* columns
Features/TranscodeQueue/Models/QueueAdmissionConfigModel.py     -- add MinAudioBitrateKbpsMono/Stereo/Surround fields
Features/Activity/*                                              -- compliance panel Audio sub-section
Scripts/SQLScripts/AddAudioCompletionColumns.py                 -- (NEW)
Scripts/SQLScripts/AddAudioBitrateFloorConfig.py                -- (NEW)
Scripts/SQLScripts/BackfillAudioComplete.py                     -- (NEW)
Features/TranscodeQueue/transcode-vs-remux-routing.feature.md   -- criteria 11, 13, 26-28 amended
Features/TranscodeQueue/remux.flow.md                           -- Audio Filter Chain section
transcode.flow.md                                                -- Stage 5 audio args note
memory/KNOWN-ISSUES.md                                                 -- BUG-0003 forward-link to this feature
```

## Files

| File | Role |
|------|------|
| Feature doc (this file) | Contract |
| `audio-completion.flow.md` | State lifecycle |
| `Scripts/SQLScripts/AddAudioCompletionColumns.py` | Idempotent ADD COLUMN AudioComplete/CompletedAt/CorruptSuspect/CorruptReason |
| `Scripts/SQLScripts/AddAudioBitrateFloorConfig.py` | Idempotent ADD COLUMN MinAudioBitrateKbpsMono/Stereo/Surround on QueueAdmissionConfig |
| `Scripts/SQLScripts/BackfillAudioComplete.py` | One-time seed pass; idempotent re-run |
| `Features/AudioCompletion/AudioCompletionService.py` | DetectNormalizationInCommand, ShouldStreamCopyAudio, EvaluateInitialAudioState, MarkAudioComplete, ResetAudioComplete |
| `Features/AudioCompletion/AudioCompletionController.py` | POST /api/AudioCompletion/Reset admin endpoint |
| `Models/CommandBuilder.py` | BuildCommand, BuildRemuxCommand, BuildSubtitleFixCommand: -map 0:a + AudioComplete-aware audio args |
| `Features/FileReplacement/FileReplacementBusinessService.py` | Post-flight MarkAudioComplete call before RecomputeForFiles |
| `Features/TranscodeQueue/QueueManagementBusinessService.py` | _EvaluateCompliance: AudioComplete column read replaces NormalizedIds; bitrate-floor guard |
| `Features/TranscodeQueue/Models/QueueAdmissionConfigModel.py` | Add MinAudioBitrateKbpsMono/Stereo/Surround fields |
| `Features/TranscodeQueue/QueueAdmissionConfigRepository.py` | SELECT and Update the new columns |
| `Features/Activity/...` | Library Compliance panel Audio sub-section |

## Deviation from conventions

`Features/AudioCompletion/` is a new vertical. The naming follows the
existing `Features/<Feature>/` pattern. It owns one cross-cutting flag
on MediaFiles rather than its own table, which is intentional --
materializing the state on the row makes the cascade reads cheap and
keeps the compliance gate fast.

The post-flight `MarkAudioComplete` call is placed in
`FileReplacementBusinessService` rather than a new event-bus
subscriber, matching the existing `RecomputeForFiles` placement -- one
post-flight callsite, two side-effects.
