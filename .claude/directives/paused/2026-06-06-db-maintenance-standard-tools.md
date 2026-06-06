# Current Directive

**Set:** 2026-06-06
**Status:** Active 2026-06-06 -- phase: IMPLEMENTING
**Slug:** db-maintenance-standard-tools
**Replaces:** (none -- new ground)

## Outcome

The MediaVortex PostgreSQL cluster (CT 203) is maintained by an industry-standard stack -- `pg_cron` for scheduling, `pg_partman` for time-series retention, `pg_repack` for on-demand bloat removal, `pgstattuple` for bloat measurement -- plus per-table autovacuum tuning. The `logs` table is partitioned by day; retention runs via `DROP PARTITION` (O(1)) instead of batched `DELETE` (O(rows)). Steady-state `logs` size is bounded by the retention window. The exact same stack and the same three deployable artifacts (`ClusterBaseline.sh`, `MaintenancePolicies.sql`, `AutovacuumTuning.sql`) constitute the operator's portable fleet baseline -- copy them to any other PostgreSQL cluster they own and apply with table-name substitutions.

## Acceptance Criteria

1. **Extensions installed in the cluster.** `\dx` in `mediavortex` lists `pg_cron`, `pg_partman`, `pg_repack`, `pgstattuple`. Verifiable:
   ```sql
   SELECT extname FROM pg_extension
   WHERE extname IN ('pg_cron','pg_partman','pg_repack','pgstattuple');
   ```
   Returns four rows.

2. **`pg_cron` wired to the application database.** `SHOW shared_preload_libraries` contains `pg_cron`; `SHOW cron.database_name` returns `mediavortex`. Without this, scheduled jobs do not fire.

3. **`logs` table is partitioned by day on `timestamp`.** `\d+ logs` shows `Partition key: RANGE ("timestamp")`. `partman.part_config` has exactly one row with `parent_table = 'public.logs'`, `partition_interval = '1 day'`, `retention = '30 days'`, `retention_keep_table = false`. (Daily granularity over weekly: keeps the dropped-partition unit small and bounds vacuum/freeze work.)

4. **All pre-migration `logs` rows preserved through the cutover.** Pre-migration `COUNT(*)` from `logs` is captured to the migration script's audit output; post-migration `COUNT(*)` from the partitioned `logs` matches within a tolerance equal to rows written during the cutover window. An `mvarchive_logs_pre_partition_YYYY-MM-DD.sql.gz` dump is produced and retained on the host until 30 days post-cutover.

5. **Retention enforced by `pg_partman` + `pg_cron` daily.** 8 days after the cutover, `SELECT MIN("timestamp") FROM logs >= NOW() - INTERVAL '31 days'` (one-day grace for the just-rotated partition). The retention window is `partman.part_config.retention`, not a value in any application code.

6. **`partman.run_maintenance_proc()` scheduled hourly.** `SELECT * FROM cron.job WHERE command LIKE '%run_maintenance_proc%'` returns one enabled row. `cron.job_run_details` shows `status='succeeded'` for runs in the last 6 hours.

7. **Per-table autovacuum reloptions on high-churn tables.** `activejobs`, `transcodeprogress`, `qualitytestingqueue`, `qualitytestprogress`, `servicestatus`, `workers` each have `autovacuum_vacuum_scale_factor=0.05` and `autovacuum_vacuum_threshold=10` in their `reloptions`. Verifiable:
   ```sql
   SELECT relname, reloptions FROM pg_class
   WHERE relname IN ('activejobs','transcodeprogress','qualitytestingqueue',
                     'qualitytestprogress','servicestatus','workers');
   ```
   Every row's `reloptions` contains both keys.

8. **`logs` steady-state size bounded.** 14 days after the cutover, `pg_total_relation_size('public.logs') < 3 GB` at current ingest rates (~1.4M rows/day x 30d retention x avg row width + indexes). If the projection is exceeded by >50%, this is a signal to escalate to per-loglevel retention or shorter window -- it does not invalidate the design.

9. **Three deployable scripts exist and are runnable on a throwaway cluster.** Files exist:
   - `Scripts/SQLScripts/Maintenance/ClusterBaseline.sh`
   - `Scripts/SQLScripts/Maintenance/MaintenancePolicies.sql`
   - `Scripts/SQLScripts/Maintenance/AutovacuumTuning.sql`

   A smoke run against an empty PostgreSQL 16 container reproduces the same `\dx` and `cron.job` state as criterion 1+6 -- the scripts are self-contained and idempotent (re-running produces no errors and no double-scheduled jobs).

10. **Migration script exists and is idempotent.** `Scripts/SQLScripts/Maintenance/MigrateLogsToPartitioned.py` partitions `logs` if not already partitioned, leaves it alone if already partitioned. Re-running on a partitioned table is a no-op (zero rows moved, zero errors).

11. **Fleet baseline doc exists.** `Docs/PostgreSQLMaintenance.md` describes (a) what the stack is and why, (b) the one-time per-cluster `apt install` + `postgresql.conf` edit + extension creates, (c) the per-DB SQL deploy, (d) operator runbook for "this DB is bloated" / "what's scheduled" / "force-run a job", and (e) the rollback path if pg_cron causes contention. Links to the three scripts.

12. **No application-side retention values.** `grep -rEn 'retain.{0,3}=.{0,3}[0-9]+\b|RETENTION_DAYS|LOG_RETAIN' Features/ Repositories/ Services/ Core/ WebService/ WorkerService/` returns zero hits that name a log-retention integer literal. Retention lives in `partman.part_config` only.

