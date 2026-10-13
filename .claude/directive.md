# Current Directive

**Set:** 2026-10-13
**Status:** Active -- phase: DELIVERING
**Slug:** movies-video-rule
**Replaces:** `directives/closed/2026-10-13-crash-recovery-audiofix-type.md` (closed)

## Outcome

A movie's bucket and its encode quality are decided by its genre. Each genre carries an operator-set quality tier; a movie takes the highest tier among its genres, and a movie with no known genre takes the Movies library default. Action and visually heavy films keep more bitrate; romcoms and slow films are tiered lower. Genres come from Radarr, with no per-movie operator work. The video rule is the same one TV already uses (source bitrate against the tier's encode bitrate times the resolution multiplier); assigned profile and source codec stop moving a movie between buckets. TV and XXX behave exactly as before. XXX is the next directive (`xxx-video-rule`), which also deletes the old profile-and-codec path.

Backlog row 1 of `.claude/directives/backlog/_bucket-rules-phase-2.md`, Movies half. Operator 2026-10-13: Movies only; tier by type of movie; asked whether Radarr genres can drive it (they can: 3,422 of 3,427 movie files have at least one).

## Acceptance Criteria

1. Every genre seen on a movie has an operator-set quality tier. The operator views and changes genre tiers on `/settings` with no SQL; a change re-evaluates the affected movies and is seen by the next evaluation without a restart.
2. Every movie file whose movie Radarr knows has that movie's genres recorded. Verify: count of Movies files with no recorded genres equals the count Radarr has no genres or no entry for (5 today).
3. A movie's tier is the highest tier among its genres. A movie with no recorded genre takes the Movies library default tier (2). Verify: SQL recomputing the tier from recorded genres and the genre tiers disagrees with the tier named in the stored reason on 0 Movies rows.
4. A movie's video is compliant iff its source video kbps <= (the kbps its tier encodes that resolution at) x (that resolution's multiplier). Assigned profile and source codec play no part. Verify: SQL recompute disagrees with stored `VideoCompliant` on 0 Movies rows; 0 Movies rows with a reason starting `source_codec_matches_target` or equal to `missing_input:AssignedProfile`.
5. The stored reason for a movie names source kbps, ceiling, tier, multiplier, and where the tier came from (the deciding genre, or the library default).
6. A movie whose profile was not set by the operator carries its tier's profile, so it is encoded at its genre's tier. A profile the operator set on a movie is kept and changes only what that movie is encoded at, never its bucket.
7. A movie added after this ships gets its genres and tier with no operator action, before it is bucketed.
8. When Radarr cannot be reached, a movie is not quietly given the library default: it stays undecided, the failure is visible to the operator, and it is retried.
9. TV and XXX are untouched. Verify: snapshot of `(Id, VideoCompliant, VideoCompliantReason, WorkBucket, AssignedProfile)` for TV + XXX before vs after differs on 0 rows.
10. `transcode.flow.md` D4 states the video rule once, covering genre tiers; no other doc states a conflicting rule for Movies.

### Proposed starting genre tiers (operator edits on `/settings` afterwards)

| Tier | Genres | Movies today |
|---|---|---|
| 3 | Action, Adventure, Science Fiction, Fantasy, War | 1,721 |
| 2 (library default) | Thriller, Crime, Horror, Mystery, Family, Animation, Western, and any genre not listed | 717 |
| 1 | Romance, Comedy, Drama, Documentary, Music, History, TV Movie | 989 |

Highest tier wins: an action comedy is Tier 3; a romantic comedy is Tier 1; a crime drama is Tier 2. Tier 1 outputs 720p (58 Tier 1 movies are 1080p today). Projected against today's library with these tiers: 24 movies fail video (19 of them new to Transcode), 55 leave the Transcode bucket. 2,006 movies are already our own output and are never re-encoded (D7), so the tiers mostly govern movies that arrive from now on.

## Call-Graph Audit

