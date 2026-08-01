import argparse
import hashlib
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Optional

DepsFingerprintPath = "/opt/mediavortex/.deploy-deps-fingerprint"
TorchPin = "torch==2.6.0 torchaudio==2.6.0"
TorchExpectedVersion = "2.6.0"


MediaVortexRoot = Path(__file__).resolve().parent.parent
BaremetalDir = MediaVortexRoot / "deploy" / "baremetal"
DefaultInventoryToml = Path(r"C:\Code\infrastructure\terraform\inventory.toml")
SshOpts = ["-o", "ConnectTimeout=5", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new"]
DefaultWorkerCount = 4
TorchIndexByVariant = {
    "cpu": "https://download.pytorch.org/whl/cpu",
    "cu124": "https://download.pytorch.org/whl/cu124",
    "cu121": "https://download.pytorch.org/whl/cu121",
    "xpu": "https://download.pytorch.org/whl/xpu",
}


def _Status(Step: int, Total: int, Title: str, Result: str = "...", Detail: str = "") -> None:
    Tag = {"OK": "[OK]   ", "SKIPPED": "[SKIP] ", "FAILED": "[FAIL] ", "...": "[..]   "}.get(Result, f"[{Result}] ")
    Suffix = f" -- {Detail}" if Detail else ""
    print(f"  {Tag}({Step}/{Total}) {Title}{Suffix}", flush=True)


def _Ssh(Target: str, Cmd: str, Timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["ssh", *SshOpts, Target, Cmd], capture_output=True, text=True, timeout=Timeout)


def _Scp(LocalPath: Path, Target: str, RemotePath: str, Timeout: int = 300) -> bool:
    R = subprocess.run(["scp", *SshOpts, "-r", str(LocalPath), f"{Target}:{RemotePath}"], capture_output=True, text=True, timeout=Timeout)
    return R.returncode == 0


def _ResolveTarget(TargetArg: str, InventoryToml: Path, UserOverride: Optional[str]):
    if not InventoryToml.exists():
        return TargetArg, TargetArg, (UserOverride or "root"), DefaultWorkerCount
    with open(InventoryToml, "rb") as F:
        Data = tomllib.load(F)
    for S in Data.get("services", []):
        if S.get("name") == TargetArg or S.get("compose_template") == TargetArg:
            Ip = None
            for N in S.get("nics", []):
                if N.get("role") == "primary":
                    Ip = N.get("ip")
                    break
            Ip = Ip or S.get("ip") or TargetArg
            Count = int(S.get("worker_count") or DefaultWorkerCount)
            User = UserOverride or S.get("ssh_user") or "root"
            return TargetArg, Ip, User, Count
    return TargetArg, TargetArg, (UserOverride or "root"), DefaultWorkerCount


def _DetectTorchVariant(Target: str) -> str:
    R = _Ssh(Target, "nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1", Timeout=10)
    if (R.stdout or "").strip():
        return "cu124"
    R = _Ssh(Target, "lspci -nn 2>/dev/null | grep -iE 'vga|3d|display' | grep -iE '\\[8086:e' | head -1", Timeout=10)
    if (R.stdout or "").strip():
        return "xpu"
    return "cpu"


def StepPreflight(Target: str, Friendly: str) -> bool:
    R = _Ssh(Target, "which python3.12 && test -d /mnt/media_tv && echo mounts_ok", Timeout=10)
    if "mounts_ok" not in (R.stdout or ""):
        _Status(1, 13, "preflight", "FAILED", f"missing python3.12 or /mnt/media_tv on {Friendly}")
        return False
    _Status(1, 13, "preflight", "OK", f"python3.12 + mounts present on {Friendly}")
    return True


def _ComputeDepsFingerprint(TorchVariant: str) -> str:
    # directive: scan-broken-restore -- fingerprints inputs that decide pip install output; changes invalidate cache.
    RequirementsPath = MediaVortexRoot / "WorkerService" / "requirements.txt"
    RootRequirementsPath = MediaVortexRoot / "requirements.txt"
    H = hashlib.sha256()
    H.update(f"torch-variant:{TorchVariant}\n".encode())
    H.update(f"torch-pin:{TorchPin}\n".encode())
    for P in (RootRequirementsPath, RequirementsPath):
        if P.exists():
            H.update(f"file:{P.name}\n".encode())
            H.update(P.read_bytes())
            H.update(b"\n")
    return H.hexdigest()


def _RemoteDepsFingerprint(Target: str) -> str:
    R = _Ssh(Target, f"cat {DepsFingerprintPath} 2>/dev/null || echo NONE", Timeout=10)
    return (R.stdout or "").strip()


def _WriteRemoteDepsFingerprint(Target: str, Fingerprint: str) -> None:
    _Ssh(Target, f"mkdir -p /opt/mediavortex && printf '%s' '{Fingerprint}' > {DepsFingerprintPath}", Timeout=10)


def _RemoteTorchVersion(Target: str) -> str:
    R = _Ssh(Target, "/opt/mediavortex/host-venv/bin/pip show torch 2>/dev/null | awk '/^Version:/ {print $2}'", Timeout=15)
    return (R.stdout or "").strip()


# directive: scan-broken-restore -- state check (pip show torch) beats marker check; torch installed at pin = skip always.
def StepEnsureVenv(Target: str, TorchVariant: str, DepsFingerprint: str) -> bool:
    VenvOk = _Ssh(Target, "test -x /opt/mediavortex/host-venv/bin/pip && echo YES || echo NO", Timeout=10).stdout.strip()
    if VenvOk == "YES":
        InstalledTorch = _RemoteTorchVersion(Target)
        if InstalledTorch.startswith(TorchExpectedVersion):
            _Status(2, 13, "ensure venv", "SKIPPED", f"torch {InstalledTorch} already installed")
            return True
    Index = TorchIndexByVariant.get(TorchVariant, TorchIndexByVariant["cpu"])
    Script = (
        "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3.12-venv python3-pip > /dev/null && "
        "mkdir -p /opt/mediavortex && "
        "if [ ! -x /opt/mediavortex/host-venv/bin/pip ]; then "
        "  rm -rf /opt/mediavortex/host-venv && python3.12 -m venv /opt/mediavortex/host-venv && "
        "  /opt/mediavortex/host-venv/bin/pip install --no-cache-dir --upgrade pip wheel > /dev/null; "
        "fi && "
        "/opt/mediavortex/host-venv/bin/pip install --no-cache-dir "
        f"--index-url {Index} {TorchPin} > /tmp/mv-pip-torch.log 2>&1 && "
        "echo VENV_READY"
    )
    R = _Ssh(Target, Script, Timeout=1800)
    if "VENV_READY" not in (R.stdout or ""):
        _Status(2, 13, "ensure venv", "FAILED", (R.stderr or "")[-200:])
        return False
    _Status(2, 13, "ensure venv", "OK", f"torch variant={TorchVariant}")
    return True


# directive: scan-broken-restore -- requirements.txt content hash marker; skip pip install if unchanged.
def StepInstallRequirements(Target: str, DepsFingerprint: str) -> bool:
    Remote = _RemoteDepsFingerprint(Target)
    if Remote == DepsFingerprint:
        _Status(8, 13, "install requirements", "SKIPPED", f"requirements unchanged (fingerprint {DepsFingerprint[:8]})")
        return True
    Script = (
        "/opt/mediavortex/host-venv/bin/pip install --no-cache-dir "
        "-r /opt/mediavortex/src/WorkerService/requirements.txt "
        "> /tmp/mv-pip-reqs.log 2>&1 && echo REQS_READY"
    )
    R = _Ssh(Target, Script, Timeout=1800)
    if "REQS_READY" not in (R.stdout or ""):
        Tail = _Ssh(Target, "tail -20 /tmp/mv-pip-reqs.log", Timeout=10).stdout or ""
        _Status(8, 13, "install requirements", "FAILED", Tail[-300:])
        return False
    _WriteRemoteDepsFingerprint(Target, DepsFingerprint)
    _Status(8, 13, "install requirements", "OK", f"-r WorkerService/requirements.txt; wrote fingerprint {DepsFingerprint[:8]}")
    return True


def StepEnsureFfmpeg(Target: str) -> bool:
    R = _Ssh(Target, "test -x /usr/local/bin/ffmpeg && echo FFMPEG_OK", Timeout=10)
    if "FFMPEG_OK" in (R.stdout or ""):
        _Status(3, 13, "ensure ffmpeg", "SKIPPED", "already at /usr/local/bin/ffmpeg")
        return True
    _Ssh(Target, "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ffmpeg > /dev/null && ln -sf $(which ffmpeg) /usr/local/bin/ffmpeg && ln -sf $(which ffprobe) /usr/local/bin/ffprobe", Timeout=300)
    _Status(3, 13, "ensure ffmpeg", "OK", "apt install ffmpeg")
    return True


# directive: transcode-flow-canonical -- stop systemd units before SyncSource; SyncSource preserves the dir inode, but systemd stop is the operator-visible drain that also guarantees no ffmpeg subprocesses are mid-flight during the file swap
def StepStopSystemdUnits(Target: str, Count: int) -> bool:
    Units = " ".join(f"mediavortex-worker@{I}.service" for I in range(1, Count + 1))
    _Ssh(Target, f"systemctl stop {Units} 2>&1 || true", Timeout=120)
    _Ssh(Target, "mkdir -p /opt/mediavortex/src /etc/mediavortex", Timeout=10)
    _Status(4, 13, "stop systemd units + prep dirs", "OK", f"{Count} unit(s) stopped")
    return True


# directive: transcode-flow-canonical | # see worker-deploy.C14
def StepSyncSource(Target: str) -> bool:
    Sync = MediaVortexRoot / "deploy" / "SyncSource.py"
    R = subprocess.run([sys.executable, str(Sync), Target, "/opt/mediavortex/src", "--prune"], capture_output=True, text=True, timeout=600)
    if R.returncode != 0:
        _Status(5, 13, "sync source", "FAILED", (R.stderr or R.stdout or "")[-200:])
        return False
    _Status(5, 13, "sync source", "OK", "source at /opt/mediavortex/src (in-place; stale files pruned)")
    return True


# directive: transcode-flow-canonical -- stamp VERSION with actual HEAD sha on target
def StepStampVersion(Target: str) -> bool:
    Head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(MediaVortexRoot), capture_output=True, text=True, timeout=10)
    if Head.returncode != 0:
        _Status(6, 13, "stamp VERSION", "FAILED", (Head.stderr or Head.stdout or '')[-200:])
        return False
    Sha = Head.stdout.strip()
    R = _Ssh(Target, f"echo -n {Sha} > /opt/mediavortex/src/VERSION", Timeout=15)
    if R.returncode != 0:
        _Status(6, 13, "stamp VERSION", "FAILED", (R.stderr or R.stdout or '')[-200:])
        return False
    _Status(6, 13, "stamp VERSION", "OK", f"stamped {Sha[:7]}")
    return True


