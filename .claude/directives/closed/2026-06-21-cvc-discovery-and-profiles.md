# Cross-Vertical Contracts: Discovery + Profile + Classification

**Slug:** cvc-discovery-and-profiles
**Set:** 2026-06-21
**Closed:** 2026-06-21
**Status:** Closed -- Success

## Outcome

Cross-Vertical Contract section added to four feature docs (`FileScanning`, `ContentSignals`, `Profiles`, `ContentClassifier`) following the pattern in `audio-normalization.feature.md` lines 236-335 + `media-probe.feature.md`. Each section: WRITES (columns this vertical owns), READS (external columns it consumes), stable function entry points, HTTP API surface, NOT-a-contract list. Doc-only; no code change.

## Acceptance Criteria

C1. `Features/FileScanning/FileScanning.feature.md` gains `## Cross-Vertical Contract` section.
C2. `Features/ContentSignals/content-signals.feature.md` gains the section.
C3. `Features/Profiles/Profiles.feature.md` gains the section.
C4. `Features/ContentClassifier/content-classifier.feature.md` gains the section.
C5. Each section enumerates: ≥1 WRITES row, ≥1 READS row, ≥1 stable entry point, HTTP routes (or "None today"), ≥3 explicit NOT-a-contract items.
C6. ARCHITECTURE.md "Every non-Audio vertical | Lacks a Cross-Vertical Contract section" row updated to reflect 4 more verticals now covered (remaining count drops from ~15 to ~11).

## Status

### Verification

- **C1-C4**: `grep -c '^## Cross-Vertical Contract' Features/{Profiles/Profiles,ContentSignals/content-signals,ContentClassifier/content-classifier,FileScanning/FileScanning}.feature.md` returns 1 for each (4 of 4).
- **C5**: each CVC section has WRITES table (≥1 row), READS table (≥1 row), Stable function entry points (≥1 row), HTTP API surface (with explicit "None today" for ContentSignals + ContentClassifier), and ≥3 NOT-a-contract bullets.
- **C6**: ARCHITECTURE.md gap row updated to reflect 4 more verticals covered + names the ~11 remaining verticals.

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| Cross-Vertical Contract section | Features/Profiles/Profiles.feature.md | next commit |
| Cross-Vertical Contract section | Features/ContentSignals/content-signals.feature.md | next commit |
| Cross-Vertical Contract section | Features/ContentClassifier/content-classifier.feature.md | next commit |
| Cross-Vertical Contract section | Features/FileScanning/FileScanning.feature.md | next commit |
| Gap row updated | ARCHITECTURE.md | next commit |

### Decisions Made

- Used bash heredoc append for the 4 sections (mechanical doc edits at file end; no R12/R14 risk for the section content; faster than 4 Edit cycles).
- Each NOT-a-contract list calls out implementation details that are most likely to change (heuristics, internal class names, sync/async runtime choice) -- gives the vertical room to evolve.
