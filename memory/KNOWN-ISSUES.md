# Known Issues

## Active

### disposition

### [BUG-0079] Requeue disposition never enqueues a new TranscodeQueue row; .inprogress orphans on disk
**Date:** 2026-07-02 | **Area:** disposition / transcode-lifecycle

**What breaks:** When VMAF is below the auto-replace threshold, `DispositionDispatcher` computes `Requeue (Reason=VmafBelowMin)` and logs it, but no new `TranscodeQueue` row is inserted anywhere in the pipeline. The rejected `-mv.mp4.inprogress` output stays on disk, no adjusted-CRF re-encode is scheduled, and /Operations doesn't render the state (it's neither RecentSuccess nor RecentFailure per Success=TRUE + PassesThreshold=FALSE).

**Repro:** MediaFileId 691647 (Love Island USA S08E17), attempt 40985 on I9-2024, 2026-07-02:
- Transcode: 3.75 GB source -> 482 MB output, Success=TRUE at 18:38:07 UTC.
- QT: VMAF=84.72, PassesThreshold=FALSE at 19:16:16 UTC.
- `DispositionDispatcher` log: `Disposition for TranscodeAttempt 40985: Requeue (Reason=VmafBelowMin)`.
- `SELECT COUNT(*) FROM transcodequeue WHERE mediafileid=691647;` returns 0.
- `.inprogress` file: `T:\Love Island USA\Season 8\Love Island USA - S08E17 - Episode 17 WEBDL-720p-mv.mp4.inprogress` (482 MB, mtime 12:37 MDT), still present, orphaned.

**First place to look:**
- `Features/QualityTesting/Disposition/DispositionDispatcher.py` -- decision is computed but the write-side may return silently.
- `Features/TranscodeJob/Adjustments/AdjustmentRegistry.py` (CQ adjuster) + `RetranscodeDecider` -- these compute the adjusted CRF for the re-queue; the dispatcher may not be calling them.
- `Features/TranscodeQueue/QueueManagementBusinessService.py::CreateQueueItem*` -- the intended insert path.
- `Features/Activity/ActivityController.py` + `/Operations` templates -- add a third bucket for "Requeue-pending" / "quality-rejected" attempts.

**Proposed criterion:** "Every TranscodeAttempts row with `Success=TRUE, QualityTestCompleted=TRUE, PassesThreshold=FALSE` and a Requeue disposition results in either (a) a new `TranscodeQueue` row created with `AdjustmentRegistry`-computed CRF within 5 seconds of the disposition write, or (b) a `MediaFiles.AdmissionDeferReason='requeue_refused_<reason>'` set with the refusal reason logged. `.inprogress` outputs from Requeue'd attempts are deleted (or explicitly retained under an audit table). /Operations renders a `Quality Rejected` card counting these attempts."

**Fix with:** `/t BUG-0079`.

---

### quality-testing

### [BUG-0080] GenerateComparisonStills raises `NameError: name 'Ctx' is not defined` on every call
**Date:** 2026-07-02 | **Area:** quality-testing / stills

**What breaks:** `QualityTestingBusinessService.GenerateComparisonStills` throws `NameError: name 'Ctx' is not defined` on every timestamp it tries to capture. All 4 default timestamps (ts=60/300/600/900) fail, `Auto-captured 0/4 stills for attempt ... (policy=All)` is logged. Operator loses the visual comparison surface the disposition review UI depends on.

**Repro:** attempt 40985 (Love Island USA S08E17, MediaFileId 691647), 2026-07-02 19:16:16 UTC:
```
ERROR   GenerateComparisonStills failed for attempt 40985 at ts=60.0: name 'Ctx' is not defined
WARNING Still capture at ts=60.0 for attempt 40985 failed: Exception: name 'Ctx' is not defined
ERROR   GenerateComparisonStills failed for attempt 40985 at ts=300.0: name 'Ctx' is not defined
WARNING Still capture at ts=300.0 for attempt 40985 failed: Exception: name 'Ctx' is not defined
ERROR   GenerateComparisonStills failed for attempt 40985 at ts=600.0: name 'Ctx' is not defined
WARNING Still capture at ts=600.0 for attempt 40985 failed: Exception: name 'Ctx' is not defined
ERROR   GenerateComparisonStills failed for attempt 40985 at ts=900.0: name 'Ctx' is not defined
WARNING Still capture at ts=900.0 for attempt 40985 failed: Exception: name 'Ctx' is not defined
INFO    Auto-captured 0/4 stills for attempt 40985 (policy=All)
```

**First place to look:**
- `Features/QualityTesting/QualityTestingBusinessService.py::GenerateComparisonStills` -- grep for `Ctx` in the body and identify the intended binding (likely a `with subprocess.Popen(...) as Ctx:` block that was refactored, or a `Ctx = {...}` context-dict that got removed).
- Recent git blame on the function -- the bug looks like a partial rename or a dropped import.
- Verify by re-running QT against attempt 40985 after the fix -- expect `Auto-captured 4/4 stills`.

**Proposed criterion:** "GenerateComparisonStills produces N/N stills for every attempt where source + encoded output both exist and are readable. Contract test at `Tests/Contract/TestGenerateComparisonStills.py` exercises the ts=60/300/600/900 default set against a synthetic fixture; observed via `SELECT COUNT(*) FROM logs WHERE message LIKE 'Auto-captured %/4 stills%' AND timestamp > '<deploy_time>' AND message NOT LIKE 'Auto-captured 4/4%'` returning 0 in 24h post-deploy."

**Fix with:** `/t BUG-0080`.

---

### transcode-queue

### [BUG-0078] AddJobToQueue silently rejects ForceAdd when latest attempt VMAF>=80; API returns Success=True with no queue row
**Date:** 2026-07-02 | **Area:** transcode-queue / admission

**What breaks:** `QueueManagementBusinessService.AddJobToQueue` walks two admission gates in sequence:

1. Marginal-savings gate (lines 2011-2019) -- `if not ForceAdd:` skips the gate on force.
2. RetranscodeDecider VMAF gate (lines 2022-2031) -- runs UNCONDITIONALLY. When VMAF>=80 on the latest attempt, returns `{"Success": True, "Skipped": True}` **without inserting a queue row**.

`ForceAdd` was designed to bypass gate 1 but never got wired through gate 2. The API caller (`QueueAdmissionAppService`) then sees `Success=True` and emits the misleading `Admit one: media_file=<id> bucket=Transcode status=queued` log line even though nothing was queued. The GUI shows a success toast, the queue tab shows nothing.

**Repro:** MediaFileId 691618 (Love Island - S01E34 - Episode 34 Live Final WEBDL-1080p.mkv, VMAF=87.44 on latest attempt). Confirmed twice today at 17:33:50 and 17:34:51 UTC, then again at 18:43:16 and 18:43:38 UTC. Each attempt: `Force adding ...` WARN followed 3-5 ms later by `Quality already acceptable (VMAF >= 80), skipping retranscode for ...` INFO. Zero rows in `TranscodeQueue` for MediaFileId=691618 across the whole window.

**Evidence:**
- `Features/TranscodeQueue/QueueManagementBusinessService.py:2028` -- `if not shouldRetranscode:` returns without insert regardless of ForceAdd.
- `Features/WorkBucket/Services/QueueAdmissionAppService.py:29` -- maps `Result.get('Success')` to `Status='queued'` without checking `Skipped`.
- `SELECT COUNT(*) FROM transcodequeue WHERE mediafileid=691618;` returns 0.
- `SELECT COUNT(*) FROM logs WHERE message ILIKE '%Force adding%691618%' AND timestamp > '2026-07-02 17:00'` returns 4.

**First place to look:**
- `Features/TranscodeQueue/QueueManagementBusinessService.py:2022-2031` -- the fix.
- `Features/WorkBucket/Services/QueueAdmissionAppService.py:25-38` -- the misleading log.
- `Features/QualityTesting/Disposition/RetranscodeDecider.py` -- the gate itself; consider whether it should accept a `ForceAdd` kwarg instead of the caller wrapping the call.

**Proposed criterion:** "When `AddJobToQueue` is invoked with `ForceAdd=True` against a MediaFile whose latest TranscodeAttempt has `VMAF >= 80`, the function inserts a `TranscodeQueue` row and returns `{Success: True, Skipped: False}`. `QueueAdmissionAppService.AdmitOne` logs `status=queued` only when a row was actually inserted; when `Skipped=True` it logs `status=skipped` with the reason from `Result.get('Message')`."

**Scope note:** `QueueManagementBusinessService.py` has 10 colocated feature/flow docs. The fix directive must read the doc-preread stack per R1, not skirt it.

**Fix with:** `/t BUG-0078`.

---

### stuck-detection

### [BUG-0075] StuckJobDetectionService marks Success=TRUE on frozen ffmpeg kills; downstream sees a "successful" attempt with a frozen-error message
**Date:** 2026-07-02 | **Area:** stuck-detection / transcode-lifecycle

**What breaks:** When `StuckJobDetectionService` decides an ffmpeg process is frozen (no frame advance for N minutes) and kills it, the corresponding `TranscodeAttempts` row is updated with `Success=TRUE` even though `ErrorMessage` says the process was killed while frozen. Every downstream consumer that gates on `Success=TRUE` then behaves as if the encode succeeded:

