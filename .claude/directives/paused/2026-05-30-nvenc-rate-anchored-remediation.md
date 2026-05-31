# Current Directive

**Set:** 2026-05-30
**Status:** Paused 2026-05-30 -- phase was NEEDS_PLAN -- interrupted by unified-standards-destination (criteria not yet ratified; resume against the unified shape)
**Slug:** nvenc-rate-anchored-remediation
**Replaces:** none (new directive). Interrupts paused `ceo-mode-enforcement` (`.claude/directives/paused/2026-05-30-ceo-mode-enforcement.md`).

## Outcome

Every tunable encoder knob the operator's canary command names is held in a `ProfileThresholds` or `Profiles` column, not as a literal in `Models/CommandBuilder.py`. The operator-validated canary command is recoverable from the database as a `Profiles` + `ProfileThresholds` row pair: a SELECT against those rows reproduces the canary's knob values exactly. A live transcode against that profile emits an ffmpeg command matching the canary in the knob dimensions the canary covers (rate-control, lookahead, B-frame depth, tune, multipass, scale shape, pixel format, audio codec/bitrate, container muxing).

CommandBuilder reads; it does not decide. After this directive, adding a new encoder regime is a row insert -- not a code change. Adjusting an existing regime is a SQL UPDATE -- not a code change. The "Pinned knobs that... currently DIVERGE" audit list in `Features/Profiles/nvenc-rate-anchored.feature.md` is gone because divergence is no longer expressible: code does not carry the values to diverge from.

The standards index gains a named (not gated, judgment-reviewed) entry calling out "no hardcoded values where DB-driven is possible" so the next directive does not repeat this miss.

## Acceptance Criteria

### A. Schema lifts every canary knob to a column

Each criterion adds (or repurposes) a column that holds a knob the canary command pins. Columns live on `ProfileThresholds` unless the knob is regime-level (varies by Profile, not by resolution tier) -- in which case it lives on `Profiles`. Choice of table is per-knob:

1. **`ProfileThresholds.RcLookahead INTEGER`** holds the `-rc-lookahead` value. Nullable; when NULL, CommandBuilder does NOT emit the flag (encoder default applies). Verifiable: `\d ProfileThresholds` shows the column; canary-derived seed row carries `20`.

2. **`ProfileThresholds.BFrames INTEGER`** holds the `-bf` value. Nullable; when NULL, no `-bf` flag emitted. Verifiable: column exists; canary-derived seed row carries `4`.

3. **`ProfileThresholds.BRefMode TEXT`** holds the `-b_ref_mode` value (`'middle'` in canary, also valid: `'each'`, `'disabled'`). Nullable; when NULL, no flag emitted. CHECK constraint enforces the allowed values OR is omitted with the trade documented. Verifiable: column exists; canary-derived seed row carries `'middle'`.

4. **`Profiles.Tune TEXT`** holds the `-tune` value (`'hq'`, `'uhq'`, `'ll'`, ...). Already implicit in existing CommandBuilder branching; remediation makes it a column. Nullable allowed for backward-compat with existing rows; CommandBuilder falls back to the current hardcoded default ONLY when the column is NULL on an existing row, AND a one-time migration backfills the column to the current default for every existing row. After backfill, no future code path reads a default literal. Verifiable: column exists; all pre-existing rows have a non-NULL value matching what CommandBuilder used to emit; canary-derived seed row carries `'hq'`.

5. **`Profiles.Multipass TEXT`** holds the `-multipass` value (`'fullres'`, `'qres'`, `'disabled'`, `'2pass'`). Same shape as criterion 4 -- nullable with backfill. Verifiable: column exists, backfilled, canary seed carries `'fullres'`.

6. **`Profiles.PixelFormat TEXT`** holds the `-pix_fmt` value. Same shape as 4 / 5. Verifiable: column exists, backfilled, canary seed carries `'p010le'`.

7. **`Profiles.AudioCodec TEXT` and `Profiles.AudioBitrateKbps INTEGER`** hold the `-c:a` value and the `-b:a` value (kbps, integer). Same backfill discipline -- existing rows get the value MediaVortex currently uses for audio re-encoding so the data-driven path is byte-identical to today for legacy profiles. Verifiable: both columns exist, backfilled, canary seed carries `'eac3'` + `256`.

8. **`Profiles.Container TEXT`** holds the `-f` value (`'mp4'`, `'mkv'`, ...). **`Profiles.FastStart BOOLEAN`** holds whether `-movflags +faststart` is emitted. Nullable / backfilled per the 4 / 5 / 6 pattern; canary seed carries `'mp4'` + `TRUE`. Verifiable: columns exist, backfilled, seeded.

