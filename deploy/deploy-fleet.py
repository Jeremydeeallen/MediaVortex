#!/usr/bin/env python3
"""deploy-fleet: one-shot deploy of HEAD to every heartbeating worker.

Operator workflow:

    git push                           # land your commits first
    py deploy/deploy-fleet.py          # deploy fleet, watch for version flip

What it does:
  1. Reads git HEAD; warns if HEAD != origin/main (unpushed work).
  2. Queries Workers for hosts heartbeating in the last 5 minutes.
  3. Writes VERSION to HEAD (the local dev box's WorkerService reads this).
  4. Deploys each remote Linux host in parallel via deploy-linux-worker.py.
  5. If a local I9-shape worker is heartbeating, restarts the local
     WorkerService process (detach-spawn so the script doesn't block).
  6. Polls Workers.Version until every pre-deploy live worker reports HEAD
     and has a fresh heartbeat, or 5-minute timeout.
  7. Prints per-host OK/FAIL/timeout and exits 0 on full success.

Idempotent: re-runs do only what is needed (the per-host deploy scripts
already short-circuit when nothing changed).

Flags:
  --skip-local   Skip local WorkerService restart
  --target SHA   Deploy this SHA instead of HEAD
  --hosts X,Y    Limit remote deploys to these hosts (default: all live)
"""

import argparse
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# Local dev-box prefix. WorkerNames like "I9-2024" match this; remote
# Linux hosts use "<host>-worker-N" and don't.
LOCAL_DEV_PREFIX = "I9"

POLL_INTERVAL_SEC = 5
POLL_TIMEOUT_SEC = 300


def _Sh(Cmd, cwd=None):
    return subprocess.run(Cmd, capture_output=True, text=True, cwd=cwd)


def GitHead() -> str:
    return _Sh(["git", "rev-parse", "HEAD"], cwd=str(ROOT)).stdout.strip()


def GitOriginMain() -> str:
    R = _Sh(["git", "rev-parse", "origin/main"], cwd=str(ROOT))
    return R.stdout.strip() if R.returncode == 0 else ""


def HostFromWorkerName(Wn: str) -> str:
    """`larry-worker-1` -> `larry`. `I9-2024` -> `I9`."""
    M = re.match(r"^([A-Za-z0-9]+)-worker-\d+$", Wn)
    if M:
        return M.group(1)
    M = re.match(r"^([A-Za-z0-9]+)-\d+$", Wn)
    if M:
        return M.group(1)
    return Wn


def IsLocalDevWorker(Wn: str) -> bool:
    return Wn.startswith(LOCAL_DEV_PREFIX + "-")


def WriteVersion(Sha: str) -> None:
    (ROOT / "VERSION").write_text(Sha + "\n", encoding="utf-8")


def LiveWorkers(Db) -> list:
    return Db.ExecuteQuery(
        "SELECT WorkerName, COALESCE(Version, '') AS Version "
        "FROM Workers WHERE LastHeartbeat > NOW() - INTERVAL '5 minutes' "
        "ORDER BY WorkerName"
    )


def DeployRemoteHost(Host: str) -> tuple:
    """Run deploy/deploy-linux-worker.py for a host. Returns (host, rc, tail)."""
    R = subprocess.run(
        [sys.executable, "deploy/deploy-linux-worker.py", Host],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    Tail = "\n        ".join(R.stdout.strip().splitlines()[-3:])
    return (Host, R.returncode, Tail)


def RestartLocalWorker() -> str:
    """Stop running local WorkerService and detach-spawn a new one.
    Returns a status string."""
    try:
        import psutil
    except ImportError:
        return "psutil not installed; cannot manage local WorkerService"

    Killed = 0
    for P in psutil.process_iter(["pid", "cmdline"]):
        try:
            Cmd = " ".join(P.info.get("cmdline") or [])
            if "WorkerService" in Cmd and "Main.py" in Cmd:
                P.terminate()
                try:
                    P.wait(timeout=5)
                except psutil.TimeoutExpired:
                    P.kill()
                Killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    WorkerPy = ROOT / "WorkerService" / "venv" / "Scripts" / "python.exe"
    if not WorkerPy.exists():
        WorkerPy = ROOT / "WorkerService" / "venv" / "bin" / "python"
    Main = ROOT / "WorkerService" / "Main.py"
    LogFile = ROOT / "WorkerService" / "deploy-fleet.log"

    CreationFlags = 0
    if os.name == "nt":
        # Detach so the started process survives this script's exit.
        CreationFlags = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )

    Fh = open(LogFile, "ab", buffering=0)
    P = subprocess.Popen(
        [str(WorkerPy), str(Main)],
        cwd=str(ROOT),
        stdout=Fh, stderr=Fh,
        creationflags=CreationFlags,
        close_fds=True,
        start_new_session=(os.name != "nt"),
    )
    return f"killed {Killed} prior process(es); started PID {P.pid}"


