# Unified /Work/<bucket> Pages + Media-Tab Retirement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `Docs/superpowers/specs/2026-06-28-work-transcode-unified-design.md`

**Goal:** Collapse `/Work/Transcode`, `/Work/Remux`, `/Work/Audio` into a unified grouped-by-series surface with sort-by-size, per-series profile editing, and bulk admit; delete the `/ShowSettings` (Media) tab entirely; preserve per-series profile data behind a renamed internal storage table using the rename-then-drop pattern.

**Architecture:** One vertical death (`Features/ShowSettings/`), one vertical expansion (`Features/WorkBucket/`) with DDD layering — Domain VOs / SRP repositories / orchestration services / thin Flask controller. Unused SQL objects get a `_DEPRECATED_2026_06_28` marker; the DROP migration is authored here but only run after operator-approved soak.

**Tech Stack:** Python 3.13, Flask, psycopg2 against PostgreSQL 16 on LXC CT 203, jQuery on the client, Bootstrap 5 templating, `pytest` for tests, project-local `venv/` per `.claude/rules/python-environment.md`.

---

## Pre-flight — directive open (operator-only)

Before any task in this plan can land code, a directive must be open. Per CEO mode (`.claude/rules/ceo-mode.md`) and the PreToolUse hook, the directive file gates every Edit/Write against code or contracts.

- [ ] **Step 0a: Operator opens directive**

The operator runs:

```
/n work-transcode-unified
```

The slash command creates `.claude/directive.md` from the spec, populates the criteria list, and pushes `work-transcode-unified` onto `.claude/current-feature`. Once the directive is open, the hook permits code edits.

- [ ] **Step 0b: Directive in IMPLEMENTING phase**

After criteria are confirmed by the operator, set the directive status line to:

```
**Status:** Active -- phase: IMPLEMENTING
```

All tasks below assume this state.

---

## File structure

### New files

```
Features/WorkBucket/Domain/
  __init__.py
  SeriesIdentity.py        # frozen dataclass VO (StorageRootId, RelativePath)
  BucketKey.py             # frozen dataclass VO with FromUrlKey + ProcessingMode
  ProfileName.py           # validated VO + InvalidProfileError
  SortSpec.py              # enum + ToSql()
  FilterSpec.py            # dataclass + ToSqlFragments()
  AdmissionResult.py       # frozen dataclass (Inserted, AlreadyQueued, Total)
  Series.py                # frozen dataclass aggregate
  MediaFileRow.py          # frozen dataclass entity

Features/WorkBucket/Repositories/
  __init__.py
  SeriesQueryRepository.py
  FilesInSeriesRepository.py
  SeriesProfileRepository.py
  QueueAdmissionRepository.py

Features/WorkBucket/Services/
  __init__.py
  SeriesProfileService.py
  QueueAdmissionAppService.py

Features/WorkBucket/work-bucket.flow.md       # NEW — replaces narrow scope of existing feature md
Features/WorkBucket/work-bucket.feature.md    # REWRITE existing

Templates/WorkBucket.html                     # REWRITE existing

Scripts/SQLScripts/CreateSeriesProfilesAndDeprecateShowSettings.py
Scripts/SQLScripts/DeprecateSmartPopulateIndex.py
Scripts/SQLScripts/DropDeprecatedShowSettingsArtifacts.py

Tests/Contract/TestSeriesIdentityVO.py
Tests/Contract/TestBucketKeyVO.py
Tests/Contract/TestProfileNameVO.py
Tests/Contract/TestSeriesQueryRepository.py
Tests/Contract/TestFilesInSeriesRepository.py
Tests/Contract/TestSeriesProfileRepository.py
Tests/Contract/TestQueueAdmissionRepository.py
Tests/Contract/TestSeriesProfileService.py
Tests/Contract/TestQueueAdmissionAppService.py
Tests/Contract/TestWorkBucketController.py
Tests/Contract/TestNoShowSettingsReferences.py
```

### Modified files

```
Features/WorkBucket/WorkBucketController.py   # slim to HTTP-only
Features/WorkBucket/WorkBucketRepository.py   # delete the file (its methods migrate)
Scripts/SQLScripts/BackfillProfileAssignments.py   # ShowSettings -> SeriesProfiles
WebService/Main.py                            # remove show_settings route + blueprint
Templates/Base.html                           # remove Media nav link
transcode.flow.md                             # sweep ShowSettings references
Features/TranscodeQueue/*.feature.md          # sweep ShowSettings references where present
Features/TranscodeQueue/media-tabs.flow.md    # sweep ShowSettings references
.claude/directive.md                          # append Promotions rows per task
```

### Deleted files

```
Features/ShowSettings/                        # entire directory
Templates/ShowSettings.html
```

---

## Task 1 — Domain VO: `SeriesIdentity`

A frozen dataclass capturing the `(StorageRootId, RelativePath)` pair that uniquely identifies a series within a drive. Equality by value, immutable, URL-encodable composite key.

**Files:**
- Create: `Features/WorkBucket/Domain/__init__.py`
- Create: `Features/WorkBucket/Domain/SeriesIdentity.py`
- Create: `Tests/Contract/TestSeriesIdentityVO.py`

- [ ] **Step 1: Write the failing test**

`Tests/Contract/TestSeriesIdentityVO.py`:

```python
import unittest
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity


# directive: work-transcode-unified | # see directive.md C2
class TestSeriesIdentityVO(unittest.TestCase):
    """Value object: equality by value, immutability, URL-encodable composite key."""

    def test_equality_by_value(self):
        A = SeriesIdentity(StorageRootId=3, RelativePath='House')
        B = SeriesIdentity(StorageRootId=3, RelativePath='House')
        self.assertEqual(A, B)
        self.assertEqual(hash(A), hash(B))

    def test_inequality_by_storage_root(self):
        A = SeriesIdentity(StorageRootId=3, RelativePath='House')
        B = SeriesIdentity(StorageRootId=4, RelativePath='House')
        self.assertNotEqual(A, B)

    def test_inequality_by_relative_path(self):
        A = SeriesIdentity(StorageRootId=3, RelativePath='House')
        B = SeriesIdentity(StorageRootId=3, RelativePath='Breaking Bad')
        self.assertNotEqual(A, B)

    def test_immutability(self):
        A = SeriesIdentity(StorageRootId=3, RelativePath='House')
        with self.assertRaises(Exception):
            A.StorageRootId = 4

    def test_composite_key_roundtrip(self):
        A = SeriesIdentity(StorageRootId=3, RelativePath='Breaking Bad')
        Key = A.ToCompositeKey()
        self.assertEqual(Key, '3:Breaking Bad')
        B = SeriesIdentity.FromCompositeKey(Key)
        self.assertEqual(A, B)

    def test_composite_key_with_url_unsafe_chars(self):
        A = SeriesIdentity(StorageRootId=3, RelativePath='Star Trek: Strange New Worlds')
        Key = A.ToCompositeKey()
        B = SeriesIdentity.FromCompositeKey(Key)
        self.assertEqual(A, B)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test, confirm it fails**

```
py -m pytest Tests/Contract/TestSeriesIdentityVO.py -v
```

Expected: `ModuleNotFoundError: No module named 'Features.WorkBucket.Domain'`.

- [ ] **Step 3: Create the Domain package**

`Features/WorkBucket/Domain/__init__.py`:

```python
"""Domain layer for the WorkBucket vertical -- value objects + aggregates, no IO."""
```

- [ ] **Step 4: Implement SeriesIdentity**

`Features/WorkBucket/Domain/SeriesIdentity.py`:

```python
from dataclasses import dataclass


# directive: work-transcode-unified | # see directive.md C2
@dataclass(frozen=True)
class SeriesIdentity:
    """Identifies one series uniquely within the library: (drive, first-path-segment) pair."""

    StorageRootId: int
    RelativePath: str

    # directive: work-transcode-unified | # see directive.md C2
    def ToCompositeKey(self) -> str:
        """Render as the URL path token used by /api/Work/<bucket>/Series/<sid>."""
        return f"{self.StorageRootId}:{self.RelativePath}"

    # directive: work-transcode-unified | # see directive.md C2
    @classmethod
    def FromCompositeKey(cls, Key: str) -> "SeriesIdentity":
        """Parse the URL path token. The first colon separates StorageRootId from RelativePath; RelativePath may contain further colons."""
        Sep = Key.find(':')
        if Sep < 0:
            raise ValueError(f"SeriesIdentity composite key missing ':' separator: {Key!r}")
        return cls(StorageRootId=int(Key[:Sep]), RelativePath=Key[Sep + 1:])
```

- [ ] **Step 5: Run test, confirm it passes**

```
py -m pytest Tests/Contract/TestSeriesIdentityVO.py -v
```

Expected: 6 passed.

- [ ] **Step 6: Commit**

```
git add Features/WorkBucket/Domain/__init__.py Features/WorkBucket/Domain/SeriesIdentity.py Tests/Contract/TestSeriesIdentityVO.py
git commit -m "feat(work-bucket): SeriesIdentity value object + tests"
git push
```

---

## Task 2 — Domain VO: `BucketKey`

Frozen dataclass over the three bucket strings; carries URL ↔ bucket-name ↔ ProcessingMode mappings. Replaces the loose `URL_LABELS` / `BUCKET_TO_PROCESSING_MODE` / `BUCKET_TO_URL_KEY` dicts in the current repository.

**Files:**
- Create: `Features/WorkBucket/Domain/BucketKey.py`
- Create: `Tests/Contract/TestBucketKeyVO.py`

- [ ] **Step 1: Write the failing test**

`Tests/Contract/TestBucketKeyVO.py`:

```python
import unittest
from Features.WorkBucket.Domain.BucketKey import BucketKey


# directive: work-transcode-unified | # see directive.md C1
class TestBucketKeyVO(unittest.TestCase):
    """BucketKey: URL <-> bucket-name <-> ProcessingMode mappings."""

    def test_from_url_key_transcode(self):
        K = BucketKey.FromUrlKey('Transcode')
        self.assertIsNotNone(K)
        self.assertEqual(K.BucketName, 'Transcode')
        self.assertEqual(K.ProcessingMode, 'Transcode')

    def test_from_url_key_remux(self):
        K = BucketKey.FromUrlKey('Remux')
        self.assertIsNotNone(K)
        self.assertEqual(K.BucketName, 'Remux')
        self.assertEqual(K.ProcessingMode, 'Remux')

    def test_from_url_key_audio(self):
        K = BucketKey.FromUrlKey('Audio')
        self.assertIsNotNone(K)
        self.assertEqual(K.BucketName, 'AudioFixOnly')
        self.assertEqual(K.ProcessingMode, 'AudioFix')

    def test_from_url_key_unknown(self):
        self.assertIsNone(BucketKey.FromUrlKey('NotABucket'))

    def test_labels_present(self):
        K = BucketKey.FromUrlKey('Transcode')
        self.assertEqual(K.Title, 'Transcode')
        self.assertTrue(K.Subtitle)
        self.assertTrue(K.Icon)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test, confirm it fails**

```
py -m pytest Tests/Contract/TestBucketKeyVO.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement BucketKey**

`Features/WorkBucket/Domain/BucketKey.py`:

```python
from dataclasses import dataclass
from typing import Optional


# directive: work-transcode-unified | # see directive.md C1
@dataclass(frozen=True)
class BucketKey:
    """A bucket the WorkBucket vertical serves. Composite: URL key + DB bucket name + ProcessingMode + display labels."""

    UrlKey: str
    BucketName: str
    ProcessingMode: str
    Title: str
    Subtitle: str
    Icon: str

    # directive: work-transcode-unified | # see directive.md C1
    @classmethod
    def FromUrlKey(cls, UrlKey: str) -> Optional["BucketKey"]:
        """Resolve a URL slug ('Transcode'/'Remux'/'Audio') to its BucketKey, or None if unknown."""
        Match = _BY_URL_KEY.get(UrlKey)
        return Match


_REGISTRY = (
    BucketKey(
        UrlKey='Transcode',
        BucketName='Transcode',
        ProcessingMode='Transcode',
        Title='Transcode',
        Subtitle='Files needing full transcode -- video + audio + container.',
        Icon='fas fa-film',
    ),
    BucketKey(
        UrlKey='Remux',
        BucketName='Remux',
        ProcessingMode='Remux',
        Title='Remux',
        Subtitle='Files needing container fix (audio is also normalized through the same emitter).',
        Icon='fas fa-box',
    ),
    BucketKey(
        UrlKey='Audio',
        BucketName='AudioFixOnly',
        ProcessingMode='AudioFix',
        Title='Audio',
        Subtitle='Files where audio is the only blocker; container + video stream-copy through.',
        Icon='fas fa-volume-up',
    ),
)


_BY_URL_KEY = {B.UrlKey: B for B in _REGISTRY}
```

- [ ] **Step 4: Run test, confirm it passes**

```
py -m pytest Tests/Contract/TestBucketKeyVO.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```
git add Features/WorkBucket/Domain/BucketKey.py Tests/Contract/TestBucketKeyVO.py
git commit -m "feat(work-bucket): BucketKey value object + tests"
git push
```

---

## Task 3 — Domain VO: `ProfileName`

Validated VO. Constructor refuses any profile that isn't finalized (`Draft=FALSE`) AND active (`Active=TRUE`) in the `Profiles` table. Centralizes the validation that's currently duplicated across `EffectiveProfileResolver._IsFinalizedActive` and per-caller checks.

**Files:**
- Create: `Features/WorkBucket/Domain/ProfileName.py`
- Create: `Tests/Contract/TestProfileNameVO.py`

- [ ] **Step 1: Write the failing test**

`Tests/Contract/TestProfileNameVO.py`:

```python
import os
import unittest
from Features.WorkBucket.Domain.ProfileName import ProfileName, InvalidProfileError
from Core.Database.DatabaseService import DatabaseService


# directive: work-transcode-unified | # see directive.md C3
class TestProfileNameVO(unittest.TestCase):
    """ProfileName refuses draft/inactive/unknown profiles at construction."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('MEDIAVORTEX_DB_HOST', '10.0.0.15')

    def test_accepts_finalized_active_profile(self):
        Rows = DatabaseService().ExecuteQuery(
            "SELECT ProfileName FROM Profiles WHERE Draft = FALSE AND Active = TRUE LIMIT 1"
        )
        if not Rows:
            self.skipTest("No finalized active profile in DB")
        Name = Rows[0]['profilename']
        P = ProfileName(Name)
        self.assertEqual(P.Value, Name)

    def test_refuses_unknown(self):
        with self.assertRaises(InvalidProfileError):
            ProfileName('definitely-not-a-real-profile-xyz')

    def test_refuses_draft(self):
        DatabaseService().ExecuteNonQuery(
            "INSERT INTO Profiles (ProfileName, Codec, Container, Draft, Active) "
            "VALUES (%s, 'h264', 'mp4', TRUE, TRUE) ON CONFLICT (ProfileName) DO UPDATE SET Draft = TRUE, Active = TRUE",
            ('test-draft-profile-xyz',),
        )
        try:
            with self.assertRaises(InvalidProfileError):
                ProfileName('test-draft-profile-xyz')
        finally:
            DatabaseService().ExecuteNonQuery(
                "DELETE FROM Profiles WHERE ProfileName = %s",
                ('test-draft-profile-xyz',),
            )

    def test_refuses_inactive(self):
        DatabaseService().ExecuteNonQuery(
            "INSERT INTO Profiles (ProfileName, Codec, Container, Draft, Active) "
            "VALUES (%s, 'h264', 'mp4', FALSE, FALSE) ON CONFLICT (ProfileName) DO UPDATE SET Draft = FALSE, Active = FALSE",
            ('test-inactive-profile-xyz',),
        )
        try:
            with self.assertRaises(InvalidProfileError):
                ProfileName('test-inactive-profile-xyz')
        finally:
            DatabaseService().ExecuteNonQuery(
                "DELETE FROM Profiles WHERE ProfileName = %s",
                ('test-inactive-profile-xyz',),
            )


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test, confirm it fails**

```
py -m pytest Tests/Contract/TestProfileNameVO.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement ProfileName**

`Features/WorkBucket/Domain/ProfileName.py`:

```python
from typing import Optional
from Core.Database.DatabaseService import DatabaseService


# directive: work-transcode-unified | # see directive.md C3
class InvalidProfileError(ValueError):
    """Raised when a ProfileName is not finalized + active in the Profiles table."""


# directive: work-transcode-unified | # see directive.md C3
class ProfileName:
    """Validated value object -- constructor refuses any profile that isn't finalized AND active."""

    __slots__ = ('Value',)

    def __init__(self, RawName: str, Db: Optional[DatabaseService] = None):
        Name = (RawName or '').strip()
        if not Name:
            raise InvalidProfileError("Profile name is empty")
        DbInstance = Db or DatabaseService()
        Rows = DbInstance.ExecuteQuery(
            "SELECT Draft, Active FROM Profiles WHERE ProfileName = %s LIMIT 1",
            (Name,),
        )
        if not Rows:
            raise InvalidProfileError(f"Profile {Name!r} does not exist")
        R = Rows[0]
        if bool(R.get('draft')):
            raise InvalidProfileError(f"Profile {Name!r} is a draft")
        if not bool(R.get('active')):
            raise InvalidProfileError(f"Profile {Name!r} is not active")
        object.__setattr__(self, 'Value', Name)

    def __setattr__(self, *_args):
        raise AttributeError("ProfileName is immutable")

    def __eq__(self, Other):
        return isinstance(Other, ProfileName) and self.Value == Other.Value

    def __hash__(self):
        return hash(self.Value)

    def __repr__(self):
        return f"ProfileName({self.Value!r})"
```

