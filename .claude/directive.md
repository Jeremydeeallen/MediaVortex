# Current Directive

(none -- task-delegation mode active per `.claude/.task-delegation-on` marker)

Last closed: `mediaprobe-uses-path` (2026-06-04 -- Closed Success, Phase 7 pathfinder). Archived at `.claude/directives/closed/2026-06-04-mediaprobe-uses-path.md`. **Phase 7 pattern established.** MediaProbe now consumes paths via `Core.Path` (Path + Worker + PathError); zero `Core.PathStorage` references in the migrated vertical. `## Migration Pattern (Phase 7 caller verticals)` section in `Core/Path/path.feature.md` is the canonical recipe for the remaining 6 verticals.

**Next:** survey the remaining 6 verticals (FileScanning, FileReplacement, TranscodeJob, QualityTesting, TranscodeQueue, Activity) via parallel Explore agents, then batch-implement 3 at a time using worktree-isolated agents. Test count: 201 passed, 2 skipped.
