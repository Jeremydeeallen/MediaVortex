# Add SizeMB column to /FailedJobs

**Set:** 2026-06-13
**Status:** Active -- phase: IMPLEMENTING
**Slug:** failedjobs-size-column

## Outcome

A new "Size" column appears on `/FailedJobs` showing each capped MediaFile's `SizeMB`. Operator can sort by size to find largest failing files first.

## Acceptance Criteria

1. `FailedJobRow` carries `SizeMB: Optional[float]`. `FailedJobsRepository.GetCappedJobs` SELECTs `mf.SizeMB`. `/api/FailedJobs` JSON includes `SizeMB`. `Templates/FailedJobs.html` renders the value and offers it as a sort option.

## Files

```
Features/FailureAccounting/Models/FailedJobRow.py
Features/FailureAccounting/Repositories/FailedJobsRepository.py
Features/FailureAccounting/FailedJobsController.py
Templates/FailedJobs.html
```
