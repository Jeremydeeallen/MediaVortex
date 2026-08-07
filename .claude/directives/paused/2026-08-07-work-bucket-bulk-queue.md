# Directive: work-bucket-bulk-queue

**Slug:** work-bucket-bulk-queue
**Status:** Paused -- awaiting bug-0087-audio-per-stream-channels + follow-on transcode failure classes
**Opened:** 2026-08-07
**Paused:** 2026-08-07 -- pre-code (NEEDS_STANDARDS_REVIEW); transcode-failure fires took priority

## Ask

Operator has ~5,700 files pending across 3 work-needed buckets. Current `/Work/<bucket>` UI groups by series (first path segment) and forces one Queue-All click per series. Fine for TV; useless for Movies/Adult where each file = its own 1-file "series". At ~5,700 clicks the operator will not do it.

Add a tiny bulk-queue section at the top of `/Work/Transcode`, `/Work/Remux`, `/Work/Audio`. Three controls + one button:

```
[Source: TV | Movies | Adult]  [Tier: 1 | 2 | 3 | 4 | 5]  [Queue All]
```

Click = admit every MediaFile in `WorkBucket=<bucket>` AND `StorageRootId=<source>` at the chosen QualityTier. Result reported as tally flash.

## Domain Decisions

**DD1. Source discriminator = `MediaFiles.StorageRootId`.** Three StorageRoots exist (id=1 media_tv "TV", id=2 movies "Movies", id=3 xxx "Adult"). Path-prefix classification is already resolved -- MediaFiles carries the FK. No new column, no path parsing.

**DD2. Tier = existing `QualityTier` param on `AdmitOne`.** Admission already accepts `QualityTier: int` (routed to `queue_one` via `?tier=<n>` query param). Tier drives the AV1 profile family selection at admission time. Bulk = loop over N MediaFiles calling the same `AdmitOne`. Zero new admission logic.

**DD3. KISS scope -- 3 controls, no preview count.** Section renders 3 controls + button. No live "(N files pending)" counter on source-change. Result tally lands in flash after click. Preview count is a follow-up if operator asks.

**DD4. Additive to existing UI.** Existing Drive multi-select filter + series-grouping table stay untouched. Bulk section sits ABOVE the existing toolbar. No behavior change to any current path.

**DD5. Applies to work-needed buckets only.** Transcode / Remux / Audio get the section. Compliant + Unclassified do NOT (Compliant is browse/audit-only per work-bucket.feature.md; Unclassified action is force-decide, not admit).

**DD6. Admission idempotence preserved.** Existing `AdmitOne` returns Status ∈ {queued, already_queued, skipped, error}. Bulk sums each status into the tally. A second Queue-All click on the same source+tier reports high `AlreadyQueued`, zero `Inserted`.

## Fix shape

Add one bulk-admit route + one app-service method + one template section + one contract test. Pure add; no edits to existing admission or query paths.

## Success Criteria

C1. **New endpoint present.** `POST /api/Work/<bucket>/BulkQueue` accepts JSON body `{StorageRootId: int, QualityTier: int}`. Returns `{Success, Message, Data: {Inserted, AlreadyQueued, Skipped, AdmissionDeferred, Errored, Total}}`. Verifiable: `Tests/Contract/TestWorkBucketBulkQueue.py::test_route_registered`.

C2. **Bulk admission calls `AdmitOne` per file.** `QueueAdmissionAppService.AdmitBulk(Bucket, StorageRootId, QualityTier)` queries `SELECT Id FROM MediaFiles WHERE WorkBucket=%s AND StorageRootId=%s` and calls `self.AdmitOne(Id, Bucket, QualityTier=<n>)` for each. No inline SQL INSERT bypass; existing admission policy is the sole gate.

C3. **Tally sums to Total.** `Inserted + AlreadyQueued + Skipped + AdmissionDeferred + Errored == Total`. Same invariant as C9 of work-bucket.feature.md. Verifiable: contract test asserts arithmetic across a mixed-state fixture.

C4. **Idempotence.** Second call with identical (Bucket, StorageRootId, QualityTier) returns `Inserted=0`, `AlreadyQueued=<N-of-first-call>` (assuming no state churn between). Verifiable: contract test.

C5. **Section renders on all 3 work-needed buckets.** `/Work/Transcode`, `/Work/Remux`, `/Work/Audio` all show the section. `/Work/Compliant` + `/Work/Unclassified` do NOT. Verifiable: template conditional on `Bucket.AllowsBulkQueue` (added to `BucketKey`).

C6. **Source dropdown populated from `/api/StorageRoots`.** Reuses existing endpoint. Options: `TV` (id=1) / `Movies` (id=2) / `Adult` (id=3). No hardcoded ids in template -- id + label come from the API.

C7. **Tier dropdown = 1..5.** Static (matches `AV1 Tier 1..5` profile-family vocab). Hardcoded is fine per KISS -- tiers are a stable enumeration, not a tuning surface.