- **Flow docs:** `transcode.flow.md` (D4 rule table, ST3 assign, ST4 recompute), `ingest.flow.md` (probe -> classifier -> compliance order; genre fetch joins this order). No pair describes one operation.
- **Orchestration mode branch:** none added. `RecomputeForFiles` calls the three verticals identically for every file.
- **Signal 5 (config-driven graph shape) -- existing violation, narrowed, not removed:** `VideoVertical.Evaluate` takes the tier path when the library has a default tier and the profile-and-codec path when it does not. After this directive only XXX takes the old path. It is deleted by `xxx-video-rule`.
- **Genre tier inside the tier path:** genre refines which tier is used; it is data flowing through the same lookup (`GetTierEncodeKbps`), not a second path. TV files have no recorded genres and fall to the library tier by the same code.
- **Second Radarr caller:** `Features/AudioNormalization/Services/NoAudioResolver.py` holds private Radarr HTTP calls and the folder-to-movie match. Genre fetch is the second consumer; the shared read (list movies, match by folder) moves to one place both use.
- **Shared output columns:** `MediaFiles.VideoCompliant` / `VideoCompliantReason` keep one writer for every library. The new recorded-genres column is populated for Movies only; TV and XXX stay NULL because no genre source is wired for them (TV would be Sonarr; out of scope).
- **Cascade:** recorded genres and genre tiers become inputs to the video verdict. Their writers recompute the affected files before returning (`writer-owns-cascade.md`).
- **OOS categories:** below.

## Out of Scope

- (b) XXX video rule and deletion of the profile-and-codec path in `VideoVertical.Evaluate` -- next directive `xxx-video-rule`; includes backlog row 12 (`XxxPinTier2Good`).
- (b) Genre tiers for TV (Sonarr genres). TV stays on its library tier per operator decision 2026-10-06.
- (b) Re-acquiring movies already encoded at a tier lower than their genre's tier (1,707 movies are assigned Tier 1 or 2 today and would be Tier 3 by genre; those already encoded are terminal under D7).
- (b) Everything else in `.claude/directives/backlog/_bucket-rules-phase-2.md`.

## Constraints

- No change to the `WorkBucket` generated column.
- No production config values changed for testing.
- Workers drained before the Movies recompute and before any restart.
- Radarr is read only: no deletes, no searches, no writes to Radarr.

## Escalation Defaults

- Rule clarity vs preserving a current verdict -> rule clarity (Movies only).
- Risk tolerance: medium (projected 19 movies move into Transcode).

## Engineering Calls Already Made

- Genre source is Radarr (`GET /api/v3/movie`, field `genres`), matched to a file by its movie folder, the same match `NoAudioResolver` uses. Measured 2026-10-13: 3,424 of 3,427 files match a Radarr movie; 2 matched movies have no genres.
- Ceilings come from live ladder cells, as on TV. Today: Tier 1 480p 1600 / 720p 2000 / 1080p 2000 / 2160p 3000; Tier 2 2100 / 2500 / 4400 / 16500; Tier 3 2600 / 3400 / 6000 / 24000 kbps.
- The bucket is judged by the movie's genre tier, not by a profile the operator sets on it by hand. This keeps the TV decision (an override changes the encode, never the bucket) true for every library.
- Evaluation reads genres from the database only. Radarr is called when a movie is ingested and by a one-time backfill, never per evaluation.

## Status

Phases advance by editing the `**Status:**` header line at the top of this file.

### Files

