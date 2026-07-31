# see .claude/rules/worker-deploy-drain.md
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

MediaVortexRoot = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MediaVortexRoot))

DrainTimeoutSec = 1800
DrainPollSec = 5
VerifyTimeoutSec = 180
VerifyPollSec = 5

SshOpts = ["-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
           "-o", "StrictHostKeyChecking=accept-new"]


def _Sh(Cmd, cwd=None, timeout=60):
    return subprocess.run(Cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout)


def _GitHead() -> str:
    return _Sh(["git", "rev-parse", "HEAD"], cwd=str(MediaVortexRoot)).stdout.strip()


def _HostFromWorkerName(Wn: str) -> str:
    M = re.match(r"^([A-Za-z0-9]+)-worker-\d+$", Wn)
    if M:
        return M.group(1)
    M = re.match(r"^([A-Za-z0-9]+)-\d+$", Wn)
    if M:
        return M.group(1)
    return Wn


def _BaremetalUnitFromWorkerName(Wn: str) -> str:
    M = re.match(r"^[A-Za-z0-9]+-worker-(\d+)$", Wn)
    if not M:
        raise ValueError(f"cannot derive systemd unit from {Wn!r}")
    return f"mediavortex-worker@{M.group(1)}.service"


def PauseWorker(Db, WorkerName: str) -> float:
    T0 = time.time()
    Db.ExecuteNonQuery(
        "UPDATE Workers SET Status='Paused' WHERE WorkerName=%s AND Status<>'Paused'",
        (WorkerName,),
    )
    Elapsed = time.time() - T0
    print(f"[1/6] pause: {WorkerName} ({Elapsed:.1f}s)", flush=True)
    return Elapsed


def DrainWorker(Db, WorkerName: str) -> tuple:
    T0 = time.time()
    print(f"[2/6] drain: {WorkerName} (timeout {DrainTimeoutSec}s)", flush=True)
    Deadline = T0 + DrainTimeoutSec
    while time.time() < Deadline:
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
            return (True, Elapsed)
        Waited = int(time.time() - T0)
        print(f"       waiting: ActiveJobs={ActiveJobs} ScanBusy={ScanBusy} ({Waited}s elapsed)", flush=True)
        time.sleep(DrainPollSec)
    Elapsed = time.time() - T0
    print(f"[FAIL] drain budget exceeded ({Elapsed:.1f}s)", flush=True)
    return (False, Elapsed)


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
    Friendly, Ip, User = Mod._ResolveTarget(Host, Mod.DefaultInventoryToml, None)
    return Friendly, Ip, User


def DeployBaremetal(WorkerName: str, Host: str, Sha: str) -> tuple:
    T0 = time.time()
    print(f"[3/6] deploy backend: baremetal (host={Host})", flush=True)
    _, Ip, User = _ResolveInventory(Host)
    Target = f"{User}@{Ip}"

    print("       source rsync via deploy-baremetal-worker.py --sync-only", flush=True)
    R = subprocess.run(
        [sys.executable, str(MediaVortexRoot / "deploy" / "deploy-baremetal-worker.py"),
         Host, "--sync-only"],
        cwd=str(MediaVortexRoot),
    )
    if R.returncode != 0:
        Elapsed = time.time() - T0
        print(f"[FAIL] sync-only prep for {Host} ({Elapsed:.1f}s)", flush=True)
        return (False, Elapsed)

    Unit = _BaremetalUnitFromWorkerName(WorkerName)
    print(f"[4/6] restart systemd unit: {Unit}", flush=True)
    T1 = time.time()
    R = subprocess.run(["ssh", *SshOpts, Target, f"systemctl restart {Unit}"], timeout=60)
    Elapsed = time.time() - T0
    RestartElapsed = time.time() - T1
    print(f"       restart done ({RestartElapsed:.1f}s); backend total ({Elapsed:.1f}s)", flush=True)
    return (R.returncode == 0, Elapsed)


