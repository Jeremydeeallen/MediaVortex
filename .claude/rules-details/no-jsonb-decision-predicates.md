# No JSONB Decision Predicates

Boolean decision signals derive from typed columns, not JSONB containment probes over shared blobs written by more than one hand.

## The rule

If code makes a decision based on "does this JSONB blob contain key X?", the design is wrong. Convert to:

1. Typed column on the same row (BOOL / INT / TEXT).
2. Single writer at a known point in the pipeline.
3. Single reader via `SELECT <column>`.

JSONB `@>` containment probes are legitimate for FILTERING (operator SQL, ad-hoc analysis, dashboards). They are ILLEGITIMATE for control-flow gating in production code.

## Why

- **Predicate drift.** The literal predicate string (`'[{"key": true}]'`) gets duplicated at every reader site. When the writer changes shape, every reader silently returns false. No compile-time or type-time catch.
- **Two-writer merge race.** Once one JSONB blob has more than one writer, ordering matters. Later writers can stomp earlier writers' keys. Zero warning.
- **DDD violation.** Attempt-level facts do not belong in a per-track JSON array. The column shape IS the domain shape.
- **Query cost.** `@>` requires GIN index or seq-scan of the JSON blob. Boolean column read is 1 byte + indexable.

## Failure pattern this rule closes

`dialog-boost-marker-unify` (2026-08-22): two writers stamped keys into `TranscodeAttempts.AudioTracksEmittedJson`. `_PersistAttestation` (per-track ebur128) overwrote `PersistPreEncodeMeta` (Dialog Boost + Demucs breadcrumbs) when it ran last. Three reader sites (`ComplianceGate.py`, `TranscodedOutputPlacement.py`, `AddHasDialogBoostTrack_2026_08_13.py`) queried `AudioTracksEmittedJson::jsonb @> '[{"dialog_boost_emitted": true}]'::jsonb`. Key stomped -> probe returned FALSE -> compliance gate refused -> `HasDialogBoostTrack` written FALSE -> infinite re-queue loop. 62 failures / 24 h, 6,505 files stuck. Fix: `TranscodeAttempts.DialogBoostEmitted BOOL` column, one writer, one reader.

## When this rule applies (PR triggers)

- Adds `::jsonb @>` in production code (`Features/`, `Workers/`, `WorkerService/`, `Core/`) where the result gates a decision (if/else, return value, disposition).
- Adds a JSON key that a reader will probe for containment.
- Adds a second writer to an existing JSONB blob that another writer already populates.

## Enforcement

Judgment gate per `.claude/standards/index.md` "What is NOT gated". Reviewer flags at NEEDS_STANDARDS_REVIEW.

`Tests/Contract/TestDialogBoostMarkerCanonical.py` mechanically greps for one instance of the pattern (`AudioTracksEmittedJson::jsonb @>`); expand to other blobs if the pattern regrows elsewhere.

## Related

- `.claude/rules/db-is-authority.md` -- DB is SoT; boolean state lives in columns.
- `.claude/rules/writer-owns-cascade.md` -- single writer per derived state; two-writer merges violate the invariant.
- `.claude/rules/fail-loud.md` -- silent try/except around a broken JSONB probe masks the drift.
