-- directive: db-maintenance-standard-tools
-- Per-table autovacuum + analyze reloptions for high-churn tables.
-- Idempotent: ALTER TABLE ... SET (reloptions) overwrites cleanly.
-- Reversible: ALTER TABLE <name> RESET (autovacuum_vacuum_scale_factor, ...).

ALTER TABLE activejobs SET (
  autovacuum_vacuum_scale_factor = 0.05,
  autovacuum_vacuum_threshold = 10,
  autovacuum_analyze_scale_factor = 0.05,
  autovacuum_analyze_threshold = 10
);

ALTER TABLE transcodeprogress SET (
  autovacuum_vacuum_scale_factor = 0.05,
  autovacuum_vacuum_threshold = 10,
  autovacuum_analyze_scale_factor = 0.05,
  autovacuum_analyze_threshold = 10
);

ALTER TABLE qualitytestingqueue SET (
  autovacuum_vacuum_scale_factor = 0.05,
  autovacuum_vacuum_threshold = 10,
  autovacuum_analyze_scale_factor = 0.05,
  autovacuum_analyze_threshold = 10
);

ALTER TABLE qualitytestprogress SET (
  autovacuum_vacuum_scale_factor = 0.05,
  autovacuum_vacuum_threshold = 10,
  autovacuum_analyze_scale_factor = 0.05,
  autovacuum_analyze_threshold = 10
);

ALTER TABLE servicestatus SET (
  autovacuum_vacuum_scale_factor = 0.05,
  autovacuum_vacuum_threshold = 10,
  autovacuum_analyze_scale_factor = 0.05,
  autovacuum_analyze_threshold = 10
);

ALTER TABLE workers SET (
  autovacuum_vacuum_scale_factor = 0.05,
  autovacuum_vacuum_threshold = 10,
  autovacuum_analyze_scale_factor = 0.05,
  autovacuum_analyze_threshold = 10
);

-- Audit: print the resulting reloptions for operator confirmation.
SELECT relname, reloptions
FROM pg_class
WHERE relname IN ('activejobs','transcodeprogress','qualitytestingqueue',
                  'qualitytestprogress','servicestatus','workers')
ORDER BY relname;
