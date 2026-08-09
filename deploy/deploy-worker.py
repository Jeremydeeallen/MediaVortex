#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os as _os
import subprocess
import sys
import time
from pathlib import Path

Root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Root))

from deploy.common import (
    MediaVortexRoot, SshOpts,
    HostFromWorkerName, SystemdUnitFromWorkerName,
    IsWindowsLocal, GitHead, ResolveInventory,
)


DrainPollSec = 5


def PauseWorker(Db, WorkerName: str) -> None:
    Db.ExecuteNonQuery(
        "UPDATE Workers SET Status='Paused' WHERE WorkerName=%s AND Status<>'Paused'",
        (WorkerName,),
    )
    print(f"[1/4] pause: {WorkerName}", flush=True)


def DrainWorker(Db, WorkerName: str) -> float:
    T0 = time.time()
    print(f"[2/4] drain: {WorkerName} (poll every {DrainPollSec}s)", flush=True)
    LastReport = 0
    while True:
        ActiveJobs = Db.ExecuteQuery(
            "SELECT COUNT(*) AS N FROM ActiveJobs WHERE WorkerName=%s",
            (WorkerName,),
        )[0]["N"]
        ScanBusy = Db.ExecuteQuery(
            "SELECT COUNT(*) AS N FROM ScanJobs "
            "WHERE WorkerName=%s AND Status IN ('Pending','Running','Stopping')",
            (WorkerName,),
        )[0]["N"]
        if ActiveJobs == 0 and ScanBusy == 0:
            Elapsed = time.time() - T0
            print(f"       drained: ActiveJobs=0, ScanJobs=0 ({Elapsed:.1f}s)", flush=True)
            return Elapsed
        Waited = int(time.time() - T0)
        if Waited - LastReport >= 30 or Waited < 10:
            print(f"       waiting: ActiveJobs={ActiveJobs} ScanBusy={ScanBusy} ({Waited}s)", flush=True)
            LastReport = Waited
        time.sleep(DrainPollSec)


def _KillLocalProcs(Fragment: str, psutil_mod) -> int:
    Killed = 0
    for P in psutil_mod.process_iter(["pid", "cmdline"]):
        try:
            Cmd = " ".join(P.info.get("cmdline") or [])
            if Fragment in Cmd and "Main.py" in Cmd:
                print(f"       kill pid={P.pid} ({Fragment})", flush=True)
                P.terminate()
                Killed += 1
        except Exception:
            pass
    return Killed


def _SpawnDetached(ServiceDir: str, LogPath: Path, WorkerName: str) -> subprocess.Popen:
    ScriptsDir = MediaVortexRoot / ServiceDir / "venv" / "Scripts"
    Py = ScriptsDir / "pythonw.exe"
    if not Py.exists():
        Py = ScriptsDir / "python.exe"
    CreationFlags = 0
    if _os.name == "nt":
        CreationFlags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    Env = _os.environ.copy()
    Env["MEDIAVORTEX_WORKER_NAME"] = WorkerName
    Fh = open(LogPath, "ab", buffering=0)
    return subprocess.Popen(
        [str(Py), str(MediaVortexRoot / ServiceDir / "Main.py")],
        cwd=str(MediaVortexRoot),
        stdout=Fh, stderr=Fh,
        creationflags=CreationFlags,
        close_fds=True,
        start_new_session=(_os.name != "nt"),
        env=Env,
    )


def RestartWindowsLocal(WorkerName: str) -> bool:
    print(f"[3/4] restart backend: windows-local ({WorkerName})", flush=True)
    try:
        import psutil
    except ImportError:
        print(f"[FAIL] psutil not installed", flush=True)
        return False
    _KillLocalProcs("WorkerService", psutil)
    _KillLocalProcs("WebService", psutil)
    WebLog = MediaVortexRoot / "WebService" / "deploy-worker.log"
    WorkerLog = MediaVortexRoot / "WorkerService" / "deploy-worker.log"
    WebProc = _SpawnDetached("WebService", WebLog, WorkerName)
    WorkerProc = _SpawnDetached("WorkerService", WorkerLog, WorkerName)
    time.sleep(1)
    if WebProc.poll() is not None or WorkerProc.poll() is not None:
        print(f"[FAIL] one or both services died immediately", flush=True)
        return False
    print(f"       started web pid={WebProc.pid} worker pid={WorkerProc.pid}", flush=True)
    return True