9. **`ProfileThresholds.ScaleHeight INTEGER`** AND **`ProfileThresholds.PreserveAspect BOOLEAN`** together encode the scale filter. When `PreserveAspect=TRUE`, CommandBuilder emits `-vf scale=w=<width>:h=-1` where `<width>` is derived from the resolution tier ScaleHeight + a 16:9 default OR from a `ScaleWidth` column if added in a follow-up; this directive picks the simpler "PreserveAspect drives the `-1` form, ScaleHeight pins the height target" shape. When `PreserveAspect=FALSE`, CommandBuilder emits `-vf scale=<derived_width>:<ScaleHeight>` (forced aspect). Verifiable: columns exist; canary-derived seed row for 720p tier carries `ScaleHeight=720, PreserveAspect=TRUE`; emitted command for that row is `-vf scale=w=1280:h=-1`. (Width=1280 is derived from `round(720 * 16/9)`; documenting the formula as an `## Engineering Calls Already Made` entry is acceptable in lieu of a separate `ScaleWidth` column.)

10. **Rate-anchored bitrate triplet:** the canary uses fixed `-b:v 600k -maxrate:v 1200k -bufsize:v 1200k`. Existing schema already has `SourceBitratePercent / Min / Max` (percentage-of-source clamp). Resolution: ADD `ProfileThresholds.TargetBitrateKbps INTEGER` AND `ProfileThresholds.MaxBitrateMultiplier NUMERIC(3,2) DEFAULT 2.0`. When `TargetBitrateKbps` is non-NULL on a VBR profile, CommandBuilder ignores `SourceBitratePercent / Min / Max` and emits `-b:v <TargetBitrateKbps>k -maxrate:v <TargetBitrateKbps * MaxBitrateMultiplier>k -bufsize:v <same>k`. When `TargetBitrateKbps` is NULL, the existing percentage-of-source path applies. Both regimes coexist on the same VBR profile family -- the canary becomes a `TargetBitrateKbps=600` seed row; existing percentage-of-source profiles keep their behavior. Verifiable: both column families exist; the canary-derived seed row has `TargetBitrateKbps=600, MaxBitrateMultiplier=2.0` and NULL on `SourceBitratePercent / Min / Max`; existing rate-anchored rows are unchanged.

### B. CommandBuilder is read-only on knob values

11. **`Models/CommandBuilder.AddCodecParameters`** contains zero numeric literals or string literals for any knob covered by criteria A.1-A.10. Specifically, the following must NOT appear as literals: `'-rc-lookahead' + ' 32'`, `'-bf' + ' 7'`, `'-tune' + ' uhq'`, `'-multipass' + ' fullres'`, `'-pix_fmt' + ' yuv420p'` (or any pixel format), `'eac3'`, `'mp4'`, `'+faststart'`, `'1280:720'`, `'h=-1'`. Each is read from the Profile / ProfileThresholds row. The ffmpeg argument NAMES (`-rc-lookahead`, `-bf`, `-tune`, etc.) are NOT covered by this criterion -- they are protocol constants, not tuning choices. Verifiable: grep for each forbidden literal in `Models/CommandBuilder.py` returns zero matches; emitted command for the legacy `nv_cq32_sink` profile is byte-identical to today (backfill made this possible).

12. **CommandBuilder branching depends only on column VALUES, not on Profile name strings.** The function does NOT contain `if ProfileName == 'NVENC AV1 P7 VBR 30pct -720p'` or any name-based switch. Verifiable: grep for `ProfileName ==` and `ProfileName.startswith(` and `ProfileName.contains(` in CommandBuilder returns zero matches.

13. **Adding a new encoder regime requires a row insert, not a code change.** Verifiable: a hypothetical new profile (e.g. `NVENC AV1 P7 CBR -720p` with `-rc cbr -b:v 800k`) can be expressed as a Profile + ProfileThresholds INSERT pair using the columns from criterion A, with no edit to `CommandBuilder.py`. This criterion is verified by writing the migration as a sample (NOT applying it to production) and confirming the command builder produces the expected ffmpeg invocation.

### C. Canary seed migration

14. **A new migration `Scripts/SQLScripts/AddCanaryAnchoredProfile_2026-05-30.py`** seeds one Profile row + four ProfileThresholds rows (480p / 720p / 1080p / 2160p) representing the operator's verbatim canary command. The 720p row is the canonical one (TargetBitrateKbps=600, RcLookahead=20, BFrames=4, etc.). The 480p / 1080p / 2160p rows are either (a) populated with reasonable scaled values + `# from: derivation note` citations OR (b) marked NULL on the knobs the canary doesn't address (in which case CommandBuilder reads them from the 720p row OR raises a clear "tier not configured" error -- this directive picks "raise" for safety). Profile name: `NVENC AV1 P7 CANARY VBR -720p`. The pre-existing `NVENC AV1 P7 VBR 30pct -720p` profile is NOT touched by this migration -- it remains percentage-of-source. Verifiable: SELECT confirms the new profile + 720p threshold row exists with the canary's exact values; the existing VBR 30pct profile is unchanged.

