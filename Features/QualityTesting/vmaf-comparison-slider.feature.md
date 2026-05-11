# Feature: VMAF Comparison Slider (operator visual A/B viewer)

## What It Does

Gives the operator an in-UI way to visually compare source vs transcoded
files for any TranscodeAttempt without leaving MediaVortex. Pulls a still
from each file at a chosen timestamp, scales them to the same display
resolution, and renders them in a draggable-slider control where the
operator can sweep left/right to reveal one or the other. Pairs with the
VMAF distribution metrics that landed in commit `0d80702` -- low-P10 or
low-HarmonicMean attempts become "worth eyeballing manually," and this
gives the operator a one-click path to do it.

Tonight's manual workflow (FFmpeg extraction commands + side-by-side PNG
inspection) becomes a single page operators can bookmark.

## Surface

- **Entry points:**
  - Standalone page at `/VmafCompare?attempt=<id>&ts=<seconds>` (v1, bookmarkable)
  - Optional "Compare" button on each `QualityTestingQueue` row (v2 polish, deferred)
- **Inputs:** TranscodeAttemptId (required), timestamp in seconds (optional, default 60).
- **Output:** single rendered page with a draggable slider, both stills aligned at the same display resolution, scrubbable timestamp.
- **Errors visible to operator:** missing source file, missing transcoded file, invalid TranscodeAttemptId, FFmpeg extraction failure -- each with a clear human-readable message and no JavaScript stack traces.

## Flow (operator's path)

| Step | What the operator does | What the system does | Failure mode |
|---|---|---|---|
| 1 | Navigates to `/VmafCompare?attempt=4396` | Loads page, defaults to `ts=60` | Invalid attempt id -> 404 with reason |
| 2 | Page renders | Backend resolves source + transcoded paths from `TemporaryFilePaths` or `MediaFiles` + post-replacement `TranscodeAttempts.FileReplaced` data, extracts both stills via FFmpeg at the requested timestamp, scales smaller-res to larger-res with lanczos | One or both files missing on disk -> page renders error placeholder; FFmpeg failure -> retry button + log link |
| 3 | Sees the source on one side, transcoded on the other, draggable slider in the middle | Slider control fades between the two as the operator drags | none -- pure client-side once stills are loaded |
| 4 | Types or scrubs to a new timestamp, clicks "Apply" or hits Enter | Backend extracts both stills at the new timestamp (cached after first extraction; subsequent requests for same `(attempt, ts)` skip FFmpeg) | Out-of-bounds timestamp -> bounded to file duration with a small warning |
| 5 | (v2) Clicks "Worst VMAF" | Backend reads `QualityTestResults.VMAFP5` for this attempt, picks a representative timestamp from the worst-frame band, navigates there | No VMAF data yet -> button disabled with tooltip "VMAF not run yet" |

## Success Criteria

1. **Standalone entry.** Operator can navigate to `/VmafCompare?attempt=<id>` and see a working comparison view without any prior session state. Verifiable: hit the URL fresh in an incognito browser, page renders source vs transcoded for the specified attempt, slider drags smoothly.

2. **Both stills at the same display resolution.** The smaller-resolution side is upscaled to the larger side's height with lanczos before display. Verifiable: render comparison for a 720p-transcode attempt where source is 1080p; both rendered images are 1920x1080 pixel size in the page DOM.

3. **Slider reveals smoothly.** Dragging the divider updates the visible portion in real time (no perceptible lag, no full-image reload). Verifiable: drag the slider end-to-end; visual update is continuous (no flicker, no flash of white).

4. **Timestamp navigation.** Operator can change the timestamp via input field or URL parameter. After change, both stills update to the new timestamp without a full page refresh. Verifiable: change `ts=60` to `ts=300` via the input field; both images visibly refresh; URL updates to reflect the new ts (for bookmarkability).

5. **Caching.** Repeated requests for the same `(attempt, timestamp)` pair use cached stills. Verifiable: open the same URL twice; second open returns in < 500 ms (vs. multi-second initial extraction); FFmpeg is not re-invoked for the cached pair.

6. **Missing-file error handling.** If the source or the transcoded file is missing on disk, the page renders a clear error message naming which file is missing, with no JavaScript error in the console. Verifiable: rename the transcoded file before opening the URL; page shows "Transcoded file not found: <path>" with no infinite spinner.

