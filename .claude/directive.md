# Current Directive

(none -- task-delegation mode active per `.claude/.task-delegation-on` marker)

Last closed: `path-data-cleanup` (2026-06-04 -- Closed Success). Archived at `.claude/directives/closed/2026-06-04-path-data-cleanup.md`. Two single-row UPDATEs reconciled the 2 actionable findings from Phase 6's audit: MediaFiles id=22899 (.mp4 vs .avi content drift) and id=687504 (mnt\media_tv\... malformed legacy FilePath). Re-audit: MediaFiles parse-failure 0%, current-data ContentDrift 0, NoPrefixMatch 0. MediaFilesArchive history retains 5 case-only- and content-drift snapshots (immutable, fixed-upstream). **Phase 7 caller migration is unblocked.** Next in `.claude/programs/path-track.md`: `<feature>-uses-path` block (Phase 7, 7 directives, one per vertical: FileScanning, MediaProbe, FileReplacement, TranscodeJob, QualityTesting, TranscodeQueue, Activity).