15. **Migration is idempotent and uses `# from:` citations** (R2) for every numeric literal. Each citation points to the "Reference canary command" block in `Features/Profiles/nvenc-rate-anchored.feature.md`. Verifiable: R2 hook does not refuse the migration; second run produces zero row diffs.

### D. Schema migration discipline

16. **A new migration `Scripts/SQLScripts/AddCommandBuilderColumns_2026-05-30.py`** adds every column in criteria A.1-A.10. Idempotent (R11). Backfills the four columns whose criteria require backfill (4 / 5 / 6 / 7 / 8) using values that preserve current CommandBuilder behavior byte-for-byte on existing profiles. Verifiable: run twice; second run zero diff. After running, every existing Profile / ProfileThresholds row has non-NULL values on the backfilled columns, and a representative legacy profile's emitted command matches a saved fixture.

17. **The original `Scripts/SQLScripts/AddRateAnchoredColumns.py` and `Scripts/SQLScripts/AddRateAnchoredProfiles.py` are NOT edited.** They are part of production's audit trail. The new migrations are additive and forward-only. Verifiable: `git diff` shows both original migrations untouched.

### E. Documentation closure

18. **The "Reference canary command" section of `Features/Profiles/nvenc-rate-anchored.feature.md` is preserved verbatim** -- the canary command is the seed-row source, and `# from:` citations point at it. Verifiable: grep for `ffmpeg -i c:\myvideo.mkv` in the feature doc returns the canary block intact.

19. **The "Pinned knobs that... currently DIVERGE" audit list is REMOVED** from `Features/Profiles/nvenc-rate-anchored.feature.md`. Divergence is no longer expressible -- the values live in DB columns now, and the canary's values live in a seeded profile row. Verifiable: grep for `currently DIVERGE` returns zero matches.

20. **The feature doc gains a `### Remediation 2026-05-30` block under Status** naming the migration files (criteria 14, 16) and the new profile (`NVENC AV1 P7 CANARY VBR -720p`). The feature doc's `## Scope` Files list is updated to add the new migration files. R14-compliant: no `removed YYYY-MM-DD` lines added. Verifiable: feature doc Status contains the block; Scope lists the new files.

21. **`.claude/standards/index.md` "What is NOT gated" section gains one bullet:** "No hardcoded values where DB-driven is possible -- tunable encoder knobs / thresholds / policy values belong in columns; CommandBuilder + decision functions read, they don't decide. Memory: `feedback_no_hardcoded_values.md`." Verifiable: grep returns the line; the cited memory file exists.

### F. Live canary (the deferred Progress item 6 from the parent feature)

22. **One operator-triggered transcode against `NVENC AV1 P7 CANARY VBR -720p`** has completed end-to-end. Verifiable: `SELECT FfpmpegCommand, NewSize, OriginalSize, VMAF FROM TranscodeAttempts WHERE ProfileName = 'NVENC AV1 P7 CANARY VBR -720p' ORDER BY Id DESC LIMIT 1` returns a row whose command matches the canary in `-rc-lookahead 20`, `-bf 4`, `-b_ref_mode middle`, `-tune hq`, `-multipass fullres`, `-pix_fmt p010le`, `-c:a eac3 -b:a 256k`, `-f mp4`, `-movflags +faststart`, `-b:v 600k -maxrate:v 1200k -bufsize:v 1200k`, `-vf scale=w=1280:h=-1`. NewSize < OriginalSize on the test source (FileReplacement gate passes).

23. **One operator-triggered transcode against an EXISTING profile** (e.g. `NVENC AV1 P7 UHQ CQ32 -720p`) has completed end-to-end and its emitted command is byte-identical to a pre-migration fixture. Verifiable: `TranscodeAttempts.FfpmpegCommand` for a post-migration encode matches a saved pre-migration command for the same profile against the same source. This is the regression check that the column lift + backfill preserved legacy behavior.

## Out of Scope

- Lifting knobs from CQ-anchored profiles' OTHER unique args (e.g. `-cq <Q>`, `-spatial-aq`, `-temporal-aq`) into columns IF they are already represented in code as Profile.Cq or sibling columns. The intent is "knobs the canary names + knobs already hardcoded in the rate-anchored / anime branch." A full audit of every NVENC arg literal in CommandBuilder is a follow-up directive.
- Removing the existing `NVENC AV1 P7 VBR 30pct -720p` / `-480p` profiles. They keep working via the percentage-of-source path (criterion 10).
- Dropping the existing `SourceBitratePercent / Min / Max` columns. They remain operative for percentage-of-source profiles.
- Re-running the systematic shootout (`Scripts/Smoke/NvencRateAndAnime.matrix.json`). Operator declared SKIPPED.
- ContentClassifier rule tuning. Out of scope.
- libsvtav1 (CPU) profile column lifts. This directive is NVENC-scoped; svtav1 profiles' hardcoded knobs are a follow-up.
- Resuming `ceo-mode-enforcement`. That directive remains paused; resumption is its own decision after this remediation ships.

