# Current Directive

**Set:** 2026-06-19
**Status:** Active -- phase: IMPLEMENTING
**Slug:** h1-operator-control

## Outcome

Auto-heal (H1 self-healing daemon) is currently uncontrollable from the
GUI. Only kill-switch is "stop WebService." Operator's tunables
principle (feedback_no_hardcoded_values + db-is-authority) demands
every knob be DB-driven and GUI-editable. Ship that surface NOW.

Operator instruction: ship now; default DISABLED in DB.

## Acceptance Criteria

**H1G1.** Two new tables:
- `AudioVerticalHealthConfig` (single-row master): Enabled BOOL DEFAULT
  FALSE (off-by-default per operator instruction), IntervalSec INT
  DEFAULT 300, RemediationBatch INT DEFAULT 100, LastUpdated TIMESTAMP.
- `AudioVerticalHealthInvariantConfig` (one row per invariant):
  InvariantName TEXT PRIMARY KEY, Enabled BOOL DEFAULT TRUE,
  BatchSizeOverride INT NULL, LastUpdated TIMESTAMP. Seeded with the
  six current invariant names.

**H1G2.** `AudioVerticalHealthService.RunCycle()` reads BOTH tables
fresh per cycle (db-is-authority). If master Enabled=FALSE, writes
ONE skip-audit row and returns immediately without touching any
invariant. If per-invariant Enabled=FALSE, that invariant is skipped
with a "disabled" Notes line. Per-invariant BatchSizeOverride wins
over master RemediationBatch when set.

**H1G3.** New API:
- `GET /api/AudioNormalization/SelfHealing/Config` -> master + per-invariant
- `POST /api/AudioNormalization/SelfHealing/Config` -> update master
- `POST /api/AudioNormalization/SelfHealing/Invariant` -> update one invariant

**H1G4.** New "Self-Healing" tab on `/AudioNormalization`:
- BIG red "Auto-heal is OFF" banner when master Enabled=FALSE;
  big green "Auto-heal is RUNNING" when TRUE
- Master toggle (Enabled), IntervalSec input, RemediationBatch input
- Per-invariant rows: Name, Enabled toggle, BatchSizeOverride input
- Save button per row; reload after each save

**H1G5.** On WebService startup, the H1 background thread starts but
the FIRST cycle inspects Enabled=FALSE and no-ops. No restart needed
when operator flips Enabled.

**H1G6.** Migration applied; verified DB state shows
`AudioVerticalHealthConfig.Enabled = FALSE` and the six invariant rows
seeded with Enabled=TRUE.

## Files

```
.claude/directive.md
Scripts/SQLScripts/CreateAudioVerticalHealthConfig.py                                 -- CREATE migration
Features/AudioNormalization/SelfHealing/AudioVerticalHealthConfigRepository.py        -- CREATE: read/write helpers
Features/AudioNormalization/SelfHealing/AudioVerticalHealthService.py                 -- EDIT: master + per-invariant gates
Features/AudioNormalization/AudioNormalizationController.py                           -- EDIT: 3 new endpoints
Templates/AudioNormalization.html                                                     -- EDIT: Self-Healing tab
Tests/Contract/TestAudioVerticalHealthService.py                                      -- EDIT: master-disable test
Tests/Contract/TestAudioVerticalHealthConfig.py                                       -- CREATE: per-invariant test
```

## Status

### Progress

- [ ] H1G1 schema + migration
- [ ] H1G2 RunCycle gating
- [ ] H1G3 API
- [ ] H1G4 UI
- [ ] H1G5 startup verified
- [ ] H1G6 disabled by default verified

### Promotions

[Populated at DELIVERING phase]
