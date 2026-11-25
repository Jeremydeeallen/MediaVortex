# Current Directive

**Set:** 2026-11-25
**Status:** Active -- phase: IMPLEMENTING
**Slug:** profile-row-lookup
**Replaces:** `directives/closed/2026-11-25-insert-returning-id.md` (closed Success)

## Outcome

One answer to "which profile row applies to this file". Queue admission, the encode command, size estimates and video compliance all pick the `ProfileThresholds` row for the file's profile, its content class and its source resolution, and they all pick the same row. A file's content class comes from data the operator can edit on `/settings` (a per-genre class, else the library's default class); no code supplies a class when the data does not. Shows queue again: today every sub-4K file on a tiered profile is refused as an "Upscale" because admission compares the source to the profile's highest target across all rows (BUG-0120), and the encoder picks whichever of a resolution's two rows Postgres returns first (BUG-0121). Nothing has transcoded since 2026-10-20.

This is Unit 0 of the xxx program (`Docs/superpowers/specs/2026-10-28-xxx-stash-cull-audio-design.md`): the xxx video rule (library tier 3) and the shows both depend on it.

## Acceptance Criteria

1. For one file, admission, the encode command, the size estimate and the compliance ceiling all use the same row. Verify: contract test with one fixture (Tier 1, live_action, 1080p source) asserts admission target 720p, `-b:v 900k` + scale to 720p in the command, estimate from the 720p row, and a compliance reason naming `(profile=AV1 Tier 1 Efficient,class=live_action,res=1080p)`; the animation fixture asserts 1080p / 1600k from the animation row.
2. Admission refuses only a true upscale: source below that row's target. Verify: `POST /api/TranscodeQueue/AddJob` for MediaFile 751839 (720p) and 751897 (1080p) returns `Success=true` without `ForceAdd`; `TestUpscaleBlockEnforcement` iterates every (source, row target) pair and blocks exactly the pairs where source < target.
3. Content class is data. A genre with a class on `/settings` wins; otherwise the library's default class on `/settings`. With neither set, compliance reports `missing_input:ContentClass` and nothing is encoded. Verify: contract test over the three cases; `grep -rn "'live_action'" Features/ --include=*.py` returns only the migration seed and the CHECK constraint text.
4. The four duplicate lookups are gone. Verify: `grep -rn "GetProfileMaxTarget\|GetProfileSettingsForTargetResolution\|GetProfileQualityForTargetResolution\|_ResolveTargetResolution" --include=*.py .` returns 0; `EffectiveProfileResolver` and `EncoderKnobRepository` contain no SQL against `ProfileThresholds`. Contract test asserts both.
5. Both knobs are on `/settings` and apply without restart: a "Default content class" per library (library table) and an optional class per genre (genre table). Saving either re-evaluates that library. Verify: PUT each, read back, observe `VideoCompliantReason` change on an affected file within the recompute.
6. Live: one TV 1080p live-action file is admitted on the farm server and transcoded to 720p on a worker, attempt `Success=TRUE`, `VideoCompliantReason` cites the live_action row. One Movies file whose genres include a class-bearing genre shows the animation row in its reason.
7. TV and Movies `VideoCompliant` counts before and after differ only by files whose class changed from the old implicit live_action to animation; the delta is listed with its count.
8. After a directive closes, a non-directive edit is refused as "No active directive", not with the previous directive's phase. Verify: with the template directive in place and a stale `.session-state.json`, an Edit on a `Docs/` file returns the task-delegation message.

## Call-Graph Audit

- **Signal 1:** no new flow doc. Touched stages are `ingest.flow.md` ST5/ST6 and `transcode.flow.md` ST4 (admission) / ST5 (command).
- **Signal 2:** none added. The class is data passed through one lookup; no `if library ==` or `if class ==` at orchestration.
- **Signal 3:** `VideoCompliantReason` today names `class=live_action` for every file; after this it names the resolved class. No sparse columns.
- **Signal 5:** `DefaultContentClass` and per-genre class change which row is read, never which functions run.
- **Five lookups for one question** (tree-wide map, 2026-11-25): `ProfileRepository.GetProfileMaxTarget` (admission, max across all rows), `ProfileRepository.GetProfileSettingsForTargetResolution` (admission, profile+resolution), `ProfileRepository.GetProfileQualityForTargetResolution` (no callers), `EncoderKnobRepository._ResolveTargetResolution` + `GetEncoderKnobsForProfile` (command, profile+resolution `LIMIT 1`), `EffectiveProfileResolver._LookupThresholdsRow` (estimates/QT/compliance summary, profile+resolution `LIMIT 1`), `TierLadderRepository.GetProfileTarget`/`GetTierEncodeKbps` (compliance, already class-aware but fed `getattr(Mf,'ContentClass',None) or 'live_action'`). `MediaFiles` has no `ContentClass` column; nothing derives one. Absorbed: one `TierLadderRepository.GetProfileRow(ProfileName, ContentClass, Resolution)` returning the joined `Profiles` + `ProfileThresholds` row; every consumer reads from it; the four duplicates deleted; `GetTierEncodeKbps`/`GetProfileTarget` implemented over it.
- **Silent default (fail-loud):** `VideoVertical.py:40` `or 'live_action'`. Absorbed: class comes from `ContentClassResolver`; `None` -> `missing_input:ContentClass`.
- **Class derivation pattern:** follows `FileTierResolver` (computed at read from `StorageRoots` + `MediaFiles.Genres`, no stored column, no cascade). `GenreQualityTiers` gains nullable `ContentClass`; `StorageRoots` gains nullable `DefaultContentClass`. Saving either runs the existing `_SpawnLibraryRecompute`.
- **Seam, admission vs. encoder:** both took `(ProfileName, SourceResolution)`; `ProcessTranscodeQueueService:829` now passes the resolved class to `GetEncoderKnobsForProfile`.
- **Hook stale state:** `Get-SessionState` keeps `.session-state.json`'s phase when the directive file is the template (slug `<previous-slug>`), so the phase gate reports the closed directive's phase. Absorbed: no directive slug -> state has no phase -> task-delegation gate answers.

## Out of Scope

- (b) `ReassignTierProfiles` skips libraries without a `GenreSource`, and never moves `operator`/`series`-sourced files. Both are Unit A (`xxx-video-tier`), where the override-reset knob is added.
- (b) Audio policy authority and compliance (Unit B), cull (Unit C).
- (b) Sonarr genre sync for TV. TV files have no genres, so TV class is the library default (live_action) until a sync exists; animated TV shows get live-action rows, as today.
- (a) Tier ladder values, library tiers, classifier rules: unchanged. `AnimeByFolder` rule keeps assigning Tier 2 Good; it never set a class and still does not.
- (a) `GetEncoderKnobsForProfile`'s 47-field `EncoderKnobs` shape is unchanged; only its row source changes.

## Constraints

- No stored `MediaFiles.ContentClass`; class is resolved at read (`db-is-authority`).
- Fail loud: unresolved class is a reason string, never a default.
- Migrations idempotent; snapshot regenerated in the same commit.
- Both knobs ship with GUI in this directive (`gui-editable-knobs`).

## Escalation Defaults

- Determinism vs. compatibility -> determinism: one row, always.
- Risk tolerance: medium. Shows start transcoding again when this lands; Tier 1 live-action sends 1080p/4K to 720p @ 900, which is the configured ladder.

## Engineering Calls Already Made

- Lookup lives in `TierLadderRepository` (it already owns the class-aware queries); returns a `ProfileRow` dataclass with every `Profiles` + `ProfileThresholds` column the consumers use.
- `ContentClassResolver.Resolve(StorageRootId, MediaFileId) -> Optional[str]`: first genre (in `MediaFiles.Genres` order) with a non-null `GenreQualityTiers.ContentClass` wins; else `StorageRoots.DefaultContentClass`; else `None`.
- Seed: `DefaultContentClass='live_action'` for all three roots; `GenreQualityTiers.ContentClass='animation'` for `Animation`. Operator edits afterwards on `/settings`.
- `EffectiveProfileResolver.Resolve(Mf)` keeps its signature and resolves the class internally.

## Status

Phases advance by editing the `**Status:**` header line at the top of this file: `**Status:** Active -- phase: <NEXT>`. The PreToolUse hook reads ONLY that header line (NOT this section). See `.claude/standards/index.md` for the phase machine.

### Plan

1. Hook: `Get-SessionState` drops the state file's phase/slug when `Get-DirectiveSlug` is null (criterion 8).
2. Spec + plan: rewrite `Docs/superpowers/specs/2026-10-28-xxx-stash-cull-audio-design.md` (Unit 0 + A + B as designed 2026-11-25, -26 LUFS, policy-authoritative audio) and `Docs/superpowers/plans/2026-10-29-xxx-program.md` phases. Commit; operator reviews before step 3.
3. Migration `AddContentClassDefaults_2026_11_25.py`: `StorageRoots.DefaultContentClass TEXT NULL CHECK IN ('live_action','animation')`, `GenreQualityTiers.ContentClass TEXT NULL CHECK (...)`, seeds. Regenerate snapshot.
4. `ContentClassResolver` + repository reads/writes (`LibraryDefaultTierRepository`, `GenreQualityTierRepository`).
5. `TierLadderRepository.GetProfileRow` + `ProfileRow`; `GetProfileTarget`/`GetTierEncodeKbps` over it.
6. Consumers: `EncoderKnobRepository.GetEncoderKnobsForProfile(ProfileName, ContentClass, SourceResolution)` (delete `_ResolveTargetResolution`); `EffectiveProfileResolver` (delete own SQL); admission in `QueueManagementBusinessService` (upscale test = `row.TranscodeDownTo`; delete the three `ProfileRepository` methods and their calls at 842/1566/1569/1601; `RecalculateQueuePriorities.py:93`); `ProcessTranscodeQueueService:829`; `VideoVertical` (class from resolver, no default).
7. GUI: `/api/SystemSettings/LibraryTiers` GET/PUT carry `DefaultContentClass`; `/GenreTiers` GET/PUT carry `ContentClass`; two dropdowns in `Settings.html`; both saves call `_SpawnLibraryRecompute`.
8. Tests: new `TestProfileRowLookup.py` (criteria 1, 3, 4); `TestUpscaleBlockEnforcement` rewritten to row targets; mocks updated in `TestTvVideoRuleTier1`, `TestMoviesVideoRule`, `TestVerticalsAreProfileIndependent`, `TestEncoderKnobNormalizeResolution`, `TestWorkerEncoderResolver`.
9. Docs: `profile-tier-ladder.feature.md` (lookup + class resolution, new seam), `marginal-savings-gate.feature.md` 2b, `video-encoding.feature.md`, `classifier.feature.md`, `transcode.flow.md` ST4/ST5 pointers, GLOSSARY "content class". Close BUG-0120/0121.
10. Deploy server + fleet; smoke criteria 2, 5, 6, 7.

### Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| N1 | knobs -> class | `/settings` PUT LibraryTiers / GenreTiers | `StorageRoots.DefaultContentClass`, `GenreQualityTiers.ContentClass` (TEXT NULL, CHECK) | `ContentClassResolver` reads fresh per call | C3, C5 |
| N2 | class + profile + resolution -> row | `TierLadderRepository.GetProfileRow` | `ProfileRow` (one joined row) or `None` | admission, `EncoderKnobRepository`, `EffectiveProfileResolver`, `VideoVertical` | C1, C4 |
| N3 | row -> admission | `row.TranscodeDownTo` | resolution label | `EvaluateQueueAdmission` blocks only source < target | C2 |
| N4 | row -> command | `EncoderKnobs` from `ProfileRow` | 47 fields, unchanged shape | `VideoSlot` | C1, C6 |
| N5 | no directive -> gate | `Get-SessionState` | `$null` phase when template | task-delegation gate message | C8 |

### Files

```
.claude/hooks/pre-edit-standards.ps1                       -- EDIT: stale state ignored when no directive
Docs/superpowers/specs/2026-10-28-xxx-stash-cull-audio-design.md -- EDIT: Units 0, A, B; -26 LUFS; policy-authoritative audio
Docs/superpowers/plans/2026-10-29-xxx-program.md           -- EDIT: phases for Units 0-C
Scripts/SQLScripts/AddContentClassDefaults_2026_11_25.py   -- CREATE: two nullable CHECK columns + seeds
.claude/schema/snapshot.json                               -- REGENERATE
Features/Profiles/ContentClassResolver.py                  -- CREATE: genre class else library default else None
Features/Profiles/TierLadderRepository.py                  -- EDIT: GetProfileRow + ProfileRow; tier/target methods over it
Features/Profiles/LibraryDefaultTierRepository.py          -- EDIT: DefaultContentClass read/write
Features/Profiles/GenreQualityTierRepository.py            -- EDIT: ContentClass read/write
Features/Profiles/EffectiveProfileResolver.py              -- EDIT: row from GetProfileRow; class via resolver
Features/Profiles/EncoderKnobRepository.py                 -- EDIT: class argument; row from GetProfileRow; delete _ResolveTargetResolution
Features/Profiles/ProfileRepository.py                     -- EDIT: delete GetProfileMaxTarget, GetProfileSettingsForTargetResolution, GetProfileQualityForTargetResolution
Features/TranscodeQueue/QueueManagementBusinessService.py  -- EDIT: admission + estimate read the row
Features/TranscodeJob/ProcessTranscodeQueueService.py      -- EDIT: pass class to GetEncoderKnobsForProfile
Features/VideoEncoding/VideoVertical.py                    -- EDIT: class from resolver; no default
Features/SystemSettings/SystemSettingsController.py        -- EDIT: LibraryTiers + GenreTiers carry class
Templates/Settings.html                                    -- EDIT: two class dropdowns
Scripts/SQLScripts/RecalculateQueuePriorities.py           -- EDIT: caller of deleted method
Tests/Contract/TestProfileRowLookup.py                     -- CREATE: C1, C3, C4
Tests/Contract/TestUpscaleBlockEnforcement.py              -- EDIT: row targets
Tests/Contract/TestTvVideoRuleTier1.py, TestMoviesVideoRule.py, TestVerticalsAreProfileIndependent.py, TestEncoderKnobNormalizeResolution.py, TestWorkerEncoderResolver.py -- EDIT: mocks
Features/Profiles/profile-tier-ladder.feature.md           -- EDIT: lookup contract, class resolution, seam
Features/TranscodeQueue/marginal-savings-gate.feature.md   -- EDIT: 2b
Features/VideoEncoding/video-encoding.feature.md           -- EDIT: class input
Features/ContentClassifier/classifier.feature.md           -- EDIT: class is resolved, not assigned
transcode.flow.md, GLOSSARY.md                             -- EDIT: pointers; "content class"
memory/KNOWN-ISSUES.md, memory/BUG-INDEX.md, memory/KNOWN-ISSUES-ARCHIVE.md -- EDIT: close BUG-0120, BUG-0121
```

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|

### Verification

### Decisions Made

---

## Closure (thin-pointer archive shape)

When this directive is ready to close: confirm Promotions, set `Status: Closed -- <outcome>` with a `**Closed:**` line, then `git mv .claude/directive.md .claude/directives/closed/YYYY-MM-DD-<slug>.md` and copy `_template.md` back. Governed by `.claude/rules/doc-layering.md` and `.claude/rules/ceo-mode.md`.
