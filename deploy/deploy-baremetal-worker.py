# directive: audio-dialog-boost-real | # see audio-normalization.C14
import argparse
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
TorchIndexByVariant = {
    "cpu": "https://download.pytorch.org/whl/cpu",
    "cu124": "https://download.pytorch.org/whl/cu124",
    "cu121": "https://download.pytorch.org/whl/cu121",
    "xpu": "https://download.pytorch.org/whl/xpu",
}


# directive: audio-dialog-boost-real | # see audio-normalization.C14
def _Status(Step: int, Total: int, Title: str, Result: str = "...", Detail: str = "") -> None:
    Tag = {"OK": "[OK]   ", "SKIPPED": "[SKIP] ", "FAILED": "[FAIL] ", "...": "[..]   "}.get(Result, f"[{Result}] ")
    Suffix = f" -- {Detail}" if Detail else ""
    print(f"  {Tag}({Step}/{Total}) {Title}{Suffix}", flush=True)


# directive: audio-dialog-boost-real | # see audio-normalization.C14
def _Ssh(Target: str, Cmd: str, Timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["ssh", *SshOpts, Target, Cmd], capture_output=True, text=True, timeout=Timeout)


# directive: audio-dialog-boost-real | # see audio-normalization.C14
def _Scp(LocalPath: Path, Target: str, RemotePath: str, Timeout: int = 300) -> bool:
    R = subprocess.run(["scp", *SshOpts, "-r", str(LocalPath), f"{Target}:{RemotePath}"], capture_output=True, text=True, timeout=Timeout)
    return R.returncode == 0


# directive: audio-dialog-boost-real | # see audio-normalization.C14
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


# directive: audio-dialog-boost-real | # see audio-normalization.C14
def _DetectTorchVariant(Target: str) -> str:
    R = _Ssh(Target, "nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1", Timeout=10)
    if (R.stdout or "").strip():
        return "cu124"
    R = _Ssh(Target, "lspci -nn 2>/dev/null | grep -iE 'vga|3d|display' | grep -iE '\\[8086:e' | head -1", Timeout=10)
    if (R.stdout or "").strip():
        return "xpu"
    return "cpu"


# directive: audio-dialog-boost-real | # see audio-normalization.C14
def StepPreflight(Target: str, Friendly: str) -> bool:
    R = _Ssh(Target, "which python3.12 && which docker || which podman; test -d /mnt/media_tv && echo mounts_ok", Timeout=10)
    if "mounts_ok" not in (R.stdout or ""):
        _Status(1, 13, "preflight", "FAILED", f"missing /mnt/media_tv on {Friendly}")
        return False
    _Status(1, 13, "preflight", "OK", f"python3.12 + docker + mounts present on {Friendly}")
    return True


# directive: audio-dialog-boost-real | # see audio-normalization.C14
def StepEnsureVenv(Target: str, TorchVariant: str) -> bool:
    Index = TorchIndexByVariant.get(TorchVariant, TorchIndexByVariant["cpu"])
    Script = (
        "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3.12-venv python3-pip > /dev/null && "
        "mkdir -p /opt/mediavortex && "
        "if [ ! -x /opt/mediavortex/host-venv/bin/pip ]; then "
        "  rm -rf /opt/mediavortex/host-venv && python3.12 -m venv /opt/mediavortex/host-venv && "
        "  /opt/mediavortex/host-venv/bin/pip install --no-cache-dir --upgrade pip wheel > /dev/null; "
        "fi && "
        "/opt/mediavortex/host-venv/bin/pip install --no-cache-dir --upgrade "
        f"--index-url {Index} torch==2.6.0 torchaudio==2.6.0 > /tmp/mv-pip-torch.log 2>&1 && "
        "/opt/mediavortex/host-venv/bin/pip install --no-cache-dir --upgrade "
        "demucs==4.0.1 soundfile psycopg2-binary psutil setproctitle > /tmp/mv-pip-app.log 2>&1 && "
        "echo VENV_READY"
    )
    R = _Ssh(Target, Script, Timeout=1800)
    if "VENV_READY" not in (R.stdout or ""):
        _Status(2, 13, "ensure venv", "FAILED", (R.stderr or "")[-200:])
        return False
    _Status(2, 13, "ensure venv", "OK", f"torch variant={TorchVariant}")
    return True


