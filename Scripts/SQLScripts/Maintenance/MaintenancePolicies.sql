-- directive: db-maintenance-standard-tools
-- pg_cron-scheduled maintenance for the mediavortex database.
-- Idempotent: each schedule is wrapped so a re-run is a no-op if already present.
-- Only one job today: pg_partman maintenance, which creates next-day partitions
-- and applies retention. Run hourly so future partitions exist well before midnight.

-- partman_maintenance: creates upcoming day-partitions and drops partitions
-- past the configured retention window (UPDATE partman.part_config to change).
SELECT cron.schedule('partman_maintenance', '0 * * * *', 'CALL partman.run_maintenance_proc();')
WHERE NOT EXISTS (
  SELECT 1 FROM cron.job WHERE jobname = 'partman_maintenance'
);

-- Audit: print the scheduled jobs.
SELECT jobid, jobname, schedule, command, active
FROM cron.job
ORDER BY jobname;