# directive: transcode-flow-canonical -- .claude is excluded from SyncSource; ship schema snapshot explicitly
def StepShipSchemaSnapshot(Target: str) -> bool:
    Snapshot = MediaVortexRoot / ".claude" / "schema" / "snapshot.json"
    if not Snapshot.exists():
        _Status(7, 13, "ship schema snapshot", "SKIP", "no local snapshot")
        return True
    _Ssh(Target, "mkdir -p /opt/mediavortex/src/.claude/schema", Timeout=10)
    if not _Scp(Snapshot, Target, "/opt/mediavortex/src/.claude/schema/snapshot.json", Timeout=30):
        _Status(7, 13, "ship schema snapshot", "FAILED")
        return False
    _Status(7, 13, "ship schema snapshot", "OK")
    return True


# directive: transcode-flow-canonical | # see claim-authority.md
def StepInstallSystemdUnit(Target: str, Friendly: str, Count: int) -> bool:
    """Install unit template + write one instance-N.env per systemd instance. WorkerName is deploy-assigned; no runtime slot-claim."""
    UnitLocal = BaremetalDir / "mediavortex-worker@.service"
    EnvLocal = BaremetalDir / "worker.env.template"
    _Scp(UnitLocal, Target, "/etc/systemd/system/mediavortex-worker@.service", Timeout=30)
    R = _Ssh(Target, "test -f /etc/mediavortex/worker.env && echo ENV_EXISTS", Timeout=10)
    if "ENV_EXISTS" not in (R.stdout or ""):
        _Scp(EnvLocal, Target, "/etc/mediavortex/worker.env", Timeout=30)
    _Ssh(Target, "rm -f /etc/mediavortex/worker-prefix.env", Timeout=10)
    Writes = " && ".join(
        f"echo 'MEDIAVORTEX_WORKER_NAME={Friendly}-worker-{I}' > /etc/mediavortex/instance-{I}.env"
        for I in range(1, Count + 1)
    )
    _Ssh(Target, Writes, Timeout=30)
    _Ssh(Target, "systemctl daemon-reload", Timeout=10)
    _Status(9, 13, "install systemd unit + instance env", "OK", f"{Count} instance-N.env file(s) written under /etc/mediavortex/")
    return True


