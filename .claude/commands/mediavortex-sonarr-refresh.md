---
description: Rescan + search + reassign-quality-profile for Sonarr series by title substring or all monitored. Wraps Scripts/ArrRescanAndSearchSeries.py so operator can push Sonarr to reconcile disk state, re-download missing episodes, and bulk-switch quality profiles without opening the Sonarr UI.
argument-hint: --title "<substring>" [--set-quality-profile "<name-or-id>"] [--no-rescan] [--no-search] [--execute]
---

Fire `RescanSeries` + `SeriesSearch` against Sonarr for one or more series matched by title substring, or every monitored series. Dry-run by default.

## When to use this skill

- After deleting files from disk (e.g. via `Scripts/SQLScripts/RipDoctorWhoTargets_*.py`) so Sonarr updates its episode-file inventory and marks episodes missing.
- After changing Sonarr's quality profile on a series so a `SeriesSearch` re-grabs episodes at the new quality.
- When Sonarr's UI "Refresh & Scan" button appears to do nothing (silent task queue, path-cache staleness, etc.).
- To re-check missing monitored episodes across every series.
- To bulk-switch series to a specific quality profile (e.g. force all Doctor Who to "HD-1080p").

## Do NOT use this skill

- For a single episode search -- use the Sonarr UI directly.
- For Radarr -- this skill is Sonarr-only. Copy the pattern into a Radarr variant if needed.

## Sonarr connection (hardcoded in `Scripts/ArrRescanAndSearchSeries.py`)

- URL: `http://10.0.0.137:8989/sonarr`
- Key: baked into the script (matches `Scripts/ArrRedownloadBadDialogBoost.py`).

## How to run

Dry-run to see the match list before firing:

```
py Scripts/ArrRescanAndSearchSeries.py --title "Doctor Who"
```

Execute (fire `RescanSeries` + `SeriesSearch` per matched series):

```
py Scripts/ArrRescanAndSearchSeries.py --title "Doctor Who" --execute
```

Every monitored series (dangerous, hits every indexer):

```
py Scripts/ArrRescanAndSearchSeries.py --all-monitored --execute
```

Rescan only, no search:

```
py Scripts/ArrRescanAndSearchSeries.py --title "Doctor Who" --no-search --execute
```

Bulk-switch series to a quality profile + rescan + search (one shot):

```
py Scripts/ArrRescanAndSearchSeries.py --title "Doctor Who" --set-quality-profile "HD-1080p" --execute
```

Rescan skipped, profile switch only:

```
py Scripts/ArrRescanAndSearchSeries.py --title "Doctor Who" --set-quality-profile 4 --no-rescan --no-search --execute
```

## What each Sonarr command does

- `RescanSeries` -- Sonarr walks the on-disk folder for that series, reconciles its EpisodeFile records with what actually exists. Files that were deleted become "episode missing" rows in Sonarr's Wanted queue.
- `SeriesSearch` -- Sonarr triggers indexer searches for every missing monitored episode in the series. Results feed into the download client (Sonarr's usual grab path).
- `--set-quality-profile` -- PUT `/api/v3/series/{id}` with the new `qualityProfileId`. Idempotent: series already on the target profile are skipped. Argument accepts profile id (int) or a case-insensitive substring of the profile name; ambiguous or missing names abort with the available list.

## Related

- `Scripts/ArrRedownloadHeroesS01E08toE23.py` -- one-off delete-and-redownload against a specific S/E range (kept as reference; not a reusable tool).
- `Scripts/ArrRedownloadBadDialogBoost.py` -- delete-and-redownload driven by a DB query (matches the pattern this skill would take next if the operator asks for a "flag column drives Sonarr actions" tool).