```
Scripts/SQLScripts/AddGenreQualityTiers_2026_10_13.py        -- CREATE: GenreQualityTiers table + seed, MediaFiles.Genres, StorageRoots.GenreSource; idempotent, inert
Core/Arr/RadarrClient.py                                     -- CREATE: list movies, find a movie by its folder
Features/Profiles/GenreQualityTierRepository.py              -- CREATE: fresh read/write of genre tiers
Features/Profiles/FileTierResolver.py                        -- CREATE: a file's tier and where it came from
Features/Profiles/LibraryDefaultTierRepository.py            -- EDIT: libraries that have a genre source
Features/VideoEncoding/VideoVertical.py                      -- EDIT: tier path asks the resolver
Features/ContentClassifier/ContentClassifierService.py       -- EDIT: tier profile from the resolver; reassign tier profiles
Features/ContentClassifier/MovieGenreSyncService.py          -- CREATE: record genres for files that have none yet, then cascade
Features/FileScanning/FileScanningBusinessService.py         -- EDIT: one call to the genre sync when a scan completes
Features/AudioNormalization/Services/NoAudioResolver.py      -- EDIT: folder match through RadarrClient
Features/SystemSettings/SystemSettingsController.py          -- EDIT: GET/PUT genre tiers; library cascade reassigns tier profiles
Templates/Settings.html                                      -- EDIT: genre tier section
Scripts/ActivateMoviesGenreTiers_2026_10_13.py               -- CREATE: after deploy: Movies genre source + default tier 2, sync, reassign, recompute
Tests/Contract/TestMoviesVideoRule.py                        -- CREATE
Tests/Contract/TestTvVideoRuleTier1.py                       -- EDIT: resolver stub in place of library-tier stub
Tests/Contract/TestVerticalsAreProfileIndependent.py         -- EDIT: same
Tests/Contract/TestWriterOwnsCascadeEnforcement.py           -- EDIT: Genres is a compliance-input column
.claude/rules/writer-owns-cascade.md                         -- EDIT: Genres row
transcode.flow.md, ingest.flow.md, DOMAIN.md,
Features/VideoEncoding/video-encoding.feature.md,
Features/ContentClassifier/classifier.feature.md,
.claude/directives/backlog/_bucket-rules-phase-2.md          -- EDIT (backlog: row 1 becomes xxx-video-rule, next up)
```

### Plan

1. Migration (additive, changes no verdict): `GenreQualityTiers(Genre TEXT PRIMARY KEY, QualityTier INT NULL CHECK 1-5)` where NULL means "library default"; seed the 19 Radarr genres with the approved tiers; `MediaFiles.Genres TEXT NULL` (NULL = not fetched yet, empty = fetched and none); `StorageRoots.GenreSource TEXT NULL`.
2. `RadarrClient.ListMovies(Url, Key)` and `FindByFolder(Movies, Folder)`. `NoAudioResolver._MatchMovie` delegates to `FindByFolder`.
3. `FileTierResolver.Resolve(MediaFileId)`: library has no default tier -> None. Library has a genre source and the file's genres are not fetched -> tier undecided. Otherwise tier = highest of (genre tier, or library default when the genre's tier is NULL) across the file's genres; no genres -> library default. Returns the tier and its origin (`genre=<name>`, `genre=none`, or empty for a library with no genre source).
4. `VideoVertical.Evaluate`: resolver None -> existing profile path unchanged. Undecided -> `(None, 'missing_input:Genres')`. Otherwise the existing tier comparison; reason gains `,genre=<name>` only for a genre-sourced library, so TV reasons are byte-identical.
5. `ContentClassifierService`: unprofiled file takes its resolved tier's profile (source `genre_tier` or `library_default_tier`); undecided -> no profile yet, no rules walk. New `ReassignTierProfiles(Ids)`: files in a genre-sourced library whose profile source is not `operator` or `series` get their tier's profile.
6. `MovieGenreSyncService.SyncMissing()`: files in genre-sourced libraries with `Genres IS NULL` -> one Radarr read -> write genres, add unseen genres to `GenreQualityTiers` with NULL tier, `ReassignTierProfiles`, `RecomputeForFiles`. Nothing missing -> one SELECT, no Radarr call. Radarr failure raises. Called at the end of every scan, so a new movie is handled by the scan that finds it and a failure is retried by the next scan; the failed scan reports the Radarr error.
7. `/settings`: `GET/PUT /api/SystemSettings/GenreTiers`; PUT re-evaluates every genre-sourced library in the background. The library cascade (`_SpawnLibraryRecompute`) calls `ReassignTierProfiles` before recompute.
8. Tests per Files list. Run `TestClaimAuthority`, `TestWriterOwnsCascadeEnforcement`, `TestFailLoud`, `TestNoAudioResolver`, `TestClassifierCascade`, `TestTvPinTier1Classification`.
9. Order: migration -> commit + push -> fleet deploy (operator go-ahead) -> snapshot TV + XXX -> `ActivateMoviesGenreTiers` (sets Movies `GenreSource='radarr'` and default tier 2 when unset, sync, reassign, recompute) -> verify. Activation waits for the deploy: an old-code worker would judge movies by the bare library tier.

