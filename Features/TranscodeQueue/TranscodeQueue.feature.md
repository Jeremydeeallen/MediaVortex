# Transcode Queue

## What It Does

Populates and manages the queue of files awaiting FFmpeg transcoding. Filters files by resolution against profile thresholds, enforces safety guards, and provides queue management controls.

## Success Criteria

1. PopulateQueue filters MediaFiles by comparing their Resolution against the assigned profile's ProfileThresholds.TranscodeDownTo to determine which files need transcoding.
2. Files without explicit English audio (HasExplicitEnglishAudio = false) are blocked from queue population. Files with NULL (not yet probed) are allowed through.
3. Files already transcoded by MediaVortex (TranscodedByMediaVortex = true) with VMAF >= 80 are not re-queued.
4. Files with VMAF < 80 get CRF adjustment. Adjusted CRF cannot go below 15 -- files that would need lower CRF are logged as ProblemFiles.
5. Queue items are sortable by size, priority, and date added.
6. Queue supports pagination (10/25/50/100 per page).
7. Bulk operations are available: clear entire queue, remove items by file size threshold, cleanup duplicates.
8. Navigation bar shows a live queue count badge that refreshes automatically.
9. The /TranscodeQueue page displays all pending queue items with file details.

## Status

COMPLETE

## Scope

```
Features/TranscodeQueue/**
```

## Files

| File | Role |
|------|------|
| Features/TranscodeQueue/TranscodeQueueController.py | Flask Blueprint -- queue endpoints |
| Features/TranscodeQueue/TranscodeQueueBusinessService.py | Queue population logic, safety guards |
| Features/TranscodeQueue/TranscodeQueueRepository.py | TranscodeQueue database queries |
| Templates/Queue.html | Queue UI page |