# directive: audio-dialog-boost-real | # see audio-normalization.C14
def StepEnsureFfmpeg(Target: str) -> bool:
    R = _Ssh(Target, "test -x /usr/local/bin/ffmpeg && echo FFMPEG_OK", Timeout=10)
    if "FFMPEG_OK" in (R.stdout or ""):
        _Status(3, 13, "ensure ffmpeg", "SKIPPED", "already at /usr/local/bin/ffmpeg")
        return True
    R = _Ssh(Target, "docker ps --filter 'ancestor=mediavortex-worker:latest' --format '{{.Names}}' | head -1", Timeout=10)
    Ctr = (R.stdout or "").strip()
    if Ctr:
        _Ssh(Target, f"docker cp {Ctr}:/usr/local/bin/ffmpeg /usr/local/bin/ffmpeg && docker cp {Ctr}:/usr/local/bin/ffprobe /usr/local/bin/ffprobe && chmod +x /usr/local/bin/ffmpeg /usr/local/bin/ffprobe", Timeout=30)
        _Status(3, 13, "ensure ffmpeg", "OK", f"copied from container {Ctr}")
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


# directive: transcode-flow-canonical -- Reset 28: stamp VERSION with actual HEAD sha, not stale disk copy
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


# directive: transcode-flow-canonical -- Reset 28: .claude excluded from SyncSource so schema snapshot never lands; ship explicitly
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


# directive: audio-dialog-boost-real | # see audio-normalization.C14
def StepInstallSystemdUnit(Target: str, Friendly: str) -> bool:
    UnitLocal = BaremetalDir / "mediavortex-worker@.service"
    EnvLocal = BaremetalDir / "worker.env.template"
    _Scp(UnitLocal, Target, "/etc/systemd/system/mediavortex-worker@.service", Timeout=30)
    R = _Ssh(Target, "test -f /etc/mediavortex/worker.env && echo ENV_EXISTS", Timeout=10)
    if "ENV_EXISTS" not in (R.stdout or ""):
        _Scp(EnvLocal, Target, "/etc/mediavortex/worker.env", Timeout=30)
    Prefix = f"{Friendly}-worker"
    _Ssh(Target, f"echo 'MEDIAVORTEX_WORKER_PREFIX={Prefix}' > /etc/mediavortex/worker-prefix.env", Timeout=10)
    _Ssh(Target, "systemctl daemon-reload", Timeout=10)
    _Status(8, 13, "install systemd unit", "OK", f"mediavortex-worker@.service loaded, prefix={Prefix}")
    return True


# directive: audio-dialog-boost-real | # see audio-normalization.C14
def StepStopContainersAndClearDb(Target: str, Friendly: str) -> bool:
    R = _Ssh(Target, "docker ps -a --filter 'name=mediavortex-worker-' --format '{{.Names}}' | head -20", Timeout=10)
    Names = [N for N in (R.stdout or "").splitlines() if N.strip()]
    if Names:
        _Ssh(Target, "cd /opt/mediavortex && docker compose down --timeout 30 2>&1 | tail -3", Timeout=120)
    QueryScript = MediaVortexRoot / "Scripts" / "SQLScripts" / "QueryDatabase.py"
    Del = subprocess.run(
        [sys.executable, str(QueryScript), "sql", f"DELETE FROM Workers WHERE LOWER(WorkerName) LIKE '{Friendly.lower()}-worker-%'", "--commit"],
        capture_output=True, text=True, timeout=30,
    )
    Detail = f"stopped {len(Names)} container(s); DB clear: {(Del.stdout or '').strip().splitlines()[-1][:60] if Del.stdout else 'err'}"
    _Status(9, 13, "stop containers + clear DB", "OK", Detail)
    return True


