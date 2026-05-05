# Known Issues

## Open

### [BUG] Second concurrent job shows first job's progress
**Date:** 2025-05-05
**Affects:** TranscodeJob feature -- concurrent job progress tracking
**Criterion violated:** TranscodeJob.feature.md -- each running job must report independent progress

When MaxConcurrentJobs > 1 and a second job starts while the first is still running, the second job displays the same progress percentage and ETA as the first (e.g., both show 20.5% / ETA 01:41:41). Only one FFmpeg process is actually running.

**Look first:** `Features/TranscodeJob/ProcessTranscodeQueueService.py:169` (`GetStatus` returns single `currentProgress`), `GetCurrentTranscodeProgress()` in DatabaseManager (likely returns one row, not per-job), and `VideoTranscodingService.TranscodeVideo` (process spawning).

**Fix with:** `/t`
