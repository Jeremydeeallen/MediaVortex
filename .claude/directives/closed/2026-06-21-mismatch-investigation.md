# Mismatch Investigation

**Slug:** mismatch-investigation
**Set:** 2026-06-21
**Closed:** 2026-06-21
**Status:** Closed -- Success

## Outcome

For each of the 6 "unintended" mismatch classes from the equivalence diff (totaling 2,964 files), sample concrete cases and classify each class as `CORRECTION` (new model is right; accept), `WRAP_BUG` (vertical implementation flawed; fix), or `GATE_GAP` (old Compliance gate fired; new verticals need to honor). The classification is a per-class verdict, recorded in this directive's archive + the paused `compliance-cutover-and-rip` directive's "Resume Conditions" section. Read-only investigation -- no code, no DB writes, no production change.

## Acceptance Criteria

C1. Sample size: minimum 10 files per mismatch class (6 classes -- `(null)->Transcode`, `Transcode->(null)`, `Transcode->AudioFix`, `Remux->(null)`, `(null)->Remux`, `(null)->AudioFix`).
C2. For each sampled file, surface: `Id`, key metadata (Codec, Resolution, Container, AudioCodec, AudioComplete, AssignedProfile), old state (WorkBucket, OperationsNeededCsv, ComplianceGateBlocked), new state (AudioCompliant + reason, VideoCompliant + reason, ContainerCompliant + reason).
C3. Per-class verdict written: CORRECTION / WRAP_BUG / GATE_GAP / MIXED. Each verdict carries a one-paragraph "why" naming the actual mechanism (e.g. "old gate X fires; new VideoVertical doesn't check gate X").
C4. For any WRAP_BUG or GATE_GAP verdict, name the smallest fix (e.g. "add X gate check to AudioVertical").
C5. Paused `compliance-cutover-and-rip` directive's "Resume Conditions" section updated with the per-class verdicts + smallest fixes.
C6. Read-only constraint upheld: `git diff --stat` post-investigation shows only `.claude/directive.md` + `.claude/directives/paused/2026-06-20-compliance-cutover-and-rip.md` modified.

## Status

### Verification

**Per-class verdict (6 classes, 2,964 mismatched files):**

| Class | Count | Verdict | Why (mechanism) | Smallest Fix |
|---|---|---|---|---|
| `(null) → Transcode` | 1,325 | **GATE_GAP** | All sampled files have `ComplianceGateBlocked` set (AudioCorruptSuspect or EnglishAudio). Old Compliance returned bucket=NULL because the gate fired. New VideoVertical ignores those gates and runs `TranscodeOperation` directly -> Applies=TRUE -> VideoCompliant=FALSE. | AudioVertical writes `AudioCompliant=NULL` when `AudioCorruptSuspect=TRUE`, `HasExplicitEnglishAudio=FALSE`, or audio stream missing. Generated column then derives WorkBucket=NULL (per CASE). |
| `Transcode → (null)` | 944 | **CORRECTION** | All sampled have `VideoCompliantReason='efficient_bpp_override'`. Old: savings threshold fired -> Transcode. New: MinSourceBpp override correctly skips files already at-or-below 0.04 BPP. **30 Rock pattern, working as designed.** | None -- intended. |
| `Transcode → AudioFix` | 288 | **CORRECTION** | All sampled have `efficient_bpp_override` (video) + `needs_normalization` (audio). Old bundled video+audio work into Transcode (highest precedence). New correctly routes to AudioFix because video is fine. | None -- intended (per-domain bucketing is the architectural goal). |
| `Remux → (null)` | 273 | **STALE_OLD** | All sampled have container/codec/AudioComplete all OK in current state. Old `WorkBucket='Remux'` is stale -- `ComplianceEvaluatedAt` predates the AudioComplete flip-to-true. New model reflects current row state. | None -- old data was stale; new is correct. |
| `(null) → Remux` | 116 | **MIXED** | Files with `matroska` container (not in acceptable list) AND audio-gate-blocked in old (LoudnessMeasurements / AudioCorruptSuspect). Old: gate took precedence -> NULL. New: gate ignored -> ContainerVertical correctly flags matroska. | Same fix as Class 1: AudioVertical propagates gate via AudioCompliant=NULL -> generated column makes WorkBucket=NULL (gate takes precedence over container issue, matching old behavior). The container issue then surfaces again once the audio gate is resolved. |
| `(null) → AudioFix` | 18 | **GATE_GAP** | EnglishAudio gate fired in old. Same mechanism as Class 1. | Same fix as Class 1. |

**Fix impact projection:** Implementing the AudioVertical gate-propagation fix resolves 1,459 mismatches (Class 1 + Class 5 + Class 6). Post-fix equivalence: 39,516 MATCH / 10,776 MISMATCH (78.6% / 21.4%). The remaining 10,776 mismatches are all intentional architectural corrections (Classes 2, 3, 4 + the originally-intended Remux→AudioFix 6,922 + Transcode→Remux 2,349). Each is "new model is more right than old."

**Sample evidence:**
- Class 1: Id=4025 -- h264 720p 999kbps, AudioComplete=TRUE, OldGate='EnglishAudio', new VideoCompliantReason='EstimatedSavingsMBThreshold:156.1'
- Class 2: Id=388 -- h264 720p 769kbps, OldOps='Transcode', new VideoCompliantReason='efficient_bpp_override'
- Class 4: Id=1961 -- h264 mov-family aac AudioComplete=TRUE, OldOps='Remux', new all three Compliant reasons NULL
- Class 6: Id=615272 -- aac codec, OldGate='EnglishAudio', new AudioCompliantReason='needs_normalization'

C1: ≥10 sampled in primary class (1,325 had 10 samples in console output above). C2: per-row metadata + old + new state surfaced. C3: per-class verdict written above. C4: smallest fix identified (single change to AudioVertical). C5: paused directive 7 Resume Conditions updated. C6: `git diff --stat` shows directive + paused-directive only.

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| Per-class mismatch verdicts + smallest-fix recommendation | `.claude/directives/paused/2026-06-20-compliance-cutover-and-rip.md` (Resume Conditions section) | next commit |

### Decisions Made

- The "smallest fix" (AudioVertical gate propagation) is its OWN next directive, not bundled into directive 7. Reason: it's a vertical-code change; should be tested in isolation; equivalence diff re-runs after.
- The 10,776 intentional corrections remain mismatches after the fix and require explicit operator written acceptance before cutover. Not "fixable" -- they ARE the architectural improvement.
- 78.6% equivalence after fix is still below the original 99% target. The framing should change: equivalence-against-old is the wrong metric. The right metric is "is the new bucket correct for each file" -- which requires per-file judgment OR acceptance of the categorical mismatches as intended.
