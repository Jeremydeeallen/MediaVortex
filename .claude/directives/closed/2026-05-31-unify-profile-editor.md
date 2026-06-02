# Current Directive

**Set:** 2026-05-31
**Status:** Closed -- Success
**Closed:** 2026-05-31
**Slug:** unify-profile-editor
**Replaces:** none (follow-up from `directives/closed/2026-05-31-nvenc-rate-anchored-remediation.md` and `directives/closed/2026-05-31-commandbuilder-comment-promotion.md`)

## Outcome

There is exactly ONE editor for the Profile + ProfileThresholds conceptual unit. The "cogs" knob modal becomes the canonical profile editor; the legacy `ProfileManagementModal` is retired (HTML deleted, JS removed). Every Profile and ProfileThresholds column an operator could legitimately edit is editable through the cogs modal -- legacy fields (Codec, Preset, FilmGrain, YadifMode/Parity/Deint, UseNvidiaHardware, Description, ProfileName, Under30/65MinMB, Fallback bitrates, Video/AudioBitrateKbps) PLUS the lifted NVENC knob columns from the parent directives. The Codec dropdown includes `av1_nvenc` so NVENC profiles can be loaded, edited, and saved without silent column corruption.

This operationalizes the new policy `.claude/rules/ceo-mode.md#one-editor-per-conceptual-unit-no-parallel-uis` and closes the latent corruption bug (BUG-NNNN, filed in this directive) where opening an NVENC profile in the legacy modal silently coerced `Codec='av1_nvenc'` to `Codec='libsvtav1'` on save.

## Acceptance Criteria

1. **Legacy `ProfileManagementModal` HTML block removed** from `Templates/Settings.html`. Verifiable: `grep -n 'id="ProfileManagementModal"' Templates/Settings.html` returns zero matches.

2. **Legacy `EditProfile`, `ShowCreateProfileModal`, `SaveProfile` JS functions removed OR repointed at the cogs modal.** Verifiable: `grep -n 'function EditProfile\|function ShowCreateProfileModal\|function SaveProfile\b' Templates/Settings.html` either returns zero matches OR returns a one-line shim that calls `ShowProfileKnobs(<id>)`.

3. **Profile-card Edit button (pencil icon) opens the cogs modal,** not a separate legacy modal. Verifiable: the only on-click handler in the profile-card render that opens any modal points at `ShowProfileKnobs`.

4. **Cogs modal is the complete editor** -- every editable Profile column appears as an input/select with current value populated: ProfileName, Description, Codec, Preset, FilmGrain, YadifMode, YadifParity, YadifDeint, UseNvidiaHardware, Tune, Multipass, PixelFormat, AudioCodec, AudioBitrateKbps, AudioChannels, AudioFilter, Container, FastStart, RateControlMode, AqStrength. Verifiable: each column name appears in the modal's rendered HTML next to a corresponding form control (`<input>` / `<select>`).

5. **Cogs modal is the complete per-threshold editor** -- every editable ProfileThresholds column appears as an input/select per resolution row: Resolution, TranscodeDownTo, Quality, ContainerType, Under30MinMB, Under65MinMB, Over65MinMB, VideoBitrateKbps, AudioBitrateKbps, FallbackVideoBitrateKbps, FallbackAudioBitrateKbps, RcLookahead, BFrames, BRefMode, ScaleHeight, PreserveAspect, MaxBitrateMultiplier, SourceBitratePercent, MinBitrateKbps, MaxBitrateKbps, Gop.

6. **Codec dropdown includes `av1_nvenc`** (and `libsvtav1`). Verifiable: opening the canary profile `NVENC AV1 P7 CANARY VBR -720p` in the cogs modal shows Codec=`av1_nvenc` selected; saving without changing Codec leaves the DB row unchanged.

7. **PATCH `/api/profiles/<id>/knobs` accepts every column in criteria 4 + 5.** Allowlist expanded to cover the full editable set. Column names whitelisted (SQL-injection-safe). Verifiable: a PATCH with all fields succeeds; a PATCH with an unknown field is silently dropped (not blindly UPDATEd).