# directive: transcode-flow-canonical | # see claim-authority.md
def StepStartInstances(Target: str, Friendly: str, Count: int) -> bool:
    """Start each systemd instance. Serialization not required: WorkerName is deploy-assigned, no advisory-claim race."""
    Units = " ".join(f"mediavortex-worker@{I}.service" for I in range(1, Count + 1))
    _Ssh(Target, f"systemctl enable --now {Units}", Timeout=60)
    R = _Ssh(Target, f"systemctl list-units 'mediavortex-worker@*' --no-legend --state=active | wc -l", Timeout=10)
    Active = int((R.stdout or "0").strip() or 0)
    if Active < Count:
        _Status(11, 13, "start instances", "FAILED", f"expected {Count} active, got {Active}")
        return False
    _Status(11, 13, "start instances", "OK", f"{Active}/{Count} instances active")
    return True


def StepVerify(Target: str, Friendly: str, Count: int) -> bool:
    R = _Ssh(Target, "systemctl list-units 'mediavortex-worker@*' --no-legend --state=active | awk '{print $1}' | head -8", Timeout=10)
    Lines = [L.strip() for L in (R.stdout or "").splitlines() if L.strip()]
    _Status(13, 13, "verify", "OK" if len(Lines) >= Count else "FAILED", f"{len(Lines)}/{Count} systemd units active on {Friendly}")
    return len(Lines) >= Count


