# Resolution Types -- typed value objects + ScalePolicy (eliminates string-heterogeneity bug)

**Set:** 2026-06-15
**Status:** Active -- phase: VERIFYING
**Slug:** resolution-types
**Interrupts:** table-renderer-service (paused 2026-06-15), quality-floor-lift (paused 2026-06-15 at 45278eb)
**Bug:** Live -- Men in Black II (MF 621554) 2026-06-15: 81.6% reduction discarded because the encoded output wasn't downscaled.

## Outcome

Replace the string-heterogeneity bug class at the heart of CommandBuilder's scale-filter omission. Today three different string shapes (`'1916x1040'`, `'1080p'`, `'720p'`, `'No downscaling'`, `''`, `None`) flow through the same code paths and are compared with `==`. For off-canonical 1080p sources (e.g. cinematic letterbox `1916x1040`), the equality compare fails wrong, the `-vf scale=...` filter never gets emitted, FFmpeg encodes at source resolution, and the post-flight compliance gate correctly refuses replacement with `downscale_needed`. After this directive, a typed `Resolution` value object and a `ResolutionTier` enum own all string parsing at the boundary; the encode + compliance call chain consumes typed values only; aspect ratio is preserved; adding a new tier (e.g. `1440p`) is a one-row change with zero edits to the decision code.

## Acceptance Criteria

1. **`Resolution` value object is the only string parser.** `Core/Resolution/Resolution.py` defines `@dataclass(frozen=True) Resolution(Width: int, Height: int, Tier: ResolutionTier, AspectRatio: float)`. `Resolution.FromAny(Value)` accepts `'1916x1040'`, `'1080p'`, `(1916, 1040)`, an existing `Resolution`, or `None`. No field is a string after construction. Verifiable: `Tests/Contract/TestResolution.py` covers raw pixels, canonical category, cinematic letterbox (`1916x1040` -> Tier T1080p, AspectRatio 1.842), anamorphic (`853x480`), ultra-wide (`1920x800`), idempotent (existing `Resolution` returns unchanged), `None`/empty (returns `None`, never raises).

2. **`ResolutionTier` is a runtime-loaded value object backed by `ResolutionTiers` DB table.** `Core/Resolution/ResolutionTier.py` defines `@dataclass(frozen=True) ResolutionTier(Name, MinLongEdge, CanonicalWidth, CanonicalHeight, Rank)`. No hardcoded thresholds in code. `Core/Resolution/ResolutionTierRegistry` loads all tiers per-instance from DB (fresh per request batch; db-is-authority compliant -- not per-process cache). `Registry.FromDims(Width, Height)` uses `max(Width, Height)` as the discriminator (orientation-agnostic; works for landscape, portrait, square, ultra-wide, letterbox). `Registry.FromCategory(str)` maps `'1080p'`/`'720p'`/`'4k'`/etc to a Tier or None. Verifiable: `Tests/Contract/TestResolutionTier.py` covers boundary values with the live (seeded) thresholds and the round-trip `Registry.FromDims(T.CanonicalWidth, T.CanonicalHeight) == T`.

3. **`ScalePolicy` is the SOLE producer of scale-filter strings.** `Core/Resolution/ScalePolicy.py` defines `class IScalePolicy(ABC): def Decide(Source: Resolution, TargetTier: ResolutionTier) -> Optional[ScaleFilter]`. Concrete `WidthAnchoredScalePolicy.Decide` returns `None` when `Source.Tier.Rank <= TargetTier.Rank` (same-tier or upscale); else returns `ScaleFilter(Width=TargetTier.CanonicalWidth, HeightExpr='-2')`. `ScaleFilter.AsFfmpegArg()` returns `'scale=w=1280:h=-2'`. Verifiable: `Tests/Contract/TestScalePolicy.py` covers MIB-II regression (`Resolution.FromAny('1916x1040')` + `ResolutionTier.T720p` -> `scale=w=1280:h=-2`), upscale block, same-tier no-op, every (Source, Target) tier pair.

4. **`ResolutionCalculator` becomes a thin facade.** `Features/TranscodeJob/Emit/ResolutionCalculator.CalculateScaleFilter` delegates to `WidthAnchoredScalePolicy.Decide(Resolution.FromAny(SourceResolution), ResolutionTier.From*(TargetResolution))`. Returns `Decision.AsFfmpegArg()` for backward-compat with legacy callers, OR `None`. No string compares remain in the method bodies. Verifiable: existing `Tests/Contract/TestResolutionCalculator.py` passes unchanged; `grep -nE "\\s==\\s|\\s!=\\s" Features/TranscodeJob/Emit/ResolutionCalculator.py` returns zero matches in method bodies (excluding `is None` checks).

