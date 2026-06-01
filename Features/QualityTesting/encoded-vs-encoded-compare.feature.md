# Feature: Encoded-vs-Encoded Slider Comparison

**Slug:** encoded-vs-encoded-compare

## What It Does

Extends the `/VmafCompare` slider so the operator can compare two different
encoded variants of the same source against each other, not just each against
the source. The default behavior (source-vs-encoded) is preserved; this adds
an alternate mode where the slider shows variant A on one side and variant B
on the other.

Use case: when the FG sweep test produces variants at FG=0, FG=4, FG=8, FG=12
all scoring around the same VMAF, the operator wants to see "does FG=4 look
better than FG=8 subjectively?" -- a question that source-vs-encoded
comparisons cannot answer. Same for CRF sweeps and any other variant
dimension.

The source-vs-encoded comparison stays the default because that is the
"is this transcode acceptable" question. Encoded-vs-encoded is the "which
of these is better" question -- a different decision that needs the same
slider UI but a different left-side image.

## Surface

- **Entry point**: existing `/VmafCompare` page when a variant group is open
  (Test bench mode OR Recent attempts test-mode group).
- **UI addition**: a "Compare against:" selector in the slider header next to
  the existing TV-fair / Native pixels toggle. Options:
  - `Source (default)` -- existing behavior, left side = source still
  - `<other variant label>` -- one option per other variant in the active
    group, e.g. `1080p CRF28 FG4`, `1080p CRF28 FG8`
- When a non-default option is picked, the left-side `<img>` swaps to that
  variant's transcoded still at the current timestamp. The right-side stays
  on the currently-active variant. The slider divider behavior is unchanged.
- An indicator (badge or label below the slider) makes the current
  left-vs-right pairing explicit: e.g. `1080p CRF28 FG4 vs 1080p CRF28 FG8 @ 5:00`.
- **No new backend endpoints**: the comparison stills are already cached
  per-variant per-timestamp by the existing CompareStillsBatch endpoint.
  Switching the left side just points the existing `<img>` to a different
  cached PNG.

## Flow (operator's path)

| Step | What the operator does | What the system does | Failure mode |
|---|---|---|---|
| 1 | Opens a test-mode group from Recent attempts OR a sidecar from Test bench | Existing flow: variant pills render | -- |
| 2 | Clicks a variant pill (e.g. variant B, FG=4) | Slider loads source-vs-B at the configured timestamps; thumbnail strip renders | -- |
| 3 | In slider header, changes "Compare against:" from `Source` to `1080p CRF28 FG8` (variant C) | Left-side `<img>` swaps to variant C's transcoded still at the current timestamp; right side stays on variant B; indicator below slider updates | If variant C's still has not been extracted for the current timestamp + view mode, system fetches it via the existing single-pair endpoint (small delay) |
| 4 | Drags the slider divider | Standard slider behavior reveals one or the other | -- |
| 5 | Clicks a different timestamp in the thumbnail strip | Both left and right swap to the new timestamp's cached stills for the same pairing | -- |
| 6 | Changes "Compare against:" back to `Source (default)` | Left-side `<img>` returns to source's still at the current timestamp | -- |

## Success Criteria

1. **Selector renders for groups only.** "Compare against:" selector appears in the slider header when the active view is a multi-variant group (Test bench sidecar with >= 2 variants OR Recent attempts test-mode group with >= 2 attempts). When the active view is a single attempt (no peer variants), the selector is hidden. Verifiable: open a single production attempt, no selector; open the 4K test set with 3 variants, selector appears with 2 non-default options.

2. **Default is Source.** Selector defaults to `Source (default)`, slider behavior is unchanged from current. Verifiable: open any variant; before touching the selector, the slider shows source on the left and the active variant on the right.

3. **Switching to a peer variant swaps the left image only.** Picking a non-default option swaps the left-side `<img>.src` to the chosen peer variant's transcoded PNG (cached). The right side is unchanged. Verifiable: open variant B, switch left to variant C; ImgSource.src points at variant C's transcoded PNG; ImgTranscoded.src is unchanged at variant B.

4. **Pairing indicator shows current sides.** A small badge/label below the slider names both sides explicitly: e.g. `Left: 1080p CRF28 FG4   Right: 1080p CRF28 FG8 @ 5:00`. Verifiable: peer comparison shows both variant labels; source comparison shows `Left: Source   Right: 1080p CRF28 FG4`.

