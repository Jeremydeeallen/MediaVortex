# Current Directive

**Set:** 2026-06-09
**Status:** Active -- phase: DELIVERING
**Slug:** compliance-solid-refactor
**Interrupts:** local-staging (paused at `.claude/directives/paused/2026-06-09-local-staging.md`; resume by un-pausing after this closes)

## Outcome

Replace the monolithic `QueueManagementBusinessService._EvaluateCompliance` cascade (150-line if/elif inside a 2,064 LOC service with 7 concerns -- BUG-0028) with a data-driven, SOLID-decomposed compliance engine that lives in its own vertical at `Features/Compliance/`. Three guarantees:

1. **Data-driven rules.** Each operation (Transcode, Remux, AudioFix, SubtitleFix) and the hard-block Gates have a dedicated single-row scalar config table (typed columns -- same pattern as `QueueAdmissionConfig`, `PostTranscodeGateConfig`, `LocalStagingConfig`). Operator tunes thresholds, whitelists, and enable/disable flags via GUI without code changes.
2. **GUI for tweaking.** New `/settings` "Compliance Rules" collapsible card; one section per operation + one for Gates. Each section binds to its rule table columns. Save flips the table; next compliance evaluation honors the new values (db-is-authority).
3. **Bucketed prioritization, materialized.** `MediaFiles.WorkBucket` enum column derived from the decision:
   - `'Transcode'` -- needs Transcode AND/OR Remux AND/OR AudioFix (a)
   - `'Remux'` -- needs Remux AND/OR AudioFix, NOT Transcode (b)
   - `'AudioFixOnly'` -- needs AudioFix only (c)
   - `'SubtitleFixOnly'` -- needs SubtitleFix only
   - `NULL` -- compliant OR undecidable (gate-blocked)

The new vertical owns ONE public entry: `ComplianceEvaluator.Evaluate(MediaFile, EffectiveProfile) -> ComplianceDecision`. Every consumer (recompute hooks, queue admission, SmartPopulate, Activity widget) calls this single function. The old `_EvaluateCompliance` method is deleted; `transcode-vs-remux-routing.feature.md` retires its C11 cascade prose in favor of a pointer to the new `compliance.feature.md`.

## Concern

Five concerns motivate this work:

1. **`QueueManagementBusinessService` is BUG-0028.** 2,064 LOC, 7 concerns, hard to test, hard to extend. Compliance evaluation lives 1,500 lines deep inside a class that also does queue population, priority calc, recompute, job add/remove, statistics, and subtitle-fix population. SRP violation; OCP violation (any rule change requires editing a method full of if/elifs); ISP violation (callers depending on QMBS for compliance evaluation drag in queue management).

2. **Compliance rules are hardcoded.** Acceptable video codecs `{h264, hevc, av1}`, audio codecs `{aac, ac3, eac3, mp3}`, container set, audio LUFS tolerance, savings threshold -- all live as Python literals or in scattered tables (`CodecCompatibility`, `QueueAdmissionConfig`). No single place an operator can edit one rule and see the effect. The operator-facing memory `feedback_no_hardcoded_values.md` is the standing instruction; this directive operationalizes it for compliance.

3. **The "anything else?" question is unanswered.** Today's `RecommendedMode` enum is `{'Transcode', 'Remux', 'AudioFix', NULL}` -- but the cascade evaluates them as a flat if/elif chain that short-circuits at the first hit. A file that needs BOTH a container fix AND a loudnorm pass is bucketed as `'Remux'` (since Remux subsumes audio), but a file that needs ONLY a loudnorm pass goes to `'AudioFix'`. The decision logic is correct; the data model isn't expressive enough. We need a `OperationsNeeded: set` plus a derived `WorkBucket` so the operator can see "this file needs {AudioFix} only" vs "this file needs {Remux, AudioFix}" without re-deriving from the cascade.

4. **SubtitleFix is orphaned.** `ProcessingMode='SubtitleFix'` exists; `PopulateQueueForSubtitleFix` exists. But the cascade never proposes it -- it's manual-only. Bringing SubtitleFix into the compliance engine with its own rule table (e.g. "ASS/SSA subtitles in MP4 container -> convert to mov_text") lets it ride the same auto-detection rails.

5. **Operator visibility is poor.** Today, "why was this file flagged non-compliant?" requires reading source. The new `ComplianceDecision` carries a structured `Reasons: list[(Rule, Operator, Actual, Threshold)]` trace; the GUI surfaces it; debugging stops requiring grep.

## Acceptance Criteria

### A. Schema (data-driven, normalized, idempotent)

C1. Five new single-row scalar config tables exist via idempotent migration `Scripts/SQLScripts/AddComplianceRuleTables.py`: `TranscodeRules`, `RemuxRules`, `AudioFixRules`, `SubtitleFixRules`, `ComplianceGates`. Each follows the existing pattern (`Id INT PRIMARY KEY DEFAULT 1`, `LastUpdated TIMESTAMP DEFAULT NOW()`, `CHECK (Id = 1)`). Columns are typed (BOOLEAN / INT / TEXT / TEXT-csv) -- no JSONB. Each table seeds one row with operator-defaults via `INSERT ... ON CONFLICT DO NOTHING`. Verifiable: `\d TranscodeRules`, etc., show the schema; `SELECT * FROM TranscodeRules` returns one row; re-running the script is a no-op (R11).

C2. **TranscodeRules columns** (initial set): `ResolutionExceedsProfileTarget BOOLEAN NOT NULL DEFAULT TRUE`, `AcceptableVideoCodecsCsv TEXT NOT NULL DEFAULT 'h264,hevc,av1'`, `EstimatedSavingsMBThreshold INT NOT NULL DEFAULT 150` (mirrors `QueueAdmissionConfig.MinTranscodeSavingsMB` -- this directive does NOT duplicate the value; instead the column is dropped at DELIVERING from `QueueAdmissionConfig` and moved here, where it semantically belongs). Verifiable: SELECT each column returns the seed value; mid-flight UPDATE to one column changes the next compliance evaluation's transcode decision.

C3. **RemuxRules columns**: `AcceptableContainersCsv TEXT NOT NULL DEFAULT 'mp4,mov,m4v'`, `AcceptableAudioCodecsMp4Csv TEXT NOT NULL DEFAULT 'aac,ac3,eac3,mp3'`, `RequireAudioNormalized BOOLEAN NOT NULL DEFAULT TRUE`. Supersedes `CodecCompatibility` rows for `Kind='Container'` and `Kind='AudioCodecMp4'`. Migration deletes those rows at DELIVERING; the `CodecCompatibility` table is retained only if `Kind='VideoCodec'` rows remain in use (else dropped).

C4. **AudioFixRules columns**: `TargetLoudnessLufs INT NOT NULL DEFAULT -23`, `ToleranceLufs DOUBLE PRECISION NOT NULL DEFAULT 1.0`, `RequireLufsMeasured BOOLEAN NOT NULL DEFAULT TRUE`. Reads existing `MediaFiles.SourceIntegratedLufs` for the off-target predicate; honors `MediaFiles.AudioComplete=TRUE` as already-normalized (no re-evaluation).

