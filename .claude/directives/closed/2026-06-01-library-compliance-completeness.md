# Current Directive

**Set:** 2026-06-01
**Closed:** 2026-06-01
**Status:** Closed -- Abandoned
**Slug:** library-compliance-completeness
**Replaces:** none (new directive)

## Outcome

The `/Activity/LibraryCompliance` panel's Undecided count drops materially from its current ~16,673 (33% of 49,936 MediaFiles). The English-audio detector becomes a best-guess classifier (combined signals) instead of "did ffprobe see the literal `eng` tag." The `HasExplicitEnglishAudio` column keeps its name and binary True/False shape -- only the producer logic changes. The library re-probe naturally repopulates the column via the existing `NeedsReprobe` lane. The post-reprobe residual count becomes the basis for setting concrete acceptability thresholds in a follow-up.

## Acceptance Criteria

1. `Services/FFmpegAnalysisService.SelectPreferredAudioStream` returns `HasExplicitEnglish=True` if ANY of the following hold:
   - Any audio stream has `tags.language` in (`eng`, `en`) (existing rule).
   - Any audio stream has `tags.title` matching `/english|eng/i`.
   - Exactly one audio stream exists and it has no language tag (or tag is empty / `und`).
   - All audio streams are untagged or `und` AND at least one subtitle stream has `tags.language` in (`eng`, `en`).

   Returns `False` otherwise (zero audio streams, OR all audio streams have explicit non-English tags with no English signal above). No NULL return -- column stays binary. Verifiable: `py -c` with five synthetic stream-dict inputs (untagged single-stream, jpn-tagged only, jpn+und mix with English subs, eng-tagged, title="English 5.1") asserts `True, False, True, True, True` respectively.

2. `Repositories/DatabaseManager.SaveMediaFile` write path unchanged. Column type and existing UPDATE clauses stay as-is; no migration. Verifiable: `SELECT data_type, is_nullable FROM information_schema.columns WHERE table_name='mediafiles' AND column_name='hasexplicitenglishaudio'` returns the same shape before and after.

3. `QueueManagementBusinessService._EvaluateCompliance` hard-block on `HasExplicitEnglishAudio IS FALSE` is unchanged. The cascade is not edited; only the producer changes. Verifiable by grep diff on `_EvaluateCompliance` over the directive's commits showing zero changes to that function.

4. **Re-probe drives reclassification.** The operator-run reset (already complete 2026-06-01) left the suspect cohort at `HasExplicitEnglishAudio IS NULL AND IsCompliant IS NULL AND Codec IS NOT NULL`, sized 16,434 rows. After the producer fix from criterion 1 deploys, the existing `GetFilesNeedingProbe` loop processes these via `NeedsReprobe=TRUE`; the upgraded producer reclassifies them on probe completion; the existing `MediaProbeBusinessService` -> `RecomputeForFiles` co-trigger writes `IsCompliant` in the same pass. No backfill script is required.

   Verifiable: after the re-probe pass completes on the cohort, the count from `SELECT COUNT(*) FROM MediaFiles WHERE HasExplicitEnglishAudio IS NULL AND IsCompliant IS NULL AND Codec IS NOT NULL` is materially lower than the starting 16,434 and the rest of the cohort has `HasExplicitEnglishAudio IS NOT NULL` + `IsCompliant IS NOT NULL`. Concrete pass/fail threshold deferred -- operator reviews the residual size and bucket breakdown to decide whether to ship as-is, iterate the producer, or escalate.

5. After the re-probe pass completes on the live library, the count from `SELECT COUNT(*) FROM MediaFiles WHERE IsCompliant IS NULL` is materially lower than the current ~16,673. The exact target threshold is set after this measurement -- the directive captures the before/after delta as evidence; pass/fail on the absolute count is deferred to operator review.

6. The residual Undecided rows fall into exactly three buckets: (a) `SourceIntegratedLufs IS NULL` (awaiting loudness), (b) `Codec IS NULL` (unprobed orphan), (c) `HasExplicitEnglishAudio = FALSE` (correctly identified as non-English by the upgraded producer). Verifiable: SQL bucket query against the post-reset+reprobe state returns 0 rows in an "other" catch-all CASE bucket.

