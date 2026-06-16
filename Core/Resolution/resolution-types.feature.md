# Resolution Types

**Slug:** resolution-types

## What It Does

Owns every string-to-shape conversion the encode and compliance pipelines need to reason about source vs target resolution. Three frozen value objects (`Resolution`, `ResolutionTier`, `ScaleFilter`), one decision interface (`IScalePolicy` + `WidthAnchoredScalePolicy`), and one data-driven `ResolutionTierRegistry` backed by the `ResolutionTiers` DB table replace the prior string-heterogeneity bug class -- where `'1916x1040'`, `'1080p'`, `'No downscaling'`, `''`, and `None` flowed through the same `==` comparisons and silently mis-aligned. After this feature, classification is `max(W,H)`-based at a single seam, scale-filter strings are emitted by a single producer, and adding a new tier (e.g. `T1440p`) is one DB INSERT with zero code edits.

## Workflows

| #  | User action | Surface element | Handler | Backing class.method |
|----|-------------|-----------------|---------|----------------------|
| W1 | (Operator) tune a tier threshold | direct `UPDATE ResolutionTiers SET MinLongEdge = ... WHERE Name = 'T1080p'` | DB | `Core/Resolution/ResolutionTiersRepository.GetAll` (read fresh per request batch) |
| W2 | (Operator) add a new tier | direct `INSERT INTO ResolutionTiers (Name, MinLongEdge, CanonicalWidth, CanonicalHeight, Rank) VALUES (...)` | DB | `Core/Resolution/ResolutionTierRegistry.__init__` -- next batch picks it up automatically |

## Success Criteria

C1. **`Resolution` is the only string parser for resolution inputs.** `Resolution.FromAny(Value, Registry=...)` accepts `'WIDTHxHEIGHT'` (e.g. `'1916x1040'`), canonical category strings (`'480p'`/`'720p'`/`'1080p'`/`'2160p'`/`'4k'`), `(Width, Height)` tuples, an existing `Resolution` (passthrough), or `None`/`''` (returns `None`, never raises). After construction no field on the dataclass is a raw resolution string. Verifiable: `Tests/Contract/TestResolution.py` 12/12 (raw pixels, canonical category, cinematic 1916x1040 -> AspectRatio 1.842, anamorphic 853x480, ultra-wide 1920x800, idempotent, None/empty).

C2. **`ResolutionTier` is a data-driven frozen value object backed by the `ResolutionTiers` DB table.** `@dataclass(frozen=True) ResolutionTier(Name, MinLongEdge, CanonicalWidth, CanonicalHeight, Rank)`. Thresholds live in DB rows, never in code. `Core/Resolution/ResolutionTierRegistry` loads all tiers per-instance from the DB on construction (fresh per request batch; db-is-authority compliant -- no process-wide cache). Verifiable: `Tests/Contract/TestResolutionTier.py` 19/19 (boundary values, synonyms, custom thresholds via injected mock repo, OCP probe with a synthetic T1440p added by repo only).

C3. **`WidthAnchoredScalePolicy` is the SOLE producer of scale-filter strings.** `IScalePolicy.Decide(Source: Resolution, TargetTier: ResolutionTier) -> Optional[ScaleFilter]`. Returns `None` when `Source.Tier.Rank <= TargetTier.Rank` (same-tier or upscale); else returns `ScaleFilter(Width=TargetTier.CanonicalWidth, HeightExpr='-2')` whose `AsFfmpegArg()` emits `'scale=w=W:h=-2'` (aspect-preserving, codec-legal even height). Verifiable: `Tests/Contract/TestScalePolicy.py` 8/8 + 1 subtest matrix (MIB-II regression `Resolution.FromAny('1916x1040') + T720p -> 'scale=w=1280:h=-2'`; every downscale tier pair).