C5. **SubtitleFixRules columns**: `Enabled BOOLEAN NOT NULL DEFAULT FALSE` (defaults OFF -- operator opts in once the SubtitleFix queue path proves stable), `MovTextRequiredForMp4 BOOLEAN NOT NULL DEFAULT TRUE`, `NonNativeSubtitleFormatsCsv TEXT NOT NULL DEFAULT 'ass,ssa,vobsub'`, `RequireForcedSubtitlesPresent BOOLEAN NOT NULL DEFAULT TRUE` (operator-facing motivating case: forced subtitle tracks on foreign-language scenes -- LOTR Elvish, Star Trek Klingon, anime overlay text). When `TRUE`, the SubtitleFix operation proposes itself only when `MediaFiles.HasForcedSubtitles = TRUE`; when `FALSE`, the operation fires on any incompatible-format subtitle in an MP4. A `NULL` `HasForcedSubtitles` value (pre-probe-extension row) is treated as undecidable for SubtitleFix and the operation does not propose itself until reprobe populates the column.

C5b. **Forced-subtitle probe extension.** `MediaProbeBusinessService._ExecuteProbe` (file 13) reads each subtitle stream's `Disposition.forced` value during probe and aggregates: `HasForcedSubtitles = TRUE` if any stream's `forced` is `1`; `FALSE` if probe ran but no stream is flagged; `NULL` if probe has not yet captured the field (legacy rows). Backfill is operator-driven via the existing `POST /api/MediaProbe/Reprobe` endpoint. Verifiable: probe a forced-subs MKV -> `HasForcedSubtitles = TRUE`; probe one without forced flag -> `FALSE`; pre-extension rows still `NULL` until reprobe. **Sequencing note**: lands in Batch 2 (worker-redeploy batch).

C6. **ComplianceGates columns** (hard-blocks; `NULL` decision when any gate fires): `RequireExplicitEnglishAudio BOOLEAN NOT NULL DEFAULT TRUE`, `BlockOnAudioCorruptSuspect BOOLEAN NOT NULL DEFAULT TRUE`, `RequireAudioStream BOOLEAN NOT NULL DEFAULT TRUE`, `RequireLoudnessMeasurements BOOLEAN NOT NULL DEFAULT TRUE`, `RequireProbeMetadata BOOLEAN NOT NULL DEFAULT TRUE`, `RequireEffectiveProfile BOOLEAN NOT NULL DEFAULT TRUE`, `RequireResolutionCategory BOOLEAN NOT NULL DEFAULT TRUE`, `RequireProfileThresholds BOOLEAN NOT NULL DEFAULT TRUE`. Each gate maps 1:1 to a current undecidable-return path in `_EvaluateCompliance`. Operator can disable a gate (e.g. accept files without English audio) -- the engine then evaluates them like any other.

C7. **MediaFiles schema extensions** via idempotent migration `Scripts/SQLScripts/AddWorkBucketColumn.py`: `WorkBucket TEXT NULL` (enum-string: `'Transcode' | 'Remux' | 'AudioFixOnly' | 'SubtitleFixOnly' | NULL`), `OperationsNeededCsv TEXT NULL` (set-as-csv: e.g. `'Remux,AudioFix'`), `ComplianceGateBlocked TEXT NULL` (gate name when undecidable, NULL otherwise), `ComplianceEvaluatedAt TIMESTAMP NULL`, `HasForcedSubtitles BOOLEAN NULL` (populated by C5b probe extension; NULL = pre-extension data). Verifiable: `\d MediaFiles` shows the five columns; running the script twice is a no-op.

### B. SOLID decomposition (SRP / OCP / LSP / ISP / DIP)

C8. **New `Features/Compliance/` vertical.** One concern, one module:

| File | Concern | SOLID anchor |
|---|---|---|
| `Features/Compliance/ComplianceController.py` | HTTP endpoints for the GUI (GET/PUT per rule table; POST recompute) | SRP: HTTP only |
| `Features/Compliance/Services/ComplianceEvaluator.py` | SOLE public entry: `Evaluate(MediaFile, EffectiveProfile) -> ComplianceDecision` | SRP: orchestration only; DIP: depends on `IComplianceOperation`s + `IComplianceGate`s, not implementations |
| `Features/Compliance/Services/ComplianceGateChain.py` | Apply gates in order; first failing gate short-circuits with undecidable | SRP: gate dispatch only |
| `Features/Compliance/Services/ComplianceRuleEngine.py` | Run each registered `IComplianceOperation` and collect results | SRP: rule dispatch only; OCP: registry-driven, no edits to add a new op |
| `Features/Compliance/Services/ComplianceBucketResolver.py` | Map `OperationsNeeded: set[str]` -> `WorkBucket: str` | SRP: derivation only; pure function |
| `Features/Compliance/Operations/IComplianceOperation.py` | Abstract: `Name`, `LoadRules(repo)`, `EvaluatesFor(decision_in_progress) -> bool`, `Apply(MediaFile, EffectiveProfile, rules) -> OperationResult` | ISP: tiny interface |
| `Features/Compliance/Operations/TranscodeOperation.py` | One impl of `IComplianceOperation` | LSP: interchangeable from engine's view |
| `Features/Compliance/Operations/RemuxOperation.py` | Same | LSP |
| `Features/Compliance/Operations/AudioFixOperation.py` | Same | LSP |
| `Features/Compliance/Operations/SubtitleFixOperation.py` | Same | LSP |
| `Features/Compliance/Gates/IComplianceGate.py` | Abstract: `Name`, `IsEnabled(gates_row) -> bool`, `Blocks(MediaFile) -> bool` | ISP |
| `Features/Compliance/Gates/*.py` | One impl per gate (EnglishAudio, AudioCorruptSuspect, AudioStream, LoudnessMeasurements, ProbeMetadata, EffectiveProfile, ResolutionCategory, ProfileThresholds) | LSP / SRP |
| `Features/Compliance/Repositories/TranscodeRulesRepository.py` | CRUD for `TranscodeRules`; mirror of `QueueAdmissionConfigRepository` shape | SRP: one table |
| `Features/Compliance/Repositories/RemuxRulesRepository.py` | Same | SRP |
| `Features/Compliance/Repositories/AudioFixRulesRepository.py` | Same | SRP |
| `Features/Compliance/Repositories/SubtitleFixRulesRepository.py` | Same | SRP |
| `Features/Compliance/Repositories/ComplianceGatesRepository.py` | Same | SRP |
| `Features/Compliance/Models/ComplianceDecision.py` | Immutable dataclass: `IsCompliant, OperationsNeeded, WorkBucket, GateBlocked, Reasons` | SRP: shape only |
| `Features/Compliance/Models/OperationResult.py` | `OperationName, Applies, Reasons[(Rule, Operator, Actual, Threshold)]` | SRP: shape only |

C9. **`QueueManagementBusinessService._EvaluateCompliance` is deleted.** Every caller is migrated to `ComplianceEvaluator.Evaluate`. `QueueManagementBusinessService` loses the compliance concern. Verifiable: `grep -rn '_EvaluateCompliance\|EvaluateCompliance' --include='*.py'` returns zero matches outside `Features/Compliance/`. **Sequencing note**: lands in Batch 2 because `MediaProbeBusinessService` and `FileReplacementBusinessService` (worker-context loaders) must be migrated in the same commit; workers drain + redeploy before this lands.

C10. **R19 path.** No edits to `Repositories/DatabaseManager.py`. New repositories live under `Features/Compliance/Repositories/` per the vertical-slice pattern.

C11. **DIP enforcement.** `ComplianceEvaluator` accepts its dependencies via constructor: `def __init__(self, OperationRegistry, GateChain, BucketResolver)`. Wiring lives in a single composition root `Features/Compliance/ComplianceComposition.py` that builds the registry from the per-operation classes. No service does `from Features.Compliance.Operations.TranscodeOperation import TranscodeOperation` inside its own body.

