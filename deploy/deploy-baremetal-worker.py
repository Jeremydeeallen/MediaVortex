import argparse
import hashlib
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Optional


MediaVortexRoot = Path(__file__).resolve().parent.parent
BaremetalDir = MediaVortexRoot / "deploy" / "baremetal"
DefaultInventoryToml = Path(r"C:\Code\infrastructure\terraform\inventory.toml")
SshOpts = ["-o", "ConnectTimeout=5", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new"]
DefaultWorkerCount = 4

TorchPin = "torch==2.6.0 torchaudio==2.6.0"
TorchExpectedVersion = "2.6.0"
TorchIndexByVariant = {
    "cpu": "https://download.pytorch.org/whl/cpu",
    "cu124": "https://download.pytorch.org/whl/cu124",
    "cu121": "https://download.pytorch.org/whl/cu121",
    "xpu": "https://download.pytorch.org/whl/xpu",
}

# see .claude/rules/worker-deploy.md
KeepVersions = 5


def _Status(Step: int, Total: int, Title: str, Result: str = "...", Detail: str = "") -> None:
    Tag = {"OK": "[OK]   ", "SKIPPED": "[SKIP] ", "FAILED": "[FAIL] ", "...": "[..]   "}.get(Result, f"[{Result}] ")
    Suffix = f" -- {Detail}" if Detail else ""
    print(f"  {Tag}({Step}/{Total}) {Title}{Suffix}", flush=True)


def _Ssh(Target: str, Cmd: str, Timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["ssh", *SshOpts, Target, Cmd], capture_output=True, text=True, timeout=Timeout)


def _Scp(LocalPath: Path, Target: str, RemotePath: str, Timeout: int = 300) -> bool:
    R = subprocess.run(["scp", *SshOpts, "-r", str(LocalPath), f"{Target}:{RemotePath}"],
                       capture_output=True, text=True, timeout=Timeout)
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


def _ComputeDepsFingerprint(TorchVariant: str) -> str:
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


def StepPreflight(Target: str, Friendly: str) -> bool:
    R = _Ssh(Target, "which python3.12 && test -d /mnt/media_tv && echo mounts_ok", Timeout=10)
    if "mounts_ok" not in (R.stdout or ""):
        _Status(1, 10, "preflight", "FAILED", f"missing python3.12 or /mnt/media_tv on {Friendly}")
        return False
    _Status(1, 10, "preflight", "OK", f"python3.12 + mounts present on {Friendly}")
    return True


def StepMigrateLegacyLayout(Target: str, Friendly: str) -> bool:
    # see .claude/rules/worker-deploy.md
    Script = (
        "mkdir -p /opt/mediavortex /etc/mediavortex && cd /opt/mediavortex && "
        "if [ -e src ] && [ ! -L src ] && [ -d src ]; then "
        "  mv src src-legacy-$(date +%Y%m%d-%H%M%S); "
        "fi && "
        "if [ -e host-venv ] && [ ! -L host-venv ] && [ -d host-venv ]; then "
        "  mv host-venv host-venv-legacy-$(date +%Y%m%d-%H%M%S); "
        "fi && echo MIGRATE_OK"
    )
    R = _Ssh(Target, Script, Timeout=30)
    _Status(2, 10, "migrate legacy layout", "OK" if "MIGRATE_OK" in (R.stdout or "") else "FAILED", "")
    return "MIGRATE_OK" in (R.stdout or "")


def StepEnsureVenv(Target: str, TorchVariant: str, DepsFingerprint: str) -> tuple:
    # see .claude/rules/worker-deploy.md
    VenvPath = f"/opt/mediavortex/host-venv-{DepsFingerprint[:16]}"
    Check = _Ssh(Target, f"test -x {VenvPath}/bin/pip && echo YES || echo NO", Timeout=10).stdout.strip()
    if Check == "YES":
        InstalledTorch = _Ssh(
            Target,
            f"{VenvPath}/bin/pip show torch 2>/dev/null | awk '/^Version:/ {{print $2}}'",
            Timeout=15,
        ).stdout.strip()
        if InstalledTorch.startswith(TorchExpectedVersion):
            _Status(3, 10, "ensure venv", "SKIPPED", f"{VenvPath} exists, torch {InstalledTorch}")
            return True, VenvPath
    Index = TorchIndexByVariant.get(TorchVariant, TorchIndexByVariant["cpu"])
    Script = (
        "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3.12-venv python3-pip > /dev/null && "
        f"rm -rf {VenvPath} && python3.12 -m venv {VenvPath} && "
        f"{VenvPath}/bin/pip install --no-cache-dir --upgrade pip wheel > /dev/null && "
        f"{VenvPath}/bin/pip install --no-cache-dir --index-url {Index} {TorchPin} > /tmp/mv-pip-torch.log 2>&1 && "
        "echo VENV_READY"
    )
    R = _Ssh(Target, Script, Timeout=1800)
    if "VENV_READY" not in (R.stdout or ""):
        _Status(3, 10, "ensure venv", "FAILED", (R.stderr or "")[-200:])
        return False, VenvPath
    _Status(3, 10, "ensure venv", "OK", f"{VenvPath} (torch={TorchVariant})")
    return True, VenvPath


def StepEnsureFfmpeg(Target: str) -> bool:
    R = _Ssh(Target, "test -x /usr/local/bin/ffmpeg && echo FFMPEG_OK", Timeout=10)
    if "FFMPEG_OK" in (R.stdout or ""):
        _Status(4, 10, "ensure ffmpeg", "SKIPPED", "already at /usr/local/bin/ffmpeg")
        return True
    _Ssh(Target,
         "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ffmpeg > /dev/null && "
         "ln -sf $(which ffmpeg) /usr/local/bin/ffmpeg && "
         "ln -sf $(which ffprobe) /usr/local/bin/ffprobe",
         Timeout=300)
    _Status(4, 10, "ensure ffmpeg", "OK", "apt install ffmpeg")
    return True


def StepSyncSource(Target: str, Sha: str) -> tuple:
    # see .claude/rules/worker-deploy.md
    SrcPath = f"/opt/mediavortex/src-{Sha[:16]}"
    _Ssh(Target, f"mkdir -p {SrcPath}", Timeout=10)
    Sync = MediaVortexRoot / "deploy" / "SyncSource.py"
    R = subprocess.run([sys.executable, str(Sync), Target, SrcPath, "--prune"],
                       capture_output=True, text=True, timeout=600)
    if R.returncode != 0:
        _Status(5, 10, "sync source", "FAILED", (R.stderr or R.stdout or "")[-200:])
        return False, SrcPath
    _Status(5, 10, "sync source", "OK", SrcPath)
    return True, SrcPath


def StepStampVersion(Target: str, SrcPath: str, Sha: str) -> bool:
    R = _Ssh(Target, f"echo -n {Sha} > {SrcPath}/VERSION", Timeout=15)
    if R.returncode != 0:
        _Status(6, 10, "stamp VERSION", "FAILED", "")
        return False
    _Status(6, 10, "stamp VERSION", "OK", f"{Sha[:7]} into {SrcPath}/VERSION")
    return True


def StepShipSchemaSnapshot(Target: str, SrcPath: str) -> bool:
    Snapshot = MediaVortexRoot / ".claude" / "schema" / "snapshot.json"
    if not Snapshot.exists():
        _Status(7, 10, "ship schema snapshot", "SKIP", "no local snapshot")
        return True
    _Ssh(Target, f"mkdir -p {SrcPath}/.claude/schema", Timeout=10)
    if not _Scp(Snapshot, Target, f"{SrcPath}/.claude/schema/snapshot.json", Timeout=30):
        _Status(7, 10, "ship schema snapshot", "FAILED")
        return False
    _Status(7, 10, "ship schema snapshot", "OK")
    return True


def StepInstallRequirements(Target: str, VenvPath: str, SrcPath: str, DepsFingerprint: str) -> bool:
    # see .claude/rules/worker-deploy.md
    FingerprintFile = f"{VenvPath}/.deps-fingerprint"
    Remote = _Ssh(Target, f"cat {FingerprintFile} 2>/dev/null || echo NONE", Timeout=10).stdout.strip()
    if Remote == DepsFingerprint:
        _Status(8, 10, "install requirements", "SKIPPED", f"fingerprint {DepsFingerprint[:8]} unchanged")
        return True
    Script = (
        f"{VenvPath}/bin/pip install --no-cache-dir -r {SrcPath}/WorkerService/requirements.txt "
        "> /tmp/mv-pip-reqs.log 2>&1 && "
        f"printf '%s' '{DepsFingerprint}' > {FingerprintFile} && echo REQS_READY"
    )
    R = _Ssh(Target, Script, Timeout=1800)
    if "REQS_READY" not in (R.stdout or ""):
        Tail = _Ssh(Target, "tail -20 /tmp/mv-pip-reqs.log", Timeout=10).stdout or ""
        _Status(8, 10, "install requirements", "FAILED", Tail[-300:])
        return False
    _Status(8, 10, "install requirements", "OK", f"{DepsFingerprint[:8]}")
    return True


def StepRenderSystemdUnit(Target: str, Friendly: str, Count: int, SrcPath: str, VenvPath: str) -> bool:
    # see .claude/rules/worker-deploy.md
    UnitBody = (
        "[Unit]\n"
        "Description=MediaVortex WorkerService instance %i\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        "User=root\n"
        f"WorkingDirectory={SrcPath}\n"
        "EnvironmentFile=/etc/mediavortex/worker.env\n"
        "EnvironmentFile=/etc/mediavortex/instance-%i.env\n"
        "Environment=PYTHONUNBUFFERED=1\n"
        "Environment=HOME=/root\n"
        f"ExecStart={VenvPath}/bin/python {SrcPath}/WorkerService/Main.py\n"
        "Restart=always\n"
        "RestartSec=10\n"
        "TimeoutStopSec=1800\n"
        "KillSignal=SIGTERM\n"
        "LimitNOFILE=65536\n"
        "\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )
    EnvLocal = BaremetalDir / "worker.env.template"
    R = _Ssh(Target,
             f"cat > /etc/systemd/system/mediavortex-worker@.service <<'UNIT_EOF'\n{UnitBody}UNIT_EOF",
             Timeout=15)
    if R.returncode != 0:
        _Status(9, 10, "render systemd unit", "FAILED", (R.stderr or "")[-200:])
        return False
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
    _Ssh(Target, "systemctl enable " + " ".join(f"mediavortex-worker@{I}.service" for I in range(1, Count + 1)), Timeout=30)
    _Status(9, 10, "render systemd unit", "OK", f"{Count} instance env(s); daemon-reload")
    return True


def StepGarbageCollect(Target: str) -> bool:
    # see .claude/rules/worker-deploy.md
    Script = (
        f"cd /opt/mediavortex && "
        f"ls -1t src-* 2>/dev/null | grep -v -- '-legacy-' | tail -n +{KeepVersions + 1} | "
        f"  xargs -r -I {{}} rm -rf {{}} && "
        f"ls -1t host-venv-* 2>/dev/null | grep -v -- '-legacy-' | tail -n +{KeepVersions + 1} | "
        f"  xargs -r -I {{}} rm -rf {{}} && "
        "echo GC_OK"
    )
    R = _Ssh(Target, Script, Timeout=60)
    _Status(10, 10, "garbage collect", "OK" if "GC_OK" in (R.stdout or "") else "SKIPPED",
            f"kept last {KeepVersions} src + venv")
    return True


def main():
    Parser = argparse.ArgumentParser(description="Bare-metal per-host sync: versioned src + venv + rendered systemd unit + GC. Restarts happen via deploy-worker.py.")
    Parser.add_argument("target", help="Friendly name (dot, wakko, mediavortex-workers) or IP.")
    Parser.add_argument("--user", default=None)
    Parser.add_argument("--count", type=int, default=None)
    Parser.add_argument("--torch-variant", default=None, choices=list(TorchIndexByVariant.keys()))
    Parser.add_argument("--inventory", type=Path, default=DefaultInventoryToml)
    Args = Parser.parse_args()

    Friendly, Ip, User, InventoryCount = _ResolveTarget(Args.target, Args.inventory, Args.user)
    Count = Args.count or InventoryCount
    Target = f"{User}@{Ip}"

    Sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(MediaVortexRoot),
                         capture_output=True, text=True, timeout=10).stdout.strip()
    if not Sha:
        print("[FAIL] git HEAD unreadable")
        return 2

    Variant = Args.torch_variant or _DetectTorchVariant(Target)
    DepsFingerprint = _ComputeDepsFingerprint(Variant)

    print("=" * 60)
    print(f"Target: {Friendly} ({Target}), count={Count}")
    print(f"Sha: {Sha[:16]}")
    print(f"Torch variant: {Variant}")
    print(f"Deps fingerprint: {DepsFingerprint[:16]}")
    print("=" * 60)

    if not StepPreflight(Target, Friendly):
        return 1
    if not StepMigrateLegacyLayout(Target, Friendly):
        return 2
    Ok, VenvPath = StepEnsureVenv(Target, Variant, DepsFingerprint)
    if not Ok:
        return 2
    if not StepEnsureFfmpeg(Target):
        return 2
    # directive: deploy-gc-before-sync -- pre-sync GC frees disk before tar; prevents death-spiral when disk fills mid-deploy
    StepGarbageCollect(Target)
    Ok, SrcPath = StepSyncSource(Target, Sha)
    if not Ok:
        return 2
    if not StepStampVersion(Target, SrcPath, Sha):
        return 2
    if not StepShipSchemaSnapshot(Target, SrcPath):
        return 2
    if not StepInstallRequirements(Target, VenvPath, SrcPath, DepsFingerprint):
        return 2
    if not StepRenderSystemdUnit(Target, Friendly, Count, SrcPath, VenvPath):
        return 2
    if not StepGarbageCollect(Target):
        return 2

    print()
    print(f"[OK] bare-metal sync complete on {Friendly}")
    print(f"     src={SrcPath}")
    print(f"     venv={VenvPath}")
    print(f"     Restart workers to pick up new unit config: `py deploy/deploy-fleet.py`")
    return 0


if __name__ == "__main__":
    sys.exit(main())