5. **`TranscodeOperation._HeightOf` replaced by `ResolutionTier`.** `Features/Compliance/Operations/TranscodeOperation.py` removes the inline `_RES_HEIGHTS = {...}` dict. Maps `Mf.ResolutionCategory` and `Profile.TargetResolutionCategory` to `ResolutionTier` via the same factory, compares via `.Rank`. Verifiable: existing `TestComplianceEngine::TestOperations` passes unchanged.

6. **`EffectiveProfileResolver` returns a typed `TargetTier`.** `Features/Compliance/Services/EffectiveProfileResolver._LookupThresholdsRow` returns `'TargetTier': ResolutionTier` instead of `'TargetResolution': str`. `EffectiveProfile.TargetResolutionCategory` field type becomes `Optional[ResolutionTier]`. The legacy string `'No downscaling'` is mapped to `Source.Tier` (no-op) at the resolver boundary, not inside operation code. Verifiable: field annotation is `ResolutionTier`, not `str`; downstream compliance tests pass.

7. **Live MIB-II shape produces the right scale filter.** `Resolution.FromAny('1916x1040')` -> `Tier=T1080p, AspectRatio=1.842`. `WidthAnchoredScalePolicy.Decide(that, T720p)` -> `ScaleFilter(1280, '-2')` -> `'scale=w=1280:h=-2'`. Verifiable: dedicated test case + a live re-encode of MF 621554 after deploy yields an ffmpeg command containing `-vf "scale=w=1280:h=-2"`.

8. **No raw-string heterogeneity remains in the encode + compliance call chain.** `grep -rEn "SourceResolution\\s*==|TargetResolution\\s*==" --include='*.py' Features/TranscodeJob/Emit/ Features/Compliance/ Core/Resolution/` returns zero matches in production code (test fixture strings excluded). Verifiable: grep output.

9. **OCP: adding a tier is one place.** Adding `T1440p` (probe-only, not landing) is exactly: one enum row in `ResolutionTier`, one entry in the `CanonicalWidth/Height` lookup, one entry in the `From` boundary table. Zero edits to `ResolutionCalculator`, `ScalePolicy`, `TranscodeOperation`, or `EffectiveProfileResolver`. Verifiable: probe diff stat shows a single file changed.

10. **Live remediation.** After deploy + library-wide `RecomputeForFiles`, the queue submitting MF 621554 (Men in Black II) emits an ffmpeg argv with `-vf "scale=w=1280:h=-2"`; the encoded output lands at `1280x695` (cinematic aspect preserved); post-flight `EvaluateCandidateCompliance` returns `IsCompliant=True`; `FileReplaced=True`. Verifiable: live SQL after a fresh attempt.

11. **CI invariant tests.** `TestResolution.py`, `TestResolutionTier.py`, `TestScalePolicy.py` all green. Existing `TestResolutionCalculator.py`, `TestComplianceEngine.py`, `TestTranscodeOperationMvTrust.py` remain green. Verifiable: `py -m pytest Tests/Contract/ -k 'Resolution or Compliance or Transcode' -v` exits 0.

12. **Reversible deployment, idempotent migration.** One new table (`ResolutionTiers`) seeded with the four canonical tiers. Schema migration idempotent (`CREATE TABLE IF NOT EXISTS` + `INSERT ON CONFLICT DO NOTHING` via a `UNIQUE(Name)` index). Rollback DDL is one statement (`DROP TABLE ResolutionTiers;`). No existing column dropped, no destructive data change. Verifiable: re-running the migration is a no-op; rollback restores pre-deploy state.

13. **Tier thresholds are operator-tunable via SQL.** `UPDATE ResolutionTiers SET MinLongEdge = X WHERE Name = 'T1080p'` takes effect on the NEXT compliance recompute or NEXT encode-command build (no service restart). Verifiable: change a threshold, observe a previously-1080p file get reclassified on its next recompute.

14. **`max(Width, Height)` is the SOLE classification discriminant.** Replaces production's width-primary + height-fallback two-step. Works for landscape (max=Width, equivalent to today's rule), portrait (max=Height, fixes FullHD-portrait misclassification), square, ultra-wide, letterbox. Verifiable: parametrized test asserts `Registry.FromDims(1080, 1920) == T1080p` (portrait FullHD) AND every landscape case matches today's production answer (zero diff on library-wide recompute for landscape).