C12. **No cached config.** Every `*RulesRepository.Get()` reads fresh from DB per call (R3 + db-is-authority). `ComplianceEvaluator.Evaluate` accepts an optional pre-loaded `RuleCache` arg for tight loops (bulk recompute) -- the cache is built ONCE at the top of `RecomputeForFiles` and passed down. Verifiable: contract test exercises mid-flight UPDATE to a rule table during bulk recompute -- the cached path uses the snapshot (correct: bulk operations want stability), the non-cached path uses the new value.

### C. Decision shape (observable, debuggable)

C13. `ComplianceDecision` is an immutable dataclass with five fields:
- `IsCompliant: Optional[bool]` -- `True` / `False` / `None` (gate-blocked)
- `OperationsNeeded: frozenset[str]` -- subset of `{'Transcode','Remux','AudioFix','SubtitleFix'}`
- `WorkBucket: Optional[str]` -- `'Transcode'` / `'Remux'` / `'AudioFixOnly'` / `'SubtitleFixOnly'` / `None`
- `GateBlocked: Optional[str]` -- gate name (e.g. `'EnglishAudio'`, `'LoudnessMeasurements'`) when `IsCompliant is None`; `None` otherwise
- `Reasons: list[ReasonRow]` -- per-rule trace: `(OperationName, RuleName, Operator, ActualValue, ThresholdValue, Applies: bool)`

C14. **Bucket derivation rules** (pure, in `ComplianceBucketResolver`):
- `OperationsNeeded == set()` -> `WorkBucket = None`, `IsCompliant = True`
- `'Transcode' in OperationsNeeded` -> `WorkBucket = 'Transcode'`, `IsCompliant = False`
- `'Remux' in OperationsNeeded and 'Transcode' not in OperationsNeeded` -> `WorkBucket = 'Remux'`, `IsCompliant = False`
- `OperationsNeeded == {'AudioFix'}` -> `WorkBucket = 'AudioFixOnly'`, `IsCompliant = False`
- `OperationsNeeded == {'SubtitleFix'}` -> `WorkBucket = 'SubtitleFixOnly'`, `IsCompliant = False`
- `OperationsNeeded == {'AudioFix','SubtitleFix'}` -> `WorkBucket = 'AudioFixOnly'` (audio takes precedence; subtitle ride-along when remux runs anyway). **Open question** -- if no other op routes the file, what tab claims it? Surface for operator review at DELIVERING.

C15. **`MediaFiles.RecommendedMode` retired.** The column is dropped at DELIVERING after every consumer migrates to `MediaFiles.WorkBucket`. Migration `Scripts/SQLScripts/DropRecommendedModeColumn.py` is idempotent. Verifiable: `grep -rn 'RecommendedMode' --include='*.py'` returns zero matches at DELIVERING.

### D. GUI (`/settings` "Compliance Rules" card)

C16. New collapsible card on `/settings`, patterned on the existing "Queue admission" card (`Templates/Settings.html:356-427`). Five sub-sections: Transcode, Remux, AudioFix, SubtitleFix, Gates. Each renders its table's columns as labeled form inputs with appropriate widget per type (checkbox for BOOLEAN, number for INT/DOUBLE, comma-separated text for CSV). Lazy-loads on `shown.bs.collapse`. Verifiable: open the card, edit one Transcode rule, save, observe `LastUpdated` advances and the next bulk recompute reflects the new value.

C17. **Live preview before save.** Each section has a "Preview impact" button that runs a dry recompute (no DB writes) against a sample of 1,000 random `MediaFiles` rows and shows: how many files newly flagged compliant, how many newly flagged non-compliant, breakdown by `WorkBucket`. Operator sees "if I lower `EstimatedSavingsMBThreshold` from 150 to 100, 743 files move from compliant -> Transcode bucket." Saves only after operator confirms.

C18. Save endpoints follow `{Success, Message|Error, Data}` envelope (CLAUDE.md). Each section saves to its own endpoint -- saves are independent; you don't need to re-submit AudioFix when editing Transcode.

C19. The card also surfaces a per-`WorkBucket` count (live from `SELECT WorkBucket, COUNT(*) FROM MediaFiles GROUP BY 1`) so the operator sees the library-wide effect of past rule changes without leaving the page.

### E. Bucketed prioritization (user's a/b/c)

C20. **Existing queue surfaces route by `WorkBucket`, not `RecommendedMode`.** Migrate every reader:
- `NextTranscodeBatch` (TV + Movies Next Batch cards): WHERE `WorkBucket = 'Transcode'`
- `SmartPopulateQueue(Mode='Remux')`: WHERE `WorkBucket = 'Remux'`
- `SmartPopulateQueue(Mode='AudioFix')`: WHERE `WorkBucket = 'AudioFixOnly'`
- (New) `SmartPopulateQueue(Mode='SubtitleFix')`: WHERE `WorkBucket = 'SubtitleFixOnly'`
- Activity compliance widget: GROUP BY `WorkBucket`.

C21. **Claim contract unchanged.** Worker claim order is owned by `queue-priority.feature.md` (largest non-compliant first; 195-200 override window). This directive does NOT touch claim ORDER BY; it only changes what enters the queue and how the tabs are populated.

C22. **`NeedsTranscode` / `NeedsQuick` materialized columns retired.** They were derived from `RecommendedMode`; with `WorkBucket` materialized, they're redundant. Dropped via `Scripts/SQLScripts/DropNeedsFlags.py` at DELIVERING after every reader migrates to `WorkBucket`. Verifiable: `grep -rn 'NeedsTranscode\|NeedsQuick' --include='*.py'` returns zero matches at DELIVERING.

### F. Recompute, indexes, observability

C23. **`RecomputeForFiles(MediaFileIds)` is the only writer of `WorkBucket` / `OperationsNeededCsv` / `ComplianceGateBlocked` / `ComplianceEvaluatedAt`.** The function builds the rule cache once, then loops calling `ComplianceEvaluator.Evaluate` per row. One bulk UPDATE writes all four columns. Triggers unchanged: probe completion, FileReplacement post-flight, AssignedProfile bulk-update, admin recompute endpoint.

C24. **Partial indexes for each bucket** via idempotent migration `Scripts/SQLScripts/AddWorkBucketIndexes.py`:
- `CREATE INDEX IF NOT EXISTS idx_mediafiles_wb_transcode ON MediaFiles (SizeMB DESC NULLS LAST) WHERE WorkBucket = 'Transcode' AND HasExplicitEnglishAudio IS NOT FALSE`
- (analogous for Remux, AudioFixOnly, SubtitleFixOnly)
Verifiable: `EXPLAIN ANALYZE` on each card's query shows `Index Scan` not `Seq Scan`.

C25. **Backfill script** `Scripts/SQLScripts/BackfillWorkBucket.py` walks the full library in batches, runs `RecomputeForFiles`, logs progress every 1000 rows. Idempotent, batched, `--dry-run` and `--limit` flags. Verifiable on dev DB: `SELECT WorkBucket IS NOT NULL OR ComplianceGateBlocked IS NOT NULL` is `TRUE` for every row after backfill.

