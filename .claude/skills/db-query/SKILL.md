---
name: db-query
description: Query the MediaVortex PostgreSQL database. Use when the user asks to check database tables, run SQL queries, inspect schema, or troubleshoot data.
argument-hint: "[tables | schema <table> | <table> | sql \"SELECT ...\"]"
allowed-tools: Bash(*/venv/Scripts/python.exe *)
---

## MediaVortex Database Query Skill

Run queries against the local MediaVortex PostgreSQL database using the `QueryDatabase.py` script.

**Python executable** (must use the venv):
```
C:/Code/Automation/MediaVortex/venv/Scripts/python.exe
```

**Script path**:
```
C:/Code/Automation/MediaVortex/Scripts/SQLScripts/QueryDatabase.py
```

### Available Commands

Based on the user's request, run the appropriate command:

**List all tables:**
```bash
C:/Code/Automation/MediaVortex/venv/Scripts/python.exe C:/Code/Automation/MediaVortex/Scripts/SQLScripts/QueryDatabase.py tables
```

**Show table schema:**
```bash
C:/Code/Automation/MediaVortex/venv/Scripts/python.exe C:/Code/Automation/MediaVortex/Scripts/SQLScripts/QueryDatabase.py schema <table>
```

**Query a table with filters:**
```bash
C:/Code/Automation/MediaVortex/venv/Scripts/python.exe C:/Code/Automation/MediaVortex/Scripts/SQLScripts/QueryDatabase.py <table> [--where "condition"] [--columns "col1,col2"] [--order "col DESC"] [--limit N] [--count]
```

**Run raw SQL:**
```bash
C:/Code/Automation/MediaVortex/venv/Scripts/python.exe C:/Code/Automation/MediaVortex/Scripts/SQLScripts/QueryDatabase.py sql "SELECT ..."
```

### Argument Handling

- If the user provides `$ARGUMENTS`, parse it to determine which command form to use
- `$0` = first argument (tables, schema, table name, or sql)
- `$1` = second argument (table name for schema, or SQL string for sql)
- If no arguments are given, ask the user what they want to query

### Examples

| User says | Command to run |
|-----------|---------------|
| `/db-query tables` | `...QueryDatabase.py tables` |
| `/db-query schema transcodequeue` | `...QueryDatabase.py schema transcodequeue` |
| `/db-query transcodequeue --limit 10` | `...QueryDatabase.py transcodequeue --limit 10` |
| `/db-query sql "SELECT status, COUNT(*) FROM transcodequeue GROUP BY status"` | `...QueryDatabase.py sql "SELECT ..."` |
| `/db-query transcodequeue` | `...QueryDatabase.py transcodequeue` |

### Notes

- The script defaults to LIMIT 50. Use `--limit 0` for unlimited.
- The script does NOT commit modifications — raw SQL writes are rolled back.
- Table/column names are lowercase in PostgreSQL but the app uses PascalCase via CaseInsensitiveDict.
- Known typo: `transcodeattempts.ffpmpegcommand` (double 'p').