Seams added or changed:

| Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|
| Radarr -> recorded genres | `MovieGenreSyncService.SyncMissing` | `MediaFiles.Genres TEXT`: NULL not fetched, `''` none, else comma-joined Radarr genre names | `FileTierResolver` splits on comma | `TestMoviesVideoRule`; count query in criterion 2 |
| Genre tier -> file tier | operator via `/settings` PUT | `GenreQualityTiers(Genre, QualityTier INT NULL)` | `FileTierResolver` reads per call; NULL = library default | `TestMoviesVideoRule` |
| File tier -> video rule | `FileTierResolver.Resolve` | `None` or `(Tier: int or None, Origin: str)` | `VideoVertical.Evaluate` | `TestMoviesVideoRule`, `TestTvVideoRuleTier1` |
| File tier -> profile | same | same | `ContentClassifierService` maps tier -> `Profiles(Family='ANY', QualityTier)` name | `TestMoviesVideoRule` |
| Library genre source | activation script | `StorageRoots.GenreSource TEXT NULL` (`'radarr'`) | resolver and sync; any other value raises | `TestMoviesVideoRule` |

### Promotions

| Source artifact | Target file |
|---|---|
| Video rule with genre tier; how a file's tier is found | `transcode.flow.md` D4 |
| Reason format with deciding genre; genre tier GUI | `Features/VideoEncoding/video-encoding.feature.md` C1, C4 |
| Genre tier profile; reassignment on tier change | `Features/ContentClassifier/classifier.feature.md` C9 |
| Genre record at end of scan; `Genres` wire shape | `ingest.flow.md` ST3, ST5, S12 |
| Operator decisions and starting tiers | `DOMAIN.md` 2026-10-13 entry |
| `Genres` is a compliance-input column | `.claude/rules/writer-owns-cascade.md` |
| XXX is next up | `.claude/directives/backlog/_bucket-rules-phase-2.md` rows 1, 12 |

### Verification