C4. **`ResolutionCalculator.CalculateScaleFilter` and `EncoderKnobRepository._NormalizeResolution` delegate to the typed shape.** The former composes `Resolution.FromAny` + `Registry.FromCategory` + `WidthAnchoredScalePolicy.Decide`; the latter buckets `WIDTHxHEIGHT` via `Registry.FromDims`. No raw-string `==` / `!=` comparisons on resolution values remain in the encode + compliance call chain (`grep` in `Features/TranscodeJob/Emit/`, `Features/Compliance/`, `Core/Resolution/`, `Features/Profiles/`; one filename-equality match in `OutputFilenameBuilder.py` is naming-only, not scale-decision). Verifiable: `Tests/Contract/TestResolutionCalculator.py` 12/12 + `Tests/Contract/TestEncoderKnobNormalizeResolution.py` 8/8.

C5. **`Features/Compliance/Operations/TranscodeOperation` compares via `ResolutionTier.Rank`.** The legacy inline `_RES_HEIGHTS = {...}` dict + `_HeightOf` static method are removed. The `PreventUpscale` + `ResolutionExceedsProfileTarget` rules use `SrcTier.Rank` vs `TgtTier.Rank`. `EffectiveProfile.TargetResolutionCategory` is typed `Optional[ResolutionTier]` (not `str`). Verifiable: `Tests/Contract/TestComplianceEngine.py::TestOperations` (8 cases) green; `Tests/Contract/TestTranscodeOperationMvTrust.py` (7 cases) green.

C6. **`EffectiveProfileResolver` returns a typed `TargetTier`.** `EffectiveProfileResolver.Resolve()` maps the `TargetResolution` string from `ProfileThresholds` to `ResolutionTier` via the injected `ResolutionTierRegistry` at this single boundary; `EffectiveProfile.TargetResolutionCategory: Optional[ResolutionTier]`. Legacy `'No downscaling'` is collapsed at the resolver, not inside operation code. Verifiable: field annotation + `Tests/Contract/TestComplianceEngine.py::TestCrfProfileRegression` 3/3.

C7. **Live MIB-II shape produces the right scale filter end-to-end.** `Resolution.FromAny('1916x1040')` -> `Tier=T1080p, AspectRatio=1.842`. `WidthAnchoredScalePolicy.Decide(that, T720p)` -> `ScaleFilter(1280, '-2')` -> `'scale=w=1280:h=-2'`. Verifiable: dedicated test `test_mib_ii_regression_1916x1040_to_720p` + live re-encode of MF 621554 (TranscodeAttempt 37754) -- FFmpeg argv contains `-vf "scale=w=1280:h=-2"`, output landed at `1280x694` (cinematic aspect preserved), `FileReplaced=TRUE`, size reduction 82.94%.

C8. **OCP: adding a tier is one place.** Adding a new tier (e.g. `T1440p`) requires exactly one DB row insert into `ResolutionTiers`. No edits to `ResolutionCalculator`, `ScalePolicy`, `TranscodeOperation`, `EffectiveProfileResolver`, or `EncoderKnobRepository`. Verifiable: `TestRegistryDataDriven::test_new_tier_added_via_db_only` proves a synthetic T1440p row makes `Registry.FromDims(2560, 1440).Name == 'T1440p'` with no code change.

C9. **`max(Width, Height)` is the SOLE classification discriminant.** `Registry.FromDims(W, H)` walks `_ByRankDesc` and returns the highest-rank tier whose `MinLongEdge <= max(W, H)`. Works orientation-agnostically for landscape, portrait, square, ultra-wide, and letterbox content. Verifiable: `TestRegistryFromDimsMaxEdge` (10 cases incl. portrait FullHD 1080x1920 -> T1080p, broadcast 1280x718 -> T720p, ultra-wide 1920x800 -> T1080p, MIB-II 1916x1040 -> T1080p, canonical round-trip for all four tiers).