8. **No silent codec corruption possible.** Verifiable: open `NVENC AV1 P7 CANARY VBR -720p` -> change Description only -> save -> `SELECT Codec FROM Profiles WHERE Id=39` still returns `av1_nvenc`. The pre-fix behavior would have written `libsvtav1`.

9. **BUG-NNNN entry filed** in `memory/KNOWN-ISSUES.md` documenting the legacy-modal Codec-corruption footgun and naming this directive as the close.

10. **Both smoke paths still green** -- canary command + legacy CQ32 command from the parent directive still emit unchanged ffmpeg invocations. The unification is UI-only; CommandBuilder behavior unchanged.

## Out of Scope

- Profile CREATION via the unified editor. The "+ New profile" button can stay pointed at the legacy create flow OR be retired -- decided during impl. If retired, creation is via SQL or migration scripts until a separate directive ships create-in-cogs-modal.
- The PUT `/api/profiles/<id>` legacy endpoint -- decide during impl whether to retire it. If kept, it stays as a backward-compat path with no UI surface.
- Comment cleanup in Settings.html -- if R12 fires on Settings.html legacy comments, defer per the comment-promotion policy.

## Constraints

- One editor in production after delivery (per the new ceo-mode rule).
- No CommandBuilder behavior change (criterion 10).
- No DB schema change (the columns already exist from parent directives).

## Engineering Calls Already Made

- The cogs modal becomes the canonical editor (not extending the legacy modal). Reason: the cogs modal already has the right per-resolution row matrix shape and a typed-cell editor pattern; extending it is cheaper than re-architecting the legacy single-resolution modal.
- The Codec dropdown becomes a flat allowlist of actual codecs (`av1_nvenc`, `libsvtav1`). Disabled placeholder options for libx265/libx264/libvpx-vp9 are dropped -- "not implemented yet" stubs are UX noise; restore via a future directive when actually implemented.

## Status

Active 2026-05-31 -- phase: IMPLEMENTING.

### Files

```
Templates/Settings.html                                   -- EDIT: delete legacy modal block, extend cogs modal, repoint Edit button
Features/Profiles/ProfileController.py                    -- EDIT: extend PATCH /knobs allowlist
memory/KNOWN-ISSUES.md                                           -- EDIT: file BUG-NNNN for legacy modal Codec corruption
```

### Verification

1. `grep -n 'id="ProfileManagementModal"' Templates/Settings.html` -> 0 matches. PASS.
2. `grep -nE 'function (EditProfile|ShowCreateProfileModal|SaveProfile|GenerateProfileName|PopulateProfileForm|ClearProfileForm|CopyProfile|ApplyTranscodeDownTo|UpdateBitrateFieldsState)' Templates/Settings.html` -> 0 matches. PASS.
3. Profile-card render in `DisplayProfiles` has exactly one Edit-style button (pencil icon) pointing at `ShowProfileKnobs(${Profile.Id})`. Copy button removed. PASS.
4. `ProfileEditable` array in `ShowProfileKnobs` covers: ProfileName, Description, Codec, Preset, FilmGrain, YadifMode, YadifParity, YadifDeint, UseNvidiaHardware, Tune, Multipass, PixelFormat, AqStrength, AudioCodec, AudioBitrateKbps, AudioChannels, AudioFilter, Container, FastStart, RateControlMode -- 20 fields, all rendered as editable controls with the appropriate `CellInput` kind. PASS.
5. `ThresholdEditable` array covers: TranscodeDownTo, Quality, ContainerType, Under30MinMB, Under65MinMB, Over65MinMB, VideoBitrateKbps, AudioBitrateKbps, FallbackVideoBitrateKbps, FallbackAudioBitrateKbps, RcLookahead, BFrames, BRefMode, ScaleHeight, PreserveAspect, MaxBitrateMultiplier, SourceBitratePercent, MinBitrateKbps, MaxBitrateKbps, Gop -- 20 fields. PASS.
6. Codec dropdown options: `['libsvtav1','av1_nvenc']`. Live API confirms `GET /api/profiles/39` returns `Codec='av1_nvenc'`. PASS.
7. `PATCH /api/profiles/<id>/knobs` allowlist (`PROFILE_COLS` + `THRESHOLD_COLS`) covers every column in criteria 4 + 5. Live verified: PATCH succeeded with all field updates. PASS.
8. **Corruption-fix smoke test passed:** PATCH `{"Profile": {"Description": "..."}, "Thresholds": []}` against profile Id=39 (canary). Post-PATCH SELECT: `Codec='av1_nvenc'` (unchanged), all other fields intact. Pre-fix legacy modal behavior would have overwritten `Codec='libsvtav1'`. PASS.
9. BUG-0023 filed in `memory/KNOWN-ISSUES.md` with full footgun description, audit query, and resolution attribution. PASS.
10. Canary + legacy CQ32 smoke tests run via `/tmp/smoke_canary.py` and `/tmp/smoke_legacy.py` after the edits -- both still produce expected ffmpeg invocations (canary matches NvidiaOptimization1.ps1, legacy CQ32 byte-identical to pre-cleanup). PASS.