C26. **Contract tests** under `Tests/Contract/TestComplianceEngine.py` (R8): one test per gate, one test per operation (each gate-blocked path + each `WorkBucket` outcome). Each test seeds a `MediaFiles` row and an `EffectiveProfile`, calls `Evaluate`, asserts the `ComplianceDecision`. Mid-flight rule-table UPDATE is exercised at least once (no caching at the non-bulk entry point). SubtitleFix-specific cases:
- Forced-subs in MP4 with non-mov_text format, `Enabled=TRUE`, `RequireForcedSubtitlesPresent=TRUE` -> `WorkBucket='SubtitleFixOnly'` (when no other op fires).
- Non-forced subs in MP4 with non-mov_text format, `Enabled=TRUE`, `RequireForcedSubtitlesPresent=TRUE` -> SubtitleFix NOT proposed; bucket reflects other ops.
- Non-forced subs in MP4, `Enabled=TRUE`, `RequireForcedSubtitlesPresent=FALSE` -> SubtitleFix proposed.
- `HasForcedSubtitles=NULL` (pre-extension), `Enabled=TRUE`, `RequireForcedSubtitlesPresent=TRUE` -> SubtitleFix NOT proposed (undecidable input).

## Out of Scope

- **Touching the worker claim path.** Claim order is owned by `queue-priority.feature.md` and was just shipped. This directive does not edit `TranscodeQueueRepository.ClaimNextPendingTranscodeJob`.
- **Per-show rule overrides.** Today rules are library-wide. A per-show override (e.g. "this anime show wants AV1 with film-grain regardless of savings") is a follow-up. Defer.
- **VMAF / quality-floor integration.** Quality-test feedback into compliance is the paused `quality-floor-lift` directive's territory. Resume that after this closes.
- **CodecCompatibility table redesign for video codecs.** The `Kind='VideoCodec'` rows remain consulted by the Transcode operation via the new `TranscodeRules.AcceptableVideoCodecsCsv` column. Migration deletes `Kind='Container'` and `Kind='AudioCodecMp4'` rows only.
- **Removing `MediaFiles.AssignedProfile` denormalization.** Still used by the priority/claim paths and the SmartPopulate readers. Compliance reads through it via the cascade.
- **The 2,064 LOC QueueManagementBusinessService cleanup beyond compliance extraction.** This directive removes one concern (~150 LOC). The other six (BUG-0028 items 2-6) stay deferred.

## Constraints

- **db-is-authority** (`.claude/rules/db-is-authority.md`): every `*RulesRepository.Get()` reads fresh per call. `ComplianceEvaluator` accepts an optional pre-loaded cache for bulk recompute only.
- **R3**: no `self._cached_*` in any new service / repository.
- **R5**: `ExecuteQuery` for SELECT only; INSERT/UPDATE/DELETE via `ExecuteNonQuery`.
- **R9**: no LIKE queries expected; if any added, `EscapeLikePattern` in the same function.
- **R10**: no `Claim*` additions. None planned.
- **R11**: every migration uses `ADD COLUMN IF NOT EXISTS` / `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS` / `INSERT ... ON CONFLICT DO NOTHING`.
- **R12**: single-line comments only; no docstrings > 1 line; no module-level docstrings; no triple-quoted SQL. **Details belong in feature/flow docs**, not in code comments. Edit-region scope -- preexisting triple-quoted SQL in edited files is preserved by keeping it outside the edit region.
- **R13**: new `Features/Compliance/compliance.feature.md` and `Features/Compliance/compliance.flow.md` created at DELIVERING (promoted out of this directive). No premature creation.
- **R14**: edits to `transcode-vs-remux-routing.feature.md` (replace C11 cascade prose with pointer) delete the obsolete section in place -- no `removed YYYY-MM-DD` annotation.
- **R15**: every new and every edited def/class in this directive's `## Files` list carries `# directive: compliance-solid-refactor | # see compliance-solid-refactor.C<N>` directly above the `def` / `class`. Replace any preexisting `# directive:` line; multiple consecutive `# directive:` lines violate R12.
- **R16**: new `*.feature.md` / `*.flow.md` (at DELIVERING) carry `**Slug:** <slug>` in the first 15 lines.
- **R18**: any colocated `*.feature.md` read during NEEDS_DOC_PREREAD uses `limit<=50` + offset walking. Existing reads this session already satisfy preread for `Features/TranscodeQueue/*`.
- **R19**: no edits to `Repositories/DatabaseManager.py`. New repositories live in `Features/Compliance/Repositories/`.
- **No hook overrides.** Per `memory/feedback_no_hook_overrides.md` -- if a hook refuses, fix the root cause (missing anchor, unread doc, phase mismatch); never `# allow:`.
- **No hardcoded values.** Every threshold, whitelist, and enable-flag is a column in the new rule tables. `ComplianceEvaluator` reads; it doesn't decide. Per `memory/feedback_no_hardcoded_values.md`.
- **One editor per conceptual unit.** The /settings card is the SINGLE editor for compliance rules. No other UI surface duplicates the rule inputs.

## Engineering Calls Already Made

- **Typed columns per operation, not a generic `Rules(RuleKind, ParamJson)` table.** Generic schemas defer the data-driven win -- every new RuleKind still needs a Python interpreter. Typed columns let the GUI generate from `\d` and let Postgres enforce types. Matches the existing single-row scalar config precedent in this repo.
- **One table per operation, not one per (operation, rule).** Operator tunes a coherent unit (Transcode policy = one row of related knobs). Many small tables = many save events; one row per operation = atomic policy update.
- **Bucket derivation in `ComplianceBucketResolver`, not embedded in each operation.** Operations decide "do I apply?"; the resolver decides "what tab does this file belong on?". Keeps operations independent (LSP: any operation can be added without touching the resolver beyond a new branch).
- **`OperationsNeeded` as `frozenset[str]`, not `OperationsNeeded` flags per operation.** Set semantics fit the "anything else?" extensibility -- a new operation is a new string, not a new column on the decision. The CSV materialization on `MediaFiles.OperationsNeededCsv` is for SQL readability.
- **SubtitleFix included as the 4th operation, defaulted OFF** (`SubtitleFixRules.Enabled = FALSE`). Brings it into the cascade so it can ride the same auto-detection rails, but ships dormant until the SubtitleFix queue path proves stable on the manual `PopulateQueueForSubtitleFix` road.
- **`MediaFiles.RecommendedMode` deletion is in scope.** Keeping both `RecommendedMode` and `WorkBucket` is exactly the cruft this refactor exists to remove. Single column, single semantic.
- **`NeedsTranscode` / `NeedsQuick` deletion is in scope.** Same reasoning. Their indexes get rebuilt against `WorkBucket`.
- **No worktree** -- per operator instruction, work on main.
- **Phase machine: NEEDS_PLAN -> NEEDS_DOC_PREREAD -> IMPLEMENTING -> VERIFYING -> DELIVERING.** Standard CEO flow.
- **Commits: one per criterion group** (A schema / B service+operations+gates / C decision model + RecommendedMode retirement / D GUI / E bucket routing / F backfill+indexes+tests). Each commit deploys to a worker, smoke-tests one recompute, before advancing. Per memory `feedback_smoke_test_per_step_not_at_end.md`.
- **Hook conformance pre-flight: spelled out below** so R-rule surprises don't bite mid-implementation. Per operator instruction.

## Status