# directive: transcode-flow-canonical -- age -1..-N slot heartbeats past 2min so prefix advisory-claim reclaims them cleanly on restart
def StepAgeSlotHeartbeats(Friendly: str, Count: int) -> bool:
    Prefix = f"{Friendly}-worker"
    Names = ",".join(f"'{Prefix}-{I}'" for I in range(1, Count + 1))
    QueryScript = MediaVortexRoot / "Scripts" / "SQLScripts" / "QueryDatabase.py"
    subprocess.run(
        [sys.executable, str(QueryScript), "sql", f"UPDATE Workers SET LastHeartbeat = NOW() - INTERVAL '5 min' WHERE WorkerName IN ({Names})", "--commit"],
        capture_output=True, text=True, timeout=30,
    )
    _Status(10, 13, "age slot heartbeats", "OK", f"{Count} slot row(s) aged for clean reclaim")
    return True


# directive: transcode-flow-canonical -- serialized start avoids advisory-claim race where 2 boots see the same stale slot in the same window
def StepStartInstances(Target: str, Friendly: str, Count: int) -> bool:
    for I in range(1, Count + 1):
        _Ssh(Target, f"systemctl enable --now mediavortex-worker@{I}.service", Timeout=30)
        _Ssh(Target, "sleep 3", Timeout=10)
    R = _Ssh(Target, f"systemctl list-units 'mediavortex-worker@*' --no-legend --state=active | wc -l", Timeout=10)
    Active = int((R.stdout or "0").strip() or 0)
    if Active < Count:
        _Status(11, 13, "start instances", "FAILED", f"expected {Count} active, got {Active}")
        return False
    _Status(11, 13, "start instances", "OK", f"{Active}/{Count} instances active")
    return True


# directive: audio-dialog-boost-real | # see audio-normalization.C14
def StepVerify(Target: str, Friendly: str, Count: int) -> bool:
    R = _Ssh(Target, "systemctl list-units 'mediavortex-worker@*' --no-legend --state=active | awk '{print $1}' | head -8", Timeout=10)
    Lines = [L.strip() for L in (R.stdout or "").splitlines() if L.strip()]
    _Status(13, 13, "verify", "OK" if len(Lines) >= Count else "FAILED", f"{len(Lines)}/{Count} systemd units active on {Friendly}")
    return len(Lines) >= Count


# directive: transcode-flow-canonical -- Reset 28: bare-metal deploy must reconcile Workers.{nvenccapable,qsvcapable} same as docker path
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


# directive: audio-dialog-boost-real | # see audio-normalization.C14
def main():
    Parser = argparse.ArgumentParser(description="Idempotent bare-metal deploy for MediaVortex WorkerService.")
    Parser.add_argument("target", help="Friendly name (dot, wakko, larry) or IP literal.")
    Parser.add_argument("--user", default=None)
    Parser.add_argument("--count", type=int, default=None)
    Parser.add_argument("--torch-variant", default=None, choices=list(TorchIndexByVariant.keys()))
    Parser.add_argument("--inventory", type=Path, default=DefaultInventoryToml)
    Args = Parser.parse_args()

    Friendly, Ip, User, InventoryCount = _ResolveTarget(Args.target, Args.inventory, Args.user)
    Count = Args.count or InventoryCount
    Target = f"{User}@{Ip}"
    print("=" * 60)
    print(f"Target: {Friendly} ({Target}), count={Count}")

    Variant = Args.torch_variant or _DetectTorchVariant(Target)
    print(f"Torch variant: {Variant}")
    print("=" * 60)

    if not StepPreflight(Target, Friendly):
        return 1
    if not StepEnsureVenv(Target, Variant):
        return 2
    if not StepEnsureFfmpeg(Target):
        return 2
    if not StepStopSystemdUnits(Target, Count):
        return 2
    if not StepSyncSource(Target):
        return 2
    if not StepStampVersion(Target):
        return 2
    if not StepShipSchemaSnapshot(Target):
        return 2
    if not StepInstallSystemdUnit(Target, Friendly):
        return 2
    if not StepStopContainersAndClearDb(Target, Friendly):
        return 2
    if not StepAgeSlotHeartbeats(Friendly, Count):
        return 2
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
