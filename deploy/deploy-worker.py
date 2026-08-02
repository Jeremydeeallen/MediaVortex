# see .claude/rules/worker-deploy-invariants.md
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

MediaVortexRoot = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MediaVortexRoot))

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


def RestartWindowsLocal(WorkerName: str, Sha: str) -> tuple:
    # see worker-deploy-invariants.md I1+I2+I3+I4 -- kill is safe; ActiveJobs sweep runs at boot; VERSION stamp before spawn keeps I3; Popen return value + one-shot poll enforces I4.
    T0 = time.time()
    print(f"       restart backend: windows-local ({WorkerName})", flush=True)
    import os as _os
    try:
        import psutil
    except ImportError:
        return (False, time.time() - T0)

    (MediaVortexRoot / "VERSION").write_text(Sha + "\n", encoding="utf-8")

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
    print(f"       restart backend: baremetal (host={Host}, skip_sync={SkipSync})", flush=True)
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
    # see worker-deploy-invariants.md I1 -- hard-kill is safe; boot cleanup restores state. Avoids graceful-stop wait (systemd TimeoutStopSec) blocking deploy.
    R = subprocess.run(
        ["ssh", *SshOpts, Target,
         f"systemctl kill -s KILL {Unit}; systemctl start {Unit}"],
        timeout=30,
    )
    Elapsed = time.time() - T0
    print(f"       systemctl kill+start {Unit} rc={R.returncode} ({Elapsed:.1f}s)", flush=True)
    return (R.returncode == 0, Elapsed)


def DeployOne(WorkerName: str, Sha: str, SkipSync: bool = False) -> int:
    from Core.Database.DatabaseService import DatabaseService
    Db = DatabaseService()

    Rows = Db.ExecuteQuery(
        "SELECT WorkerName, Platform FROM Workers WHERE WorkerName=%s",
        (WorkerName,),
    )
    if not Rows:
        print(f"[FAIL] no Workers row for {WorkerName!r}")
        return 2
    Platform = (Rows[0].get("Platform") or "").lower()
    Host = _HostFromWorkerName(WorkerName)

    print(f"=== deploy-worker {WorkerName} (Platform={Platform}, Host={Host}, Sha={Sha[:8]}) ===", flush=True)
    TStart = time.time()

    if _WindowsLocal(Host):
        Ok, TDeploy = RestartWindowsLocal(WorkerName, Sha)
    else:
        Ok, TDeploy = RestartBaremetal(WorkerName, Host, SkipSync=SkipSync)

    TTotal = time.time() - TStart
    if not Ok:
        print(f"=== FAIL {WorkerName} in {TTotal:.1f}s ===", flush=True)
        return 4
    print(f"=== OK {WorkerName} restarted in {TTotal:.1f}s ===", flush=True)
    return 0


def Main(Argv=None) -> int:
    P = argparse.ArgumentParser(description="Per-worker restart: sync (baremetal only) + restart process.")
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