## Out of Scope

- `pg_repack` runtime jobs. The extension is installed; using it is an on-demand operator action when a specific table needs unblocking. No scheduled `pg_repack` runs.
- `postgres_exporter` / Prometheus / Grafana setup. Recommended in the fleet doc as the next layer; not built here. (Filed as follow-up directive candidate.)
- Partitioning of other tables (`scanjobs`, `transcodeattempts`, `mediafilesarchive`, `jellyfinoperations`). They are an order of magnitude smaller; revisit only if any crosses 1 GB.
- Per-loglevel retention (separate windows for INFO / WARNING / ERROR). One unified 30-day window is simpler and travels cleanly to other DBs. Re-evaluated at criterion 8 review.
- Application-side log shipping (Loki, Elasticsearch) -- distinct concern.
- Backup strategy (pgBackRest, pg_dump scheduling) -- distinct concern.
- A bespoke `/Maintenance` UI in MediaVortex. Observability surface is `cron.job_run_details` / `partman.part_config` / pgAdmin / future Grafana.
- Changes to the `LoggingService` Python API or the `logs` schema columns. Partitioning is a storage-layer change; readers/writers are unaffected.

## Constraints

- **Cluster restart required once.** Adding `pg_cron` to `shared_preload_libraries` needs `systemctl restart postgresql`. WebService + WorkerService must be stopped (or tolerant of brief DB downtime). Operator schedules the window.
- **Migration downtime window: 10-30 min.** Partitioning an existing 4 GB table requires creating the partitioned parent, copying rows, swapping names. Workers paused; WebService writes redirected or paused.
- **Cluster runs on Ubuntu 24.04 + PostgreSQL 16.13** -- PGDG repos provide all four extensions.
- **DB-driven config invariant** (project rule): retention values live in `partman.part_config`, never in `.py` files.
- **Idempotency invariant** (`.claude/rules/data-integrity.md`): every script in `Scripts/SQLScripts/Maintenance/` re-runs cleanly.
- **PascalCase** for new Python file/function/class names. SQL identifiers follow existing lowercase Postgres convention because pg_partman API requires it.

## Escalation Defaults

- **Cluster restart** -> operator decides timing. Claude prepares the runbook and stops services.
- **Cutover migration window** -> operator decides timing; Claude prepares the migration script + a verified-in-throwaway-cluster dry run + rollback path.
- **Daily vs. weekly partition** -> daily. Smaller drop unit, more uniform bloat profile, cheaper retention enforcement.
- **Unified vs. per-loglevel retention** -> unified 30d. Fleet-portable. Re-evaluate at criterion 8 if size exceeds projection.
- **Risk tolerance: low** for the cutover (data-integrity); medium for the autovacuum tuning (reversible reloptions); low for the cluster restart (one-time).

## Engineering Calls Already Made

- **pg_cron over pgAgent / app-side scheduler.** pg_cron is in-DB, survives any application restart, ships in PGDG, and the same `cron.schedule(...)` row pattern travels verbatim across every cluster. App-side schedulers don't.
- **pg_partman over manual partition management.** Handles partition creation (`run_maintenance_proc`), retention dropping, and pre-makes future partitions. Manual partition mgmt is the recurring-toil version of the same thing.
- **Daily partition granularity.** Weekly partitions accumulate more dead tuples between drops; daily are smaller drop units and more predictable.
- **30-day unified retention.** ERROR-only retention extension is a future option but adds per-DB customization that defeats "same baseline everywhere." 30d at 1.4M rows/day -> ~42M rows, well-bounded.
- **Three-script delivery shape.** `ClusterBaseline.sh` + `MaintenancePolicies.sql` + `AutovacuumTuning.sql` map 1:1 to the three operational layers (OS, scheduling, per-table). Same files copy to any other PG cluster; only `AutovacuumTuning.sql` and the `partman.create_parent` call need per-cluster table-name edits.
- **No bespoke `/Maintenance` UI.** Building one couples maintenance observability to MediaVortex's frontend; the fleet wants a portable surface (`cron.job_run_details`, pgAdmin, Grafana). Skipping a UI is a feature.
- **Migration via Python script (not raw SQL).** The migration is a guarded multi-step procedure (count -> dump -> create parent -> attach existing as initial partition OR copy -> swap -> verify). Python lets us interleave count assertions and rollback. Lives next to other migration scripts in `Scripts/SQLScripts/`.

## Status

Active 2026-06-06 -- phase: IMPLEMENTING -- Stage A artifacts in progress; Stages B/C/D require operator-scheduled windows.

### Files

```
Scripts/SQLScripts/Maintenance/ClusterBaseline.sh             -- CREATE: apt install + postgresql.conf + CREATE EXTENSION
Scripts/SQLScripts/Maintenance/MaintenancePolicies.sql        -- CREATE: cron.schedule(...) rows + partman.create_parent
Scripts/SQLScripts/Maintenance/AutovacuumTuning.sql           -- CREATE: per-table ALTER TABLE ... SET (autovacuum_*)
Scripts/SQLScripts/Maintenance/MigrateLogsToPartitioned.py    -- CREATE: guarded partitioning cutover
Docs/PostgreSQLMaintenance.md                                  -- CREATE: fleet baseline + operator runbook
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
