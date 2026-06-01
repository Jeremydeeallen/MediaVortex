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
