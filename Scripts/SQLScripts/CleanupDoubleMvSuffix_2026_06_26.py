import argparse
import os
import re
import subprocess
import sys

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


# from: dot worker /mnt/* mount entries verified 2026-06-26
STORAGE_ROOT_LINUX_PATHS = {
    1: '/mnt/media_tv',
    2: '/mnt/movies',
    3: '/mnt/xxx',
}


SSH_HOST = 'root@dot'


FK_CHILD_TABLES = ('problemfiles', 'transcodeattempts', 'transcodefiles', 'transcodequeue')


# directive: worker-runtime-state
def _CollapseMvSuffix(BaseName: str) -> str:
    while BaseName and BaseName.lower().endswith('-mv'):
        BaseName = BaseName[:-3]
    return BaseName


# directive: worker-runtime-state
def _BuildCorrectName(FileName: str) -> str:
    Stem, Ext = os.path.splitext(FileName)
    Stem = _CollapseMvSuffix(Stem)
    return f"{Stem}-mv{Ext}"


# directive: worker-runtime-state
def _RunSshBatch(Cmds):
    if not Cmds:
        return (True, "")
    Script = "set -e\n" + "\n".join(Cmds) + "\n"
    R = subprocess.run(
        ['ssh', SSH_HOST, 'bash -s'],
        input=Script.encode('utf-8'),
        capture_output=True,
        timeout=180,
    )
    Out = (R.stdout or b'').decode('utf-8', errors='replace')
    Err = (R.stderr or b'').decode('utf-8', errors='replace')
    return (R.returncode == 0, (Out + Err).strip())


# directive: worker-runtime-state
def _ShQuote(S: str) -> str:
    return "'" + S.replace("'", "'\\''") + "'"


# directive: worker-runtime-state
def _FindSurvivorId(Db, Srid, NewRel):
    Rows = Db.ExecuteQuery(
        "SELECT Id FROM MediaFiles WHERE StorageRootId = %s AND LOWER(RelativePath) = LOWER(%s) LIMIT 1",
        (Srid, NewRel),
    )
    if not Rows:
        return None
    R = Rows[0]
    return int(R.get('Id') or R.get('id'))


# directive: worker-runtime-state
def _ResolvePair(Db, KeptRowId, RowToDeleteId):
    """Re-point FKs from RowToDeleteId -> KeptRowId, then DELETE RowToDeleteId. Caller updates KeptRow's name afterwards."""
    for ChildTable in FK_CHILD_TABLES:
        Db.ExecuteNonQuery(
            f"UPDATE {ChildTable} SET MediaFileId = %s WHERE MediaFileId = %s",
            (KeptRowId, RowToDeleteId),
        )
    Db.ExecuteNonQuery("DELETE FROM MediaFiles WHERE Id = %s", (RowToDeleteId,))


# directive: worker-runtime-state
def _ClassifyBatch(Plan):
    """Run SSH probe for each row; return dict Id -> outcome string."""
    Outcomes = {}
    Errors = []
    Batch = []
    InFlight = []
    for P in Plan:
        Source = _ShQuote(P['Source'])
        Target = _ShQuote(P['Target'])
        Dir = _ShQuote(P['Dir'])
        Cmd = (
            f"if [ -e {Source} ] && [ ! -e {Target} ]; then echo SOURCE_ONLY:{P['Id']}; "
            f"elif [ -e {Target} ] && [ ! -e {Source} ]; then echo TARGET_ONLY:{P['Id']}; "
            f"elif [ -e {Source} ] && [ -e {Target} ]; then echo BOTH:{P['Id']}; "
            f"else echo NEITHER:{P['Id']}; fi"
        )
        Batch.append(Cmd)
        InFlight.append(P)
        if len(Batch) >= 50:
            Ok, Out = _RunSshBatch(Batch)
            if not Ok:
                Errors.append(f"batch ssh failed: {Out[:200]}")
            else:
                for Line in Out.splitlines():
                    Line = Line.strip()
                    if ':' in Line:
                        Tag, IdStr = Line.split(':', 1)
                        try:
                            Outcomes[int(IdStr)] = Tag
                        except ValueError:
                            pass
            Batch = []
            InFlight = []
    if Batch:
        Ok, Out = _RunSshBatch(Batch)
        if not Ok:
            Errors.append(f"batch ssh failed: {Out[:200]}")
        else:
            for Line in Out.splitlines():
                Line = Line.strip()
                if ':' in Line:
                    Tag, IdStr = Line.split(':', 1)
                    try:
                        Outcomes[int(IdStr)] = Tag
                    except ValueError:
                        pass
    return Outcomes, Errors


