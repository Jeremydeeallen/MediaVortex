#!/usr/bin/env python3
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from Core.Database.DatabaseService import DatabaseService


_FIXTURE_DIR = Path(__file__).resolve().parent


# directive: harness-drift-fixes
_BUCKET_WHERE = {
    'Transcode': (
        "WorkBucket = 'Transcode' "
        "AND VideoCompliant = FALSE AND AudioCompliant = TRUE AND ContainerCompliant = TRUE "
        "AND VideoBitrateKbps >= 2000"
    ),
    'Remux': (
        "WorkBucket = 'Remux' "
        "AND VideoCompliant = TRUE AND AudioCompliant = TRUE AND ContainerCompliant = FALSE"
    ),
    'AudioFixOnly': (
        "WorkBucket = 'AudioFixOnly' "
        "AND VideoCompliant = TRUE AND AudioCompliant = FALSE AND ContainerCompliant = TRUE"
    ),
    'Compliant': "WorkBucket IS NULL AND IsCompliant = TRUE AND AudioComplete = TRUE",
}


# directive: e2e-pipeline-test-framework
def _LoadPrefixMap() -> dict:
    Db = DatabaseService()
    return {int(R['Id']): R['CanonicalPrefix'] for R in Db.ExecuteQuery("SELECT Id, CanonicalPrefix FROM StorageRoots")}


# directive: e2e-pipeline-test-framework
def _Pick(Bucket: str, PrefixMap: dict) -> dict:
    print(f"[{Bucket}] querying...", flush=True)
    Db = DatabaseService()
    Sql = (
        "SELECT Id, FileName, StorageRootId, RelativePath, Codec, AudioCodec, ContainerFormat, "
        "Resolution, ResolutionCategory, VideoBitrateKbps, DurationMinutes, SizeMB, AssignedProfile, "
        "AudioCompliant, VideoCompliant, ContainerCompliant, AudioCompliantReason, "
        "VideoCompliantReason, ContainerCompliantReason, WorkBucket, IsCompliant, "
        "AudioComplete, HasExplicitEnglishAudio, SourceIntegratedLufs, SourceTruePeakDbtp "
        "FROM MediaFiles "
        f"WHERE ({_BUCKET_WHERE[Bucket]}) "
        "AND StorageRootId IN (1, 2) "
        "AND HasExplicitEnglishAudio = TRUE "
        "AND SizeMB BETWEEN 10 AND 500 "
        "AND (AudioCorruptSuspect IS NULL OR AudioCorruptSuspect = FALSE) "
        "AND VideoBitrateKbps IS NOT NULL AND VideoBitrateKbps > 0 "
        "ORDER BY SizeMB ASC LIMIT 10"
    )
    Rows = Db.ExecuteQuery(Sql)
    if not Rows:
        raise RuntimeError(f"No I9-reachable candidate found for bucket={Bucket}")
    for R in Rows:
        Sid = int(R['StorageRootId'])
        Rel = R['RelativePath'].replace('/', '\\') if R['RelativePath'] else ''
        Prefix = PrefixMap.get(Sid, '')
        LocalPath = Path(Prefix + Rel)
        if LocalPath.exists():
            print(f"[{Bucket}] picked Id={R['Id']} size={R['SizeMB']:.1f}MB path={LocalPath}", flush=True)
            R['_ResolvedLocalPath'] = str(LocalPath)
            R['_CanonicalPath'] = Prefix + Rel
            return R
        else:
            print(f"[{Bucket}]   miss: {LocalPath}", flush=True)
    raise RuntimeError(f"All {len(Rows)} top-10 candidates for {Bucket} are in DB but not on disk")


# directive: e2e-pipeline-test-framework
def _CopyFixture(Bucket: str, Row: dict) -> dict:
    OriginalName = Row['FileName'] or f"fixture_{Row['Id']}"
    BucketDir = _FIXTURE_DIR / Bucket
    BucketDir.mkdir(parents=True, exist_ok=True)
    DestPath = BucketDir / OriginalName
    SrcPath = Path(Row['_ResolvedLocalPath'])
    SrcSize = SrcPath.stat().st_size
    if DestPath.exists() and DestPath.stat().st_size == SrcSize:
        print(f"[{Bucket}] fixture already present (same size) at {DestPath}", flush=True)
    else:
        print(f"[{Bucket}] copying {SrcSize / (1024*1024):.1f} MB -> {DestPath}", flush=True)
        shutil.copy2(SrcPath, DestPath)
        print(f"[{Bucket}] copy done", flush=True)
    PropsContent = {
        'CapturedAt': datetime.now(timezone.utc).isoformat(),
        'SourceMediaFileId': int(Row['Id']),
        'SourceCanonicalPath': Row['_CanonicalPath'],
        'FixtureFileName': OriginalName,
        'FixtureLocalPath': str(DestPath),
        'ExpectedBucket': Bucket if Bucket != 'Compliant' else None,
        'ExpectedReasons': {
            'AudioCompliantReason': Row.get('AudioCompliantReason'),
            'VideoCompliantReason': Row.get('VideoCompliantReason'),
            'ContainerCompliantReason': Row.get('ContainerCompliantReason'),
        },
        'Properties': {K: (V.isoformat() if isinstance(V, datetime) else V) for K, V in Row.items() if not K.startswith('_')},
    }
    PropsPath = BucketDir / 'properties.json'
    PropsPath.write_text(json.dumps(PropsContent, indent=2, default=str), encoding='utf-8')
    print(f"[{Bucket}] wrote {PropsPath.name}", flush=True)
    return PropsContent


# directive: e2e-pipeline-test-framework
def Main():
    PrefixMap = _LoadPrefixMap()
    print(f"PrefixMap: {PrefixMap}", flush=True)
    Manifest = {'GeneratedAt': datetime.now(timezone.utc).isoformat(), 'Fixtures': {}}
    for Bucket in _BUCKET_WHERE:
        try:
            Row = _Pick(Bucket, PrefixMap)
            Props = _CopyFixture(Bucket, Row)
            Manifest['Fixtures'][Bucket] = {
                'FixtureLocalPath': Props['FixtureLocalPath'],
                'SourceMediaFileId': Props['SourceMediaFileId'],
                'ExpectedBucket': Props['ExpectedBucket'],
            }
        except Exception as Ex:
            print(f"[{Bucket}] FAILED: {type(Ex).__name__}: {Ex}", flush=True)
            Manifest['Fixtures'][Bucket] = {'Error': f"{type(Ex).__name__}: {Ex}"}
    ManifestPath = _FIXTURE_DIR / 'manifest.json'
    ManifestPath.write_text(json.dumps(Manifest, indent=2, default=str), encoding='utf-8')
    print(f"Manifest written: {ManifestPath}", flush=True)


if __name__ == '__main__':
    Main()
