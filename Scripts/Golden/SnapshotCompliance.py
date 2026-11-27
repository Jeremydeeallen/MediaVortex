# directive: target-policy-1a-tables | # see policy.C9 -- TV + Movies compliance verdicts frozen per file; a migration must not move a verdict without the file itself changing
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SNAPSHOT_PATH = os.path.join(REPO_ROOT, 'Tests', 'Contract', 'Golden', 'compliance-counts.json')
ROOTS = [1, 2]
DIMENSIONS = ('VideoCompliant', 'AudioCompliant', 'ContainerCompliant')


# directive: target-policy-1a-tables | # see policy.C9
def _Epoch(Value):
    if Value is None:
        return None
    if Value.tzinfo is None:
        Value = Value.replace(tzinfo=timezone.utc)
    return int(Value.timestamp())


# directive: target-policy-1a-tables | # see policy.C9
def _Tri(Value):
    if Value is None:
        return None
    return bool(Value)


# directive: target-policy-1a-tables | # see policy.C9
def QueryLive(Db=None):
    Db = Db or DatabaseService()
    Rows = Db.ExecuteQuery(
        "SELECT Id, StorageRootId, FileModificationTime, LastModifiedDate, VideoCompliant, AudioCompliant, ContainerCompliant "
        "FROM MediaFiles WHERE StorageRootId = ANY(%s) ORDER BY Id",
        (ROOTS,),
    )
    return [
        [int(R['Id']), int(R['StorageRootId']), _Epoch(R['FileModificationTime']), _Epoch(R['LastModifiedDate']),
         _Tri(R['VideoCompliant']), _Tri(R['AudioCompliant']), _Tri(R['ContainerCompliant'])]
        for R in Rows
    ]


# directive: target-policy-1a-tables | # see policy.C9
def Counts(Files):
    Out = {}
    for _Id, Root, _Mtime, _Lmd, V, A, C in Files:
        Bucket = Out.setdefault(str(Root), {D: {'true': 0, 'false': 0, 'null': 0} for D in DIMENSIONS})
        for Dim, Value in zip(DIMENSIONS, (V, A, C)):
            Bucket[Dim]['null' if Value is None else ('true' if Value else 'false')] += 1
    return Out


# directive: target-policy-1a-tables | # see policy.C9
def Compare(Snapshot, Live):
    ById = {Row[0]: Row for Row in Live}
    Mismatches, Moved, Deleted = [], [], []
    for Row in Snapshot['Files']:
        Id, _Root, Mtime, _Lmd, V, A, C = Row
        LiveRow = ById.pop(Id, None)
        if LiveRow is None:
            Deleted.append(Id)
            continue
        if LiveRow[2] != Mtime:
            Moved.append(Id)
            continue
        if (LiveRow[4], LiveRow[5], LiveRow[6]) != (V, A, C):
            Mismatches.append({'Id': Id, 'Snapshot': [V, A, C], 'Live': LiveRow[4:7], 'LiveLastModified': LiveRow[3]})
    return {'Mismatches': Mismatches, 'Moved': Moved, 'Deleted': Deleted, 'New': sorted(ById)}


# directive: target-policy-1a-tables | # see policy.C9
def Write(Path=SNAPSHOT_PATH):
    Files = QueryLive()
    Doc = {
        'TakenAt': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'Roots': ROOTS,
        'FileColumns': ['Id', 'StorageRootId', 'FileModificationTimeEpoch', 'LastModifiedDateEpoch', 'VideoCompliant', 'AudioCompliant', 'ContainerCompliant'],
        'Counts': Counts(Files),
        'Files': Files,
    }
    with open(Path, 'w', encoding='utf-8') as F:
        F.write('{\n')
        for Key in ('TakenAt', 'Roots', 'FileColumns', 'Counts'):
            F.write(f'  {json.dumps(Key)}: {json.dumps(Doc[Key], sort_keys=True)},\n')
        F.write('  "Files": [\n')
        F.write(',\n'.join('    ' + json.dumps(Row) for Row in Files))
        F.write('\n  ]\n}\n')
    return Doc


# directive: target-policy-1a-tables | # see policy.C9
def Load(Path=SNAPSHOT_PATH):
    with open(Path, 'r', encoding='utf-8') as F:
        return json.load(F)


# directive: target-policy-1a-tables | # see policy.C9
def Main():
    Parser = argparse.ArgumentParser(description='Write or check the TV + Movies per-file compliance snapshot.')
    Parser.add_argument('--write', action='store_true', help='Overwrite Tests/Contract/Golden/compliance-counts.json from the live DB')
    Args = Parser.parse_args()
    if Args.write:
        Doc = Write()
        print(f"Wrote {SNAPSHOT_PATH}: {len(Doc['Files'])} files; counts={json.dumps(Doc['Counts'], sort_keys=True)}")
        return 0
    Result = Compare(Load(), QueryLive())
    print(json.dumps({K: (V if K == 'Mismatches' else len(V)) for K, V in Result.items()}, indent=2, default=str))
    return 1 if Result['Mismatches'] else 0


if __name__ == '__main__':
    raise SystemExit(Main())
