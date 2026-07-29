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


def _ComposeServiceFromWorkerName(Wn: str) -> str:
    M = re.match(r"^[A-Za-z0-9]+-(worker-\d+)$", Wn)
    if not M:
        raise ValueError(f"cannot derive compose service from {Wn!r}")
    return M.group(1)


def _BaremetalUnitFromWorkerName(Wn: str) -> str:
    M = re.match(r"^[A-Za-z0-9]+-worker-(\d+)$", Wn)
    if not M:
        raise ValueError(f"cannot derive systemd unit from {Wn!r}")
    return f"mediavortex-worker@{M.group(1)}.service"


def PauseWorker(Db, WorkerName: str) -> None:
    print(f"[1/6] pause: {WorkerName}")
    Db.ExecuteNonQuery(
        "UPDATE Workers SET Status='Paused' WHERE WorkerName=%s AND Status<>'Paused'",
        (WorkerName,),
    )


def DrainWorker(Db, WorkerName: str) -> bool:
    print(f"[2/6] drain: {WorkerName} (timeout {DrainTimeoutSec}s)")
    Deadline = time.time() + DrainTimeoutSec
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
            print("       drained: ActiveJobs=0, ScanJobs=0")
            return True
        Elapsed = int(DrainTimeoutSec - (Deadline - time.time()))
        print(f"       waiting: ActiveJobs={ActiveJobs} ScanBusy={ScanBusy} ({Elapsed}s elapsed)")
        time.sleep(DrainPollSec)
    print("[FAIL] drain budget exceeded")
    return False


def _LinuxDockerHost(Host: str) -> bool:
    return (MediaVortexRoot / "deploy" / "compose-templates" / f"{Host}.yml").exists()


def _WindowsLocal(Host: str) -> bool:
    return Host.upper().startswith("I9")


def _LoadLinuxDeployModule():
    from importlib.util import spec_from_file_location, module_from_spec
    LinuxDeploy = MediaVortexRoot / "deploy" / "deploy-linux-worker.py"
    Spec = spec_from_file_location("_ld", str(LinuxDeploy))
    Mod = module_from_spec(Spec)
    Spec.loader.exec_module(Mod)
    return Mod


def _ResolveInventory(Host: str):
    Mod = _LoadLinuxDeployModule()
    Friendly, Ip, User = Mod._ResolveTarget(Host, Mod.DefaultInventoryToml, None)
    return Friendly, Ip, User


def DeployLinuxDocker(WorkerName: str, Host: str, Sha: str) -> bool:
    print(f"[3/6] deploy backend: linux-docker (host={Host})")
    _, Ip, User = _ResolveInventory(Host)
    Target = f"{User}@{Ip}"

    print("       source sync + image build via deploy-linux-worker.py --build-only")
    R = subprocess.run(
        [sys.executable, str(MediaVortexRoot / "deploy" / "deploy-linux-worker.py"),
         Host, "--build-only"],
        cwd=str(MediaVortexRoot),
    )
    if R.returncode != 0:
        print(f"[FAIL] build-only prep for {Host}")
        return False

    Svc = _ComposeServiceFromWorkerName(WorkerName)
    print(f"[4/6] recreate service: {Svc}")
    Cmd = f"cd /opt/mediavortex && docker compose up -d --no-deps --force-recreate {Svc}"
    R = subprocess.run(["ssh", *SshOpts, Target, Cmd], timeout=180)
    return R.returncode == 0


def DeployBaremetal(WorkerName: str, Host: str, Sha: str) -> bool:
    print(f"[3/6] deploy backend: baremetal (host={Host})")
    _, Ip, User = _ResolveInventory(Host)
    Target = f"{User}@{Ip}"

    print("       source rsync via deploy-baremetal-worker.py --sync-only")
    R = subprocess.run(
        [sys.executable, str(MediaVortexRoot / "deploy" / "deploy-baremetal-worker.py"),
         Host, "--sync-only"],
        cwd=str(MediaVortexRoot),
    )
    if R.returncode != 0:
        print(f"[FAIL] sync-only prep for {Host}")
        return False

    Unit = _BaremetalUnitFromWorkerName(WorkerName)
    print(f"[4/6] restart systemd unit: {Unit}")
    R = subprocess.run(["ssh", *SshOpts, Target, f"systemctl restart {Unit}"], timeout=60)
    return R.returncode == 0


