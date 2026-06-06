# PostgreSQL Maintenance -- Fleet Baseline

Same stack, every PostgreSQL cluster you own. Three extensions, six per-table autovacuum reloptions, one operator-runnable apt+SQL bringup. Copy the three artifacts in `Scripts/SQLScripts/Maintenance/` to any other cluster, edit the table list and DB name, apply.

## What this stack is

| Extension | Role | Why we use it |
|---|---|---|
| `pg_cron` | In-DB job scheduler | SQL-native cron rows in `cron.job`. Survives application restarts. Same `cron.schedule(...)` pattern across every cluster. |
| `pg_repack` | Online VACUUM FULL / REINDEX | Operator-triggered when one table is genuinely bloated. No scheduled use. |
| `pgstattuple` | Bloat measurement | The "is this table actually bloated?" answer before reaching for `pg_repack`. |

`pg_partman` is **intentionally omitted** at MediaVortex's scale. Steady-state log volume after the `filescanning-repo-attrerror-fix` (commit 99275ad) is ~30-60K rows/day; a plain `logs` table sustains for years under default autovacuum. The "add partitioning if volume crosses 100K/day" recipe is at the bottom of this doc -- install + migrate-in-place when the math says so, not preemptively.

## One-time per-cluster bringup

```bash
# Stop the application's WebService + WorkerService first
ssh root@<db-host>
cd /path/to/MediaVortex/Scripts/SQLScripts/Maintenance
./ClusterBaseline.sh
```

The script:
1. `apt install` of `pg_cron` + `pg_repack`
2. Backs up `postgresql.conf` to `.bak.<timestamp>`
3. Adds `shared_preload_libraries = 'pg_cron'`, `cron.database_name = '<dbname>'`, `cron.timezone = 'UTC'`
4. Restarts the cluster (`systemctl restart postgresql@16-main`)
5. `CREATE EXTENSION IF NOT EXISTS` for `pg_cron`, `pg_repack`, `pgstattuple`
6. Prints the version table for the operator to confirm

Then apply the per-DB SQL:

```bash
psql -d <dbname> -f AutovacuumTuning.sql
psql -d <dbname> -f MaintenancePolicies.sql
```

`AutovacuumTuning.sql` is idempotent (`ALTER TABLE ... SET (reloptions)` overwrites cleanly). `MaintenancePolicies.sql` schedules zero jobs by default at MediaVortex's volume; it's a populated template, not an active job set.

## The cluster is bloated -- what do I do?

```sql
SELECT relname,
       pg_size_pretty(pg_total_relation_size(relid)) AS total,
       n_dead_tup, n_live_tup,
       ROUND(100.0 * n_dead_tup / NULLIF(n_live_tup + n_dead_tup, 0), 1) AS pct_dead
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 10;
```

For any row with `pct_dead > 20` AND `total > 100 MB`:

```sql
SELECT * FROM pgstattuple('<schema>.<table>');
```

If `dead_tuple_percent > 20` or `free_percent > 50` (table has lots of holes), reach for `pg_repack` -- it rewrites the table without holding an ACCESS EXCLUSIVE lock:

```bash
sudo -u postgres pg_repack -d <dbname> -t <table>
```

`pg_repack` requires the table to have a PRIMARY KEY or a UNIQUE NOT NULL constraint. Runtime is roughly the size of the table; expect transient disk-space doubling.

## What's scheduled?

```sql
SELECT jobid, jobname, schedule, command, active FROM cron.job ORDER BY jobname;
SELECT jobname, status, start_time, end_time
FROM cron.job_run_details
ORDER BY start_time DESC LIMIT 20;
```

At MediaVortex's current scale: nothing scheduled. The cron extension is installed so changes are SQL-only when scheduling becomes warranted.

## Schedule a one-off task

```sql
-- Run once at 2026-06-15 02:00 UTC
SELECT cron.schedule(
  'oneoff_<task-name>',
  '0 2 15 6 *',
  $$<SQL>;$$
);

-- Run every night at 03:15 UTC
SELECT cron.schedule(
  'nightly_<task-name>',
  '15 3 * * *',
  $$<SQL>;$$
);

-- Cancel
SELECT cron.unschedule('<task-name>');
```

Output goes to `cron.job_run_details`. Use the `MaintenancePolicies.sql` template patterns for retention and weekly VACUUM examples.