C8. **feature.md updated in DELIVERING.** `work-bucket.feature.md` gains W8 (Bulk queue by source+tier), C11 (bulk-admit contract), S6 (Controller -> AdmitBulk seam). DD1-DD6 promoted.

C9. **Live smoke on I9.** After code lands + I9 restart: (a) hit `/Work/Transcode`, verify section renders with 3 controls; (b) click Queue All with Source=Movies, Tier=2, observe tally flash; (c) verify N=<some non-zero> Movies files transitioned to `TranscodeQueue.Status='Pending'` via SQL.

## Files

**Edit:**
- `Features/WorkBucket/WorkBucketController.py` -- add `bulk_queue` route
- `Features/WorkBucket/Services/QueueAdmissionAppService.py` -- add `AdmitBulk` method
- `Features/WorkBucket/Domain/BucketKey.py` -- add `AllowsBulkQueue` property (True for Transcode/Remux/Audio, False for Compliant/Unclassified)
- `Templates/WorkBucket.html` -- add bulk section conditional on `Bucket.AllowsBulkQueue`
- `Features/WorkBucket/work-bucket.feature.md` -- add W8 + C11 + S6 + Design Decisions section (at DELIVERING)

**Create:**
- `Tests/Contract/TestWorkBucketBulkQueue.py` -- route + tally + idempotence

**Delete:** (none)

## Call-Graph Audit

- **Signal 1 (multiple flow docs):** N/A -- WorkBucket is a UI vertical, no flow doc. Admission goes through `QueueManagementBusinessService.AddJobToQueue` (transcode.flow.md ST0/ST1); bulk reuses that path unchanged.
- **Signal 2 (orchestration mode-branch):** `AdmitBulk` is a pure loop over `AdmitOne`; no `if source == X` branching in orchestration. Source is a WHERE-clause filter (data), not a shape decision (orchestration).
- **Signal 3 (mode-sparse output columns):** N/A -- no new columns written.
- **Signal 4 (OOS ambiguity):** all OOS items categorized (a) below.
- **Signal 5 (config-driven graph shape):** section visibility gated on `BucketKey.AllowsBulkQueue` -- static property of the bucket, not runtime config. Same functions get called regardless; only which buckets render the section changes.

## Out of Scope

- **(a) In-flight preserved:** existing series-grouping table + Drive multi-select filter + Sort dropdown -- unchanged.
- **(a) In-flight preserved:** existing `AdmitSeries` (Queue-all-in-series button) + `AdmitOne` (per-row Queue button) -- unchanged, reused by AdmitBulk.
- **(a) In-flight preserved:** `/Work/Compliant` + `/Work/Unclassified` -- bulk section does NOT render there.
- **(a) In-flight preserved:** live "(N pending)" count preview on source-change -- deferred (DD3); ship without.
- **(a) In-flight preserved:** progress bar / streaming during bulk admit -- deferred; response is synchronous. If bulk of 5,700 exceeds request timeout, revisit; for now the AdmitOne loop runs in one request.

## Phase machine

NEEDS_STANDARDS_REVIEW -> NEEDS_PLAN -> NEEDS_DOC_PREREAD -> IMPLEMENTING -> VERIFYING -> DELIVERING

### Progress

- [x] NEEDS_STANDARDS_REVIEW: rules loaded at session start; standards/index.md read
- [ ] NEEDS_PLAN: criteria + Files + Call-Graph Audit + Domain Decisions locked (this doc)
- [ ] NEEDS_DOC_PREREAD: read `work-bucket.feature.md` (already read at limit=50 above; walk remainder)
- [ ] IMPLEMENTING: BucketKey.AllowsBulkQueue property
- [ ] IMPLEMENTING: QueueAdmissionAppService.AdmitBulk method
- [ ] IMPLEMENTING: WorkBucketController bulk_queue route
- [ ] IMPLEMENTING: WorkBucket.html bulk section
- [ ] IMPLEMENTING: TestWorkBucketBulkQueue contract test
- [ ] VERIFYING: contract test PASS; existing work-bucket tests still green
- [ ] SMOKE-GATE: I9 restart; /Work/Transcode renders section; Queue-All Movies+Tier2 lands rows
- [ ] DELIVERING: feature.md updates (W8/C11/S6/DD promotions); close report

### R13 overrides

(none anticipated -- no new *.feature.md / *.flow.md file created; only edits)

### R18 overrides

(none anticipated -- feature docs read with limit=50)

### Promotions

| Source (directive) | Target (durable) |
|---|---|
| DD1-DD6 | `Features/WorkBucket/work-bucket.feature.md` -- new Design Decisions section |
| W8 (Bulk queue by source+tier) | `work-bucket.feature.md` -- Workflows table |
| C11 (Bulk-admit contract) | `work-bucket.feature.md` -- Success Criteria |
| S6 (Controller -> AdmitBulk) | `work-bucket.feature.md` -- Seams table |
