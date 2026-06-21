# SQL Queries

**Slug:** sqlqueries

## What It Does

Provides an ad-hoc database query interface for troubleshooting. Offers quick-query buttons for common diagnostic queries and a custom SQL execution box.

## Success Criteria

1. Quick-query buttons execute predefined diagnostic queries: Queue Status, Active Jobs, Stuck Jobs, Recent Errors, Error Summary, Service Health, Database Info.
2. Custom SQL can be entered and executed from the UI.
3. Query results are displayed in a formatted table.
4. Recent failures are shown with a force-complete option for stuck jobs.
5. The /SQLQueries page is accessible from the navigation bar.
6. [BUG] The CLI query tool (`Scripts/SQLScripts/QueryDatabase.py`) does not truncate text columns unless the operator opts in. Long values (error messages, file paths, FFmpeg commands) are shown in full by default, with an optional `--width N` flag to truncate for readability.

## Status

COMPLETE

## Scope

```
Features/SQLQueries/**
```

## Files

| File | Role |
|------|------|
| Features/SQLQueries/SQLQueriesController.py | Flask Blueprint -- query endpoints |
| Templates/SQLQueries.html | SQL query UI page |

## Cross-Vertical Contract

### Columns the SQLQueries vertical WRITES

| Column | Written by |
|---|---|
| (any column the operator types into the SQL box) | operator |

### Columns READS

| Column | Read by | Owner |
|---|---|---|
| (any) | operator queries | any vertical |

### Stable function entry points

None internal. The vertical is a thin Flask wrapper over DatabaseService.ExecuteQuery / ExecuteNonQuery.

### HTTP API surface

| Method + URL | Purpose |
|---|---|
| GET /SQLQueries | Render the ad-hoc query page |
| POST /api/SQLQueries/Run | Run a SQL string |
| GET /api/SQLQueries/QuickQueries/{name} | Predefined diagnostic queries |
| GET /api/SQLQueries/GetActiveJobs | Used by nav badge |

### What is EXPLICITLY NOT a contract

- The set of "quick query" names -- expandable
- Output format of /api/SQLQueries/Run -- consumers parse Data array
- Truncation behavior of long text columns -- tunable via --width flag