def DeployWindowsLocal(WorkerName: str, Sha: str) -> tuple:
    T0 = time.time()
    print(f"[3/6] deploy backend: windows-local ({WorkerName})", flush=True)
    import os as _os
    try:
        import psutil
    except ImportError:
        Elapsed = time.time() - T0
        print(f"[FAIL] psutil not installed ({Elapsed:.1f}s)", flush=True)
        return (False, Elapsed)
    Killed = 0
    for P in psutil.process_iter(["pid", "cmdline"]):
        try:
            Cmd = " ".join(P.info.get("cmdline") or [])
            if "WorkerService" in Cmd and "Main.py" in Cmd:
                P.terminate()
                try:
                    P.wait(timeout=10)
                except psutil.TimeoutExpired:
                    P.kill()
                Killed += 1
        except Exception:
            pass
    print(f"       terminated {Killed} WorkerService process(es)", flush=True)

    WorkerPy = MediaVortexRoot / "WorkerService" / "venv" / "Scripts" / "python.exe"
    Main = MediaVortexRoot / "WorkerService" / "Main.py"
    LogFile = MediaVortexRoot / "WorkerService" / "deploy-worker.log"
    CreationFlags = 0
    if _os.name == "nt":
        CreationFlags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    Fh = open(LogFile, "ab", buffering=0)
    print("[4/6] start WorkerService (detached)", flush=True)
    subprocess.Popen(
        [str(WorkerPy), str(Main)],
        cwd=str(MediaVortexRoot),
        stdout=Fh, stderr=Fh,
        creationflags=CreationFlags,
        close_fds=True,
        start_new_session=(_os.name != "nt"),
    )
    Elapsed = time.time() - T0
    print(f"       backend total ({Elapsed:.1f}s)", flush=True)
    return (True, Elapsed)


def VerifyWorker(Db, WorkerName: str, Sha: str) -> tuple:
    T0 = time.time()
    print(f"[5/6] verify: Version~={Sha[:8]}, heartbeat<60s", flush=True)
    Deadline = T0 + VerifyTimeoutSec
    while time.time() < Deadline:
        Rows = Db.ExecuteQuery(
            "SELECT COALESCE(Version,'') AS Version, "
            "EXTRACT(EPOCH FROM (NOW() - LastHeartbeat))::int AS hb_age "
            "FROM Workers WHERE WorkerName=%s",
            (WorkerName,),
        )
        if not Rows:
            Elapsed = time.time() - T0
            print(f"[FAIL] worker {WorkerName} not found ({Elapsed:.1f}s)", flush=True)
            return (False, Elapsed)
        R = Rows[0]
        if (R["Version"] or "").startswith(Sha[:8]) and (R["hb_age"] or 999) < 60:
            Elapsed = time.time() - T0
            print(f"       ok: Version={R['Version'][:8]} hb_age={R['hb_age']}s ({Elapsed:.1f}s)", flush=True)
            return (True, Elapsed)
        Waited = int(time.time() - T0)
        print(f"       waiting: Version={(R['Version'] or 'NONE')[:8]} hb_age={R['hb_age']}s ({Waited}s elapsed)", flush=True)
        time.sleep(VerifyPollSec)
    Elapsed = time.time() - T0
    print(f"[FAIL] verify timeout ({Elapsed:.1f}s)", flush=True)
    return (False, Elapsed)


def OnlineWorker(Db, WorkerName: str) -> float:
    T0 = time.time()
    Db.ExecuteNonQuery(
        "UPDATE Workers SET Status='Online' WHERE WorkerName=%s",
        (WorkerName,),
    )
    Elapsed = time.time() - T0
    print(f"[6/6] online: {WorkerName} ({Elapsed:.1f}s)", flush=True)
    return Elapsed


def DeployOne(WorkerName: str, Sha: str) -> int:
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

    TPause = PauseWorker(Db, WorkerName)
    Drained, TDrain = DrainWorker(Db, WorkerName)
    if not Drained:
        return 3

    if _WindowsLocal(Host):
        Ok, TDeploy = DeployWindowsLocal(WorkerName, Sha)
    else:
        Ok, TDeploy = DeployBaremetal(WorkerName, Host, Sha)
    if not Ok:
        print("[FAIL] backend deploy failed; leaving Status=Paused", flush=True)
        return 4

    Ok, TVerify = VerifyWorker(Db, WorkerName, Sha)
    if not Ok:
        print("[FAIL] verify failed; leaving Status=Paused", flush=True)
        return 5

    TOnline = OnlineWorker(Db, WorkerName)
    TTotal = time.time() - TStart
    print(
        f"=== OK {WorkerName} back Online in {TTotal:.1f}s "
        f"(pause={TPause:.1f}s, drain={TDrain:.1f}s, deploy={TDeploy:.1f}s, "
        f"verify={TVerify:.1f}s, online={TOnline:.1f}s) ===",
        flush=True,
    )
    return 0


def Main(Argv=None) -> int:
    P = argparse.ArgumentParser(description="Per-service deploy: pause -> drain -> deploy -> Online.")
    P.add_argument("WorkerName", help="e.g. larry-worker-1, wakko-worker-2, I9-2024")
    Args = P.parse_args(Argv)
    Sha = _GitHead()
    if not Sha:
        print("[FAIL] git HEAD unreadable")
        return 2
    return DeployOne(Args.WorkerName, Sha)


if __name__ == "__main__":
    sys.exit(Main())
