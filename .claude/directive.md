# Compliance Recompute Tools

**Slug:** compliance-recompute-tools
**Set:** 2026-06-22
**Status:** Active -- phase: IMPLEMENTING
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

Active -- IMPLEMENTING.