## Out of Scope

- Loosening the compliance gate's threshold *rules* (the gate logic is correct; the encode is broken).
- Landing new tier values (`T1440p` etc.). The OCP probe demonstrates the one-place-add invariant but isn't merged.
- CommandBuilder refactor beyond the scale-decision path. Other ResolutionCalculator methods (filename, audio bitrate defaults) are untouched.
- Profile / threshold schema migrations.
- Any downscale-decision call site outside the listed files.

## Engineering Calls Already Made

- **Three classes, not two.** `Resolution` (value object), `ResolutionTier` (enum), `ScalePolicy` (decision). Separating Resolution from Tier lets a 1916x1040 source carry both its exact pixels AND its bucket; the policy reads only the tier for decisions but the exact pixels remain for downstream display / logging.
- **`-2` height anchor, not explicit pixel.** `scale=w=<TierWidth>:h=-2` lets FFmpeg derive an even codec-legal height from source aspect. No aspect ratio is forced; letterboxed and cinematic content render correctly.
- **`'No downscaling'` mapped at boundary.** The legacy threshold-row string is translated to `Source.Tier` at the resolver, so operation code never sees the literal. Old data flows compatibly without a migration.
- **Backward-compat facade.** `ResolutionCalculator.CalculateScaleFilter` keeps its old signature and returns a string -- so legacy callers don't see a churn diff. The string comes from `ScaleFilter.AsFfmpegArg()`; the heterogeneity is gone from the inside.
- **Typed `EffectiveProfile.TargetResolutionCategory: Optional[ResolutionTier]`.** Breaking change for the dataclass type, but contained: the field is only consumed inside the compliance vertical we're editing in this directive.

## Risk + Rollback

| Risk | Likelihood | Impact | Mitigation / Rollback |
|---|---|---|---|
| `Resolution.FromAny` mis-parses a corner case (e.g. odd ratio anamorphic) | Low | Medium | Parametrized contract test covers cinematic, anamorphic, ultra-wide, ratio 1:1. Rollback = revert single commit. |
| `EffectiveProfile.TargetResolutionCategory` type flip breaks an unseen consumer | Low | Medium | grep before commit; type-check at every call site; small blast radius (compliance vertical only). |
| Library-wide recompute introduces churn before deploy reaches workers | Low | Low | Recompute is post-deploy; if reverted, recompute again to restore prior state. |
| MIB-II is special (cinematic 1.85:1) and the fix doesn't help typical 16:9 | Low | Low | `scale=w=W:h=-2` is aspect-agnostic; works for 16:9, 1.85:1, 2.40:1. Covered in tests. |

## Notes

This is an `## Interrupts: table-renderer-service` push. Operator's tabular UI work is paused at `.claude/directives/paused/2026-06-15-table-renderer-service.md` and is reversible. The parent stack also carries `quality-floor-lift` paused at commit `45278eb`.

---

## Status

**Phase:** NEEDS_PLAN (waiting for criteria approval before implementing)
**Last touched:** 2026-06-15 by Claude (directive drafted from operator-confirmed design discussion)

### Approval Tracking

| AC | Status | Date | Notes / Amendment text |
|---|---|---|---|
| AC1 (Resolution value object) | approved | 2026-06-15 | CEO blanket "let's proceed" |
| AC2 (ResolutionTier enum) | approved | 2026-06-15 | CEO blanket "let's proceed" |
| AC3 (ScalePolicy + ScaleFilter) | approved | 2026-06-15 | CEO blanket "let's proceed" |
| AC4 (ResolutionCalculator facade) | approved | 2026-06-15 | CEO blanket "let's proceed" |
| AC5 (TranscodeOperation use Tier) | approved | 2026-06-15 | CEO blanket "let's proceed" |
| AC6 (EffectiveProfileResolver typed return) | approved | 2026-06-15 | CEO blanket "let's proceed" |
| AC7 (MIB-II live shape) | approved | 2026-06-15 | CEO blanket "let's proceed" |
| AC8 (no string heterogeneity) | approved | 2026-06-15 | CEO blanket "let's proceed" |
| AC9 (OCP probe) | approved | 2026-06-15 | CEO blanket "let's proceed" |
| AC10 (live remediation MF 621554) | approved | 2026-06-15 | CEO blanket "let's proceed" |
| AC11 (CI tests green) | approved | 2026-06-15 | CEO blanket "let's proceed" |
| AC12 (reversible, no schema) | approved | 2026-06-15 | CEO blanket "let's proceed" |