C10. **Tier thresholds are operator-tunable via SQL.** `UPDATE ResolutionTiers SET MinLongEdge = X WHERE Name = 'T1080p'` takes effect on the next request batch (next `ResolutionTierRegistry.__init__`), no service restart, no code change. Verifiable: `TestRegistryDataDriven::test_custom_threshold_takes_effect` proves a mocked-repo threshold change reclassifies a borderline shape.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `Resolution.FromAny <- caller` | Any code holding a resolution string/tuple | `str | tuple | Resolution | None` | typed `Resolution` (or None) -- never raises | `Tests/Contract/TestResolution.py` |
| S2 | `ResolutionTierRegistry.FromDims <- caller` | Code holding raw `(Width, Height)` ints | `(int, int)` | typed `ResolutionTier` -- guaranteed non-None (falls back to lowest-rank tier on tiny inputs) | `Tests/Contract/TestResolutionTier.py::TestRegistryFromDimsMaxEdge` |
| S3 | `ResolutionTierRegistry.FromCategory <- caller` | Code holding a category-string (`'1080p'`, `'4k'`, etc.) | `Optional[str]` | typed `ResolutionTier` or `None` | `Tests/Contract/TestResolutionTier.py::TestRegistryFromCategory` |
| S4 | `WidthAnchoredScalePolicy.Decide <- ResolutionCalculator` / any encode-shape | `(Source: Resolution, TargetTier: ResolutionTier)` | `Optional[ScaleFilter]` (None on same-tier or upscale) | `Features/TranscodeJob/Emit/ResolutionCalculator.CalculateScaleFilter` -- returns `.AsFfmpegArg()` for backward-compat | `Tests/Contract/TestScalePolicy.py`, `Tests/Contract/TestResolutionCalculator.py` |
| S5 | `ResolutionTiersRepository.GetAll <- Registry` | `ResolutionTiers` DB table (4 seeded rows) | `List[ResolutionTier]` (one per row) | Registry constructor; empty list raises (signals migration not run) | `Scripts/SQLScripts/AddResolutionTiersTable.py` (idempotent) + `TestRegistryDataDriven::test_empty_table_raises` |

## Status

COMPLETE -- shipped via the `resolution-types` directive (2026-06-15).

## Scope

```
Core/Resolution/**
Scripts/SQLScripts/AddResolutionTiersTable.py
Features/TranscodeJob/Emit/ResolutionCalculator.py (CalculateScaleFilter only)
Features/Compliance/Models/EffectiveProfile.py
Features/Compliance/Services/EffectiveProfileResolver.py
Features/Compliance/Operations/TranscodeOperation.py
Features/Profiles/EncoderKnobRepository.py (_NormalizeResolution only)
```

## Files

| File | Role |
|------|------|
| `Core/Resolution/Resolution.py` | Frozen value object `Resolution(Width, Height, Tier, AspectRatio)` + `FromAny` sole string parser |
| `Core/Resolution/ResolutionTier.py` | Frozen value object `ResolutionTier(Name, MinLongEdge, CanonicalWidth, CanonicalHeight, Rank)` |
| `Core/Resolution/ResolutionTiersRepository.py` | DB-fresh read of `ResolutionTiers` table |
| `Core/Resolution/ResolutionTierRegistry.py` | Per-batch registry; `FromDims` uses `max(W, H)`; `FromCategory` maps legacy strings |
| `Core/Resolution/ScalePolicy.py` | `IScalePolicy` ABC + `WidthAnchoredScalePolicy` + `ScaleFilter` value object |
| `Scripts/SQLScripts/AddResolutionTiersTable.py` | Idempotent migration; seeds T480p / T720p / T1080p / T2160p |
| `Features/TranscodeJob/Emit/ResolutionCalculator.py` | `CalculateScaleFilter` thin facade over the policy |
| `Features/Profiles/EncoderKnobRepository.py` | `_NormalizeResolution` delegates to `Registry.FromDims` |
| `Features/Compliance/Models/EffectiveProfile.py` | `TargetResolutionCategory: Optional[ResolutionTier]` |
| `Features/Compliance/Services/EffectiveProfileResolver.py` | Maps `TargetResolutionStr -> ResolutionTier` at the resolver boundary |
| `Features/Compliance/Operations/TranscodeOperation.py` | Rank-based comparisons via `ResolutionTier` |
| `Tests/Contract/TestResolution.py` | 12 contract tests |
| `Tests/Contract/TestResolutionTier.py` | 19 contract tests (incl. data-driven OCP probe) |
| `Tests/Contract/TestScalePolicy.py` | 8 contract tests + tier-pair subtest matrix |
| `Tests/Contract/TestEncoderKnobNormalizeResolution.py` | 8 contract tests (root-cause coverage) |
