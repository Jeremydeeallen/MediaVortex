# MediaProbe + Activity Feature Docs

**Slug:** media-probe-and-activity-docs
**Set:** 2026-06-20
**Closed:** 2026-06-20
**Status:** Closed -- Success

## Outcome

Two top-level `*.feature.md` files created -- `Features/MediaProbe/media-probe.feature.md` (with full Cross-Vertical Contract) and `Features/Activity/activity.feature.md` (unifies the two sub-feature docs + flow doc). Two gap rows close from `ARCHITECTURE.md`. No code change.

## Acceptance Criteria

C1. `Features/MediaProbe/media-probe.feature.md` exists with required structure per `feature-docs.md`: Slug, What It Does, Workflows (W-IDs), Success Criteria (C-IDs), Seams (S-IDs), Status.
C2. MediaProbe Cross-Vertical Contract section parallels `audio-normalization.feature.md` lines 236-335 -- WRITES, READS, function entry points, HTTP routes, NOT-a-contract.
C3. `Features/Activity/activity.feature.md` exists with required structure.
C4. Activity feature doc references sub-feature docs + flow doc; does not duplicate their criteria.
C5. ARCHITECTURE.md Gap section's two rows for these docs REMOVED.
C6. All criteria in both new feature docs pass the five litmus tests (rename / outsider / rewrite / negation / stability).

## Status

### Verification

- **C1**: `ls Features/MediaProbe/media-probe.feature.md` confirms; `**Slug:** media-probe` in first 15 lines (R16); W1-W9, C1-C7, S1-S5, Status present.
- **C2**: Cross-Vertical Contract has 17-column WRITES, 3-source READS, 6 entry points, 9 HTTP routes, 6 NOT-a-contract items.
- **C3**: `ls Features/Activity/activity.feature.md` confirms; `**Slug:** activity` in first 15 lines (R16); W1-W8, C1-C7, S1-S4, Status present.
- **C4**: Activity doc C5 + C6 + "See also" defer to `active-jobs-filter-sort.feature.md`, `activity-dashboard-improvements.feature.md`, `activity-dashboard.flow.md` without restating their criteria/seams.
- **C5**: `grep 'MediaProbe.feature.md\|Activity.feature.md' ARCHITECTURE.md` returns no matches.
- **C6**: MediaProbe C1-C7 + Activity C1-C7 use observable behavior (column writes, return values, page render, endpoint shapes) without internal Python identifiers.

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| MediaProbe top-level feature doc + full Cross-Vertical Contract | `Features/MediaProbe/media-probe.feature.md` | TBD until close |
| Activity top-level feature doc unifying sub-features + flow | `Features/Activity/activity.feature.md` | TBD until close |
| Two gap rows removed | `ARCHITECTURE.md` | TBD until close |

### Decisions Made

- MediaProbe got the full Cross-Vertical Contract in THIS directive (not deferred to directives 8-10). Reason: MediaProbe's write surface is the most-read in the system; drafting the base doc + CVC in one pass avoided a second pass.
- Activity did NOT get a Cross-Vertical Contract in THIS directive. Reason: Activity is a UI consumer (almost-all-reads, near-zero writes); the CVC is mostly READS and lands in directive 10 (`cvc-surfaces-and-infrastructure`).
- Activity top-level feature doc OWNS only the page-level shape; it explicitly defers Active-Jobs-table behavior to `active-jobs-filter-sort.feature.md`, per-worker badge lifecycle to `activity-dashboard-improvements.feature.md`, and cross-stage seams to `activity-dashboard.flow.md`. Avoids duplicating content already documented.
