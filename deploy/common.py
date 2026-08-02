# see .claude/rules/worker-deploy.md
import re
import subprocess
from pathlib import Path

MediaVortexRoot = Path(__file__).resolve().parent.parent

SshOpts = ["-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
           "-o", "StrictHostKeyChecking=accept-new"]


def HostFromWorkerName(WorkerName: str) -> str:
    M = re.match(r"^(.+)-worker-\d+$", WorkerName)
    if M:
        return M.group(1)
    M = re.match(r"^([A-Za-z0-9]+)-\d+$", WorkerName)
    if M:
        return M.group(1)
    return WorkerName


def SystemdInstanceFromWorkerName(WorkerName: str) -> str:
    M = re.match(r"^.+-worker-(\d+)$", WorkerName)
    if not M:
        raise ValueError(f"cannot derive systemd instance from {WorkerName!r}")
    return M.group(1)


def SystemdUnitFromWorkerName(WorkerName: str) -> str:
    return f"mediavortex-worker@{SystemdInstanceFromWorkerName(WorkerName)}.service"


def IsWindowsLocal(Host: str) -> bool:
    return Host.upper().startswith("I9")


def GitHead() -> str:
    R = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                       cwd=str(MediaVortexRoot))
    return R.stdout.strip()


def GitOriginMain() -> str:
    R = subprocess.run(["git", "rev-parse", "origin/main"], capture_output=True, text=True,
                       cwd=str(MediaVortexRoot))
    return R.stdout.strip() if R.returncode == 0 else ""


def Sh(Cmd, cwd=None, timeout=60):
    return subprocess.run(Cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout)


def LoadBaremetalDeployModule():
    from importlib.util import spec_from_file_location, module_from_spec
    Baremetal = MediaVortexRoot / "deploy" / "deploy-baremetal-worker.py"
    Spec = spec_from_file_location("_bd", str(Baremetal))
    Mod = module_from_spec(Spec)
    Spec.loader.exec_module(Mod)
    return Mod


def ResolveInventory(Host: str):
    Mod = LoadBaremetalDeployModule()
    Friendly, Ip, User, _ = Mod._ResolveTarget(Host, Mod.DefaultInventoryToml, None)
    return Friendly, Ip, User
