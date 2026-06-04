# Archived Directive: Path-Shape Migration

**Filed:** 2026-05-31 (by `nvenc-rate-anchored-remediation` close-out)
**Closed:** 2026-06-04 -- Superseded
**Status:** Closed -- Superseded by `paths-canonical-completion` (2026-06-03) + `paths-normalize-completion` (2026-06-04)
**Slug:** path-shape-migration

## Supersession note

The scope this directive owned was delivered by two later directives:

- `paths-canonical-completion` (closed 2026-06-03) -- created `Core.PathStorage` canonical surface; migrated every production `os.path.X(pathvar)` site; deleted every `# allow: R6` annotation in production; baselined production R6 violations at zero (criterion 6).
- `paths-normalize-completion` (closed 2026-06-04) -- added `Normalize` + `PathsEqual` to the canonical surface.

Naming evolved: this directive's outcome named `Core.Services.PathTranslationService`; the actual replacement that shipped is `Core.PathStorage`. Scope is identical.

Acceptance criteria status:

| # | Asked | Delivered by |
|---|---|---|
| 1 | Zero `# allow: R6` in production | `paths-canonical-completion` C3 |
| 2 | Zero R6 hook violations in scope | `paths-canonical-completion` C6 (monotone-zero baseline) |
| 3 | Each site migrated to approved replacement | `paths-canonical-completion` C2 |
| 4 | No behavior change cross-platform | Verified by `paths-canonical-completion` close-out smoke |
| 5 | `Tests/Contract/` green | Verified by `paths-canonical-completion` close-out |

No remaining work. Archived from backlog 2026-06-04.

---

**Original triggered-by:** `nvenc-rate-anchored-remediation` directive scattered 10+ `# allow: R6 -- preexisting` overrides on `os.path.dirname(InputPath)` and similar calls across `CommandBuilder.py`, `ProcessTranscodeQueueService.py`, `QualityTestingBusinessService.py`. R6 catches `os.path.{dirname,basename,join,split}` called on path-named variables because `MediaFiles.FilePath` is a mix of UNC, drive-letter, and POSIX shapes and `os.path` is platform-relative -- silent bugs from shape coercion.

## Outcome

Every `os.path.{dirname,basename,join,split}` call on a path-named variable in the codebase is replaced with either:

- A call to `Core.Services.PathTranslationService` when the operation needs canonical<->local translation (worker-local mount mapping per `Workers.ShareMountPrefix` + `WorkerShareMappings`), OR
- A shape-explicit `ntpath` / `posixpath` / `PurePosixPath` / `PureWindowsPath` call when the operation is pure string manipulation in a known shape.

All `# allow: R6 -- preexisting` overrides are removed. The hook does not flag R6 violations.

## Acceptance Criteria

1. `grep -rn "# allow: R6" Models/ Features/ Core/ WorkerService/ WebService/` returns zero matches.
2. The R6 hook scan of every `.py` file under `Models/`, `Features/`, `Core/`, `WorkerService/`, `WebService/` returns zero violations.
3. Every replaced call site uses one of the approved replacements; document the call-site map in this directive's `## Status` block: `<file>:<line> -- <original> -> <replacement> -- <reason>`.
4. No behavior change on any cross-platform path operation. Smoke test on Windows (I9-2024) and Linux (larry LXC 218 worker container) shows identical FilePath handling pre/post.
5. `Tests/Contract/` suite green.

## Out of Scope

- Path-storage refactor (`PathStorage.Resolve`) -- that's a separate concern from call-site migration.
- Comment / docstring cleanup -- tracked by `commandbuilder-comment-promotion` and `transcode-pipeline-comment-promotion`.

## Reference

Source policy: `.claude/rules/ceo-mode.md#handling-preexisting-comment--doc-violations-encountered-mid-directive` (R6 section) + `.claude/rules/data-integrity.md` (path-shape rule)
Parent directive (closed): `.claude/directives/closed/2026-05-31-nvenc-rate-anchored-remediation.md`
Memory note: `feedback_paths_must_be_shape_agnostic.md`