# directive: transcode-flow-canonical -- bare-metal deploy reconciles Workers.{nvenccapable,qsvcapable}
def StepReconcileCapabilities(Target: str, Friendly: str) -> bool:
    ScriptsDir = MediaVortexRoot / "Scripts"
    Prefix = f"{Friendly}-worker"
    NvR = subprocess.run([sys.executable, str(ScriptsDir / "ReconcileNvencCapability.py"), Target, "--worker-prefix", Prefix], capture_output=True, text=True, timeout=180)
    if NvR.returncode != 0:
        _Status(12, 13, "capability reconcile", "FAILED", f"nvenc: {(NvR.stderr or NvR.stdout)[-200:]}")
        return False
    QsvR = subprocess.run([sys.executable, str(ScriptsDir / "ReconcileQsvCapability.py"), Target, "--worker-prefix", Prefix], capture_output=True, text=True, timeout=180)
    if QsvR.returncode != 0:
        _Status(12, 13, "capability reconcile", "FAILED", f"qsv: {(QsvR.stderr or QsvR.stdout)[-200:]}")
        return False
    NvTail = (NvR.stdout or '').strip().splitlines()[-1] if NvR.stdout else ''
    QsvTail = (QsvR.stdout or '').strip().splitlines()[-1] if QsvR.stdout else ''
    _Status(12, 13, "capability reconcile", "OK", f"nvenc: {NvTail} | qsv: {QsvTail}")
    return True


def main():
    Parser = argparse.ArgumentParser(description="Idempotent bare-metal deploy for MediaVortex WorkerService.")
    Parser.add_argument("target", help="Friendly name (dot, wakko, larry) or IP literal.")
    Parser.add_argument("--user", default=None)
    Parser.add_argument("--count", type=int, default=None)
    Parser.add_argument("--torch-variant", default=None, choices=list(TorchIndexByVariant.keys()))
    Parser.add_argument("--inventory", type=Path, default=DefaultInventoryToml)
    Parser.add_argument("--sync-only", action="store_true",
                        help="Sync source + install deps + install systemd unit; skip stop/start/verify. Used by deploy-worker.py per-service driver.")
    Args = Parser.parse_args()

    Friendly, Ip, User, InventoryCount = _ResolveTarget(Args.target, Args.inventory, Args.user)
    Count = Args.count or InventoryCount
    Target = f"{User}@{Ip}"
    print("=" * 60)
    print(f"Target: {Friendly} ({Target}), count={Count}")

    Variant = Args.torch_variant or _DetectTorchVariant(Target)
    print(f"Torch variant: {Variant}")
    DepsFingerprint = _ComputeDepsFingerprint(Variant)
    print(f"Deps fingerprint: {DepsFingerprint[:16]}")
    print("=" * 60)

    if not StepPreflight(Target, Friendly):
        return 1
    if not StepEnsureVenv(Target, Variant, DepsFingerprint):
        return 2
    if not StepEnsureFfmpeg(Target):
        return 2
    if not Args.sync_only:
        if not StepStopSystemdUnits(Target, Count):
            return 2
    if not StepSyncSource(Target):
        return 2
    if not StepStampVersion(Target):
        return 2
    if not StepShipSchemaSnapshot(Target):
        return 2
    if not StepInstallRequirements(Target, DepsFingerprint):
        return 2
    if not StepInstallSystemdUnit(Target, Friendly, Count):
        return 2
    if Args.sync_only:
        print()
        print(f"[OK] --sync-only complete on {Friendly}; per-service restart handled by deploy-worker.py")
        return 0
    if not StepStartInstances(Target, Friendly, Count):
        return 3
    if not StepReconcileCapabilities(Target, Friendly):
        return 3
    if not StepVerify(Target, Friendly, Count):
        return 3
    print()
    print(f"[OK] bare-metal deploy complete on {Friendly}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
