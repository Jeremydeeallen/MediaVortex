-- directive: db-maintenance-no-partition
-- pg_cron-scheduled maintenance for the mediavortex database.
-- No active jobs today -- log volume (~30-60K rows/day post-bug-fix) does not warrant
-- scheduled retention. The cron extension is installed so future jobs are SQL-only.
-- Each schedule is wrapped so a re-run is idempotent.

-- TEMPLATE: log retention. Uncomment + edit <DAYS> when daily volume crosses ~100K/day
-- or table size approaches operator preference.
-- SELECT cron.schedule(
--   'prune_logs_retention',
--   '15 3 * * *',
--   $$DELETE FROM logs WHERE timestamp < NOW() - INTERVAL '<DAYS> days';$$
-- )
-- WHERE NOT EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'prune_logs_retention');

-- TEMPLATE: weekly VACUUM ANALYZE on a specific table (rarely needed when autovacuum is
-- tuned, but the syntax lives here so the next operator does not re-derive it).
-- SELECT cron.schedule(
--   'vacuum_<table>_weekly',
--   '30 4 * * 0',
--   $$VACUUM ANALYZE <table>;$$
-- )
-- WHERE NOT EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'vacuum_<table>_weekly');

-- Audit: print whatever is currently scheduled.
SELECT jobid, jobname, schedule, command, active
FROM cron.job
ORDER BY jobname;
