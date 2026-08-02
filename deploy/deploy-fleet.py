import datetime as _dt
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

Root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Root))

try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

from deploy.common import (
    MediaVortexRoot, HostFromWorkerName, IsWindowsLocal,
    GitHead, GitOriginMain, Sh,
)


def _EnabledWorkers(Db) -> list:
    return Db.ExecuteQuery(
        "SELECT WorkerName, COALESCE(Version, '') AS Version, Status "
        "FROM Workers WHERE Enabled = TRUE "
        "ORDER BY WorkerName"
    )


def _StreamChild(Prefix: str, Cmd: list) -> tuple:
    StartTs = _dt.datetime.now()
    print(f"[{Prefix}] START {StartTs.strftime('%H:%M:%S')}", flush=True)
    Proc = subprocess.Popen(
        Cmd, cwd=str(MediaVortexRoot), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    LastLines = []
    for Line in Proc.stdout:
        Line = Line.rstrip()
        print(f"[{Prefix}] {Line}", flush=True)
        LastLines.append(Line)
        if len(LastLines) > 3:
            LastLines.pop(0)
    Proc.wait()
    EndTs = _dt.datetime.now()
    Elapsed = (EndTs - StartTs).total_seconds()
    print(f"[{Prefix}] END {EndTs.strftime('%H:%M:%S')} (elapsed {Elapsed:.1f}s, rc={Proc.returncode})", flush=True)
    return (Proc.returncode, "\n        ".join(LastLines), StartTs, EndTs, Elapsed)


def _SyncHost(HostName: str) -> tuple:
    Cmd = [sys.executable, "-u", str(MediaVortexRoot / "deploy" / "deploy-baremetal-worker.py"), HostName]
    Rc, Tail, StartTs, EndTs, Elapsed = _StreamChild(f"sync:{HostName}", Cmd)
    return (HostName, Rc, Tail, StartTs, EndTs, Elapsed)


def _DeployWorker(WorkerName: str) -> tuple:
    Cmd = [sys.executable, "-u", str(MediaVortexRoot / "deploy" / "deploy-worker.py"), WorkerName]
    Rc, Tail, StartTs, EndTs, Elapsed = _StreamChild(WorkerName, Cmd)
    return (WorkerName, Rc, Tail, StartTs, EndTs, Elapsed)


def Main() -> int:
    Sha = GitHead()
    if not Sha:
        print("ERROR: git HEAD unreadable")
        return 2

    Dirty = Sh(["git", "status", "--porcelain"], cwd=str(MediaVortexRoot)).stdout.strip()
    if Dirty:
        print("ERROR: working tree is dirty. Commit first. Refused:")
        for L in Dirty.splitlines()[:20]:
            print(f"  {L}")
        return 2
    Origin = GitOriginMain()
    if not Origin:
        print("ERROR: origin/main unreadable. `git fetch origin` first.")
        return 2
    if Origin != Sha:
        print(f"ERROR: HEAD ({Sha[:8]}) != origin/main ({Origin[:8]}). Push (or pull) first.")
        return 2

    print(f"deploy-fleet: target = {Sha[:8]}")

    from Core.Database.DatabaseService import DatabaseService
    Db = DatabaseService()

    _PriorShaRow = Db.ExecuteQuery("SELECT NewSha FROM DeployHistory WHERE Outcome='OK' ORDER BY Id DESC LIMIT 1")
    _PriorSha = _PriorShaRow[0].get('newsha') if _PriorShaRow else None
    Db.ExecuteNonQuery(
        "INSERT INTO DeployHistory (StartedAt, PriorSha, NewSha, Outcome) "
        "VALUES (NOW(), %s, %s, 'RUNNING')",
        (_PriorSha, Sha),
    )
    HistId = Db.GetLastInsertId()

    def _FinishHist(Outcome, Attempted, Succeeded, ErrorMessage=None):
        if not HistId:
            return
        Db.ExecuteNonQuery(
            "UPDATE DeployHistory SET CompletedAt=NOW(), "
            "ElapsedSeconds=EXTRACT(EPOCH FROM (NOW() - StartedAt))::int, "
            "HostsAttempted=%s, HostsSucceeded=%s, Outcome=%s, ErrorMessage=%s "
            "WHERE Id=%s",
            (",".join(Attempted), ",".join(Succeeded), Outcome, ErrorMessage, HistId),
        )

    Pre = _EnabledWorkers(Db)
    if not Pre:
        print("ERROR: no Enabled workers in Workers table")
        _FinishHist('FAILED', [], [], 'no enabled workers')
        return 1

    AllNames = [R["WorkerName"] for R in Pre]

    # see .claude/rules/worker-deploy.md
    RemoteHosts = sorted({HostFromWorkerName(W) for W in AllNames if not IsWindowsLocal(HostFromWorkerName(W))})

    print(f"deploying {len(AllNames)} worker(s):")
    for H in RemoteHosts:
        HostWorkers = sorted([W for W in AllNames if HostFromWorkerName(W) == H])
        print(f"   host={H}: {', '.join(HostWorkers)}")
    LocalWorkers = sorted([W for W in AllNames if IsWindowsLocal(HostFromWorkerName(W))])
    if LocalWorkers:
        print(f"   windows-local: {', '.join(LocalWorkers)}")

    T0 = _dt.datetime.now()
    Results = []
    SyncResults = {}

    MaxThreads = len(RemoteHosts) + len(AllNames)
    with ThreadPoolExecutor(max_workers=max(1, MaxThreads)) as Ex:
        SyncFuts = {H: Ex.submit(_SyncHost, H) for H in RemoteHosts}

        def _RestartAfterSync(WorkerName):
            Host = HostFromWorkerName(WorkerName)
            SyncFut = SyncFuts.get(Host)
            if SyncFut is not None:
                _, Rc, Tail, _S, _E, _El = SyncFut.result()
                if Rc != 0:
                    return (WorkerName, 90, f"sync:{Host} failed rc={Rc}\n        {Tail}",
                            _dt.datetime.now(), _dt.datetime.now(), 0.0)
            return _DeployWorker(WorkerName)

        WorkerFuts = [Ex.submit(_RestartAfterSync, W) for W in AllNames]

        for F in as_completed(WorkerFuts):
            Results.append(F.result())

        for H, F in SyncFuts.items():
            SyncResults[H] = F.result()

    TotalElapsed = (_dt.datetime.now() - T0).total_seconds()

    AnyFail = False
    OkNames = []
    print()
    print("=" * 76)
    print(f"{'Worker':<32} {'Started':<10} {'Finished':<10} {'Elapsed':>10} {'Result':<8}")
    print("-" * 76)
    for Wn, Rc, Tail, StartTs, EndTs, Elapsed in sorted(Results, key=lambda x: x[0]):
        Result = "OK" if Rc == 0 else f"FAIL rc={Rc}"
        print(f"{Wn:<32} {StartTs.strftime('%H:%M:%S'):<10} {EndTs.strftime('%H:%M:%S'):<10} {Elapsed:>9.1f}s {Result:<8}")
        if Rc == 0:
            OkNames.append(Wn)
        else:
            AnyFail = True
    print("=" * 76)
    for Wn, Rc, Tail, _S, _E, _El in sorted(Results, key=lambda x: x[0]):
        if Rc != 0:
            print(f"   [FAIL tail] {Wn}\n        {Tail}")
    print()
    print(f"Fleet wall time: {TotalElapsed:.1f}s")
    for H, (_, Rc, _, _, _, Elapsed) in sorted(SyncResults.items()):
        print(f"  sync:{H}: {Elapsed:.1f}s rc={Rc}")

    if AnyFail:
        _FinishHist('PARTIAL', AllNames, OkNames, 'per-worker failures during deploy')
        return 1

    print()
    print(f"== FLEET ON {Sha[:8]} ({len(OkNames)} workers) ==")
    _FinishHist('OK', AllNames, OkNames)
    return 0


if __name__ == "__main__":
    sys.exit(Main())
