# Fail Loud

Decision inputs (config reads, DB reads, function args) must never be silently substituted. Errors propagate; defaults do not paper over gaps. A caller with a `None` profile has a bug; giving it a `0` makes the bug invisible.

Prerequisite for C7 in `.claude/directive.md` (`transcode-flow-canonical`) -- the sweep step greps for these anti-patterns and refuses to ship until count is zero outside the whitelist.

## The four anti-patterns

1. **Bare `except:` / `except Exception:` without re-raise.** Swallows unknown failures. If you can't name the exceptions you handle, you're not handling them.
2. **`X or <default>` on a decision input.** `profile.AudioBitrate or 0` sends `0` to ffmpeg when the DB read returned `None`. Encoder runs with 0 kbps audio. File corrupted. Caller thinks it succeeded.
3. **`if X is None: X = <default>` on a decision input.** Same problem, spelled out.
4. **Silent `try/except` around a DB write.** Log-only handlers make the caller think the write succeeded. Either re-raise after logging, or don't catch.

## Scope

Production paths: `Features/`, `Workers/`, `WorkerService/`, `WebService/`, `Repositories/`, `Core/`. Test fixtures and explicit whitelist entries in `Tests/Contract/TestFailLoud.py` are exempt.

## Boundary sanitization is legal

Input edges (HTTP handler parsing request body, file parser reading disk) receive untrusted data. Catch there, log, and return a structured error response (`{'Success': False, 'Message': ...}`). That's not silent -- the error surfaces to the operator.

Rule of thumb: sanitize once, at the boundary. Internal code trusts. If internal code needs to guard, the wire shape upstream is wrong -- fix that instead.

## Verified conventions

- Contract test `Tests/Contract/TestFailLoud.py` greps for the four patterns in production paths; count == 0 outside the whitelist.
- Whitelist entries carry an inline `# fail-loud-ok: <reason>` marker within 3 lines. The test reads the marker and skips the line.
- API response format is `{'Success': True/False, 'Message': '...', 'Data': {...}}` (see `.claude/rules/error-ux.md`). Structured `Success=False` at boundaries is the only sanctioned "handled" outcome.

## When this rule applies (PR triggers)

- Adds `except:` or `except Exception:` to production code
- Adds `or 0` / `or ''` / `or None` / `or <literal>` to a value derived from a DB read, config read, or function arg
- Wraps a DB write in `try/except`
- Adds an `if X is None: X = ...` guard to a decision input

If your PR touches any of the above, run `py -m pytest Tests/Contract/TestFailLoud.py` and confirm the change either passes or adds a whitelist entry with a written reason.

## Cross-references

- `.claude/rules/db-is-authority.md` -- DB is SOT; silent defaults defeat that.
- `.claude/rules/error-ux.md` -- errors reach the user via structured API response, not silent success.
- `.claude/rules/data-integrity.md` -- data must never be silently lost or corrupted.

**Details, examples, common mistakes:** see `.claude/rules-details/fail-loud.md`.