## Use this stack on another DB I own

Three changes for a new cluster:
1. **`ClusterBaseline.sh`**: change `PG_DBNAME` default (line ~12) to the new DB name.
2. **`AutovacuumTuning.sql`**: replace the six MediaVortex table names with that DB's hot-and-cold table list. Pick the six (or however many) tables with the highest dead-tuple ratios from the bloat query above.
3. **`MaintenancePolicies.sql`**: usually no change -- the template comments already cover the common patterns.

Then run on the new host:
```bash
./ClusterBaseline.sh
psql -d <new-db> -f AutovacuumTuning.sql
psql -d <new-db> -f MaintenancePolicies.sql
```

Same recipe, every cluster. Different table lists, same scaffold.

## Rollback the cluster baseline

Removing `pg_cron` requires a cluster restart:
```bash
sudo cp /etc/postgresql/16/main/postgresql.conf.bak.<TS> /etc/postgresql/16/main/postgresql.conf
sudo systemctl restart postgresql@16-main
sudo -u postgres psql -d <dbname> -c "DROP EXTENSION IF EXISTS pg_cron CASCADE;"
```

`pg_repack` and `pgstattuple` are simple `DROP EXTENSION` -- no restart, no shared_preload_libraries entry.

Autovacuum reloptions roll back per-table:
```sql
ALTER TABLE <name> RESET (
  autovacuum_vacuum_scale_factor, autovacuum_vacuum_threshold,
  autovacuum_analyze_scale_factor, autovacuum_analyze_threshold
);
```

## If log volume ever crosses 100K rows/day, add partitioning

The paused directive `.claude/directives/paused/2026-06-06-db-maintenance-standard-tools.md` carries the full partitioning design. Quick add path:

```bash
sudo apt install postgresql-16-partman
sudo -u postgres psql -d <dbname> -c "CREATE EXTENSION pg_partman;"
```

Then convert `logs` to a partitioned parent via the script outlined in that paused directive -- rename existing logs, create a partitioned parent with composite PK `(id, timestamp)` and a `logs_template`, `partman.create_parent` with daily intervals + 30-day retention, COPY the data, swap. Add `partman_maintenance` to `MaintenancePolicies.sql` (hourly `CALL partman.run_maintenance_proc()`). Operator-scheduled migration window: 10-30 minutes.

The trigger threshold (100K/day) is a soft signal -- the real test is whether autovacuum keeps up. If `pg_stat_user_tables` shows `last_autovacuum` for `logs` slipping past 24 hours behind the dead-tuple growth rate, that is the actual call to act.

## Why we made these calls

| Decision | Rationale |
|---|---|
| `pg_cron` installed even with no scheduled jobs | Pays the one-time cluster-restart cost up front. Future scheduling is SQL-only. Symmetric fleet baseline. |
| No `pg_partman` today | At 30-60K rows/day, plain table + default autovacuum sustains for years. `pg_partman`'s value scales with row velocity. |
| Per-table autovacuum reloptions on six tables | High-churn tables (`activejobs`, `transcodeprogress`, `qualitytestingqueue`, `qualitytestprogress`, `servicestatus`, `workers`) sit at 90-100% dead-tuple ratios under default settings. Tuning fixes them independently of `logs`. |
| `pg_repack` operator-triggered, never scheduled | Bloat is event-driven, not periodic. Scheduling `pg_repack` blindly would burn IO for no gain in steady state. |
| No bespoke `/Maintenance` UI | `cron.job_run_details`, `pgstattuple`, pgAdmin are the portable observability surface. Building UI would couple maintenance to one app. |

## Related artifacts

- `Scripts/SQLScripts/Maintenance/ClusterBaseline.sh` -- the apt+postgresql.conf+restart+extension script
- `Scripts/SQLScripts/Maintenance/AutovacuumTuning.sql` -- per-table reloptions
- `Scripts/SQLScripts/Maintenance/MaintenancePolicies.sql` -- cron template (no active jobs at MV scale)
- `Tests/Contract/TestMaintenanceBaseline.py` -- skip-when-not-deployed contract assertions
- `.claude/directives/paused/2026-06-06-db-maintenance-standard-tools.md` -- the partitioning design, preserved for the "if volume ever warrants" case
