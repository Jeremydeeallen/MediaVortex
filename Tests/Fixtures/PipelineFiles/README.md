# Pipeline Test Fixtures -- Permanent Bucket Samples

**Purpose:** preserve one representative media file in each WorkBucket so the E2E pipeline tests have something to chew on even after the live library is fully fixed.

## Layout

```
Tests/Fixtures/PipelineFiles/
├── Transcode/        <- a file whose VideoCompliant=FALSE (codec / resolution / savings rule fires)
├── Remux/            <- a file whose ContainerCompliant=FALSE (matroska, avi, etc.)
├── AudioFixOnly/     <- a file whose AudioCompliant=FALSE (loudness off-target)
├── Compliant/        <- a file with all three booleans TRUE (no work needed)
├── manifest.json     <- per-fixture expected properties + source provenance
└── README.md         <- this file
```

Each bucket directory contains:
- The media file itself (binary; gitignored)
- A `properties.json` per file recording: source codec, container, audio codec, expected bucket, original DB Id, capture date.

## Regenerate

When you need to refresh the fixtures (e.g. moved to a new test machine, or the live library no longer has representative violations):

```
py Tests/Fixtures/PipelineFiles/RegenerateFromLive.py
```

That script picks one small reachable MediaFile from each bucket via the existing harness fixtures (`Fixtures.TranscodeCandidate`, `Fixtures.RemuxCandidate`, `Fixtures.AudioFixOnlyCandidate`, `Fixtures.AlreadyCompliant`), copies the file in, and writes the per-bucket `properties.json`.

## Why not commit the binaries?

Even small-ish media files (200-500 MB each) would bloat the repo. The fixtures are local-to-I9 by default. To deploy them to a new test machine, run the regenerate script there OR sync the directory via rsync/scp.

## Test usage

```python
from Tests.Pipeline.Harness import PermanentFixtures

LocalPath = PermanentFixtures.GetFixtureFile('Transcode')
Props = PermanentFixtures.GetProperties('Transcode')
assert Props['ExpectedBucket'] == 'Transcode'
```

Tests register a temporary RootFolder pointing at the fixture's parent, run the pipeline, assert post-state, and clean up DB rows. The fixture file is left intact for the next test run.
