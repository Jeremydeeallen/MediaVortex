# Repository Split: Feature-Vertical Migration of `DatabaseManager.py`

## Status

BACKLOG -- not on the active feature stack. Drafted 2026-05-27 from a CEO-mode design discussion. Move to active by adding the slug to `.claude/current-feature`.

### Progress

- [x] Feature doc drafted (this file)
- [ ] Operator review + criteria approval
- [ ] Inventory pass: tag every method in `Repositories/DatabaseManager.py` with its target aggregate home (read-only, no edits)
- [ ] Extract shared helpers (`PrivateNormalizePathToFilesystemCase`, `EscapeLikePattern`) to `Core/Database/` utility modules; update existing callers
- [ ] Move ActiveJobs aggregate (smallest, narrowest caller set) -> verify
- [ ] Move TranscodeAttempts + TranscodeFiles + TranscodeProgress aggregate -> verify
- [ ] Move MediaFiles + MediaFilesArchive aggregate -> verify
- [ ] Move TranscodeQueue methods into existing `Features/TranscodeQueue/TranscodeQueueRepository.py` -> verify
- [ ] Move remaining aggregates (Workers, ProblemFiles, etc.) -> verify
- [ ] Delete `Repositories/DatabaseManager.py` once empty; remove the `Repositories/` directory
- [ ] Update `CLAUDE.md` to drop the "Legacy code being migrated" line

## What It Does

Finishes a migration the codebase already started: breaks `Repositories/DatabaseManager.py` (5,785 lines, omnibus data-access module from the pre-feature-vertical era) into per-aggregate repositories colocated with the features that own them. The destination shape already exists in practice -- `Features/FileScanning/FileScanningRepository.py`, `Features/MediaProbe/MediaProbeRepository.py`, `Features/TranscodeQueue/TranscodeQueueRepository.py`, `Features/SystemSettings/SystemSettingsRepository.py` -- this feature completes the pattern for the aggregates still living in the legacy module.

The architectural payoff is reviewability and drift resistance. Per-aggregate modules of under ~800 lines are reviewable in one read; the silent-column-drop class of bug (BUG-0017, BUG-0019 -- both rooted in a hand-maintained UPDATE column list that drifted out of sync with the model) is much less likely when the persistence module is small enough to hold in head. The split also makes the contract-test boundary natural: each repository gets its own `Tests/Contract/Test<Aggregate>Repository.py`.

This is a pure refactor. No behavior change. No new functionality. No performance work.

## Scope

```
Repositories/DatabaseManager.py                          (source -- being broken up)
Features/MediaFiles/MediaFilesRepository.py              (new aggregate home)
Features/TranscodeJob/TranscodeAttemptRepository.py      (new aggregate home)
Features/ServiceControl/ActiveJobRepository.py           (new aggregate home)
Features/TranscodeQueue/TranscodeQueueRepository.py      (existing; absorb)
Core/Database/PathNormalizer.py                          (new -- shared helper)
Core/Database/SqlEscape.py                               (new -- shared helper)
Tests/Contract/Test<Aggregate>Repository.py              (new -- one per aggregate)
```

Explicitly **OUT OF SCOPE:**

- Behavior changes. Move methods verbatim; no "improvements" during the move.
- Performance tuning. Same query shapes; same connection-per-call pattern.
- Connection-lifecycle refactor (shared connections, pooling). That is a separate feature with its own risk profile.
- Replacing the `CaseInsensitiveDict` lowercase-key convention.
- Adding ORM, query builder, or migration framework.
- The architectural single-source-of-truth `SaveMediaFile` refactor (was in the SUPERSEDED `mediafile-persistence-no-drift` doc). May be picked up after this refactor if column-drift is still a concern.

## Success Criteria

1. **`Repositories/DatabaseManager.py` reduced to zero lines (file deleted) or to a thin deprecating shim with a documented removal commit.** Verifiable: `wc -l Repositories/DatabaseManager.py` reports 0 (file absent) or the file content is exclusively `from <new_home> import <Name> as <LegacyName>` re-exports with a `# DEPRECATED, removal target: <commit/date>` header. Survives rename of any internal symbol.

2. **Every method that was in DatabaseManager.py lives in exactly one new home.** No method is duplicated across two repositories. Verifiable: grep for each method name in the final state returns exactly one definition site.

3. **Each new repository owns exactly one aggregate root.** An aggregate is the set of tables that compose one logical entity and write together transactionally (e.g. MediaFiles + MediaFilesArchive; TranscodeAttempts + TranscodeFiles + TranscodeProgress). Verifiable: each repository's method list reads/writes only the tables of its declared aggregate, with documented exceptions for cross-aggregate read queries.

4. **No `BaseRepository` superclass or repository inheritance hierarchy.** Repositories compose `DatabaseService` via constructor injection. Verifiable: `grep -rn "class.*Repository.*Repository.*:" Features/ Core/` returns no matches indicating Repository-to-Repository inheritance.

5. **Cross-aggregate queries live in a feature service that composes multiple repositories, not inside any single repository's private surface.** Example: a query that joins MediaFiles to TranscodeAttempts belongs in a service in `Features/Activity/` (the feature that reads both), not in either repository. Verifiable: grep each repository for `JOIN` keywords against tables outside its declared aggregate -- zero matches.

6. **Contract tests pass at every aggregate move.** Before an aggregate is moved, its current behavior is captured in `Tests/Contract/Test<Aggregate>Repository.py`. After the move, the same tests pass against the new import path. No test is deleted during the move; tests update imports only.

