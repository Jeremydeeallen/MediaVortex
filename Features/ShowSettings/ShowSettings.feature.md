# Media Page Feature

**Slug:** showsettings

## Purpose

The Media page (`/ShowSettings`) lets users browse all discovered media (shows, movies, etc.) and queue titles for transcoding. Three distinct tables serve three workflows: (1) batch processing the largest files, (2) searching and queuing specific titles, and (3) browsing the full media library.

## Page Layout

```
[Header: "Media" (h2) + subnav]

[Card 1: Next Batch -- bg-primary, auto-populates T: drive on page load]
  [Header: "Next Batch" badge(count) description | Profile dropdown | Add Batch | Re-Analyze]
  [Table: remove btn, title, file, size, codec, bitrate, resolution]
  [Footer: batch total size]

[Card 2: Title Search -- bg-success]
  [Header: "Title Search" | Drive dropdown | Search input | Profile dropdown | Queue Selected | count]
  [Table: checkbox, title, files, size(GB), source res, codec, done, queue action(+)]

[Card 3: Media Library -- bg-dark]
  [Header: "Media Library" badge(count) | total GB | transcoded stats]
  [Table: title, files, size(GB), source res, codec, done -- sortable columns]
```

## Data Model

- `ShowSettings` table: `Id`, `ShowFolder` (UNIQUE), `TargetResolution`, `CreatedDate`, `LastModifiedDate`, `AssignedProfile`
- `TargetResolution` values: `480p`, `720p`, `1080p`, `2160p`, or empty string (defer to profile)
- Titles are derived from `MediaFiles` table by grouping on folder path
- **No global default row.** The `ShowFolder='*'` row was removed (and the cascade that consulted it deleted) on 2026-05-10 -- profiles already encode the default behavior via `ProfileThresholds.TranscodeDownTo`. ShowSettings now only carries explicit per-show overrides.
- **Note:** TargetResolution is maintained in the backend but not exposed in the UI. Profile selection (which includes per-resolution TranscodeDownTo thresholds) is the sole user-facing control for transcode targeting.

## Success Criteria

1. **ShowSettings only overrides when a per-show row exists.** When a file's show folder has no row in `ShowSettings`, the worker MUST use the profile's `TranscodeDownTo` value as the target resolution. There is no global default row; profiles drive default behavior. Verifiable: assign a profile with `TranscodeDownTo='720p'` for 1080p sources to a file whose show has no `ShowSettings` row, populate the queue, observe the FFmpeg command in `TranscodeAttempts.FFpmpegCommand` contains `scale=1280:720`. Regression check: querying `SELECT * FROM ShowSettings WHERE ShowFolder='*'` returns zero rows.

## API Endpoints (all under `/api/ShowSettings/`)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/Shows` | GET | All titles with stats (file count, size, codec, resolution, transcode progress) |
| `/Settings` | GET | All show settings |
| `/Save` | POST | Save single title's target resolution |
| `/Delete` | POST | Delete a title setting (revert to default) |
| `/BulkUpdate` | POST | Update target resolution for multiple titles |
| `/Default` | GET/POST | Get or set the global default target resolution |
| `/SmartPopulate` | POST | Generate batch suggestions (largest untranscoded files, sorted by size then bitrate) |
| `/AddToQueue` | POST | Add batch suggestions to transcode queue |
| `/QueueByFolder` | POST | Queue all untranscoded files for specified folders (takes ShowFolders[], ProfileId) |

## Key Files

| File | Role |
|------|------|
| `Templates/ShowSettings.html` | Template + embedded JS (3 cards, all client-side rendering) |
| `Features/ShowSettings/ShowSettingsController.py` | Flask Blueprint, 9 endpoints |
| `Features/ShowSettings/ShowSettingsRepository.py` | Database queries, stats aggregation |
| `Features/ShowSettings/Models/ShowSettingModel.py` | Dataclass: Id, ShowFolder, TargetResolution, dates |

## User Workflows

### Process largest files via batch (Card 1 -- primary workflow)
1. Page loads with Next Batch auto-populated from T: drive (top 10 by size, bitrate as tiebreaker)
2. Review suggested files
3. Select a profile from the dropdown in the card header
4. Click "Add Batch" -- items queue, next batch loads automatically
5. Click "Re-Analyze" to refresh candidates
6. Remove individual items with the "x" button

### Find and queue a specific title (Card 2)
1. Select a drive from the dropdown (defaults to T:)
2. Type title name in search box -- results filter in real-time
3. Select a profile from the dropdown in the card header
4. Click the `+` button on the row -- files are queued immediately
5. For bulk: check multiple titles, click "Queue Selected"

### Browse the media library (Card 3)
1. All titles across all drives are shown
2. Click column headers to sort (title, files, size)
3. Header shows aggregate stats: title count, total GB, transcoded file count/percentage

## Design Decisions

- **Three distinct cards** -- each card has a single purpose, its own colored header, and self-contained controls
- **Batch card is primary** -- top of page, auto-populates with T: drive, always visible
- **Title Search is action-oriented** -- drive filter, search, profile picker, per-row queue button all in one card
- **Media Library is read-only** -- overview/reference of the full library, sortable, no queue actions
- **No target resolution in UI** -- profiles already define TranscodeDownTo per resolution tier in ProfileThresholds. Exposing a separate per-title target resolution was redundant and confusing
- **Per-row queue action** -- plain `+` button when untranscoded files remain; "Done" text when 100% complete
- **Inline profile picker** -- in each card's header, no modal. Click `+` and it queues immediately using the selected profile
- **No decorative icons in card headers** -- plain text titles with Bootstrap badges for counts
- **Consistent card header styling** -- all three cards use colored bg with white text, matching visual weight