**CLOSED** 2026-06-09 -- DELIVERING complete. All Promotions delivered: `Features/Compliance/compliance.feature.md` + `compliance.flow.md` created; `transcode-vs-remux-routing.feature.md` C11 + `transcode.flow.md` Stage 3.5 retired in-place (R14); `IDEAS.md` appended with SQL-view follow-up. Drop scripts `Scripts/SQLScripts/DropRecommendedModeColumn.py` + `DropNeedsFlags.py` authored; **execution deferred to operator-authorized run** (production-shape MediaFiles schema change). Workers (I9 + dot + larry) on hotfix code; 51/51 contract tests pass; dual-write keeps operator UI rendering unchanged. Directive doc to move to `.claude/directives/closed/2026-06-09-compliance-solid-refactor.md` after final commit; `.claude/current-feature` stack pops `compliance-solid-refactor`.

### Files

| # | File | Action | Anchor (`# directive: compliance-solid-refactor \| # see compliance-solid-refactor.<ID>`) | R-rule notes |
|---|---|---|---|---|
| 1 | `Scripts/SQLScripts/AddComplianceRuleTables.py` | NEW | `C1` on `Run()` | R11: `CREATE TABLE IF NOT EXISTS` x5 + `INSERT ... ON CONFLICT DO NOTHING` seed. R12: single-line SQL strings; no module docstring. |
| 2 | `Scripts/SQLScripts/AddWorkBucketColumn.py` | NEW | `C7` on `Run()` | R11: `ADD COLUMN IF NOT EXISTS` x5 on MediaFiles (the 4 bucket / gate columns + `HasForcedSubtitles BOOLEAN NULL` per `C5b`). |
| 3 | `Scripts/SQLScripts/AddWorkBucketIndexes.py` | NEW | `C24` on `Run()` | R11: 4x `CREATE INDEX IF NOT EXISTS`. Prints EXPLAIN ANALYZE for each. |
| 4 | `Scripts/SQLScripts/BackfillWorkBucket.py` | NEW | `C25` on `Run()` | R12: single-line docstrings. Batched, `--dry-run`, `--limit`. |
| 5 | `Scripts/SQLScripts/DropRecommendedModeColumn.py` | NEW (DELIVERING) | `C15` on `Run()` | R11: idempotent `DROP COLUMN IF EXISTS`. Ships in the same commit as the last reader migration. |
| 5b | `Scripts/SQLScripts/DropNeedsFlags.py` | NEW (DELIVERING) | `C22` on `Run()` | R11: idempotent `DROP COLUMN IF EXISTS` for NeedsTranscode + NeedsQuick + their indexes. |
| 6 | `Features/Compliance/Repositories/TranscodeRulesRepository.py` | NEW | `C2`/`C12` on `class`; `C2` on `Get()`/`Update()` | R3: stateless. R12: single-line SQL + one-line docstrings. Mirrors `QueueAdmissionConfigRepository`. |
| 6b-6e | `Features/Compliance/Repositories/{Remux,AudioFix,SubtitleFix,ComplianceGates}RulesRepository.py` | NEW | analogous per `C3`/`C4`/`C5`/`C6` | same R-notes |
| 6f | `Features/Compliance/Repositories/ComplianceWriteRepository.py` | NEW (Batch 2) | `C23` on `BulkWriteRecomputeResults` | Surfaced by R12 mandate #2 (SQL-in-Repository) when migrating `RecomputeForFiles`. Owns the bulk UPDATE that writes AssignedProfile / PriorityScore / IsCompliant / RecommendedMode / NeedsQuick / NeedsTranscode / AdmissionDeferReason + new WorkBucket / OperationsNeededCsv / ComplianceGateBlocked / ComplianceEvaluatedAt. R5: ExecuteNonQuery for the UPDATE. R12: single-line SQL strings, one-line docstring. R19: lives in `Features/Compliance/Repositories/`, not `Repositories/DatabaseManager.py`. |
| 7 | `Features/Compliance/Models/ComplianceDecision.py` | NEW | `C13` on `class` | R12: dataclass; one-line docstring. |
| 7b | `Features/Compliance/Models/OperationResult.py` | NEW | `C13` on `class` | same |
| 8 | `Features/Compliance/Operations/IComplianceOperation.py` | NEW | `C8` on `class` (abstract) | R12: one-line interface docstring. |
| 8b-8e | `Features/Compliance/Operations/{Transcode,Remux,AudioFix,SubtitleFix}Operation.py` | NEW | `C8` on `class`; rule application per `C2`-`C5` | LSP/ISP. R12. |
| 9 | `Features/Compliance/Gates/IComplianceGate.py` | NEW | `C8` on `class` (abstract) | R12. |
| 9b-9i | `Features/Compliance/Gates/{EnglishAudio,AudioCorruptSuspect,AudioStream,LoudnessMeasurements,ProbeMetadata,EffectiveProfile,ResolutionCategory,ProfileThresholds}Gate.py` | NEW | `C8` + each gate's `C6` mapping | LSP/SRP. R12. |
| 10 | `Features/Compliance/Services/ComplianceEvaluator.py` | NEW | `C8`/`C11` on `class`; `C13` on `Evaluate()` | DIP via constructor injection. R3/R12. |
| 10b | `Features/Compliance/Services/ComplianceGateChain.py` | NEW | `C8` on `class`; `C13`/`C6` on `Run()` | R12. |
| 10c | `Features/Compliance/Services/ComplianceRuleEngine.py` | NEW | `C8` on `class`; `C8` on `Run()` | OCP via registry. R12. |
| 10d | `Features/Compliance/Services/ComplianceBucketResolver.py` | NEW | `C8`/`C14` on `class` | Pure function. R12. |
| 10e | `Features/Compliance/ComplianceComposition.py` | NEW | `C11` on `Build()` | Composition root. R12. |
| 11 | `Features/Compliance/ComplianceController.py` | NEW | `C16`-`C19` on each route handler | Flask blueprint. R12. |
| 12 | `Features/TranscodeQueue/QueueManagementBusinessService.py` | EDIT (delete `_EvaluateCompliance`, migrate callers to `ComplianceEvaluator`) | `C9` on each touched method | R3/R12. R19-adjacent: keep QMBS shrinkage to compliance extraction only. |
| 13 | `Features/MediaProbe/MediaProbeBusinessService.py` | EDIT (read `Disposition.forced` per subtitle stream, populate `MediaFiles.HasForcedSubtitles` per `C5b`; call `RecomputeForFiles` with new bucket fields populated per `C23`) | `C5b`/`C23` on `_ExecuteProbe` | **Batch 2** (worker redeploy required). R12 edit-region. |
| 14 | `Features/FileReplacement/FileReplacementBusinessService.py` | EDIT (recompute post-flight reads `WorkBucket`) | `C23` on the post-flight hook | **Batch 2** (worker redeploy required). R12 edit-region. |
| 15 | `Features/TranscodeQueue/QueueManagementBusinessService.py` -- `NextTranscodeBatch` + `SmartPopulateQueue` | **DEFERRED to Batch 2.5 / DELIVERING** -- migrating WHERE clauses to `WorkBucket` requires that WorkBucket be populated for the bulk of the library, which requires CRF-bitrate-estimate integration (`marginal-savings-gate.feature.md` CRF lookups). Backfill ran during Batch 2 step 2 and surfaced 92% of the library gate-blocked on `ProfileThresholds` because CRF profiles store `VideoBitrateKbps=0`. Switching readers now would empty operator UI. Dual-write from RecomputeForFiles keeps both column families in sync so the swap can land later atomically. | `C20` on each query | R12 edit-region (when it lands). |
| 16 | `Features/Activity/ActivityController.py` (not Repository -- SQL currently inlined in Controller; will move during this edit) | **DEFERRED to Batch 2.5 / DELIVERING** -- same blocker as file 15 (needs WorkBucket populated) AND will also satisfy R12 mandate #2 by moving the 4 inlined `LibraryCompliance` SQL blocks to `ActivityRepository.py`. | `C20` on the query | R12 edit-region (when it lands); R12 mandate #2 (SQL-in-Repository). |
| 17 | `Templates/Settings.html` | EDIT (new "Compliance Rules" collapsible card) | N/A (HTML; R15 N/A) | Follows the Queue admission card pattern. |
| 18 | `Tests/Contract/TestComplianceEngine.py` | NEW | `C26` distributed across `test_*` | R8 placement. R12 one-line docstrings. |
| 19 | `Features/TranscodeQueue/transcode-vs-remux-routing.feature.md` | EDIT (C11 prose replaced with pointer to `compliance.feature.md`) | N/A (R15 N/A); R14: delete in place, no annotation | DELIVERING-phase edit. |
| 20 | `transcode.flow.md` | EDIT (Stage 3.5 RECOMPUTE prose replaced with pointer to `compliance.flow.md`) | N/A; R14 | DELIVERING-phase edit. |
| 21 | `Features/Compliance/compliance.feature.md` | NEW (DELIVERING per R13) | N/A | R16 Slug. C1-C26 promote here. |
| 22 | `Features/Compliance/compliance.flow.md` | NEW (DELIVERING per R13) | N/A | R16 Slug. Stage descriptions for: load rules -> apply gates -> apply operations -> resolve bucket -> emit decision. |