def DeployWindowsLocal(WorkerName: str, Sha: str) -> bool:
    print(f"[3/6] deploy backend: windows-local ({WorkerName})")
    import os as _os
    try:
        import psutil
    except ImportError:
        print("[FAIL] psutil not installed")
        return False
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
    print(f"       terminated {Killed} WorkerService process(es)")

    WorkerPy = MediaVortexRoot / "WorkerService" / "venv" / "Scripts" / "python.exe"
    Main = MediaVortexRoot / "WorkerService" / "Main.py"
    LogFile = MediaVortexRoot / "WorkerService" / "deploy-worker.log"
    CreationFlags = 0
    if _os.name == "nt":
        CreationFlags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    Fh = open(LogFile, "ab", buffering=0)
    print("[4/6] start WorkerService (detached)")
    subprocess.Popen(
        [str(WorkerPy), str(Main)],
        cwd=str(MediaVortexRoot),
        stdout=Fh, stderr=Fh,
        creationflags=CreationFlags,
        close_fds=True,
        start_new_session=(_os.name != "nt"),
    )
    return True


def VerifyWorker(Db, WorkerName: str, Sha: str) -> bool:
    print(f"[5/6] verify: Version~={Sha[:8]}, heartbeat<60s")
    Deadline = time.time() + VerifyTimeoutSec
    while time.time() < Deadline:
        Rows = Db.ExecuteQuery(
            "SELECT COALESCE(Version,'') AS Version, "
            "EXTRACT(EPOCH FROM (NOW() - LastHeartbeat))::int AS hb_age "
            "FROM Workers WHERE WorkerName=%s",
            (WorkerName,),
        )
        if not Rows:
            print(f"[FAIL] worker {WorkerName} not found")
            return False
        R = Rows[0]
        if (R["Version"] or "").startswith(Sha[:8]) and (R["hb_age"] or 999) < 60:
            print(f"       ok: Version={R['Version'][:8]} hb_age={R['hb_age']}s")
            return True
        Elapsed = int(VerifyTimeoutSec - (Deadline - time.time()))
        print(f"       waiting: Version={(R['Version'] or 'NONE')[:8]} hb_age={R['hb_age']}s ({Elapsed}s elapsed)")
        time.sleep(VerifyPollSec)
    print("[FAIL] verify timeout")
    return False


def OnlineWorker(Db, WorkerName: str) -> None:
    print(f"[6/6] online: {WorkerName}")
    Db.ExecuteNonQuery(
        "UPDATE Workers SET Status='Online' WHERE WorkerName=%s",
        (WorkerName,),
    )


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

    print(f"=== deploy-worker {WorkerName} (Platform={Platform}, Host={Host}, Sha={Sha[:8]}) ===")

    PauseWorker(Db, WorkerName)
    if not DrainWorker(Db, WorkerName):
        return 3

    if _WindowsLocal(Host):
        Ok = DeployWindowsLocal(WorkerName, Sha)
    elif _LinuxDockerHost(Host):
        Ok = DeployLinuxDocker(WorkerName, Host, Sha)
    else:
        Ok = DeployBaremetal(WorkerName, Host, Sha)
    if not Ok:
        print("[FAIL] backend deploy failed; leaving Status=Paused")
        return 4

    if not VerifyWorker(Db, WorkerName, Sha):
        print("[FAIL] verify failed; leaving Status=Paused")
        return 5

    OnlineWorker(Db, WorkerName)
    print(f"=== OK {WorkerName} ===")
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
