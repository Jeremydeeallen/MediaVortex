# Data Integrity

Schema changes must be backward-compatible. User data must never be silently lost or corrupted.

## Verified conventions
- PostgreSQL migrations in `Scripts/SQLScripts/` are idempotent (IF NOT EXISTS, ON CONFLICT)
- New columns are nullable or have defaults
- `MediaFilesArchive` preserves original metadata before any destructive replacement
- `DatabaseService.ExecuteNonQuery()` auto-commits; reads use `ExecuteQuery()`

## Required reading
- `CLAUDE.md` -- Database section, key tables
- `transcode.flow.md` -- post-transcode data flow (archive -> replace -> re-probe)

## Common mistakes
- Adding a required (NOT NULL, no default) column to an existing table
- Dropping a column in the same migration that removes the code reading it
- Running raw DELETE/UPDATE without WHERE clause scoping
- Forgetting `EscapeLikePattern()` for LIKE queries (paths contain `%`, `_`, `!`)