### Hook Conformance Pre-Flight

Accepted code-anchor syntax: **`# directive: compliance-solid-refactor | # see compliance-solid-refactor.C<N>`** -- second `#` after the pipe is required (Test-R15-DirectiveAnchor regex `#\s*see\s+[a-z0-9-]+\.(S|W|C|ST)\d+`). Working examples in tree: `Core/WorkerContext.py:4`, `Features/MediaFiles/MediaFilesRepository.py:8`.

R-rules most likely to bite this directive:

- **R12 -- single-line comments + no docstrings >1 line + no triple-quoted SQL.** Highest risk. New service modules will tempt prose docstrings. Discipline: every class gets ONE one-line docstring; every method gets ONE one-line docstring (often just the function name reflowed); SQL strings are single-line concatenations or string-tuples. **Details that don't fit on one line go into `compliance.feature.md` / `compliance.flow.md` -- which exist at DELIVERING. During IMPLEMENTING, design prose grows in this directive doc, then promotes out at the phase transition.**
- **R3 + db-is-authority -- no cached rule snapshots.** Every `*RulesRepository.Get()` reads fresh. The bulk-recompute optimization (single cache snapshot per `RecomputeForFiles` call) is a parameter passed down, not state stored on a Repository or Service.
- **R11 -- migrations idempotent.** Every `Scripts/SQLScripts/Add*.py` and `Drop*.py` is re-runnable on the same DB. CI re-runs them on a fresh schema to verify.
- **R13 -- no `*.feature.md` / `*.flow.md` outside DELIVERING.** Filings 21-22 are explicitly DELIVERING-phase creations. Anything else attempted earlier gets refused -- design prose stays in this directive.
- **R14 -- no annotation lines** when editing existing `transcode-vs-remux-routing.feature.md` and `transcode.flow.md` (filings 19-20). Delete obsolete sections in place; do not append "(retired 2026-06-09)" annotations.
- **R15 -- two-anchor line on every edited/new def/class.** Multiple consecutive `# directive:` lines fail R12. If a function already carries a closed directive's anchor, REPLACE it with this directive's anchor (git history preserves the breadcrumb).
- **R19 -- no `Repositories/DatabaseManager.py` edits.** Every new repository lives under `Features/Compliance/Repositories/`.
- **R10 -- no `Claim*` additions.** None planned. If a downstream tweak requires one, it lands in `Features/TranscodeQueue/TranscodeQueueRepository.py`.
- **R2 -- seed evidence.** Any `INSERT` numeric literal in the seed migrations carries `# from: <path>` pointing at the source. For migration C1's seed defaults, the source is this directive doc (cite `.claude/directive.md` + criterion ID).

Operationally-judged risks (not hook-gated):
- **Scope creep into BUG-0028 items 2-6.** Tempting. Out of scope per the "## Out of Scope" section.
- **GUI live-preview cost.** Sampling 1,000 rows per preview is the bound; if EXPLAIN shows seq scan, the preview falls back to "rules saved -- recompute the library to see impact" rather than blocking on a slow query.
- **Bucket resolver edge cases.** C14 lists one open question (`{AudioFix, SubtitleFix}` precedence). Surface at DELIVERING for operator decision; default to `AudioFixOnly`.

### Per-file hook tactics (survives session boundaries)

**R12 in legacy edits (files 12, 13, 14, 15, 16).** Edit-region scope is the protection. Tactics:
- The `_EvaluateCompliance` removal in file 12 is a **pure deletion** -- R12 is skipped on the deleted region per `.claude/standards/index.md` ("Pure-deletion edits (all `new_string` empty) skip the check").
- The ~6 caller migrations (`self._EvaluateCompliance(...)` -> `self.ComplianceEvaluator.Evaluate(...)`) are single-line substitutions inside existing one-liners. Edit region = one line; preexisting multi-line docstrings around them stay outside scope.
- **Never widen an edit region to tidy up a nearby preexisting multi-line docstring.** That pulls the docstring into scope and triggers R12 even though the violation is preexisting.

**R15 + R12 anchor interaction (files 12, 13, 14, 15, 16).** When a function I'm editing already carries `# directive: <old-slug> | # see <old-slug>.<ID>` (e.g. `CalculatePriority` already carries `# directive: path-schema-migration | # see path.S8`), I **REPLACE** the line with this directive's anchor -- I do not append above it. Two consecutive `# directive:` lines violate R12 (comment block > 1 line). Git history preserves the prior breadcrumb.

**R2 seed evidence sidestep (files 1, plus any seed migration).** Seed `INSERT` statements specify ONLY `Id` and rely on column `DEFAULT` clauses for every other value:
```sql
INSERT INTO TranscodeRules (Id) VALUES (1) ON CONFLICT DO NOTHING;
```
No numeric literals in the INSERT -> R2 doesn't fire. The defended values live in column `DEFAULT` declarations, and the upstream citation for the chosen defaults is this directive's C2-C6.

**R3 false-positive guard (file 10).** `ComplianceEvaluator.__init__(OperationRegistry, GateChain, BucketResolver)` injects dependencies, not config. Field names use no underscore prefix and avoid the substrings R3 scans for (`_cached_*`, `_*_settings`, `_config_snapshot`): use `self.OperationRegistry`, `self.GateChain`, `self.BucketResolver`. The bulk-recompute `RuleCache` is a **method parameter** to `RecomputeForFiles`, not instance state.

**R14 retirement discipline (files 19, 20 at DELIVERING).** When the C11 cascade prose and `transcode.flow.md` Stage 3.5 RECOMPUTE prose are retired in favor of pointers to `compliance.feature.md` / `compliance.flow.md`, the obsolete sections are **deleted in place** and replaced by the pointer line. No `(retired 2026-06-09 -- see compliance.feature.md)` annotations. Git history holds the prior content.