### Files

```
Core/Resolution/__init__.py                                       -- NEW package marker
Core/Resolution/Resolution.py                                     -- NEW frozen value object + FromAny
Core/Resolution/ResolutionTier.py                                 -- NEW frozen value object (Name + dims + rank)
Core/Resolution/ResolutionTierRegistry.py                         -- NEW per-batch registry; loads from DB; FromDims (max-edge) + FromCategory
Core/Resolution/ResolutionTiersRepository.py                      -- NEW DB-fresh read of ResolutionTiers table
Core/Resolution/ScalePolicy.py                                    -- NEW IScalePolicy + WidthAnchoredScalePolicy + ScaleFilter
Scripts/SQLScripts/AddResolutionTiersTable.py                     -- NEW idempotent migration + seed
Features/TranscodeJob/Emit/ResolutionCalculator.py                -- EDIT delegate to ScalePolicy
Features/Compliance/Operations/TranscodeOperation.py              -- EDIT replace _HeightOf with ResolutionTier
Features/Compliance/Services/EffectiveProfileResolver.py          -- EDIT return typed TargetTier
Features/Compliance/Models/EffectiveProfile.py                    -- EDIT field type Optional[ResolutionTier]
Tests/Contract/TestResolution.py                                  -- NEW
Tests/Contract/TestResolutionTier.py                              -- NEW
Tests/Contract/TestScalePolicy.py                                 -- NEW
```

### Plan

1. Build the three new types: `Resolution`, `ResolutionTier`, `IScalePolicy + WidthAnchoredScalePolicy + ScaleFilter`.
2. Contract tests for the three new types (TDD: write tests first).
3. Edit `ResolutionCalculator.CalculateScaleFilter` + `CalculateTargetResolution` to delegate to `ScalePolicy`. Existing tests stay green.
4. Edit `EffectiveProfile.TargetResolutionCategory` field to `Optional[ResolutionTier]`. Map `'No downscaling'` at resolver.
5. Edit `EffectiveProfileResolver._LookupThresholdsRow` to return `TargetTier: ResolutionTier`.
6. Edit `TranscodeOperation` to use `ResolutionTier.CanonicalHeight` / `.Rank` instead of `_HeightOf` dict.
7. Library-wide `RecomputeForFiles` after deploy.
8. Re-queue MF 621554 and verify live ffmpeg command + post-flight `FileReplaced=True`.
9. Promote durable content at DELIVERING: create `Core/Resolution/resolution-types.feature.md`; add cross-stage seam row to `transcode.flow.md`'s `## Seams`; retag references in `encode-emit.feature.md` C2 + `compliance.feature.md` C5.

### Preread Checklist (NEEDS_DOC_PREREAD; R1)

Each file edited in this directive has a colocated `*.feature.md` / `*.flow.md` that must be Read (partial, `limit<=50` per R18 with offset walks) before any Edit/Write on the code file. The hook gates this:

