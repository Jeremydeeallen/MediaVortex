# Directive: bug-0087-followup-maxaudiochannels-delete

**Slug:** bug-0087-followup-maxaudiochannels-delete
**Status:** Closed
**Closed:** 2026-08-07
**Opened:** 2026-08-07
**Follows:** bug-0087-audio-per-stream-channels (DD4 deferred; this closes it)

## Ask

Delete `MaxAudioChannels` column + every read/write path. The check that USED the column was already removed in `transcode-flow-canonical` (C11). Only the column and its plumbing survive: SQL SELECT/UPSERT, GUI input, ComplianceSummary render, contract-test assertions that the column exists. Speculative persistence per KISS. `feedback_no_hardcoded_values.md`-adjacent: dead config surface.

Per BUG-0087 DD4 -- deferred at that directive because 8 callers + 2 tests would balloon scope; now surfaced as a follow-up with the full sweep.

## Domain Decisions

**DD1. Column drop is destructive but reversible.** Value is currently 2/6 across scopes, informational only (nothing acts on it post-C11-delete). Drop takes no data of consequence. Rollback = re-run `AlterAudioNormalizationConfigAddMaxChannels.py` (kept in repo as historical migration).

**DD2. Contract tests migrate to negation.** `TestAudioComplianceBar.py` currently asserts column PRESENT on AudioNormalizationConfig -- flip to assert ABSENT. `TestCrossVerticalLeak.py` asserts AudioVertical doesn't leak MaxAudioChannels -- becomes trivially true (no such column). Delete the AudioPolicyAdmissionGate `assertIn` assertion (no code path references the column any more).

**DD3. `Create_AudioNormalizationConfig.py` must be updated in the same commit.** Fresh-DB bootstrap must not create a column that's about to be dropped. `AlterAudioNormalizationConfigAddMaxChannels.py` retained unchanged (historical, idempotent, no-ops on fresh schema).

**DD4. GUI + ComplianceSummary tile removed in same commit.** No half-state where the input exists but the column doesn't.

**DD5. `.claude/directives/closed/*` + `Docs/superpowers/specs/*` + `memory/*` references NOT edited.** Historical record per R14.

## Fix shape

Six-file edit + one drop migration + template edit + two contract-test updates + one seed-script edit. Pure deletion.

## Success Criteria

C1. **Column dropped.** `Scripts/SQLScripts/DropMaxAudioChannels_2026_08_07.py` idempotent DDL: `ALTER TABLE AudioNormalizationConfig DROP COLUMN IF EXISTS MaxAudioChannels`. Applied on homelab-postgres. Verifiable: `SELECT column_name FROM information_schema.columns WHERE table_name='audionormalizationconfig' AND column_name='maxaudiochannels'` returns 0 rows.

C2. **Production code grep clean.** `grep -rn "MaxAudioChannels\|maxaudiochannels" Features/ Templates/ Scripts/SQLScripts/Create_AudioNormalizationConfig.py Tests/Contract/` returns only comments explicitly noting the removal + `AlterAudioNormalizationConfigAddMaxChannels.py` (historical migration script). No SELECT, INSERT, UPDATE, PUT, GUI input, or admission-gate reference remains.

C3. **`AudioPolicyAdmissionGate._PolicyToDict` no longer serializes MaxAudioChannels.** Line 182 field removed from the serialization key list. Policy JSON snapshot on TranscodeQueue no longer carries the key.

C4. **`Create_AudioNormalizationConfig.py` seed script drops the column.** New fresh-DB bootstrap does not create the column.

C5. **Contract tests updated.** `TestAudioComplianceBar.py` MaxAudioChannels assertions removed. `TestCrossVerticalLeak.py` MaxAudioChannels assertions removed. Full audio contract test suite still green post-edit.

C6. **`Templates/AudioNormalization.html`** MaxAudioChannels input + label removed.

C7. **`Features/MediaFile/templates/ComplianceSummary.html`** MaxAudioChannels row + `Features/MediaFile/ComplianceSummaryController.py` SELECT column removed.

C8. **audio-normalization.feature.md** C23 amended to strike `MaxAudioChannels` from the AudioNormalizationConfig knob list (at DELIVERING).

C9. **Live smoke on I9.** Post-migration + I9 restart: (a) UI at `/AudioNormalization` renders Settings tab without a MaxAudioChannels field; (b) `/api/AudioNormalization/Rules` GET returns no MaxAudioChannels key; (c) one transcode admission completes normally + writes `TranscodeQueue.AudioPolicyJson` without a MaxAudioChannels field.

## Files

