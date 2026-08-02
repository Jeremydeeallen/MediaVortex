# see .claude/rules/worker-deploy.md
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

MediaVortexRoot = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MediaVortexRoot))

DrainPollSec = 5

SshOpts = ["-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
           "-o", "StrictHostKeyChecking=accept-new"]


def _Sh(Cmd, cwd=None, timeout=60):
    return subprocess.run(Cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout)


def _GitHead() -> str:
    return _Sh(["git", "rev-parse", "HEAD"], cwd=str(MediaVortexRoot)).stdout.strip()


def _HostFromWorkerName(Wn: str) -> str:
    M = re.match(r"^(.+)-worker-\d+$", Wn)
    if M:
        return M.group(1)
    M = re.match(r"^([A-Za-z0-9]+)-\d+$", Wn)
    if M:
        return M.group(1)
    return Wn


def _BaremetalUnitFromWorkerName(Wn: str) -> str:
    M = re.match(r"^.+-worker-(\d+)$", Wn)
    if not M:
        raise ValueError(f"cannot derive systemd unit from {Wn!r}")
    return f"mediavortex-worker@{M.group(1)}.service"


def _WindowsLocal(Host: str) -> bool:
    return Host.upper().startswith("I9")


def _LoadBaremetalDeployModule():
    from importlib.util import spec_from_file_location, module_from_spec
    BaremetalDeploy = MediaVortexRoot / "deploy" / "deploy-baremetal-worker.py"
    Spec = spec_from_file_location("_bd", str(BaremetalDeploy))
    Mod = module_from_spec(Spec)
    Spec.loader.exec_module(Mod)
    return Mod


def _ResolveInventory(Host: str):
    Mod = _LoadBaremetalDeployModule()
    Friendly, Ip, User, _Count = Mod._ResolveTarget(Host, Mod.DefaultInventoryToml, None)
    return Friendly, Ip, User


def PauseWorker(Db, WorkerName: str) -> float:
    T0 = time.time()
    Db.ExecuteNonQuery(
        "UPDATE Workers SET Status='Paused' WHERE WorkerName=%s AND Status<>'Paused'",
        (WorkerName,),
    )
    Elapsed = time.time() - T0
    print(f"[1/5] pause: {WorkerName} ({Elapsed:.1f}s)", flush=True)
    return Elapsed


def DrainWorker(Db, WorkerName: str) -> float:
    # see worker-deploy.md step 2 -- poll until in-flight work reaches zero. No hard timeout; drain is the contract, not a suggestion.
    T0 = time.time()
    print(f"[2/5] drain: {WorkerName} (poll every {DrainPollSec}s)", flush=True)
    LastReportedAt = 0
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
        if Waited - LastReportedAt >= 30 or Waited < 10:
            print(f"       waiting: ActiveJobs={ActiveJobs} ScanBusy={ScanBusy} ({Waited}s elapsed)", flush=True)
            LastReportedAt = Waited
        time.sleep(DrainPollSec)


def _KillMediaVortexProcs(NameFragment: str, psutil_mod) -> int:
    Killed = 0
    for P in psutil_mod.process_iter(["pid", "cmdline"]):
        try:
            Cmd = " ".join(P.info.get("cmdline") or [])
            if NameFragment in Cmd and "Main.py" in Cmd:
                print(f"       kill pid={P.pid} ({NameFragment})", flush=True)
                P.terminate()
                Killed += 1
        except Exception:
            pass
    return Killed


def _SpawnDetached(ServiceDir: str, MainPy, LogFile, _os, WorkerName: str):
    ScriptsDir = MediaVortexRoot / ServiceDir / "venv" / "Scripts"
    Py = ScriptsDir / "pythonw.exe"
    if not Py.exists():
        Py = ScriptsDir / "python.exe"
    CreationFlags = 0
    if _os.name == "nt":
        CreationFlags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    Env = _os.environ.copy()
    Env["MEDIAVORTEX_WORKER_NAME"] = WorkerName
    Fh = open(LogFile, "ab", buffering=0)
    Proc = subprocess.Popen(
        [str(Py), str(MainPy)],
        cwd=str(MediaVortexRoot),
        stdout=Fh, stderr=Fh,
        creationflags=CreationFlags,
        close_fds=True,
        start_new_session=(_os.name != "nt"),
        env=Env,
    )
    return Proc, Py


def RestartWindowsLocal(WorkerName: str) -> tuple:
    # see worker-deploy.md steps 3-4 -- drain confirmed by caller so hard kill is safe. Worker reads sha from .git/HEAD (worker-lifecycle-invariants.md I3) so no VERSION stamp needed. Popen return + one-shot poll enforces fail-loud (I4).
    T0 = time.time()
    print(f"[3/5] restart backend: windows-local ({WorkerName})", flush=True)
    import os as _os
    try:
        import psutil
    except ImportError:
        return (False, time.time() - T0)

    KilledW = _KillMediaVortexProcs("WorkerService", psutil)
    KilledS = _KillMediaVortexProcs("WebService", psutil)
    print(f"       terminated {KilledW} WorkerService + {KilledS} WebService", flush=True)

    WebProc, _ = _SpawnDetached("WebService", MediaVortexRoot / "WebService" / "Main.py",
                                MediaVortexRoot / "WebService" / "deploy-worker.log", _os, WorkerName)
    WorkerProc, _ = _SpawnDetached("WorkerService", MediaVortexRoot / "WorkerService" / "Main.py",
                                   MediaVortexRoot / "WorkerService" / "deploy-worker.log", _os, WorkerName)
    time.sleep(1)
    if WebProc.poll() is not None:
        return (False, time.time() - T0)
    if WorkerProc.poll() is not None:
        return (False, time.time() - T0)
    Elapsed = time.time() - T0
    print(f"       started web pid={WebProc.pid} worker pid={WorkerProc.pid} ({Elapsed:.1f}s)", flush=True)
    return (True, Elapsed)