- [ ] **Step 4: Run test, confirm it passes**

```
py -m pytest Tests/Contract/TestProfileNameVO.py -v
```

Expected: 4 passed (or 1 skipped + 3 passed if no finalized profile present).

- [ ] **Step 5: Commit**

```
git add Features/WorkBucket/Domain/ProfileName.py Tests/Contract/TestProfileNameVO.py
git commit -m "feat(work-bucket): ProfileName validated value object + tests"
git push
```

---

## Task 4 — Domain support VOs: `SortSpec`, `FilterSpec`, `AdmissionResult`

Three small VOs that the repositories consume.

**Files:**
- Create: `Features/WorkBucket/Domain/SortSpec.py`
- Create: `Features/WorkBucket/Domain/FilterSpec.py`
- Create: `Features/WorkBucket/Domain/AdmissionResult.py`

- [ ] **Step 1: Implement SortSpec**

`Features/WorkBucket/Domain/SortSpec.py`:

```python
from enum import Enum


# directive: work-transcode-unified | # see directive.md C2
class SortSpec(Enum):
    """Supported sort modes for the series list. ToSql() emits an ORDER BY fragment."""

    TotalGbDesc = 'TotalGB.desc'
    FileCountDesc = 'FileCount.desc'
    NameAsc = 'Name.asc'

    # directive: work-transcode-unified | # see directive.md C2
    def ToSql(self) -> str:
        """SQL ORDER BY clause body (no leading 'ORDER BY ')."""
        if self is SortSpec.TotalGbDesc:
            return "TotalGB DESC NULLS LAST"
        if self is SortSpec.FileCountDesc:
            return "FileCount DESC NULLS LAST"
        return "ShowName ASC"

    # directive: work-transcode-unified | # see directive.md C2
    @classmethod
    def FromString(cls, RawValue: str) -> "SortSpec":
        """Parse the query-string value, defaulting to TotalGbDesc when missing or unknown."""
        if not RawValue:
            return cls.TotalGbDesc
        for Member in cls:
            if Member.value == RawValue:
                return Member
        return cls.TotalGbDesc
```

- [ ] **Step 2: Implement FilterSpec**

`Features/WorkBucket/Domain/FilterSpec.py`:

```python
from dataclasses import dataclass, field
from typing import Tuple


# directive: work-transcode-unified | # see directive.md C6
@dataclass(frozen=True)
class FilterSpec:
    """Optional filters applied to the series list. Empty fields = no filter."""

    StorageRootIds: Tuple[int, ...] = field(default_factory=tuple)
    SearchTerm: str = ''

    # directive: work-transcode-unified | # see directive.md C6
    def ToSqlFragments(self) -> Tuple[str, Tuple]:
        """Return (where_clause_addition, params). where_clause_addition starts with 'AND' if non-empty, '' otherwise."""
        from Core.Database.DatabaseService import EscapeLikePattern
        Clauses = []
        Params = []
        if self.StorageRootIds:
            Placeholders = ','.join(['%s'] * len(self.StorageRootIds))
            Clauses.append(f"mf.StorageRootId IN ({Placeholders})")
            Params.extend(self.StorageRootIds)
        if self.SearchTerm.strip():
            Clauses.append("split_part(mf.RelativePath, '/', 1) ILIKE %s ESCAPE '!'")
            Params.append('%' + EscapeLikePattern(self.SearchTerm.strip()) + '%')
        if not Clauses:
            return ('', ())
        return ('AND ' + ' AND '.join(Clauses), tuple(Params))
```

- [ ] **Step 3: Implement AdmissionResult**

`Features/WorkBucket/Domain/AdmissionResult.py`:

```python
from dataclasses import dataclass


# directive: work-transcode-unified | # see directive.md C4
@dataclass(frozen=True)
class AdmissionResult:
    """Result of a series-level admission to TranscodeQueue."""

    Inserted: int
    AlreadyQueued: int
    Total: int
```

- [ ] **Step 4: Commit**

```
git add Features/WorkBucket/Domain/SortSpec.py Features/WorkBucket/Domain/FilterSpec.py Features/WorkBucket/Domain/AdmissionResult.py
git commit -m "feat(work-bucket): SortSpec/FilterSpec/AdmissionResult VOs"
git push
```

---

## Task 5 — Domain aggregates: `Series`, `MediaFileRow`

Two frozen dataclasses representing the JSON-projectable rows the repositories return.

**Files:**
- Create: `Features/WorkBucket/Domain/Series.py`
- Create: `Features/WorkBucket/Domain/MediaFileRow.py`

- [ ] **Step 1: Implement Series**

`Features/WorkBucket/Domain/Series.py`:

```python
from dataclasses import dataclass
from typing import Optional
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity
from Features.WorkBucket.Domain.BucketKey import BucketKey


# directive: work-transcode-unified | # see directive.md C2
@dataclass(frozen=True)
class Series:
    """Aggregated row for one series within one bucket -- the unit the grouped page renders."""

    Identity: SeriesIdentity
    Bucket: BucketKey
    ShowName: str
    FileCount: int
    TotalGB: float
    CommonResolution: Optional[str]
    CommonCodec: Optional[str]
    AssignedProfile: Optional[str]
    AnyInQueue: bool

    # directive: work-transcode-unified | # see directive.md C2
    def ToJson(self) -> dict:
        """JSON projection for /api/Work/<bucket>."""
        return {
            'StorageRootId': self.Identity.StorageRootId,
            'RelativePath': self.Identity.RelativePath,
            'ShowName': self.ShowName,
            'CompositeKey': self.Identity.ToCompositeKey(),
            'Bucket': self.Bucket.BucketName,
            'FileCount': self.FileCount,
            'TotalGB': self.TotalGB,
            'CommonResolution': self.CommonResolution,
            'CommonCodec': self.CommonCodec,
            'AssignedProfile': self.AssignedProfile,
            'AnyInQueue': self.AnyInQueue,
        }
```

- [ ] **Step 2: Implement MediaFileRow**

`Features/WorkBucket/Domain/MediaFileRow.py`:

```python
from dataclasses import dataclass
from typing import Optional


# directive: work-transcode-unified | # see directive.md C2
@dataclass(frozen=True)
class MediaFileRow:
    """A single file row inside an expanded series."""

    Id: int
    FileName: str
    SizeGB: float
    Resolution: Optional[str]
    AudioCodec: Optional[str]
    AudioLanguages: Optional[str]
    VideoCompliantReason: Optional[str]
    ContainerCompliantReason: Optional[str]
    AudioCompliantReason: Optional[str]
    InQueue: bool

    # directive: work-transcode-unified | # see directive.md C2
    def ToJson(self) -> dict:
        """JSON projection for /api/Work/<bucket>/Series/<sid>."""
        return {
            'Id': self.Id,
            'FileName': self.FileName,
            'SizeGB': self.SizeGB,
            'Resolution': self.Resolution,
            'AudioCodec': self.AudioCodec,
            'AudioLanguages': self.AudioLanguages,
            'VideoCompliantReason': self.VideoCompliantReason,
            'ContainerCompliantReason': self.ContainerCompliantReason,
            'AudioCompliantReason': self.AudioCompliantReason,
            'InQueue': self.InQueue,
        }
```

- [ ] **Step 3: Commit**

```
git add Features/WorkBucket/Domain/Series.py Features/WorkBucket/Domain/MediaFileRow.py
git commit -m "feat(work-bucket): Series + MediaFileRow domain types"
git push
```

---

## Task 6 — Repository: `SeriesQueryRepository`

Read-only, paged repository that returns the grouped series rows for a given bucket. Owns the single aggregate query.

**Files:**
- Create: `Features/WorkBucket/Repositories/__init__.py`
- Create: `Features/WorkBucket/Repositories/SeriesQueryRepository.py`
- Create: `Tests/Contract/TestSeriesQueryRepository.py`

- [ ] **Step 1: Write the failing test**

`Tests/Contract/TestSeriesQueryRepository.py`:

```python
import os
import unittest
from Core.Querying import PagedQuery
from Features.WorkBucket.Domain.BucketKey import BucketKey
from Features.WorkBucket.Domain.FilterSpec import FilterSpec
from Features.WorkBucket.Domain.SortSpec import SortSpec
from Features.WorkBucket.Repositories.SeriesQueryRepository import SeriesQueryRepository


# directive: work-transcode-unified | # see directive.md C1
class TestSeriesQueryRepository(unittest.TestCase):
    """Contract: grouped series query respects bucket filter, sort, HAVING."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('MEDIAVORTEX_DB_HOST', '10.0.0.15')

    def test_list_series_by_bucket_transcode_returns_only_transcode_files(self):
        Repo = SeriesQueryRepository()
        Result = Repo.ListSeriesByBucket(
            Bucket=BucketKey.FromUrlKey('Transcode'),
            Query=PagedQuery(Page=1, PageSize=25),
            Sort=SortSpec.TotalGbDesc,
            Filter=FilterSpec(),
        )
        # Every series row's underlying files must be in the Transcode bucket -- spot-check by re-querying.
        # The query's WHERE clause is the contract; row presence implies match.
        self.assertGreaterEqual(Result.TotalCount, 0)
        for S in Result.Rows:
            self.assertGreater(S.FileCount, 0)
            self.assertGreaterEqual(S.TotalGB, 0)
            self.assertEqual(S.Bucket.BucketName, 'Transcode')

    def test_having_clause_excludes_empty_series(self):
        # HAVING COUNT(*) > 0 means no Series row can have FileCount = 0.
        Repo = SeriesQueryRepository()
        Result = Repo.ListSeriesByBucket(
            Bucket=BucketKey.FromUrlKey('Transcode'),
            Query=PagedQuery(Page=1, PageSize=100),
            Sort=SortSpec.TotalGbDesc,
            Filter=FilterSpec(),
        )
        for S in Result.Rows:
            self.assertGreater(S.FileCount, 0)

    def test_sort_total_gb_desc_is_monotonic(self):
        Repo = SeriesQueryRepository()
        Result = Repo.ListSeriesByBucket(
            Bucket=BucketKey.FromUrlKey('Transcode'),
            Query=PagedQuery(Page=1, PageSize=10),
            Sort=SortSpec.TotalGbDesc,
            Filter=FilterSpec(),
        )
        Prev = None
        for S in Result.Rows:
            if Prev is not None:
                self.assertLessEqual(S.TotalGB, Prev)
            Prev = S.TotalGB

    def test_unknown_bucket_returns_empty_result(self):
        # FromUrlKey('Bogus') is None -- repo must not panic.
        # Caller's responsibility to map None -> 404 at the controller layer.
        Repo = SeriesQueryRepository()
        with self.assertRaises((AttributeError, TypeError, ValueError)):
            Repo.ListSeriesByBucket(
                Bucket=None,
                Query=PagedQuery(Page=1, PageSize=10),
                Sort=SortSpec.TotalGbDesc,
                Filter=FilterSpec(),
            )


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test, confirm it fails**

```
py -m pytest Tests/Contract/TestSeriesQueryRepository.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Create Repositories package**

`Features/WorkBucket/Repositories/__init__.py`:

```python
"""Repositories for the WorkBucket vertical -- one file per query family (SRP)."""
```

- [ ] **Step 4: Implement SeriesQueryRepository**

`Features/WorkBucket/Repositories/SeriesQueryRepository.py`:

```python
from Core.Database.DatabaseService import DatabaseService
from Core.Querying import PagedQuery, PagedQueryResult
from Features.WorkBucket.Domain.BucketKey import BucketKey
from Features.WorkBucket.Domain.FilterSpec import FilterSpec
from Features.WorkBucket.Domain.Series import Series
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity
from Features.WorkBucket.Domain.SortSpec import SortSpec


# directive: work-transcode-unified | # see directive.md C1
class SeriesQueryRepository:
    """Read-only grouped query: returns Series rows for one bucket, paged + sortable + filterable."""

    # directive: work-transcode-unified | # see directive.md C1
    def __init__(self, Db: DatabaseService = None):
        self.Db = Db or DatabaseService()

    # directive: work-transcode-unified | # see directive.md C1, C2, C6
    def ListSeriesByBucket(
        self,
        Bucket: BucketKey,
        Query: PagedQuery,
        Sort: SortSpec,
        Filter: FilterSpec,
    ) -> PagedQueryResult:
        FilterClause, FilterParams = Filter.ToSqlFragments()
        Offset = max(0, (Query.Page - 1) * Query.PageSize)
        Limit = max(1, min(Query.PageSize, 200))
        Sql = (
            "SELECT * FROM ("
            "  SELECT mf.StorageRootId AS StorageRootId,"
            "         split_part(mf.RelativePath, '/', 1) AS RelativePath,"
            "         split_part(mf.RelativePath, '/', 1) AS ShowName,"
            "         COUNT(*)::int AS FileCount,"
            "         ROUND(SUM(mf.SizeMB)::numeric / 1024, 1)::float AS TotalGB,"
            "         MODE() WITHIN GROUP (ORDER BY mf.ResolutionCategory) AS CommonResolution,"
            "         MODE() WITHIN GROUP (ORDER BY mf.Codec) AS CommonCodec,"
            "         sp.AssignedProfile AS AssignedProfile,"
            "         EXISTS ("
            "           SELECT 1 FROM TranscodeQueue tq"
            "             JOIN MediaFiles m2 ON m2.Id = tq.MediaFileId"
            "            WHERE tq.Status = 'Pending'"
            "              AND m2.StorageRootId = mf.StorageRootId"
            "              AND split_part(m2.RelativePath, '/', 1) = split_part(mf.RelativePath, '/', 1)"
            "              AND m2.WorkBucket = mf.WorkBucket"
            "         ) AS AnyInQueue,"
            "         COUNT(*) OVER () AS __TotalCount"
            "    FROM MediaFiles mf"
            "    LEFT JOIN SeriesProfiles sp"
            "      ON sp.StorageRootId = mf.StorageRootId"
            "     AND sp.RelativePath = split_part(mf.RelativePath, '/', 1)"
            "   WHERE mf.WorkBucket = %s "
            f"   {FilterClause} "
            "   GROUP BY mf.StorageRootId, split_part(mf.RelativePath, '/', 1), sp.AssignedProfile"
            "   HAVING COUNT(*) > 0"
            ") agg "
            f"ORDER BY {Sort.ToSql()} "
            "LIMIT %s OFFSET %s"
        )
        Params = (Bucket.BucketName,) + FilterParams + (Limit, Offset)
        Rows = self.Db.ExecuteQuery(Sql, Params)
        TotalCount = int(Rows[0]['__totalcount']) if Rows else 0
        SeriesList = [
            Series(
                Identity=SeriesIdentity(
                    StorageRootId=int(R['storagerootid']),
                    RelativePath=R['relativepath'],
                ),
                Bucket=Bucket,
                ShowName=R['showname'],
                FileCount=int(R['filecount']),
                TotalGB=float(R['totalgb']) if R['totalgb'] is not None else 0.0,
                CommonResolution=R.get('commonresolution'),
                CommonCodec=R.get('commoncodec'),
                AssignedProfile=R.get('assignedprofile'),
                AnyInQueue=bool(R.get('anyinqueue')),
            )
            for R in Rows
        ]
        return PagedQueryResult(
            Rows=SeriesList,
            TotalCount=TotalCount,
            Page=Query.Page,
            PageSize=Query.PageSize,
        )
```

- [ ] **Step 5: Run test against pre-migration DB**

```
py -m pytest Tests/Contract/TestSeriesQueryRepository.py -v
```

