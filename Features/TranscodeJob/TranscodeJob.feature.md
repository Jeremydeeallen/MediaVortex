# TranscodeJob Feature

Executes FFmpeg transcode jobs from the queue, tracks progress, and handles results.

## Scope

- `Features/TranscodeJob/**`
- `TranscodeService/Main.py`

## Criteria

- Jobs claimed from queue are executed via FFmpeg with the correct command built from profile settings
- Progress is tracked per-job via TranscodeProgress table and reported to the UI
- [BUG] Each running job MUST report independent progress -- when multiple jobs run concurrently, each job's progress reflects its own FFmpeg process, not another job's
- Failed jobs are marked failed with error message and do not block the queue
- Completed jobs update TranscodeAttempts with final size, duration, and FFmpeg command
- ActiveJobs table tracks running processes for stuck-job detection
- Distributed workers claim jobs atomically via SELECT FOR UPDATE SKIP LOCKED

## Progress

- [x] Single-job transcoding pipeline
- [x] Distributed worker support (Phase 1)
- [ ] Fix: concurrent job progress isolation (see KNOWN-ISSUES.md)
