# Admission Adequacy Gate

**Slug:** admission-adequacy-gate

## What It Does

Refuses to enqueue re-encode work when the source is already at or below the lowest tier's target bitrate for its resolution. Prevents wasted CPU on already-compact sources and prevents doomed VMAF chases on sources whose bitrate is fundamentally below what the profile targets. Container/audio compliance issues still route to StreamCopy (Remux/AudioFix) -- adequacy only refuses full re-encode admission.

## Workflows

| # | User action | Surface | Handler | Backing |
|---|---|---|---|---|
| W1 | Operator adds a MediaFile via WorkBucket that turns out to already be compact | `/api/Work/<Bucket>/Queue/<mfid>` POST | WorkBucketController.queue_one -> QueueAdmissionAppService.AdmitOne -> AddJobToQueue | AdequacyGate.Evaluate short-circuits before INSERT; response Status='skipped', reason='AlreadyCompact' |
| W2 | Scanner surfaces an eligible MediaFile that AdequacyGate excludes | (internal PopulateQueueFromMediaFiles) | scanner -> AddJobToQueue | AdequacyGate.Evaluate short-circuits; MediaFile.AdequacyDecision written for audit |
| W3 | Operator toggles AdequacyGateEnabled on /settings Transcoding card | `/settings` Adequacy toggle | `PUT /api/SystemSettings/Transcoding` | `SystemSettings.AdequacyGateEnabled` UPDATE; next AdequacyGate.Evaluate observes fresh value |

## Success Criteria

C1. `Features/TranscodeQueue/AdequacyGate.py` exists with public method `Evaluate(MediaFile) -> AdequacyDecision`. `AdequacyDecision` is a dataclass `{Action: str in ('Admit','Exclude','GateDisabled','RouteToStreamCopy'), Reason: str, Notes: dict}`. Verifiable: import + call.

C2. `SourceKbps` computed at admission from `MediaFile.VideoBitrateKbps`. If `MediaFile.AssignedProfile` is a Reencode family (VBR or ICQ):
   - Look up Tier 1 TargetKbps for `(AssignedProfile.Family, ContentClass, SourceResolutionTier)`.
   - Effective threshold = `Tier1TargetKbps * (1 + AdequacyGateMarginPercent/100)`.
   - If `SourceKbps <= EffectiveThreshold` -> `Exclude(reason='CompactSource', Notes={SourceKbps, Tier1TargetKbps, EffectiveThreshold})`.
   - Else `Admit`.
   Verifiable: unit test with mocked ProfileThresholds proves the boundary.

C3. Container / audio compliance columns still consulted after adequacy: if `MediaFile.WorkBucket IN ('Remux','AudioFix')`, adequacy is skipped and StreamCopy admission proceeds (no video re-encode, but container/audio work still needed). Verifiable: unit test.

C4. `MediaFiles` schema adds `AdequacyDecision TEXT NULL`, `AdequacyDecisionAt TIMESTAMP NULL`. Every Evaluate() call that returns Exclude writes the row (through MediaFilesRepository). Admit does not write (no state change needed). Verifiable: SQL audit `SELECT COUNT(*) FROM MediaFiles WHERE AdequacyDecision IS NOT NULL AND AdequacyDecisionAt > <cutover>`.

C5. `QueueManagementBusinessService.AddJobToQueue` calls AdequacyGate.Evaluate at the start of the Reencode admission path. On Exclude, returns `{Success=True, Skipped=True, ErrorMessage='CompactSource: <SourceKbps> <= <EffectiveThreshold>'}`. Verifiable: `Tests/Contract/TestAdequacyGate.py`.

C6. `AdequacyGate.Evaluate` reads `SystemSettings.AdequacyGateEnabled + AdequacyGateMarginPercent` fresh per call (db-is-authority). OFF -> returns `GateDisabled` without evaluating. Verifiable: live-mid-flight audit -- toggle observed on next call, no restart required.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `AddJobToQueue -> AdequacyGate.Evaluate` | admission entry | `(MediaFile)` | `AdequacyDecision` VO | `TestAdequacyGate` |
| S2 | `AdequacyGate -> ProfileThresholds` | Repository lookup | `(Family, ContentClass, ResolutionTier)` | Tier 1 TargetKbps INT | unit test |
| S3 | `MediaFiles.AdequacyDecision audit` | AdequacyGate writes on Exclude | `TEXT + TIMESTAMP` | operator SQL query | SQL audit |
| S4 | `SystemSettings -> AdequacyGate (fresh read)` | operator toggle via /settings | `AdequacyGateEnabled BOOL + AdequacyGateMarginPercent NUMERIC` | Evaluate observes on next call | round-trip smoke |

## Status

Shipped 2026-07-04 via `transcode-flow-canonical` directive Reset 10 (backend) + Reset 11 (SystemSettings wiring) + Reset 14 (promoted from directive parked section at DELIVERING).

## Files

- `Features/TranscodeQueue/AdequacyGate.py` -- Evaluate + AdequacyDecision VO
- `Features/TranscodeQueue/QueueManagementBusinessService.py` -- caller wiring
- `Tests/Contract/TestAdequacyGate.py` -- 9 tests (boundaries + toggle + margin)