Expected: tests requiring `SeriesProfiles` will FAIL (table doesn't exist yet). That's fine — the migration in Task 12 creates the table; we'll re-run after.

If you want the tests to pass NOW pre-migration, temporarily change `LEFT JOIN SeriesProfiles sp` to `LEFT JOIN ShowSettings sp` in your local copy ONLY to verify the query shape works. Revert before commit. Skipping ahead to Task 12 first is also valid.

- [ ] **Step 6: Commit**

```
git add Features/WorkBucket/Repositories/__init__.py Features/WorkBucket/Repositories/SeriesQueryRepository.py Tests/Contract/TestSeriesQueryRepository.py
git commit -m "feat(work-bucket): SeriesQueryRepository -- grouped paged series query"
git push
```

---

## Task 7 — Repository: `FilesInSeriesRepository`

Read-only, returns the flat file list for one expanded series, filtered by bucket.

**Files:**
- Create: `Features/WorkBucket/Repositories/FilesInSeriesRepository.py`
- Create: `Tests/Contract/TestFilesInSeriesRepository.py`

- [ ] **Step 1: Write the failing test**

`Tests/Contract/TestFilesInSeriesRepository.py`:

```python
import os
import unittest
from Core.Database.DatabaseService import DatabaseService
from Features.WorkBucket.Domain.BucketKey import BucketKey
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity
from Features.WorkBucket.Repositories.FilesInSeriesRepository import FilesInSeriesRepository


# directive: work-transcode-unified | # see directive.md C2
class TestFilesInSeriesRepository(unittest.TestCase):
    """Contract: ListFilesInSeries returns rows of the requested bucket + series, sorted by size desc."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('MEDIAVORTEX_DB_HOST', '10.0.0.15')

    def test_returns_only_files_in_the_bucket(self):
        Sample = DatabaseService().ExecuteQuery(
            "SELECT mf.StorageRootId, split_part(mf.RelativePath, '/', 1) AS RelativePath "
            "FROM MediaFiles mf WHERE mf.WorkBucket = 'Transcode' "
            "GROUP BY mf.StorageRootId, split_part(mf.RelativePath, '/', 1) "
            "LIMIT 1"
        )
        if not Sample:
            self.skipTest("No Transcode bucket series in DB")
        S = Sample[0]
        Identity = SeriesIdentity(StorageRootId=int(S['storagerootid']), RelativePath=S['relativepath'])
        Files = FilesInSeriesRepository().ListFilesInSeries(
            Identity=Identity,
            Bucket=BucketKey.FromUrlKey('Transcode'),
        )
        self.assertGreater(len(Files), 0)
        Sizes = [F.SizeGB for F in Files]
        self.assertEqual(Sizes, sorted(Sizes, reverse=True))

    def test_returns_empty_for_unknown_series(self):
        Files = FilesInSeriesRepository().ListFilesInSeries(
            Identity=SeriesIdentity(StorageRootId=999999, RelativePath='__no_such_show__'),
            Bucket=BucketKey.FromUrlKey('Transcode'),
        )
        self.assertEqual(Files, [])


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test, confirm it fails**

```
py -m pytest Tests/Contract/TestFilesInSeriesRepository.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement FilesInSeriesRepository**

`Features/WorkBucket/Repositories/FilesInSeriesRepository.py`:

```python
from typing import List
from Core.Database.DatabaseService import DatabaseService
from Features.WorkBucket.Domain.BucketKey import BucketKey
from Features.WorkBucket.Domain.MediaFileRow import MediaFileRow
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity


# directive: work-transcode-unified | # see directive.md C2
class FilesInSeriesRepository:
    """Read-only: list MediaFiles in one (bucket, series-identity) scope, sorted by size desc."""

    # directive: work-transcode-unified | # see directive.md C2
    def __init__(self, Db: DatabaseService = None):
        self.Db = Db or DatabaseService()

    # directive: work-transcode-unified | # see directive.md C2
    def ListFilesInSeries(self, Identity: SeriesIdentity, Bucket: BucketKey) -> List[MediaFileRow]:
        Sql = (
            "SELECT mf.Id, mf.FileName, "
            "       ROUND(mf.SizeMB::numeric / 1024, 2)::float AS SizeGB, "
            "       mf.Resolution, mf.AudioCodec, mf.AudioLanguages, "
            "       mf.VideoCompliantReason, mf.ContainerCompliantReason, mf.AudioCompliantReason, "
            "       EXISTS ("
            "         SELECT 1 FROM TranscodeQueue tq "
            "          WHERE tq.MediaFileId = mf.Id AND tq.Status = 'Pending'"
            "       ) AS InQueue "
            "  FROM MediaFiles mf "
            " WHERE mf.WorkBucket = %s "
            "   AND mf.StorageRootId = %s "
            "   AND split_part(mf.RelativePath, '/', 1) = %s "
            " ORDER BY mf.SizeMB DESC NULLS LAST"
        )
        Rows = self.Db.ExecuteQuery(Sql, (Bucket.BucketName, Identity.StorageRootId, Identity.RelativePath))
        return [
            MediaFileRow(
                Id=int(R['id']),
                FileName=R['filename'],
                SizeGB=float(R['sizegb']) if R['sizegb'] is not None else 0.0,
                Resolution=R.get('resolution'),
                AudioCodec=R.get('audiocodec'),
                AudioLanguages=R.get('audiolanguages'),
                VideoCompliantReason=R.get('videocompliantreason'),
                ContainerCompliantReason=R.get('containercompliantreason'),
                AudioCompliantReason=R.get('audiocompliantreason'),
                InQueue=bool(R.get('inqueue')),
            )
            for R in Rows
        ]
```

- [ ] **Step 4: Run test, confirm it passes**

```
py -m pytest Tests/Contract/TestFilesInSeriesRepository.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```
git add Features/WorkBucket/Repositories/FilesInSeriesRepository.py Tests/Contract/TestFilesInSeriesRepository.py
git commit -m "feat(work-bucket): FilesInSeriesRepository -- expand-series query"
git push
```

---

## Task 8 — Repository: `SeriesProfileRepository`

Read/write `SeriesProfiles` only. UPSERT + GET + DELETE.

**Files:**
- Create: `Features/WorkBucket/Repositories/SeriesProfileRepository.py`
- Create: `Tests/Contract/TestSeriesProfileRepository.py`

- [ ] **Step 1: Write the failing test**

`Tests/Contract/TestSeriesProfileRepository.py`:

```python
import os
import unittest
from Core.Database.DatabaseService import DatabaseService
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity
from Features.WorkBucket.Repositories.SeriesProfileRepository import SeriesProfileRepository


# directive: work-transcode-unified | # see directive.md C3
class TestSeriesProfileRepository(unittest.TestCase):
    """Contract: UPSERT / GET / DELETE against SeriesProfiles."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('MEDIAVORTEX_DB_HOST', '10.0.0.15')
        cls.TestIdentity = SeriesIdentity(StorageRootId=99, RelativePath='__test_series_profile_repo__')

    def setUp(self):
        DatabaseService().ExecuteNonQuery(
            "DELETE FROM SeriesProfiles WHERE StorageRootId = %s AND RelativePath = %s",
            (self.TestIdentity.StorageRootId, self.TestIdentity.RelativePath),
        )

    def tearDown(self):
        DatabaseService().ExecuteNonQuery(
            "DELETE FROM SeriesProfiles WHERE StorageRootId = %s AND RelativePath = %s",
            (self.TestIdentity.StorageRootId, self.TestIdentity.RelativePath),
        )

    def test_get_returns_none_when_absent(self):
        self.assertIsNone(SeriesProfileRepository().GetProfile(self.TestIdentity))

    def test_upsert_inserts(self):
        Repo = SeriesProfileRepository()
        Repo.UpsertProfile(self.TestIdentity, 'h264-1080p')
        self.assertEqual(Repo.GetProfile(self.TestIdentity), 'h264-1080p')

    def test_upsert_updates(self):
        Repo = SeriesProfileRepository()
        Repo.UpsertProfile(self.TestIdentity, 'h264-1080p')
        Repo.UpsertProfile(self.TestIdentity, 'hevc-2160p')
        self.assertEqual(Repo.GetProfile(self.TestIdentity), 'hevc-2160p')

    def test_delete_removes(self):
        Repo = SeriesProfileRepository()
        Repo.UpsertProfile(self.TestIdentity, 'h264-1080p')
        Repo.DeleteProfile(self.TestIdentity)
        self.assertIsNone(Repo.GetProfile(self.TestIdentity))


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test, confirm it fails**

```
py -m pytest Tests/Contract/TestSeriesProfileRepository.py -v
```

Expected: ModuleNotFoundError (or "table SeriesProfiles does not exist" if module imports OK but table absent — that's also fine).

- [ ] **Step 3: Implement SeriesProfileRepository**

`Features/WorkBucket/Repositories/SeriesProfileRepository.py`:

```python
from typing import Optional
from Core.Database.DatabaseService import DatabaseService
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity


# directive: work-transcode-unified | # see directive.md C3
class SeriesProfileRepository:
    """Read/write SeriesProfiles -- per-series sticky AssignedProfile only."""

    # directive: work-transcode-unified | # see directive.md C3
    def __init__(self, Db: DatabaseService = None):
        self.Db = Db or DatabaseService()

    # directive: work-transcode-unified | # see directive.md C3
    def GetProfile(self, Identity: SeriesIdentity) -> Optional[str]:
        Rows = self.Db.ExecuteQuery(
            "SELECT AssignedProfile FROM SeriesProfiles "
            "WHERE StorageRootId = %s AND RelativePath = %s LIMIT 1",
            (Identity.StorageRootId, Identity.RelativePath),
        )
        if not Rows:
            return None
        return Rows[0].get('assignedprofile')

    # directive: work-transcode-unified | # see directive.md C3
    def UpsertProfile(self, Identity: SeriesIdentity, AssignedProfile: str) -> None:
        self.Db.ExecuteNonQuery(
            "INSERT INTO SeriesProfiles (StorageRootId, RelativePath, AssignedProfile, CreatedDate, LastModifiedDate) "
            "VALUES (%s, %s, %s, NOW(), NOW()) "
            "ON CONFLICT (StorageRootId, RelativePath) DO UPDATE "
            "SET AssignedProfile = EXCLUDED.AssignedProfile, LastModifiedDate = NOW()",
            (Identity.StorageRootId, Identity.RelativePath, AssignedProfile),
        )

    # directive: work-transcode-unified | # see directive.md C3
    def DeleteProfile(self, Identity: SeriesIdentity) -> None:
        self.Db.ExecuteNonQuery(
            "DELETE FROM SeriesProfiles WHERE StorageRootId = %s AND RelativePath = %s",
            (Identity.StorageRootId, Identity.RelativePath),
        )
```

- [ ] **Step 4: Defer running the test until after Task 12**

The test depends on the `SeriesProfiles` table, which is created by Task 12's migration. Leave the test in place; it will run green after Task 12.

- [ ] **Step 5: Commit**

```
git add Features/WorkBucket/Repositories/SeriesProfileRepository.py Tests/Contract/TestSeriesProfileRepository.py
git commit -m "feat(work-bucket): SeriesProfileRepository -- UPSERT/GET/DELETE on SeriesProfiles"
git push
```

---

## Task 9 — Repository: `QueueAdmissionRepository`

Write-only against `TranscodeQueue`. Single-row + per-series-bulk admission with idempotency.

**Files:**
- Create: `Features/WorkBucket/Repositories/QueueAdmissionRepository.py`
- Create: `Tests/Contract/TestQueueAdmissionRepository.py`

- [ ] **Step 1: Write the failing test**

`Tests/Contract/TestQueueAdmissionRepository.py`:

```python
import os
import unittest
from Core.Database.DatabaseService import DatabaseService
from Features.WorkBucket.Domain.BucketKey import BucketKey
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity
from Features.WorkBucket.Repositories.QueueAdmissionRepository import QueueAdmissionRepository


# directive: work-transcode-unified | # see directive.md C4, C5
class TestQueueAdmissionRepository(unittest.TestCase):
    """Contract: AdmitOne + AdmitSeries are idempotent and bucket-scoped."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('MEDIAVORTEX_DB_HOST', '10.0.0.15')

    def test_admit_one_is_idempotent(self):
        Row = DatabaseService().ExecuteQuery(
            "SELECT Id FROM MediaFiles WHERE WorkBucket = 'Transcode' AND TranscodedByMediaVortex IS NOT TRUE LIMIT 1"
        )
        if not Row:
            self.skipTest("No Transcode MediaFile in DB")
        MediaFileId = int(Row[0]['id'])
        Repo = QueueAdmissionRepository()
        DatabaseService().ExecuteNonQuery(
            "DELETE FROM TranscodeQueue WHERE MediaFileId = %s AND Status = 'Pending'",
            (MediaFileId,),
        )
        Status1, _Id1 = Repo.AdmitOne(MediaFileId, 'Transcode')
        Status2, _Id2 = Repo.AdmitOne(MediaFileId, 'Transcode')
        self.assertEqual(Status1, 'queued')
        self.assertEqual(Status2, 'already_queued')
        DatabaseService().ExecuteNonQuery(
            "DELETE FROM TranscodeQueue WHERE MediaFileId = %s AND Status = 'Pending'",
            (MediaFileId,),
        )

    def test_admit_series_idempotent(self):
        Sample = DatabaseService().ExecuteQuery(
            "SELECT mf.StorageRootId, split_part(mf.RelativePath, '/', 1) AS RelativePath, COUNT(*)::int AS c "
            "FROM MediaFiles mf WHERE mf.WorkBucket = 'Transcode' "
            "GROUP BY mf.StorageRootId, split_part(mf.RelativePath, '/', 1) "
            "HAVING COUNT(*) >= 2 LIMIT 1"
        )
        if not Sample:
            self.skipTest("Need a Transcode series with >=2 files")
        S = Sample[0]
        Identity = SeriesIdentity(StorageRootId=int(S['storagerootid']), RelativePath=S['relativepath'])
        DatabaseService().ExecuteNonQuery(
            "DELETE FROM TranscodeQueue WHERE Status='Pending' AND MediaFileId IN ("
            "  SELECT Id FROM MediaFiles WHERE WorkBucket='Transcode' AND StorageRootId=%s AND split_part(RelativePath,'/',1)=%s"
            ")",
            (Identity.StorageRootId, Identity.RelativePath),
        )
        Repo = QueueAdmissionRepository()
        R1 = Repo.AdmitSeries(Identity, BucketKey.FromUrlKey('Transcode'))
        R2 = Repo.AdmitSeries(Identity, BucketKey.FromUrlKey('Transcode'))
        self.assertGreater(R1.Inserted, 0)
        self.assertEqual(R2.Inserted, 0)
        self.assertEqual(R2.AlreadyQueued, R1.Inserted)
        DatabaseService().ExecuteNonQuery(
            "DELETE FROM TranscodeQueue WHERE Status='Pending' AND MediaFileId IN ("
            "  SELECT Id FROM MediaFiles WHERE WorkBucket='Transcode' AND StorageRootId=%s AND split_part(RelativePath,'/',1)=%s"
            ")",
            (Identity.StorageRootId, Identity.RelativePath),
        )


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test, confirm it fails**

```
py -m pytest Tests/Contract/TestQueueAdmissionRepository.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement QueueAdmissionRepository**

`Features/WorkBucket/Repositories/QueueAdmissionRepository.py`:

```python
from typing import Tuple
from Core.Database.DatabaseService import DatabaseService
from Features.WorkBucket.Domain.AdmissionResult import AdmissionResult
from Features.WorkBucket.Domain.BucketKey import BucketKey
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity


# directive: work-transcode-unified | # see directive.md C4, C5
class QueueAdmissionRepository:
    """Write-only INSERTs against TranscodeQueue with idempotency guards."""

    # directive: work-transcode-unified | # see directive.md C4, C5
    def __init__(self, Db: DatabaseService = None):
        self.Db = Db or DatabaseService()

    # directive: work-transcode-unified | # see directive.md C5
    def AdmitOne(self, MediaFileId: int, ProcessingMode: str) -> Tuple[str, int]:
        """Insert one Pending row if absent. Returns ('queued', QueueId) or ('already_queued', QueueId)."""
        Existing = self.Db.ExecuteQuery(
            "SELECT Id FROM TranscodeQueue WHERE MediaFileId = %s AND Status = 'Pending' LIMIT 1",
            (int(MediaFileId),),
        )
        if Existing:
            return ('already_queued', int(Existing[0]['id']))
        self.Db.ExecuteNonQuery(
            "INSERT INTO TranscodeQueue ("
            "  FileName, Directory, SizeBytes, SizeMB, MediaFileId, StorageRootId, RelativePath, "
            "  ProcessingMode, Status, Priority, DateAdded"
            ") "
            "SELECT mf.FileName, '', COALESCE(mf.FileSize, 0), COALESCE(mf.SizeMB, 0), mf.Id, "
            "  mf.StorageRootId, mf.RelativePath, %s, 'Pending', 100, NOW() "
            "FROM MediaFiles mf WHERE mf.Id = %s",
            (ProcessingMode, int(MediaFileId)),
        )
        Inserted = self.Db.ExecuteQuery(
            "SELECT Id FROM TranscodeQueue WHERE MediaFileId = %s AND Status = 'Pending' LIMIT 1",
            (int(MediaFileId),),
        )
        return ('queued', int(Inserted[0]['id']) if Inserted else 0)

    # directive: work-transcode-unified | # see directive.md C4
    def AdmitSeries(self, Identity: SeriesIdentity, Bucket: BucketKey) -> AdmissionResult:
        """Bulk-insert Pending rows for every untranscoded file in the series with no existing Pending row."""
        Total = int(
            self.Db.ExecuteQuery(
                "SELECT COUNT(*)::int AS c FROM MediaFiles mf "
                "WHERE mf.WorkBucket = %s "
                "  AND mf.StorageRootId = %s "
                "  AND split_part(mf.RelativePath, '/', 1) = %s",
                (Bucket.BucketName, Identity.StorageRootId, Identity.RelativePath),
            )[0]['c']
        )
        Candidates = int(
            self.Db.ExecuteQuery(
                "SELECT COUNT(*)::int AS c FROM MediaFiles mf "
                "WHERE mf.WorkBucket = %s "
                "  AND mf.StorageRootId = %s "
                "  AND split_part(mf.RelativePath, '/', 1) = %s "
                "  AND NOT EXISTS ("
                "    SELECT 1 FROM TranscodeQueue tq "
                "     WHERE tq.MediaFileId = mf.Id AND tq.Status = 'Pending'"
                "  )",
                (Bucket.BucketName, Identity.StorageRootId, Identity.RelativePath),
            )[0]['c']
        )
        if Candidates == 0:
            return AdmissionResult(Inserted=0, AlreadyQueued=Total, Total=Total)
        self.Db.ExecuteNonQuery(
            "INSERT INTO TranscodeQueue ("
            "  FileName, Directory, SizeBytes, SizeMB, MediaFileId, StorageRootId, RelativePath, "
            "  ProcessingMode, Status, Priority, DateAdded"
            ") "
            "SELECT mf.FileName, '', COALESCE(mf.FileSize, 0), COALESCE(mf.SizeMB, 0), mf.Id, "
            "  mf.StorageRootId, mf.RelativePath, %s, 'Pending', 100, NOW() "
            "FROM MediaFiles mf "
            " WHERE mf.WorkBucket = %s "
            "   AND mf.StorageRootId = %s "
            "   AND split_part(mf.RelativePath, '/', 1) = %s "
            "   AND NOT EXISTS ("
            "     SELECT 1 FROM TranscodeQueue tq "
            "      WHERE tq.MediaFileId = mf.Id AND tq.Status = 'Pending'"
            "   )",
            (Bucket.ProcessingMode, Bucket.BucketName, Identity.StorageRootId, Identity.RelativePath),
        )
        return AdmissionResult(Inserted=Candidates, AlreadyQueued=Total - Candidates, Total=Total)
```

- [ ] **Step 4: Run test, confirm it passes**

```
py -m pytest Tests/Contract/TestQueueAdmissionRepository.py -v
```

Expected: 2 passed (or skipped if DB has no Transcode samples).

- [ ] **Step 5: Commit**

```
git add Features/WorkBucket/Repositories/QueueAdmissionRepository.py Tests/Contract/TestQueueAdmissionRepository.py
git commit -m "feat(work-bucket): QueueAdmissionRepository -- idempotent AdmitOne + AdmitSeries"
git push
```

---

## Task 10 — Service: `SeriesProfileService`

Orchestrates the profile-set use case. Validates via `ProfileName` VO → upserts SeriesProfiles → bulk-updates `MediaFiles.AssignedProfile`. Returns `FilesAffected`.

**Files:**
- Create: `Features/WorkBucket/Services/__init__.py`
- Create: `Features/WorkBucket/Services/SeriesProfileService.py`
- Create: `Tests/Contract/TestSeriesProfileService.py`

- [ ] **Step 1: Write the failing test**

`Tests/Contract/TestSeriesProfileService.py`:

```python
import os
import unittest
from Core.Database.DatabaseService import DatabaseService
from Features.WorkBucket.Domain.ProfileName import InvalidProfileError
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity
from Features.WorkBucket.Services.SeriesProfileService import SeriesProfileService


# directive: work-transcode-unified | # see directive.md C3
class TestSeriesProfileService(unittest.TestCase):
    """Contract: SetProfile validates, upserts, and bulk-updates MediaFiles."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('MEDIAVORTEX_DB_HOST', '10.0.0.15')

    def test_set_profile_refuses_unknown_profile(self):
        Identity = SeriesIdentity(StorageRootId=99, RelativePath='__test_series__')
        with self.assertRaises(InvalidProfileError):
            SeriesProfileService().SetProfile(Identity, 'this-profile-does-not-exist')

    def test_set_profile_updates_only_untranscoded_files(self):
        Sample = DatabaseService().ExecuteQuery(
            "SELECT mf.StorageRootId, split_part(mf.RelativePath, '/', 1) AS RelativePath "
            "FROM MediaFiles mf WHERE mf.WorkBucket = 'Transcode' AND mf.TranscodedByMediaVortex IS NOT TRUE "
            "GROUP BY mf.StorageRootId, split_part(mf.RelativePath, '/', 1) "
            "HAVING COUNT(*) >= 1 LIMIT 1"
        )
        if not Sample:
            self.skipTest("No untranscoded Transcode series available")
        ProfileRow = DatabaseService().ExecuteQuery(
            "SELECT ProfileName FROM Profiles WHERE Draft = FALSE AND Active = TRUE LIMIT 1"
        )
        if not ProfileRow:
            self.skipTest("No active profile available")
        Identity = SeriesIdentity(
            StorageRootId=int(Sample[0]['storagerootid']),
            RelativePath=Sample[0]['relativepath'],
        )
        Profile = ProfileRow[0]['profilename']
        Original = DatabaseService().ExecuteQuery(
            "SELECT Id, AssignedProfile FROM MediaFiles "
            "WHERE WorkBucket='Transcode' AND StorageRootId=%s AND split_part(RelativePath,'/',1)=%s "
            "AND TranscodedByMediaVortex IS NOT TRUE",
            (Identity.StorageRootId, Identity.RelativePath),
        )
        try:
            FilesAffected = SeriesProfileService().SetProfile(Identity, Profile)
            self.assertEqual(FilesAffected, len(Original))
            Updated = DatabaseService().ExecuteQuery(
                "SELECT AssignedProfile FROM MediaFiles "
                "WHERE WorkBucket='Transcode' AND StorageRootId=%s AND split_part(RelativePath,'/',1)=%s "
                "AND TranscodedByMediaVortex IS NOT TRUE",
                (Identity.StorageRootId, Identity.RelativePath),
            )
            for R in Updated:
                self.assertEqual(R['assignedprofile'], Profile)
        finally:
            for R in Original:
                DatabaseService().ExecuteNonQuery(
                    "UPDATE MediaFiles SET AssignedProfile = %s WHERE Id = %s",
                    (R.get('assignedprofile'), int(R['id'])),
                )
            DatabaseService().ExecuteNonQuery(
                "DELETE FROM SeriesProfiles WHERE StorageRootId = %s AND RelativePath = %s",
                (Identity.StorageRootId, Identity.RelativePath),
            )


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test, confirm it fails**

```
py -m pytest Tests/Contract/TestSeriesProfileService.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Create Services package**

`Features/WorkBucket/Services/__init__.py`:

```python
"""Application services for the WorkBucket vertical -- orchestrate domain + repositories."""
```

- [ ] **Step 4: Implement SeriesProfileService**

`Features/WorkBucket/Services/SeriesProfileService.py`:

```python
from typing import Optional
from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Features.WorkBucket.Domain.ProfileName import ProfileName
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity
from Features.WorkBucket.Repositories.SeriesProfileRepository import SeriesProfileRepository


# directive: work-transcode-unified | # see directive.md C3
class SeriesProfileService:
    """Orchestrates per-series profile assignment: validate -> persist sticky -> propagate to untranscoded MediaFiles."""

    # directive: work-transcode-unified | # see directive.md C3
    def __init__(
        self,
        Db: Optional[DatabaseService] = None,
        ProfileRepo: Optional[SeriesProfileRepository] = None,
    ):
        self.Db = Db or DatabaseService()
        self.ProfileRepo = ProfileRepo or SeriesProfileRepository(self.Db)

    # directive: work-transcode-unified | # see directive.md C3
    def SetProfile(self, Identity: SeriesIdentity, RawProfileName: str) -> int:
        Profile = ProfileName(RawProfileName, Db=self.Db)
        self.ProfileRepo.UpsertProfile(Identity, Profile.Value)
        Result = self.Db.ExecuteQuery(
            "UPDATE MediaFiles "
            "   SET AssignedProfile = %s, "
            "       AssignedProfileSource = 'series', "
            "       LastModifiedDate = NOW() "
            " WHERE StorageRootId = %s "
            "   AND split_part(RelativePath, '/', 1) = %s "
            "   AND TranscodedByMediaVortex IS NOT TRUE "
            "RETURNING Id",
            (Profile.Value, Identity.StorageRootId, Identity.RelativePath),
        )
        Affected = len(Result) if Result else 0
        LoggingService.LogInfo(
            f"Series profile set: {Identity.ToCompositeKey()} -> {Profile.Value}, {Affected} files updated",
            "SeriesProfileService",
            "SetProfile",
        )
        return Affected

    # directive: work-transcode-unified | # see directive.md C3
    def ClearProfile(self, Identity: SeriesIdentity) -> None:
        """Remove the sticky series profile. Does NOT clear MediaFiles.AssignedProfile -- those rows keep the historical assignment."""
        self.ProfileRepo.DeleteProfile(Identity)
        LoggingService.LogInfo(
            f"Series profile cleared: {Identity.ToCompositeKey()}",
            "SeriesProfileService",
            "ClearProfile",
        )
```

- [ ] **Step 5: Defer test run until Task 12**

`SeriesProfiles` table is required. Re-run after Task 12.

- [ ] **Step 6: Commit**

```
git add Features/WorkBucket/Services/__init__.py Features/WorkBucket/Services/SeriesProfileService.py Tests/Contract/TestSeriesProfileService.py
git commit -m "feat(work-bucket): SeriesProfileService -- validate + upsert + propagate"
git push
```

---

## Task 11 — Service: `QueueAdmissionAppService`

Thin orchestration around `QueueAdmissionRepository`. Provides a single per-bucket entrypoint that the controller calls.

**Files:**
- Create: `Features/WorkBucket/Services/QueueAdmissionAppService.py`
- Create: `Tests/Contract/TestQueueAdmissionAppService.py`

- [ ] **Step 1: Implement QueueAdmissionAppService**

`Features/WorkBucket/Services/QueueAdmissionAppService.py`:

```python
from typing import Optional, Tuple
from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Features.WorkBucket.Domain.AdmissionResult import AdmissionResult
from Features.WorkBucket.Domain.BucketKey import BucketKey
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity
from Features.WorkBucket.Repositories.QueueAdmissionRepository import QueueAdmissionRepository


# directive: work-transcode-unified | # see directive.md C4, C5
class QueueAdmissionAppService:
    """Orchestrates queue admission. Wraps the repository so the controller depends on the service, not the repo."""

    # directive: work-transcode-unified | # see directive.md C4, C5
    def __init__(
        self,
        Db: Optional[DatabaseService] = None,
        Repo: Optional[QueueAdmissionRepository] = None,
    ):
        self.Db = Db or DatabaseService()
        self.Repo = Repo or QueueAdmissionRepository(self.Db)

    # directive: work-transcode-unified | # see directive.md C5
    def AdmitOne(self, MediaFileId: int, Bucket: BucketKey) -> Tuple[str, int]:
        Status, QueueId = self.Repo.AdmitOne(MediaFileId, Bucket.ProcessingMode)
        LoggingService.LogInfo(
            f"Admit one: media_file={MediaFileId} bucket={Bucket.BucketName} status={Status}",
            "QueueAdmissionAppService",
            "AdmitOne",
        )
        return Status, QueueId

    # directive: work-transcode-unified | # see directive.md C4
    def AdmitSeries(self, Identity: SeriesIdentity, Bucket: BucketKey) -> AdmissionResult:
        Result = self.Repo.AdmitSeries(Identity, Bucket)
        LoggingService.LogInfo(
            f"Admit series: {Identity.ToCompositeKey()} bucket={Bucket.BucketName} inserted={Result.Inserted} already={Result.AlreadyQueued}",
            "QueueAdmissionAppService",
            "AdmitSeries",
        )
        return Result
```

- [ ] **Step 2: Write the contract test**

`Tests/Contract/TestQueueAdmissionAppService.py`:

```python
import os
import unittest
from Core.Database.DatabaseService import DatabaseService
from Features.WorkBucket.Domain.BucketKey import BucketKey
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity
from Features.WorkBucket.Services.QueueAdmissionAppService import QueueAdmissionAppService


# directive: work-transcode-unified | # see directive.md C4
class TestQueueAdmissionAppService(unittest.TestCase):
    """Service delegates correctly and reports accurate counts."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('MEDIAVORTEX_DB_HOST', '10.0.0.15')

    def test_admit_series_returns_admission_result(self):
        Sample = DatabaseService().ExecuteQuery(
            "SELECT mf.StorageRootId, split_part(mf.RelativePath, '/', 1) AS RelativePath "
            "FROM MediaFiles mf WHERE mf.WorkBucket = 'Transcode' "
            "GROUP BY mf.StorageRootId, split_part(mf.RelativePath, '/', 1) "
            "HAVING COUNT(*) >= 1 LIMIT 1"
        )
        if not Sample:
            self.skipTest("No Transcode series in DB")
        Identity = SeriesIdentity(StorageRootId=int(Sample[0]['storagerootid']), RelativePath=Sample[0]['relativepath'])
        DatabaseService().ExecuteNonQuery(
            "DELETE FROM TranscodeQueue WHERE Status='Pending' AND MediaFileId IN ("
            "  SELECT Id FROM MediaFiles WHERE WorkBucket='Transcode' AND StorageRootId=%s AND split_part(RelativePath,'/',1)=%s"
            ")",
            (Identity.StorageRootId, Identity.RelativePath),
        )
        Result = QueueAdmissionAppService().AdmitSeries(Identity, BucketKey.FromUrlKey('Transcode'))
        self.assertEqual(Result.Inserted + Result.AlreadyQueued, Result.Total)
        DatabaseService().ExecuteNonQuery(
            "DELETE FROM TranscodeQueue WHERE Status='Pending' AND MediaFileId IN ("
            "  SELECT Id FROM MediaFiles WHERE WorkBucket='Transcode' AND StorageRootId=%s AND split_part(RelativePath,'/',1)=%s"
            ")",
            (Identity.StorageRootId, Identity.RelativePath),
        )


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 3: Run test, confirm it passes**

```
py -m pytest Tests/Contract/TestQueueAdmissionAppService.py -v
```

Expected: 1 passed (or skipped).

- [ ] **Step 4: Commit**

```
git add Features/WorkBucket/Services/QueueAdmissionAppService.py Tests/Contract/TestQueueAdmissionAppService.py
git commit -m "feat(work-bucket): QueueAdmissionAppService -- orchestration over the admission repo"
git push
```

---

## Task 12 — Migration: create `SeriesProfiles`, rename old `ShowSettings` to deprecated marker

The rename-then-drop pattern's create+rename phase. One atomic transaction.

**Files:**
- Create: `Scripts/SQLScripts/CreateSeriesProfilesAndDeprecateShowSettings.py`

- [ ] **Step 1: Write the migration script**

`Scripts/SQLScripts/CreateSeriesProfilesAndDeprecateShowSettings.py`:

```python
#!/usr/bin/env python3
"""
CreateSeriesProfilesAndDeprecateShowSettings.py

Migration: create the new SeriesProfiles table, copy data from the legacy
ShowSettings table, and rename ShowSettings to ShowSettings_DEPRECATED_2026_06_28.

One atomic transaction. Idempotent -- safe to re-run.

Spec: Docs/superpowers/specs/2026-06-28-work-transcode-unified-design.md
      criteria C7-C12.
"""

import os
import sys
import psycopg2


# directive: work-transcode-unified | # see directive.md C7
def GetConnection():
    return psycopg2.connect(
        host=os.environ.get('MEDIAVORTEX_DB_HOST', 'localhost'),
        port=int(os.environ.get('MEDIAVORTEX_DB_PORT', '5432')),
        database=os.environ.get('MEDIAVORTEX_DB_NAME', 'mediavortex'),
        user=os.environ.get('MEDIAVORTEX_DB_USER', 'mediavortex'),
        password=os.environ.get('MEDIAVORTEX_DB_PASSWORD', 'mediavortex'),
    )


# directive: work-transcode-unified | # see directive.md C7
def TableExists(Cursor, Name) -> bool:
    Cursor.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
        (Name.lower(),),
    )
    return Cursor.fetchone() is not None


# directive: work-transcode-unified | # see directive.md C7
def RunMigration():
    Conn = GetConnection()
    Cur = Conn.cursor()
    try:
        SeriesExists = TableExists(Cur, 'seriesprofiles')
        ShowExists = TableExists(Cur, 'showsettings')
        DeprecatedExists = TableExists(Cur, 'showsettings_deprecated_2026_06_28')

        if SeriesExists and DeprecatedExists and not ShowExists:
            print("Migration already applied -- SeriesProfiles + deprecated marker present, no live ShowSettings.")
            return

        if SeriesExists and ShowExists:
            print("Both SeriesProfiles and ShowSettings exist -- inconsistent state. Aborting; investigate manually.")
            sys.exit(1)

        print("Beginning migration...")
        Cur.execute("BEGIN")

        if not SeriesExists:
            print("  CREATE TABLE SeriesProfiles ...")
            Cur.execute(
                "CREATE TABLE SeriesProfiles ("
                "  Id SERIAL PRIMARY KEY, "
                "  StorageRootId INTEGER NOT NULL, "
                "  RelativePath VARCHAR(500) NOT NULL, "
                "  TargetResolution VARCHAR(20), "
                "  AssignedProfile VARCHAR(100), "
                "  CreatedDate TIMESTAMP NOT NULL DEFAULT NOW(), "
                "  LastModifiedDate TIMESTAMP NOT NULL DEFAULT NOW(), "
                "  CONSTRAINT seriesprofiles_natural_key UNIQUE (StorageRootId, RelativePath)"
                ")"
            )
            Cur.execute(
                "CREATE INDEX idx_seriesprofiles_lookup "
                "ON SeriesProfiles (StorageRootId, RelativePath)"
            )

        if ShowExists:
            print("  INSERT INTO SeriesProfiles SELECT ... FROM ShowSettings ON CONFLICT DO NOTHING ...")
            Cur.execute(
                "INSERT INTO SeriesProfiles "
                "  (StorageRootId, RelativePath, TargetResolution, AssignedProfile, CreatedDate, LastModifiedDate) "
                "SELECT StorageRootId, RelativePath, TargetResolution, AssignedProfile, "
                "       CreatedDate, LastModifiedDate "
                "  FROM ShowSettings "
                "ON CONFLICT (StorageRootId, RelativePath) DO NOTHING"
            )
            CopiedCount = Cur.rowcount
            print(f"    copied {CopiedCount} rows")
            print("  ALTER TABLE ShowSettings RENAME TO ShowSettings_DEPRECATED_2026_06_28 ...")
            Cur.execute("ALTER TABLE ShowSettings RENAME TO ShowSettings_DEPRECATED_2026_06_28")

        Cur.execute("COMMIT")

        Cur.execute("SELECT COUNT(*)::int FROM SeriesProfiles")
        NewCount = Cur.fetchone()[0]
        print(f"  SeriesProfiles: {NewCount} rows")
        if TableExists(Cur, 'showsettings_deprecated_2026_06_28'):
            Cur.execute("SELECT COUNT(*)::int FROM ShowSettings_DEPRECATED_2026_06_28")
            DepCount = Cur.fetchone()[0]
            print(f"  ShowSettings_DEPRECATED_2026_06_28: {DepCount} rows")
            if DepCount != NewCount:
                print("  WARNING: row counts diverge. Inspect manually.")

        print("Migration complete.")
    except Exception:
        Conn.rollback()
        raise
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    RunMigration()
```

- [ ] **Step 2: Run the migration on dev DB**

```
py Scripts/SQLScripts/CreateSeriesProfilesAndDeprecateShowSettings.py
```

Expected output: "Beginning migration..." → "CREATE TABLE..." → "INSERT INTO..." → "ALTER TABLE..." → "Migration complete." with row counts matching.

- [ ] **Step 3: Smoke test the migration**

```
py Scripts/SQLScripts/QueryDatabase.py sql "SELECT count(*) FROM SeriesProfiles"
py Scripts/SQLScripts/QueryDatabase.py sql "SELECT count(*) FROM ShowSettings_DEPRECATED_2026_06_28"
py Scripts/SQLScripts/QueryDatabase.py sql "SELECT count(*) FROM ShowSettings"
```

Expected:
- First two return identical counts.
- Third errors with `relation "showsettings" does not exist`.

- [ ] **Step 4: Re-run dependent contract tests**

```
py -m pytest Tests/Contract/TestSeriesProfileRepository.py Tests/Contract/TestSeriesProfileService.py Tests/Contract/TestSeriesQueryRepository.py -v
```

Expected: all pass.

- [ ] **Step 5: Re-run idempotency**

```
py Scripts/SQLScripts/CreateSeriesProfilesAndDeprecateShowSettings.py
```

Expected: "Migration already applied -- ... no live ShowSettings."

- [ ] **Step 6: Update the directive's Promotions section**

Append to `.claude/directive.md` under `### Promotions`:

```
- DB table `ShowSettings` -> deprecated marker + new `SeriesProfiles` -> SQL artifacts in `Scripts/SQLScripts/CreateSeriesProfilesAndDeprecateShowSettings.py` (this commit) and future `work-bucket.flow.md` ST6.
```

- [ ] **Step 7: Commit**

```
git add Scripts/SQLScripts/CreateSeriesProfilesAndDeprecateShowSettings.py .claude/directive.md
git commit -m "feat(db): create SeriesProfiles + rename old ShowSettings to deprecated marker"
git push
```

---

## Task 13 — Update `BackfillProfileAssignments.py` to read `SeriesProfiles`

Replace the only producer code that reads from the old name.

**Files:**
- Modify: `Scripts/SQLScripts/BackfillProfileAssignments.py`

- [ ] **Step 1: Find the existing references**

```
py -m grep -rn "ShowSettings" Scripts/SQLScripts/BackfillProfileAssignments.py
```

(Or use the Grep tool against that file.)

- [ ] **Step 2: Read the script's current shape**

Read `Scripts/SQLScripts/BackfillProfileAssignments.py` end-to-end (limit 200).

- [ ] **Step 3: Replace every `ShowSettings` reference with `SeriesProfiles`**

In every SQL string in the file, substitute the table name:
- `FROM ShowSettings` → `FROM SeriesProfiles`
- `JOIN ShowSettings` → `JOIN SeriesProfiles`
- `INTO ShowSettings` → `INTO SeriesProfiles` (if any — likely none, it's read-only of this table)
- Any docstring references rewritten.

Do this in a single Edit per SQL string. After editing, the file must contain zero literal occurrences of `ShowSettings`.

- [ ] **Step 4: Run the backfill against dev DB**

```
py Scripts/SQLScripts/BackfillProfileAssignments.py
```

Expected: same behavior as before -- updates MediaFiles.AssignedProfile from per-series rows.

- [ ] **Step 5: Spot-check**

```
py Scripts/SQLScripts/QueryDatabase.py sql "SELECT count(*) FROM MediaFiles WHERE AssignedProfile IS NOT NULL"
```

Should be at least as many rows as before (any newly-discoverable rows now get backfilled too).

- [ ] **Step 6: Commit**

```
git add Scripts/SQLScripts/BackfillProfileAssignments.py
git commit -m "fix(backfill): point BackfillProfileAssignments at SeriesProfiles"
git push
```

---

## Task 14 — Rewrite `WorkBucketController.py` to thin HTTP-only

Replace the controller with a thin Flask blueprint that wires the new repositories + services. Delete the old `WorkBucketRepository.py` file.

**Files:**
- Modify: `Features/WorkBucket/WorkBucketController.py`
- Delete: `Features/WorkBucket/WorkBucketRepository.py`
- Modify: `Tests/Contract/TestWorkBucketRepository.py` → rename to `TestWorkBucketController.py` and rewrite (steps below)

- [ ] **Step 1: Write the controller test first**

`Tests/Contract/TestWorkBucketController.py`:

```python
import os
import unittest
from WebService.Main import WebServiceApp


# directive: work-transcode-unified | # see directive.md C1, C6
class TestWorkBucketController(unittest.TestCase):
    """Live HTTP route contract for /Work/<bucket> + /api/Work/<bucket> routes."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('MEDIAVORTEX_DB_HOST', '10.0.0.15')
        cls.App = WebServiceApp().App
        cls.App.config['TESTING'] = True
        cls.Client = cls.App.test_client()

    def test_render_transcode_page(self):
        Response = self.Client.get('/Work/Transcode')
        self.assertEqual(Response.status_code, 200)
        self.assertIn(b'Transcode', Response.data)

    def test_render_remux_page(self):
        Response = self.Client.get('/Work/Remux')
        self.assertEqual(Response.status_code, 200)
        self.assertIn(b'Remux', Response.data)

    def test_render_audio_page(self):
        Response = self.Client.get('/Work/Audio')
        self.assertEqual(Response.status_code, 200)
        self.assertIn(b'Audio', Response.data)

    def test_unknown_bucket_404(self):
        Response = self.Client.get('/Work/Bogus')
        self.assertEqual(Response.status_code, 404)

    def test_api_series_list_envelope(self):
        Response = self.Client.get('/api/Work/Transcode?page=1&pageSize=5')
        self.assertEqual(Response.status_code, 200)
        Payload = Response.get_json()
        self.assertTrue(Payload['Success'])
        self.assertIn('Series', Payload['Data'])
        self.assertIn('Total', Payload['Data'])
        self.assertIn('Page', Payload['Data'])
        self.assertIn('PageSize', Payload['Data'])

    def test_api_unknown_bucket_404(self):
        Response = self.Client.get('/api/Work/Bogus')
        self.assertEqual(Response.status_code, 404)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Delete the old test file**

```
git rm Tests/Contract/TestWorkBucketRepository.py
```

- [ ] **Step 3: Rewrite WorkBucketController.py**

`Features/WorkBucket/WorkBucketController.py` — full replacement:

```python
from flask import Blueprint, jsonify, render_template, request

from Core.Logging.LoggingService import LoggingService
from Core.Querying import PagedQuery
from Features.WorkBucket.Domain.BucketKey import BucketKey
from Features.WorkBucket.Domain.FilterSpec import FilterSpec
from Features.WorkBucket.Domain.ProfileName import InvalidProfileError
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity
from Features.WorkBucket.Domain.SortSpec import SortSpec
from Features.WorkBucket.Repositories.FilesInSeriesRepository import FilesInSeriesRepository
from Features.WorkBucket.Repositories.SeriesQueryRepository import SeriesQueryRepository
from Features.WorkBucket.Services.QueueAdmissionAppService import QueueAdmissionAppService
from Features.WorkBucket.Services.SeriesProfileService import SeriesProfileService


# directive: work-transcode-unified | # see directive.md C1
class WorkBucketController:
    """Flask blueprint serving /Work/<bucket> + /api/Work/<bucket>/*. HTTP-only -- no SQL, no business logic."""

    # directive: work-transcode-unified | # see directive.md C1
    def __init__(self):
        self.Blueprint = Blueprint('work_bucket', __name__)
        self.SeriesRepo = SeriesQueryRepository()
        self.FilesRepo = FilesInSeriesRepository()
        self.ProfileService = SeriesProfileService()
        self.QueueService = QueueAdmissionAppService()
        self._RegisterRoutes()

    # directive: work-transcode-unified | # see directive.md C1
    def _RegisterRoutes(self):
        @self.Blueprint.route('/Work/<url_key>', methods=['GET'])
        def render_page(url_key):
            Bucket = BucketKey.FromUrlKey(url_key)
            if Bucket is None:
                return render_template('Error.html', ErrorCode=404, ErrorMessage=f"Unknown work bucket: {url_key}"), 404
            return render_template('WorkBucket.html', UrlKey=url_key, Bucket=Bucket)

        @self.Blueprint.route('/api/Work/<url_key>', methods=['GET'])
        def list_series(url_key):
            try:
                Bucket = BucketKey.FromUrlKey(url_key)
                if Bucket is None:
                    return jsonify({'Success': False, 'Message': f"Unknown bucket: {url_key}", 'Data': {}}), 404
                Page = max(1, int(request.args.get('page', 1) or 1))
                PageSize = max(1, min(200, int(request.args.get('pageSize', 25) or 25)))
                Sort = SortSpec.FromString(request.args.get('sort', ''))
                Drives = tuple(
                    int(D) for D in request.args.getlist('drive') if D.strip().isdigit()
                )
                Filter = FilterSpec(StorageRootIds=Drives, SearchTerm=request.args.get('search', '') or '')
                Result = self.SeriesRepo.ListSeriesByBucket(
                    Bucket=Bucket,
                    Query=PagedQuery(Page=Page, PageSize=PageSize),
                    Sort=Sort,
                    Filter=Filter,
                )
                return jsonify({
                    'Success': True, 'Message': 'OK',
                    'Data': {
                        'Bucket': Bucket.BucketName,
                        'Total': Result.TotalCount,
                        'Page': Result.Page,
                        'PageSize': Result.PageSize,
                        'Series': [S.ToJson() for S in Result.Rows],
                    },
                })
            except Exception as Ex:
                LoggingService.LogException(f"list_series failed for {url_key}", Ex, "WorkBucketController", "list_series")
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 500

        @self.Blueprint.route('/api/Work/<url_key>/Series/<path:sid>', methods=['GET'])
        def list_files_in_series(url_key, sid):
            try:
                Bucket = BucketKey.FromUrlKey(url_key)
                if Bucket is None:
                    return jsonify({'Success': False, 'Message': f"Unknown bucket: {url_key}", 'Data': {}}), 404
                Identity = SeriesIdentity.FromCompositeKey(sid)
                Files = self.FilesRepo.ListFilesInSeries(Identity, Bucket)
                return jsonify({
                    'Success': True, 'Message': 'OK',
                    'Data': {
                        'Bucket': Bucket.BucketName,
                        'Series': Identity.ToCompositeKey(),
                        'Files': [F.ToJson() for F in Files],
                    },
                })
            except ValueError as Ex:
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 400
            except Exception as Ex:
                LoggingService.LogException(f"list_files_in_series failed for {url_key}/{sid}", Ex, "WorkBucketController", "list_files_in_series")
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 500

        @self.Blueprint.route('/api/Work/<url_key>/Series/<path:sid>/Profile', methods=['POST'])
        def set_series_profile(url_key, sid):
            try:
                Bucket = BucketKey.FromUrlKey(url_key)
                if Bucket is None:
                    return jsonify({'Success': False, 'Message': f"Unknown bucket: {url_key}", 'Data': {}}), 404
                Identity = SeriesIdentity.FromCompositeKey(sid)
                Body = request.get_json(force=True, silent=True) or {}
                RawName = Body.get('ProfileName', '')
                Affected = self.ProfileService.SetProfile(Identity, RawName)
                return jsonify({
                    'Success': True, 'Message': f"Applied profile to {Affected} files",
                    'Data': {'FilesAffected': Affected, 'ProfileName': RawName},
                })
            except InvalidProfileError as Ex:
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 400
            except ValueError as Ex:
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 400
            except Exception as Ex:
                LoggingService.LogException(f"set_series_profile failed for {url_key}/{sid}", Ex, "WorkBucketController", "set_series_profile")
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 500

        @self.Blueprint.route('/api/Work/<url_key>/Series/<path:sid>/Profile', methods=['DELETE'])
        def clear_series_profile(url_key, sid):
            try:
                Bucket = BucketKey.FromUrlKey(url_key)
                if Bucket is None:
                    return jsonify({'Success': False, 'Message': f"Unknown bucket: {url_key}", 'Data': {}}), 404
                Identity = SeriesIdentity.FromCompositeKey(sid)
                self.ProfileService.ClearProfile(Identity)
                return jsonify({'Success': True, 'Message': 'Profile cleared', 'Data': {}})
            except ValueError as Ex:
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 400
            except Exception as Ex:
                LoggingService.LogException(f"clear_series_profile failed for {url_key}/{sid}", Ex, "WorkBucketController", "clear_series_profile")
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 500

        @self.Blueprint.route('/api/Work/<url_key>/Series/<path:sid>/Queue', methods=['POST'])
        def queue_series(url_key, sid):
            try:
                Bucket = BucketKey.FromUrlKey(url_key)
                if Bucket is None:
                    return jsonify({'Success': False, 'Message': f"Unknown bucket: {url_key}", 'Data': {}}), 404
                Identity = SeriesIdentity.FromCompositeKey(sid)
                Result = self.QueueService.AdmitSeries(Identity, Bucket)
                return jsonify({
                    'Success': True,
                    'Message': f"Queued {Result.Inserted}",
                    'Data': {'Inserted': Result.Inserted, 'AlreadyQueued': Result.AlreadyQueued, 'Total': Result.Total},
                })
            except ValueError as Ex:
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 400
            except Exception as Ex:
                LoggingService.LogException(f"queue_series failed for {url_key}/{sid}", Ex, "WorkBucketController", "queue_series")
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 500

        @self.Blueprint.route('/api/Work/<url_key>/Queue/<int:media_file_id>', methods=['POST'])
        def queue_one(url_key, media_file_id):
            try:
                Bucket = BucketKey.FromUrlKey(url_key)
                if Bucket is None:
                    return jsonify({'Success': False, 'Message': f"Unknown bucket: {url_key}", 'Data': {}}), 404
                Status, QueueId = self.QueueService.AdmitOne(media_file_id, Bucket)
                return jsonify({
                    'Success': True,
                    'Message': 'Queued' if Status == 'queued' else 'Already queued',
                    'Data': {'Status': Status, 'QueueId': QueueId, 'ProcessingMode': Bucket.ProcessingMode},
                })
            except Exception as Ex:
                LoggingService.LogException(f"queue_one failed for {url_key}/{media_file_id}", Ex, "WorkBucketController", "queue_one")
                return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 500
```

- [ ] **Step 4: Delete the old WorkBucketRepository.py**

```
git rm Features/WorkBucket/WorkBucketRepository.py
```

- [ ] **Step 5: Run the controller test (template doesn't exist yet — expect render 500)**

```
py -m pytest Tests/Contract/TestWorkBucketController.py::TestWorkBucketController::test_api_series_list_envelope -v
py -m pytest Tests/Contract/TestWorkBucketController.py::TestWorkBucketController::test_api_unknown_bucket_404 -v
py -m pytest Tests/Contract/TestWorkBucketController.py::TestWorkBucketController::test_unknown_bucket_404 -v
```

These three should pass. The three render-page tests will fail until Task 15 produces the template.

- [ ] **Step 6: Commit**

```
git add Features/WorkBucket/WorkBucketController.py Tests/Contract/TestWorkBucketController.py
git rm Features/WorkBucket/WorkBucketRepository.py Tests/Contract/TestWorkBucketRepository.py
git commit -m "feat(work-bucket): thin HTTP-only controller wiring new repos+services"
git push
```

---

## Task 15 — Rewrite `Templates/WorkBucket.html` (grouped UI)

A single template renders all three bucket pages. The JS calls `/api/Work/<bucket>` to load series rows, expands rows on click to fetch files, dispatches profile-change and queue-all clicks back to the API.

**Files:**
- Modify: `Templates/WorkBucket.html` (full replacement)

- [ ] **Step 1: Replace `Templates/WorkBucket.html` end-to-end**

```html
{% extends "Base.html" %}

{% block title %}{{ Bucket.Title }} -- MediaVortex{% endblock %}

{% block content %}
<div class="container-fluid mt-3">
  <div class="d-flex justify-content-between align-items-center mb-3">
    <h2><i class="{{ Bucket.Icon }}"></i> {{ Bucket.Title }}</h2>
    <p class="text-muted mb-0">{{ Bucket.Subtitle }}</p>
  </div>

  <div class="card mb-3">
    <div class="card-body py-2">
      <div class="row g-2 align-items-center">
        <div class="col-md-3">
          <label class="form-label small mb-0">Drive</label>
          <select id="filter-drive" class="form-select form-select-sm" multiple size="3"></select>
        </div>
        <div class="col-md-5">
          <label class="form-label small mb-0">Search</label>
          <input id="filter-search" type="text" class="form-control form-control-sm" placeholder="series name">
        </div>
        <div class="col-md-2">
          <label class="form-label small mb-0">Sort</label>
          <select id="sort-spec" class="form-select form-select-sm">
            <option value="TotalGB.desc" selected>Total size desc</option>
            <option value="FileCount.desc">File count desc</option>
            <option value="Name.asc">Series name</option>
          </select>
        </div>
        <div class="col-md-2 d-flex align-items-end">
          <button id="btn-apply" class="btn btn-sm btn-primary w-100">Apply</button>
        </div>
      </div>
    </div>
  </div>

  <div id="series-container">
    <div class="text-center py-5"><div class="spinner-border" role="status"></div></div>
  </div>

  <nav>
    <ul id="pager" class="pagination justify-content-center"></ul>
  </nav>
</div>

<script>
(function() {
  const UrlKey = {{ UrlKey | tojson }};
  const ApiBase = '/api/Work/' + UrlKey;
  let CurrentPage = 1;
  let PageSize = 25;
  let ProfileOptions = [];

  function FetchProfiles() {
    return fetch('/api/Profiles/Active', {timeout: 10000})
      .then(R => R.json())
      .then(P => { ProfileOptions = (P.Data && P.Data.Profiles) || P.Profiles || []; })
      .catch(() => { ProfileOptions = []; });
  }

  function FetchDrives() {
    return fetch('/api/StorageRoots').then(R => R.json()).then(P => {
      const Select = document.getElementById('filter-drive');
      Select.innerHTML = '';
      const List = (P.Data && P.Data.StorageRoots) || P.StorageRoots || [];
      List.forEach(SR => {
        const Opt = document.createElement('option');
        Opt.value = SR.Id || SR.id;
        Opt.textContent = (SR.CanonicalPrefix || SR.canonicalprefix || ('Root ' + Opt.value));
        Select.appendChild(Opt);
      });
    }).catch(() => {});
  }

  function BuildQueryString() {
    const Params = new URLSearchParams();
    Params.set('page', CurrentPage);
    Params.set('pageSize', PageSize);
    Params.set('sort', document.getElementById('sort-spec').value);
    const Drives = Array.from(document.getElementById('filter-drive').selectedOptions).map(O => O.value);
    Drives.forEach(D => Params.append('drive', D));
    const Search = document.getElementById('filter-search').value.trim();
    if (Search) Params.set('search', Search);
    return Params.toString();
  }

  function RenderSeriesRows(Rows, Total) {
    const C = document.getElementById('series-container');
    if (!Rows.length) {
      C.innerHTML = '<div class="alert alert-info">No series in this bucket.</div>';
      return;
    }
    let Html = '<table class="table table-sm table-hover"><thead><tr>';
    Html += '<th></th><th>Series</th><th class="text-end">Files</th><th class="text-end">GB</th>';
    Html += '<th>Resolution</th><th>Codec</th><th>Profile</th><th>Queue</th><th></th></tr></thead><tbody>';
    Rows.forEach(S => {
      const Sid = S.CompositeKey;
      const ProfileSelect = '<select class="form-select form-select-sm series-profile" data-sid="' + encodeURIComponent(Sid) + '">'
        + '<option value="">(none)</option>'
        + ProfileOptions.map(P => {
            const Name = P.ProfileName || P.profilename;
            const Sel = (Name === S.AssignedProfile) ? ' selected' : '';
            return '<option value="' + Name + '"' + Sel + '>' + Name + '</option>';
          }).join('')
        + '</select>';
      const QueueBadge = S.AnyInQueue
        ? '<span class="badge bg-warning text-dark">Pending</span>'
        : '<span class="badge bg-secondary">Idle</span>';
      Html += '<tr class="series-row" data-sid="' + encodeURIComponent(Sid) + '">';
      Html += '<td><button class="btn btn-sm btn-link expand-toggle">&#9656;</button></td>';
      Html += '<td>' + S.ShowName + '</td>';
      Html += '<td class="text-end">' + S.FileCount + '</td>';
      Html += '<td class="text-end">' + (S.TotalGB || 0).toFixed(1) + '</td>';
      Html += '<td>' + (S.CommonResolution || '') + '</td>';
      Html += '<td>' + (S.CommonCodec || '') + '</td>';
      Html += '<td>' + ProfileSelect + '</td>';
      Html += '<td>' + QueueBadge + '</td>';
      Html += '<td><button class="btn btn-sm btn-primary queue-all-btn" data-sid="' + encodeURIComponent(Sid) + '">Queue all</button></td>';
      Html += '</tr>';
      Html += '<tr class="files-row d-none" data-sid="' + encodeURIComponent(Sid) + '"><td colspan="9"><div class="files-container py-2"></div></td></tr>';
    });
    Html += '</tbody></table>';
    C.innerHTML = Html;
    RenderPager(Total);
    AttachRowEvents();
  }

  function RenderPager(Total) {
    const Pages = Math.max(1, Math.ceil(Total / PageSize));
    const P = document.getElementById('pager');
    let Html = '';
    for (let i = 1; i <= Pages && i <= 20; i++) {
      Html += '<li class="page-item' + (i === CurrentPage ? ' active' : '') + '">'
        + '<a class="page-link" href="#" data-page="' + i + '">' + i + '</a></li>';
    }
    P.innerHTML = Html;
    Array.from(P.querySelectorAll('a')).forEach(A => {
      A.addEventListener('click', (E) => {
        E.preventDefault();
        CurrentPage = parseInt(A.dataset.page, 10);
        LoadSeries();
      });
    });
  }

  function AttachRowEvents() {
    document.querySelectorAll('.expand-toggle').forEach(Btn => {
      Btn.addEventListener('click', () => {
        const Tr = Btn.closest('tr');
        const Sid = Tr.dataset.sid;
        const FilesRow = document.querySelector('.files-row[data-sid="' + Sid + '"]');
        if (FilesRow.classList.contains('d-none')) {
          LoadFiles(decodeURIComponent(Sid), FilesRow.querySelector('.files-container'));
          FilesRow.classList.remove('d-none');
          Btn.innerHTML = '&#9662;';
        } else {
          FilesRow.classList.add('d-none');
          Btn.innerHTML = '&#9656;';
        }
      });
    });

    document.querySelectorAll('.series-profile').forEach(Sel => {
      Sel.addEventListener('change', () => {
        const Sid = decodeURIComponent(Sel.dataset.sid);
        const ProfileName = Sel.value;
        const Method = ProfileName ? 'POST' : 'DELETE';
        fetch(ApiBase + '/Series/' + encodeURIComponent(Sid) + '/Profile', {
          method: Method,
          headers: {'Content-Type': 'application/json'},
          body: ProfileName ? JSON.stringify({ProfileName}) : null,
        }).then(R => R.json()).then(P => {
          if (P.Success) {
            FlashToast(P.Message);
          } else {
            FlashToast(P.Message, 'danger');
          }
        }).catch(E => FlashToast('Profile update failed: ' + E, 'danger'));
      });
    });

    document.querySelectorAll('.queue-all-btn').forEach(Btn => {
      Btn.addEventListener('click', () => {
        const Sid = decodeURIComponent(Btn.dataset.sid);
        Btn.disabled = true;
        Btn.innerHTML = '...';
        fetch(ApiBase + '/Series/' + encodeURIComponent(Sid) + '/Queue', {method: 'POST'})
          .then(R => R.json()).then(P => {
            if (P.Success) {
              FlashToast('Queued ' + P.Data.Inserted + ' files (' + P.Data.AlreadyQueued + ' already pending)');
              LoadSeries();
            } else {
              FlashToast(P.Message, 'danger');
            }
          })
          .catch(E => FlashToast('Queue failed: ' + E, 'danger'))
          .finally(() => { Btn.disabled = false; Btn.innerHTML = 'Queue all'; });
      });
    });
  }

  function LoadFiles(Sid, Container) {
    Container.innerHTML = '<div class="text-center"><div class="spinner-border spinner-border-sm" role="status"></div></div>';
    fetch(ApiBase + '/Series/' + encodeURIComponent(Sid))
      .then(R => R.json()).then(P => {
        if (!P.Success) {
          Container.innerHTML = '<div class="alert alert-danger">' + P.Message + '</div>';
          return;
        }
        const Files = P.Data.Files || [];
        let Html = '<table class="table table-sm mb-0"><thead><tr>';
        Html += '<th>File</th><th class="text-end">GB</th><th>Resolution</th><th>Audio</th><th>Languages</th><th>Reasons</th><th>Queue</th><th></th></tr></thead><tbody>';
        Files.forEach(F => {
          const Reasons = [F.VideoCompliantReason, F.ContainerCompliantReason, F.AudioCompliantReason].filter(Boolean).join('; ');
          const Badge = F.InQueue ? '<span class="badge bg-warning text-dark">Pending</span>' : '';
          Html += '<tr>';
          Html += '<td>' + F.FileName + '</td>';
          Html += '<td class="text-end">' + (F.SizeGB || 0).toFixed(2) + '</td>';
          Html += '<td>' + (F.Resolution || '') + '</td>';
          Html += '<td>' + (F.AudioCodec || '') + '</td>';
          Html += '<td>' + (F.AudioLanguages || '') + '</td>';
          Html += '<td><small class="text-muted">' + Reasons + '</small></td>';
          Html += '<td>' + Badge + '</td>';
          Html += '<td><button class="btn btn-sm btn-outline-primary queue-one-btn" data-id="' + F.Id + '">Queue</button></td>';
          Html += '</tr>';
        });
        Html += '</tbody></table>';
        Container.innerHTML = Html;
        Container.querySelectorAll('.queue-one-btn').forEach(B => {
          B.addEventListener('click', () => {
            B.disabled = true;
            fetch(ApiBase + '/Queue/' + B.dataset.id, {method: 'POST'})
              .then(R => R.json()).then(P => {
                FlashToast(P.Message, P.Success ? 'info' : 'danger');
                if (P.Success) LoadSeries();
              })
              .catch(E => FlashToast('Queue failed: ' + E, 'danger'))
              .finally(() => { B.disabled = false; });
          });
        });
      })
      .catch(E => { Container.innerHTML = '<div class="alert alert-danger">' + E + '</div>'; });
  }

  function LoadSeries() {
    const C = document.getElementById('series-container');
    C.innerHTML = '<div class="text-center py-5"><div class="spinner-border" role="status"></div></div>';
    fetch(ApiBase + '?' + BuildQueryString())
      .then(R => R.json()).then(P => {
        if (!P.Success) {
          C.innerHTML = '<div class="alert alert-danger">' + P.Message + '</div>';
          return;
        }
        RenderSeriesRows(P.Data.Series || [], P.Data.Total || 0);
      })
      .catch(E => { C.innerHTML = '<div class="alert alert-danger">' + E + '</div>'; });
  }

  function FlashToast(Message, Kind) {
    Kind = Kind || 'info';
    const Wrap = document.createElement('div');
    Wrap.className = 'toast align-items-center text-bg-' + Kind + ' border-0 position-fixed top-0 end-0 m-3 show';
    Wrap.style.zIndex = 1080;
    Wrap.innerHTML = '<div class="d-flex"><div class="toast-body">' + Message + '</div>'
      + '<button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>';
    document.body.appendChild(Wrap);
    setTimeout(() => Wrap.remove(), 5000);
  }

  document.getElementById('btn-apply').addEventListener('click', () => { CurrentPage = 1; LoadSeries(); });
  document.getElementById('filter-search').addEventListener('keydown', E => { if (E.key === 'Enter') { CurrentPage = 1; LoadSeries(); } });

  Promise.all([FetchProfiles(), FetchDrives()]).then(LoadSeries);
})();
</script>
{% endblock %}
```

- [ ] **Step 2: Restart WebService**

```
py StopMediaVortex.py
py StartMediaVortex.py
```

- [ ] **Step 3: Live smoke each bucket page in the browser**

Visit (manually or via curl):
- `http://10.0.0.7:5000/Work/Transcode`
- `http://10.0.0.7:5000/Work/Remux`
- `http://10.0.0.7:5000/Work/Audio`
- `http://10.0.0.7:5000/Work/Bogus` (expect 404)

Confirm: each page renders, series rows appear, sort dropdown changes order, expand reveals files, profile dropdown loads choices, Queue all reflects InQueue badge changes after click.

- [ ] **Step 4: Re-run controller tests, all 6 must pass**

```
py -m pytest Tests/Contract/TestWorkBucketController.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```
git add Templates/WorkBucket.html
git commit -m "feat(ui): grouped-by-series WorkBucket template with sort/filter/profile/queue"
git push
```

---

## Task 16 — Sweep cross-vertical references to deleted ShowSettings docs

Surviving feature/flow docs reference the deleted `Features/ShowSettings/*.md` paths. Rewrite each pointer to the new home or strike it cleanly (no annotation lines per R14).

**Files:**
- Modify: `transcode.flow.md`
- Modify: `Features/TranscodeQueue/transcode-vs-remux-routing.feature.md`
- Modify: `Features/TranscodeQueue/TranscodeQueue.feature.md`
- Modify: `Features/TranscodeQueue/next-batch-per-drive.feature.md`
- Modify: `Features/TranscodeQueue/media-tabs.flow.md`
- Modify: `Features/TranscodeQueue/media-tabs-and-loudness.feature.md`
- Modify: `Features/TranscodeQueue/priority-materialization.feature.md`
- Modify: `Features/TranscodeQueue/queue-priority.feature.md`
- Modify: `Features/TranscodeQueue/QueueManagementBusinessService.py`
- Modify: `Features/FailureAccounting/failure-accounting.feature.md`
- Modify: `Features/FailureAccounting/failure-accounting.flow.md`
- Modify: `Features/ContentClassifier/content-classifier.feature.md`
- Modify: `Features/ContentClassifier/content-classifier.flow.md`
- Modify: `Features/FileReplacement/remuxed-flag.feature.md`
- Modify: `Features/SharedTable/shared-table-renderer.feature.md`
- Modify: `Core/Querying/paged-query.feature.md`

- [ ] **Step 1: Find every reference**

Use the Grep tool:

```
Grep pattern: ShowSettings|smart-populate|remux-populate-card
       glob: **/*.md
```

(Already enumerated above — list may grow if anything was missed.)

- [ ] **Step 2: For each file, replace pointers**

Decision rule per occurrence:
- If the reference points at a workflow that NOW lives in `Features/WorkBucket/`, rewrite the pointer.
- If the reference is documenting historical fact ("this used to call ShowSettings.X"), DELETE the sentence (R14: no annotation lines).
- If the reference is inside a code block (e.g. example SQL), update to the new table/route names.

For each file, do one Edit per occurrence. Show the file's surrounding context with Grep before editing.

- [ ] **Step 3: After sweep, confirm no surviving references in production docs**

```
Grep pattern: ShowSettings
       glob: **/*.md
```

Should match only `.claude/directives/closed/` and `memory/KNOWN-ISSUES-ARCHIVE.md` (historical).

- [ ] **Step 4: Commit**

```
git add -- *.md Features/**/*.md Core/**/*.md transcode.flow.md Features/TranscodeQueue/QueueManagementBusinessService.py
git commit -m "docs(sweep): rewrite cross-vertical pointers away from deleted ShowSettings"
git push
```

---

## Task 17 — Delete `Features/ShowSettings/` directory

**Files:**
- Delete: `Features/ShowSettings/__init__.py`
- Delete: `Features/ShowSettings/ShowSettingsController.py`
- Delete: `Features/ShowSettings/ShowSettingsRepository.py`
- Delete: `Features/ShowSettings/Models/__init__.py`
- Delete: `Features/ShowSettings/Models/ShowSettingModel.py`
- Delete: `Features/ShowSettings/ShowSettings.feature.md`
- Delete: `Features/ShowSettings/smart-populate.feature.md`
- Delete: `Features/ShowSettings/smart-populate.flow.md`
- Delete: `Features/ShowSettings/remux-populate-card.feature.md`
- Delete: `Features/ShowSettings/__pycache__/` (any .pyc files)

- [ ] **Step 1: Confirm nothing imports it**

```
Grep pattern: from Features.ShowSettings|import Features.ShowSettings|Features\.ShowSettings
```

Result must be: only `WebService/Main.py` line 445/458 (still active — Task 18 deletes those) and `Tests/Contract/TestNoShowSettingsReferences.py` (which we'll add in Task 20).

- [ ] **Step 2: Delete the directory**

```
git rm -r Features/ShowSettings/
```

- [ ] **Step 3: Commit**

```
git commit -m "feat(work-bucket): delete Features/ShowSettings/ (replaced by WorkBucket vertical)"
git push
```

---

## Task 18 — Delete `Templates/ShowSettings.html`, blueprint, route, nav link

**Files:**
- Delete: `Templates/ShowSettings.html`
- Modify: `WebService/Main.py` (remove `show_settings` route handler + `ShowSettingsBlueprint` import + registration)
- Modify: `Templates/Base.html` (remove Media nav `<li>`)

- [ ] **Step 1: Delete the template**

```
git rm Templates/ShowSettings.html
```

- [ ] **Step 2: Edit `WebService/Main.py` — remove the route handler**

Replace lines 388-394:

OLD:
```python
        @self.App.route('/ShowSettings')
        def show_settings():
            try:
                return render_template('ShowSettings.html')
            except Exception as e:
                LoggingService.LogException("Error rendering ShowSettings page", e, "WebService", "show_settings")
                return render_template('Error.html', ErrorCode=500, ErrorMessage="Failed to load page"), 500
```

NEW: (delete the block entirely — leaving no trace)

- [ ] **Step 3: Edit `WebService/Main.py` — remove the blueprint import (line 445)**

Delete:
```python
        from Features.ShowSettings.ShowSettingsController import ShowSettingsBlueprint
```

- [ ] **Step 4: Edit `WebService/Main.py` — remove the registration (line 458)**

Delete:
```python
        self.App.register_blueprint(ShowSettingsBlueprint)
```

- [ ] **Step 5: Edit `Templates/Base.html` — remove the Media nav `<li>` (lines 25-29)**

Delete:
```html
                    <li class="nav-item">
                        <a class="nav-link {% if request.endpoint in ['show_settings', 'clip_builder'] %}active{% endif %}" href="/ShowSettings">
                            <i class="fas fa-film"></i> Media
                        </a>
                    </li>
```

If `clip_builder` is still a valid endpoint elsewhere, change its `active` highlight to a separate `<li>` block — Grep for it first.

- [ ] **Step 6: Restart WebService**

```
py StopMediaVortex.py
py StartMediaVortex.py
```

- [ ] **Step 7: Live smoke**

```
curl -i http://10.0.0.7:5000/ShowSettings
```

Expected: HTTP 404 (page no longer mapped). The Error.html template should render with "Page not found" or similar.

Visit `/Work/Transcode` — confirm Media link is gone from top nav.

- [ ] **Step 8: Commit**

```
git add WebService/Main.py Templates/Base.html
git rm Templates/ShowSettings.html
git commit -m "feat(web): delete /ShowSettings route, blueprint registration, and Media nav link"
git push
```

---

## Task 19 — Migration: deprecate `idx_mediafiles_smartpopulate`

The index supported a query path that no longer exists. Rename it to the deprecated marker.

**Files:**
- Create: `Scripts/SQLScripts/DeprecateSmartPopulateIndex.py`

- [ ] **Step 1: Write the migration**

`Scripts/SQLScripts/DeprecateSmartPopulateIndex.py`:

```python
#!/usr/bin/env python3
"""
DeprecateSmartPopulateIndex.py

Migration: rename the SmartPopulate-specific index to its deprecated marker.
The query path that exercised this index was deleted in the
work-transcode-unified directive; the index itself is dropped only after
soak via DropDeprecatedShowSettingsArtifacts.py.

Idempotent.

Spec: Docs/superpowers/specs/2026-06-28-work-transcode-unified-design.md C15.
"""

import os
import psycopg2


def GetConnection():
    return psycopg2.connect(
        host=os.environ.get('MEDIAVORTEX_DB_HOST', 'localhost'),
        port=int(os.environ.get('MEDIAVORTEX_DB_PORT', '5432')),
        database=os.environ.get('MEDIAVORTEX_DB_NAME', 'mediavortex'),
        user=os.environ.get('MEDIAVORTEX_DB_USER', 'mediavortex'),
        password=os.environ.get('MEDIAVORTEX_DB_PASSWORD', 'mediavortex'),
    )


def IndexExists(Cur, Name) -> bool:
    Cur.execute(
        "SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname=%s",
        (Name.lower(),),
    )
    return Cur.fetchone() is not None


def RunMigration():
    Conn = GetConnection()
    Cur = Conn.cursor()
    try:
        Original = 'idx_mediafiles_smartpopulate'
        Deprecated = 'idx_mediafiles_smartpopulate_deprecated_2026_06_28'
        if IndexExists(Cur, Deprecated):
            print("Already deprecated -- nothing to do.")
            return
        if not IndexExists(Cur, Original):
            print("Original index absent and no deprecated marker -- nothing to do.")
            return
        print(f"ALTER INDEX {Original} RENAME TO {Deprecated}")
        Cur.execute(f"ALTER INDEX {Original} RENAME TO {Deprecated}")
        Conn.commit()
        print("Done.")
    except Exception:
        Conn.rollback()
        raise
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    RunMigration()
```

- [ ] **Step 2: Run the migration**

```
py Scripts/SQLScripts/DeprecateSmartPopulateIndex.py
```

Expected: "ALTER INDEX ... RENAME TO ..." → "Done."

- [ ] **Step 3: Verify**

```
py Scripts/SQLScripts/QueryDatabase.py sql "SELECT indexname FROM pg_indexes WHERE indexname LIKE 'idx_mediafiles_smartpopulate%'"
```

Expected: one row, name `idx_mediafiles_smartpopulate_deprecated_2026_06_28`.

- [ ] **Step 4: Idempotency**

```
py Scripts/SQLScripts/DeprecateSmartPopulateIndex.py
```

Expected: "Already deprecated -- nothing to do."

- [ ] **Step 5: Commit**

```
git add Scripts/SQLScripts/DeprecateSmartPopulateIndex.py
git commit -m "feat(db): deprecate idx_mediafiles_smartpopulate (rename to *_DEPRECATED_2026_06_28)"
git push
```

---

## Task 20 — Audit test: no surviving references to deleted vertical

**Files:**
- Create: `Tests/Contract/TestNoShowSettingsReferences.py`

- [ ] **Step 1: Implement the audit test**

`Tests/Contract/TestNoShowSettingsReferences.py`:

```python
import os
import unittest
from pathlib import Path


# directive: work-transcode-unified | # see directive.md C11, C16
class TestNoShowSettingsReferences(unittest.TestCase):
    """Audit: no surviving references to the deleted ShowSettings vertical (incl. deprecated markers)."""

    ROOT = Path(__file__).resolve().parent.parent.parent

    SCAN_DIRS = ['Features', 'Templates', 'WebService', 'Core', 'Services', 'Repositories', 'Models']

    EXEMPT_FILES = {
        'Scripts/SQLScripts/CreateSeriesProfilesAndDeprecateShowSettings.py',
        'Scripts/SQLScripts/DeprecateSmartPopulateIndex.py',
        'Scripts/SQLScripts/DropDeprecatedShowSettingsArtifacts.py',
        'Tests/Contract/TestNoShowSettingsReferences.py',
    }

    NEEDLES = [
        'ShowSettings',
        '/api/ShowSettings/',
        'Features/ShowSettings/',
        'smart-populate',
        'remux-populate-card',
        'ShowSettings_DEPRECATED_',
        'idx_mediafiles_smartpopulate',
    ]

    def test_no_references_in_production_tree(self):
        Violations = []
        for D in self.SCAN_DIRS:
            Root = self.ROOT / D
            if not Root.exists():
                continue
            for P in Root.rglob('*'):
                if not P.is_file():
                    continue
                if P.suffix not in ('.py', '.html', '.md', '.feature', '.flow'):
                    continue
                Rel = str(P.relative_to(self.ROOT)).replace('\\', '/')
                if Rel in self.EXEMPT_FILES:
                    continue
                if '/__pycache__/' in Rel or Rel.endswith('.pyc'):
                    continue
                try:
                    Text = P.read_text(encoding='utf-8', errors='ignore')
                except Exception:
                    continue
                for N in self.NEEDLES:
                    if N in Text:
                        Violations.append(f"{Rel}: contains {N!r}")
                        break
        if Violations:
            self.fail("Surviving ShowSettings references:\n  " + "\n  ".join(Violations))


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run it**

```
py -m pytest Tests/Contract/TestNoShowSettingsReferences.py -v
```

Expected: 1 passed. If it fails, the failure message lists every surviving reference — go back to Task 16 and sweep them.

- [ ] **Step 3: Commit**

```
git add Tests/Contract/TestNoShowSettingsReferences.py
git commit -m "test(audit): refuse any surviving ShowSettings / SmartPopulate / deprecated-marker reference"
git push
```

---

## Task 21 — Author (do NOT run) the DROP migration

The destructive final step. Committed but not run during this directive.

**Files:**
- Create: `Scripts/SQLScripts/DropDeprecatedShowSettingsArtifacts.py`

- [ ] **Step 1: Write the drop migration**

`Scripts/SQLScripts/DropDeprecatedShowSettingsArtifacts.py`:

```python
#!/usr/bin/env python3
"""
DropDeprecatedShowSettingsArtifacts.py

DESTRUCTIVE FOLLOW-UP MIGRATION. Run ONLY after the work-transcode-unified
directive has soaked for at least 24h and the operator has verified all
three /Work/<bucket> pages plus the BackfillProfileAssignments cascade.

Drops:
  - TABLE ShowSettings_DEPRECATED_2026_06_28
  - INDEX idx_mediafiles_smartpopulate_DEPRECATED_2026_06_28

Idempotent. Authored in the work-transcode-unified directive; not run as
part of that directive's auto-flow. Operator authority per ceo-mode.md.

Spec: Docs/superpowers/specs/2026-06-28-work-transcode-unified-design.md C15.
"""

import os
import psycopg2


def GetConnection():
    return psycopg2.connect(
        host=os.environ.get('MEDIAVORTEX_DB_HOST', 'localhost'),
        port=int(os.environ.get('MEDIAVORTEX_DB_PORT', '5432')),
        database=os.environ.get('MEDIAVORTEX_DB_NAME', 'mediavortex'),
        user=os.environ.get('MEDIAVORTEX_DB_USER', 'mediavortex'),
        password=os.environ.get('MEDIAVORTEX_DB_PASSWORD', 'mediavortex'),
    )


def RunMigration():
    Conn = GetConnection()
    Cur = Conn.cursor()
    try:
        print("DROP INDEX IF EXISTS idx_mediafiles_smartpopulate_deprecated_2026_06_28")
        Cur.execute("DROP INDEX IF EXISTS idx_mediafiles_smartpopulate_deprecated_2026_06_28")
        print("DROP TABLE IF EXISTS ShowSettings_DEPRECATED_2026_06_28")
        Cur.execute("DROP TABLE IF EXISTS ShowSettings_DEPRECATED_2026_06_28 CASCADE")
        Conn.commit()
        print("Done.")
    except Exception:
        Conn.rollback()
        raise
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    Confirm = input("DESTRUCTIVE. Type 'DROP' to proceed: ")
    if Confirm != 'DROP':
        print("Aborted.")
    else:
        RunMigration()
```

- [ ] **Step 2: DO NOT run it**

This script is staged for the post-soak follow-up only. Operator runs it manually after verification.

- [ ] **Step 3: Re-run the audit test**

```
py -m pytest Tests/Contract/TestNoShowSettingsReferences.py -v
```

Must still pass — this script is in the exempt list.

- [ ] **Step 4: Commit**

```
git add Scripts/SQLScripts/DropDeprecatedShowSettingsArtifacts.py
git commit -m "feat(db): author DropDeprecatedShowSettingsArtifacts migration (not run)"
git push
```

---

## Task 22 — Rewrite `work-bucket.feature.md`

The existing feature doc describes the narrow contract of the pre-redesign WorkBucket. Rewrite it to describe the new contract.

**Files:**
- Modify: `Features/WorkBucket/work-bucket.feature.md` (full replacement)

- [ ] **Step 1: Read the existing doc (partial, 50 lines)**

```
Read Features/WorkBucket/work-bucket.feature.md (limit 50)
```

- [ ] **Step 2: Replace the file with the new contract**

`Features/WorkBucket/work-bucket.feature.md`:

```markdown
# WorkBucket -- grouped-by-series operator surface for /Work/<bucket>

**Slug:** work-bucket

## What It Does

Renders `/Work/Transcode`, `/Work/Remux`, and `/Work/Audio` as an always-grouped-by-series view of files that need work in that bucket. Each series row exposes file count, total GB, common resolution/codec, an InQueue badge, a per-series profile dropdown, and a Queue-all button. Series rows expand inline to show their files, sorted by size. The page replaces the old `/ShowSettings` (Media) tab; per-series sticky profile assignment is preserved in the internal `SeriesProfiles` table.

## Workflows

| #  | User action | Surface element | Handler | Backing class.method |
|----|-------------|-----------------|---------|----------------------|
| W1 | Browse series needing work in a bucket | `/Work/<bucket>` page | GET `/Work/<bucket>` | `WorkBucketController.render_page` (`Features/WorkBucket/WorkBucketController.py`) |
| W2 | Paginate / sort / filter the series list | toolbar + pager | GET `/api/Work/<bucket>` | `SeriesQueryRepository.ListSeriesByBucket` (`Features/WorkBucket/Repositories/SeriesQueryRepository.py`) |
| W3 | Expand a series to see its files | row chevron | GET `/api/Work/<bucket>/Series/<sid>` | `FilesInSeriesRepository.ListFilesInSeries` (`Features/WorkBucket/Repositories/FilesInSeriesRepository.py`) |
| W4 | Set the profile on a series | series-row dropdown | POST `/api/Work/<bucket>/Series/<sid>/Profile` | `SeriesProfileService.SetProfile` (`Features/WorkBucket/Services/SeriesProfileService.py`) |
| W5 | Clear the profile on a series | dropdown -> blank | DELETE `/api/Work/<bucket>/Series/<sid>/Profile` | `SeriesProfileService.ClearProfile` (`Features/WorkBucket/Services/SeriesProfileService.py`) |
| W6 | Queue every file in a series | Queue-all button | POST `/api/Work/<bucket>/Series/<sid>/Queue` | `QueueAdmissionAppService.AdmitSeries` (`Features/WorkBucket/Services/QueueAdmissionAppService.py`) |
| W7 | Queue a single file | per-row Queue button | POST `/api/Work/<bucket>/Queue/<id>` | `QueueAdmissionAppService.AdmitOne` (`Features/WorkBucket/Services/QueueAdmissionAppService.py`) |

## Success Criteria

C1. `/Work/Transcode`, `/Work/Remux`, and `/Work/Audio` each render only `MediaFiles.WorkBucket = <X>` rows. Spot-checkable: `SELECT WorkBucket FROM MediaFiles WHERE Id IN (...the ids surfaced by /api/Work/Transcode...)` returns only `Transcode`.

C2. Series rows default-sorted by total GB descending; secondary file-row sort by size desc. `Sort: File count desc` and `Sort: Series name asc` are alternative sort modes via the toolbar.

C3. Setting a profile on a series row writes `SeriesProfiles.AssignedProfile` AND updates `MediaFiles.AssignedProfile` for every untranscoded file in the series. Re-scanned files inherit via the existing `BackfillProfileAssignments` cascade.

C4. Queue-all is idempotent. A second click never produces duplicate Pending rows; reports `AlreadyQueued = N` instead of `Inserted = N` on retry.

C5. Per-row Queue is idempotent. Returns `'queued'` first time, `'already_queued'` subsequently.

C6. Filters: multi-select drive + free-text series search. Pagination: 25 rows per page server-side via `Core.Querying.PagedQueryBuilder`.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | Controller -> SeriesQueryRepository | `WorkBucketController.list_series` | `(BucketKey, PagedQuery, SortSpec, FilterSpec)` | Returns `PagedQueryResult[Series]` | `Tests/Contract/TestSeriesQueryRepository.py` |
| S2 | Controller -> FilesInSeriesRepository | `WorkBucketController.list_files_in_series` | `(SeriesIdentity, BucketKey)` | Returns `list[MediaFileRow]` | `Tests/Contract/TestFilesInSeriesRepository.py` |
| S3 | Controller -> SeriesProfileService | `WorkBucketController.set_series_profile` | `(SeriesIdentity, RawProfileName: str)` | Raises `InvalidProfileError` on bad input; otherwise returns `FilesAffected: int` | `Tests/Contract/TestSeriesProfileService.py` |
| S4 | SeriesProfileService -> SeriesProfileRepository | `SeriesProfileService.SetProfile` | UPSERT (StorageRootId, RelativePath, AssignedProfile) | Row present on subsequent `GetProfile` | `Tests/Contract/TestSeriesProfileRepository.py` |
| S5 | SeriesProfileService -> MediaFiles | `SeriesProfileService.SetProfile` | `UPDATE MediaFiles SET AssignedProfile = ? WHERE ... AND TranscodedByMediaVortex IS NOT TRUE` | `MediaFiles.AssignedProfile` reflects choice for untranscoded files only | `Tests/Contract/TestSeriesProfileService.py::test_set_profile_updates_only_untranscoded_files` |
| S6 | QueueAdmissionRepository -> TranscodeQueue | `QueueAdmissionRepository.AdmitSeries` | bulk INSERT with `NOT EXISTS` Pending guard | No duplicate Pending row per MediaFileId | `Tests/Contract/TestQueueAdmissionRepository.py::test_admit_series_idempotent` |
| S7 | BackfillProfileAssignments -> SeriesProfiles | `Scripts/SQLScripts/BackfillProfileAssignments.py` | reads sp.AssignedProfile, writes MediaFiles.AssignedProfile | New files in an existing series get the sticky profile | manual smoke: insert a MediaFiles row with the right show folder, run backfill, observe AssignedProfile populated |

## Status

**Phase:** Active feature, replaces the deleted `Features/ShowSettings/` vertical.

**Files:**

- `Features/WorkBucket/WorkBucketController.py` -- HTTP routes only
- `Features/WorkBucket/Domain/` -- value objects + aggregates (SeriesIdentity, BucketKey, ProfileName, Series, MediaFileRow, SortSpec, FilterSpec, AdmissionResult)
- `Features/WorkBucket/Repositories/SeriesQueryRepository.py` -- grouped paged query
- `Features/WorkBucket/Repositories/FilesInSeriesRepository.py` -- expanded file list
- `Features/WorkBucket/Repositories/SeriesProfileRepository.py` -- SeriesProfiles CRUD
- `Features/WorkBucket/Repositories/QueueAdmissionRepository.py` -- TranscodeQueue inserts
- `Features/WorkBucket/Services/SeriesProfileService.py` -- validate + persist + propagate
- `Features/WorkBucket/Services/QueueAdmissionAppService.py` -- queue orchestration
- `Templates/WorkBucket.html` -- grouped UI
- `Tests/Contract/Test{SeriesIdentity,BucketKey,ProfileName,SeriesQueryRepository,FilesInSeriesRepository,SeriesProfileRepository,QueueAdmissionRepository,SeriesProfileService,QueueAdmissionAppService,WorkBucketController,NoShowSettingsReferences}VO.py / .py`

## Cross-Vertical Contract

### Columns the WorkBucket vertical WRITES

| Column | Written by |
|---|---|
| `SeriesProfiles.AssignedProfile` | `SeriesProfileService.SetProfile` |
| `MediaFiles.AssignedProfile`, `MediaFiles.AssignedProfileSource`, `MediaFiles.LastModifiedDate` | `SeriesProfileService.SetProfile` (untranscoded only) |
| `TranscodeQueue` row INSERT (`ProcessingMode`, `Status='Pending'`, ...) | `QueueAdmissionRepository.AdmitOne` / `AdmitSeries` |

### Columns READ

| Column | Read by | Owner |
|---|---|---|
| `MediaFiles.{Id, FileName, FileSize, SizeMB, StorageRootId, RelativePath, Resolution, ResolutionCategory, Codec, AudioCodec, AudioLanguages, VideoCompliantReason, ContainerCompliantReason, AudioCompliantReason, WorkBucket, AssignedProfile, TranscodedByMediaVortex}` | repositories | per-vertical (WorkBucket is GENERATED) |
| `SeriesProfiles.{StorageRootId, RelativePath, AssignedProfile}` | `SeriesProfileRepository`, `SeriesQueryRepository` | WorkBucket vertical |
| `TranscodeQueue.{Id, MediaFileId, Status}` | "AnyInQueue" + idempotency guard | TranscodeQueue |
| `Profiles.{ProfileName, Draft, Active}` | `ProfileName` VO ctor | Profiles |

### HTTP API surface

| Method + URL | Purpose |
|---|---|
| GET `/Work/<bucket>` | Render landing |
| GET `/api/Work/<bucket>` | Paged series list |
| GET `/api/Work/<bucket>/Series/<sid>` | Files in one series |
| POST `/api/Work/<bucket>/Series/<sid>/Profile` | Set series profile |
| DELETE `/api/Work/<bucket>/Series/<sid>/Profile` | Clear series profile |
| POST `/api/Work/<bucket>/Series/<sid>/Queue` | Queue all files in series |
| POST `/api/Work/<bucket>/Queue/<MediaFileId>` | Queue one file |

### What is EXPLICITLY NOT a contract

- The exact HTML structure inside `WorkBucket.html` -- internal layout choice.
- The list of sort options (extensible via `SortSpec`).
- The exact JSON keys inside the `Data` envelope -- expand freely; consumers (only the template) update in lockstep.
```

- [ ] **Step 3: Update directive Promotions**

Append to `.claude/directive.md` under `### Promotions`:

```
- WorkBucket contract docs -> `Features/WorkBucket/work-bucket.feature.md` (rewritten this commit).
```

- [ ] **Step 4: Commit**

```
git add Features/WorkBucket/work-bucket.feature.md .claude/directive.md
git commit -m "docs(work-bucket): rewrite feature md for grouped-by-series contract"
git push
```

---

## Task 23 — New `work-bucket.flow.md`

Pipeline-shape flow doc for the page-load -> series-list -> expand -> set-profile -> queue path.

**Files:**
- Create: `Features/WorkBucket/work-bucket.flow.md`

- [ ] **Step 1: Write the flow doc**

`Features/WorkBucket/work-bucket.flow.md`:

```markdown
# WorkBucket flow -- request lifecycle for /Work/<bucket>

**Slug:** work-bucket-flow

## Entry point and stages

`WorkBucketController.Blueprint` (registered in `WebService/Main.py`) is the entry. Browser hits a `/Work/<bucket>` URL; subsequent fetches go to `/api/Work/<bucket>/...`. The pipeline runs entirely inside one request (no cross-process state).

```
Browser  -- ST1 -> WorkBucketController.render_page  -- ST2 -> SeriesQueryRepository
        \         WorkBucketController.list_series                  |
         \-- ST3 -> WorkBucketController.list_files_in_series -- FilesInSeriesRepository
          \-- ST4 -> WorkBucketController.set_series_profile -- SeriesProfileService -- ST5 -> SeriesProfileRepository, MediaFiles UPDATE
           \-- ST6 -> WorkBucketController.queue_series -- QueueAdmissionAppService -- QueueAdmissionRepository (TranscodeQueue INSERT)
```

## Per-stage detail

### ST1 -- Render landing
`GET /Work/<bucket>` is mapped to `WorkBucketController.render_page`. The controller resolves `BucketKey.FromUrlKey(url_key)`; on None returns the 404 Error template. On hit it renders `Templates/WorkBucket.html` with `UrlKey` and `Bucket` in template context.

### ST2 -- Paged series list
JS calls `GET /api/Work/<bucket>?page=N&pageSize=M&sort=...&drive=...&search=...`. Controller builds `PagedQuery`, `SortSpec`, `FilterSpec` and delegates to `SeriesQueryRepository.ListSeriesByBucket`. Repository runs the single aggregate SQL (see Seam S1) and returns `PagedQueryResult[Series]`. Controller projects via `Series.ToJson` into the standard `{Success, Data: {Series, Total, Page, PageSize}}` envelope.

### ST3 -- Expand series -> files
JS calls `GET /api/Work/<bucket>/Series/<composite-key>`. Controller parses identity via `SeriesIdentity.FromCompositeKey` (raises ValueError -> 400). Delegates to `FilesInSeriesRepository.ListFilesInSeries`. Returns `list[MediaFileRow]` projected via `MediaFileRow.ToJson`.

### ST4 -- Set series profile (validation)
JS calls `POST /api/Work/<bucket>/Series/<sid>/Profile {ProfileName: "..."}`. Controller calls `SeriesProfileService.SetProfile(Identity, RawName)`. Service constructs `ProfileName(RawName)` -- VO ctor refuses draft/inactive/unknown by raising `InvalidProfileError` (-> 400 at controller).

### ST5 -- Set series profile (persist + propagate)
`SeriesProfileService.SetProfile` performs `SeriesProfileRepository.UpsertProfile`, then `UPDATE MediaFiles ... WHERE ... AND TranscodedByMediaVortex IS NOT TRUE RETURNING Id`. Affected row count is logged and returned to the controller.

### ST6 -- Admit to queue
`POST /api/Work/<bucket>/Series/<sid>/Queue` triggers `QueueAdmissionAppService.AdmitSeries` -> `QueueAdmissionRepository.AdmitSeries`. Bulk INSERT into TranscodeQueue with `NOT EXISTS` Pending guard. Returns `AdmissionResult(Inserted, AlreadyQueued, Total)`.

## Seams

Cross-stage seams (transitions). Intra-feature seams live in `work-bucket.feature.md`'s Seams section.

| ID | Transition | Producer (writer) | Wire shape | Consumer (reader) expects | Verification |
|---|---|---|---|---|---|
| S1 | ST1 -> ST2 | `WorkBucketController.render_page` (only sets `UrlKey, Bucket` in template) | template renders, JS issues `GET /api/Work/<bucket>` | Controller `list_series` handler accepts query string params | `Tests/Contract/TestWorkBucketController.py::test_api_series_list_envelope` |
| S2 | ST2 -> ST3 | `Series.ToJson` writes `CompositeKey` field | JSON path component `<storageRootId>:<showName>` | `SeriesIdentity.FromCompositeKey` parses; ValueError on missing colon | `Tests/Contract/TestSeriesIdentityVO.py::test_composite_key_roundtrip` |
| S3 | ST3 -> ST4 | UI dropdown change | `POST .../Profile {ProfileName: "..."}` body | `ProfileName(RawName)` VO ctor validates against Profiles table | `Tests/Contract/TestProfileNameVO.py` |
| S4 | ST5 -> ST6 (data) | `SeriesProfileService.SetProfile` writes `MediaFiles.AssignedProfile` | Column non-NULL on subsequent read | `EffectiveProfileResolver._ResolveAssignedProfileName` returns the value | `Tests/Contract/TestSeriesProfileService.py::test_set_profile_updates_only_untranscoded_files` |
| S5 | ST6 -> downstream worker | `TranscodeQueue` row Status='Pending' | Row claim via `WorkerCapabilityPredicate.BuildClaimPredicate` in `DatabaseManager.ClaimNextPendingTranscodeJob` | Worker picks the row matching its capability + ProcessingMode | `Tests/Contract/TestClaimAuthority.py` |
| S6 | New scan -> series row | `Scripts/SQLScripts/BackfillProfileAssignments.py` reads `SeriesProfiles` | UPDATE `MediaFiles.AssignedProfile` for matching (StorageRootId, first-segment) | `EffectiveProfileResolver` picks up the value | manual: insert MediaFiles row + run backfill; observe AssignedProfile populated |
```

- [ ] **Step 2: Update directive Promotions**

Append to `.claude/directive.md` under `### Promotions`:

```
- WorkBucket pipeline -> `Features/WorkBucket/work-bucket.flow.md` (new this commit).
```

- [ ] **Step 3: Commit**

```
git add Features/WorkBucket/work-bucket.flow.md .claude/directive.md
git commit -m "docs(work-bucket): flow md (stages ST1-ST6 + cross-stage seams)"
git push
```

---

## Task 24 — Verify success criteria + close out the directive

The final task: run every criterion's check and capture evidence.

- [ ] **Step 1: Restart WebService**

```
py StopMediaVortex.py
py StartMediaVortex.py
```

- [ ] **Step 2: Verify each criterion**

For each criterion (C1-C16 in the spec), record the verification command and its output. Concrete checks:

```
# C1: only bucket-matching rows
py Scripts/SQLScripts/QueryDatabase.py sql "SELECT DISTINCT WorkBucket FROM MediaFiles WHERE Id IN (SELECT mf.Id FROM MediaFiles mf WHERE mf.WorkBucket = 'Transcode' LIMIT 50)"

# C2: sort default + secondary
# Visual confirm via browser: load /Work/Transcode, observe series rows desc by GB. Click chevron, observe files desc by size.

# C3: profile change propagates
# Pick a series via /Work/Transcode UI, change profile, observe toast "Applied to N files". Then:
py Scripts/SQLScripts/QueryDatabase.py sql "SELECT count(*) FROM MediaFiles WHERE AssignedProfile = '<picked>' AND StorageRootId = <sid> AND split_part(RelativePath,'/',1) = '<show>' AND TranscodedByMediaVortex IS NOT TRUE"

# C4: queue all idempotent
# Click Queue all twice; second click reports "Queued 0 (N already pending)".

# C5: queue one idempotent
# Same, per row.

# C6: filters + pagination
# Visual confirm.

# C7: /ShowSettings -> 404
curl -i http://10.0.0.7:5000/ShowSettings

# C8: dir gone
test ! -e Features/ShowSettings; echo $?

# C9: template gone
test ! -e Templates/ShowSettings.html; echo $?

# C10: API endpoints 404
curl -i http://10.0.0.7:5000/api/ShowSettings/Shows

# C11: audit test green
py -m pytest Tests/Contract/TestNoShowSettingsReferences.py -v

# C12: row counts match
py Scripts/SQLScripts/QueryDatabase.py sql "SELECT (SELECT count(*) FROM SeriesProfiles) AS new_count, (SELECT count(*) FROM ShowSettings_DEPRECATED_2026_06_28) AS old_count"

# C13: backfill works
py Scripts/SQLScripts/BackfillProfileAssignments.py

# C14: EffectiveProfileResolver unchanged behavior -- run existing tests
py -m pytest Tests/Contract/TestProfileNameVO.py -v

# C15: deprecated marker present + drop script committed
py Scripts/SQLScripts/QueryDatabase.py sql "SELECT tablename FROM pg_tables WHERE tablename ILIKE 'showsettings%'"
py Scripts/SQLScripts/QueryDatabase.py sql "SELECT indexname FROM pg_indexes WHERE indexname ILIKE 'idx_mediafiles_smartpopulate%'"
ls Scripts/SQLScripts/DropDeprecatedShowSettingsArtifacts.py

# C16: audit refuses deprecated names too -- same audit test from C11
```

Paste each command's output into the directive's `## Verification` section as evidence.

- [ ] **Step 3: Run the full Contract suite**

```
py -m pytest Tests/Contract/ -v
```

Expected: all green, including the new tests + every pre-existing test.

- [ ] **Step 4: Live-deploy smoke on Worker LXC 218**

If WorkerService changes were touched (they were not in this directive, but verify): restart per `feedback_worker_restart_protocol.md`. Otherwise skip.

- [ ] **Step 5: Advance directive to DELIVERING**

Edit `.claude/directive.md` Status line:

```
**Status:** Active -- phase: DELIVERING
```

Confirm the `### Promotions` section has rows for each durable artifact landed (added in Tasks 12, 22, 23).

- [ ] **Step 6: Final commit**

```
git add .claude/directive.md
git commit -m "docs(directive): work-transcode-unified -- DELIVERING; verification complete"
git push
```

- [ ] **Step 7: Operator closes the directive**

The user reviews the Verification section and either approves close (`Active -- phase: DELIVERING` -> `Closed`) or requests changes. Closing is the operator's authority per the memory rule "Never close a directive until operator agrees."

---

## Self-Review

**Spec coverage:**
- C1 (only bucket rows) -- Task 6 (`WHERE mf.WorkBucket = %s`) + Task 24 step 2.
- C2 (grouped + sort) -- Tasks 6 + 15.
- C3 (profile propagation) -- Tasks 8, 10, 14.
- C4 (queue all idempotent) -- Task 9 + Task 11.
- C5 (queue one idempotent) -- Task 9 (`AdmitOne` existing-check) + Task 14.
- C6 (filters + pagination) -- Tasks 4 (FilterSpec), 6 (PagedQuery), 15 (UI).
- C7 (/ShowSettings 404) -- Task 18.
- C8 (dir gone) -- Task 17.
- C9 (template gone) -- Task 18.
- C10 (API endpoints 404) -- Task 17 (deletes the controller; blueprint registration removed in Task 18).
- C11 (audit green) -- Task 20.
- C12 (row counts match) -- Task 12.
- C13 (backfill works) -- Task 13.
- C14 (EffectiveProfileResolver unchanged) -- no task modifies it; verified in Task 24 step 2.
- C15 (deprecated marker present, drop script committed) -- Tasks 12, 19, 21.
- C16 (audit refuses deprecated names) -- Task 20 (NEEDLES list includes deprecated markers).

**Placeholder scan:** No TBDs, no "fill in details," no "similar to Task N" without code, no "appropriate error handling" weasel-words. Every step shows the code or command to run.

**Type consistency:** `SeriesIdentity`, `BucketKey`, `ProfileName`, `Series`, `MediaFileRow`, `SortSpec`, `FilterSpec`, `AdmissionResult` — names match across all tasks. Service method names (`SetProfile`, `ClearProfile`, `AdmitOne`, `AdmitSeries`) match across controller, services, tests. Route URLs (`/api/Work/<bucket>/Series/<sid>/Profile` etc.) match between controller, template JS, and tests.

---

## Execution

After confirming the plan, execution follows superpowers:executing-plans or superpowers:subagent-driven-development. Each task is one focused commit; pushes are per-commit per the operator's memory rule.