def RestartBaremetal(WorkerName: str, Host: str, SkipSync: bool = False) -> tuple:
    T0 = time.time()
    print(f"[3/5] restart backend: baremetal (host={Host}, skip_sync={SkipSync})", flush=True)
    _, Ip, User = _ResolveInventory(Host)
    Target = f"{User}@{Ip}"

    if not SkipSync:
        R = subprocess.run(
            [sys.executable, str(MediaVortexRoot / "deploy" / "deploy-baremetal-worker.py"),
             Host, "--sync-only"],
            cwd=str(MediaVortexRoot),
        )
        if R.returncode != 0:
            return (False, time.time() - T0)

    Unit = _BaremetalUnitFromWorkerName(WorkerName)
    # Drain confirmed by caller; systemctl restart's graceful-stop wait is redundant. kill -s TERM + start = fast + clean.
    R = subprocess.run(
        ["ssh", *SshOpts, Target,
         f"systemctl kill -s TERM {Unit}; systemctl start {Unit}"],
        timeout=30,
    )
    Elapsed = time.time() - T0
    print(f"       systemctl kill+start {Unit} rc={R.returncode} ({Elapsed:.1f}s)", flush=True)
    return (R.returncode == 0, Elapsed)


def OnlineWorker(Db, WorkerName: str, WasOnline: bool) -> float:
    T0 = time.time()
    if WasOnline:
        Db.ExecuteNonQuery(
            "UPDATE Workers SET Status='Online' WHERE WorkerName=%s",
            (WorkerName,),
        )
        Elapsed = time.time() - T0
        print(f"[5/5] online: {WorkerName} ({Elapsed:.1f}s)", flush=True)
    else:
        Elapsed = time.time() - T0
        print(f"[5/5] leaving Paused (was not Online pre-deploy)", flush=True)
    return Elapsed


def DeployOne(WorkerName: str, Sha: str, SkipSync: bool = False) -> int:
    from Core.Database.DatabaseService import DatabaseService
    Db = DatabaseService()

    Rows = Db.ExecuteQuery(
        "SELECT WorkerName, Platform, Status FROM Workers WHERE WorkerName=%s",
        (WorkerName,),
    )
    if not Rows:
        print(f"[FAIL] no Workers row for {WorkerName!r}")
        return 2
    Platform = (Rows[0].get("Platform") or "").lower()
    WasOnline = (Rows[0].get("Status") or "") == "Online"
    Host = _HostFromWorkerName(WorkerName)

    print(f"=== deploy-worker {WorkerName} (Platform={Platform}, Host={Host}, Sha={Sha[:8]}, WasOnline={WasOnline}) ===", flush=True)
    TStart = time.time()

    TPause = PauseWorker(Db, WorkerName)
    TDrain = DrainWorker(Db, WorkerName)

    if _WindowsLocal(Host):
        Ok, TRestart = RestartWindowsLocal(WorkerName)
    else:
        Ok, TRestart = RestartBaremetal(WorkerName, Host, SkipSync=SkipSync)

    if not Ok:
        print(f"[FAIL] restart backend failed; leaving Status=Paused", flush=True)
        return 4

    print(f"[4/5] start returned rc=0 (fail-loud invariant satisfied)", flush=True)

    TOnline = OnlineWorker(Db, WorkerName, WasOnline)
    TTotal = time.time() - TStart
    print(
        f"=== OK {WorkerName} in {TTotal:.1f}s "
        f"(pause={TPause:.1f}s, drain={TDrain:.1f}s, restart={TRestart:.1f}s, online={TOnline:.1f}s) ===",
        flush=True,
    )
    return 0


def Main(Argv=None) -> int:
    P = argparse.ArgumentParser(description="Per-worker deploy: pause -> drain -> restart -> online. See .claude/rules/worker-deploy.md.")
    P.add_argument("WorkerName", help="e.g. larry-worker-1, wakko-worker-2, I9-2024")
    P.add_argument("--skip-sync", action="store_true",
                   help="Skip source sync (fleet uses per-host sync-once + this flag on per-worker restart)")
    Args = P.parse_args(Argv)
    Sha = _GitHead()
    if not Sha:
        print("[FAIL] git HEAD unreadable")
        return 2
    return DeployOne(Args.WorkerName, Sha, SkipSync=Args.skip_sync)


if __name__ == "__main__":
    sys.exit(Main())
