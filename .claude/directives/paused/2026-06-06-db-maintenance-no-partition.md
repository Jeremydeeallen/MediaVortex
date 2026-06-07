# Current Directive

**Set:** 2026-06-06
**Status:** Active -- phase: IMPLEMENTING
**Slug:** db-maintenance-no-partition
**Replaces:** `.claude/directives/paused/2026-06-06-db-maintenance-standard-tools.md` (paused -- partitioned design abandoned after `filescanning-repo-attrerror-fix` (commit 99275ad) cut log volume 50x; the paused directive's premise of "logs grows unbounded at 1.4M rows/day" no longer applies)

## Outcome

The MediaVortex PostgreSQL cluster (CT 203) gets the **right-sized** version of the industry-standard maintenance stack: `pg_cron` for in-DB scheduling, `pg_repack` for on-demand bloat removal, `pgstattuple` for bloat measurement, plus per-table autovacuum tuning. **`pg_partman` and `logs` partitioning are deliberately excluded** -- at the new steady-state log volume (~30-60K rows/day vs. the 1.4M/day pre-fix), a plain `logs` table with default autovacuum sustains for years. The same three deployable artifacts (`ClusterBaseline.sh`, `MaintenancePolicies.sql`, `AutovacuumTuning.sql`) constitute the operator's portable fleet baseline -- copy to any other PostgreSQL cluster they own and apply with table-name substitutions. Partitioning is in the runbook as a "if/when you outgrow this" recipe rather than as installed infrastructure.

## Acceptance Criteria

1. **Extensions installed.** `\dx` in `mediavortex` lists `pg_cron`, `pg_repack`, `pgstattuple`. `pg_partman` is intentionally NOT installed. Verifiable:
   ```sql
   SELECT extname FROM pg_extension
   WHERE extname IN ('pg_cron','pg_repack','pgstattuple');
   ```
   Returns three rows.

2. **`pg_cron` wired to the application database.** `SHOW shared_preload_libraries` contains `pg_cron`; `SHOW cron.database_name` returns `mediavortex`; `SHOW cron.timezone` returns `UTC`.

3. **Per-table autovacuum reloptions on high-churn tables.** `activejobs`, `transcodeprogress`, `qualitytestingqueue`, `qualitytestprogress`, `servicestatus`, `workers` each have `autovacuum_vacuum_scale_factor=0.05`, `autovacuum_vacuum_threshold=10`, `autovacuum_analyze_scale_factor=0.05`, `autovacuum_analyze_threshold=10` in their `reloptions`. Verifiable:
   ```sql
   SELECT relname, reloptions FROM pg_class
   WHERE relname IN ('activejobs','transcodeprogress','qualitytestingqueue',
                     'qualitytestprogress','servicestatus','workers');
   ```
   Every row's `reloptions` contains the four required keys.

4. **Three deployable scripts exist and are runnable on a throwaway cluster.** Files exist:
   - `Scripts/SQLScripts/Maintenance/ClusterBaseline.sh`
   - `Scripts/SQLScripts/Maintenance/MaintenancePolicies.sql`
   - `Scripts/SQLScripts/Maintenance/AutovacuumTuning.sql`

   A smoke run against an empty PostgreSQL 16 container reproduces criteria 1+2+3 on a fresh DB. Scripts are idempotent -- re-running produces no errors and no duplicate state.

5. **MaintenancePolicies.sql is a non-empty template.** No active cron jobs scheduled today (volume doesn't warrant any), but the file contains a commented-out example `cron.schedule(...)` for "delete logs older than N days" plus the syntax for scheduling any `partman.run_maintenance_proc` style job, so a future operator can uncomment + edit + apply without re-reading documentation.

6. **Fleet baseline doc exists.** `Docs/PostgreSQLMaintenance.md` describes (a) what the stack is and why pg_partman is omitted at MediaVortex's current scale, (b) the one-time per-cluster `apt install` + `postgresql.conf` edit + extension creates, (c) per-DB SQL deploy, (d) operator runbook for "this DB is bloated" / "what's scheduled" / "force-run a job" / "if log volume ever crosses 100K/day, here is how to add partitioning later", (e) rollback path. Links to the three scripts.

7. **Contract test exists and is green.** `Tests/Contract/TestMaintenanceBaseline.py` exercises criteria 1, 2, 3, skipping with informative messages on a dev box that hasn't applied the baseline. After cluster baseline applied: every test passes.

## Out of Scope

- `pg_partman` installation or any partitioning work. Re-evaluate only if `logs` daily growth crosses ~100K rows/day for a sustained week. Recipe to add partitioning later is in the runbook (criterion 6).
- `pg_repack` scheduled runs. Installed only; operator-driven when a specific table is unhealthy.
- `postgres_exporter` / Prometheus / Grafana. Recommended in the runbook as the next observability layer; not built here.
- Partitioning of `scanjobs`, `transcodeattempts`, `mediafilesarchive`, `jellyfinoperations`. All <100 MB; default autovacuum is fine.
- Log shipping to external systems (Loki, Elasticsearch).
- Backup strategy (pgBackRest, pg_dump scheduling). Distinct concern.
- A bespoke `/Maintenance` UI in MediaVortex. Observability lives in `cron.job_run_details` / `pgstattuple` / pgAdmin.
- Changes to LoggingService or the `logs` schema. The bug fix in `filescanning-repo-attrerror-fix` (commit 99275ad) addressed the actual log growth problem; this directive is fleet hygiene, not pressure relief.

## Constraints

- **Cluster restart required once.** Adding `pg_cron` to `shared_preload_libraries` needs `systemctl restart postgresql@16-main`. WebService + WorkerService must be stopped (or tolerant of brief DB downtime). Operator schedules the window (~2-4 min).
- **No migration window required.** With partitioning removed, there is no `logs` cutover. Per-table autovacuum reloptions are metadata-only changes -- applied live.
- **PostgreSQL 16.13 on Ubuntu 24.04** -- PGDG repos provide all three extensions.
- **Idempotency invariant** (`.claude/rules/data-integrity.md`): every script in `Scripts/SQLScripts/Maintenance/` re-runs cleanly.
- **Three of the four files already exist on disk** from the prior (paused) maintenance directive: `AutovacuumTuning.sql` (unchanged), `MaintenancePolicies.sql` (needs trim -- remove `partman_maintenance` job, add commented template), `ClusterBaseline.sh` (needs trim -- remove `postgresql-16-partman` apt install + `pg_partman` CREATE EXTENSION).

## Escalation Defaults

- **Cluster restart** -> operator decides timing. Claude prepares the runbook and stops services.
- **Re-introduce partitioning** -> operator decision when/if log volume warrants. The recipe is in the runbook; not Claude's call.
- **Risk tolerance: low** for the cluster restart (one-time); medium for autovacuum tuning (reversible reloptions).

## Engineering Calls Already Made

- **Drop `pg_partman` entirely.** At 30-60K rows/day, the default autovacuum sustains `logs` for years. `pg_partman`'s value scales with row velocity; at low velocity, it's complexity without benefit. The runbook documents the "add partitioning if volume ever exceeds 100K/day" path for symmetry with the fleet template.
- **Schedule zero cron jobs today.** Without `pg_partman`, the only candidate jobs would be DELETE-based retention -- premature at this volume. Leaving `MaintenancePolicies.sql` as a populated template means future operator changes are SQL-only, not "re-read all the docs" work.
- **Keep `pg_cron` extension install in scope despite no scheduled jobs.** Pays the one-time cluster-restart cost up front so future scheduling work is SQL-only and the fleet baseline is symmetric across DBs (one apt+restart recipe per cluster).
- **Carry over the three existing artifacts.** `AutovacuumTuning.sql` is unchanged. `ClusterBaseline.sh` + `MaintenancePolicies.sql` are trimmed in place. `MigrateLogsToPartitioned.py` is deleted from the prior plan (it was never written to disk after the R-rule hook refusals, so there's nothing to remove).

## Status

Active 2026-06-06 -- phase: IMPLEMENTING. Three carry-over files trimmed (ClusterBaseline.sh, MaintenancePolicies.sql) or kept (AutovacuumTuning.sql); runbook created at Docs/PostgreSQLMaintenance.md. TestMaintenanceBaseline.py contract test is the last artifact.

### Files

```
Scripts/SQLScripts/Maintenance/ClusterBaseline.sh             -- EDIT: remove pg_partman apt install + CREATE EXTENSION
Scripts/SQLScripts/Maintenance/MaintenancePolicies.sql        -- EDIT: remove partman_maintenance job; add commented retention template
Scripts/SQLScripts/Maintenance/AutovacuumTuning.sql           -- KEEP: unchanged from paused directive
Docs/PostgreSQLMaintenance.md                                  -- CREATE: trimmed runbook (no partitioning chapter; partitioning recipe in "future" section)
Tests/Contract/TestMaintenanceBaseline.py                      -- CREATE: skip-when-not-deployed assertions for criteria 1-3
```

### Promotions

(Populated at DELIVERING.)

| Source artifact | Target file | Commit |
|---|---|---|
| TBD | TBD | TBD |

### Verification

(Populated at VERIFYING; one entry per acceptance criterion.)

### Decisions Made

(Populated during execution as ambiguities surface.)