## Constraints

- **Backwards compatibility is non-negotiable.** Every existing profile must emit a byte-identical command after the schema lift + backfill. Verified by criterion 23 against a saved fixture. If a knob lift breaks legacy behavior on an existing profile, the backfill default is wrong, not the lift.
- **No env vars introduced** (R4). All knob values come from DB columns.
- **Directive anchors required** (R15) on every edited function/class in `Models/CommandBuilder.py` and on the new migrations: `# directive: nvenc-rate-anchored-remediation` on the line directly above.
- **Migrations idempotent** (R11), seed values cited (R2).
- **No new `*.feature.md` / `*.flow.md` files** (R13). Documentation updates go in this directive doc and in the existing `nvenc-rate-anchored.feature.md` (per criteria 19 / 20).
- **No `removed YYYY-MM-DD` annotation drift** (R14) when editing the feature doc. Delete sections; don't annotate.

## Escalation Defaults

- Tradeoff between "lift the knob to a column" vs "leave it hardcoded because it's a protocol constant" -> default LIFT unless the value is unambiguously a definitional constant (ffmpeg arg NAME, schema NAME). Operator can override per knob in `Out of Scope`.
- Tradeoff between "one big migration" vs "one schema migration + one seed migration" -> SPLIT (criteria 14 + 16). Schema add is reusable; seed is canary-specific.
- Tradeoff between "raise error on unconfigured tier" vs "fall back to nearest tier" when a knob is NULL in the resolution tier being encoded -> RAISE (criterion 14). Silent fallback hides config gaps; explicit failure surfaces them. The operator decides on a per-knob basis whether NULL means "encoder default" (allowed for criteria 1, 2, 3) or "config gap" (criterion 14's tier-not-configured case for backfilled knobs).
- Risk tolerance: low on legacy regression (constraint above + criterion 23), medium on the canary profile's encode quality (FileReplacement size gate is the safety net).

## Engineering Calls Already Made

- The canary becomes a NEW profile (`NVENC AV1 P7 CANARY VBR -720p`), not an edit of the existing `NVENC AV1 P7 VBR 30pct -720p`. Reason: the two regimes are different (fixed vs percentage); preserving both lets the operator A/B them and avoids destroying production rows that workers may have queued against.
- Backfill discipline (criteria 4 / 5 / 6 / 7 / 8) is the linchpin: it lets the lift be a refactor that preserves byte-for-byte behavior on legacy profiles. Without backfill, the lift would silently change legacy commands. The backfill values are derived by inspecting the current hardcoded CommandBuilder defaults at the moment of the lift -- those are pulled into the migration's INSERT values with `# from: Models/CommandBuilder.py:<line>` citations.
- ScaleHeight + PreserveAspect (criterion 9) is preferred over a more-general `ScaleFilter TEXT` column. Reason: an opaque text column is a config trap; structured columns make the intent legible and let the CommandBuilder fail loudly on impossible combinations.
- The original `AddRateAnchoredColumns.py` / `AddRateAnchoredProfiles.py` stay untouched (criterion 17). Reason: production audit trail. The schema additions in this directive are additive, not corrective.
- Criterion 21 patches the standards index. Reason: the principle that should have caught this miss did not exist anywhere. Adding it as a NAMED operator-reviewed standard is the cheapest insurance against repeating the miss; making it a mechanical R16 is harder (judgment call) and deferred to a future directive if the principle keeps getting violated.

## Status

Active 2026-05-30 -- phase: NEEDS_PLAN -- awaiting operator ratification of criteria. No code changes until criteria are explicitly approved or amended.

### Files

```
.claude/directive.md                                            -- THIS doc
.claude/standards/index.md                                      -- EDIT: criterion 21 named-standard bullet
Features/Profiles/nvenc-rate-anchored.feature.md                -- EDIT: remove audit list (criterion 19), Remediation Status block (criterion 20), Scope file list update
Models/CommandBuilder.py                                        -- EDIT: read every knob from row, no literals for tuning values (criterion 11), no name-based switching (criterion 12)
Scripts/SQLScripts/AddCommandBuilderColumns_2026-05-30.py       -- NEW: schema lift + backfill (criterion 16)
Scripts/SQLScripts/AddCanaryAnchoredProfile_2026-05-30.py       -- NEW: canary seed profile + thresholds (criterion 14)
```

### Verification (filled during VERIFYING phase)

Per criterion -- to be recorded here when each one passes.

### Closure

Closure is gated on all 23 criteria. The paused `ceo-mode-enforcement` directive's resumption is a separate decision.
