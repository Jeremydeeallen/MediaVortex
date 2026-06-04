# Current Directive

(none -- task-delegation mode active per `.claude/.task-delegation-on` marker)

Last closed: `path-db-roundtrip-live` (2026-06-04 -- Closed Success). Archived at `.claude/directives/closed/2026-06-04-path-db-roundtrip-live.md`. Phase 5 of `.claude/programs/path-track.md` complete -- 19 contract tests pass against live 10.0.0.15:5432 PostgreSQL across all 6 path-bearing tables; ~700 production rows audited with zero parse failures; UTF-8 byte-equal round-trip verified; `TemporaryFilePaths` dual-pair (Source / Output prefixes) verified. No `path.feature.md` amendments required; the existing contract holds end-to-end. Next in the program: `path-migration-rehearsal` (Phase 6 -- full-table walk + parse-failure rate report). Open with `/n path-migration-rehearsal` when ready.