- **Migration:** `AddGenreQualityTiers_2026_10_13.py` applied twice 2026-10-13; 19 genres seeded (5 at Tier 3, 7 at Tier 1, 7 at library default); `MediaFiles.Genres` and `StorageRoots.GenreSource` exist, all NULL. No verdict changed: Movies has no default tier until activation.
- **Logic:** 84 contract tests pass (`TestMoviesVideoRule` 23, `TestTvVideoRuleTier1`, `TestVerticalsAreProfileIndependent`, `TestWriterOwnsCascadeEnforcement`, `TestNoAudioResolver`, `TestClassifierCascade`, `TestTvPinTier1Classification`, `TestVideoVerticalCodecMatch`, `TestVideoComplianceMultiplier`, `TestNonVideoContainersExcluded`, `TestRecomputeForFilesRowIsolation`).
- **Not run:** `TestClaimAuthority` (queue held 25 pending + 2 running jobs; the test claims live rows; no claim code changed). `TestFailLoud`: the same 2 baseline tests fail with and without this change; none of the changed files is named.
- **1 (partial):** I9 WebService restarted on `1555686e` 2026-10-13. `GET /api/SystemSettings/GenreTiers` returns the 19 genres with tiers; PUT rejects tier 9 (400) and an unknown genre (404); `/settings` renders the Genre tiers section. A successful PUT with its cascade is not exercised yet: it re-evaluates Movies, held for after activation.
- **Deploy:** fleet on `5efe1389` 2026-10-13, 9 workers OK, exit 0, no job running at the time. dot-3/4 and wakko-3/4 still heartbeat old code with every capability off.
- **Activation:** `ActivateMoviesGenreTiers_2026_10_13.py` 2026-10-13 18:08 UTC: Movies `DefaultQualityTier=2`, `GenreSource='radarr'`; genres recorded for 3,427 files (5 with none); 2,616 profiles reassigned; 3,427 files re-evaluated.
- **1:** on the running I9 WebService, `PUT /api/SystemSettings/GenreTiers {Action, 3}` (its current value) -> 200; log `Library tier recompute complete: StorageRootId=2, 3427 files` at 18:11:37 UTC.
- **2:** Movies files with `Genres IS NULL`: 0. With empty genres: 5 (3 not in Radarr, 2 with no genre in Radarr).
- **3, 4, 5, 6:** `TestMoviesVideoRuleLive` 4/4 against live rows after activation (verdict equals the rule; reason names the recomputed tier and a genre; no profile or codec reason; every non-operator profile equals its tier's profile). Sample: `source_above_ceiling:2249>2000(tier=1:1000*2.0,genre=Documentary)`. Movies video verdicts: 3,403 pass, 24 fail. Profiles: Tier 3 1,718, Tier 1 992, Tier 2 717; the 4 `series`-sourced profiles kept.
- **Movies buckets before -> after:** Transcode 57 -> 21, Remux 461 -> 457, AudioFix 2,414 -> 2,410, Compliant 490 -> 538, Unclassified 5 -> 1.
- **7:** MediaFile 618475: recorded genres cleared, `POST /api/Sync/Path` for its folder -> scan `df288fef` on worker I9-2024 logged `Genres recorded for 1 files` at 18:11:30 UTC, before `Scan complete`; genres, tier 3 reason and profile restored with no other action. No movie has arrived from Radarr since activation; this is the same code path a new file takes.
- **8:** same file, live database, Radarr client pointed at a closed port: fetch raised `URLError`, nothing written, video verdict stayed undecided with reason `missing_input:Genres`; the next fetch with the real Radarr restored it. `PerformScan` returns the error as the scan's failure message (read in code, not driven live: Radarr was not taken down).
- **9:** TV + XXX snapshot `(VideoCompliant, VideoCompliantReason, WorkBucket, AssignedProfile)`, 51,819 rows, before deploy vs after activation: 0 changed, 0 added, 0 removed.
- **10:** `transcode.flow.md` D4 carries the rule; see Promotions.

### Delivery

```
DIRECTIVE: movies get their tier, bucket and encode quality from their Radarr genres
STATUS: Done, awaiting operator closure
WHAT SHIPPED: genre tiers on /settings; Movies judged by genre tier with the TV rule; profiles follow the genre tier; genres fetched at the end of every scan
HOW TO USE IT: /settings -> Transcoding -> "Genre tiers (Movies)". Pick a tier per genre and Save; Movies re-evaluate in the background. "Library default" follows the Movies default tier in the table above it. To pin one movie, set its profile by hand; that changes its encode, not its bucket.
WHAT YOU NEED TO EXECUTE: nothing. 21 movies sit in the Transcode bucket; queue them from /Work when wanted.
DECISIONS I MADE: see Decisions Made.
KNOWN GAPS / DEFERRED: none inside this directive. XXX and the deletion of the old profile-and-codec path are the next directive (`xxx-video-rule`).
```

### Decisions Made

- Genres are recorded at the end of every scan, not at probe and not by a new timer. One fetch path covers a new movie (the scan that finds it), a failed fetch (the next scan) and the first backfill (the activation script calls the same function).
- A failed Radarr read fails the scan it ran in. That is where the operator already looks for scan trouble, and it needs no new surface.
- A genre's tier may be "library default" (NULL). Seven genres start there, so moving the Movies default moves them together.
- `StorageRoots.GenreSource` names which libraries tier by genre. It is wiring (which service backs a library), not a tuning knob, so it has no GUI control; the activation script sets it for Movies.
- The resolver reads a file's genres by id instead of through the media file model, so no model or save path changed.
- Operator-set profile sources are `operator`, `series`, `root_folder`, `manual_sql` (`classifier.feature.md` S5). Every other source follows the genre tier.
