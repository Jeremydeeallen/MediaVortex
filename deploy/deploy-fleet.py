# see .claude/rules/worker-deploy-drain.md
import argparse
import datetime as _dt
import re
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# directive: orphan-generators-stop -- force line-buffered stdout so background/piped invocations see live progress.
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass


def _HostFromWorkerName(Wn: str) -> str:
    M = re.match(r"^(.+)-worker-\d+$", Wn)
    if M:
        return M.group(1)
    M = re.match(r"^([A-Za-z0-9]+)-\d+$", Wn)
    if M:
        return M.group(1)
    return Wn


def _Sh(Cmd, cwd=None):
    return subprocess.run(Cmd, capture_output=True, text=True, cwd=cwd)


def GitHead() -> str:
    return _Sh(["git", "rev-parse", "HEAD"], cwd=str(ROOT)).stdout.strip()


def GitOriginMain() -> str:
    R = _Sh(["git", "rev-parse", "origin/main"], cwd=str(ROOT))
    return R.stdout.strip() if R.returncode == 0 else ""


def LiveWorkers(Db) -> list:
    return Db.ExecuteQuery(
        "SELECT WorkerName, COALESCE(Version, '') AS Version, Status "
        "FROM Workers WHERE LastHeartbeat > NOW() - INTERVAL '5 minutes' "
        "ORDER BY WorkerName"
    )


def _StreamChild(Prefix: str, Cmd: list) -> tuple:
    # directive: orphan-generators-stop -- stream child stdout line-by-line, prefixed for legibility across parallel subprocesses.
    StartTs = _dt.datetime.now()
    print(f"[{Prefix}] START {StartTs.strftime('%H:%M:%S')}", flush=True)
    Proc = subprocess.Popen(
        Cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
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


def SyncHost(HostName: str) -> tuple:
    # directive: orphan-generators-stop -- one source sync per host, not per worker. rsync/pip target-disk contention was the actual bottleneck.
    Cmd = [sys.executable, "-u", str(ROOT / "deploy" / "deploy-baremetal-worker.py"), HostName, "--sync-only"]
    Rc, Tail, StartTs, EndTs, Elapsed = _StreamChild(f"sync:{HostName}", Cmd)
    return (HostName, Rc, Tail, StartTs, EndTs, Elapsed)


def DeployWorker(WorkerName: str, SkipSync: bool = False) -> tuple:
    Cmd = [sys.executable, "-u", str(ROOT / "deploy" / "deploy-worker.py"), WorkerName]
    if SkipSync:
        Cmd.append("--skip-sync")
    Rc, Tail, StartTs, EndTs, Elapsed = _StreamChild(WorkerName, Cmd)
    return (WorkerName, Rc, Tail, StartTs, EndTs, Elapsed)


def Main() -> int:
    P = argparse.ArgumentParser(description="Per-service fleet deploy: pause -> drain -> deploy -> Online for each live worker.")
    P.add_argument("--workers", help="comma-separated WorkerName list; default = all live")
    Args = P.parse_args()

    Sha = GitHead()
    if not Sha:
        print("ERROR: git HEAD unreadable")
        return 2

    Dirty = _Sh(["git", "status", "--porcelain"], cwd=str(ROOT)).stdout.strip()
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

    Pre = LiveWorkers(Db)
    if not Pre:
        print("ERROR: no workers heartbeating in the last 5 minutes")
        _FinishHist('FAILED', [], [], 'no live workers')
        return 1

    AllNames = [R["WorkerName"] for R in Pre]
    if Args.workers:
        Want = {W.strip() for W in Args.workers.split(",") if W.strip()}
        AllNames = [N for N in AllNames if N in Want]
        if not AllNames:
            print(f"ERROR: --workers {Args.workers!r} matched no live workers")
            _FinishHist('FAILED', [], [], 'no matching live workers')
            return 1

    # directive: orphan-generators-stop -- group by host so each host syncs source once (rsync/pip contention on target disk was the real bottleneck when running per-worker sync). Then per-worker restart-only in parallel across ALL workers.
    ByHost = defaultdict(list)
    WindowsWorkers = []
    for N in AllNames:
        Host = _HostFromWorkerName(N)
        if Host.upper().startswith("I9"):
            WindowsWorkers.append(N)
        else:
            ByHost[Host].append(N)

    print(f"deploying {len(AllNames)} worker(s):")
    for H in sorted(ByHost):
        print(f"   host={H}: {', '.join(sorted(ByHost[H]))}")
    if WindowsWorkers:
        print(f"   windows-local: {', '.join(sorted(WindowsWorkers))}")

    (ROOT / "VERSION").write_text(Sha + "\n", encoding="utf-8")
    print(f"VERSION bumped -> {Sha[:8]}")

    Results = []

    if ByHost:
        print(f"[phase 1/2] per-host source sync + dep install ({len(ByHost)} host(s) in parallel)")
        SyncResults = {}
        with ThreadPoolExecutor(max_workers=max(1, len(ByHost))) as Ex:
            Futs = {Ex.submit(SyncHost, H): H for H in ByHost.keys()}
            for F in as_completed(Futs):
                H, Rc, Tail, StartTs, EndTs, Elapsed = F.result()
                SyncResults[H] = (Rc, Tail, StartTs, EndTs, Elapsed)

        FailedHosts = [H for H, (Rc, *_ ) in SyncResults.items() if Rc != 0]
        if FailedHosts:
            print(f"[FAIL] per-host sync failed on: {FailedHosts}")
            for H in FailedHosts:
                Rc, Tail, *_ = SyncResults[H]
                print(f"   sync:{H} rc={Rc}\n        {Tail}")

    RestartTargets = [N for N in AllNames if _HostFromWorkerName(N) not in (FailedHosts if ByHost else [])]

    if RestartTargets:
        print(f"[phase 2/2] per-worker pause+drain+restart+verify ({len(RestartTargets)} in parallel)")
        with ThreadPoolExecutor(max_workers=max(1, len(RestartTargets))) as Ex:
            Futs = []
            for N in RestartTargets:
                SkipSync = _HostFromWorkerName(N) in ByHost
                Futs.append(Ex.submit(DeployWorker, N, SkipSync))
            for F in as_completed(Futs):
                Results.append(F.result())

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

    if AnyFail:
        _FinishHist('PARTIAL', AllNames, OkNames, 'per-worker failures during deploy')
        return 1

    print(f"== FLEET ON {Sha[:8]} ({len(OkNames)} workers) ==")
    _FinishHist('OK', AllNames, OkNames)
    return 0


if __name__ == "__main__":
    sys.exit(Main())
