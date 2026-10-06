# Bucket rules -- phase 2

Opened 2026-10-06 alongside `tv-video-rule-tier1` (phase 1). Each row is its own directive, in this order. Phase 1 is not "bucket rules done" until row 1 lands -- that row removes the two-path video rule phase 1 leaves behind.

| # | Slug | What | Blocked on |
|---|---|---|---|
| 1 | `movies-xxx-video-rule` | Give Movies and XXX a library tier model (Movies vary by genre: romcom Tier 1, action Tier 2-3). Delete the profile-target + codec-match path from `VideoVertical.Evaluate` so one rule serves every library. | Operator domain session on Movies / XXX tiers |
| 2 | `queue-tier-no-profile-rewrite` | Bulk-queue selector defaults to Tier 2 and `AddJobToQueue` permanently rewrites `MediaFiles.AssignedProfile` with no source tag and no recompute (`Templates/WorkBucket.html:24`, `QueueManagementBusinessService.py` ~1927-1938). Per-series override is the only sanctioned way to move a TV file off the library tier. | -- |
| 3 | `bucket-rules-display` | `/Work/<bucket>` header renders that bucket's rule with live numbers from one read endpoint; readable per-file reason; `/Admin/Compliance` gets the video rule. | Row 1 for the all-library version; TV-only version can ship earlier |
| 4 | `compliance-gate-fail-loud` | BUG-0106 suspect A: two silent `except Exception: pass` blocks in `Features/FileReplacement/ComplianceGate.py`, regex-scrape of the ffmpeg command for audio languages, hand-rolled candidate row. | -- |
| 5 | `iscompliant-terminal-parity` | Generated `IsCompliant` lacks the `TranscodedByMediaVortex AND HasDialogBoostTrack` branch `WorkBucket` has; the two can disagree. BUG-0106 suspect B query belongs here. | -- |
| 6 | `audio-vertical-pure-evaluate` | `AudioVertical.Evaluate` writes (remeasure mark, review queue) while evaluating; loads two loudness targets it never reads. | -- |
| 7 | `stale-compliance-tests` | Contract tests asserting shapes the code no longer has: `TestAudioComplianceBar.py`, `TestWorkBucketDerivation.py`, `TestCrossVerticalLeak.py`, `TestComplianceIdempotency.py`, `TestE2EPerBucket.py`, `TestWorkBucketMvTerminal.py`. | -- |
| 8 | `tier-ladder-truth` | Tier 1 1080p / 2160p `TargetKbps` cells are never encoded from (tier outputs 720p). Ladder and multiplier edits on `/settings` leave no audit trail and do not recompute verdicts -- the 2026-09 Tier 1 720p 900 -> 1000 change had to be dated from ffmpeg commands. | -- |
| 9 | `failure-classes-settings-tab` | `bug-0095-failure-classification` closed 2026-10-06 with the `/settings` FailureClasses tab unbuilt (API shipped). | -- |
