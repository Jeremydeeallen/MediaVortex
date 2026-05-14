"""Assess the state of .orig files left by the remux re-queue bug.

Reads all MediaFiles that had a 'Pre-existing .orig' failure from I9-2024,
checks disk state, and categorizes them.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from Core.Database.DatabaseService import DatabaseService

DB = DatabaseService()

# All distinct MediaFileIds that hit the .orig error
Rows = DB.ExecuteQuery(
    """SELECT DISTINCT ON (ta.mediafileid) ta.mediafileid, mf.filepath, mf.filesize as dbsize, mf.containerformat, mf.recommendedmode
       FROM transcodeattempts ta
       JOIN mediafiles mf ON ta.mediafileid = mf.id
       WHERE ta.success = false
       AND ta.errormessage LIKE %s
       ORDER BY ta.mediafileid, ta.id DESC""",
    ('%Pre-existing .orig%',)
)

print(f"Total affected MediaFiles: {len(Rows)}")
print()

BothExist = []
Mp4Only = []
OrigOnly = []
Neither = []

for R in Rows:
    FP = R['filepath']
    Orig = FP + '.orig'
    FPEx = os.path.exists(FP)
    OrigEx = os.path.exists(Orig)
    FPSz = os.path.getsize(FP) if FPEx else 0
    OrigSz = os.path.getsize(Orig) if OrigEx else 0
    Entry = {
        'MediaFileId': R['mediafileid'],
        'FilePath': FP,
        'ContainerFormat': R['containerformat'],
        'RecommendedMode': R['recommendedmode'],
        'DbSize': R['dbsize'] or 0,
        'Mp4Exists': FPEx,
        'OrigExists': OrigEx,
        'Mp4Size': FPSz,
        'OrigSize': OrigSz,
    }
    if FPEx and OrigEx:
        BothExist.append(Entry)
    elif FPEx and not OrigEx:
        Mp4Only.append(Entry)
    elif not FPEx and OrigEx:
        OrigOnly.append(Entry)
    else:
        Neither.append(Entry)

print(f"BOTH exist (mp4 + .orig): {len(BothExist)}")
print(f"MP4 only (no .orig):      {len(Mp4Only)}")
print(f"ORIG only (no mp4!):      {len(OrigOnly)}")
print(f"NEITHER exists:           {len(Neither)}")
print()

if BothExist:
    print("--- BOTH EXIST (first 10) ---")
    for E in BothExist[:10]:
        Ratio = E['OrigSize'] / E['Mp4Size'] if E['Mp4Size'] > 0 else 0
        print(f"  MF {E['MediaFileId']}: mp4={E['Mp4Size']:>13,}  orig={E['OrigSize']:>13,}  ratio={Ratio:.2f}x  mode={E['RecommendedMode']}")
    print()

if OrigOnly:
    print("--- ORIG ONLY (DB path MISSING on disk!) ---")
    for E in OrigOnly:
        print(f"  MF {E['MediaFileId']}: orig={E['OrigSize']:>13,}  dbpath={E['FilePath']}")
    print()

if Neither:
    print("--- NEITHER EXISTS ---")
    for E in Neither:
        print(f"  MF {E['MediaFileId']}: dbpath={E['FilePath']}")
    print()

# Also count: how many TranscodeAttempts wasted on .orig errors total (all workers)
WastedRows = DB.ExecuteQuery(
    "SELECT COUNT(*) as cnt FROM transcodeattempts WHERE success = false AND errormessage LIKE %s",
    ('%Pre-existing .orig%',)
)
print(f"Total wasted TranscodeAttempts (.orig errors): {WastedRows[0]['cnt']}")

# How many remux queue items point to already-MP4 files
BogusQueue = DB.ExecuteQuery(
    """SELECT COUNT(*) as cnt FROM TranscodeQueue tq
       JOIN MediaFiles mf ON tq.MediaFileId = mf.Id
       WHERE tq.ProcessingMode = 'Remux'
       AND tq.Status IN ('Pending', 'Running')
       AND mf.ContainerFormat LIKE %s""",
    ('%mp4%',)
)
print(f"Bogus remux queue items (already MP4): {BogusQueue[0]['cnt']}")

# How many MP4 files still have stale RecommendedMode = 'Remux'
StaleRows = DB.ExecuteQuery(
    "SELECT COUNT(*) as cnt FROM MediaFiles WHERE ContainerFormat LIKE %s AND RecommendedMode = 'Remux'",
    ('%mp4%',)
)
print(f"Stale RecommendedMode='Remux' on MP4 files: {StaleRows[0]['cnt']}")
