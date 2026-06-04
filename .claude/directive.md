# Current Directive

(none -- task-delegation mode active per `.claude/.task-delegation-on` marker)

Last closed: `path-migration-rehearsal` (2026-06-04 -- Closed Success). Archived at `.claude/directives/closed/2026-06-04-path-migration-rehearsal.md`. Phase 6 of `.claude/programs/path-track.md` complete -- 101,355 rows audited in 1.66s; parse-failure rate 0.0010% (target < 0.1%, 100x under); 49 case-only drift (informational, expected per D2/D10); **6 content-drift rows surfaced as real anomaly** (legacy and typed pair point to different files); 1 no-prefix-match row needs operator review. Report committed at repo root as `path-migration-rehearsal-report-2026-06-04.md` for Phase 8 reference.

**Operator decision recommended before Phase 7:** open follow-up `path-content-drift-remediation` to reconcile the 6 content-drift rows + manually fix MediaFiles id=687504. Phase 7 caller migration is otherwise unblocked. Next program phase: `<feature>-uses-path` (Phase 7, the caller migration block -- 7 directives, one per vertical).
