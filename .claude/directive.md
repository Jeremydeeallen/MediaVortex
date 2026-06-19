# Current Directive

**Set:** 2026-06-18
**Status:** Active -- phase: IMPLEMENTING
**Slug:** work-bucket-landing-pages

## Outcome

The three top-nav items (Transcode | Remux | Audio) currently dump to
the same `/TranscodeQueue` page. They need distinct landing pages
showing files needing each specific WorkBucket.

## Acceptance Criteria

**W1.** Three distinct routes exist:
  - `/Work/Transcode` -> files with WorkBucket='Transcode'
  - `/Work/Remux` -> files with WorkBucket='Remux'
  - `/Work/Audio` -> files with WorkBucket='AudioFixOnly'

**W2.** Each page renders a single shared `WorkBucket.html` template
with WorkBucket-specific title + helper text. The template shows:
  - Total count + a hint of how many are already queued
  - Paginated list (50 per page) of MediaFiles: Id, FileName, Resolution,
    AudioCodec, AudioLanguages, SourceIntegratedLufs, OperationsNeededCsv
  - One Action button per row: "Queue now" (inserts a transcodequeue row
    with the matching ProcessingMode if not already queued).

**W3.** Backend API:
  - `GET /api/Work/<bucket>?offset=N&limit=M` returns
    `{Total, AlreadyQueued, Rows:[...]}`.
  - `POST /api/Work/<bucket>/Queue/<id>` inserts a transcodequeue row
    for that MediaFile with the corresponding ProcessingMode; idempotent
    (returns 200 + "already queued" if a Pending row already exists).

**W4.** Top-nav links point to the three new routes (not to
`/TranscodeQueue`).

## Files

```
.claude/directive.md                                                 -- EDIT
Features/WorkBucket/__init__.py                                      -- CREATE
Features/WorkBucket/WorkBucketController.py                          -- CREATE: routes + API
Features/WorkBucket/WorkBucketRepository.py                          -- CREATE: SELECT by WorkBucket + queue-insert
Features/WorkBucket/workbucket.feature.md                            -- CREATE
Templates/WorkBucket.html                                            -- CREATE: single template per bucket
Templates/Base.html                                                  -- EDIT: nav links point to /Work/<bucket>
WebService/Main.py                                                   -- EDIT: register the blueprint
Tests/Contract/TestWorkBucketRepository.py                           -- CREATE
```

## Status

### Progress

- [ ] W1 routes
- [ ] W2 template
- [ ] W3 API
- [ ] W4 nav links

### Promotions

[Populated at DELIVERING phase]
