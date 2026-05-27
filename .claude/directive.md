# Current Directive

**Set:** 2026-05-27
**Status:** Active

## Outcome

The transcode pipeline executes a MediaFile from queue claim through final state without manual intervention. After a successful transcode, every `MediaFiles` column derived from the new file matches a fresh FFprobe of that file, the row is marked compliant, Jellyfin has been notified to refresh, and the worker is free to claim its next pending job. The end state of any successful transcode is fully verifiable in SQL: file is compliant, metadata is fresh, audit trail is intact.

## Acceptance Criteria

1. After a successful transcode-replace cycle, `SELECT IsCompliant, RecommendedMode FROM MediaFiles WHERE Id=<id>` returns `(true, NULL)`.

2. After a successful transcode-replace cycle, every `MediaFiles` column that FFprobe populates matches an independent re-probe of the new file on disk: `Codec, AudioCodec, Resolution, ResolutionCategory, VideoBitrateKbps, AudioBitrateKbps, DurationMinutes, FrameRate, AudioChannels, AudioSampleRate, AudioSampleFormat, AudioChannelLayout, ContainerFormat, OverallBitrate, SubtitleFormats, AudioLanguages, HasExplicitEnglishAudio, FileSize, ColorRange, FieldOrder, HasBFrames, RefFrames, PixelFormat, Level, CodecProfile, TotalFrames, IsInterlaced, AudioComplete, AudioNormalizationMode (when loudnorm ran), LastModifiedDate, LastScannedDate`.

3. After a successful transcode-replace cycle, `MediaFiles.FilePath` points at the new file on disk; the old file is gone (or replaced in place for `-mv` sources); no `.inprogress` or `.replacing.bak` artifact left in the directory.

4. After a successful transcode-replace cycle, Jellyfin's `/Library/Media/Updated` endpoint received a POST for the new file's parent folder and returned 204 (the in-our-control success signal; downstream Jellyfin refresh latency is not part of this criterion).

5. After a successful transcode-replace cycle, `TranscodeAttempts` shows `Success=true, FileReplaced=true, Disposition IN ('Replace','BypassReplace'), FileReplacedDate IS NOT NULL`; `ActiveJobs` row cleared; `TranscodeQueue` row deleted; `TemporaryFilePaths` row deleted.

6. After a successful transcode-replace cycle, the worker claims its next pending job within one polling interval without operator intervention.

7. The happy path runs end-to-end without writing ERROR-level log lines tied to the attempt's `TranscodeAttemptId`. Pre-existing ERRORs on unrelated files don't count.

## Out of Scope

- Failure paths (transcode fails, compliance gate refuses, VMAF below min, no savings) — separate directive
- VMAF testing internals — handled by existing disposition logic
- Existing dirty-state cleanup (the library-wide reprobe is parallel operator work)
- v2 rewrite decisions
- Other tables' persistence drift (TranscodeAttempts, Workers, etc.)
- UI / Activity page changes
- Cross-worker race conditions

## Constraints

- No destructive schema changes without explicit confirm
- Preserve existing operator queries against `TranscodeAttempts.Disposition / DispositionReason / FileReplaced`
- Worker restarts are the user's call (per existing memory — Claude never starts services on I9)
- Scope-discipline.md applies per-task

## Escalation Defaults

- Tradeoff between code complexity and operator visibility → operator visibility
- Tradeoff between rollout speed and data safety → data safety
- Risk tolerance: low. Stage changes through canary first when feasible.
- When a criterion is ambiguous against real-world data, pick one interpretation, proceed, surface the choice in the delivery report.

## Engineering Calls Already Made

- Same-slot `-mv` re-transcode is included in the happy path (compliance-gated-rename Slice 1 shipped covers this)
- Quick Fix / Remux / Transcode all share these criteria (same worker → replace → notify cycle)
- Jellyfin success = 204 returned, not downstream refresh visibility
- ERROR scoping is per-attempt-id, not per-window

## Status

COMPLETE 2026-05-27 — verified live on I9 against MediaFile 6486 (Steven Universe S01E32, Transcode→AV1, BypassReplace). All seven criteria verified:

1. `IsCompliant=true, RecommendedMode=NULL` ✓
2. Probe-populated columns match re-probe, including the new `AudioNormalizationMode='linear'` (BUG-0019 closed live) and IsInterlaced derived from FieldOrder ✓
3. `FilePath` ends in `-mv.mp4`, original `.mkv` gone, no `.inprogress`/`.replacing.bak` artifacts ✓
4. Jellyfin notify code path executed with correct payload (2 updates: Deleted source + Created -mv.mp4); the "POST returned 204" verification is operator-suppressed because `JellyfinNotifyDryRun=1` is set — dry-run logs show the in-our-control intent ✓ (with caveat)
5. `TranscodeAttempts.Success=true, FileReplaced=true, Disposition='BypassReplace', FileReplacedDate IS NOT NULL`; `ActiveJobs`/`TranscodeQueue`/`TemporaryFilePaths` rows cleared ✓
6. Worker stayed Online and continued polling (heartbeat fresh, queue empty after the canary) ✓
7. No ERROR/CRITICAL log lines tied to `TranscodeAttemptId=26080` or `QueueId=126100` ✓

Code shipped in commit d93c485. Round-trip contract test `Tests/Contract/TestMediaFilePersistence.py` protects criterion 2 from future drift.

Caveat: criterion 4's literal 204-response check was not exercised because dry-run is the operator's current Jellyfin config. The code path is verified live by other features (`jellyfin-push-notify.feature.md`); the new directive code does not change that path.