1. `QualityTestingQueue` gets a row enqueued for the killed attempt -> some worker claims it -> runs VMAF against a truncated `-mv.mp4.inprogress` output -> VMAF ffmpeg hangs against the incomplete file -> `qualitytestresults` row sits in `status='Running'` indefinitely (today's hung QT sweep found 30 such orphans across weeks).
2. `TranscodeFiles` rollup marks the file as successfully transcoded when the output is incomplete or missing.
3. `/Activity` failure surface hides the failure -- operator has no visible signal.
4. Retry policy skips the file because "it already succeeded."

**Repro:** `TranscodeAttempts.id=40967` (Breaking Bad S03E08 on wakko-worker-1, 2026-07-01): `Success=TRUE`, `ErrorMessage='FFmpeg process died unexpectedly - cleaned by StuckJobDetectionService: FFmpeg process is alive but frozen - no frame advance for 5.3 minutes (threshold...'`. QT queue row 1986 enqueued from this, claimed by larry-worker-4, hung for 18.6 h before manual sweep.

**Evidence:**
- `SELECT id, success, errormessage FROM transcodeattempts WHERE id=40967;` -> `success=TRUE, errormessage LIKE '%frozen%'`
- `SELECT COUNT(*) FROM qualitytestresults WHERE status='Running';` returned 30 before today's sweep -- all orphans of the same shape.

**First place to look:**
- `Features/ServiceControl/StuckJobDetectionService.py` -- the freeze-cleanup path that updates `TranscodeAttempts`; find every place it writes `Success=` and default to `False` in the freeze / kill path.
- `Features/QualityTesting/ProcessQualityTestQueueService.py` -- QT admission should refuse to enqueue when the driving `TranscodeAttempts` row's `ErrorMessage` contains the freeze marker, even if `Success=TRUE`.
- `Features/QualityTesting/QualityTestingBusinessService.py` -- add a stale-Running sweep (age > N hours + no matching ActiveJob row) that flips to `Failed` with a diagnostic reason. Prevents future 18-hour orphans.

**Proposed criterion:** "Every `TranscodeAttempts` row updated by `StuckJobDetectionService`'s freeze-cleanup path carries `Success=FALSE`. QT admission refuses to enqueue when the source `TranscodeAttempts` row's `ErrorMessage` matches the freeze marker regex. A background sweep marks any `qualitytestresults` row in `status='Running'` for > 60 minutes with no matching `activejobs` row as `status='Failed'` with `errormessage='orphan_prior_session'`."

**Fix with:** `/t BUG-0075`.

---

### audio-quality

### [BUG-0071] av1_qsv crashes mid-encode on Arc B580 + libmfx-gen 2.16 when `-extbrc` or `-look_ahead` are set
**Date:** 2026-06-29 | **Area:** transcode-encoder

**What breaks:** `av1_qsv` running on Intel Arc B580 (Battlemage `[8086:e20b]`) with libmfx-gen `26.2.2-1~24.04~ppa1` + libvpl `2.16.0-1~24.04~ppa1` + iHD `26.2.2-1~24.04~ppa1` (Intel kobuk PPA for Ubuntu noble) crashes at a non-deterministic frame past the first ~2 seconds with `[av1_qsv] Invalid FrameType:0` followed by `Error submitting video frame to the encoder` -> `Error encoding a frame: Invalid data found when processing input` (`-1094995529 / 0xBEBBB1B7`). ffmpeg muxes the partial output and prints `Conversion failed!`. Exit code 183.

**Repro:** Documented in `Scripts/Smoke/QsvCrashDiagnostic-2026-06-29.shootout.json`. 3-source matrix (NewGirl S06E03 live drama at HEVC 720p / Arcane S01E06 animation at H264 720p / 30 Rock S06E12 sitcom at H264 720p) all crash at distinct frame counts (8064 / 69 / 3835). Pattern is reproducible across content types -- not source-specific. Knob bisect (`Scripts/Smoke/_qsv_isolate.sh`): minimal `-c:v av1_qsv -b:v 480k -pix_fmt p010le` encodes the full Arcane episode cleanly (143 MB output). Adding `-extbrc 1 -look_ahead 1 -look_ahead_depth 40` to the same minimal set reproduces the crash within seconds.

**Trigger isolated:** `-extbrc 1` AND/OR `-look_ahead 1` (with any look_ahead_depth value). These knobs route encoding through the libmfx-gen look-ahead BRC path, which appears to mis-handle the Battlemage AV1 ASIC frame typing.

**Workaround in production:** Phase G seed (`Scripts/SQLScripts/AddQsvProfiles.py`) sets `QsvExtBrc=NULL`, `QsvLookaheadDepth=NULL`, `QsvBStrategy=NULL` on every threshold row of the two seeded QSV profiles. `QsvEncoderArgsStrategy.AddCodecParameters` omits the corresponding ffmpeg flags when ProfileSettings hold None. Live verification 2026-06-29: Arcane S01E06 transcoded end-to-end on wakko-worker-3 (TranscodeAttempts.id 40792, Success=TRUE, output 218 MB).

**Cost of the workaround:** loses bitrate-distribution optimization from look-ahead. Quality at matched bitrate may drop ~1-2 VMAF vs the look-ahead path. Acceptable until upstream fix.

**Upstream path:** report to Intel `kobuk-team/intel-graphics` PPA + ffmpeg-libvpl issue tracker. Revisit when libmfx-gen ships a fix. Test re-enable per `Scripts/Smoke/_qsv_isolate.sh`.

**See also:** `Docs/superpowers/specs/2026-06-29-wakko-arc-b580-onboarding-design.md` Phase H findings.

### [BUG-0072] Delete + requeue in Sonarr/Radarr for shows and movies destroyed by under-bitrated + downmixed transcode settings
**Date:** 2026-07-01 | **Area:** media-recovery

**What breaks:** Files transcoded under the deprecated policy stack (`-ac 2` forced-downmix + `-b:a 96k` bitrate cap + AudioNormalizationConfig.MaxAudioChannels=2 global) shipped audibly compromised: source 5.1 permanently collapsed to stereo (surround + LFE lost) AND the resulting stereo encoded at 96 kbps AAC-LC which is below transparency for orchestral / music / dynamic content. Damage is baked into the -mv.mp4 output; the source .mkv was replaced. Companion of BUG-0070 (which handles the detection query). This bug is about the recovery pipeline: (1) identify affected MediaFiles, (2) delete the destroyed -mv output on disk, (3) mark the file for re-acquisition, (4) trigger Sonarr/Radarr to re-fetch the source at the same or better quality, (5) let the freshly-scanned source flow through the current corrected pipeline (5.1 preserved on Track 0 + Dialog Boost on Track 1). Reality-TV shows may be excluded from the recovery set (operator judgement -- typically simple stereo mixes with low information density where the loss is smaller and re-download is bandwidth-expensive).

**Repro:** Doctor Strange in the Multiverse of Madness (MediaFileId=620518) ffmpeg command captures the exact damage: `-c:a aac -ac 2 -b:a 96k`. Source was 5.1; output is stereo at 96 kbps AAC-LC = smeared cymbals, muddled orchestra, missing bass rumble.

**Evidence:**
- `TranscodeAttempts.FfpmpegCommand` for Doctor Strange (attempt 36887): `-c:a aac -ac 2 -b:a 96k` confirms both downmix + low bitrate applied.
- `AudioNormalizationConfig.MaxAudioChannels = 2` at global scope means EVERY transcode through the affected window forced stereo downmix.
- `MediaFiles.TranscodedByMediaVortex=TRUE` with the compromised profile identifies the affected population.

**First place to look:**
- Sonarr API: `/api/v3/episodefile/{id}` for DELETE, `/api/v3/episodefile/bulk` for bulk operations, `/api/v3/wanted/missing` after delete triggers re-search
- Radarr API: same shape at `/api/v3/moviefile/{id}` + `/api/v3/movie/{id}/refresh`
- `TranscodeAttempts.FfpmpegCommand` regex for `-ac 2` AND (`-b:a 96k` OR `-b:a 128k`) as the damage marker
- `AudioNormalizationConfig` history if audit table exists, or grep git history for MaxAudioChannels changes
- MediaFile Genre / library tag to identify reality-TV subset for optional exclusion

**Proposed criterion:** "Provide a script/report + operator-triggered recovery flow that (1) enumerates every MediaFileId whose latest FileReplaced attempt was emitted through the `-ac 2 + b:a <=128k` damage window, (2) supports optional reality-TV exclusion by genre or library tag, (3) issues Sonarr/Radarr delete + re-search for each affected file, (4) verifies the re-download completes and the new file re-enters the current corrected pipeline."

**Out of scope for /b:** feature-doc criterion add + implementation of Sonarr/Radarr client + reality-TV classifier -- lands with `/t BUG-0072`.

**Fix with:** `/t BUG-0072`.

---

### [BUG-0070] Detect transcoded files affected by deprecated 96 kbps audio bitrate -- "robotic" audio across the library
**Date:** 2026-06-29 | **Area:** audio-quality

**What breaks:** Earlier in the month, profiles were configured with an audio bitrate limit at 96 kbps. Files transcoded under that policy ship with audibly degraded audio (robotic / artifact-laden output across the program). Audio settings have since been changed but the affected outputs were already replaced -- the operator wants a way to identify the affected set so they can be flagged for re-transcode at the corrected bitrate.

**Repro:** Play any media file whose successful TranscodeAttempt completed during the 96 kbps window. Robotic / metallic artifacts audible throughout.

**Evidence:**
- Operator reports "robotic sounds throughout the media" on multiple recently-transcoded files.
- Profile `AudioBitrateKbps` history shows a prior 96 kbps setting (now changed).
- `TranscodeAttempts.FfpmpegCommand` captures the actual `-b:a` argument used per encode -- the signal for which attempts ran under the 96 kbps cap.

**First place to look:**
- `TranscodeAttempts.FfpmpegCommand` -- grep for `-b:a 96k` (or `-b:a:0 96k`) in completed-and-replaced rows.
- `TranscodeAttempts.AudioBitrateKbps` (if populated) -- WHERE `AudioBitrateKbps <= 96 AND FileReplaced=TRUE`.
- `Profiles` history -- when was the AudioBitrateKbps changed and which profile was in effect during the window?
- Cross-reference with `MediaFiles.TranscodedByMediaVortex=TRUE` AND replacement-date inside the 96 kbps window.

**Proposed criterion (to be added to `Features/AudioNormalization/audio-normalization.feature.md` as C30 when `/t BUG-0070` runs):** "Provide a query/report that identifies every MediaFile whose latest replaced TranscodeAttempt was emitted at the deprecated 96 kbps audio bitrate (parse FfpmpegCommand for `-b:a 96k` OR check AudioBitrateKbps <= 96). Operator uses the list to flag affected files for re-transcode."

**Out of scope for /b:** feature-doc criterion add (cross-directive R14 refusal); will land with the dedicated /t session.

**Fix with:** `/t BUG-0070`.

---

### uncategorized

*Per-entry area subsection assignment deferred to follow-up directive `migrate-bugs-compliance-deep`. Consult `memory/BUG-INDEX.md` for per-bug area metadata and the operationally-correct active/resolved classification (several entries below still bear `RESOLVED`/`FIXED` annotations in their headers despite living under `## Active`; the INDEX classifies them correctly).*

**SMB-on-Windows long-handle drops** (Microsoft SMB client EINVAL on long-duration handles under GPU-paced reads -- see memory `feedback_ms_nfs_client_unreliable.md` for the diagnostic pattern) are mitigated by **per-worker local staging** -- `Features/TranscodeJob/local-staging.feature.md`. Enable on Windows + SMB workers; leave OFF on Linux NFS workers.

### [BUG-0069] PopulateQueueForSubtitleFix references undefined `existingFilePaths` (latent NameError)
**Date:** 2026-06-28 | **Area:** transcodequeue / subtitle-fix

**What breaks:** `Features/TranscodeQueue/QueueManagementBusinessService.py:2489` -- the line `existingFilePaths.add(mediaFile.FilePath)` references a variable name never assigned in the enclosing function `_GetSubtitleFixEligibleFiles` (called from `PopulateQueueForSubtitleFix`). The function will `NameError` the first time `itemsAdded > 0` and the function attempts to track added files for dedup. The only path that imports / calls this is `POST /api/SubtitleFix/PopulateQueue` (operator-driven), so the bug has been latent.

**Look first:** the function uses pair-based dedup (`existingPairs.add((mediaFile.StorageRootId, mediaFile.RelativePath or ''))`) at line 2461. The 2489 `existingFilePaths.add` is dead-code residue from an earlier per-FilePath dedup design.

**Trivial fix:** replace `existingFilePaths.add(mediaFile.FilePath)` with `existingPairs.add((mediaFile.StorageRootId, mediaFile.RelativePath or ''))` -- matches the pair-based dedup already in use.

**Why latent:** the test `Tests/Contract/TestPopulateQueueForSubtitleFix.py` (if it exists) likely covers the path where no files are added (empty result). The crash only fires when at least one file is admitted.

**Fix with:** `/t BUG-0069`.

---

### [BUG-0067] CLOSED 2026-06-23 -- FileReplacement orphan-on-failure -- TranscodedOutputPlacement leaves transcoded .mp4 on disk when MediaFiles update fails; scanner ingests it as a duplicate row; next encode attempt fails identically; loop snowballs
**Date:** 2026-06-23 -> Closed 2026-06-23 by `/t BUG-0067` within `worker-runtime-state` directive | **Area:** file-replacement | **Resolution:** `Features/FileReplacement/TranscodedOutputPlacement.Execute` failure branch (post-rename, pre-original-delete) replaced silent `Success=True` + warning with explicit rollback (non-SameSlot: `os.remove(TargetPath)`; SameSlot: `os.rename(TargetPath, LocalStagedPath)` + `os.rename(BackupPath, LocalOriginalPath)` + remove staging) and returns `Success=False` carrying the real `_UpdateMediaFilesAfterReplacement` error. SameSlot eager `os.remove(BackupPath)` moved from inner rename block to after MediaFiles update commits so the rollback path can restore source. `FinalizePartialReplacement` parallel branch returns `Success=False` with the real error rather than masking. C13 + S4 added to `Features/FileReplacement/transcoded-output-placement.feature.md`. Verified by `Tests/Contract/TestFileReplacementRollbackOnUpdateFailure.py` (3/3 PASS: non-SameSlot orphan removed + source intact + bytes match; SameSlot source restored + backup gone + staging gone + bytes match; FinalizePartialReplacement returns Success=False with real error).

**What breaks:** `Features/FileReplacement/TranscodedOutputPlacement.py:Execute` lines 219-230. When `_UpdateMediaFilesAfterReplacement` returns `Success=False` (today's case: duplicate-key violation on `idx_mediafiles_storageroot_relpath_unique`), the function logs a warning ("future probe will reconcile") and returns `Success=True`. That promise is fiction: the orphan `.mp4` stays on disk next to the source `.mkv`, the file scanner later ingests the orphan as a brand-new MediaFile row, and the NEXT encode attempt for the same source hits the same unique-key collision. Each failed cleanup snowballs into another duplicate row.

Evidence from 2026-06-23 smoke (MediaFile 689432 Young Sheldon S07E11):
- 179MB `-mv.mp4` on disk from a June 14 encode attempt -- never cleaned up because that attempt also hit this branch
- Today's 126MB `-mv.mp4` from a fresh encode -- same outcome
- MediaFile 689416 (scanner-discovered duplicate of the June 14 orphan) blocks the update of MediaFile 689432
- Source `.mkv` (624MB) untouched, MediaFile 689432 still reports source codec h264 + eac3 + matroska

The fallback "return Success with a warning" is the bug. The principle: when post-rename DB update fails, the rename MUST be rolled back (move `.mp4` back to `.mp4.inprogress`, or delete it), the attempt MUST be marked failed with the actual error visible, and the source MUST stay intact.

**Look first:**
- `Features/FileReplacement/TranscodedOutputPlacement.py:Execute` lines 219-230 -- the orphan-on-failure branch; replace `return {Success: True, ...}` with rollback (rename target back to .inprogress, or os.remove) + `return {Success: False, ErrorMessage: <real error>}`
- `Features/FileReplacement/TranscodedOutputPlacement.py:_UpdateMediaFilesAfterReplacement` -- when this fails on unique-key collision, the upstream symptom is "another MediaFile row already owns the target path". Investigate WHY a row exists at the target path; if the cause is a previous orphan (recursive symptom) the rollback above fixes both. If the cause is a legitimate MV-output that was previously transcoded, the system needs to dedup BEFORE writing rather than after.
- `Features/FileScanning/FileScanningBusinessService` (or wherever a `-mv.mp4` filename is ingested) -- a scanner that discovers a `-mv.mp4` file should either (a) attach it to the source MediaFile by matching basename + storage root + relpath stripping the `-mv.mp4`-vs-source-extension suffix, OR (b) refuse to ingest if it would create a duplicate -- never silently create a parallel row

**Settings knobs (GUI-level):**
- No hardcoded retry / rollback / cleanup behavior -- exposed via `SystemSettings.FileReplacementOnUpdateFailure` enum ('Rollback' / 'LeaveOrphan' / 'DeleteOrphan'; default 'Rollback'). Visible in /Settings.
- No hardcoded constants in the rollback path -- target path / staging path are both DB-resolved (already are).

**Acceptance principle:** simplify and 100% solid-perfect implementation; NO hardcoding, NO fallbacks. Replace the orphan-on-failure branch with explicit rollback + loud failure; downstream the scanner-creates-duplicate-row symptom disappears because no orphans are produced.

**Cross-references:** Surfaces during `worker-runtime-state` directive smoke verification (2026-06-23). The 689432 / 689416 duplicate is one snapshot of this bug; the same shape applies to any file where `_UpdateMediaFilesAfterReplacement` could fail.

**Fix with:** `/t BUG-0067`.

---

### [BUG-0066] Audio pipeline has silent fallback chains -- principle violation; we cannot tell whether the primary rule fired
**Date:** 2026-06-23 | **Area:** audio-pipeline | **Reshapes:** BUG-0065 fix path

**What breaks:** Operator principle stated 2026-06-23: "We CANNOT have fallbacks. This prevents us from knowing if our system is working." The audio pipeline today is fallback-shaped in at least two places:

1. **`LanguageDetector.Detect` (C11)** -- explicitly chains six rules in order: ISO 639-2 tag -> title regex -> single-audio-stream short-circuit -> `disposition.default==1` -> per-library default -> `AudioStreamLanguageDetectionsJson` cache. Whichever rule fires first wins; the others' outputs are discarded and nothing records WHICH rule actually picked the language. If rule 1 silently mis-tags `eng` as `und` because a tag is malformed, the chain falls through to rule 4 (disposition) and the operator sees a "correct" answer with no signal that rule 1 broke.

2. **`_PickDefaultLanguage` (L1)** -- chains three rules for `disposition.default=1` placement: source's per-stream default-language -> library default -> first present language. Same silent-cascade pattern.

3. **The BUG-0065 entry filed earlier today** proposed adding ANOTHER fallback layer (English-when-present, between source-default and first-present). That direction multiplies the problem instead of fixing it.

The principle: each pick decision must either (a) be a single explicit rule with no fallback (fail loud if it doesn't apply), OR (b) record on the output which rule fired so the operator can audit. Silent cascades are forbidden.

**Violates:** `Features/AudioNormalization/audio-normalization.feature.md` criterion C25 (added with this entry). Reshapes C24 (BUG-0065) -- the fix for BUG-0065 must satisfy C25 (no silent fallback) rather than extending the existing chain.

**Look first:**
- `Features/AudioNormalization/LanguageDetector.py` `Detect()` -- the explicit six-rule chain; the function's return must include WHICH rule fired (e.g. tagged result type carrying `Rule` field), AND the rule choice must be persisted to `TranscodeAttempts.AudioTracksEmittedJson` (C15) or a sibling column so an operator querying the DB can see whether ISO tags are doing their job or whether the system is silently leaning on the disposition fallback
- `Features/AudioNormalization/AudioFilterEmitter.py` `_PickDefaultLanguage()` -- same pattern; emit a "default-pick-rule" annotation
- `Features/AudioNormalization/audio-normalization.feature.md` C11 + L1 -- the contracts that codify the cascades; both need to be rewritten to either single-rule + fail-loud OR explicit-rule-recording
- Any other `# fallback` / `or X if not Y` / chained-`elif` pattern in the audio vertical -- audit and either collapse or expose

**Decision needed at fix time:** does the audio pipeline switch to (a) single explicit rule (English-or-fail) -- simple but rejects non-English-only sources, OR (b) explicit-rule-with-recorded-provenance -- keeps current capability but adds observability? The phrasing "prevents us from knowing if our system is working" suggests (b) is acceptable IF the rule provenance is recorded and queryable. Confirm during `/t`.

**Fix with:** `/t BUG-0066`. Address BEFORE `/t BUG-0065` -- BUG-0065's fix must conform to the principle this bug establishes.

---

### [BUG-0065] Default audio track must be English when source carries multiple language audio streams
**Date:** 2026-06-23 | **Area:** audio-default

**What breaks:** When a media file carries multiple language audio streams (e.g. `eng` + `jpn`), the emitter's current default-language pick rule -- per `Features/AudioNormalization/audio-normalization.feature.md` lines 183-186: "source's per-stream default-language, falling back to library default, falling back to first present language" -- can land `disposition.default=1` on a non-English track when the source's `disposition.default` flag points at a non-English stream and the per-library default is unset. Operator expects English to be the implicit default whenever it is present, regardless of source disposition.

**Violates:** `Features/AudioNormalization/audio-normalization.feature.md` criterion C24 (added with this entry). Related context: C11 (LanguageDetector.Detect chain) and C23 (EmitTracks.LanguageDefault config).

**Look first:**
- `Features/AudioNormalization/audio-normalization.feature.md` lines 179-186 (multi-language live-encode invariant L1) -- governs which track receives `disposition.default=1`
- `Features/AudioNormalization/AudioFilterEmitter.py` `_PickDefaultLanguage(AudioStreams, StreamLanguageMap, ...)` -- the function that applies the fallback chain
- `Features/AudioNormalization/LanguageDetector.py` `Detect()` -- the per-stream language identification (English detection already exists here via title regex `english|eng\b|en-us|en-gb`)
- `AudioNormalizationConfig.LanguageDefault` -- per-scope override; new criterion should not weaken this (operator-set library default still wins over the implicit-English rule)

**Decision needed at fix time:** does the English-default rule sit BEFORE or AFTER `disposition.default` from source? The user's phrasing ("audio should default to english if it has multiple languages") suggests English wins over source disposition. Confirm during `/t`.

**Fix with:** `/t BUG-0065`.

---

### [BUG-0064] Deploy story not cleanly documented -- I9 local-vs-remote split missing; remote-worker deploy has inter-worker dependencies; two scripts where one SOLID script belongs
**Date:** 2026-06-23 | **Area:** deploy

**What breaks:** The deploy contract conflates two fundamentally different operations: (a) bringing remote worker hosts (Linux Docker / Windows SMB) online, and (b) cycling local I9 WebService + WorkerService processes that run directly from the live source tree. Today both go through the deploy/ surface, references to "deploy I9" exist in flow docs + bringup, and there's no single operator-facing script that captures the policy. Three concrete acceptance criteria from operator:

1. **Local I9 services have NO deploy.** They are the active codebase -- code changes apply on restart. Operator-facing command starts both services from their respective venvs (`venv/` for the worker, `WebService/venv/` for the WebService -- see memory `feedback_webservice_venv_drift.md`), **WebService ALWAYS first online**, and **must check for any running WorkerService process on I9 and stop it before starting a new one** (see memory `feedback_one_i9_worker_instance.md` + `feedback_worker_restart_protocol.md`). No SyncSource, no Task Scheduler registration, no Docker.

2. **Remote worker deploys are independent.** Deploying larry/wakko/dot or any future host MUST NOT depend on the state of any other worker. Today `deploy-fleet.py`-style orchestration and shared compose templates create cross-worker dependencies (one host's deploy can stall waiting on another's heartbeat or share a build context). Each remote deploy is a self-contained unit; failure on host A does not block or roll back host B.

3. **Single SOLID deploy script.** Today there are two scripts (`deploy-linux-worker.py` + `deploy-windows-worker.py`) plus a fleet wrapper plus a register-task PS1. Collapse to ONE entry-point script with a Strategy pattern per host shape (LXC-Docker / bare-metal-Docker / Windows-SMB / I9-local). SRP: per-shape strategy owns its bring-up steps; the entry script owns CLI parsing + inventory lookup + verification polling only. Constructor-DI throughout. 100% clean code -- no scripts-shaped-as-bash-pipelines, no shared mutable state, no copy-paste between OS branches.

**Violates:** `deploy/worker-deploy.feature.md` criterion 14 (added with this entry). Also touches:
- `feature-docs.md` / `flow-docs.md` -- the I9-local-vs-remote split must be reflected in feature + flow contracts
- `scope-discipline.md` -- a perfect-implementation directive cannot leave the I9 case smudged across "Code updates on I9-2024" prose

**Look first:**
- `deploy/worker-deploy.feature.md` lines 16-17 -- the "Code updates on I9-2024" paragraph today is informal prose; it needs to become a hard contract (no deploy path, just start/stop)
- `deploy/deploy-windows-worker.py` -- this exists today and registers a Windows Task Scheduler task; if I9 is local-only it shouldn't be running through this path
- `deploy/bringup.md` -- the runbook should route I9 to a local start command, not a deploy
- `deploy/deploy-linux-worker.py` + `deploy/deploy-fleet.py` (if it exists) -- audit for inter-worker dependencies
- `StartMediaVortex.py` -- already exists as the local lifecycle entry point; the I9-local "deploy" probably collapses into this
- The four host-shape strategies that need to exist: LXC-Docker, bare-metal-Docker (wakko/dot), Windows-SMB, and the I9-local NO-OP

**Fix with:** `/t BUG-0064`.

---

### [BUG-0063] CLOSED 2026-06-23 -- CLUSTER -- Activity dashboard SOLID rewrite (FPS smoothing + ETA countdown + drain-visible jobs + worker-status decoupling)
**Date:** 2026-06-12 -> Closed 2026-06-23 by `worker-runtime-state` directive | **Area:** activity-page | **Subsumes:** BUG-0057, BUG-0058, BUG-0059, BUG-0040, BUG-0037, BUG-0025, BUG-0007 | **Resolved:** Activity refocused to active in-flight work (Active Jobs + Active Scans); worker tiles relocated to `/Admin/Workers`; library compliance relocated to `/Admin/Compliance`; workers are now authoritative source of truth for runtime state via `WorkerStateReporter` writing `Workers.RuntimeState` + `CurrentAttemptId` + `LastRuntimeStateUpdate` directly to DB.

**Why bundled:** Today's `/Activity` page is a god-template. `Templates/Activity.html` mixes (a) ad-hoc data fetching per panel, (b) zero progress smoothing -- raw spot FPS/Speed values from `TranscodeProgressModel` render verbatim and jitter wildly, (c) hard-coded worker-status interpretation that conflates "operational state" with "process reachable," (d) jQuery DOM manipulation per-panel with no shared model, (e) per-button click handlers that fire N serial requests where one bulk call would do. Six bugs file against this single template + its backing endpoints. The SRP fix is a layered ViewModel + Service decomposition, not point patches.

**SOLID/SRP target architecture (full criteria live in feature/flow docs at directive open):**

1. **Single dashboard payload.** `ActivityRepository.GetDashboardSnapshot()` returns `{Workers, ActiveJobs, QueueCounts, BadgeState}` in one round-trip. Frontend never fetches more than once per poll. Verifiable: DevTools Network tab shows exactly one XHR per 5s tick from the Activity page.

2. **ProgressSmoothingService** (server-side, new `Features/Activity/Services/`). Owns the rolling-window arithmetic mean of `CurrentFPS` and `CurrentSpeed` per `TranscodeAttemptId`. Window: 10 samples or 30 seconds (whichever is smaller). Resets on `TranscodeAttemptId` change. Stale-sample threshold from `SystemSettings.StaleProgressThresholdSec` (default 15s); past threshold emits `NULL` (rendered as `--`). Constructor-injected: `(ProgressRepository, SystemSettingsRepository, Clock)`. DB-is-authority on threshold.

3. **ActiveJobsViewModel + WorkersViewModel are decoupled.** `ActiveJobsViewModel` rows are sourced from `ActiveJobs WHERE TranscodeAttempts.Success IS NULL` joined to `Workers` for the display name only -- NEVER filtered by `Workers.Status`. `WorkersViewModel` reflects `Workers.Status` for tile badges. A job claimed by a `Draining` worker appears in both views; the worker tile shows `Draining`, the job row shows continuing progress. Defense against BUG-0059 family.

4. **WorkerStatusRenderer is a data-driven mapping.** Single JS table `Status -> {Label, BadgeClass, Tooltip}`. Unknown values render with `bg-secondary` + the raw string. `Workers.Status` gains terminal `Stopped` via migration; `Offline` becomes a derived UI concept (heartbeat-staleness), not a column value. Migration: `RenameWorkerStatusOfflineToStopped.py` (idempotent). Subsumes BUG-0037 + BUG-0025.

5. **Connectivity vs operational state.** Worker tile carries TWO indicators: badge (from `Workers.Status` -- operator-set) and connectivity dot (from `LastHeartbeat` age vs `SystemSettings.HeartbeatStaleThresholdSec`, default 300s). They are independent: a `Stopped` worker still heartbeating shows green dot + grey "Stopped" badge.

6. **ETACountdownTimer** (client-side, new JS module). Maintains a per-job timer that decrements 1s per second between server polls. On each poll, compares server ETA to client running value: `|delta| <= 5s` -> client wins (smooth); `> 5s` -> client resets to server value (material change). Renders `--:--:--` when smoothed FPS is unavailable.

7. **Per-job progress isolation.** `TranscodeProgress` rows are keyed and indexed by `TranscodeAttemptId`; rendering joins ActiveJobs to TranscodeProgress on that key. No worker-name fallback, no most-recent shortcut -- second concurrent job NEVER shows first job's progress. Subsumes BUG-0040.

8. **Draining has a terminal state.** `_DrainAndStop()` writes `Status='Stopped'` when join completes. Drain waiter thread + 3-state model collapses to 2-state (Online / Paused) with `_StopAllCapabilities` covering remux + transcode + VMAF + scan. Subsumes BUG-0025.

9. **Bulk worker-status endpoint.** `POST /api/TeamStatus/Workers/BulkStatus` replaces N serial fetches. Per-worker success/failure in one payload.

10. **Capability toggle re-renders inline.** `POST /api/TeamStatus/Workers/<name>/<Capability>` Success refetches the snapshot and re-renders the affected tile/modal without operator close-and-reopen. Subsumes BUG-0007.

11. **Failed Jobs panel adopted from BUG-0061.** Panel renders from `FailedJobsRepository` (owned by BUG-0061 cluster); this cluster supplies the operator surface only (route, template, click-through). Cross-cluster contract.

12. **TranscodeProgress schema discipline.** `TranscodeProgress.LastProgressUpdate` becomes the smoothing service's freshness signal. INSERTs without `LastProgressUpdate` are refused at the model layer (`__post_init__` validation in `TranscodeProgressModel`).

13. **All criteria in the existing DRAFTED `activity-dashboard-improvements.feature.md` C1-C22 stand.** This cluster ADOPTS that feature doc as its primary contract; the SOLID decomposition above is added to its `## Architecture` section at directive-open.

**Feature/flow doc deliverables:**
- `Features/Activity/activity-dashboard-improvements.feature.md` -- absorb the C20-C22 already added + new `## Architecture` block naming the ViewModels + Service layering
- `Features/Activity/activity-dashboard.flow.md` -- NEW. Stages: ST1 Poll trigger -> ST2 GetDashboardSnapshot -> ST3 ProgressSmoothingService -> ST4 ViewModel build -> ST5 Render -> ST6 Action dispatch. Seams between each stage.

**Sequencing:** Third (last) cluster -- benefits from BUG-0061's `FailedJobsRepository` already existing. Estimate 7-10 day directive.

**Evidence preserved:** See SUPERSEDED entries for BUG-0057 / BUG-0058 / BUG-0059 below + existing entries for BUG-0040 / BUG-0037 / BUG-0025 / BUG-0007.

---

### [BUG-0062] CLUSTER -- Compliance writeback invariant enforcement
**Date:** 2026-06-12 | **Area:** compliance | **Subsumes:** BUG-0056

**Why bundled:** The new compliance engine (shipped 2026-06-09 via `compliance-solid-refactor`) materializes per-row decisions to `MediaFiles` via `BulkWriteRecomputeResults`. The decision-precedence contract in `compliance.feature.md` C3 says bucket assignment and `IsCompliant` are mutually-derived: empty `OperationsNeeded` -> bucket None + `IsCompliant=True`; any operation needed -> bucket assigned + `IsCompliant=False`. Live DB shows 5703 rows where `IsCompliant=TRUE` AND `WorkBucket IS NOT NULL` AND `OperationsNeededCsv != ''` -- the precedence is honored in the engine's `ComplianceDecision` data structure but NOT enforced at the write boundary, so some path lets contradictory tuples through. This is a single surgical fix, not a wide rewrite -- the engine's SOLID shape is already good; the invariant just needs a defensible enforcement layer.

**SOLID/SRP target architecture:**

1. **`ComplianceDecision` self-validates in `__post_init__`.** The frozen dataclass raises `ContradictoryDecisionError` if the C3 precedence is violated -- empty `OperationsNeeded` with non-None `WorkBucket`, any op present with `IsCompliant=True`, etc. Producers can never construct an invalid Decision.

2. **`ComplianceBucketResolver` is the sole producer of the `(IsCompliant, WorkBucket)` tuple.** Refactor `ComplianceEvaluator.Evaluate` so that `IsCompliant` is NEVER set independently of `WorkBucket` -- both fall out of `Resolver.Resolve(OperationsNeeded)`. Eliminates the seam where the two fields can drift.

3. **SQL-level enforcement.** `ALTER TABLE MediaFiles ADD CONSTRAINT chk_compliance_consistency CHECK ( (IsCompliant=TRUE AND WorkBucket IS NULL AND (OperationsNeededCsv IS NULL OR OperationsNeededCsv='')) OR (IsCompliant=FALSE AND WorkBucket IS NOT NULL AND OperationsNeededCsv IS NOT NULL AND OperationsNeededCsv!='') OR (IsCompliant IS NULL AND ComplianceGateBlocked IS NOT NULL) )`. Migration is idempotent. Constraint is added AFTER the one-shot remediation recompute.

4. **`BulkWriteRecomputeResults` loud-fails on invariant violation BEFORE the SQL.** Loops the tuples, asserts C3 precedence per row, logs WARN with MediaFileId + decision fields for any violation, refuses to write that row, returns count of written + count of refused. Defense in depth even with SQL CHECK.

5. **`Tests/Contract/TestComplianceWriteConsistency.py` asserts the invariant against the live DB after any full or partial recompute. Runs on every CI pass.** Greps for: `SELECT COUNT(*) FROM MediaFiles WHERE NOT (chk_compliance_consistency_predicate)` returns 0.

6. **One-shot remediation script.** `Scripts/SQLScripts/RemediateComplianceWritebackInvariant.py` triggers full library recompute (`POST /api/Compliance/Recompute` with `All=true`) and verifies the contradictory-row count drops to 0 before exiting.

7. **`Features/Compliance/compliance.feature.md` gets criterion 7-9** (the existing C6 stays; new criteria cover the Decision self-validation, the BucketResolver-as-sole-producer contract, and the SQL CHECK constraint).

**Feature/flow doc deliverables:**
- `Features/Compliance/compliance.feature.md` -- amend C6 to reference the SQL invariant + add C7-C9 for Decision self-validation, BucketResolver sole-producer, SQL CHECK
- `Features/Compliance/compliance.flow.md` -- update stage where writeback happens to reflect the loud-fail seam

**Sequencing:** First cluster (per /t recommendation -- foundation move). Estimated 1-2 day directive.

**Evidence preserved:** See SUPERSEDED BUG-0056 entry below.

---

### [BUG-0061] CLUSTER -- Failure accounting (FailureBudgetService + FailedJobs surface + TranscodeAttempts accountability)
**Date:** 2026-06-12 | **Area:** failure-accounting | **Subsumes:** BUG-0055, BUG-0060, BUG-0029

**Why bundled:** Three current bugs share one root pathology: `TranscodeAttempts` rows are not held accountable for their identity, their owner, or their retry budget. (a) Failed encodes have NO cap analogous to `RetryBudgetService.MaxRequeueAttempts` for VMAF -- failing jobs re-queue indefinitely via the compliance recompute (15 fails on Mune Guardian; 1455 orphan-MediaFileId rows back to 2025-10-15). (b) The failure INSERT path can drop `MediaFileId` AND `ProfileName`, leaving rows that can't be diagnosed from the table alone. (c) There is no operator surface for "what's stuck" -- the operator has to grep DB logs to find files that ate the worker pool. The SOLID fix is a new `Features/FailureAccounting/` vertical with its own Repository + Service + Controller + ViewModel, mirroring the existing `Features/QualityTesting/Disposition/` SOLID shape that capped VMAF retries cleanly.

**SOLID/SRP target architecture:**

1. **`IFailurePolicy` + `FailureBudgetService` impl.** Sibling to `Features/QualityTesting/Disposition/RetryBudgetService`. Counts `TranscodeAttempts WHERE Success=FALSE AND MediaFileId=<id>` since the most recent `Success=TRUE` (or since `MediaFiles.CreatedAt` if no prior success). Returns `HasBudgetRemaining(MediaFileId) -> bool`. Constructor-injected: `(TranscodeAttemptsRepository, FailureBudgetConfigRepository, Clock)`. DB-fresh per call (db-is-authority -- no caching).

2. **`FailureBudgetConfig` table.** Single-row config (mirrors `PostTranscodeGateConfig`). Columns: `MaxEncodeFailures INTEGER NOT NULL DEFAULT 3`, `ResetWindowDays INTEGER NULL` (NULL = no time-based reset, only operator-triggered or Success=TRUE). GUI surface on `/settings`.

3. **`FailedJobsRepository`** owns the read of capped jobs: filename, failure count, last `ErrorMessage`, last `AttemptDate`, `AssignedProfile`, last `WorkerName`. Plus reset operation: `ResetFailureBudget(MediaFileId, OperatorName)` writes an audit row to new `FailureBudgetResets` table and bumps `MediaFiles.LastFailureResetAt` so the budget counter ignores prior failures.

4. **`FailedJobsController`** at `/api/FailedJobs/`. Routes: `GET /` (paginated list), `GET /<MediaFileId>/Attempts` (full attempt history), `POST /<MediaFileId>/Reset` (operator reset).

5. **`FailedJobsViewModel`** for the `/FailedJobs` page (new). Operator can see, sort, search, click-through to attempt log, and reset individual files. No bulk reset -- intentional friction so operator looks at the failures before re-allowing them.

6. **`Templates/FailedJobs.html`** as the surface. Linked from `/Activity` page nav + a "Failed Jobs (N)" pill badge (consumed by BUG-0063 cluster).

7. **Claim path consults FailureBudgetService.** `TranscodeQueueRepository.ClaimNextPendingTranscodeJob` adds `AND NOT EXISTS (capped predicate)` to its WHERE clause. Defense-in-depth -- if the recompute gate misses, the claim still skips. Same change to `ClaimNextPendingRemuxJob`, `ClaimQualityTestJob` (per `db-is-authority.md` -- one helper emits the SQL fragment).

8. **Recompute path consults FailureBudgetService.** `QueueManagementBusinessService.RecomputeForFiles` does NOT `INSERT INTO TranscodeQueue` if `FailureBudgetService.HasBudgetRemaining(MediaFileId) == False`. Primary gate -- caps the queue at the source.

9. **`/ShowSettings` Next-batch surfaces consult FailureBudgetService.** `NextTranscodeBatch`, `SmartPopulate` Quick Fix + Remux + AudioFix all add the cap predicate. Verifiable: insert N+1 consecutive failures on MediaFileId X, hit `/ShowSettings`, confirm X is absent from every Next-batch card; reset X via the FailedJobs surface, confirm X re-appears.

10. **`TranscodeAttempts.MediaFileId` becomes `NOT NULL`.** Migration runs AFTER the one-shot cleanup. Migration is idempotent (NULL count = 0 precondition asserted).

11. **`TranscodeAttempts` INSERT discipline.** Every INSERT path -- success AND failure, every ProcessingMode (Transcode, Remux, Quick, AudioFix, SubtitleFix, TestVariant) -- sets `MediaFileId` from the resolved Job row AND sets `ProfileName` (resolved transcode profile OR `'Remux'`/`'Quick'`/`'AudioFix'`/`'SubtitleFix'` literal for non-transcode). Loud-fails if either is unresolvable. Subsumes BUG-0029.

12. **One-shot cleanup script** `Scripts/SQLScripts/CleanupOrphanFailedAttempts.py`. Triages the 1455 orphan rows: dedupes by `ErrorMessage + AttemptDate-rounded-to-minute + WorkerName`, best-effort backfills `MediaFileId` via TranscodeQueue.Id correlation where available, archives the rest to `Reports/OrphanFailedAttempts-2026-06-12.csv`, deletes archived rows from `TranscodeAttempts`. Idempotent.

13. **`Tests/Contract/TestFailureAccounting.py` asserts:** (a) `MediaFileId IS NULL` count is 0; (b) `ProfileName IS NULL` count on failure rows is 0; (c) every Pending TranscodeQueue row has `FailureBudgetService.HasBudgetRemaining = True` for its MediaFileId; (d) FailedJobs API returns the expected set for a synthetic over-cap MediaFile.

**Feature/flow doc deliverables:**
- `Features/FailureAccounting/failure-accounting.feature.md` -- NEW. Outcome, Workflows (W1 Open /FailedJobs, W2 Click filename to see attempts, W3 Click Reset), Success Criteria 1-13 above, Seams.
- `Features/FailureAccounting/failure-accounting.flow.md` -- NEW. Stages: ST1 Encode failure write -> ST2 FailureBudgetService eval -> ST3 Claim/Recompute/NextBatch consult -> ST4 FailedJobs surface render -> ST5 Operator reset write. Cross-stage seams.
- `Features/TranscodeQueue/TranscodeQueue.feature.md` C10 (already added, retagged) confirms claim/recompute integration.
- `Features/TranscodeQueue/next-batch-per-drive.feature.md` C12 (already added, retagged) confirms ShowSettings exclusion.
- `Features/TranscodeJob/TranscodeJob.feature.md` `[BUG-0061]` bullet (already added, retagged) confirms INSERT-path discipline + cleanup script + NOT NULL.

**Sequencing:** Second cluster (post-Cluster B which establishes compliance trustworthiness for the recompute gate). Estimated 3-5 day directive.

**Evidence preserved:** See SUPERSEDED BUG-0055 + BUG-0060 entries below + existing BUG-0029.

---

### [BUG-0060] [SUPERSEDED BY BUG-0061 2026-06-12] TranscodeAttempts rows with MediaFileId=NULL -- 1455 orphan failure rows back to 2025-10-15
**Date:** 2026-06-12 | **Area:** transcode-job | **Status:** Folded into BUG-0061 failure-accounting cluster; evidence preserved below.

**What breaks:** `TranscodeAttempts` should be MediaFile-scoped: every failed/successful encode attempt belongs to a specific `MediaFiles.Id`. As of 2026-06-12 the production DB carries 1455 rows with `MediaFileId IS NULL`, all `Success=FALSE`, dating back to 2025-10-15. Without `MediaFileId`:
- Operator can't join the failure back to the source file for diagnosis.
- The per-MediaFile failure-cap predicate from BUG-0055 (`COUNT(*) FROM TranscodeAttempts WHERE Success=FALSE AND MediaFileId=<id>`) silently undercounts.
- Every aggregate that filters `WHERE Success=FALSE` carries this noise floor of stale, unattributable failures.

**Root-cause suspect:** `Features/TranscodeJob/ProcessTranscodeQueueService.HandleJobFailure` at line 1100 builds a fallback `TranscodeAttemptModel` (lines 1113-1133) without explicitly setting `MediaFileId` when the existing `TranscodeAttemptId` is missing. The pre-flight-failure path (source unreachable, profile resolution failure) likely enters this branch with `Job.MediaFileId` populated but the model constructor doesn't propagate it. Needs audit of every INSERT path -- Transcode, Remux, Quick, AudioFix, SubtitleFix, TestVariant -- before `/t` writes the fix.

**Success criteria for the fix:**

1. Every `TranscodeAttempts` INSERT path (success AND failure, every ProcessingMode) sets `MediaFileId` from the resolved Job row, or refuses the INSERT with a logged exception. Loud-fail on the contract violation.

2. Migration: after cleanup of the 1455 existing rows, `TranscodeAttempts.MediaFileId` gains a `NOT NULL` constraint. Idempotent migration script per repo convention.

3. One-shot cleanup script `Scripts/SQLScripts/CleanupOrphanFailedAttempts.py`: triages the 1455 rows -- dedupe by `ErrorMessage + AttemptDate-rounded-to-minute + WorkerName` (most are likely same-batch noise), best-effort backfill `MediaFileId` from `TranscodeQueue.Id <-> TranscodeAttempts.Id` correlation where the queue row was caught before deletion, archive the remainder to `Reports/OrphanFailedAttempts-YYYY-MM-DD.csv` and delete from `TranscodeAttempts`.

4. Verifiable: post-fix `SELECT COUNT(*) FROM TranscodeAttempts WHERE MediaFileId IS NULL` returns 0. `\d TranscodeAttempts` shows `MediaFileId BIGINT NOT NULL`. Insert a forced-failure transcode (e.g. via a missing-source canary) and confirm the resulting row carries the correct MediaFileId.

**Violates:** `Features/TranscodeJob/TranscodeJob.feature.md` `[BUG-0060]` criterion (added with this entry).

**Look first:** `Features/TranscodeJob/ProcessTranscodeQueueService.HandleJobFailure` (line 1100-1164, lines 1113-1133 are the suspect fallback INSERT), `Core/Models/TranscodeAttemptModel.py` (model definition -- does MediaFileId have a sensible default?), every `SaveTranscodeAttempt` callsite (`grep -rn "SaveTranscodeAttempt\(" --include='*.py'`).

**Related:** BUG-0055 (the failure-cap that needs this column to count correctly).

**Fix with:** `/t BUG-0060`

---

### [BUG-0059] [SUPERSEDED BY BUG-0063 2026-06-12] Active Jobs panel hides jobs claimed by Draining workers
**Date:** 2026-06-12 | **Area:** activity-page | **Status:** Folded into BUG-0063 activity-dashboard cluster; evidence preserved below.

**What breaks:** When an operator flips a worker to `Status='Draining'`, the worker continues running its in-flight job(s) until they complete (per `graceful-drain.feature.md`). But the Active Jobs panel on `/Activity` removes those still-running jobs from view as soon as the worker enters Draining state. The operator loses visibility: ETA, FPS, progress -- all gone. The temptation is to kill the worker thinking it's hung, which orphans the claimed rows in `Running` state.

**Likely cause (defer root-cause to `/t`):** the panel's source query joins `Workers` with an implicit `Workers.Status='Online'` filter, OR the frontend filters rendered rows by worker status. `GET /api/SQLQueries/GetActiveJobs` itself is unfiltered (`Features/SQLQueries/SQLQueriesController.py:121`), so the filter is elsewhere -- possibly in `Features/Activity/ActivityRepository.py` or in `Templates/Activity.html` JS.

**Success criteria for the fix:**

1. Active Jobs list includes every job where `TranscodeAttempts.Success IS NULL` AND a live `ActiveJobs` row exists, regardless of the owning `Workers.Status`. Worker tile state (Online/Draining/Stopped) is DECOUPLED from job visibility.

2. Worker tile and Active Jobs panel are separately driven: a draining worker shows the `Draining` badge on its tile AND its still-running job appears in the Active Jobs list with the worker's name + a (subtle) Draining hint adjacent to the worker column.

3. Verifiable: start a long encode on `larry-worker-1`, flip larry to Draining mid-encode, confirm the Active Jobs row for that encode remains visible with continuing progress until the encode completes naturally; confirm the worker tile badge shows `Draining`.

**Violates:** `Features/Activity/activity-dashboard-improvements.feature.md` criterion 22 (added with this entry).

**Look first:** `Features/Activity/ActivityRepository.py` (search for `Status` joins to Workers), `Templates/Activity.html` (search the JS render path for filter by `IsOnline` or `Status='Online'`), `Features/TeamStatus/TeamStatusController.py` (any per-worker job rollup that the panel might be reading instead of GetActiveJobs).

**Related:** `Features/ServiceControl/graceful-drain.feature.md` (backend drain semantics; this bug is the UI-visibility complement).

**Fix with:** `/t BUG-0059`

---

### [BUG-0058] [SUPERSEDED BY BUG-0063 2026-06-12] ETA on Active Jobs table doesn't count down smoothly
**Date:** 2026-06-12 | **Area:** activity-page | **Status:** Folded into BUG-0063 activity-dashboard cluster; evidence preserved below.

**What breaks:** The ETA cell on the Active Jobs table on `/Activity` is recomputed from scratch on every render poll (every 5s) using the latest spot `CurrentFPS` value. Because FFmpeg's per-second FPS sample is noisy (keyframe intervals, scene-change pauses), the ETA cell ticks erratically -- jumps from `00:14:23` to `00:08:11` to `00:17:55` purely from FFmpeg's per-second noise, never decrements smoothly. Operator can't tell whether the encode is making real progress or what to expect.

**Success criteria for the fix:**

1. Client maintains a per-job ETA timer that decrements 1 second per second between server polls (smooth countdown).

2. On each poll, the server-computed ETA is compared to the client's running ETA. If `|delta| <= 5s`, the client's timer wins (no recompute -- preserves the smooth countdown). If `|delta| > 5s`, the client resets to the server value (material change, recompute justified).

3. The server-computed ETA uses the smoothed FPS from BUG-0057 (`activity-dashboard-improvements.feature.md` C20), not the raw spot value, so the polled value itself is stable.

4. ETA renders as `--:--:--` when smoothed FPS is unavailable or stale (per BUG-0057 stale-sample rule).

5. Verifiable: open Active Jobs on a long encode, observe ETA decrements 1s per second between 5s polls; force a step-change in encode rate (e.g. toggle worker concurrency), observe ETA snaps to the new estimate on the next poll.

**Violates:** `Features/Activity/activity-dashboard-improvements.feature.md` criterion 21 (added with this entry).

**Depends on:** BUG-0057 (smoothed FPS is a precondition).

**Look first:** `Templates/Activity.html` (Active Jobs render path -- the ETA cell rendering JS), `Features/Activity/ActivityRepository.py` or the endpoint that returns Active Jobs payload (the source of the server-side ETA).

**Fix with:** `/t BUG-0058`

---

### [BUG-0057] [SUPERSEDED BY BUG-0063 2026-06-12] Active Jobs FPS and Speed columns fluctuate wildly / appear frozen at 0
**Date:** 2026-06-12 | **Area:** activity-page | **Status:** Folded into BUG-0063 activity-dashboard cluster; evidence preserved below.

**What breaks:** `TranscodeProgressModel.CurrentFPS` and `CurrentSpeed` (defined at `Features/TranscodeJob/Models/TranscodeProgressModel.py`) are raw spot values from the most recent FFmpeg progress line and render verbatim in the Active Jobs table. FFmpeg's per-second emit jumps between e.g. 100 / 5 / 95 / 0 / 80 during keyframe intervals and the UI fluctuates wildly. Conversely, if no progress sample has arrived for several seconds, the cells continue showing the stale last value -- looks frozen at e.g. `100 fps` while nothing is actually moving. Operator can't tell "encode is making real progress" from "worker is hung."

**Success criteria for the fix:**

1. Rendered FPS column shows a rolling 10-sample (or 30-second window, whichever is smaller) arithmetic mean of `CurrentFPS` samples for the same `TranscodeAttemptId`, not the raw last value.

2. Rendered Speed column applies the same smoothing (10-sample / 30-second window).

3. When no progress sample has arrived in the last `StaleProgressThresholdSec` (new `SystemSettings` row, default 15s), FPS/Speed cells render as `--` -- distinguishes "actually paused" from "just hasn't ticked yet."

4. Smoothing window resets to the new value when a worker's claim transitions to a new `TranscodeAttemptId`, so a fresh job doesn't inherit the previous job's average.

5. Verifiable: synthetic injection of progress samples `[100, 5, 95, 0, 80, 105, 8, 90, 0, 100]` renders as `58.3` (mean), not the trailing `100`; subsequent 20-second silence renders as `--`, not the stale `100`.

**Violates:** `Features/Activity/activity-dashboard-improvements.feature.md` criterion 20 (added with this entry).

**Look first:** `Features/TranscodeJob/Models/TranscodeProgressModel.py` (the source -- single-sample model, no smoothing primitive), `Features/TranscodeJob/Worker/EncodeExecutor.py` (where progress samples are written), `Templates/Activity.html` (where FPS / Speed cells are rendered), `Features/Activity/ActivityRepository.py` (if any server-side aggregation should happen there instead of the client).

**Related:** BUG-0040 (Second concurrent job shows first job's progress) -- same family of progress-rendering issues; consider whether 0057's smoothing window addresses or compounds 0040.

**Fix with:** `/t BUG-0057`

---

### [BUG-0056] [SUPERSEDED BY BUG-0062 2026-06-12] Compliance engine writes contradictory rows -- IsCompliant=TRUE alongside non-null WorkBucket / OperationsNeededCsv
**Date:** 2026-06-12 | **Area:** compliance | **Status:** Folded into BUG-0062 compliance-writeback-invariant cluster; evidence preserved below.

**What breaks:** The new compliance engine (shipped 2026-06-09 via `compliance-solid-refactor` directive) materializes per-row recompute results to `MediaFiles` via `ComplianceWriteRepository.BulkWriteRecomputeResults`. The decision contract in `compliance.feature.md` C3 says bucket precedence is mutually exclusive: empty `OperationsNeeded` -> bucket None / `IsCompliant=True`; any operation needed -> bucket assigned / `IsCompliant=False`. The written rows violate this -- 5703 rows currently hold `IsCompliant=TRUE` AND a non-null `WorkBucket` AND a non-empty `OperationsNeededCsv` simultaneously.

**Live-DB evidence (2026-06-12):**

| IsCompliant | rows | also has WorkBucket | also has OperationsNeededCsv |
|---|---|---|---|
| False | 24942 | 22268 | 22268 |
| True | 21162 | **5703** | **5703** |
| NULL | 4387 | 8 | 8 |

Breakdown of the 5703 contradictory rows:

| WorkBucket | OperationsNeededCsv | rows |
|---|---|---|
| Transcode | Transcode | 2305 |
| Remux | Remux | 2239 |
| Remux | AudioFix,Remux | 1097 |
| Transcode | Remux,Transcode | 62 |

**Sample rows (all `ComplianceEvaluatedAt = 2026-06-09 22:06:04`):** Eight `The Sandman` + `The Real Housewives of Rhode Island` `-mv.mp4` files, all `Codec='av1'` `ResolutionCategory='720p'` `AssignedProfile='NVENC AV1 P7 CANARY VBR -720p'` -- written by the post-engine-ship recompute pass as both compliant AND needing transcode.

**Root cause hypotheses (defer to `/t`):**
1. Tuple-building code that calls `BulkWriteRecomputeResults` computes `IsCompliant` from a source OTHER than `ComplianceDecision.IsCompliant` (the writeback unpacks tuple `(Id, AssignedProfile, PriorityScore, IsCompliant, DeferReason, WorkBucket, OperationsNeededCsv, ComplianceGateBlocked)` at `ComplianceWriteRepository.py:11-38` and SETs the row verbatim).
2. `ComplianceDecision.IsCompliant` is itself set without consulting `OperationsNeeded`.
3. `ComplianceBucketResolver.Resolve` or `ComplianceEvaluator.Evaluate` returns a Decision whose fields contradict each other.

**Mitigating factor:** Zero of the 5703 contradictory rows are currently in `TranscodeQueue`. They are not blocking active work. But the operator-facing "compliant" count on `/Activity` is overstated by ~5700 files, the `/api/Compliance/Buckets` widget under-counts bucketed work, and any UI/code that reads `IsCompliant` to gate work makes wrong decisions on these rows.

**Cross-link with BUG-0055:** Some frequently-failing MediaFiles also carry weird compliance flags -- e.g. `Id 13275 Drake & Josh S02E02` shows `IsCompliant=TRUE / WorkBucket=NULL / 9 failed TranscodeAttempts`. Same-symptom family: the engine's contract isn't being honored end-to-end.

**Success criteria for the fix:**

1. Audit the path from `ComplianceEvaluator.Evaluate -> ComplianceDecision -> RecomputeForFiles tuple build -> BulkWriteRecomputeResults` and identify which step lets the IsCompliant/Bucket contradiction through.

2. Fix the root cause (engine, tuple build, or both) so a fresh recompute writes rows that satisfy the C6 SQL invariant: `(IsCompliant=TRUE AND WorkBucket IS NULL AND OperationsNeededCsv IS NULL/'') OR (IsCompliant=FALSE AND WorkBucket IS NOT NULL AND OperationsNeededCsv IS NOT NULL) OR (IsCompliant IS NULL AND ComplianceGateBlocked IS NOT NULL)`.

3. Add `Tests/Contract/TestComplianceWriteConsistency.py` that runs the SQL invariant query against the live DB and asserts zero violating rows. Run on every CI pass.

4. One-shot remediation: run a full library recompute (`POST /api/Compliance/Recompute` with `All=true`) after the fix lands. Verify the contradictory-row count drops to 0. The fix is incomplete if writeback consistency requires the recompute to be re-run.

5. Add a single-row trace assertion in the bulk-write loop: log a WARN with `MediaFileId + Decision fields` whenever a row is about to be written that violates the invariant, before the write happens. Loud-failure principle (R6 / R12 spirit) -- silent contradictions are the original sin.

**Violates:** `Features/Compliance/compliance.feature.md` criterion 6 (added with this entry). Functionally also violates criteria 2 (ComplianceDecision shape: `IsCompliant: Optional[bool]` + `OperationsNeeded: FrozenSet[str]` are coupled by C3 precedence) and 3 (BucketResolver precedence rules).

**Look first:** `Features/Compliance/Services/ComplianceEvaluator.Evaluate` (does the Decision it returns satisfy the precedence?), `Features/Compliance/Services/ComplianceBucketResolver.Resolve` (is it called with the right OperationsNeeded set?), the `RecomputeForFiles` tuple-build site (search `BulkWriteRecomputeResults` callers in `Features/TranscodeQueue/QueueManagementBusinessService.py` line 1852 `RecomputeForFiles` body), `Features/Compliance/Services/ComplianceRecomputeService.Recompute` (the admin recompute path).

**Fix with:** `/t BUG-0056`

---

### [BUG-0055] [SUPERSEDED BY BUG-0061 2026-06-12] TranscodeQueue has no encode-failure cap; failing jobs re-queue indefinitely via compliance recompute
**Date:** 2026-06-12 | **Area:** transcode-queue | **Status:** Folded into BUG-0061 failure-accounting cluster; evidence preserved below.

**What breaks:** A job that fails to encode (FFmpeg crash, FFprobe failure, FileReplacement failure, source unreachable) writes `TranscodeAttempts(Success=FALSE)` and the queue row is DELETEd. The next `QueueManagementBusinessService.RecomputeForFiles` re-evaluates compliance and INSERTs a fresh queue row -- the file is still non-compliant, the compliance engine doesn't consult prior failure history. Loop: fail -> delete -> recompute -> re-insert -> fail again.

**Asymmetric retry policy:** VMAF-failed encodes are capped at `PostTranscodeGateConfig.MaxRequeueAttempts=3` via `Features/QualityTesting/Disposition/RetryBudgetService.HasBudgetRemaining`, which counts `TranscodeAttempts WHERE Success=TRUE AND VMAF<MinThreshold`. Encode-failed attempts (`Success=FALSE`) have NO analogous cap. The claim path filters only on `Status='Pending'` + capability + NVENC + AllowedProfiles -- no failure-count predicate. `grep -rn "FailureCount\|PriorFailures\|HasFailedAttempts" Features/Compliance/` returns zero matches.

**Live-DB evidence (2026-06-12):**

| MediaFileId | File | Failed attempts | Span |
|---|---|---|---|
| 619064 | Mune Guardian of the Moon (2015) Bluray-1080p.mkv | 15 | 2026-05-31 -> 2026-06-08 (8 days) |
| 7072 | Survivor S36E01-E02 SDTV-720p-mv.mp4 | 13 | 17 hours |
| 18691, 18695 | Celebrity Family Feud S04E05/E07 WEBDL-480p-mv.mp4 | 10 each | 14 hours |
| 615238 | The Hunting Party S02E07 WEBDL-480p.mp4 | 10 | 2 days |
| 614226 | -- | 8 | 21 days, last 2026-06-11 (still failing) |

Plus 1455 orphan failures with `MediaFileId=NULL` going back to 2025-10-15 -- queue rows that never carried a MediaFileId; needs a separate cleanup script.

**Success criteria for the fix:**

1. A configurable per-MediaFile encode-failure cap (sibling to `MaxRequeueAttempts`, default 3) stops re-queueing after N consecutive `TranscodeAttempts.Success=FALSE` rows since the last `Success=TRUE` (or since file creation if no prior success). DB-fresh read per claim or per recompute (db-is-authority).

2. The cap is consulted in BOTH the claim path (`ClaimNextPendingTranscodeJob` skips Pending rows whose MediaFile has exceeded cap -- defense in depth) AND the recompute path (`RecomputeForFiles` does not INSERT a new queue row for a MediaFile that has exceeded cap).

3. Capped MediaFiles are visible to the operator in a troubleshooting surface. Operator sees filename, failure count, last `ErrorMessage`, last `AttemptDate`, `AssignedProfile`, last `WorkerName`. Operator can (a) reset (re-allow next claim), (b) view full attempt log for the file, (c) take no action. Reasonable home: `/Activity` page (new "Failed Jobs" panel) or new `/FailedJobs` page; defer placement decision to `/t`-time.

4. Capped MediaFiles MUST NOT appear in any `/ShowSettings` "Next batch" table -- TV Next Batch, Movies Next Batch, Quick Fix, legacy Remux / AudioFix Next Batch. Verifiable: insert N+1 consecutive failures for MediaFileId X (where N=cap), confirm X is absent from every `/ShowSettings` Next-batch card; reset X and confirm it re-appears.

5. The 1455 orphan failures (`TranscodeAttempts.MediaFileId IS NULL`) get a one-shot cleanup script. Decide at `/t`-time whether to dedupe by `ErrorMessage+AttemptDate` or just archive.

6. Reset semantics: when operator clears a capped MediaFile, the next claim is allowed even though `TranscodeAttempts` history is unchanged. Implementation choice (timestamp on `MediaFiles`, separate `ResetFailureCountAt` column, audit table) is a `/t` decision.

**Violates:** `Features/TranscodeQueue/TranscodeQueue.feature.md` criterion 10 (added with this entry), `Features/TranscodeQueue/next-batch-per-drive.feature.md` criterion 12 (added with this entry).

**Not in scope:** Changing the FFmpeg pipeline. Changing what counts as a failure. Reworking compliance evaluation (BUG-0056 covers that). The VMAF retry budget (already exists and works).

**Look first:** `Features/TranscodeQueue/TranscodeQueueRepository.ClaimNextPendingTranscodeJob` (lines 270-364, claim WHERE clause), `Features/TranscodeJob/ProcessTranscodeQueueService.HandleJobFailure` (line 1100, DELETE at 1144), `Features/TranscodeQueue/QueueManagementBusinessService.RecomputeForFiles` (re-INSERT at lines 609, 696), `Features/QualityTesting/Disposition/RetryBudgetService` (sibling pattern -- mirror its shape for encode failures), `Features/QualityTesting/PostTranscodeGateConfigRepository` (add `MaxEncodeFailures` column alongside `MaxRequeueAttempts`).

**Fix with:** `/t BUG-0055`

---

### [BUG-0046] Legacy acompressor+dynamic-loudnorm chain damaged 8,249 library files; population is closed but damage is permanent
**Date:** 2026-06-08 | **Area:** audio-pipeline

**What happened:** Between 2025-10-03 and 2026-05-30 the production audio-filter chain was `acompressor=threshold=-15dB:ratio=3:attack=0.01:release=0.1:makeup=3dB,loudnorm=I=-23:LRA=7:TP=-2`. The `linear-loudnorm.feature.md` design replaced this with linear-mode loudnorm starting 2026-05-25; the transition completed 2026-05-30.

**Scope:** 8,249 audio-bearing files were processed under the legacy chain. Split: 22 movies + 8,227 TV episodes. Population is closed -- no new files entering since 2026-05-25.

**Damage profile:** Irreversible. The acompressor reduced peaks above -15 dB at a 3:1 ratio with 3 dB makeup gain; the dynamic-mode `loudnorm LRA=7` then forced everything into a 7-LU loudness range envelope. Dynamic range was compressed and peaks were limited in ways that cannot be recovered from the encoded output. Films/cinematic content with native LRA 12-20+ LU took audible damage; TV-series content with native LRA 5-8 LU took subtle damage that is typically inaudible.

**Affected file list:** `Reports/LegacyAudioDamagedMovies.csv` lists 18 rows post-operator-triage (down from 22; see `### Operator triage 2026-06-08` below). The 8,227 TV episodes are queryable via `Scripts/IdentifyLegacyDamagedMovies.py` with the `seasonid IS NULL` and filename regex filters removed.

**Operator triage 2026-06-08:**
- 17 rows on storage root `xxx` flagged `AudioDamageNotMaterial=TRUE` -- adult content; loudness fidelity not operationally meaningful for this share. No remediation planned.
- 4 rows on storage root `media_tv` (LOONEYTOONS_SHOW_SEASON_1_VOL2.Title3-6, MediaFileIds 39551-39554) DELETED from disk + MediaFiles + dependent rows (32 TranscodeAttempts + 4 TranscodeFiles + 4 MediaFiles, all committed). These were unrenamed DVD-title rips in `Minnie's Bow-Toons` folder.
- 1 row on storage root `media_tv` (Firefly Serenity Pilot 2002, MediaFileId 1980) KEPT with `AudioDamageNotMaterial=FALSE`. Operator declined deletion -- pilot is a legitimate TV-movie worth keeping despite audio damage.

**Why not remediated:** Zero of the 8,249 files have `MediaFiles.KeepSource=TRUE` -- the original sources were deleted by FileReplacement post-flight in every case. Full re-transcode from MediaVortex-managed source is impossible. Audio-only re-pass (considered + closed as `audio-renorm-legacy` directive) does not recover dynamic range or peak fidelity -- it would only re-normalize the loudness of already-damaged audio. External re-acquisition (Sonarr/Radarr/manual) for the 22 movies is the operator-driven recovery path; the 8,227 TV episodes are accepted as historical loss.

**Forward-guarantee:** `Tests/Contract/TestLinearLoudnormEnforcement.py` greps the python tree for the legacy chain literal + `acompressor=` and asserts production code is clean. `Models/CommandBuilder.BuildAudioFilters` now raises `RuntimeError(ungainable_peak)` on the case that previously triggered the dynamic-mode fallback -- "linear or refused" is now mechanically enforced, not just documented.

**Look first:** `Reports/LegacyAudioDamagedMovies.csv` (the operator-actionable subset), `Features/LoudnessAnalysis/linear-loudnorm.feature.md` (forward policy), `Tests/Contract/TestLinearLoudnormEnforcement.py` (regression guard), `.claude/directives/closed/2026-06-08-legacy-audio-damage-accounting.md` (full directive context).

---

### [BUG-0045] Directive anchor convention + hook validators are too loose for shared / hot functions
**Date:** 2026-06-08 | **Area:** standards-hook

**What breaks:** Three related gaps in how `pre-edit-standards.ps1` validates the `# directive: <slug> | # see <slug>.<ID>` anchor on a `def`/`class`. All three surface as the same operator-visible pain: shared functions touched by multiple directives end up with either lost provenance (operator "replaces" the anchor to avoid R12) or silently-wrong anchors (active directive's slug not present, see-ID typo'd against the active directive).

**Three sub-items, ship in one follow-up directive (`/n anchor-convention-comma-separated`):**

1. **R12 refusal message should TEACH the comma-separated format** when the stacked-`#`-lines pattern is two consecutive `# directive:` anchors. Today the message says "one-line max; rationale belongs in the directive doc" -- which is misleading because the right fix is NOT to delete one anchor or move rationale to the directive doc; it is to MERGE the two anchors into one line as `# directive: slug-a, slug-b | # see slug-a.C1, slug-b.C5`. The Path-Forward text should detect "both lines are directive anchors" and suggest the merge format with a worked example. Surfaced twice this session: worker-routing (replaced path-schema anchor on ClaimNextPendingTranscodeJob, losing breadcrumb) and local-staging (attempted to stack on CreateTemporaryFilePath, R12 fired with misleading guidance).

2. **R15 should validate the ACTIVE directive's slug is present in the list**, not just "any slug present." Today the hook's regex `#\s*directive:\s*[a-z0-9-]+` matches the first slug it finds. An operator could leave only a closed-directive anchor on an edited function and the hook would pass -- the active directive's provenance would be missing from the code. Fix: parse `.claude/directive.md` for the active slug, then ensure that slug is one of the comma-separated tokens on the anchor line.

3. **R15 `# see` should validate the criterion ID against the ACTIVE directive doc**. Today the regex `#\s*see\s+[a-z0-9-]+\.(S|W|C|ST)\d+` checks shape only -- a typo like `local-staging.C77` (instead of `C7`) passes regex but doesn't resolve to any real criterion. Fix: when the see anchor names the active directive's slug, parse the directive's `## Acceptance Criteria` section and confirm the cited ID exists. Closed-directive see anchors (e.g. `path.S8` for a closed `path-schema-migration` directive) are unverifiable post-close, so skip validation for those -- only enforce the live one.

**Convention to codify (in `.claude/rules/ceo-mode.md` and/or `.claude/standards/index.md` R15 row):**

```
# directive: slug-a, slug-b, slug-c | # see slug-a.C1, slug-b.C5, slug-c.C7
def SharedHotFunction(...):
```

- One line per function (R12 OK).
- Slugs accumulate in chronological order (oldest -> newest left to right).
- When a directive closes, its slug stays as a historical breadcrumb (preserves "this function was touched by directive X" for future archaeology).
- Active directive (rightmost typically) gates the current edit (R15 enforced via #2 above).
- `# see` carries one ID per slug, comma-separated in matching order.

**Look first:** `.claude/hooks/pre-edit-standards.ps1` -- `Test-R12-CommentVolume` (for sub-item 1: add a "is this a stacked-directive-anchors block?" detector + a path-forward message variant), `Test-R15-DirectiveAnchor` (for sub-items 2 + 3: parse active directive doc for slug + criterion IDs and validate against the anchor line). `.claude/rules/ceo-mode.md` -- add the comma-separated convention example. `.claude/standards/index.md` R15 row -- update description.

**Fix with:** `/n anchor-convention-comma-separated` -- single directive, ~3 hook functions touched, one rule doc updated, one standards row updated. Out of scope: retroactively converting every existing single-anchor function in the codebase (do that opportunistically when each is touched next).

---

### [BUG-0044] CpuAffinityService loses its SystemSettingsRepository wiring on every worker startup -- config knobs silently ignored
**Date:** 2026-06-06 | **Area:** worker-lifecycle

**What breaks:** On every WorkerService startup, `CpuAffinityService._LoadConfig()` raises `AttributeError: 'CpuAffinityService' object has no attribute 'SystemSettingsRepository'`. The exception is caught -- the service then logs `INFO CpuAffinityService initialized` 4 ms later and proceeds to pin P-cores correctly using hardcoded defaults. But the SystemSettings-driven knobs covered by `Features/SystemSettings/SystemSettings.feature.md` criterion 3 (temperature threshold, monitoring interval, cooling wait) never actually take effect on the worker. Whatever is configured in the SystemSettings table is silently overridden.

**Repro:** Restart WorkerService on any host (observed on I9-2024). Within ~15 s of `Worker is Online`:
```sql
SELECT TimeStamp, Message FROM logs
WHERE FunctionName='CpuAffinityService' AND LogLevel='ERROR'
ORDER BY TimeStamp DESC LIMIT 1;
```
returns the AttributeError. Observed timestamps this session: `2026-06-06 22:01:31.540373` on PID 21252.

**Evidence:** Adjacent commit `d0d48b3 fix(worker-init-ordering): move repo field assignments before _RegisterAndLoadWorkerConfig() call` (2026-06-06) fixed the same shape of bug on a different service. The CpuAffinityService init path apparently expects `self.SystemSettingsRepository` to be assigned before `_LoadConfig()` runs, and that assignment is either missing or happening in the wrong order. After the AttributeError, the service still emits `Hybrid=True, Detection=GetSystemCpuSetInformation, P-cores=[0..15], E-cores=[16..31]` and successfully pins both concurrent transcode jobs (30344, 30345) -- so the regression is observability-only at runtime, not functional. The hidden cost is that operator-configured thermal knobs do nothing.

**Violates:** `Features/SystemSettings/SystemSettings.feature.md` criterion 13 (added with this bug). Indirect impact on criterion 3 (configured values are not actually controlling behavior).

**Same shape, sibling case — broaden the fix to cover both:** `StuckJobDetectionService` raises `'StuckJobDetectionService' object has no attribute 'ActiveJobRepository'` on every sweep cycle (observed 26 occurrences in a 35-minute window 2026-06-06 21:10:17 - 21:45:48). Each stuck-job check for a candidate job ID raises and is caught, so the sweep silently no-ops on every candidate. Same root cause class: a repo attribute the service expects is not assigned before the method that reads it runs. Fix scope for `/t BUG-0044` should be "audit every WorkerService-owned service `__init__` for missing repo attributes that `_LoadConfig` / sweep methods rely on," not just CpuAffinityService.

**Look first:**
1. `Services/CpuAffinityService.py` -- `__init__` and `_LoadConfig`. Look for the line that references `self.SystemSettingsRepository`; trace where the attribute is supposed to be assigned and confirm the call ordering matches the d0d48b3 fix pattern.
2. `Services/StuckJobDetectionService.py` -- same audit: `self.ActiveJobRepository` is referenced but never assigned in `__init__` (or assigned after the method that uses it).
3. `WorkerService/Main.py` -- service wiring during worker boot; compare to the sibling fix in d0d48b3 to see which repos are now assigned pre-config-load and which were missed.
4. `Repositories/SystemSettingsRepository.py` + `Repositories/ActiveJobRepository.py` -- confirm the expected interfaces both services are trying to call.

**Flow doc:** `WorkerService/WorkerService.flow.md` covers worker startup including service init -- `/t` should verify the init-ordering contract is captured there before fixing.

**Fix with:** `/t BUG-0044`.

---

### [BUG-0020] Workers must own their processes end-to-end, and `-mv` must only be appended when the output is actually compliant
**Date:** 2026-05-26 | **Area:** worker-lifecycle / file-replacement

**What breaks (two coupled gaps):**

1. **End-to-end ownership.** Workers do not own the lifecycle of the processes they spawn. When a worker's encode finishes but a downstream step (FileReplacement, VMAF dispatch, TFP cleanup) fails or races a sibling sweep (see BUG-0018), the partial artifact survives as a disk and/or DB orphan. The worker that created the artifact is in the best position to clean it up -- it knows its own attempt ID, its own `.inprogress` path, and whether FileReplacement returned success. Today that responsibility is split across multiple services (OrphanCleanupService, scan adoption, manual scripts), creating the BUG-0015 + BUG-0018 lifecycle holes we are currently mitigating by hand.

2. **Premature `-mv` naming.** A file is renamed to `<basename>-mv.mp4` once FFmpeg returns 0 and the FFprobe sanity check passes (`worker-lifecycle.feature.md` criterion 8). But "FFmpeg produced a valid MP4" is not the same as "the output is compliant" -- the rename can land on a file that still has wrong audio, missed loudnorm, oversized output (no-savings refusal), or any other downstream-detectable defect. The next scan / cascade recompute then sees a `-mv.mp4` path and assumes work is done, when in fact the file would still get picked up by a remux / audio / transcode job if it were re-evaluated.

   Stronger rule: `-mv` should only be appended when the output passes the same compliance gate that the cascade uses to decide whether a file needs work. If the output would still get re-queued, the rename is misleading at best, an infinite-loop risk at worst (re-encode produces same non-compliant output, `-mv-mv.mp4` grows another generation each cycle -- see Doctor Who / Love Death Robots ghost-row pattern this session).

**Success criteria for the real fix:**
1. A worker process that produces a `.inprogress` file is responsible for that file's terminal state. On any non-success exit (encode failure, FFprobe failure, FileReplacement failure, kill/crash mid-flow), the same worker deletes the `.inprogress` before releasing the active-job slot. No other service is permitted to delete `.inprogress` files belonging to a live worker.
2. A worker that completes an encode AND succeeds at FileReplacement is responsible for the post-replacement state (TFP cleanup, MediaFile row update). No other service may touch TFP rows for an attempt whose owning worker is alive.
3. The `-mv.mp4` rename happens only after compliance is verified against the same predicate the cascade uses (`NeedsQuick`, `NeedsTranscode`, audio criteria, savings gate). If the candidate output would still be re-queued by the cascade, the worker must not rename and must instead emit a non-Replace disposition with the audit trail naming which compliance check failed.
4. Crash recovery on worker startup (`worker-lifecycle.feature.md` C11-C13) remains the safety net for the case where the worker died before reaching its own cleanup. Crash recovery operates only on rows OWNED by the restarting worker.
5. After the fix, the operator-run scripts (`CleanupSourceFileOrphans.py`, `CleanupStaleInProgressFiles.py`, `CleanupGenerationalGhostRows.py`, `CleanupOrphanMvPairs.py`) should report zero candidates on a fresh fleet pass -- if they find candidates, that is a worker bug, not an expected sweep target.

**Violates:**
- `WorkerService/worker-lifecycle.feature.md` criteria 8-13 (rename / cleanup ownership)
- `Features/FileReplacement/FileReplacement.feature.md` (transition contract)
- The compliance contract enforced by the cascade in `Features/TranscodeQueue/QueueManagementBusinessService._EvaluateCompliance`

**Related:** BUG-0015 (disk orphans), BUG-0016 (DB ghost-row pairs), BUG-0018 (TFP sweep race). All three are downstream symptoms of the ownership gap this bug names. Fix them together as a single "worker process ownership + compliance-gated rename" feature pass.

---

### [BUG-0007] Worker capability toggle does not refresh UI until modal is closed and reopened
**Date:** 2026-05-22 | **Area:** activity-page

**What breaks:** Clicking a capability switch on a worker tile / modal on the `/Activity` page (TranscodeEnabled / QualityTestEnabled / ScanEnabled / RemuxEnabled) hits `POST /api/TeamStatus/Workers/<name>/<Capability>` and the DB row updates correctly, but the on-screen toggle stays in its pre-click position until the operator closes the modal and reopens it (or reloads the page). The handler appears to fire-and-forget without re-rendering from the fresh server payload.

**Repro:** Open `/Activity`. Click a worker to open its modal (or expand its tile). Toggle any capability switch. Without closing the modal, observe the switch position. Query `SELECT TranscodeEnabled FROM Workers WHERE WorkerName=<name>` -- the DB value has flipped, but the UI still shows the old value. Close the modal and reopen it; UI now matches the DB.

**Evidence:** The capability poller is doing its job (`Features/ServiceControl/capability-control-plane.feature.md` criteria 2-4 still hold -- the backend loop starts/stops within 60-90s of the flip). The bug is strictly UI: the post-toggle handler does not call the same render function that initial-load uses, so the modal's component state drifts from server state until next open.

**Violates:** `Features/Activity/activity-dashboard-improvements.feature.md` criterion 18 (added with this bug).

**Look first:** `Templates/Activity.html` -- `ActivityPage.ToggleWorkerCapability` (around the `/api/TeamStatus/Workers/<name>/<Capability>` fetch call). The success branch returns without re-fetching `/api/TeamStatus/Workers` or re-rendering the modal contents. Compare with how the modal is initially populated and pull the same render path into the success handler. Related: `CapabilityRow(...)` builder used in worker tile rendering.

**Fix with:** `/t BUG-0007`.

---

### [BUG-0002] Media files with zero audio streams persist in DB after silent-output Remux -- must be purged with full FK history
**Date:** 2026-05-16

**What breaks:** Multiple `MediaFiles` rows have a non-NULL `AudioBitrateKbps` value but the actual on-disk file has zero audio streams. The Remux pipeline successfully ran, replaced the source, and updated the DB without catching that the output was silent. The post-replacement re-probe in `_UpdateMediaFilesAfterReplacement` failed to clear or flag the missing audio — instead the pre-Remux `AudioBitrateKbps` was kept and `AudioCodec` ended up NULL. So the DB now contains "ghost audio" rows pointing at silent files.

**Confirmed silent on disk via ffprobe** (sample of 4 of the 16 NULL-codec candidates):
- `T:\Doctor Who (2005)\Specials\Doctor Who (2005) - S00E72 - Doctor Who in America SDTV-720p-mv.mp4`
- `T:\Monk\Season 7\Monk - S07E08-E09 - Mr. Monk Gets Hypnotized + Mr. Monk and the Miracle WEBDL-480p-mv.mp4`
- `T:\Shameless\Season 1\Shameless - S01E06 - Monica Comes Home (1) SDTV-720p-mv.mp4`
- `T:\Xena - Warrior Princess\Season 1\Xena - Warrior Princess - S01E05 - The Path Not Taken DVD-720p-mv.mp4`

Each has a video stream (HEVC) but no audio stream at all. The 16-file NULL-codec set is a lower bound — files where the pre-probe captured a codec name will not be caught by `AudioCodec IS NULL` alone, so the actual silent population is likely larger. Definitive identification requires `ffprobe` against every transcoded file.

**Why the DB can't be trusted as the source of truth:** `AudioBitrateKbps` was kept from the pre-Remux source instead of being NULL'd. `AudioCodec` ended up NULL only by accident on a subset of files. Any silent file whose re-probe happened to keep both fields populated is undetectable from the DB. Conclusion: the re-probe in `_UpdateMediaFilesAfterReplacement` must overwrite every audio column based strictly on what the post-replacement file actually contains — present audio populates them, absent audio NULLs them and triggers Discard. No partial updates, no defaulting to source values.

**What the user wants:** purge these rows from the DB entirely (along with the on-disk silent file) and record every removed path so they can be re-acquired from source.

**Cleanup behavior (per criterion 19 on `post-transcode-pipeline.feature.md`):**
1. ffprobe every `MediaFiles` row (or every `TranscodedByMediaVortex = true` row as a faster first pass) to identify rows whose file has zero audio streams.
2. For each silent file: delete the row and every dependent record in `TranscodeAttempts`, `TranscodeFiles`, `MediaFilesArchive`, `QualityTestResults`, `QualityTestProgress`, `TranscodeQueue`, `QualityTestingQueue`, `ActiveJobs`, `TemporaryFilePaths`, `ScanJobs` (if linked), `ProblemFiles` (if linked). One transaction per file.
3. Before the row is deleted, append its `RelativePath` (fallback `FilePath`) to a timestamped report at the repo root: `deleted-silent-files-YYYY-MM-DD.md`, grouped by show, so the operator can re-acquire.
4. Delete the silent file from disk.
5. Going forward, harden `_UpdateMediaFilesAfterReplacement` to fail loud when the re-probe finds no audio — `Discard` disposition, on-disk silent output removed, source restored if `.orig`/`.inprogress` is still recoverable.

**Violates:** `Features/FileReplacement/post-transcode-pipeline.feature.md` criterion 19 (added with this bug). Indirectly: the missing MediaProbe feature doc (no `Features/MediaProbe/*.feature.md` exists) means the re-probe contract has no owner — flag the gap, /t should create one when fixing.

**Related (not duplicate):** `### [BUG] Next Remux Batch table shows files with no audio stream that silently fail when queued` (2026-05-14, line 200) covers the *upstream* problem of queueing video-only files that error out with code 4294967274. BUG-0002 is the *downstream* problem of files that successfully completed Remux but came out silent and now sit in the DB with stale audio metadata. Different failure mode (success-with-no-audio vs explicit failure), different cleanup need (purge + report vs exclude from queue).

**Look first:**
- `Features/FileReplacement/FileReplacementBusinessService.py` — `_UpdateMediaFilesAfterReplacement` (no-audio detection gap, criterion 19 second half).
- `Features/MediaProbe/MediaProbeBusinessService.py` — the probe call that ought to surface zero-audio explicitly.
- DB foreign-key map: `TranscodeAttempts.MediaFileId`, `TranscodeFiles.MediaFileId`, `MediaFilesArchive.Id` (shared PK), `QualityTestResults.TranscodeAttemptId`, `QualityTestProgress.TranscodeAttemptId`, `TemporaryFilePaths.TranscodeAttemptId`, `ActiveJobs.QueueId` (polymorphic — see BUG-0001 criterion 16).
- Sample file paths above for `ffprobe` verification before/after.

**Fix with:** `/t BUG-0002`.

---

---

### [BUG-0029] TranscodeAttempts failure rows lack ProfileName -- operator cannot tell what KIND of job failed from the row alone
**Date:** 2026-05-16

**What breaks:** When a remux or transcode job fails early (pre-flight, pre-FFmpeg), the resulting `TranscodeAttempts` row has `Success=False` and `ErrorMessage` populated (loud failure IS in the DB), but `ProfileName=NULL`. The queue row was DELETEd by the failure handler so its `ProcessingMode` context is gone. Operator looking at the row can see "this attempt failed with this error" but not "this was a Remux job" vs "this was an SVT-AV1 transcode." They must join `MediaFiles` via `MediaFileId` to recover even partial context.

Confirmed against attempts 16240-16243 on 2026-05-16: 4 remux jobs failed with `"No active StorageRootResolutions row for (StorageRootId=None, WorkerName='...')"`. All 4 rows have `ProfileName=NULL`. The triggering test-setup script inserted queue rows without `StorageRootId`/`RelativePath` (script bug, not production bug), but the observability gap is real for ANY early failure in production too.

**Note on FilePath=NULL:** That is BY DESIGN per the existing entry "FilePath used as denormalized natural key across 6+ tables" -- FilePath was removed from TranscodeAttempts INSERTs as part of the denormalization cleanup. Operators join via MediaFileId for path. ProfileName is NOT in that denormalization scope; it should be populated.

**Violates:** `Features/TranscodeJob/TranscodeJob.feature.md` criterion 30 (added with this entry). Adjacent to criterion 29 (ErrorMessage content) -- this entry owns the ProfileName slice of the same "diagnose from attempts table alone" contract.

**What "fixed" looks like:** Every `TranscodeAttempts` INSERT in the failure path sets `ProfileName` -- from the queue row's `ProcessingMode='Remux'` literal for remux jobs, from the resolved transcode profile name for transcode jobs -- regardless of how early in the pipeline the failure occurs. Verifiable: trigger a remux job that fails at the `Resolve()` call (e.g. insert a queue row with `StorageRootId=NULL`); query the resulting `TranscodeAttempts` row; observe `ProfileName='Remux'`.

**Look first:** `Features/TranscodeJob/ProcessTranscodeQueueService.py` and `Features/TranscodeJob/ProcessRemuxQueueService.py` -- the failure path in `_ProcessJob` (or equivalent) that creates the TranscodeAttempt row when an exception is caught early. The fix is to populate `ProfileName` from the queue context BEFORE the work begins, not after.

---

### [BUG-0024] FindFuzzyFileMatch is O(N x M) -- reloads + regex-parses all RootFolder rows per new file
**Date:** 2026-05-15

**What breaks:** Every NEW file the scanner discovers triggers `FindFuzzyFileMatch`, which:
1. Calls `Repository.GetMediaFilesByRootFolderId(RootFolderId)` -- returns ALL MediaFiles rows for that RootFolder (for T:\, that is ~45,000 rows; multi-MB transfer through psycopg2).
2. Calls `ExtractShowInfo` (regex parse) on every loaded row's `FileName`.
3. For any candidate that passes the IsFuzzyMatch shape check, stats the candidate path over NFS.

The 5-thread parallel pool in `ProcessMediaFiles` means every new-file slot does this independently and concurrently -- the same 45k rows get loaded 5 times in parallel.

Confirmed against I9-2024 scan #64925 on 2026-05-15: ~22 new Graham Norton episodes were taking 3-5 seconds each. That is 22 x (45k DB load + 45k regex parses) = 990,000 ops where 22 dict lookups would suffice. For larger libraries the per-file cost grows linearly with library size -- O(N x M) where N is new files and M is RootFolder size.

Same anti-pattern family as criterion 23 (per-file work that should be precomputed once per scan) but a distinct code path: `FindMovedFile` (covered by 23) vs `FindFuzzyFileMatch` (this entry).

**Violates:** `Features/FileScanning/FileScanning.feature.md` criterion 25 (added with this entry).

**What "fixed" looks like:**
- In `PerformScan`, after `GetOrCreateRootFolder` succeeds, do a single `GetMediaFilesByRootFolderId(RootFolder.Id)` call.
- Build a `{(ShowName, Season, Episode): [DbFile, ...]}` index from that result. Skip rows where `ExtractShowInfo` returns empty parts -- they cannot be fuzzy-matched anyway.
- Pass the index through `ProcessMediaFiles -> ProcessSingleMediaFile -> FindFuzzyFileMatch` (or hold it on `self` for the duration of a single `PerformScan`).
- `FindFuzzyFileMatch` looks up `Index[(ShowName, Season, Episode)]` -- O(1) -- and runs the existing `IsFuzzyMatch` size check + `os.path.exists` candidate validation on the small candidate list.
- Index is read-only after build, safe for the parallel pool (same threading model as the filename index in `ReconcileWithDisk`).
- Verifiable: trigger a scan that introduces N new files; observe per-new-file wall-clock under 100ms instead of 3-5 seconds.

**Look first:** `Features/FileScanning/FileScanningBusinessService.py` -- `FindFuzzyFileMatch` (~line 685), called from `ProcessSingleMediaFile` new-file branch (~line 785). `PerformScan` (~line 313) is where the index should be built. The `ReconcileWithDisk` filename-index pattern (the criterion 23 fix in the same file) is the template.

---

### [BUG-0024] ScanJobs NewFiles / UpdatedFiles / DeletedFiles counters stay at zero
**Date:** 2026-05-15

**What breaks:** A scan in progress writes `ScanJobs.NewFiles=0, UpdatedFiles=0, DeletedFiles=0` even when MediaFiles rows are being inserted, updated, or deleted. Confirmed mid-scan on 2026-05-15 against I9-2024 scan #64925: the heartbeat showed all three counters stuck at 0 while `SELECT * FROM MediaFiles WHERE LastScannedDate > NOW() - INTERVAL '3 minutes'` returned freshly-inserted rows (IDs 622023-622032 against `T:\The Graham Norton Show\Season 20`). The total-files counter (`ProcessedFiles`) climbs correctly thanks to the criterion 17 heartbeat fix, but the per-disposition breakdown the operator needs to answer "what changed?" is not produced.

**Root cause:** `FileScanResultModel` defines only `TotalFilesFound / TotalFilesProcessed / TotalFilesSkipped / TotalFilesWithErrors`. No fields exist for new / updated / deleted. `ProcessSingleMediaFile` increments `TotalFilesProcessed` uniformly for inserts and updates. `ReconcileWithDisk` (the new code that owns deletes per criterion 23) does not surface its delete count to ScanResults. `UpdateJobStatus` only writes the New/Updated/Deleted columns when a ScanResults model is passed, and even then the model has nothing meaningful in those slots.

**Violates:** `Features/FileScanning/FileScanning.feature.md` criterion 24 (added with this entry). Criterion 17 already names these columns in its contract; criterion 24 owns the per-disposition slice of that contract while criterion 17 owns the heartbeat-cadence dimension.

**What "fixed" looks like:**
- Add `NewFilesCount`, `UpdatedFilesCount`, `DeletedFilesCount` (or matching field names) to `FileScanResultModel`.
- `ProcessSingleMediaFile` insert branch increments `NewFilesCount`; update branch increments `UpdatedFilesCount`. Both protected by the existing `ProgressLock`.
- `ReconcileWithDisk` increments `DeletedFilesCount` per delete and `UpdatedFilesCount` per fuzzy-match reassignment.
- `UpdateJobStatus` writes the three new fields when ScanResults is passed.
- The heartbeat thread (criterion 17 fix) already passes ScanResults -- once the model has the fields, the heartbeat will surface them automatically with no further plumbing.
- Verifiable: trigger a scan that creates N new files, updates M files, deletes K files; observe `SELECT NewFiles, UpdatedFiles, DeletedFiles FROM ScanJobs WHERE Id=<scan>` returns (N, M, K) matching reality.

**Look first:** `Features/FileScanning/Models/FileScanResultModel.py` -- add fields. `Features/FileScanning/FileScanningBusinessService.py` -- `ProcessSingleMediaFile` (insert branch ~line 815, update branch ~line 773), `ReconcileWithDisk` (delete branch and fuzzy-match branch). The thread-safe lock pattern at `ProcessMediaFilesWithMetadata` line ~1503 is the template.

---

### [BUG-0024] Scan triple-stats DB rows over NFS and runs the existence checks single-threaded
**Date:** 2026-05-15

**What breaks:** A continuous-scan iteration on a Windows or Linux worker does the following for every RootFolder:

1. `FileManagerService.ScanDirectory` walks the filesystem (`os.walk`) -- fast (T:\ over NFS: 45,716 files in 10 seconds).
2. `FileScanningBusinessService.DetectMovedFiles` iterates every `MediaFiles` row whose path is under this RootFolder and calls `os.path.exists(_ToLocalPath(DbFile.FilePath))` **serially, single-threaded**. For T:\ with 47,970 rows at ~25ms per NFS stat, this is ~20 minutes of wall-clock blocking before the parallel processor even starts.
3. `CleanupMissingFiles` then runs and does **the same 47,970 `os.path.exists` calls again** -- already called out by criterion 12, still present.
4. For files declared missing in step 2, `FindMovedFile` calls `os.walk` over **every one of 587 RootFolders** looking for a filename match -- exponential cost: O(missing_files x rootfolders x dir_count).
5. `ProcessMediaFiles` (5-thread parallel) then stats each file a **third time** via `FileManager.GetFileSizeMB` / `os.path.getsize` / `os.path.exists` plus a DB lookup, mostly to discover the row hasn't changed.

Worker process memory is fine (~279 MB). The bottleneck is wall-clock from sequential NFS round-trips. Observed T:\ scan #64923 on I9-2024 2026-05-15: 20+ minutes blocked in `DetectMovedFiles` with the heartbeat thread (criterion 17 fix) confirming the process is alive but the scan thread is stat-bound.

**Violates:** `Features/FileScanning/FileScanning.feature.md` criterion 23 (added with this entry). Complements criterion 12 (which owns the cap behavior); this entry owns the throughput dimension of the same `DetectMovedFiles` / `CleanupMissingFiles` / `FindMovedFile` code path.

**What "fixed" looks like:**
- Existence-check work is parallelized with the same `ThreadPoolExecutor(max_workers=5)` pattern `ProcessMediaFiles` already uses, or merged into a single `os.scandir`-driven pass that builds a `{path: stat_result}` dict for the whole RootFolder once and reuses it.
- `DetectMovedFiles` and `CleanupMissingFiles` collapse into one per-row decision so each file is stat'd at most once per scan.
- `FindMovedFile` builds a single `{filename: [paths]}` index from the `os.walk` results once per scan and looks up missing files in O(1) instead of `os.walk`-per-missing-file.
- Verifiable: re-run T:\ scan on a worker against a database whose rows match disk; observe wall-clock under 5 minutes for a no-change pass on ~50k rows.

**Look first:** `Features/FileScanning/FileScanningBusinessService.py` -- `DetectMovedFiles` (~line 1363), `CleanupMissingFiles` (call site immediately after), `FindMovedFile` (~line 1297), and the inner `os.walk` in `FindMovedFile` (~line 1318). The `ProcessMediaFiles` `ThreadPoolExecutor` pattern (~line 1486) is the template to copy. `Services/FileManagerService.py` `ScanDirectory` already produces the `os.walk` result that could feed a `{filename: [paths]}` index.

---

### [BUG-0024] Scan progress writer is silent -- ScanJobs counters and CurrentDirectory don't advance mid-walk
**Date:** 2026-05-15

**What breaks:** A scan triggered via `ContinuousScanService` (or manual `POST /api/FileScanning/Scan/Start`) walks the filesystem but does not update `ScanJobs.ProcessedFiles`, `CurrentDirectory`, or `LastUpdated` until the scan ends. Confirmed against I9-2024 on 2026-05-15: M:\ scan #64919 ran 75s and T:\ scan #64920 ran 4+ minutes, both over NFS (89ms/dir for M:\, 18ms/dir for T:\), and both reported `ProcessedFiles=0`, `CurrentDirectory=NULL`, `LastUpdated=StartTime` for the entire run. From the operator's view, a healthy running scan and a hung scan look identical -- the only safety net is `StuckJobDetectionService` at the 15-minute threshold, which is well past the point where a real hang is impacting throughput.

**Violates:** `Features/FileScanning/FileScanning.feature.md` criterion 17 (promoted to [BUG] with this entry). The criterion text now covers two dimensions: cadence (this entry) AND phase visibility. The phase dimension was added on the same date after observing scan #64925's walk finish (`ProcessedFiles=45716`) while `Status` stayed `Running` for the entire metadata-extraction phase that followed -- `PerformScan` folds `ProbeFilesNeedingMetadata` inside its return, so the operator cannot tell "still walking files" from "files done, now FFprobing." Fix candidates: add a `ScanJobs.Phase` column, or split probe out of PerformScan so Status flips to Completed when the walk finishes and a separate row tracks probe.

**What "fixed" looks like:** During an active scan, `ScanJobs.LastUpdated` advances at least every 5 seconds even if no files changed; `CurrentDirectory` reflects the directory currently being walked; `ProcessedFiles` increments per file visited (not just per file inserted/updated). Verifiable: poll `SELECT LastUpdated, CurrentDirectory, ProcessedFiles FROM ScanJobs WHERE Id=<running-id>` every 5s and observe values advance well before `EndTime` is set.

**Look first:** `Features/FileScanning/FileScanningBusinessService.py` -- the scan-walk implementation called from `ContinuousScanService._ExecuteScan` via `StartScanning`. Find where `ProcessedFiles` increments live and confirm whether the path is taken when files are skipped vs only when files are inserted/updated. Likely fix: lift the increment to the `os.walk` yield (not the per-file work branches), and add a heartbeat write of `LastUpdated` + `CurrentDirectory` every N seconds independent of file count.

---

### [BUG-0025] Worker status model is overcomplicated -- Draining state is broken, invisible, and unnecessary
**Date:** 2026-05-14

**What breaks:** Three related problems in the worker status/capability system:

**(1) Draining doesn't stop remux.** `_HandleStatusChange("Draining")` sets `StopRequested` on TranscodeService, stops QualityTestService, and stops ContinuousScanService -- but has no awareness of RemuxService (added later). Remux jobs keep being claimed during the entire drain window. The drain-to-Paused auto-transition eventually triggers `_StopAllCapabilities` which does know about remux, but that's a two-poll-cycle delay (~120s) during which the worker grabs new work it shouldn't.

**(2) Draining is invisible to the operator.** The Activity page UI only exposes Online and Pause buttons. `Draining` is an internal-only transient state with its own code path (`_DrainAndStop`, drain waiter thread), but the operator cannot set it from the UI and has no reason to know it exists. The operator's intent is "stop gracefully" -- that should be what Pause does.

**(3) Capability polling has unjustified constraints.** The `_ApplyConcurrencyChanges` loop still clamps concurrency to 1-5 (already removed from API validation and TeamStatus controller, but survives in the polling loop). The actual polling interval is 60s despite criterion 2 documenting "within one polling interval (default 15s)" and `SystemSettings.CapabilityPollingIntervalSec` supposedly controlling it. The 60s delay means any status or concurrency change takes up to a minute to take effect.

**Root cause:** Draining was designed before RemuxService existed and was never updated. The three-state model (Online/Draining/Paused) adds complexity for no operator benefit -- Paused should have always meant "finish in-flight, don't claim new."

**Design direction (discuss before implementing):**
- Two states only: **Online** (accepting work) and **Paused** (finish in-flight, stop claiming)
- Paused = set `StopRequested` on every capability via `_StopAllCapabilities`, let processing loops wind down naturally
- Remove `_DrainAndStop`, remove the `Draining` branch from `_HandleStatusChange`, remove the drain waiter thread
- Remove the 1-5 concurrency clamp (floor of 1, no ceiling)
- Align polling interval to the documented 15s default, verify `SystemSettings.CapabilityPollingIntervalSec` is actually wired

**Violates:** `WorkerService/WorkerService.feature.md` criteria 3, 20, 21.

**Feature doc:** `WorkerService/worker-lifecycle.feature.md` -- full design decisions and success criteria for the fix.

**Look first:** `WorkerService/Main.py` -- `_HandleStatusChange` (line ~741), `_DrainAndStop` (line ~766), `_StopAllCapabilities` (line ~783), `_ApplyConcurrencyChanges` (search for 1-5 clamp), `_CapabilityPollingLoop` (interval). `Features/FileReplacement/FileReplacementBusinessService.py` -- `PrepareReplacement` (the `.orig` rename to replace with `.inprogress` pattern). `WorkerService/WorkerService.flow.md` -- "Per-Worker Status Control" section (update to two states). `Templates/Activity.html` -- tile layout and per-machine pause.

**Fix with:** `/t`

---

### [BUG-0025] Per-capability concurrency is not data-driven -- requires worker restart to take effect
**Date:** 2026-05-13

**What breaks:** Changing `MaxConcurrentTranscodeJobs`, `MaxConcurrentQualityTestJobs`, or `MaxConcurrentRemuxJobs` in the Workers table does not take effect until the worker process is restarted. The concurrency value is read once during `_StartXxxCapability()` and passed to `Run(MaxConcurrentJobs=N)`. The capability polling loop (60s) checks enabled/disabled flags but never re-reads the concurrency columns. This violates the "data-driven" contract: if the max is raised from 1 to 2, the worker should spin up an additional thread on its next poll without restart.

**Violates:** `WorkerService/WorkerService.feature.md` criterion 18 (added with this entry).

**Look first:** `WorkerService/Main.py` `_CapabilityPollingLoop` and `_GetPerCapabilityConcurrency()`. The queue service `Run()` method needs to support dynamic thread-pool resizing, or the capability must be stopped and restarted with the new concurrency value.

---

### [BUG-0030] Status page "Possibly Corrupt" count has no drill-down to see which files are affected
**Date:** 2026-05-13

**What breaks:** The `/Status` page shows "Possibly Corrupt: N" (files with `FFProbeFailureCount >= 3`) as a static number with no click-through. The operator sees there ARE corrupt files but cannot see WHICH ones without navigating to `/Scanning` and opening the Corrupt Files modal. The API endpoint (`GET /api/FileScanning/MediaFiles/Corrupt`) and the detail modal (`Templates/FileScanning.html#CorruptFilesModal`) already exist -- the Status page just doesn't use them.

**Violates:** `Features/FileScanning/FileScanning.feature.md` criterion 19 (added with this entry).

**Look first:** `Templates/Status.html` line 55-61 (the `#LibCorrupt` card -- make it clickable). Reuse the existing `/api/FileScanning/MediaFiles/Corrupt` endpoint. Either inline a modal on the Status page or link to `/Scanning?openCorrupt=true` with auto-open logic.

**Fix with:** `/t`.

---

### [BUG-0031] Next Remux Batch table shows files with no audio stream that silently fail when queued
**Date:** 2026-05-14

**What breaks:** The "Next Remux Batch" card on the ShowSettings page calls `/api/ShowSettings/SmartPopulate` with `Mode='Remux'`. The SmartPopulate query filters by `HasExplicitEnglishAudio IS NULL OR HasExplicitEnglishAudio = true`, but files that have never been probed with audio-aware code have `HasExplicitEnglishAudio = NULL` -- which passes the filter. These video-only files (e.g. Survivor S43E01, S45E02) get displayed as candidates, queued by the user, then fail with "Transcoding failed with return code 4294967274" because the remux command maps `0:a:0` which doesn't exist.

**Violates:** SmartPopulate should exclude files that are known to have zero audio streams (possibly corrupt). No feature doc exists yet for this card's population logic end-to-end.

**Look first:** `Features/TranscodeQueue/QueueManagementBusinessService.py` `SmartPopulateQueue()` WHERE clause; `Features/ShowSettings/remux-populate-card.feature.md`; the `RecommendedMode` materialization in `_EvaluateCompliance()`.

**Fix with:** `/t`.

---

### [BUG-0033] Linux worker deploy flow doc incomplete -- no post-deploy verification, FFmpeg path troubleshooting, or automation parity with Windows
**Date:** 2026-05-13

**What breaks:** `deploy/worker-deploy.flow.md` ends at `docker compose up -d` with only an optional SVT-AV1 encoder check and a Workers table query. Does not document: post-deploy health checks confirming FFmpeg/FFprobe paths resolve inside the container, the full container-started-to-operational sequence, troubleshooting when FFmpeg path resolution fails, or what additional operator actions differ between first deploy vs code-only redeploy. An operator following this doc alone would not know how to diagnose "worker registered but can't find FFmpeg" without reading source code. The Windows deploy path (`deploy/windows-worker.flow.md` + `deploy-windows-worker.py`) has full post-deploy verification and single-command automation; Linux has neither.

**Violates:** `deploy/worker-deploy.feature.md` criterion 20 (added with this entry).

**Look first:** `deploy/worker-deploy.flow.md` -- compare post-deploy coverage to `deploy/windows-worker.flow.md`. The Runtime Pipeline table documents what happens inside the container (steps 8-17) but that knowledge is not surfaced as operator-actionable verification steps. Also consider whether a `deploy-linux-worker.py` (or shell script) should exist to match the Windows automation.

**Fix with:** `/t`.

---

### [BUG-0034] Terminology inconsistency: "quality test" (what) and "VMAF" (how) used interchangeably
**Date:** 2026-05-12

**What breaks:** Code, DB columns, settings keys, log messages, and UI labels mix the policy term ("quality test" -- the decision to accept/requeue/discard a transcode) with the specific implementation term ("VMAF" -- one numeric metric). Examples: `QualityTestEnabled` (policy flag) coexists with `VMAFAutoReplaceMinThreshold` (metric-specific); `QualityTestProgress` table updated by `MonitorVMAFProgress` function; `QualityTestingBusinessService.BuildVMAFCommand`. The mixing bakes the current metric choice into surfaces that should be metric-agnostic and makes a future SSIMU2/PSNR/visual-comparison alternative awkward to add.

**Violates:** `Features/QualityTesting/QualityTesting.feature.md` criterion 11b (added with this entry).

**Look first:** `Features/QualityTesting/QualityTestingBusinessService.py` (mixed naming across method names); `Repositories/DatabaseManager.py` (column names, e.g. `QualityTestRequired` vs `VMAF`); `Templates/*.html` (operator-facing labels); `Core/Logging` strings. Fix needs a documented glossary first, then a careful rename pass; expect schema migrations for any DB columns renamed.

**Fix with:** `/t`.

---

### [BUG-0026 - PARTIAL FIX 2026-05-16] VMAF distribution becomes bimodal on held-frame content -- mean/HMean/P5 unreliable until motion-filter applied
**Date:** 2026-05-10 | **Investigated + partial fix:** 2026-05-16

**Re-classified 2026-05-16:** the original framing pinned this on MKV containers, but a controlled experiment ruled the container out. The real cause is libvmaf mis-scoring held-frame animation (animation-on-2s/3s). The fix is motion-filtered pooling, not a filter-chain change.

**Investigation summary (2026-05-16):** ran the smoke reproducer with the existing Minnie's Bow-Toons variants and five candidate fixes against the same encoded MP4s (no re-encoding -- isolates the VMAF measurement). Results in `Scripts/Smoke/VmafFilterExperiment.py`:

| Recipe | Mean | StdDev | P5 | Verdict |
|---|---|---|---|---|
| baseline (current production filter) | 74.60 | 32.58 | 0.00 | reproduces bug |
| bit10 (compare both at 10-bit, no downcast) | 74.66 | 32.60 | 0.00 | no effect |
| setparams (force range=tv:colorspace=bt709 metadata on both) | 74.60 | 32.58 | 0.00 | no effect |
| scale_range (active in_range=auto:out_range=tv conversion) | 74.60 | 32.58 | 0.00 | no effect |
| baseline against remuxed MP4 source (no re-encode) | 74.60 | 32.58 | 0.00 | **container ruled out** |
| neg_model (vmaf_v0.6.1neg) | 72.79 | 32.81 | 0.00 | marginal regression |
| mpdecimate (drop duplicate frames symmetrically before VMAF) | 73.47 | 33.01 | 0.00 | no effect (only dropped 209/4321 frames; libvmaf's motion is stricter than mpdecimate's "is duplicate" detection) |

Every filter-chain mitigation produced byte-identical or near-identical results. ffprobe confirmed Minnie's source MKV and encoded MP4 have IDENTICAL color metadata (`color_range=tv`, `color_space=bt709`, `color_transfer=bt709`, `color_primaries=bt709`); only pix_fmt differs (8-bit source, 10-bit encoded). The bug doc's color-metadata-mismatch hypothesis applies to Black Butler's `color_range=unknown` case but is NOT the cause on Minnie's, yet Minnie's bimodal'd just as hard.

**Actual cause:** libvmaf's `integer_motion` elementary feature is the temporal absolute difference between consecutive reference frames. Cross-tabulating motion vs VMAF on Minnie's: 41.3% of source frames have motion=0 (1783 of 4321), and 281 of those score VMAF<10. VMAF model 0.6.1 was trained on continuous-motion live-action and produces wildly wrong scores on motion=0 frames even when the encoded picture is visually identical to the source. PNG stills extracted at the VMAF=0 frames confirm: encoder is fine, libvmaf is mis-measuring.

**The trigger is byte-identical consecutive frames, not "animation."** Production-DB cross-check 2026-05-16 against shows with VMAF data:

| Show | Type | Mean | P5 | StdDev |
|---|---|---|---|---|
| Pokémon S20E10 | Hand-drawn anime | 71.5 | 0.0 | 35.1 |
| Real Housewives S03E22 | Reality TV | 76.6 | 9.2 | 29.8 |
| Steven Universe S05E14 | 2D Western animation | 76.8 | 18.9 | 22.7 |
| Bunk'd S02E11 | Disney sitcom | 78.3 | 22.7 | 24.7 |
| The Bear S03E10 | Live-action drama | 79.4 | 10.8 | 27.8 |
| **Garfield Show S01E19** | **Modern CGI** | **97.7** | **95.7** | **1.5** |
| Outlander | Live action | 96.7 | -- | 2.0 |

Counter-intuitively, modern CGI is NOT a reliable predictor of the bug -- Garfield's render pipeline likely uses per-frame motion blur or sub-pixel dither that breaks byte-identity. The shows that DO bimodal are the ones with truly identical held frames: hand-drawn anime animated-on-2s, 2D Western animation with the same technique, reality TV with photo montages and title cards, sitcoms shot multicam on static stages, and dramas with title-card / chapter-card interludes. The Office S00E05 from the original report fits this pattern (S00 specials/extras with lots of static title content).

A secondary contributor: even among motion>0 frames, ~114 frames score VMAF<10 due to low VIF/ADM values on low-spatial-information regions (flat color areas common in animation). VMAF's features fall outside their training distribution on stylized content. This residual can't be cleanly filtered without false positives, so even after motion filtering the metric remains less reliable on animation than on live action.

**Fix shipped (partial):** `Features/QualityTesting/QualityTestingBusinessService.py::ParseVMAFMetrics` now parses `integer_motion` per frame in addition to the VMAF score. When more than 15% of source frames have motion<0.5 (held-frame animation detected), Mean/StdDev/HarmonicMean/percentiles are pooled over only the motion>=0.5 frames -- the duplicate frames are excluded from the metric. Live action sits at <2% motion=0 so the filter is a no-op. Two new fields surface for observability: `MotionZeroFraction` and `MotionFilterApplied`. Smoke harness `Scripts/Smoke/EncodeAndVmaf.py::ParseMetricsFromXml` mirrors the same logic so harness reports stay consistent with production.

Minnie's metrics with the fix:

| Metric | Raw (broken) | Motion-filtered | Clean 4K MP4 reference |
|---|---|---|---|
| Mean | 74.60 | **84.43** | 95.77 |
| HarmonicMean | 11.20 | **24.64** | 95.75 |
| StdDev | 32.58 | **26.75** | 1.18 |
| P5 | 0.00 | **12.08** | 94.30 |
| P25 | 54.12 | **94.39** | -- |

**Residual limitation:** filtered Mean=84 is still below `VmafAutoReplaceMinThreshold=88` even though the encode is visually clean -- so the auto-replace gate will still Requeue this attempt today. P25 of 94 over the filtered pool tells the real story (75% of unique frames score 94+), but the gate doesn't look at P25. Possible follow-ups (not in this fix): (a) lower the threshold when `MotionFilterApplied=True`, (b) gate on filtered P25 instead of filtered Mean for animation, (c) skip the VMAF gate entirely for animation and rely on visual slider review. These are operator-policy decisions, separate from the measurement fix.

**Violates:** `Features/QualityTesting/QualityTesting.feature.md` criterion 2b (re-scoped 2026-05-16 to reflect the actual cause).

**Investigation artifacts:** `Scripts/Smoke/VmafFilterExperiment.py` (committed -- per-recipe harness for re-running the experiment matrix) and `Scripts/Smoke/MinnieBowToons-S04E07-Animation8Mbps.results.json` (committed -- known-bimodal reference, baseline numbers in the file). The remuxed-source MP4 and per-frame PNG extracts are gitignored (regeneratable: `ffmpeg -i <mkv> -map 0:v:0 -map 0:a:0? -c copy <mp4>` to remux; `ffmpeg -i <file> -vf "select=eq(n\,61)" -vframes 1 <png>` to extract frame 61).

---

### [BUG-0026] `MonitorVMAFProgress` stops emitting updates ~25% before FFmpeg exits
**Date:** 2026-05-10

**What breaks:** On attempt 4396 (Steven Universe S05E14, 16,080 frames), the progress log went silent at frame 12,000 (74.6%) and then `Process completed return code: 0` appeared ~25 seconds later. No exception was thrown; no error in the Logs table for that window. Same monitor failure leaves `QualityTestProgress.Status` stuck at `'Processing'` (or `'Started'` with pre-`RETURNING Id` worker code) and `ProgressPercentage` stuck wherever the last successful poll landed -- so the Activity UI shows a phantom "running" row forever even though the VMAF actually finished.

**Data integrity NOT affected:** the FFmpeg process itself completes normally. `vmaf_output.xml` is well-formed (verified: 1,609 frame elements covering frames 0-16080), `QualityTestResults.VMAFScore` is parsed correctly from the XML, and the disposition function reads the right value. The bug is purely on the operator-visibility side.

**Isolated to the Python wrapper (2026-05-10):** ran the EXACT same FFmpeg command directly in a terminal (no `MonitorVMAFProgress` wrapping). FFmpeg emitted clean progress lines every ~100 frames all the way to frame 16,037 (99.7%) and produced the final `frame=16083` line, with VMAF score 79.603343 -- identical to the worker run. So FFmpeg is not the problem. The defect is entirely in our stderr-consumer thread.

**Violates:** `Features/QualityTesting/QualityTesting.feature.md` criterion 7 ("Quality test progress is reported in real time"). [BUG] criterion 7b added with this entry.

**Look first:** `Features/QualityTesting/QualityTestingBusinessService.py:722` (`MonitorVMAFProgress`) and `ParseFFmpegProgressLine` (~line 803). Most likely: the FFmpeg stderr read loop terminates on a short/empty read that gets interpreted as EOF before FFmpeg has actually written its final stderr buffer. Or: a poll-timeout in the monitor loop is shorter than FFmpeg's final-flush interval. The thread that runs `MonitorVMAFProgress` should keep reading until FFmpeg's `wait()` returns, and should emit a final `UpdateProgressRecord(..., Status='Completed', ProgressPercentage=100)` regardless of whether stderr produced a tail progress line.

**Fix with:** `/t`. Same monitor handles two visible symptoms (no late-stage progress lines, `Status` never advancing to `Completed`); fix once.

---

### [BUG-0035] env-driven config in singleton `__new__` never fires; operator-controllable knobs scattered across env / KV / fossilized rows
**Date:** 2026-05-10

**Today's specific instance (fixed in commit `e291ca4`):** `Core/Logging/LoggingService.py` read its verbosity flags inside `__new__`, but every callsite in the codebase uses the `@classmethod` form (`LoggingService.LogInfo(...)`) without instantiating -- so `__new__` never executed and `_InfoEnabled` stayed `False` regardless of the `MEDIAVORTEX_LOG_INFO` env var. WorkerService produced zero INFO logs anywhere (terminal or DB) for the entire post-disposition feature work. Discovered during the i9 smoke test when no QT-loop diagnostics were visible. The fix moved env reads to class-attribute initialization (runs at import) and split `LogInfo` so the DB audit write is unconditional while only the terminal print stays gated.

**Broader concern (still open):** operator-controllable knobs are spread across three surfaces today -- env vars (`MEDIAVORTEX_LOG_INFO`, `MEDIAVORTEX_DEBUG`, `MEDIAVORTEX_SHARE_MAPPINGS`, `MEDIAVORTEX_DB_*`), legacy `SystemSettings` KV rows (mostly retired by the post-transcode-disposition feature 2026-05-10), and fossilized state rows (`ServiceStatus.QualityTestService`, fixed in commit `afdca4a`). No doc owns the rule "which kind of knob lives where". Future config bugs will keep slipping through this gap. The path-storage entry below retires the share-mapping env-vars; the typed `PostTranscodeGateConfig` retired a slice of legacy KV; what's left needs an explicit policy.

**Look first:** `grep -rn "os.getenv" --include="*.py"` outside DB connection strings and process-local startup constants. Each match is a candidate for the same trap or worse: an env-driven knob the operator can't change without restarting workers, with no audit, no UI, no per-worker visibility, no hot-reload.

**Fix with:** `/n config-plane.feature.md` -- when scoped, define a typed config table for operator knobs and the explicit rule "env vars only for genuinely process-local startup constants". Also audit other singletons (e.g. `WorkerContext`, `FFmpegService` cached path) for the `__new__`-runs-once-on-instantiation trap. Not in scope today; the immediate observability bug is patched.

**Related (also fixed 2026-05-10):** `ServiceStatus.<X>Service.Status` was being read as a live gate inside `ProcessQualityTestQueueService.ProcessQueueLoop` and `ProcessTranscodeQueueService.ProcessQueueLoop` -- the same fossilized-row anti-pattern as the disposition function. Retired in `Features/ServiceControl/capability-control-plane.feature.md`. The single gate for "should this worker run capability X right now?" is now `Workers.<X>Enabled + Workers.Status='Online' + fresh heartbeat`, full stop.

---

### [BUG-0027 - CRITICAL - WORKAROUND IN PLACE] Canonical path storage is OS-coupled
**Date:** 2026-05-10
**Single source of truth for this issue.** Every other doc that touches path translation, share mappings, drive letters, or platform-specific path handling MUST link to this entry rather than re-describing the problem. If you find a duplicate description in any feature/flow doc, replace it with a link to here.

**Affects:** every path column in the database. Concretely: `MediaFiles.FilePath`, `TranscodeQueue.FilePath`, `RootFolders.RootFolder`, `ShowSettings.ShowFolder`, `TranscodeAttempts` path columns, `MediaFilesArchive.FilePath`, and any future column shaped like a path. Also: `Services/PathTranslationService.py`, `Core/WorkerContext.py`, `Repositories/DatabaseManager.py:RegisterWorkerShareMappings`, the `WorkerShareMappings` table, and the `MEDIAVORTEX_SHARE_MAPPINGS` env var.

**Diagnosis:** the canonical form of every path stored in the DB is Windows-shaped -- drive letter + backslashes (`T:\Show\Season 1\file.mkv`). The schema decided, at the row level, that one specific OS shape is the source of truth. Linux workers cannot use the canonical value directly; every read/write has to translate `T:\…` to `/mnt/media_tv/…` via a runtime layer. The translation layer works, but it is a workaround for a schema decision, not a feature.

**Symptoms (all observable in DB Logs):**
- 271+ "Path does not exist, cannot normalize" WARNINGs (`PrivateNormalizePathToFilesystemCase`).
- 80+ "FFprobe failed for ..." ERRORs with no captured stderr.
- 439 "FFmpeg path from settings not found" ERRORs across three distinct path shapes.
- 3 "/bin/sh: 1: C:CodeAutomationMediaVortex..." Linux failures (Windows backslashes shell-stripped).
- The full existence of `PathTranslationService`, `WorkerContext.PathTranslation`, and `WorkerShareMappings` -- all of these are workaround scaffolding.

**Current workaround (in production, working, do NOT touch without a feature):**
- `Services/PathTranslationService.py` translates `T:\…` to per-worker mount on every read/write.
- `WorkerShareMappings` table holds per-worker drive-letter -> local-mount rows (12 rows today: 4 workers x 3 letters M/T/Z).
- `MEDIAVORTEX_SHARE_MAPPINGS` env var on each container seeds those rows at registration time.
- `WorkerContext.Current().PathTranslation` is the runtime entry point all services call.
- `Core/WorkerContext.feature.md` and `deploy/worker-deploy.feature.md` document the workaround surfaces.

**Violates:** `path-storage.feature.md` (repo root) -- success criteria 1, 2, 4. Criterion 1 is the [BUG] criterion: no row in any DB table contains a drive letter or backslash in a path field.

**The right shape (deferred -- scoped in `path-storage.feature.md`):**
- Path columns become `(RootId BIGINT REFERENCES RootFolders(Id), RelativePath TEXT)`. Forward slashes, no drive letter, no leading slash.
- New table `RootFolderResolutions` replaces `WorkerShareMappings`: one row per `(RootId, WorkerName)` with the worker's absolute path for that root.
- Absolute paths are computed at I/O boundaries (FFmpeg invocation, `open()`, `os.path.exists`) by joining root resolution + relative path. Never stored.
- `PathTranslationService` reduces to a join lookup (< 50 LOC, no regex, no drive-letter parsing).

**Look first:** `Services/PathTranslationService.py`, `Core/WorkerContext.py`, `Repositories/DatabaseManager.py:RegisterWorkerShareMappings`, schema of `RootFolders` and `WorkerShareMappings`, and any code site that splits or constructs a path with a drive letter (grep for `[A-Za-z]:\\\\` and `os.sep`).

**Fix with:** `/n` against `path-storage.feature.md`. This is a real project (~8-12 Progress steps when planned). Migration is the bulk of the work; the rule is precise. Do NOT attempt incrementally -- the contract has to flip atomically (schema migration + code cutover + backfill in one operator window).

**Note for future bug records:** symptoms of OS-coupled storage (Windows-flavored paths on Linux, drive-letter assumptions, mount-prefix mismatches) append context HERE rather than open a new entry. This issue is the umbrella.

---

### [BUG-0036 - CRITICAL] Profile-less savings estimate uses misleading `SizeMB * 0.5` proxy
**Date:** 2026-05-10
**Affects:** `Features/TranscodeQueue/QueueManagementBusinessService.py:CalculatePriority` (size*0.5 fallback at line 1032), `_EvaluateCompliance` (returns undecidable when profile missing), `EstimateTargetSizeMB` (returns None when profile missing).

When a `MediaFile` has no `AssignedProfile` (and the profile cascade doesn't resolve), every estimate-of-savings path either falls back to `SizeMB * 0.5` (priority calc) or returns "undecidable" (compliance / admission). Result: profile-less files all rank by file size, regardless of compression headroom -- a 5 GB already-AV1 source ranks the same as a 5 GB h264 source. The operator looking at the library to decide which titles to assign profiles to next is sorted by the wrong signal.

**The probed metadata is already there** -- `MediaFiles.Codec`, `OverallBitrate`, `VideoBitrateKbps`, `AudioBitrateKbps`, `DurationMinutes`, `ResolutionCategory` -- nothing reads them for a profile-agnostic compression-potential estimate.

**Why critical:** profile assignment is operator-driven; the operator needs a ranked "next candidates to look at" view that works WITHOUT a profile already being set. Otherwise the assignment-then-queue loop has a chicken-and-egg.

**Violates:** `queue-priority.feature.md` Success Criterion 15 (added with this bug).

**Look first:** `QueueManagementBusinessService.CalculatePriority` (the size*0.5 fallback path) and the `EstimateTargetSizeMB` helper introduced by `marginal-savings-gate.feature.md`. The fix is a profile-agnostic estimator that reads `Codec` + `OverallBitrate` + `ResolutionCategory` and looks up an expected-output-bitrate table (could extend `CrfBitrateEstimates` or add a sibling table -- design choice for the `/t` session).

**Fix with:** `/t`

---

### [BUG-0028] QueueManagementBusinessService.py Cursor-era cleanup backlog
**Date:** 2026-05-10
**Affects:** `Features/TranscodeQueue/QueueManagementBusinessService.py` (2,064 LOC, 35 methods)

Pre-claude-rails (Cursor-written) patterns that the marginal-savings-gate feature explicitly DID NOT clean up to keep its scope tight. Recorded here so they're not lost:

1. **Class is too big.** 2,064 LOC across 7 distinct concerns: queue population, priority calculation, compliance evaluation, recompute, job add/remove, statistics, subtitle-fix population. Fold into smaller services, one per concern.
2. **Silent except blocks** at lines 548-549, 567-568, 1485-1493 (and others). Pattern: `except Exception: pass` with a comment justifying defensiveness. Violates the Phase 2a loud-failure rule. Sweep to `LogException` + re-raise or `LogWarning` with explicit reason.
3. **`LogFunctionEntry(...)` boilerplate** at almost every public method's first line. Useful in early dev, log-spam at scale. Remove or gate on `LOG_LEVEL=DEBUG`.
4. **Boilerplate docstrings** that restate the function name (e.g. line 32 docstring "Populate transcoding queue from MediaFiles..." on `PopulateQueueFromMediaFiles`). CLAUDE.md says "default to writing no comments." Sweep to remove redundant docstrings; keep only ones with WHY content.
5. **Conditional imports inside try blocks** (e.g. line 546). Defensive against modules that always exist. Move to top-level imports.
6. **Legacy `self.DatabaseManager` use** -- 30 call sites of `Repositories/DatabaseManager.py` instead of the feature-local `TranscodeQueueRepository`. The marginal-savings gate replaces this only inside its own touched paths (~5 call sites); remaining 25+ are legacy code paths that need migration to the vertical-slice repo per `KNOWN-ISSUES.md:146`.

**Look first:** `Features/TranscodeQueue/QueueManagementBusinessService.py` -- start with the function-list scan to plan the split, then attack one concern at a time.

**Fix with:** `/n` (this is a refactor, not a single bug -- needs its own feature doc + criteria, especially around the class split which has API-surface implications)

---

### [TECH DEBT BUG-0037] Activity page conflates worker liveness and operational state
**Date:** 2026-05-08
**Affects:** Templates/Activity.html (worker tag display), API endpoints that return worker status

The Activity page shows a single "Online/Offline" badge per worker. It appears to be driven by `Workers.LastHeartbeat` freshness (process-is-alive signal). But the `Workers.Status` column is a separate axis -- it carries the operational state set by the Drain/Offline buttons (`Online` / `Draining` / `Offline`). When the user clicked Offline, the DB column flipped correctly to `Offline`, but the UI badge stayed green because the worker process is still alive and heartbeating (alive AND stopped is a valid combination today).

The four real states from the combination:
- Status=Online + heartbeat fresh -- alive AND working (the green "Online" users expect)
- Status=Online + heartbeat stale -- should be working but process is dead (broken, needs investigation)
- Status=Offline + heartbeat fresh -- alive but stopped (process running, not picking up jobs)
- Status=Offline + heartbeat stale -- clean shutdown

**Fix:** show two separate visuals per worker row in the Activity table.
1. Connectivity indicator (dot or pill, color from heartbeat age: green <60s, yellow 60s-5m, red >5m)
2. Operational state pill (text + color from `Workers.Status`: Online green, Draining amber, Offline gray)

The connectivity indicator answers "can I reach this worker?". The operational state pill answers "should this worker be picking up jobs?". These are independent and both useful.

**Look first:** Templates/Activity.html worker-tag rendering, the API endpoint that feeds it (likely under `Features/TeamStatus/` or `Features/ServiceControl/`), and `Workers` schema (Status + LastHeartbeat already exist, no schema change needed).

**Fix with:** `/n` (template + API change, ~30 min)

---

### [TECH DEBT - PARTIALLY RESOLVED] Loud-failure sweep -- Phase 2
**Date:** 2026-05-08 | **Phase 2a applied:** 2026-05-08
**Affects:** Models/CommandBuilder.py, WebService/Main.py, WorkerService/Main.py, Repositories/DatabaseManager.py, Features/Profiles/, Features/FileScanning/, Features/TranscodeQueue/, Services/FFmpegAnalysisService.py, Features/MediaProbe/, Features/FileReplacement/

Phase 1 (commit 6bf51b2) addressed the four highest-risk silent swallows that hid today's Windows-worker FFmpegPath bug. Three parallel agent audits (silent-failure code patterns, recent DB Logs over 48h, FFmpeg path resolution chain) surfaced ~30 more sites and several systemic blind spots that need a follow-up pass. Documented here so the next session can pick it up cleanly.

**Phase 2a applied (this session):**
- [x] WebService/Main.py: 10 `except: print(...)` blocks converted to LoggingService.LogException (lines 154, 341, 354, 363, 390, 421, 434, 447, 455, 464). When WebService is launched detached by StartMediaVortex.py, errors now land in the DB Logs table instead of vanishing to a closed stdout.
- [x] Models/CommandBuilder.py: 4 codec/audio swallows (`AddCodecParameters`, `AddFilmGrainParameter`, `AddPixelFormatParameter`, `BuildAudioFilters`) now LogException with explicit "transcode will run with partial settings" wording so wrong-quality output is traceable.
- [x] Features/FileReplacement/FileReplacementBusinessService.py: stripped the `Failed to update MediaFiles table: Failed to extract metadata: ...` double-wrap. Original FFprobe error surfaces verbatim via LogError with both local + canonical paths; outer call site logs an explicit "MediaFiles update skipped after successful replacement" warning so the cause/consequence are linkable in DB Logs.
- [x] Services/FFmpegService.py ExecuteFFprobe: subprocess timeout and generic exceptions now use LogException (was LogError, no traceback). Non-zero return code log includes truncated stderr + stdout + command in a multi-line block.
- [x] Services/FFmpegAnalysisService.AnalyzeMediaFile: removed redundant double-log of FFprobe failure (ExecuteFFprobe already logs). JSONDecodeError now LogException with output-snippet for diagnosis.
- [x] WorkerService/Main.py SignalHandler: 3 silent `except: pass` blocks (FFmpeg-kill outer, mark-Offline, pool-close) now LogException with stderr fallback if logger itself fails (defensive for shutdown teardown).
- [x] Repositories/DatabaseManager.py: DeleteProfile, DeleteRootFolder, RecordProblemFile getsize -- all 3 now LogException.
- [x] Scripts/FlagMissingMediaFiles.py created. One-shot to bump FFprobeFailureCount=3 on rows whose source path is missing on disk, so queue-population's existing safety guard skips them. Run with --dry-run first.

**Phase 2b remaining (lower priority, capture for future session):**

**Remaining silent-swallow sites (lower-risk, code path):**
- `Models/CommandBuilder.py:284-285` -- `ExtractResolutionFromFilename` returns None silently. Affects output naming.
- `Features/FileScanning/FileScanningRepository.py:80-81` and `Features/Profiles/ProfileRepository.py:121-122` -- duplicates of `DeleteProfile` / `DeleteRootFolder` in vertical-slice copies (Phase 2a covered the DatabaseManager versions).
- `Features/TranscodeQueue/QueueManagementBusinessService.py:478-479` -- silent skip of show-override lookup; file gets wrong target resolution.
- `Features/MediaProbe/MediaProbeBusinessService.py:134-135` -- `_DeriveResolutionCategory` returns None silently; NULL `ResolutionCategory` leaks into queue logic.
- `Features/TranscodeJob/VideoTranscodingService.py:406-408` -- progress parser swallow, "not critical" comment.
- `Features/TranscodeJob/ProcessTranscodeQueueService.py:1660-1661` -- `_ExtractResolutionFromFilename` swallow.
- `WorkerService/Main.py:251-252` -- scan interval setting parse error silent (falls back to 60min).
- `WorkerService/Main.py:488-489` -- drain mode silently swallows QualityTestService.Stop() failure; drain may never actually stop.
- `TranscodeService/config.py:110` -- same `except:print` pattern (TranscodeService is being deprecated -- delete with the dir per the other tech-debt entry above).

**Systemic blind spots from the DB-log audit (48h window):**
- **439 hits** of `GetFFmpegPathFromSettings: "FFmpeg path from settings not found"` -- ERROR-level, no `ExceptionType`. Three distinct paths recur (`/opt/mediavortex/FFmpeg`, `/opt/mediavortex/MediaVortex/...`, `C:\Code\MediaVortex\...`). The function probes/falls back without surfacing the failure. Caller is silently degraded.
- **271+ hits** of `DatabaseManager: "Path does not exist, cannot normalize"` -- WARNING. Likely the dead-file pattern from `PrivateNormalizePathToFilesystemCase` running on stale MediaFiles rows. Phase 1's pre-flight check stops new occurrences from creating attempt rows but doesn't sweep the existing stale rows. Need a one-shot script that flags `MediaFiles` where the path doesn't exist on disk for any worker that can reach it.
- **121 hits** of `_ProcessCompleteFileReplacement: "Failed to update MediaFiles table: Failed to extract metadata"` -- WARNING. Two layers of "Failed to" with no underlying cause. The `ntpath.dirname` fix (commit f5021d2) addresses new occurrences but the wrapper still strips the original exception. Strip the wrapper, log the original.
- **80+ hits** of `AnalyzeMediaFile: "FFprobe failed for ..."` -- ERROR with no `ExceptionType` and no `StackTrace`. Caller logs only the path, not the FFprobe stderr. Capture stderr into ExceptionMessage so we can see *why* FFprobe failed.
- **3 occurrences** of `/bin/sh: 1: C:CodeAutomationMediaVortexFFm...` -- Linux Larry workers tried to execute a Windows-flavored path with backslashes shell-stripped. The path purge in commit 87aaf58 removed the source string, but find the call site that constructed it; some code is still concatenating Windows paths on Linux callers.

**Recommended order when picking this up:**
1. Sweep `WebService/Main.py` `except: print(...)` -> `LogException`. Mechanical, low-risk, big visibility win.
2. Fix the 4 `CommandBuilder.AddCodecParameters/BuildAudioFilters` silent swallows -- highest-risk because they corrupt transcode quality.
3. Strip the "Failed to update MediaFiles table:" wrapper in `_ProcessCompleteFileReplacement` so the original exception surfaces.
4. Capture FFprobe stderr in `AnalyzeMediaFile` exception-path log.
5. One-shot `Scripts/FlagMissingMediaFiles.py` to mark all existing MediaFiles where the path is unreadable from any registered worker.
6. Then the lifecycle / DB-delete swallows.

**Fix with:** `/n` (multi-feature sweep, ~2-3 hours)

---

### [BUG-0025] Worker capability flags not editable from the UI
**Date:** 2026-05-08
**Affects:** WorkerService.feature.md (criterion 14), Activity page, Settings page, `Features/TeamStatus/TeamStatusController.py`

`Workers.TranscodeEnabled`, `Workers.QualityTestEnabled`, `Workers.ScanEnabled` are read by the worker's 60s capability poller, but no UI control writes them -- the operator has to run `UPDATE Workers SET ScanEnabled=true WHERE WorkerName=...` directly via SQL. Same gap as the per-worker Status (Online/Draining/Offline) controls -- but those at least have buttons on the Activity page; capability flags have nothing.

**Look first:** `Features/TeamStatus/TeamStatusController.py` already has `POST /api/TeamStatus/Workers/<name>/Status` for status changes -- mirror that pattern for capability flags. `Templates/Activity.html` worker-row rendering already iterates `/api/TeamStatus/Workers` JSON which includes `TranscodeEnabled`/`QualityTestEnabled`/`ScanEnabled` -- add three toggle controls to each row alongside the existing status buttons.

**Flow doc gap:** `WorkerService.flow.md` covers the read-path (capability polling) but not the write-path. `/t` should extend it with a stage describing the API endpoint contract before the fix.

**Fix with:** `/t` (one new POST endpoint + Activity template change + JS handler; estimate 30-45 min)

---

### [BUG-0038] SystemSettings not normalized; /settings page does not show every row
**Date:** 2026-05-08
**Affects:** SystemSettings.feature.md (criteria 11, 12), `Features/SystemSettings/SystemSettingsRepository.py`, `Templates/Settings.html`

DB state: no UNIQUE on `SettingKey` (duplicates exist: ContinuousScanEnabled x2, ContinuousScanIntervalMinutes x2, ExcludedDirectories x4). `DataType` mixes BOOLEAN/boolean/string/INTEGER/integer/text. List-shaped values stored as CSV (`AllowedExtensions`, `ExcludedDirectories`). Per-file CRF overrides use `CRFOverride_<long_path>` keys instead of a typed override table. Until tonight's UI patch the /settings page only rendered hardcoded known keys (FFmpegPath, MaxCpuThreads, etc.) -- new keys like `DisplayTimezone` were invisible despite existing in the DB. Tonight's commit 505fac2 added a generic "All System Settings" advanced table; criterion 12 is now achievable but the normalization gaps in criterion 11 remain.

**Look first:** `Scripts/SQLScripts/` -- needs a migration that dedupes by `SettingKey` (keep most-recently `LastModified`), adds `UNIQUE(SettingKey)`, and a CHECK constraint on `DataType`. Then move `AllowedExtensions` / `ExcludedDirectories` to child tables and `CRFOverride_*` to a `MediaFileTranscodeOverrides` table keyed on `MediaFileId`. Frontend code that splits CSV in `Settings.html` (search for `.split(',')` near AllowedExtensions/ExcludedDirectories) needs to follow.

**Flow doc gap:** No general flow doc exists for the SystemSettings pipeline (DB row -> Repository -> Controller -> Settings.html UI -> POST round-trip). `/t` should create one before the fix so the dedupe migration and frontend follow-up have a documented contract.

**Fix with:** `/t` (multi-step migration + UI follow-up; estimate 1-2 hours)

---

### [BUG-0040] Second concurrent job shows first job's progress
**Date:** 2026-05-05
**Affects:** TranscodeJob feature -- concurrent job progress tracking
**Criterion violated:** TranscodeJob.feature.md -- each running job must report independent progress

When MaxConcurrentJobs > 1 and a second job starts while the first is still running, the second job displays the same progress percentage and ETA as the first (e.g., both show 20.5% / ETA 01:41:41). Only one FFmpeg process is actually running.

**Look first:** `Features/TranscodeJob/ProcessTranscodeQueueService.py:169` (`GetStatus` returns single `currentProgress`), `GetCurrentTranscodeProgress()` in DatabaseManager (likely returns one row, not per-job), and `VideoTranscodingService.TranscodeVideo` (process spawning).

**Fix with:** `/t`

---

### [BUG-0028] DatabaseManager.py monolith -- dual database access paths
**Date:** 2026-05-07
**Affects:** All features that still import from Repositories/DatabaseManager.py instead of their own Repository
**Criterion violated:** Feature vertical isolation -- each feature should access the database exclusively through its own Repository

`Repositories/DatabaseManager.py` (630+ lines) is the legacy data access layer. Features are supposed to use `Features/<Name>/<Name>Repository.py`, but some still call DatabaseManager directly. This creates two paths to the database: the feature Repository and the legacy monolith. Unclear where new queries should go, and changing a query may need updates in two places.

**Look first:** `Repositories/DatabaseManager.py` -- audit which features import from it. Cross-reference with each `Features/<Name>/<Name>Repository.py` to find overlap.

**Fix with:** `/n` (this is a migration, not a quick fix -- needs audit of all callers first)

---

### [BUG-0028] Feature vertical boundaries do not match governed code
**Date:** 2026-05-07
**Affects:** TranscodeJob.feature.md, FileReplacement.feature.md, Services/CommandBuilderService.py, Services/FFmpegAnalysisService.py, Core/Services/PathTranslationService.py
**Criterion violated:** TranscodeJob.feature.md scope/criteria mismatch; FileReplacement.feature.md cross-feature dependency

TranscodeJob.feature.md declares scope `Features/TranscodeJob/**` + `WorkerService/Main.py`, but its criteria govern behavior in CommandBuilderService (conditional yadif, output mode), FFmpegAnalysisService (per-worker FFprobe), PathTranslationService (multi-prefix translation), and ProcessTranscodeQueueService (VMAF toggle, worker config loading). Separately, FileReplacement depends on MediaProbe for re-probing with no explicit contract.

**Look first:** TranscodeJob.feature.md criteria list -- each criterion that references a file outside the declared scope. `Features/FileReplacement/FileReplacementBusinessService.py` for the MediaProbe call.

**Fix with:** `/n` (architectural boundary redesign -- either expand TranscodeJob scope or extract worker/command-building into separate feature verticals)

---

### [BUG-0027] FilePath used as denormalized natural key across 6+ tables
**Date:** 2026-05-05
**Affects:** Schema-wide -- MediaFiles, TranscodeAttempts, TranscodeFiles, TranscodeQueue, CompliantFiles, ProblemFiles
**Criterion violated:** Data normalization -- same filepath (with platform-specific drive letter prefix) stored redundantly across tables instead of referencing MediaFiles.Id as a foreign key.

Full Windows paths (e.g., `T:\Shows\file.mkv`) are stored as natural keys in at least 6 tables. This causes:
1. Case inconsistencies already present in production data (`T:\` vs `t:\`, `Z:\` vs `z:\`)
2. Platform coupling -- every table embeds Windows drive letters, making cross-platform workers depend on prefix translation at query boundaries
3. No referential integrity -- deleting/renaming a file in MediaFiles does not cascade to dependent tables
4. Path changes (drive letter remapping, share migration) require updating every table

**Scale:** ~67k rows in MediaFiles, ~3.8k in TranscodeFiles, ~2.9k in TranscodeAttempts, ~1.4k in CompliantFiles.

**Migration in progress (Phase 3 of architecture redesign):**
- [x] MediaFileId BIGINT columns + indexes added to 5 child tables (AddMediaFileIdColumns.py)
- [x] Backfill completed: 1,952 rows linked, 6,867 orphans (old history with deleted files)
- [x] All JOINs and INSERTs updated in code to use MediaFileId
- [x] FK constraints added (AddMediaFileForeignKeys.py) -- TranscodeFiles/TranscodeAttempts ON DELETE SET NULL, TranscodeQueue/CompliantFiles/ProblemFiles ON DELETE CASCADE
- [x] All WHERE/JOIN reads switched from FilePath to MediaFileId (Phase 3b Step 1)
- [x] FilePath removed from INSERT/UPDATE statements for TranscodeAttempts, TranscodeFiles, ProblemFiles (Phase 3b Step 2)
- [x] NOT NULL constraint dropped from FilePath on TranscodeAttempts, TranscodeFiles, ProblemFiles (was blocking INSERTs)
- [x] Deploy verification -- workers Online and heartbeating (root cause: CrashRecoveryService killed itself because Python is PID 1 in Docker and the recorded ProcessId from a prior crash matched the new container's own PID; also bumped postgres max_connections 30->200 and added pool closeall() before os._exit() to stop connection-leak death spiral)
- [ ] Run RenameFilePathColumns.py to soft-rename columns (Phase 3b Step 4)
- [ ] Drop FilePath_Deprecated columns (Phase 4 -- point of no return)

---

### [BUG-0027] Workers in broken canonical state silently fail scanning; no multi-drive scanning workflow
**Date:** 2026-05-13

**What breaks:** Two related gaps in the scanning pipeline:

(1) **Unknown worker state.** A worker with `ScanEnabled=true` but broken path resolution (missing `WorkerShareMappings` rows, unmapped drives, `PathTranslationService` returning untranslated Windows paths on Linux) silently begins a scan pass. `ContinuousScanService` calls `StartScanning` for each RootFolder without validating that `_ToLocalPath(RootFolderPath)` resolves to an accessible local directory. The result is `os.walk` errors, wrong paths inserted into MediaFiles, or scans that appear to complete with 0 files found. No pre-scan health check, no operator-visible signal that a worker's path state is broken.

(2) **Multi-drive scanning.** RootFolders are seeded under specific drive prefixes (T:\\, M:\\, Z:\\). Adding a new drive to scan requires: manually inserting RootFolders rows, adding `WorkerShareMappings` rows for every worker that can reach the new drive, and restarting workers. There is no UI workflow to register a new drive/share, associate it with workers, and begin scanning. The operator cannot scan from all workers across all drives without manual SQL and restarts.

**Violates:** `Features/FileScanning/FileScanning.feature.md` criteria 20, 21 (added with this entry). `WorkerService/WorkerService.feature.md` criterion 19 (added with this entry).

**Look first:** `Features/FileScanning/ContinuousScanService.py` `_ExecuteScan` -- where pre-scan path validation should fire. `Features/FileScanning/FileScanningBusinessService.py` `_ToLocalPath` -- the translation call that should be validated. `Services/PathTranslationService.py` -- the translation layer. `Templates/Settings.html` or `Templates/FileScanning.html` -- where a "add drive" UI would live. `Repositories/DatabaseManager.py:RegisterWorkerShareMappings` -- the current seeding path for share mappings. Related: `KNOWN-ISSUES.md` canonical path storage entry (the root cause); `path-storage.feature.md` (the long-term fix).

---

## Resolved

### [BUG-0042] Active Jobs list view omits VMAF runs while header badge counts them -- operator misreads as "stuck", kills workers, orphans claimed rows
**Date:** 2026-06-03 -> 2026-06-03 | **Area:** activity-page

**Resolution:** `GetRunningQualityTestProgress` rewritten to drive from `ActiveJobs WHERE ServiceName='QualityTestService'` LEFT JOIN `QualityTestProgress`/`QualityTestingQueue`/`TranscodeAttempts`, returning one row per claim (with NULL progress fields when no `QualityTestProgress` row exists). `Templates/Activity.html` `RenderActiveJobs` renders NULL-progress rows with a yellow stale-claim badge + human-readable claim age via a new `FormatClaimAge` helper. Method migrated from `Repositories/DatabaseManager.py` to `Features/QualityTesting/QualityTestRepository.py` (per `database-manager-aggregates.json`); `QualityTestController.GetQualityTestProgress` now routes through the repository. Live canary against 12 orphan QualityTestService claims: `/api/QualityTesting/Progress` returned `Jobs.Count=12` matching `/api/SQLQueries/GetActiveJobs` `QualityTestService=12`.

**Out of scope (still active):** worker-side claim release on graceful shutdown/SIGTERM, and any orphan-cleanup sweep that automatically releases stale `ActiveJobs` rows. This fix is the display layer only; producer-side gaps are tracked separately.

---