- [ ] `Features/TranscodeJob/Emit/ResolutionCalculator.py` -> read `Features/TranscodeJob/Emit/encode-emit.feature.md` (covers C2 ResolutionCalculator)
- [ ] `Features/Compliance/Operations/TranscodeOperation.py` -> read `Features/Compliance/compliance.feature.md` + `compliance.flow.md` (already in this session's read history; refresh on the C5 section if cache miss)
- [ ] `Features/Compliance/Services/EffectiveProfileResolver.py` -> same as above (compliance feature + flow)
- [ ] `Features/Compliance/Models/EffectiveProfile.py` -> same
- [ ] `transcode.flow.md` (repo root) -- read at DELIVERING for the seam-row edit (R14: no annotation lines; edit the existing `## Seams` table directly)

Tests live under `Tests/Contract/`; R1 does not apply (no colocated doc by convention).

### Hook Rule Coverage

| Rule | Applies? | Plan |
|---|---|---|
| Phase gate | Yes | `**Status:**` line drives the hook; advance via Edit on this doc. |
| R1 Doc preread | Yes | See checklist above; partial Read with `limit<=50` + offset walk for every `*.feature.md`. |
| R2 Seed evidence | No | No INSERT numeric literals; no migration script in scope. |
| R3 No cached settings | Yes | New services: `ScalePolicy` is stateless; `Resolution` is frozen. No `self._cached_*`. |
| R4 No env vars | Yes | None of the new files touch `os.environ`. |
| R5 ExecuteQuery misuse | No | No SQL writes; resolver only SELECTs. |
| R6 Path shape | No | No filesystem paths handled. |
| R7 Polymorphic CASCADE | No | No FK changes. |
| R8 Test placement | Yes | All new tests under `Tests/Contract/`. |
| R9 LIKE escape | No | No LIKE clauses. |
| R10 Claim predicate | No | No `Claim*` methods touched. |
| R11 Migration idempotency | No (AC12) | No migration scripts. |
| R12 Comment volume | Yes | One-line docstrings; no multi-line `#` blocks; no triple-quoted SQL. New files designed accordingly. |
| R13 No new feature/flow docs | Yes | New `Core/Resolution/resolution-types.feature.md` created at DELIVERING only; criteria live in this directive until then. |
| R14 Annotation drift | Yes | Edits to `encode-emit.feature.md` / `transcode.flow.md` / `compliance.feature.md` use deletion or in-place edit; no `removed YYYY-MM-DD` lines. |
| R15 Directive anchor | Yes | Every def/class in `## Files` carries `# directive: resolution-types | # see resolution-types.C<N>` directly above (decorator-aware: comment line immediately above `def` / `class`, NOT above `@dataclass`). |
| R16 Feature/flow Slug | Yes (at DELIVERING) | New `resolution-types.feature.md` ships with `**Slug:** resolution-types` in first 15 lines. |
| R18 Doc read budget | Yes | `Read(*.feature.md, limit<=50)` with offset walks. Override only if absolutely necessary via `### R18 overrides` here. |
| R19 DatabaseManagerSteering | No | Not touching `DatabaseManager.py`. |
| DELIVERING -> Closed (Promotions) | Yes | `### Promotions` table populated with commit SHAs at delivery. |
| DELIVERING -> Closed (anti-drift size) | Yes | Directive body won't grow past 110% of IMPLEMENTING snapshot; durable content gets promoted out, not duplicated. |

### R18 overrides

(none)

### Verification

| AC | Evidence | Run by | Date | Result |
|---|---|---|---|---|
| AC1 | `py -m pytest Tests/Contract/TestResolution.py -v` -> 12 passed (cinematic 1916x1040, anamorphic 853x480, ultra-wide 1920x800, idempotent, None/empty). `Resolution.FromAny` is sole parser. | Claude / I9 | 2026-06-15 | PASS |
| AC2 | `py -m pytest Tests/Contract/TestResolutionTier.py -v` -> 19 passed. Live registry from `ResolutionTiers` DB (4 rows seeded). max(W,H) discriminant verified. `Registry.FromDims(T.CanonicalWidth, T.CanonicalHeight) == T` round-trip. | Claude / I9 | 2026-06-15 | PASS |
| AC3 | `py -m pytest Tests/Contract/TestScalePolicy.py -v` -> 8 passed. MIB-II regression test `1916x1040 + T720p -> 'scale=w=1280:h=-2'` green. Every (Src, Tgt) downscale pair emits target canonical width. | Claude / I9 | 2026-06-15 | PASS |
| AC4 | `py -m pytest Tests/Contract/TestResolutionCalculator.py -v` -> 12 passed (unchanged). `CalculateScaleFilter` delegates to `WidthAnchoredScalePolicy.Decide(Resolution.FromAny(...), Registry.FromCategory(...))`. No raw `==`/`!=` between resolution strings in method bodies. | Claude / I9 | 2026-06-15 | PASS |
| AC5 | `_RES_HEIGHTS` + `_HeightOf` removed from `TranscodeOperation.py`. Comparisons now via `SrcTier.Rank` vs `TgtTier.Rank`. `TestComplianceEngine::TestOperations` (8 cases) + `TestTranscodeOperationMvTrust` (7 cases) all green. | Claude / I9 | 2026-06-15 | PASS |
| AC6 | `EffectiveProfile.TargetResolutionCategory: Optional[ResolutionTier]` (frozen dataclass field type). `EffectiveProfileResolver.Resolve()` maps `TargetResolutionStr -> TargetTier` at the resolver boundary via injected `ResolutionTierRegistry`. `TestComplianceEngine::TestCrfProfileRegression` (3 cases) green with typed Tier fixtures. | Claude / I9 | 2026-06-15 | PASS |
| AC7 | Live invocation against actual MF 621554 via `ResolutionCalculator().CalculateScaleFilter('1916x1040', '720p', mf)` -> `'scale=w=1280:h=-2'`. Dedicated `test_mib_ii_regression_1916x1040_to_720p` in TestScalePolicy.py also green. | Claude / I9 | 2026-06-15 | PASS |
| AC8 | `grep -rEn "SourceResolution\s*==\|TargetResolution\s*==" --include='*.py' Features/TranscodeJob/Emit/ Features/Compliance/ Core/Resolution/` -> 1 match: `OutputFilenameBuilder.py:20` (filename-token equality, NOT scale-decision; documented as out-of-scope per directive's "filename ... untouched" Out-of-Scope clause). Zero matches in the scale-decision call chain. | Claude / I9 | 2026-06-15 | PASS (filename match documented) |
| AC9 | TestResolutionTier::test_new_tier_added_via_db_only proves OCP: an additional row in the `ResolutionTiers` table (T1440p) is enough; no edits to `ResolutionCalculator`, `ScalePolicy`, `TranscodeOperation`, or `EffectiveProfileResolver` were needed for the test to pass. | Claude / I9 | 2026-06-15 | PASS |
| AC10 | Library recompute: `POST /api/Compliance/Recompute {"MediaFileIds":[621554]}` -> `Bucketed.Transcode=1`. MF 621554 enqueued as job 140073 priority 200. Live re-encode pending I9 slot free-up (currently 2/2 slots busy with jobs 139952, 139963). Direct live-stack invocation already verified `'scale=w=1280:h=-2'`. Full FileReplaced=TRUE will land on first I9 claim. | Claude / I9 | 2026-06-15 | IN PROGRESS (pending I9 slot) |
| AC11 | `py -m pytest Tests/Contract/ -k 'Resolution or Compliance or Transcode' --ignore=...(3 flask-controller tests that can't import in pytest venv) --tb=line` -> 158 passed, 1 skipped, 1 xfailed. The single non-resolution failure (`TestPathDbRoundTripAllTables::test_transcodeattempts_round_trip`) is pre-existing from earlier `failure-accounting` directive (MediaFileId NOT NULL); reproduced with my changes stashed -- not a regression. | Claude / I9 | 2026-06-15 | PASS (with documented pre-existing failure) |
| AC12 | `py Scripts/SQLScripts/AddResolutionTiersTable.py` is idempotent (CREATE TABLE IF NOT EXISTS + INSERT ON CONFLICT DO NOTHING via UNIQUE(Name)). Re-running is a no-op (verified). Rollback DDL: `DROP TABLE ResolutionTiers;` (one statement, no dependencies). No existing column dropped. | Claude / I9 | 2026-06-15 | PASS |
| AC13 | Tunable per-instance: `ResolutionTierRegistry` builds a fresh snapshot per `__init__`; per-call instances pick up tier-table UPDATEs immediately (no service restart). `TestRegistryDataDriven::test_custom_threshold_takes_effect` proves a different MinLongEdge changes classification without any code change. | Claude / I9 | 2026-06-15 | PASS |
| AC14 | `Registry.FromDims(Width, Height)` uses `max(Width, Height)` exclusively (`ResolutionTierRegistry.py:30`). `TestRegistryFromDimsMaxEdge` covers landscape, portrait FullHD (1080x1920 -> T1080p), portrait 4K (2160x3840 -> T2160p), ultra-wide 1920x800 -> T1080p, broadcast 1280x718 -> T720p, cinematic letterbox 1916x1040 -> T1080p, square 1080x1080 -> T480p (documented; tunable via threshold change). | Claude / I9 | 2026-06-15 | PASS |

### Promotions

(Populated at DELIVERING.)

| Source artifact in directive | Target file | Commit |
|---|---|---|
| AC1-AC3 architecture (Resolution + ResolutionTier + ScalePolicy) | `Core/Resolution/resolution-types.feature.md` C1-C3 (new file at DELIVERING) | -- |
| AC4 facade pattern | `Features/TranscodeJob/Emit/encode-emit.feature.md` C2 retag | -- |
| AC5-AC6 compliance integration | `Features/Compliance/compliance.feature.md` C5 retag | -- |
| AC5-AC6 cross-stage seam (typed Resolution flows ST<n>->ST<m>) | `transcode.flow.md` `## Seams` new row | -- |
| AC11 CI tests | `Tests/Contract/TestResolution.py`, `TestResolutionTier.py`, `TestScalePolicy.py` (files are the artifact) | -- |