**R11 idempotency token map.** Every migration carries the right token:
- `Scripts/SQLScripts/AddComplianceRuleTables.py` -> `CREATE TABLE IF NOT EXISTS` x5 + `INSERT ... ON CONFLICT DO NOTHING` seed x5
- `Scripts/SQLScripts/AddWorkBucketColumn.py` -> `ADD COLUMN IF NOT EXISTS` x4
- `Scripts/SQLScripts/AddWorkBucketIndexes.py` -> `CREATE INDEX IF NOT EXISTS` x4
- `Scripts/SQLScripts/BackfillWorkBucket.py` -> re-runnable by predicate (`WHERE ComplianceEvaluatedAt IS NULL` or `WHERE WorkBucket IS NULL`)
- `Scripts/SQLScripts/DropRecommendedModeColumn.py` -> `DROP COLUMN IF EXISTS`
- `Scripts/SQLScripts/DropNeedsFlags.py` -> `DROP COLUMN IF EXISTS` x2 + `DROP INDEX IF EXISTS` for the matching indexes

### Promotions

| Source artifact | Target file | Status |
|---|---|---|
| `## Acceptance Criteria` C1-C26 + C5b | `Features/Compliance/compliance.feature.md` (NEW at DELIVERING per R13) | Pending |
| Per-stage pipeline design (load rules -> gates -> operations -> bucket -> emit decision) + seams table | `Features/Compliance/compliance.flow.md` (NEW at DELIVERING per R13) | Pending |
| Retirement of C11 cascade prose + pointer to compliance.feature.md | `Features/TranscodeQueue/transcode-vs-remux-routing.feature.md` (EDIT, R14 delete-in-place) | Pending |
| Retirement of Stage 3.5 RECOMPUTE prose + pointer to compliance.flow.md | `transcode.flow.md` (EDIT, R14 delete-in-place) | Pending |
| `IDEAS.md` line: SQL-view gate simplification | `IDEAS.md` (EDIT, append from `### Deferred Ideas`) | Pending |
| Drop scripts authored (operator runs at their discretion) | `Scripts/SQLScripts/DropRecommendedModeColumn.py` + `Scripts/SQLScripts/DropNeedsFlags.py` (NEW) | Authored, execution deferred to operator |

### Verification