7. Event-driven cascade triggers continue to fire post-fix: a fresh probe of a `HasExplicitEnglishAudio = FALSE` MediaFile via `MediaProbeBusinessService.ProbeFile` produces a row that is either reclassified to TRUE (one of the new signals fires) or stays FALSE with `IsCompliant IS NULL` (genuinely non-English -- operator review), and the cascade write fires either way. Verifiable: new pytest `Tests/Pipeline/test_probe_triggers_compliance_recompute.py` using a new `UndTaggedCandidate` fixture in `Tests/Pipeline/Harness/Fixtures.py` (pinned to one MediaFile.Id selected from `WHERE AudioLanguages = 'und' AND IsCompliant IS NULL` at directive plan time). Test runs in <= 30 seconds, backups + restores the row per existing harness contract.

8. **Adult-content storage root forces `HasExplicitEnglishAudio=TRUE` at producer time.** `SelectPreferredAudioStream` (or its immediate caller in `FFmpegAnalysisService.ParseFFprobeOutput`) short-circuits to `True` for any MediaFile whose `StorageRootId` matches the StorageRoot named `xxx` (currently Id=3, prefix `Z:\`, ~5,678 files). The xxx root id is resolved once by name (single `SELECT Id FROM StorageRoots WHERE Name='xxx'` lookup, cached for the service instance) -- no hardcoded id literal. The cascade `_EvaluateCompliance` is NOT edited (criterion 3 still holds). All write paths (initial probe via `MediaProbeBusinessService`, post-replace via `FileReplacementBusinessService`) inherit the override automatically. Verifiable: direct call to `SelectPreferredAudioStream(streams=[{'tags': {'language': 'jpn'}, ...}], media_file=MediaFile(StorageRootId=<xxx-id>))` returns `HasExplicitEnglish=True`; same call with a non-xxx StorageRootId returns `False`.

Operator can additionally run the one-shot `UPDATE MediaFiles SET HasExplicitEnglishAudio = TRUE WHERE StorageRootId = <xxx-id>;` + `RecomputeForFiles` over those Ids to unblock the existing 5,678 immediately (without waiting for the NeedsReprobe lane to drain).

## Out of Scope

- Periodic / scheduled cascade recompute (the system remains purely event-driven post-fix; the backfill is one-shot).
- Detector changes for non-language audio attributes (channels, bitrate, codec quirks).
- `CleanupOrphanMvPairs.py` lane (BUG-0016 territory -- 51 pre-existing `-mv-mv` on-disk files + 414 zombie DB rows). Separate directive.
- Closure of `compliance-gated-rename` (this directive unblocks one of its open items but does not close the feature; the feature has separate canary work + flow-doc updates).
- I9 worker — it is mid-transcode and stays on its current code per operator instruction. Larry workers redeployed at commit `5530c89` and will pick up this fix on the next deploy.

## Constraints

- No DB schema migration. The `HasExplicitEnglishAudio` column is already nullable BOOLEAN; tri-state is supported at the column level.
- No worker protocol change. The detector lives in `FFmpegAnalysisService` which workers and the WebService share.
- No service restart required to test the detector — it's a per-call function. The backfill runs as an operator script from any host with DB + repo access.
- Backfill must coordinate with live workers per memory `feedback_coordinate_live_worker_writes.md`: Phase 2 writes to `MediaFiles` rows that the queue claim queries read. Use a transaction-per-batch (~1 second hold) so live claims don't observe partial state.

## Escalation Defaults

- Tradeoff: detector "ambiguous" (None) vs "default English" (True) on untagged streams -> None. Reason: True would mis-classify foreign content with stripped tags as English; None lets the cascade decide on other inputs and leaves the operator-review surface honest.
- Tradeoff: backfill rebuilds compliance for all eligible rows vs only the formerly-blocked rows -> all eligible. Reason: one-shot recompute closes any other latent inconsistencies in the column at the same cost.
- Risk tolerance: low. Production data, but read-then-recompute pattern is contained.

## Engineering Calls Already Made

- Binary column kept (no tri-state, no rename, no new column). The producer becomes smarter; the consumer's language hard-block stays; the schema is unchanged. Name decay (`HasExplicitEnglishAudio` no longer means "explicit" only) accepted -- avoiding a 31-file refactor on a column that already has the right shape.
- Z:/xxx adult-content override lives in the producer (not the cascade). Reason: a cascade-level bypass leaves persisted `HasExplicitEnglishAudio` honest-but-misleading, requiring two-place reasoning forever. A producer-level override makes every write path (probe, file-replacement) converge on `True` for xxx-root files automatically -- the operator's quick UPDATE survives re-probe, and any new Z: file gets the same treatment on first probe. Bypass root is resolved by name (`StorageRoots.Name='xxx'`) at service construction -- data-driven, survives Id renumbering.
- Reset + re-probe replaces a dedicated backfill script. The existing `NeedsReprobe` lane is the durable backfill mechanism; one SQL UPDATE is cheaper than a new script + drift surface. Operator ran the reset 2026-06-01 ahead of producer ship; directive owns the producer fix + the post-reprobe verification.
- No new tests in `Tests/Contract/` -- criterion 7 covers the contract via the existing pipeline harness pattern.

## Status

Active 2026-06-01 -- phase: NEEDS_STANDARDS_REVIEW -- pending operator approval of acceptance criteria before advancing to NEEDS_PLAN.

Phases advance by editing this Status line: `**Status:** Active -- phase: <NEXT>`. The PreToolUse hook reads this line to gate tool calls. See `.claude/standards/index.md` for the phase machine.

### Files

```
Services/FFmpegAnalysisService.py                            -- EDIT: SelectPreferredAudioStream best-guess (signals 1-4 in criterion 1) + xxx-root override (criterion 8); load xxx root id by name on service construction
Tests/Pipeline/Harness/Fixtures.py                           -- EDIT: add UndTaggedCandidate fixture
Tests/Pipeline/test_probe_triggers_compliance_recompute.py   -- CREATE: criterion 7 regression test
```

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| no promotions | n/a | directive abandoned -- problem resolved via SQL UPDATE outside code-change scope (see Decisions Made) |

### Verification

(populated at VERIFYING phase)

- **Criterion 1:** `<evidence>`
- **Criterion 2:** `<evidence>`
- **Criterion 3:** `<evidence>`
- **Criterion 4:** `<evidence>`
- **Criterion 5:** `<evidence>`
- **Criterion 6:** `<evidence>`
- **Criterion 7:** `<evidence>`

### Decisions Made

- **Abandoned 2026-06-01:** problem resolved without code changes. Three SQL operations (all run by operator + Claude during 2026-06-01 session):
  1. `UPDATE MediaFiles SET HasExplicitEnglishAudio = TRUE WHERE HasExplicitEnglishAudio IS DISTINCT FROM TRUE` -- 19,169 rows. Removes the cascade's `no_english_audio` hard-block library-wide. Sonarr is configured for English, so default-true is correct ~95% of the time; the operator opts out individual rows that surface playback problems.
  2. `UPDATE MediaFiles SET NeedsReprobe = FALSE WHERE NeedsReprobe = TRUE AND AudioLanguages IS NULL AND StorageRootId IN (1, 2)` -- 14,701 TV + 1,097 movies = 15,798 rows. Prevents the producer (still on the strict `eng`/`en` tag check) from re-classifying back to FALSE on re-probe.
  3. `RecomputeForFiles` over 16,557 Undecided rows with full cascade inputs. Drops `IsCompliant IS NULL` from 16,673 to 988 (-94%).
- No producer change made. The `SelectPreferredAudioStream` heuristic stays single-signal (literal `eng`/`en` tag). Tradeoff accepted: the SQL flip needs periodic re-application if new files arrive with `und`/missing tags, but most ingest goes through Sonarr (English by config), so frequency is low.
- No Z: special-case made. The 521 Z: files without audio streams remain Undecided; they'll be handled by a separate one-shot SQL (`UPDATE … IsCompliant = TRUE WHERE StorageRootId = 3 AND (AudioCodec IS NULL OR AudioCorruptSuspect)`) if/when surfaced as a problem.
- Pipeline-test-harness regression test for the cascade dropped from scope -- the cascade was not edited, so no new test was needed.
