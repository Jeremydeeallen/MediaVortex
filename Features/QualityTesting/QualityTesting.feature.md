# Quality Testing

## What It Does

Runs VMAF quality analysis comparing transcoded files against originals. Scores determine whether a transcode is acceptable (>= 80) or needs re-encoding with adjusted CRF.

## Success Criteria

1. After a transcode completes, the output file is automatically queued for VMAF quality testing (when QualityTestEnabled is on).
2. VMAF scoring compares the transcoded file against the original and produces a numeric score (0-100).
3. Files with VMAF >= 80 pass quality testing and are eligible for file replacement.
4. Files with VMAF < 80 trigger CRF adjustment for the next transcode attempt.
5. Quality test results are recorded in TranscodeAttempts with the VMAF score.
6. Quality testing runs as a capability within WorkerService (QualityTestEnabled flag). Workers with this capability enabled poll for queued quality tests.
7. Quality test progress (current file, percentage) is reported in real time.
8. Quality testing can be paused, resumed, or gracefully stopped (finish current test then stop).
9. SystemSettings.QualityTestEnabled controls whether quality testing runs globally (default OFF). Workers.QualityTestEnabled provides per-worker override (NULL = use global).
10. Test result history is viewable with pagination.
11. ShouldQualityTestService.ProcessTranscodedFile() respects QualityTestRequired. When QualityTestRequired=False on the TranscodeAttempt, the bridge skips the quality test queue and goes directly to file replacement.

## Status

COMPLETE

## Scope

```
Features/QualityTesting/**
WorkerService/**
```

## Files

| File | Role |
|------|------|
| Features/QualityTesting/QualityTestingController.py | Flask Blueprint -- quality test endpoints |
| Features/QualityTesting/QualityTestingBusinessService.py | VMAF execution, scoring logic |
| Features/QualityTesting/QualityTestingRepository.py | Quality test queue and results queries |
| WorkerService/Main.py | Unified worker entry point (runs quality testing when QualityTestEnabled=TRUE) |