# directive: worker-runtime-state
def Main():
    Parser = argparse.ArgumentParser(description='Clean up MediaFiles with accumulated -mv-mv suffix from BUG-0067 second-pass remux.')
    Parser.add_argument('--commit', action='store_true', help='Pass A: rename + DB update for rows where only the -mv-mv file exists on disk.')
    Parser.add_argument('--resolve-collisions', action='store_true',
                        help='Pass B (requires --commit): when both -mv and -mv-mv exist on disk, KEEP -mv-mv (newer encode), DELETE -mv. Reassigns FK history to survivor row.')
    Args = Parser.parse_args()

    Db = DatabaseService()
    Rows = Db.ExecuteQuery(
        "SELECT Id, StorageRootId, RelativePath, FileName FROM MediaFiles "
        "WHERE FileName ~ '-mv-mv' ORDER BY StorageRootId, RelativePath"
    )

    Plan = []
    Skipped = []
    for R in (Rows or []):
        Mid = int(R.get('Id') or R.get('id'))
        Srid = R.get('StorageRootId') if 'StorageRootId' in R else R.get('storagerootid')
        Rel = (R.get('RelativePath') or R.get('relativepath') or '').strip()
        Fn = (R.get('FileName') or R.get('filename') or '').strip()
        if Srid is None or Srid not in STORAGE_ROOT_LINUX_PATHS or not Rel or not Fn:
            Skipped.append({'Id': Mid, 'Reason': 'missing_path_components'})
            continue
        BaseLinuxRoot = STORAGE_ROOT_LINUX_PATHS[Srid]
        SourceFileLinux = f"{BaseLinuxRoot}/{Rel.replace(chr(92), '/')}"
        NewFn = _BuildCorrectName(Fn)
        if NewFn == Fn:
            Skipped.append({'Id': Mid, 'Reason': 'already_correct'})
            continue
        TargetFileLinux = f"{os.path.dirname(SourceFileLinux)}/{NewFn}"
        DirLinux = os.path.dirname(SourceFileLinux)
        NewRel = f"{os.path.dirname(Rel.replace(chr(92), '/'))}/{NewFn}" if os.path.dirname(Rel.replace(chr(92), '/')) else NewFn
        Plan.append({
            'Id': Mid, 'Srid': Srid,
            'OldFn': Fn, 'NewFn': NewFn,
            'OldRel': Rel, 'NewRel': NewRel,
            'Source': SourceFileLinux, 'Target': TargetFileLinux,
            'Dir': DirLinux,
        })

    print(f"Found {len(Plan)} candidates with -mv-mv suffix; {len(Skipped)} skipped.")
    if not Plan:
        return 0

    if not Args.commit:
        print(f"\nDry-run (no --commit). First 4 candidates:")
        for P in Plan[:4]:
            print(f"  Id={P['Id']:>6}  '{P['OldFn']}' -> '{P['NewFn']}'")
        print("\nRun with --commit for Pass A (rename rows where only -mv-mv exists on disk).")
        print("Add --resolve-collisions for Pass B (keep -mv-mv content, delete -mv where both exist).")
        return 0

    # Single SSH probe pass, classify all rows.
    print(f"\nProbing disk state for {len(Plan)} rows...")
    Outcomes, ProbeErrors = _ClassifyBatch(Plan)
    PlanById = {P['Id']: P for P in Plan}
    Tally = {'SOURCE_ONLY': 0, 'TARGET_ONLY': 0, 'BOTH': 0, 'NEITHER': 0, 'UNPROBED': 0}
    for P in Plan:
        Tag = Outcomes.get(P['Id'], 'UNPROBED')
        Tally[Tag] = Tally.get(Tag, 0) + 1
    print(f"Disk classification: SOURCE_ONLY={Tally['SOURCE_ONLY']}  TARGET_ONLY={Tally['TARGET_ONLY']}  BOTH={Tally['BOTH']}  NEITHER={Tally['NEITHER']}  UNPROBED={Tally.get('UNPROBED', 0)}")
    for E in ProbeErrors[:3]:
        print(f"  probe error: {E}")

    PassARenamed = 0
    PassAErrors = []

    # Pass A: SOURCE_ONLY -> mv on disk, update DB
    print(f"\nPass A: renaming {Tally['SOURCE_ONLY']} SOURCE_ONLY rows...")
    SrcOnly = [P for P in Plan if Outcomes.get(P['Id']) == 'SOURCE_ONLY']
    Batch = []
    InFlight = []
    for P in SrcOnly:
        Source = _ShQuote(P['Source'])
        Target = _ShQuote(P['Target'])
        Dir = _ShQuote(P['Dir'])
        Batch.append(f"mv {Source} {Target} && touch {Dir} && echo OK:{P['Id']}")
        InFlight.append(P)
        if len(Batch) >= 50:
            Ok, Out = _RunSshBatch(Batch)
            if not Ok:
                PassAErrors.append(f"Pass A batch ssh failed: {Out[:200]}")
            else:
                OkIds = {int(L.split(':', 1)[1]) for L in Out.splitlines() if L.startswith('OK:')}
                for Q in InFlight:
                    if Q['Id'] in OkIds:
                        try:
                            Db.ExecuteNonQuery(
                                "UPDATE MediaFiles SET FileName = %s, RelativePath = %s WHERE Id = %s",
                                (Q['NewFn'], Q['NewRel'], Q['Id']),
                            )
                            PassARenamed += 1
                        except psycopg2.errors.UniqueViolation:
                            PassAErrors.append(f"Pass A dup-key Id={Q['Id']}; left disk renamed; survivor row will need pass-B cleanup")
                        except Exception as Ex:
                            PassAErrors.append(f"Pass A DB update Id={Q['Id']}: {str(Ex)[:120]}")
            Batch = []
            InFlight = []
    if Batch:
        Ok, Out = _RunSshBatch(Batch)
        if not Ok:
            PassAErrors.append(f"Pass A batch ssh failed: {Out[:200]}")
        else:
            OkIds = {int(L.split(':', 1)[1]) for L in Out.splitlines() if L.startswith('OK:')}
            for Q in InFlight:
                if Q['Id'] in OkIds:
                    try:
                        Db.ExecuteNonQuery(
                            "UPDATE MediaFiles SET FileName = %s, RelativePath = %s WHERE Id = %s",
                            (Q['NewFn'], Q['NewRel'], Q['Id']),
                        )
                        PassARenamed += 1
                    except psycopg2.errors.UniqueViolation:
                        PassAErrors.append(f"Pass A dup-key Id={Q['Id']}; left disk renamed; survivor row will need pass-B cleanup")
                    except Exception as Ex:
                        PassAErrors.append(f"Pass A DB update Id={Q['Id']}: {str(Ex)[:120]}")

    print(f"Pass A renamed: {PassARenamed}  errors: {len(PassAErrors)}")

    # Pass B requires explicit opt-in.
    if not Args.resolve_collisions:
        if Tally['BOTH'] or Tally['TARGET_ONLY']:
            print(f"\nSkipping Pass B (no --resolve-collisions): {Tally['BOTH']} BOTH + {Tally['TARGET_ONLY']} TARGET_ONLY rows left untouched.")
        for E in PassAErrors[:5]:
            print(f"  {E}")
        return 0 if not PassAErrors else 1

    # Pass B: BOTH (collision) -> delete -mv, rename -mv-mv -> -mv; TARGET_ONLY -> just DB cleanup.
    print(f"\nPass B (path 1: keep -mv-mv content): processing {Tally['BOTH']} BOTH + {Tally['TARGET_ONLY']} TARGET_ONLY rows...")
    PassBResolved = 0
    PassBErrors = []
    PassBSkipped = []

    Targets = [P for P in Plan if Outcomes.get(P['Id']) in ('BOTH', 'TARGET_ONLY')]
    # Process one at a time -- per-row FK + DELETE + (optional) SSH + UPDATE. Idempotent: re-running picks up partial cases via re-classification.
    DiskBatch = []
    DiskBatchPlans = []
    for P in Targets:
        Outcome = Outcomes[P['Id']]
        KeptRowId = P['Id']  # the -mv-mv row, which we will rename to -mv
        SurvivorId = _FindSurvivorId(Db, P['Srid'], P['NewRel'])  # the -mv row that needs to be deleted
        if SurvivorId is None:
            PassBSkipped.append(f"Id={KeptRowId} ({Outcome}): no DB row found for -mv name; skipping")
            continue
        if SurvivorId == KeptRowId:
            PassBSkipped.append(f"Id={KeptRowId} ({Outcome}): survivor lookup returned same row; skipping")
            continue
        # 1. Re-point FKs, 2. delete old -mv row.
        try:
            _ResolvePair(Db, KeptRowId, SurvivorId)
        except Exception as Ex:
            PassBErrors.append(f"FK reassign Id={KeptRowId} loser={SurvivorId}: {str(Ex)[:160]}")
            continue
        # 3. Update kept row's FileName + RelativePath.
        try:
            Db.ExecuteNonQuery(
                "UPDATE MediaFiles SET FileName = %s, RelativePath = %s WHERE Id = %s",
                (P['NewFn'], P['NewRel'], KeptRowId),
            )
        except Exception as Ex:
            PassBErrors.append(f"Rename kept row Id={KeptRowId}: {str(Ex)[:160]}")
            continue
        # 4. Disk action (only for BOTH): rm target then mv source -> target.
        if Outcome == 'BOTH':
            Source = _ShQuote(P['Source'])
            Target = _ShQuote(P['Target'])
            Dir = _ShQuote(P['Dir'])
            DiskBatch.append(f"rm {Target} && mv {Source} {Target} && touch {Dir} && echo OK:{KeptRowId}")
            DiskBatchPlans.append(P)
            if len(DiskBatch) >= 50:
                Ok, Out = _RunSshBatch(DiskBatch)
                if not Ok:
                    PassBErrors.append(f"Pass B batch ssh failed: {Out[:200]}")
                else:
                    OkIds = {int(L.split(':', 1)[1]) for L in Out.splitlines() if L.startswith('OK:')}
                    PassBResolved += len(OkIds)
                    for Q in DiskBatchPlans:
                        if Q['Id'] not in OkIds:
                            PassBErrors.append(f"Pass B disk rm+mv missing OK for Id={Q['Id']}")
                DiskBatch = []
                DiskBatchPlans = []
        else:
            PassBResolved += 1  # TARGET_ONLY: DB-only; no disk op
    if DiskBatch:
        Ok, Out = _RunSshBatch(DiskBatch)
        if not Ok:
            PassBErrors.append(f"Pass B batch ssh failed: {Out[:200]}")
        else:
            OkIds = {int(L.split(':', 1)[1]) for L in Out.splitlines() if L.startswith('OK:')}
            PassBResolved += len(OkIds)
            for Q in DiskBatchPlans:
                if Q['Id'] not in OkIds:
                    PassBErrors.append(f"Pass B disk rm+mv missing OK for Id={Q['Id']}")

    print(f"\nFinal: pass_a_renamed={PassARenamed}  pass_b_resolved={PassBResolved}  pass_b_skipped={len(PassBSkipped)}")
    print(f"        pass_a_errors={len(PassAErrors)}  pass_b_errors={len(PassBErrors)}  skipped_inputs={len(Skipped)}  neither_on_disk={Tally['NEITHER']}")
    for E in (PassAErrors + PassBErrors)[:6]:
        print(f"  ERROR: {E}")
    for E in PassBSkipped[:6]:
        print(f"  SKIP : {E}")

    return 0 if (not PassAErrors and not PassBErrors) else 1


if __name__ == '__main__':
    raise SystemExit(Main())
