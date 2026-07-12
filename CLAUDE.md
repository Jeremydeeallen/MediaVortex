# CLAUDE.md

MediaVortex: Python/Flask media transcoding system. Scans files, runs FFmpeg, integrates with Jellyfin.

## Where everything lives

- **Target architecture:** `ARCHITECTURE.md` (target-state vertical roster, cross-cutting concerns, data flow, deprecated/dying — every directive is a delta against this)
- **Terminology:** `GLOSSARY.md` (four buckets: project vocabulary, media/encoding, job model, infrastructure; each entry names an authoritative source; deprecated terms carry replacement pointer)
- **Framework rules:** `.claude/rules/*.md` (auto-loaded; invariants only — details in `.claude/rules-details/`)
- **Mechanically enforced standards:** `.claude/standards/index.md` (phase gates + R-rules)
- **Current directive:** `.claude/directive.md` (auto-loaded; empty + no marker = hook refuses code edits)
- **Task-delegation opt-in:** `.claude/.task-delegation-on` (presence = task-delegation mode enabled for no-directive sessions; operator-only — `New-Item` to enable, `Remove-Item` to disable; warning prepended to every assistant response while active)
- **Feature contracts:** colocated `*.feature.md` next to primary code
- **Pipeline contracts:** colocated `*.flow.md` next to entry-point files
- **Known issues:** `memory/KNOWN-ISSUES.md`

## Commands

```bash
py StartMediaVortex.py                              # start all services
py StopMediaVortex.py                               # stop all services
py WebService/Main.py                               # web only (port 5000)
py -m pytest Tests/Contract/                        # all contract tests
py -m pytest Tests/Contract/TestQueueGet.py         # single test
py Scripts/SQLScripts/QueryDatabase.py tables       # list tables
py Scripts/SQLScripts/QueryDatabase.py schema <t>   # show schema
py Scripts/SQLScripts/QueryDatabase.py sql "..."    # arbitrary SQL
```

## Database

- **PostgreSQL 16** on LXC CT 203 (`10.0.0.15:5432`); db/user/password all `mediavortex`
- Host via `MEDIAVORTEX_DB_HOST` env var (defaults to localhost on user-level)
- Encoding MUST be UTF-8: `ENCODING 'UTF8' LC_COLLATE='en_US.UTF-8' LC_CTYPE='en_US.UTF-8' TEMPLATE=template0`
- `psycopg2` with `RealDictCursor` returns lowercase keys; `CaseInsensitiveDict` maps to PascalCase
- **Known typo:** column `transcodeattempts.ffpmpegcommand` (double 'p') — code must match
- **LIKE queries** require `EscapeLikePattern()` from `Core.Database.DatabaseService` with `ESCAPE '!'` — paths contain `!`, `%`, `_`

## Naming convention (CRITICAL)

**PascalCase everywhere**: variables, functions, classes, files, DB tables/columns, routes. Python built-ins exempt (`__init__`, `str()`, `len()`).

## Key patterns

```python
# API response
return jsonify({'Success': True/False, 'Message': '...', 'Data': {...}}), 200

# Logging
LoggingService.LogInfo("msg", "ClassName", "MethodName")
LoggingService.LogException("msg", exception, "ClassName", "MethodName")

# DB ops
DatabaseService.ExecuteQuery(...)       # SELECT, returns list[CaseInsensitiveDict]
DatabaseService.ExecuteNonQuery(...)    # INSERT/UPDATE/DELETE, auto-commits

# Paths -- never os.path on a path-named variable; use Core.Path.LocalPath / Core.Path.Path
from Core.Path.LocalPath import LocalExists, LocalBasename, LocalDirname, LocalJoin, LocalSplitExt, LocalIsFile, LocalIsDir, LocalGetSize, LocalGetMTime
# Run /mediavortex-paths for the full lookup (os.path.* -> canonical mapping + canonical-vs-local decision).
```

## Two microservices

- **WebService** (Flask + UI, port 5000)
- **WorkerService** (unified: transcoding + VMAF + scanning; reads capability flags from `Workers` table)

Started/stopped via `ServiceLifecycleManager` from `StartMediaVortex.py`. Architecture documented in `ARCHITECTURE.md` (vertical roster, cross-cutting concerns, data flow); per-feature contracts in `Features/<Name>/*.feature.md`; pipeline detail in `transcode.flow.md`.

## Python environment

`venv/` at repo root. `py -m venv venv` (Windows), `python3 -m venv venv` (Mac/Linux). Activate; then `python` + `pip` work cross-platform. All deps in `requirements.txt`. See `.claude/rules/python-environment.md`.

## Reading order when context-limited

1. `.claude/rules/*.md` (auto-loaded — invariants)
2. `ARCHITECTURE.md` (target state — which verticals exist, what each owns)
3. `.claude/directive.md` (the current ask)
4. Colocated `*.flow.md` first (nav hub) -> partial Read of the relevant `ST<N>` section; colocated `*.feature.md` only when stage scope is insufficient (R18 caps it at limit<=50)
5. Source code (last resort, targeted reads)

For pipeline-shaped code: add `# see <flow-slug>.ST<N>` anchor inline on the def/class line; R1 then accepts the partial flow-doc Read in lieu of colocated feature-md preread.

When editing a `*.feature.md` that references `transcode.flow.md` stage labels (e.g. "Stage 5", "Stage 3.5"), migrate the prose to `ST<N>` form in the same commit. Discipline note from `flow-docs-as-hub` close: the dual-label coexistence is a transition tax that compounds; sweep opportunistically rather than en masse.

For details on any rule: read the colocated `.claude/rules-details/<name>.md` on demand.