7. **Each aggregate move is its own commit.** No single commit moves more than one aggregate. Verifiable: `git log` for the migration shows N+1 commits for N aggregates (one inventory commit, then one per aggregate).

8. **No regressions in the existing contract test suite.** All passing tests at the start of the refactor still pass at the end. Verifiable: `py -m pytest Tests/Contract/` before vs after produces identical pass count.

9. **Shared helpers extracted, not duplicated.** `PrivateNormalizePathToFilesystemCase` and `EscapeLikePattern` (and any other cross-aggregate helpers identified during inventory) live in one module under `Core/Database/`. Verifiable: grep the codebase for the helper definition -- exactly one match.

10. **Final per-repository line count under 800.** Sustainable cohesion threshold. If any new repository lands over 800 lines, the aggregate it represents needs to be split further or the move was wrong-grained. Verifiable: `wc -l Features/*/Repository.py Core/Database/*.py` reports each file under 800.

11. **`CaseInsensitiveDict` lowercase-key handling stays in `DatabaseService` only.** New repositories must not re-implement the lowercase-to-PascalCase mapping; they consume the existing convention via `DatabaseService.ExecuteQuery` results. Verifiable: grep new repos for `CaseInsensitiveDict` or `lower()` on column names -- no matches.

12. **All existing callers updated to new import paths in the same commit as the move.** No "imports broken in main, fix in a follow-up." Verifiable: each move commit's diff includes both the method's new home and every caller's updated import.

13. **`CLAUDE.md` updated to drop the "Legacy code in top-level `Repositories/` is being migrated" line** once the directory is empty. The migration is no longer in flight; the doc shouldn't claim otherwise. Verifiable: grep CLAUDE.md for "Repositories/" -- zero matches in the legacy-migration context.

## Failure Modes (to recognize at a glance)

- **Cross-aggregate query orphan:** a moved method does a JOIN to a table outside its new repo's aggregate. Fix: query lives in a feature service that composes both repositories.
- **Connection leak from refactor drift:** the per-call open/close pattern was implicit in DatabaseManager. New repos must preserve it (open in try, close in finally). Audit each new repo's connection management.
- **Test rot from caller-import drift:** existing contract tests import `Repositories.DatabaseManager`. Each must be updated in the same commit as the move it depends on. Don't batch import updates "later."
- **"While I'm here" refactor:** the temptation to "improve" a method during the move (better name, cleaner SQL, etc.). Resist. Move first, refactor second, separate commits.
- **`BaseRepository` superclass creeping in:** if two repositories share a helper, extract to `Core/Database/`, don't introduce inheritance.

## Surface

None. This is internal infrastructure with no user-facing surface (no UI, no API endpoint change visible to operators). The operator's experience is unchanged before and after.

## Files

| File | Role |
|------|------|
| `Repositories/DatabaseManager.py` | Source being broken up. End state: deleted or thin shim. |
| `Features/MediaFiles/MediaFilesRepository.py` | New -- MediaFiles + MediaFilesArchive aggregate |
| `Features/TranscodeJob/TranscodeAttemptRepository.py` | New -- TranscodeAttempts + TranscodeFiles + TranscodeProgress aggregate |
| `Features/ServiceControl/ActiveJobRepository.py` | New -- ActiveJobs aggregate (smallest; start here) |
| `Features/TranscodeQueue/TranscodeQueueRepository.py` | Existing -- absorbs queue methods from DatabaseManager |
| `Core/Database/PathNormalizer.py` | New -- shared `PrivateNormalizePathToFilesystemCase` helper |
| `Core/Database/SqlEscape.py` | New -- shared `EscapeLikePattern` helper |
| `Tests/Contract/Test<Aggregate>Repository.py` | New -- one contract test file per aggregate |
| `CLAUDE.md` | Legacy-migration line removed once the directory is empty |
| `Core/Database/database-architecture.feature.md` | Existing sibling -- references this feature when it lands |

## Migration Shape (recommended order)

1. **Inventory commit:** tag every method in `DatabaseManager.py` with target aggregate (read-only annotation pass, no method moves).
2. **Helper extraction commit:** move shared helpers to `Core/Database/`, update existing callers.
3. **ActiveJobs aggregate commit:** smallest, narrowest caller set. Validates the pattern end-to-end before bigger moves.
4. **TranscodeAttempts aggregate commit.**
5. **MediaFiles aggregate commit.** Most complex (multi-path SaveMediaFile, archive sub-aggregate).
6. **TranscodeQueue absorb commit:** existing `Features/TranscodeQueue/TranscodeQueueRepository.py` absorbs the remaining queue methods.
7. **Remaining aggregates commit(s):** Workers, ProblemFiles, RootFolders, etc.
8. **Final cleanup commit:** delete `Repositories/DatabaseManager.py` (or reduce to deprecation shim), update CLAUDE.md, mark this feature COMPLETE.

Each commit independently reviewable. Each commit's test suite green before merge.

## Risk Register

- **Behavior drift during move:** even verbatim moves can introduce subtle bugs (whitespace in SQL, parameter order swap during cut-and-paste). Contract tests are the defense; don't skip writing one for an aggregate before moving it.
- **Connection lifetime regression:** new helper extraction may inadvertently move the connection management. Audit each new repo's connection-open/finally-close pattern; match the source exactly.
- **Hidden cross-aggregate queries:** some methods do JOINs that aren't obvious from the method name. Inventory pass should call these out before any move; service layer absorbs them.
- **Caller import update lag:** if a caller's update is missed, the test suite catches it -- but only if the test suite covers that caller. Run a full pytest before each commit, not just the moved aggregate's tests.
