# Current Directive

(none -- task-delegation mode active per `.claude/.task-delegation-on` marker)

Last closed: `filescanning-uses-path` (2026-06-04 -- Closed Success, Phase 7 vertical 7 of 7 — **PHASE 7 COMPLETE**). Archived at `.claude/directives/closed/2026-06-04-filescanning-uses-path.md`.

**Phase 7 of `.claude/programs/path-track.md` is fully shipped.** All 7 vertical migrations complete: mediaprobe / activity / qualitytesting / filereplacement / transcodequeue / transcodejob / filescanning. Zero `Core.PathStorage` references in any of the 7 verticals. Every caller routes through `Core.Path` (Path + Worker + PathError) for canonical-path operations. Mid-directive audit also caught and fixed a real production bug (TranscodeJob's hardcoded Platform="windows" would break Linux workers) and three shape-purity gaps in previously-shipped verticals. 194 unit tests pass cumulatively across all 7 path-track phases (Path class + property + security + perf + db-roundtrip + migration-rehearsal + 7 Phase 7 verticals + this final FileScanning).

**Next in `path-track.md`:** Phase 8 `path-schema-migration` (drop legacy `FilePath` columns; idempotent migration; rollback documented), Phase 9 `path-v1-deprecation` (delete Core/PathStorage.py), Phase 10 `path-flawless-attestation` (final coverage + mutmut + 1M Hypothesis attestation). Phase 7 is fully unblocking for Phase 8.
