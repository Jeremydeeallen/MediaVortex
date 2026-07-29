# see .claude/rules/worker-deploy-drain.md
import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


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


def DeployWorker(WorkerName: str) -> tuple:
    Script = str(ROOT / "deploy" / "deploy-worker.py")
    R = subprocess.run(
        [sys.executable, Script, WorkerName],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    Tail = "\n        ".join(R.stdout.strip().splitlines()[-3:])
    return (WorkerName, R.returncode, Tail)


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

    print(f"deploying {len(AllNames)} worker(s) per-service, in parallel:")
    for N in AllNames:
        print(f"   {N}")

    (ROOT / "VERSION").write_text(Sha + "\n", encoding="utf-8")
    print(f"VERSION bumped -> {Sha[:8]}")

    Results = []
    with ThreadPoolExecutor(max_workers=max(1, len(AllNames))) as Ex:
        Futs = [Ex.submit(DeployWorker, N) for N in AllNames]
        for F in as_completed(Futs):
            Results.append(F.result())

    AnyFail = False
    OkNames = []
    for Wn, Rc, Tail in sorted(Results, key=lambda x: x[0]):
        if Rc == 0:
            print(f"   [OK]   {Wn}")
            OkNames.append(Wn)
        else:
            AnyFail = True
            print(f"   [FAIL] {Wn} rc={Rc}\n        {Tail}")

    if AnyFail:
        _FinishHist('PARTIAL', AllNames, OkNames, 'per-worker failures during deploy')
        return 1

    print(f"== FLEET ON {Sha[:8]} ({len(OkNames)} workers) ==")
    _FinishHist('OK', AllNames, OkNames)
    return 0


if __name__ == "__main__":
    sys.exit(Main())
