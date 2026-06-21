# Cross-Vertical Contracts: Execution

**Slug:** cvc-execution
**Set:** 2026-06-21
**Closed:** 2026-06-21
**Status:** Closed -- Success

## Outcome

Cross-Vertical Contract sections appended to six execution-vertical feature docs: TranscodeQueue, CommandBuilder, TranscodeJob, QualityTesting, FileReplacement, FailureAccounting. Each follows the audio-normalization pattern. Doc-only; no code change.

## Acceptance Criteria

C1-C6. Each of the six feature docs gains a `## Cross-Vertical Contract` section with WRITES + READS + stable entry points + HTTP routes + NOT-a-contract bullets.
C7. ARCHITECTURE.md Gap row updated -- 6 more verticals removed from "lacks CVC."

## Status

### Verification

- **C1-C6**: `grep -c '^## Cross-Vertical Contract'` returns 1 for each of TranscodeQueue, CommandBuilder, TranscodeJob, QualityTesting, FileReplacement, FailureAccounting feature docs.
- **C7**: ARCHITECTURE.md Gap row updated to list the remaining ~9 verticals (operator surfaces + infrastructure).

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| CVC | Features/TranscodeQueue/TranscodeQueue.feature.md | next commit |
| CVC | Features/CommandBuilder/command-builder.feature.md | next commit |
| CVC | Features/TranscodeJob/TranscodeJob.feature.md | next commit |
| CVC | Features/QualityTesting/QualityTesting.feature.md | next commit |
| CVC | Features/FileReplacement/FileReplacement.feature.md | next commit |
| CVC | Features/FailureAccounting/failure-accounting.feature.md | next commit |
| Gap row updated | ARCHITECTURE.md | next commit |

### Decisions Made

- Each CVC kept tight: WRITES/READS/Entry points/HTTP/NOT-a-contract. ~30 lines each. Detailed criteria stay in the feature doc body.
- Used bash heredocs one-per-file (multiple heredocs in one Bash call had parsing issues with embedded quotes). Tradeoff: 6 turns instead of 1; reliability over speed.
