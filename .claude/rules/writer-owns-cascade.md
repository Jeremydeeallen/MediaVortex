# Writer-Owns-Cascade

Every write to a compliance-input column recomputes its derived downstream state in the same call, before returning. Deferred recompute is refused.

## The invariant

MediaFiles has three tiers of state:

1. **Source-of-truth columns** -- written by their authoritative producer (scan writes `filesize`/`filemodificationtime`; probe writes `Resolution`/`Codec`/`VideoBitrateKbps`/...; classifier writes `AssignedProfile`).
2. **Derived state columns** -- computed FROM source-of-truth columns (`VideoCompliant`, `AudioCompliant`, `ContainerCompliant`, `IsCompliant`, `WorkBucket`).
3. **Aggregate state** -- computed FROM derived state (queue admission, /Work bucketing).

Any write to a tier-1 column that another tier's derivation reads MUST recompute the tier-2 derivations for that row in the same function call, before returning. Tier-3 aggregates are trigger-derived from tier-2 and require no explicit call.

## The compliance-input columns (writers of these must cascade)

| Column | Read by | Cascade target |
|---|---|---|
| `Resolution` / `ResolutionCategory` | `VideoVertical.Evaluate` | `RecomputeForFiles([Id])` |
| `Codec` | `VideoVertical.Evaluate` / `ContainerVertical.Evaluate` | same |
| `VideoBitrateKbps` | `VideoVertical.Evaluate` | same |
| `AudioCodec` / `AudioChannels` / `AudioBitrateKbps` | `AudioVertical.Evaluate` | same |
| `ContainerFormat` | `ContainerVertical.Evaluate` | same |
| `AudioLanguages` / `HasExplicitEnglishAudio` | `AudioVertical.Evaluate` | same |
| `AssignedProfile` | `VideoVertical.Evaluate` (post `video-compliance-multiplier` 2026-07-26) | same |
| `SourceIntegratedLufs` / `SourceLoudnessRangeLU` / `SourceTruePeakDbtp` | `AudioVertical.Evaluate` (loudness gate) | same |
| `TranscodedByMediaVortex` | `VideoVertical.Evaluate` (mv-output-accepted branch) | same |

The cascade target is a single call: `QueueManagementBusinessService().RecomputeForFiles([MediaFileId])`. Phase 1 (three verticals write booleans; trigger derives WorkBucket) + Phase 2 (re-fetch + compute profile + priority + AudioFix folder pin + bulk UPDATE) as documented in that function.

## What is forbidden

- Writing any column above WITHOUT calling `RecomputeForFiles` before the writer returns.
- Deferring the recompute to a periodic sweeper.
- Guarding the recompute on "did the value actually change" -- always cascade; RecomputeForFiles is idempotent + cheap for unchanged inputs.
- Silent try/except around the cascade call (per `fail-loud.md`); if RecomputeForFiles raises, the writer raises too.

## When this rule applies (PR triggers)

- Adds or edits any function whose body UPDATEs `MediaFiles.<compliance-input-column>` (see table above).
- Adds a new column to any `*ComplianceRules` table that a vertical reads.
- Adds a new writer to an existing compliance-input column (new endpoint, new batch script, new worker path).

If your PR touches any of the above, run `py -m pytest Tests/Contract/TestWriterOwnsCascadeEnforcement.py` and confirm the check passes.

## Related

- `.claude/rules/db-is-authority.md` -- DB is SoT for runtime state; cascade preserves consistency of derived state.
- `.claude/rules/fail-loud.md` -- cascade errors propagate; do not swallow.
- `.claude/rules/ceo-mode.md` -- ProbeStage owns making derived state consistent with the columns it just wrote (Domain Decision).
- `ingest.flow.md` -- pipeline ordering (scan -> probe -> classifier -> compliance -> workbucket) ensures each writer sees populated inputs.

**Details, common failure modes, and the Full Circle S1 case study:** see `.claude/rules-details/writer-owns-cascade.md`.