5. **Timestamp switching preserves pairing.** Clicking a thumbnail in the strip updates BOTH sides to the new timestamp while keeping the same pairing (peer-vs-peer OR source-vs-peer). Verifiable: switch pairing to variant C, click the 10-minute thumbnail; both left and right update to 10-minute stills for variant C and variant B.

6. **View mode change preserves pairing.** Toggling TV-fair / Native pixels re-fetches with the new view but keeps the same pairing. Verifiable: switch pairing to peer C, toggle to Native pixels; both sides re-render at native dimensions, still showing variant C on left and variant B on right.

7. **No new on-disk cache entries.** Peer comparison uses the existing per-variant per-timestamp per-view PNGs. No new PNG file is written by virtue of switching the selector. Verifiable: count PNGs in `cache/vmaf-compare/` before and after switching pairing; counts are equal.

8. **Source pairing always available.** `Source (default)` is always selectable regardless of which peer is currently on the right side. Switching back to Source restores the left-side `<img>` to the source's cached still at the current timestamp. Verifiable: rotate through Source -> peer C -> peer D -> Source; final state matches initial.

9. **Smoke-test variants and production variants both supported.** The selector works equivalently for Test bench groups (sidecar variants, raw paths) and Recent attempts test-mode groups (DB-backed TranscodeAttempt rows). Verifiable: complete the criteria above against both surfaces.

10. **No effect when feature is off.** This feature ships always-on in v1 (no toggle). If a future config setting wants to disable it, the criterion is that the selector disappears and the default source-vs-encoded behavior remains identical. Verifiable: present-day default state (selector on Source) is byte-identical to pre-feature behavior.

## Status

**NOT STARTED** -- doc-first, awaiting operator approval of criteria.

### Progress

- [x] Draft this feature doc with criteria
- [ ] Operator approval
- [ ] **Active-group state**: when LoadBatch resolves for a variant from a group (attempt-driven or sidecar-driven), capture the list of peer variants (their cached transcoded URLs + labels) in a JS variable so the selector knows what options to render
- [ ] **Selector UI**: add `<select id="CompareAgainst">` to the slider header next to the view-mode toggle; populated from peer-variants list whenever a group is loaded; first option is always `Source (default)`
- [ ] **Pairing indicator**: small badge/label below the slider (or repurpose `MetaLine`) showing `Left: X   Right: Y @ <timestamp>`
- [ ] **Swap-left-only behavior**: change handler reads selector value; if `source` (default), restores `ImgSource.src` to the source still URL; else fetches/uses the peer variant's transcoded URL and sets `ImgSource.src` to it
- [ ] **Peer-variant cache helper**: for each peer variant, ensure CompareStills (singular) has been called for the current `(ts, view_mode)` so the PNG is available; if not yet cached, do an inline fetch before swapping `ImgSource.src`
- [ ] **Wire across surfaces**: confirm the selector works for both attempt-grouped (production test-mode rows) and sidecar-grouped (smoke tests) flows
- [ ] **Smoke test**: open the 4K FG sweep group, rotate through Source / peer A / peer B / peer C; verify indicator updates; verify thumbnail strip switching preserves pairing; verify view-mode toggle preserves pairing

## Scope

```
Templates/VmafCompare.html                 -- selector UI, pairing indicator, swap handler
```

No backend changes. CompareStills and CompareStillsBatch endpoints already produce the per-variant per-timestamp per-view cached PNGs needed.

## Files

| File | Role |
|---|---|
| `Templates/VmafCompare.html` | Selector + indicator + swap handler additions |
| `Features/QualityTesting/encoded-vs-encoded-compare.feature.md` | This doc |

## Out of Scope (deferred)

- **3-way view (source + peer A + peer B simultaneously)**: not feasible with `<img-comparison-slider>` which is 2-way by design. A future feature could add a separate 3-pane view.
- **Cross-source comparison**: comparing variant A from source X against variant A from source Y. Different conceptual question (cross-source quality trend, not within-source variant choice); separate feature when needed.
- **Annotation / labelling**: marking a peer-vs-peer comparison as "B preferred over A" persistently in the DB for trending. Not in this feature's scope.

## Deviation from conventions

None. Each criterion is observable from outside the codebase (DOM inspection + cache directory inspection) and traceable to specific slider behavior.
