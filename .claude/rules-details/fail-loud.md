# Fail Loud -- Details, Examples, Common Mistakes

Companion to `.claude/rules/fail-loud.md`. The short rule is the invariant; this file is how-to.

## Why silent defaults are the enemy

The classic argument for defaults: "the code is robust; it keeps running." The counter: bugs upstream (missing schema field, misspelled column, forgotten migration) get masked. The system reports Success while writing garbage.

Concrete cases in this repo:

- `AudioPolicyResolved` = 0/1121 populated across every strategy (Signal 3 finding in `transcode-flow-canonical`). Somewhere a producer silently skipped writing it and the read side silently accepted `None`. A raise would have surfaced the missing wire on day one.
- BUG-0072 / BUG-0070 audio-bitrate damage. Missing config values coerced to `0`; encoder ran with 0-kbps audio; files corrupted. A raise stops the encode before the file lands.
- `BypassReplace` disposition = 88% of activity (Signal 3). Verify step failed and disposition fell through to `Bypass` because the failure was swallowed. A raise means the operator sees the failure; silent bypass ships broken files.

## The four anti-patterns, detailed

### 1. Bare `except`

```python
# BAD -- swallows every error including SyntaxError, MemoryError
try:
    result = ExpensiveOperation()
except:
    result = None
```

Fix: name the exceptions you actually handle. Everything else raises.

```python
try:
    result = ExpensiveOperation()
except (IOError, ValueError) as ex:
    LoggingService.LogException("...", ex, "Class", "Method")
    raise
```

### 2. Coalescing on decision inputs

```python
# BAD -- if AudioBitrate came back None from DB, ffmpeg gets 0
audio_bitrate = profile.AudioBitrate or 0
BuildFfmpegCommand(audio=audio_bitrate)
```

Fix: raise if the field is required.

```python
if profile.AudioBitrate is None:
    raise ValueError(f"AudioBitrate missing for profile {profile.Id}")
BuildFfmpegCommand(audio=profile.AudioBitrate)
```

### 3. None-substitution on decision inputs

Semantically identical to (2), spelled out.

```python
# BAD
if target_lufs is None:
    target_lufs = -14.0  # silently invents a target
```

### 4. Silent `try/except` on DB write

```python
# BAD
try:
    DatabaseService.ExecuteNonQuery("INSERT INTO TranscodeAttempts ...")
except Exception as ex:
    LoggingService.LogException("...", ex, "Class", "Method")
    # no re-raise -- caller thinks the write succeeded
```

Fix: log AND re-raise, or don't catch.

## Boundary sanitization is legal

At input edges (HTTP handler parsing request body, file parser reading disk), unknown data can be malformed. That's where you catch, log, and return a structured error response. The error surfaces to the operator -- that's the point.

```python
# LEGAL -- at API boundary
@app.route('/api/queue', methods=['POST'])
def AddToQueue():
    try:
        body = request.get_json()
        MediaFileId = int(body['MediaFileId'])
    except (KeyError, ValueError, TypeError) as ex:
        return jsonify({'Success': False, 'Message': f'Bad payload: {ex}'}), 400
```

## What to grep for

The contract test (`Tests/Contract/TestFailLoud.py`) runs these patterns against production paths:

| Pattern | Matches |
|---|---|
| `\bexcept\s*:` | bare except |
| `\bexcept\s+Exception\s*:` | except Exception (followed by block-level grep for `raise`) |
| `\bor\s+(0\|''\|""\|None\|\[\]\|\{\})\b` | coalescing on default literal |
| `if\s+\w+\s+is\s+None\s*:\s*\n?\s*\w+\s*=` | None-substitution guard |

Whitelist entries: an inline `# fail-loud-ok: <reason>` marker within 3 lines of the pattern. The test reads the marker and skips the line. Reason must be non-empty.

## The whitelist policy

Whitelist entries are for cases where the anti-pattern is genuinely correct:

- **Input boundary** (HTTP request parsing, file parsing) -- error mapped to structured `Success=False` response.
- **Schema-optional column** -- the DB column is nullable by design (rare; document why in the marker).
- **Empty-collection default** -- `results or []` when a downstream consumer requires a list and empty is semantically equivalent to no-results (still audit -- often the producer should just return `[]`).

"Make the test green" is not a whitelist reason. If the marker's `<reason>` doesn't name a specific structural claim, the entry is drift.

## Common mistakes

- **"Defensive coding" as a habit.** The habit is wrong for internal code. Boundaries validate; internal code trusts. If internal code needs to guard, the wire shape is wrong -- fix the wire shape.
- **Logging without re-raising.** Log AND raise; logging is telemetry, not error handling.
- **"But the tests still pass."** Tests pass because they exercise the golden path; the silent branch is untested. That's the bug.
- **Adding a whitelist entry to unblock a commit.** The whitelist is for structural exemptions, not schedule pressure. If you can't articulate why the anti-pattern is right in this case, fix the code instead.
- **Catching only to log the exception context.** Log via a decorator or the caller. Catching just to log adds no value and risks the silent-swallow drift when a maintainer later removes the raise.

## Cross-references

- `.claude/rules/fail-loud.md` -- the invariant.
- `.claude/rules/db-is-authority.md` -- DB is SOT; silent defaults contradict.
- `.claude/rules/error-ux.md` -- structured API responses (not exception text) at boundaries.
- `Tests/Contract/TestFailLoud.py` -- the contract test (created in reset step 11 per `transcode-flow-canonical` directive).