def WaitForFleet(Db, Sha: str, ExpectedWorkers: list) -> tuple:
    """Poll until every expected worker is on `Sha` with a fresh heartbeat,
    or timeout. Returns (ok_rows, missing_workers)."""
    Deadline = time.time() + POLL_TIMEOUT_SEC
    Names = list(ExpectedWorkers)
    while time.time() < Deadline:
        Rows = Db.ExecuteQuery(
            "SELECT WorkerName, COALESCE(Version, '') AS Version, "
            "EXTRACT(EPOCH FROM (NOW() - LastHeartbeat))::int AS hb_age "
            "FROM Workers WHERE WorkerName = ANY(%s)",
            (Names,),
        )
        Ok = [
            R for R in Rows
            if (R["Version"] or "").startswith(Sha[:8]) and (R["hb_age"] or 999) < 60
        ]
        if len(Ok) == len(Names):
            return (Ok, [])
        OkNames = {R["WorkerName"] for R in Ok}
        Pending = [N for N in Names if N not in OkNames]
        print(
            f"   waiting: {len(Ok)}/{len(Names)} on {Sha[:8]}; "
            f"pending {Pending[:4]}{' ...' if len(Pending) > 4 else ''}"
        )
        time.sleep(POLL_INTERVAL_SEC)
    Rows = Db.ExecuteQuery(
        "SELECT WorkerName, COALESCE(Version, '') AS Version "
        "FROM Workers WHERE WorkerName = ANY(%s)",
        (Names,),
    )
    OkNames = {
        R["WorkerName"] for R in Rows
        if (R["Version"] or "").startswith(Sha[:8])
    }
    Missing = [N for N in Names if N not in OkNames]
    return ([R for R in Rows if R["WorkerName"] in OkNames], Missing)


def Main() -> int:
    P = argparse.ArgumentParser(description="One-shot fleet deploy.")
    P.add_argument("--skip-local", action="store_true",
                   help="skip local WorkerService restart")
    P.add_argument("--target", help="deploy this SHA instead of HEAD")
    P.add_argument("--hosts", help="comma-separated remote host names; default = all live")
    Args = P.parse_args()

    Sha = (Args.target or GitHead()).strip()
    if not Sha:
        print("ERROR: git HEAD unreadable")
        return 2

    Origin = GitOriginMain()
    if Origin and Origin != Sha and not Args.target:
        print(f"WARN: HEAD ({Sha[:8]}) != origin/main ({Origin[:8]}). "
              f"Workers will be on a SHA that is not pushed.")
        print("      Push first OR pass --target <pushed-sha>.")

    print(f"deploy-fleet: target = {Sha[:8]}")

    from Core.Database.DatabaseService import DatabaseService
    Db = DatabaseService()

    Pre = LiveWorkers(Db)
    if not Pre:
        print("ERROR: no workers heartbeating in the last 5 minutes")
        return 1

    ExpectedNames = [R["WorkerName"] for R in Pre]
    HostGroups = {}
    LocalNames = []
    for R in Pre:
        Wn = R["WorkerName"]
        if IsLocalDevWorker(Wn):
            LocalNames.append(Wn)
        else:
            HostGroups.setdefault(HostFromWorkerName(Wn), []).append(Wn)

    if Args.hosts:
        Want = {H.strip() for H in Args.hosts.split(",") if H.strip()}
        HostGroups = {H: V for H, V in HostGroups.items() if H in Want}

    print(f"live workers ({len(Pre)}):")
    if LocalNames:
        print(f"   local I9: {', '.join(LocalNames)}")
    for H, Wns in HostGroups.items():
        print(f"   {H}: {', '.join(Wns)}")

    WriteVersion(Sha)
    print(f"VERSION bumped -> {Sha[:8]}")

    Results = []
    if HostGroups:
        print(f"deploying remote hosts in parallel: {list(HostGroups.keys())}")
        with ThreadPoolExecutor(max_workers=max(1, len(HostGroups))) as Ex:
            Futs = [Ex.submit(DeployRemoteHost, H) for H in HostGroups.keys()]
            for F in as_completed(Futs):
                Results.append(F.result())

    AnyFail = False
    for H, Rc, Tail in Results:
        if Rc == 0:
            print(f"   [OK]   {H}")
        else:
            AnyFail = True
            print(f"   [FAIL] {H} rc={Rc}\n        {Tail}")

    if LocalNames and not Args.skip_local:
        Status = RestartLocalWorker()
        print(f"   [OK]   local I9: {Status}")

    print(f"polling for fleet to reach {Sha[:8]} (up to {POLL_TIMEOUT_SEC}s)...")
    Ok, Missing = WaitForFleet(Db, Sha, ExpectedNames)
    if not Missing:
        print(f"== FLEET ON {Sha[:8]} ({len(Ok)} workers) ==")
        for R in sorted(Ok, key=lambda r: r["WorkerName"]):
            print(f"   {R['WorkerName']:<20} {R['Version'][:8]}")
        return 0 if not AnyFail else 1

    print(f"== TIMEOUT: {len(Missing)} worker(s) not on {Sha[:8]} ==")
    for N in Missing:
        print(f"   {N}")
    return 1


if __name__ == "__main__":
    sys.exit(Main())
