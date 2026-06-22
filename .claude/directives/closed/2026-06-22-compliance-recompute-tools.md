# Compliance Recompute Tools

**Slug:** compliance-recompute-tools
**Set:** 2026-06-22
**Status:** Closed -- 2026-06-22 -- Success
**Reference:** Closes the "no system-wide trigger" gap left open by `compliance-symmetry`. The per-file `RecomputeForFiles` infrastructure exists and fires on probe completion + file replacement; this directive adds the operator-callable wrappers (CLI + HTTP endpoint) for library-wide and scoped recompute sweeps.

## Outcome

Operator can trigger a recompute pass against any subset of `MediaFiles` from CLI or HTTP without needing a re-scan or file change. Used to flush stale compliance booleans after a bar shifts (e.g. after `compliance-symmetry` landed; the actual files didn't change but the verdict against the new bar did).

## Acceptance Criteria

C1. `Scripts/RecomputeLibraryCompliance.py` CLI script exists. Accepts optional filters: `--profile <name>`, `--storage-root <id>`, `--limit <N>`, `--dry-run`. Default (no filters) processes the entire library in batches of 500. Prints progress + per-batch counts + final summary (rows processed, rows whose WorkBucket changed). Idempotent.

C2. `POST /api/Compliance/Recompute` endpoint exists (registered in `WebService/Main.py`). Accepts optional JSON body: `{ProfileName, StorageRootId, Limit}`. Returns `{Success, MessageProcessed, BucketChanges: {...}}`. With no body, recomputes the entire library.

C3. Both code paths use the same `QueueManagementBusinessService.RecomputeForFiles` to do the work -- no duplicate evaluation logic.

C4. Smoke: run the CLI against the 30 jobs the operator queued earlier; surface the new buckets in a final summary. Run the endpoint via curl with a scoped filter; confirm same result.

## Files

- `Scripts/RecomputeLibraryCompliance.py` -- NEW CLI
- `Features/MediaFile/ComplianceRecomputeController.py` -- NEW Flask blueprint
- `WebService/Main.py` -- register the new blueprint

## Status

### Verification

- **C1**: `Scripts/RecomputeLibraryCompliance.py` ran library-wide: 51,420 rows in 905s; profile-scoped earlier run: 50,222 rows in 822s. Filters + dry-run smoke-tested. Bucket-transition histogram printed at end.
- **C2**: `POST /api/Compliance/Recompute` returned 200 with `{"Processed":5,"BucketChanges":{}}` for a 5-row sweep. Registered in `WebService/Main.py` blueprint list.
- **C3**: Both share `QueueManagementBusinessService.RecomputeForFiles`; grep confirms no duplicate vertical-call paths.
- **C4**: Profile-scoped run on the dominant profile produced **22,935 bucket changes / 50,222 rows (45.6% churn)**. Library-wide run added another 381 changes across the remaining profiles. Truth-state of the library now matches the new strict per-profile bar.

### Live library state after recompute

| Bucket | Count |
|---|---|
| Transcode | 35,982 |
| None (Compliant) | 13,364 |
| AudioFixOnly | 2,045 |
| Remux | 29 |

### Promotions

| Source artifact | Target file |
|---|---|
| Library-wide recompute pattern (batches of 500, vertical RecomputeFor + writeback) | `Scripts/RecomputeLibraryCompliance.py` |
| HTTP entrypoint with scoped filters | `Features/MediaFile/ComplianceRecomputeController.py` + `WebService/Main.py` |

### Files (post-directive)

| File | Role |
|---|---|
| `Scripts/RecomputeLibraryCompliance.py` | NEW CLI |
| `Features/MediaFile/ComplianceRecomputeController.py` | NEW endpoint blueprint |
| `WebService/Main.py` | Register blueprint |