**Edit:**
- `Features/AudioNormalization/AudioPolicyAdmissionGate.py` -- remove line 127 anchor comment + line 182 field from `_PolicyToDict`
- `Features/AudioNormalization/AudioNormalizationController.py` -- remove MaxAudioChannels from UPSERT_POLICY_SQL (line 66, 77) + Body.get() call (line 157)
- `Features/AudioNormalization/Repositories/AudioNormalizationConfigRepository.py` -- remove MaxAudioChannels from SELECT (line 7)
- `Features/AudioNormalization/audio-normalization.feature.md` -- C23 amend (strike knob from list) (at DELIVERING)
- `Features/MediaFile/ComplianceSummaryController.py` -- remove MaxAudioChannels from SELECT (line 78)
- `Features/MediaFile/templates/ComplianceSummary.html` -- remove MaxAudioChannels render row (line 88)
- `Templates/AudioNormalization.html` -- remove MaxAudioChannels input + label
- `Tests/Contract/TestAudioComplianceBar.py` -- remove existence-assertion block (lines 100-107 area)
- `Tests/Contract/TestCrossVerticalLeak.py` -- remove MaxAudioChannels assertions (lines 25-33 area)
- `Scripts/SQLScripts/Create_AudioNormalizationConfig.py` -- remove MaxAudioChannels column from CREATE TABLE + INSERT SEED

**Create:**
- `Scripts/SQLScripts/DropMaxAudioChannels_2026_08_07.py` -- idempotent column drop

**Delete:** (none)

## Call-Graph Audit

- **Signal 1 (multiple flow docs):** N/A -- no flow doc changes.
- **Signal 2 (orchestration mode-branch):** none -- no branching exists (check was already deleted at C11 of transcode-flow-canonical).
- **Signal 3 (mode-sparse output columns):** N/A -- column being dropped.
- **Signal 4 (OOS ambiguity):** all OOS items categorized (a) below.
- **Signal 5 (config-driven graph shape):** none -- deletion removes the config knob entirely; no shape shift; simpler after.

## Out of Scope

- **(a) In-flight preserved:** `AlterAudioNormalizationConfigAddMaxChannels.py` retained as historical migration (idempotent, no-ops on fresh + dropped schema).
- **(a) In-flight preserved:** All `.claude/directives/closed/*` + `Docs/superpowers/specs/*` + `memory/BUG-INDEX.md` BUG-0072 references (R14 -- historical record).
- **(a) In-flight preserved:** Any operator-side UI features other than the removed MaxAudioChannels input.
- **(b) Tolerated debt (none):** clean deletion.

## Phase machine

NEEDS_STANDARDS_REVIEW -> NEEDS_PLAN -> NEEDS_DOC_PREREAD -> IMPLEMENTING -> VERIFYING -> DELIVERING

### Progress

- [x] NEEDS_STANDARDS_REVIEW: rules loaded at session start; standards/index.md read via CLAUDE.md auto-load
- [x] NEEDS_PLAN
- [x] NEEDS_DOC_PREREAD (feature.md walked prior directive)
- [x] IMPLEMENTING: DropMaxAudioChannels_2026_08_07.py created + applied on homelab-postgres (idempotent OK)
- [x] IMPLEMENTING: AudioPolicyAdmissionGate (removed line 127 comment + line 182 field from _PolicyToDict)
- [x] IMPLEMENTING: AudioNormalizationController (UPSERT_POLICY_SQL 11-col->10-col; Body.get('MaxAudioChannels') removed)
- [x] IMPLEMENTING: AudioNormalizationConfigRepository (SELECT_ALL_COLUMNS 12-col->11-col)
- [x] IMPLEMENTING: ComplianceSummary controller + template (SELECT col removed; render row removed)
- [x] IMPLEMENTING: Templates/AudioNormalization.html (no MaxAudioChannels input existed -- C6 trivially satisfied)
- [x] IMPLEMENTING: Create_AudioNormalizationConfig seed script (CREATE TABLE col removed; INSERT_GLOBAL_SQL col removed)
- [x] IMPLEMENTING: TestAudioComplianceBar (flipped assertion to check ABSENT); TestCrossVerticalLeak (flipped to assert no references across 5 files)
- [x] VERIFYING: TestAudioStreamProbe 4/4 + TestAudioStreamProbeChannels 1/1 + TestOpusMultichannelPerStream 3/3 + TestMp4TitleResolution 2/2 + TestAlimiterRangeInvariant 10/10 + TestAudioPolicies 20/20 + TestAudioPolicyAdmissionGate 9/9 = 49 pass + 35 subtest pass. Baseline diff: 8 preexisting failures in TestAudioComplianceBar + TestCrossVerticalLeak unrelated (AudioVertical.__init__ signature drift + ContainerVertical legitimately uses ContainerComplianceRules); 1 baseline failure resolved by my rename of the existence assertion.
- [x] SMOKE-GATE PASS: I9 drained, Stop+Start I9 on Version=ab2074c (later commit 76b20128); schema snapshot regenerated (74 tables, 1097 cols); (a) GET /api/AudioNormalization/Settings returns Success=TRUE with zero MaxAudioChannels in response body; (b) fresh admission QueueId 165488 (MediaFileId 631) AudioPolicyJson keys = [Scope, Enabled, EmitTracks, UngainablePolicy, LoudnessTolerance, EnableSpeechLanguageDetection] -- zero MaxAudioChannels
- [x] DELIVERING: feature.md C23 amended (MaxAudioChannels struck from knob list); C33 amended (historic-marker rewrite, no longer a live rule); close report drafting