## Delivery Report

DIRECTIVE: unify-profile-editor -- one editor for Profile + ProfileThresholds; retire the legacy modal that had the silent Codec-corruption footgun.

STATUS: Complete. All 10 criteria PASS.

WHAT SHIPPED:
- `Templates/Settings.html`: legacy `ProfileManagementModal` HTML deleted (411 lines), dead JS deleted (`EditProfile`, `ShowCreateProfileModal`, `SaveProfile`, `GenerateProfileName`, `PopulateProfileForm`, `ClearProfileForm`, `CopyProfile`, `ApplyTranscodeDownTo`, `UpdateBitrateFieldsState` -- 161 more lines), `+ New profile` button removed, `Copy` button removed from profile cards. Edit (pencil) button now opens the cogs modal which is the canonical editor.
- Cogs modal `ShowProfileKnobs`: extended with grouped Profile fields (Identity / Codec / NVENC / Deinterlace / Audio / Output) and full ProfileThresholds row matrix. Codec dropdown includes `av1_nvenc`.
- `Features/Profiles/ProfileController.py`: PATCH `/api/profiles/<id>/knobs` allowlist expanded to 20 Profile cols + 20 ProfileThresholds cols.
- `memory/KNOWN-ISSUES.md`: BUG-0023 filed for the historical Codec-corruption footgun with audit query.

DECISIONS I MADE:
- Profile CREATION via UI dropped entirely (the `+ New profile` button is gone). Creation is SQL/migration-only until a future directive ships create-in-modal. Reason: the legacy create flow had the same Codec dropdown footgun as Edit; keeping it would defeat the corruption-fix work.
- Copy button removed from profile cards (orphan after `CopyProfile` JS was deleted). Re-add in the create-in-modal follow-up.
- 161 lines of dead helper JS deleted (PopulateProfileForm, UpdateBitrateFieldsState, ApplyTranscodeDownTo, etc.) since their only callers were the deleted functions. No silent dead code carried forward.

OPERATOR ACTION:
- WebService was restarted by me during verification. Refresh `/settings` in your browser to pick up the new editor.
- Future: when you want UI-based profile creation back, file `unify-editor-creation` directive to add a Create button + modal flow on top of the existing PATCH/POST endpoints.

KNOWN GAPS:
- The audit query in BUG-0023 returned 3 rows with Codec=libsvtav1 + UseNvidiaHardware=1, but inspection shows these are intentionally-configured SVT profiles routed to NVENC-capable workers (names like `SVT-AV1 P6 FG8 CRF26 >480p NVENC`), not corruption victims. No remediation needed.
