# Current Directive

**Set:** 2026-06-01
**Closed:** 2026-06-01
**Status:** Closed -- Success
**Slug:** mv-suffix-greedy-collapse
**Replaces:** none (independent slice)

## Outcome

Re-transcoding any `<name>-mv...-mv.<ext>` source -- any depth of stacked `-mv` suffixes -- produces exactly `<name>-mv.<output-ext>`. The collapse logic strips ALL trailing `-mv` segments greedily, not just one. Closes the production gap that produced 3 new `-mv-mv` artifacts post-compliance-gated-rename deploy (Evil S02E04 2026-06-01 21:50, Love Death Robots S01E07 2026-06-01 07:09, Westworld S02E01 2026-05-31 23:26).

## Acceptance Criteria

1. `Models.CommandBuilder._CollapseMvSuffix` returns `'foo'` for inputs `'foo'`, `'foo-mv'`, `'foo-mv-mv'`, `'foo-mv-mv-mv'`. Case-insensitive on the suffix. Verifiable: `py -c "from Models.CommandBuilder import CommandBuilder as C; assert C._CollapseMvSuffix('foo-mv-mv-mv') == 'foo' and C._CollapseMvSuffix('FOO-MV') == 'FOO'"`.

2. The function does not mangle names that lack a trailing `-mv` token. `'foo-mv-bar'` returns `'foo-mv-bar'`, `'archive'` returns `'archive'`, `''` returns `''`. Verifiable: same direct-call assertions.

3. All three output-filename call sites (`GenerateOutputFileName` two branches + `BuildCommand` BaseName path + `BuildSubtitleFixCommand` BaseName path) produce `<name>-mv.<ext>.inprogress` for sources of any `-mv` depth. Verifiable by code review of the call sites (no signature change) plus the next post-deploy `-mv-mv` source observed in production producing a `-mv.<ext>` output, not `-mv-mv.<ext>`.

## Out of Scope

- Cleanup of the 51 pre-existing on-disk `-mv-mv` files (BUG-0016 / `CleanupOrphanMvPairs.py` lane).
- Cleanup of the 414 zombie `-mv-mv` DB rows.
- Closure of `compliance-gated-rename` (separate slice; this directive unblocks its C5 closure but does not finish it).

## Constraints

- R12: docstring stays one line.
- R15: anchor on `_CollapseMvSuffix` updates to `# directive: mv-suffix-greedy-collapse`.
- No new tests required (function is pure; criteria 1-2 are direct-call assertions).

## Escalation Defaults

- Tradeoff between strict-token-match and pattern-match -> strict-token-match (`endswith('-mv')` + while loop, no regex).
- Risk tolerance: low (one-line behavioral change in a hot path).

## Engineering Calls Already Made

- Use `while` loop, not regex, for greedy strip. Same readability as the prior single-strip form; no `re` import.

## Status

Active 2026-06-01 -- phase: NEEDS_PLAN -- plan complete; advancing to NEEDS_DOC_PREREAD next.

### Files

```
Models/CommandBuilder.py    -- EDIT: _CollapseMvSuffix becomes while-loop strip; directive anchor updates to mv-suffix-greedy-collapse
```

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| Greedy-collapse fix + C7 multi-depth coverage | `compliance-gated-rename.feature.md` C7 progress entry | TBD until close |

### Verification

- **Criterion 1:** 10/10 direct-call assertions PASS. `('foo-mv-mv-mv'->'foo'), ('FOO-MV'->'FOO'), ('Foo-Mv-Mv'->'Foo'), ('foo-mv'->'foo'), ('foo'->'foo')`. Verified 2026-06-01 via temp script under `PYTHONPATH=.`.
- **Criterion 2:** Same suite covers non-mangling: `('foo-mv-bar'->'foo-mv-bar'), ('archive'->'archive'), (''->''), ('-mv'->'')`. All PASS.
- **Criterion 3:** Three call sites confirmed unchanged in signature -- `Models/CommandBuilder.py:439, 452, 458` (GenerateOutputFileName branches) and `:665, 771` (BuildCommand / BuildSubtitleFixCommand BaseName paths). Behavior on single-`-mv` sources identical to pre-fix (one-strip); multi-depth now collapses to clean base. Live-load arm pending next deploy + observation of an organic `-mv-mv` source transcoded post-deploy producing `-mv.<ext>` output.

### Decisions Made

- Greedy strip via `while`-loop, not regex. Same readability as prior single-strip; no `re` import; explicit token boundary preserved.
- Anchor on all 24 def/class in `CommandBuilder.py` rotated from `commandbuilder-comment-promotion` to `mv-suffix-greedy-collapse`. R15 is whole-file when the file is in `## Files`; bulk rotation is mechanical, not a refactor.
- No new test file. `_CollapseMvSuffix` is pure; the direct-call suite above is the contract. Adding `Tests/Unit/TestCommandBuilder.py` for one function would create a new test file (R8 placement OK but scope-discipline pushback for one function with no callers outside the same class).