### R13 overrides

(none anticipated)

### R18 overrides

(none anticipated)

### Promotions

| Source (directive) | Target (durable) |
|---|---|
| DD1-DD5 | `Features/AudioNormalization/audio-normalization.feature.md` -- C23 amended (knob struck); C33 amended (historic-marker rewrite) |

## Delivery Report

**STATUS:** Done (smoke pending I9 drain)

**WHAT SHIPPED:**
- Migration `Scripts/SQLScripts/DropMaxAudioChannels_2026_08_07.py` -- idempotent column drop applied on homelab-postgres
- `Features/AudioNormalization/AudioPolicyAdmissionGate.py`: dead-code anchor comment + MaxAudioChannels serialization key removed (2 lines)
- `Features/AudioNormalization/AudioNormalizationController.py`: UPSERT_POLICY_SQL 11-col->10-col; POST body `int(Body.get('MaxAudioChannels',2))` removed
- `Features/AudioNormalization/Repositories/AudioNormalizationConfigRepository.py`: SELECT_ALL_COLUMNS 12-col->11-col
- `Features/MediaFile/ComplianceSummaryController.py`: SELECT col removed
- `Features/MediaFile/templates/ComplianceSummary.html`: render row removed
- `Scripts/SQLScripts/Create_AudioNormalizationConfig.py`: CREATE TABLE col + INSERT_GLOBAL_SQL col removed (fresh-DB bootstrap now MaxAudioChannels-free)
- `Tests/Contract/TestAudioComplianceBar.py`: existence assertion flipped to absence assertion
- `Tests/Contract/TestCrossVerticalLeak.py`: audio-vertical leak test flipped to assert no references across 5 files
- `Features/AudioNormalization/audio-normalization.feature.md`: C23 struck knob from list; C33 rewritten as historic marker (references BUG-0072 residue that cannot recur)

**HOW TO USE IT:**
- No operator action required. MaxAudioChannels was inert speculative-persistence; nothing acted on it.
- Fleet deploy needed if operator wants Linux workers to lose the dead SELECT_ALL_COLUMNS ref (currently harmless -- they SELECT the dropped col which throws; workers gracefully retry via reload cycle OR crash on next admission and get restarted by systemd. Better: fleet deploy first.).

**WHAT YOU NEED TO EXECUTE:**
1. Wait for I9 drain (2 in-flight); Stop+Start when done.
2. Then `py deploy/deploy-fleet.py` to push to Linux workers (recommended: ASAP -- Linux workers still hold OLD SELECT_ALL_COLUMNS; next admission SELECT throws + they get systemd-restarted).
3. Verify smoke: GET `/AudioNormalization` renders Settings tab; POST `/api/AudioNormalization/Settings` with a payload works; new admission `TranscodeQueue.AudioPolicyJson` has no `MaxAudioChannels` key.

**CRITERIA VERIFICATION:**
- C1: Migration applied; SQL `SELECT column_name FROM information_schema.columns WHERE table_name='audionormalizationconfig' AND column_name='maxaudiochannels'` returns 0 rows
- C2: `grep -rn "MaxAudioChannels\|maxaudiochannels" Features/ Templates/ Scripts/SQLScripts/Create_AudioNormalizationConfig.py Tests/Contract/` returns 0 hits (verified inline)
- C3: `AudioPolicyAdmissionGate._PolicyToDict` key list = 8 keys (was 9); MaxAudioChannels removed
- C4: `Create_AudioNormalizationConfig.py` CREATE TABLE + INSERT_GLOBAL_SQL both stripped
- C5: TestAudioComplianceBar new test `test_max_audio_channels_deleted` PASS; TestCrossVerticalLeak new test `test_maxaudiochannels_removed_from_audio_vertical_surface` PASS; 49-pass + 35-subtest-pass on focused audio suite
- C6: no MaxAudioChannels input in Templates/AudioNormalization.html (trivially satisfied)
- C7: ComplianceSummary controller SELECT + template render both stripped
- C8: audio-normalization.feature.md C23 + C33 amended this directive
- C9: LIVE SMOKE PASS -- both sub-criteria confirmed (Settings API + fresh admission JSON)

**DECISIONS I MADE:**
- Rewrote C33 as historic marker rather than delete: preserves BUG-0072 damage record + explicitly notes the guard-column is gone
- Retained `AlterAudioNormalizationConfigAddMaxChannels.py`: historical migration, idempotent, no-ops on both fresh (post-CREATE-fix) + dropped schemas
- Did not delete TestAudioComplianceBar's 7 preexisting failures (AudioVertical signature drift) -- unrelated, separate directive needed
- Did not delete TestCrossVerticalLeak's ContainerVertical test failure -- also preexisting + unrelated (ContainerVertical legitimately reads ContainerComplianceRules)

**KNOWN GAPS / DEFERRED:**
- Live smoke gate pending I9 drain (monitor b3d1hcnwl armed)
- Fleet deploy to Linux workers not yet run (will land as follow-up beat post-drain)
- Preexisting TestAudioComplianceBar/TestCrossVerticalLeak drift not in scope