| Criterion | Evidence | Verifying commit |
|---|---|---|
| C1 (5 single-row rule tables) | `\d TranscodeRules` / `\d RemuxRules` / `\d AudioFixRules` / `\d SubtitleFixRules` / `\d ComplianceGates` -- all 5 present with CHECK (Id = 1); `SELECT * FROM <table>` returns one seeded row per table | 9f547c5 |
| C2 (TranscodeRules columns) | `\d TranscodeRules` shows `ResolutionExceedsProfileTarget BOOL DEFAULT TRUE`, `AcceptableVideoCodecsCsv TEXT DEFAULT 'h264,hevc,av1'`, `EstimatedSavingsMBThreshold INT DEFAULT 150`, `PreventUpscale BOOL DEFAULT TRUE` | 9f547c5 |
| C3 (RemuxRules columns) | `\d RemuxRules` shows `AcceptableContainersCsv DEFAULT 'mp4,mov,m4v'`, `AcceptableAudioCodecsMp4Csv DEFAULT 'aac,ac3,eac3,mp3'`, `RequireAudioNormalized BOOL DEFAULT TRUE` | 9f547c5 |
| C4 (AudioFixRules columns) | `\d AudioFixRules` shows `TargetLoudnessLufs INT DEFAULT -23`, `ToleranceLufs FLOAT DEFAULT 1.0`, `RequireLufsMeasured BOOL DEFAULT TRUE` | 9f547c5 |
| C5 (SubtitleFixRules columns) | `\d SubtitleFixRules` shows `Enabled BOOL DEFAULT FALSE`, `MovTextRequiredForMp4 BOOL DEFAULT TRUE`, `NonNativeSubtitleFormatsCsv DEFAULT 'ass,ssa,vobsub'`, `RequireForcedSubtitlesPresent BOOL DEFAULT TRUE` | 9f547c5 |
| C5b (forced-subs probe extension) | `Models/FFmpegAnalysisModel.HasForcedSubtitles` field + `Services/FFmpegAnalysisService` subtitle-stream `disposition.forced` aggregation; smoke-verified live: MediaFile Id=25229 (Restaurant to Another World S01E05, SubtitleFormats='ass') went NULL -> True after reprobe via API | 61192af |
| C6 (ComplianceGates -- 8 BOOLEAN flags) | `\d ComplianceGates` shows the 8 flags all defaulting TRUE; contract test `TestGates.test_<gate>_disabled_lets_through` exercises each toggle | 9f547c5, 09042da |
| C7 (MediaFiles +5 columns) | `\d MediaFiles` shows `WorkBucket TEXT`, `OperationsNeededCsv TEXT`, `ComplianceGateBlocked TEXT`, `ComplianceEvaluatedAt TIMESTAMP`, `HasForcedSubtitles BOOL` | 9f547c5, 61192af |
| C8 (Features/Compliance/ vertical) | `ls Features/Compliance/` shows Repositories/, Operations/, Gates/, Services/, Models/, ComplianceController.py, ComplianceComposition.py -- 23 files total per the directive Files table | every commit |
| C9 (`_EvaluateCompliance` deleted, callers migrate to `ComplianceEvaluator`) | `grep -rn '_EvaluateCompliance' --include='*.py'` returns zero matches in `Features/TranscodeQueue/`; `EvaluateCandidateCompliance` is a delegating wrapper calling `ComplianceEvaluator.Evaluate` | c8fa349 |
| C10 (R19 -- no DatabaseManager.py edits) | `git log --since='2026-06-09 00:00' -- Repositories/DatabaseManager.py` returns no entries from this directive | (verified by git history) |
| C11 (DIP via constructor injection) | `Features/Compliance/Services/ComplianceEvaluator.__init__(GateChain, RuleEngine, BucketResolver)`; wiring in `Features/Compliance/ComplianceComposition.BuildEvaluator()`; `ComplianceRecomputeService.__init__(DatabaseServiceInstance, ProfileResolver)` | 09042da, 4532d6d |
| C12 (no cached config; bulk cache as method parameter) | `grep -rn 'self\._cached' Features/Compliance/` returns zero; `ComplianceRuleCache` is passed as `Evaluate(Mf, Profile, Cache)` argument; `EffectiveProfileResolver` reads DB fresh per `Resolve()` call (no cached fields) | 80af2de, 09042da, e33e9d9 |
| C13 (ComplianceDecision shape -- 5 fields, immutable) | `Features/Compliance/Models/ComplianceDecision` is `@dataclass(frozen=True)` with `IsCompliant`, `OperationsNeeded: FrozenSet`, `WorkBucket`, `GateBlocked`, `Reasons` | ecf9c43 |
| C14 (bucket precedence Transcode > Remux > AudioFixOnly > SubtitleFixOnly) | `Features/Compliance/Services/ComplianceBucketResolver.Resolve` implements the exact precedence; `TestBucketResolverPrecedence` covers all 6 transitions including the `{AudioFix, SubtitleFix}` -> `AudioFixOnly` open-question default | 09042da, 52efa7c |
| C15 (RecommendedMode retired at DELIVERING) | DELIVERING-phase drop script `Scripts/SQLScripts/DropRecommendedModeColumn.py` written; pending operator approval to execute. Dual-write keeps the column populated until drop. | (DELIVERING) |
| C16-C19 (GUI) | `/settings` "Compliance rules" card live (12 DOM markers); 10 API routes at `/api/Compliance/*` (GET/PUT × 5 tables + Buckets + Preview + Recompute); per-bucket counts widget functional | 049977a |
| C17 (live preview) | `POST /api/Compliance/Preview` with `{SampleSize: 1000}` returns dry-run bucket + gate breakdown; smoke-verified | d41ae3c |
| C18 ({Success, Message, Data} envelope) | `Features/Compliance/ComplianceController._Envelope` helper enforces shape; verified via curl on all 10 routes | d41ae3c |
| C19 (per-WorkBucket counts widget) | `GET /api/Compliance/Buckets` returns `{Buckets: {bucket: N}, GateBlocked: {gate: N}}`; GUI calls `RefreshBucketCounts()` JS on collapse-show | d41ae3c, 049977a |
| C20 (queue surfaces route by WorkBucket) | `NextTranscodeBatch` SQL has `WHERE m.WorkBucket = 'Transcode'`; `SmartPopulateQueue` Mode block maps Quick/Transcode/Remux/AudioFix to corresponding WorkBucket; `ActivityRepository.GetWorkBucketBreakdown` groups by WorkBucket | 8a9e42b, 85fb5d9 |
| C21 (claim contract unchanged) | `git log --since='2026-06-09' -- Features/TranscodeQueue/TranscodeQueueRepository.py` shows no claim-ORDER-BY changes in this directive; claim path still owned by `queue-priority.feature.md` | (verified by git) |
| C22 (NeedsTranscode/NeedsQuick retired) | DELIVERING-phase drop script `Scripts/SQLScripts/DropNeedsFlags.py` written; pending operator approval. Dual-write keeps the columns populated until drop. | (DELIVERING) |
| C23 (RecomputeForFiles is the only writer of new columns) | `grep -rn 'WorkBucket = %s\|ComplianceGateBlocked = %s\|OperationsNeededCsv = %s' --include='*.py'` returns only `Features/Compliance/Repositories/ComplianceWriteRepository.BulkWriteRecomputeResults` + `Features/Compliance/Services/ComplianceRecomputeService.Recompute` | c8fa349, 4532d6d |
| C24 (partial indexes per bucket) | `\di idx_mediafiles_wb_*` shows 4 partial indexes (Transcode/Remux/AudioFixOnly/SubtitleFixOnly) | 9f547c5 |
| C25 (backfill script) | `Scripts/SQLScripts/BackfillWorkBucket.py` with `--dry-run` + `--limit` + `--batch-size`; re-runs via `WHERE ComplianceEvaluatedAt IS NULL` predicate; verified full-library backfill (50,156 rows) completes | 4ecbc49 |
| C26 (contract tests) | 51 tests in `Tests/Contract/TestComplianceEngine.py` + `TestClaimAuthority.py`: TestGates (10) + TestOperations (8) + TestSubtitleFix (5) + TestMidFlightConfigChange (1) + TestBucketResolverPrecedence (6) + TestCrfProfileRegression (3) + 18 claim-authority tests carried over | 52efa7c, 4aa9d3e |
| **CRF regression (post-merge hotfix)** | `_BuildEffectiveProfileObj`/`_LoadThresholdLookup`: `Vk or None` bug converted 0 (CRF profile) to None, gate-blocked 92% of library; fixed by preserving 0 + `_EstimatedSavingsMB` accepts audio=0; 3 new TestCrfProfileRegression cases | 4aa9d3e |
| **Path A engine completion** | `EffectiveProfileResolver` (SRP profile resolution), `_BuildEffectiveProfileObj` + `ComplianceRecomputeService` delegate via DIP, `NextTranscodeBatch`/`SmartPopulateQueue`/`ActivityController.LibraryCompliance` migrate to WorkBucket; `ActivityController` SQL extracted to repo (R12 mandate #2) | e33e9d9, 4532d6d, 8a9e42b, 85fb5d9 |

### Decisions Made

(Populated during execution as ambiguities surface. Pre-populated decisions live in `## Engineering Calls Already Made` above.)

### Sequencing (Batch 1 / drain / Batch 2)

**Batch 1 -- WebService-only, additive.** Lands without touching workers:
- Files 1-5b (all migrations: rule tables, MediaFiles columns, indexes, backfill, drop scripts authored but not yet executed)
- Files 6-11 (new `Features/Compliance/` vertical -- new dir; workers never load these)
- File 17 (Templates/Settings.html GUI)
- File 18 (Tests/Contract/TestComplianceEngine.py)
- Existing `_EvaluateCompliance` stays put; new `ComplianceEvaluator` runs side-by-side. GUI works. WebService restart by me per `feedback_user_starts_webservice.md`.

**Drain checkpoint.** Before Batch 2:
- Set `Workers.Status='Draining'` on every worker via the Activity GUI (or via `UPDATE Workers SET Status='Draining'`).
- Workers finish in-flight jobs and self-flip to `Stopped` per `activity-dashboard-improvements.feature.md` C8 (within 5-7 s of last job completing).
- I report "drain complete, ready for Batch 2 + redeploy" and wait for operator confirmation before the worker code commit lands.

**Batch 2 -- worker-affecting.** Lands after drain:
- File 12 (`QueueManagementBusinessService._EvaluateCompliance` deletion + WebService caller migrations) -- DONE (commit c8fa349)
- File 13 (`MediaProbeBusinessService._ExecuteProbe` forced-subs read + recompute hook) -- DONE (commit 61192af)
- File 14 (`FileReplacementBusinessService` post-flight recompute reads WorkBucket) -- IMPLICITLY DONE via file 12 (post-flight calls RecomputeForFiles which dual-writes)
- File 15 + file 16 -- DEFERRED to Batch 2.5 / DELIVERING, gated on CRF-bitrate-estimate integration. See Files table notes.
- Operator redeploys workers via `mediavortex-deploy-worker` skill (or I run it on explicit per-step authorization).
- Workers come back up; `Workers.Status='Online'`; verify one probe + one transcode end-to-end before VERIFYING.

**Batch 2.5 (follow-up directive, not this one):**
- CRF-bitrate-estimate integration into `ComplianceRecomputeService._ResolveProfile` (use `CrfBitrateEstimates` table when `ProfileThresholds.VideoBitrateKbps=0`).
- After integration, full library re-backfill -> WorkBucket populates for the ~92% currently gate-blocked on ProfileThresholds.
- File 15: NextTranscodeBatch + SmartPopulate WHERE clauses migrate from `NeedsTranscode/NeedsQuick/RecommendedMode` to `WorkBucket`.
- File 16: ActivityController's 4 inlined `LibraryCompliance` SQL blocks move to `ActivityRepository.py` (R12 mandate #2 satisfied) + GROUP BY `WorkBucket` (file 16's original intent).

**DELIVERING** runs after both batches: file 5/5b drop scripts execute, files 19-20 prose retirement, files 21-22 (`compliance.feature.md` + `compliance.flow.md`) creation per R13.

### Deferred Ideas

(Promoted to `IDEAS.md` at DELIVERING.)

- 2026-06-09 | Push compliance Gates into a SQL view (`v_MediaFilesGateStatus` = `MediaFiles CROSS JOIN ComplianceGates` + first-fail CASE WHEN). Collapses the 8 `IComplianceGate` impls + chain + interface from this directive's C8 into one view + ~30 LOC Python reader; `RecomputeForFiles` becomes a single SQL UPDATE for the gate column. Considered for this directive; deferred to a follow-up after the engine ships.