def RestartBaremetal(WorkerName: str, Host: str) -> bool:
    print(f"[3/4] restart backend: baremetal (host={Host})", flush=True)
    _, Ip, User = ResolveInventory(Host)
    Unit = SystemdUnitFromWorkerName(WorkerName)
    PidBefore = _GetMainPid(Ip, User, Unit)
    R = subprocess.run(
        ["ssh", *SshOpts, f"{User}@{Ip}", f"systemctl restart {Unit}"],
        timeout=120,
    )
    if R.returncode != 0:
        print(f"       systemctl restart {Unit} rc={R.returncode} FAILED", flush=True)
        return False
    PidAfter = _GetMainPid(Ip, User, Unit)
    if PidAfter == 0:
        print(f"       systemctl restart {Unit} rc=0 BUT MainPID=0 (unit not running)", flush=True)
        return False
    if PidBefore != 0 and PidAfter == PidBefore:
        print(f"       systemctl restart {Unit} rc=0 BUT MainPID unchanged ({PidBefore}) -- process did not rotate", flush=True)
        return False
    print(f"       systemctl restart {Unit} rc=0 MainPID {PidBefore} -> {PidAfter}", flush=True)
    return True


def _GetMainPid(Ip: str, User: str, Unit: str) -> int:
    R = subprocess.run(
        ["ssh", *SshOpts, f"{User}@{Ip}", f"systemctl show -p MainPID --value {Unit}"],
        capture_output=True, text=True, timeout=10,
    )
    if R.returncode != 0:
        return 0
    try:
        return int(R.stdout.strip() or "0")
    except ValueError:
        return 0


def OnlineWorker(Db, WorkerName: str, WasOnline: bool) -> None:
    if WasOnline:
        Db.ExecuteNonQuery("UPDATE Workers SET Status='Online' WHERE WorkerName=%s", (WorkerName,))
        print(f"[4/4] online: {WorkerName}", flush=True)
    else:
        print(f"[4/4] leaving Paused (was not Online pre-deploy)", flush=True)


def DeployOne(WorkerName: str) -> int:
    from Core.Database.DatabaseService import DatabaseService
    Db = DatabaseService()
    Rows = Db.ExecuteQuery(
        "SELECT Platform, Status FROM Workers WHERE WorkerName=%s",
        (WorkerName,),
    )
    if not Rows:
        print(f"[FAIL] no Workers row for {WorkerName!r}")
        return 2
    Platform = (Rows[0].get("Platform") or "").lower()
    WasOnline = (Rows[0].get("Status") or "") == "Online"
    Host = HostFromWorkerName(WorkerName)

    print(f"=== deploy-worker {WorkerName} (Platform={Platform}, Host={Host}, WasOnline={WasOnline}) ===", flush=True)
    TStart = time.time()

    PauseWorker(Db, WorkerName)
    DrainWorker(Db, WorkerName)

    Ok = RestartWindowsLocal(WorkerName) if IsWindowsLocal(Host) else RestartBaremetal(WorkerName, Host)
    if not Ok:
        print(f"[FAIL] restart failed (rc!=0 OR MainPID did not rotate); leaving Status=Paused", flush=True)
        return 4
    OnlineWorker(Db, WorkerName, WasOnline)

    print(f"=== OK {WorkerName} in {time.time()-TStart:.1f}s ===", flush=True)
    return 0


def Main(Argv=None) -> int:
    P = argparse.ArgumentParser(description="Per-worker deploy: pause -> drain -> restart -> online. See .claude/rules/worker-deploy.md.")
    P.add_argument("WorkerName", help="e.g. larry-worker-1, wakko-worker-2, I9-2024")
    Args = P.parse_args(Argv)
    if not GitHead():
        print("[FAIL] git HEAD unreadable")
        return 2
    return DeployOne(Args.WorkerName)


if __name__ == "__main__":
    sys.exit(Main())
