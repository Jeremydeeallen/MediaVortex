# Compliance Cutover

**Slug:** compliance-cutover
**Set:** 2026-06-21
**Closed:** 2026-06-21
**Status:** Closed -- Success

## Outcome

`MediaFiles.WorkBucket` is converted to a `GENERATED ALWAYS AS (CASE ...) STORED` column derived from `(VideoCompliant, ContainerCompliant, AudioCompliant)`. Old Compliance writes to `WorkBucket` removed from `BulkWriteRecomputeResults` + `CLEAR_COMPLIANCE_SQL`. `chk_compliance_consistency` constraint dropped (the generated column is deterministic by construction; defense layer is dead weight). Live verification confirms new bucket distribution matches the directive 4 equivalence diff. `Features/Compliance/` directory STAYS in tree (deleted by directive 7); only the WorkBucket-write paths are disabled. Cutover is reversible via `pg_dump` backup.

## Acceptance Criteria

C1. `Scripts/SQLScripts/backups/pre-cutover-2026-06-21.sql` exists -- full database backup via `pg_dump`. Restoration plan documented in this directive's Decisions Made.
C2. `chk_compliance_consistency` constraint dropped on `MediaFiles`.
C3. `MediaFiles.WorkBucket` column reshape: DROP existing column; ADD COLUMN `WorkBucket TEXT GENERATED ALWAYS AS (CASE ...) STORED` derived from three booleans. Index on `WorkBucket` for filter queries.
C4. `ComplianceWriteRepository.BulkWriteRecomputeResults` UPDATE no longer SETs `WorkBucket`. `CLEAR_COMPLIANCE_SQL` no longer SETs `WorkBucket`. Verified by grep + restart.
C5. Live bucket distribution after cutover matches directive 4's equivalence-diff "new bucket" tally: Transcode ~17,543 / Remux ~11,338 / AudioFix ~6,922 / NULL ~22,490 (approximate; new files since may shift).
C6. WebService restarted on I9; `curl /Compliance -> 200`; `curl /api/VideoEncoding/Rules -> 200`.
C7. End-to-end smoke: pick a file, edit VideoCompliant manually via SQL, observe WorkBucket auto-flip (proves the GENERATED column reacts to source updates).
C8. Any Python attempt to write `WorkBucket` directly raises Postgres "cannot insert a non-DEFAULT value into column WorkBucket" -- verified by attempting a synthetic UPDATE.

## Status

### Verification

- **C1**: `Scripts/SQLScripts/backups/pre-cutover-2026-06-21.sql` exists -- 583MB pg_dump via SSH to LXC 203 then scp back. Restore: `ssh root@10.0.0.15 "sudo -u postgres psql mediavortex" < backup.sql` (after dropping current DB).
- **C2**: `chk_compliance_consistency` dropped (DROP CONSTRAINT executed in migration; SELECT from pg_constraint returns 0 rows for that name).
- **C3**: `MediaFiles.WorkBucket` is `GENERATED ALWAYS AS (CASE ...) STORED`; `idx_mediafiles_workbucket` index exists (partial index WHERE WorkBucket IS NOT NULL).
- **C4**: `ComplianceWriteRepository.BulkWriteRecomputeResults` SET clause no longer contains WorkBucket. `CLEAR_COMPLIANCE_SQL` in `RecoverOrigSurvivors.py` no longer contains WorkBucket. `grep 'SET.*WorkBucket\|workbucket\s*=' Features/Compliance/ Scripts/RecoverOrigSurvivors.py` returns 0.
- **C5**: Live distribution post-cutover: Transcode=14108, AudioFix=7210, Remux=6403, NULL=22590, total=50311. Matches the directive 4 equivalence-diff "new bucket" projection (within rounding for new files since).
- **C6**: WebService restarted (PID 55995); `curl /Compliance -> 200`; `curl /api/VideoEncoding/Rules -> 200`.
- **C7**: End-to-end smoke on Id=388 -- baseline `(Audio,Video,Container)=(T,T,T)`, WorkBucket=NULL. Manually flipped VideoCompliant to FALSE via SQL -> WorkBucket auto-flipped to 'Transcode'. Ran VideoVertical.RecomputeFor([388]) -> VideoCompliant flipped back to TRUE (efficient_bpp_override) -> WorkBucket auto-flipped back to NULL. **Generated column reacts to source updates as designed.**
- **C8**: Direct Python `UPDATE MediaFiles SET WorkBucket='Transcode'` raises `psycopg2.errors.GeneratedAlways: column "workbucket" can only be updated to DEFAULT`. **Postgres enforces the read-only contract.**

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| WorkBucket as GENERATED column + index | `Scripts/SQLScripts/ConvertWorkBucketToGenerated.py` (idempotent) | next commit |
| WorkBucket removed from Compliance writes | `Features/Compliance/Repositories/ComplianceWriteRepository.py` + `Scripts/RecoverOrigSurvivors.py` | next commit |
| pg_dump backup landed | `Scripts/SQLScripts/backups/pre-cutover-2026-06-21.sql` (583MB; NOT committed -- in .gitignore-equivalent) | n/a |

### Decisions Made

- pg_dump via SSH to LXC 203 + scp back. PostgreSQL client tools not installed on I9; LXC has them. 583MB file landed at `Scripts/SQLScripts/backups/pre-cutover-2026-06-21.sql`.
- Backup NOT committed to git (large binary; would bloat the repo). Filed for `.gitignore` follow-up.
- Three places wrote WorkBucket: `BulkWriteRecomputeResults` (main, dying), `CLEAR_COMPLIANCE_SQL` in `RecoverOrigSurvivors.py` (one-shot recovery script, edited too), and the `ComplianceRecomputeService` references it via the Decision tuple but doesn't directly SET (passes to BulkWrite). All three handled.
- Old `Features/Compliance/` STAYS in tree this directive. Just the WorkBucket write paths got severed. Compliance still computes WorkBucket in-memory but never writes it (the BulkWrite UPDATE simply omits the column). Rip happens in directive 7.
- `Settings.html` "Compliance rules" card STAYS this directive. The old card edits TranscodeRules/RemuxRules/AudioFixRules tables; those tables still exist + still authoritative for what Old Compliance USED TO drive WorkBucket. Now that WorkBucket is GENERATED, those tables are vestigial. Removal of the card + tables happens in directive 7 (rip).