7. **No leakage between attempts.** Stills cached for `attempt=A, ts=60` are not served for `attempt=B, ts=60`. Verifiable: open both URLs sequentially; each shows the correct file pair.

8. **Path translation works on Linux workers.** When run on a worker that needs `T:\... -> /mnt/media_tv/...` translation, the backend resolves both source and transcoded paths to local mounts before FFmpeg invocation. Verifiable: deploy to larry, open a URL for a `T:\`-canonical attempt; page renders successfully.

9. **Stills are cleaned up on a schedule.** A cleanup job removes cached stills older than N days (default 7) so the cache directory doesn't grow indefinitely. Verifiable: cached PNGs in the staging dir older than the threshold are deleted on the next cleanup pass.

10. **(Deferred to v2) Worst-VMAF jump.** When `QualityTestResults.VMAFP5` is populated for the attempt, a "Worst frames" button appears that navigates to a timestamp in the bottom-5% band. Verifiable: an attempt with P5=15 shows the button; clicking it changes timestamp to one of the low-scoring frames; the slider re-renders.

11. **Auto-capture policy is configurable.** A `SystemSettings` row keyed `VmafStillCapturePolicy` controls whether comparison stills are pre-generated when a VMAF test completes. Permitted values: `All`, `UncharacterizedProfiles`, `Off`. Default value on first install is `All`. Two companion settings tune the policy: `VmafStillCaptureTimestamps` (default `60,300,600,900` seconds, comma-separated) and `VmafStillCaptureMinSamples` (default `10`, used only by `UncharacterizedProfiles`). Verifiable: query SystemSettings for these three keys after the install/migration script runs; all three rows exist with the stated defaults and human-readable Descriptions.

12. **`All` policy captures every test.** When `VmafStillCapturePolicy=All`, every successful VMAF test completion triggers comparison-still generation at the configured timestamp set, clamped to the file's duration. Verifiable: with policy=All and timestamps=`60,300,600,900`, complete one VMAF test on a 30-min file; the cache directory contains 8 PNGs for that TranscodeAttemptId (4 timestamps × source + transcoded). Complete one VMAF test on a 5-min file; the cache contains 4 PNGs (timestamps beyond duration are skipped).

13. **`UncharacterizedProfiles` policy captures only for unfamiliar combos.** When `VmafStillCapturePolicy=UncharacterizedProfiles`, auto-capture fires only when the `(ProfileName, source ResolutionCategory)` combination has fewer than `VmafStillCaptureMinSamples` prior completed VMAF tests in `TranscodeAttempts` / `QualityTestResults`. Verifiable: set policy=UncharacterizedProfiles with MinSamples=10; run one VMAF test for a profile+resolution that has 0 prior samples → stills generated; run one VMAF test for a profile+resolution that has 20 prior samples → no stills generated.

14. **`Off` policy disables auto-capture but preserves the lazy path.** When `VmafStillCapturePolicy=Off`, no stills are auto-generated on VMAF completion. The on-demand lazy path from criterion 5 continues to work — opening `/VmafCompare?attempt=<id>` still extracts stills on first request. Verifiable: set policy=Off, complete a VMAF test, confirm cache is empty for that attempt; then open the compare URL, confirm stills appear after first request.

15. **VMAF-disabled implies no auto-capture (no separate gate).** If a worker has `QualityTestEnabled=false` or the attempt's VMAF computation fails, no auto-capture runs — there is nothing to compare against. The capture decision lives strictly after a successful VMAF score is persisted. Verifiable: set a worker QualityTestEnabled=false, transcode a file through it, observe no VMAF row and no stills regardless of policy value.

16. **Multi-timestamp thumbnail strip.** When a variant is opened (production attempt or test-bench variant), the page shows a thumbnail strip with 3-5 stills pulled from the configured `VmafStillCaptureTimestamps` set (default 60, 300, 600, 900 — clamped to file duration). The first thumbnail is active on open; clicking another thumbnail switches the slider to that timestamp without a page reload. The thumbnails reuse the cached transcoded PNGs (no separate small-thumbnail generation). Verifiable: open any variant on a file longer than 15 minutes; the strip shows 4 thumbnails labeled with their timestamps; clicking each updates the slider source+transcoded pair to the matching cached pair.

17. **TV-fair display normalization.** Comparison stills are extracted with a common display resolution applied symmetrically to source and transcoded streams: `scale=1920:1080:flags=lanczos,unsharp=5:5:0.5`. This approximates a generic TV upscaler so a 480p variant and a 1080p variant are compared on visually equal ground rather than being CSS-stretched by the browser. A "Native pixels" toggle bypasses normalization and extracts at native dimensions; the cache key includes view mode so toggling is instant after first use. The unsharp filter applies to both source and encoded so the comparison stays symmetric. Verifiable: open a 480p variant in default view; both images are 1920x1080 in the DOM; toggle Native pixels; both images render at the native scaled output dimensions; toggle back, no re-extraction (cache hit).

## Status

**NOT IMPLEMENTED** -- doc-first, awaiting operator approval of criteria.

### Progress

- [x] 1. Read existing UI patterns (`Activity.html`, `Queue.html`) -- both are Bootstrap 5 + jQuery + Flask Jinja2 templates. New page should match.
- [x] 2. Decide on slider library: `img-comparison-slider` web component (no framework dep, drops in via single `<script>` tag, 4KB gzipped). Alternative is ~30 lines of vanilla CSS/JS using `clip-path`; library wins on polish and accessibility for ~zero cost.
- [x] 3. Draft this feature doc with 10 success criteria
- [ ] 4. Operator approval of criteria
- [ ] 5. **Backend endpoint** `GET /api/QualityTest/CompareStills?attempt=<id>&ts=<seconds>` (~60 LOC):
  - Resolve source + transcoded canonical paths from `TemporaryFilePaths` (if attempt is unfinished/Pending), else from `TranscodeAttempts` (if final), else from `MediaFiles` (after replacement)
  - Apply `WorkerContext.PathTranslation` to get local paths
  - Generate two stills via FFmpeg at the timestamp (the same recipe I've been using tonight: `-ss <ts> -i <file> -frames:v 1 -y <out.png>`)
  - Cache stills by content hash + timestamp in a known dir (e.g., `WorkerContext.StagingDirectory/vmaf-compare-cache/` or just a system temp); return URLs
  - Errors -> structured JSON `{Success: false, ErrorMessage: '...'}` (matches existing API shape)
- [ ] 6. **Backend route** `GET /VmafCompare` (~30 LOC Jinja2 template + Flask handler):
  - Reads `attempt` + `ts` from query string
  - Renders a template that loads `img-comparison-slider` and the two still URLs from the API call above
  - Includes the timestamp input, "Apply" button, and bookmark-aware URL updating via `history.pushState`
- [ ] 7. **Frontend template** `Templates/VmafCompare.html` (~120 LOC HTML/JS):
  - Bootstrap 5 layout (matches /Activity, /Queue)
  - `<img-comparison-slider>` component with two `<img>` slots
  - Timestamp input (number, seconds) + Apply button
  - Quick-pick buttons for representative timestamps (1m, 5m, 10m, 15m)
  - Loading spinner during extraction
  - Error placeholder with retry
- [ ] 8. **Path translation review**: ensure the still-extraction endpoint correctly translates `T:\` paths to local mounts on Linux workers (the same WorkerContext mechanism the rest of the pipeline uses)
- [ ] 9. **Cache cleanup**: small cron-style helper in `Scripts/Maintenance/CleanCompareCache.py` (~30 LOC) that removes stills older than N days. Can run from the existing maintenance loop or be a manual operator script.
- [ ] 10. **Smoke test**: open the URL for the Steven Universe S05E14 attempt (4396 or 4397), verify slider works on both i9 (Windows native paths) and larry (Linux mount paths)
- [ ] 11. **(Deferred to v2)** "Worst frames" button: read `QualityTestResults.VMAFP5` from the attempt, find a low-scoring timestamp band, expose as a button on the page
- [ ] 12. **Auto-capture migration** (`Scripts/SQLScripts/AddVmafStillCapturePolicy.py`): insert the three SystemSettings rows (`VmafStillCapturePolicy=All`, `VmafStillCaptureTimestamps=60,300,600,900`, `VmafStillCaptureMinSamples=10`) idempotently
- [ ] 13. **Auto-capture hook** in `QualityTestingBusinessService` after VMAF metrics persist and before disposition decision: read policy fresh from SystemSettings (no caching per memory rule), evaluate against attempt + ProfileName + source ResolutionCategory, call new method `AutoCaptureStillsForAttempt(TranscodeAttemptId)` if policy fires
- [ ] 14. **Sample-count query** for `UncharacterizedProfiles`: `SELECT COUNT(*) FROM TranscodeAttempts ta JOIN QualityTestResults qtr ON qtr.TranscodeAttemptId=ta.Id JOIN MediaFiles mf ON ta.MediaFileId=mf.Id WHERE ta.ProfileName=? AND mf.ResolutionCategory=? AND qtr.VMAFMean IS NOT NULL`
- [ ] 15. **Smoke test**: with policy=All, complete a VMAF test; verify 8 PNG files appear in cache. Toggle policy=Off; complete another; verify no PNGs. Toggle policy=UncharacterizedProfiles; run one test for an unfamiliar combo and one for a familiar combo; verify the unfamiliar one captures and the familiar one does not
- [ ] 16. **Batch-stills backend** `GET /api/QualityTest/CompareStillsBatch?attempt=<id>&view=tv_fair` (or with `source_path` + `transcoded_path` + `view`): reads `VmafStillCaptureTimestamps` from SystemSettings, extracts/caches one pair per timestamp, returns list of `{ts, SourceUrl, TranscodedUrl}`
- [ ] 17. **View-mode parameter** on the stills extraction path: `_ExtractStillPair(..., ViewMode='tv_fair')` chooses filter chain (`scale=1920:1080:flags=lanczos,unsharp=5:5:0.5` for tv_fair, no filter for native). Cache key includes ViewMode so toggling is instant after first use
- [ ] 18. **Thumbnail strip UI** in `VmafCompare.html`: on variant open, call CompareStillsBatch; render a row of thumbnails (transcoded image, click handler swaps the active pair into the slider); first thumbnail active by default; "Native pixels" toggle re-calls CompareStillsBatch with view=native

## Scope

```
WebService/                                  -- new route registered here
Features/QualityTesting/                     -- API endpoint lives in QualityTestController
Templates/VmafCompare.html                   -- new template
Scripts/Maintenance/CleanCompareCache.py     -- new cleanup script
```

## Files

| File | Role |
|---|---|
| `Features/QualityTesting/QualityTestController.py` | Adds `GET /api/QualityTest/CompareStills` endpoint and `GET /VmafCompare` route |
| `Features/QualityTesting/QualityTestingBusinessService.py` | Adds `GenerateComparisonStills(AttemptId, Timestamp)` method (reads paths, runs FFmpeg, caches) |
| `Templates/VmafCompare.html` | New Bootstrap + `img-comparison-slider` page |
| `Scripts/Maintenance/CleanCompareCache.py` | Stills cache cleanup script |
| `Features/QualityTesting/vmaf-comparison-slider.feature.md` | This doc |

## How much work is it? (concrete estimate)

**v1 MVP (criteria 1-9):** ~6-8 hours of focused work.

| Slice | LOC | Hours |
|---|---|---|
| Backend endpoint + still generator (criterion 1, 2, 5, 8) | ~80 | 2-3 |
| Frontend template + slider integration (criteria 1, 3, 4, 6) | ~120 | 2 |
| Cache directory + cleanup script (criterion 9) | ~50 | 1 |
| Path translation edge cases (criterion 8) | ~20 | 0.5 |
| Smoke testing on i9 + larry (criterion 10) | -- | 1 |
| Doc updates, integration into existing surfaces | -- | 0.5 |

**v2 polish (criterion 10 + "Compare" button on `/Queue` Quality Testing Queue card):** ~2-3 more hours.

Most of the work is sequential not parallel -- one focused session for v1 lands the entire feature including the operator smoke test. Less than tonight's post-disposition disposition cleanup, more than a single bug fix.

## Deviation from conventions

None. Each criterion is observable from outside the codebase (URL probe + page inspection + DB query) and traceable to a specific operator-visible behavior. No criterion references internal symbols by name.
