# Directive: file-bug-0095-failure-class-taxonomy

**Status:** Closed

**Slug:** file-bug-0095-failure-class-taxonomy

## Outcome

Record BUG-0095 as follow-up to BUG-0061 -- failure-class taxonomy so `/FailedJobs` shows operator-actionable remediation ("Grab new source" / "Delete orphan -mv.mp4" / "Wait for BUG-0093") instead of raw ffmpeg stderr. Capture only; fix ships later.

## Motivation

Operator asked for a KISS taxonomy after 15 stuck files revealed 4 distinct failure classes needing 4 different remediations. Reading raw stderr per file does not scale.

## Acceptance Criteria

C1. `memory/BUG-INDEX.md` gains one active row: `BUG-0095 | active | failure-accounting | ...`.
C2. `memory/KNOWN-ISSUES.md` gains one `### failure-accounting` subsection with a `[BUG-0095]` entry containing Repro / Evidence / First-place-to-look.
C3. `Features/FailureAccounting/failure-accounting.feature.md` gains one new success criterion tagged `[BUG-0095]` describing the taxonomy contract.

## Files

**Edit:**
- `memory/BUG-INDEX.md`
- `memory/KNOWN-ISSUES.md`
- `Features/FailureAccounting/failure-accounting.feature.md`

### Progress

- [x] NEEDS_STANDARDS_REVIEW: rules auto-loaded; standards index already Read this session
- [x] NEEDS_PLAN: criteria + Files above
- [x] NEEDS_DOC_PREREAD: `failure-accounting.feature.md` Read this session
- [ ] IMPLEMENTING: write 3 edits
- [ ] VERIFYING: grep asserts for row presence
- [ ] DELIVERING: report BUG-0095 to operator; close

### Promotions

- Directive C1 -> `memory/BUG-INDEX.md` (BUG-0095 active row).
- Directive C2 -> `memory/KNOWN-ISSUES.md` `### failure-accounting` new subsection with BUG-0095 entry.
- Directive C3 -> `Features/FailureAccounting/failure-accounting.feature.md` C10 (`[BUG-0095]` criterion for FailureClass column + FailureClasses table + classifier + /FailedJobs grouping + /settings tuner).

### Delivery Report

- DIRECTIVE: File BUG-0095 (failure-class taxonomy) as follow-up to BUG-0061.
- STATUS: Done.
- WHAT SHIPPED: BUG-0095 recorded in BUG-INDEX + KNOWN-ISSUES + failure-accounting.feature.md C10.
- HOW TO USE IT: `/t BUG-0095` when BUG-0061 lands.
- CRITERIA VERIFICATION: `grep -c BUG-0095` in the 3 files returns 1/3/1 -- all present.
