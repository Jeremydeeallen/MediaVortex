# see worker-deploy-linux.flow.md -- Docker on Linux (LXC, bare-metal server). Bare-metal Linux hosts (Intel Arc / Xe) use deploy-baremetal-worker.py.

from __future__ import annotations

import argparse
import base64
import re
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from typing import Optional


MediaVortexRoot = Path(__file__).resolve().parent.parent
DeployDir = MediaVortexRoot / "deploy"
ComposeTemplatesDir = DeployDir / "compose-templates"

DefaultInventoryToml = Path(r"C:\Code\infrastructure\terraform\inventory.toml")

SshOpts = ["-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
           "-o", "StrictHostKeyChecking=accept-new"]

VerificationTimeoutSec = 90
VerificationPollSec = 5
HeartbeatStaleThresholdSec = 60

IpRegex = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")


def _Status(Step: int, Total: int, Title: str, Result: str = "...",
            Detail: str = "") -> None:
    Tag = {
        "OK":      "[OK]   ",
        "SKIPPED": "[SKIP] ",
        "FAILED":  "[FAIL] ",
        "...":     "[..]   ",
    }.get(Result, f"[{Result}] ")
    Suffix = f" -- {Detail}" if Detail else ""
    print(f"  {Tag}({Step}/{Total}) {Title}{Suffix}", flush=True)


def _SshTarget(User: str, Ip: str) -> str:
    return f"{User}@{Ip}"


def _RunSsh(Target: str, RemoteCmd: str, *, Timeout: int = 30,
            CaptureOutput: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ssh", *SshOpts, Target, RemoteCmd],
        capture_output=CaptureOutput, text=True, timeout=Timeout,
    )


def _ResolveTarget(TargetArg: str, InventoryToml: Path, UserOverride: Optional[str]) -> tuple[str, str, str]:
    # see worker-deploy.C1 -- resolve friendly-name / inventory-name / IP to (Friendly, Ip, SshUser).
    UseIp = bool(IpRegex.match(TargetArg))

    if not InventoryToml.exists():
        if UseIp:
            return TargetArg, TargetArg, (UserOverride or "root")
        raise FileNotFoundError(
            f"inventory.toml not found at {InventoryToml}; pass an IP literal "
            f"or set the path via --inventory."
        )

    with open(InventoryToml, "rb") as F:
        Data = tomllib.load(F)

    Services = Data.get("services", [])

    def _PrimaryIp(Entry: dict) -> Optional[str]:
        """Honor schema backward-compat: prefer `nics[role=primary].ip`,
        fall back to top-level `ip`."""
        Nics = Entry.get("nics", [])
        if Nics:
            Primary = next(
                (N for N in Nics if N.get("role") == "primary"),
                Nics[0],
            )
            Ip = Primary.get("ip")
            if Ip:
                return Ip
        return Entry.get("ip") or None

    if UseIp:
        Match = next(
            (S for S in Services if _PrimaryIp(S) == TargetArg),
            None,
        )
        if Match:
            return (
                Match.get("compose_template") or Match["name"],
                TargetArg,
                UserOverride or Match.get("ssh_user", "root"),
            )
        return TargetArg, TargetArg, (UserOverride or "root")

    # Friendly-name lookup. Prefer `compose_template` match (lets a CT named
    # `mediavortex-workers` answer to `larry` because its compose template is
    # `compose-templates/larry.yml`), then fall back to `name` match.
    Match = next(
        (S for S in Services if S.get("compose_template") == TargetArg),
        None,
    )
    if Match is None:
        Match = next(
            (S for S in Services if S.get("name") == TargetArg),
            None,
        )
    if not Match:
        raise ValueError(
            f"No inventory.toml entry with name={TargetArg!r} or "
            f"compose_template={TargetArg!r}. Pass an IP literal or add the "
            f"host to inventory.toml."
        )
    Ip = _PrimaryIp(Match)
    if not Ip:
        raise ValueError(
            f"Inventory entry {Match['name']!r} has no primary IP "
            f"(checked `nics[role=primary].ip` and top-level `ip`)."
        )
    Friendly = Match.get("compose_template") or TargetArg
    return Friendly, Ip, (UserOverride or Match.get("ssh_user", "root"))


def StepPreflight(Friendly: str, Target: str) -> tuple[bool, dict]:
    """Probe the target. Returns (ok, results_dict_for_diagnostics)."""
    Out: dict = {}

    ComposeTemplate = ComposeTemplatesDir / f"{Friendly}.yml"
    Out["compose_template"] = ComposeTemplate.exists()
    if not Out["compose_template"]:
        Out["_error"] = (
            f"Compose template missing: {ComposeTemplate}. "
            f"Copy from a sibling (larry.yml) and adjust "
            f"hostnames and cpuset."
        )
        return False, Out

    Probe = (
        'echo "HOSTNAME=$(hostname)"; '
        'echo "DOCKER=$(docker --version 2>&1 || echo NONE)"; '
        'echo "DB_REACHABLE=$(nc -zw2 10.0.0.15 5432 >/dev/null 2>&1 && echo YES || echo NO)"; '
        'for d in /mnt/media_tv /mnt/movies /mnt/xxx; do '
        '  if [ -d "$d" ] && [ "$(ls -A "$d" 2>/dev/null | head -1)" != "" ]; then '
        '    echo "MOUNT_$(basename $d)=OK"; '
        '  else '
        '    echo "MOUNT_$(basename $d)=EMPTY_OR_MISSING"; '
        '  fi; '
        'done'
    )
    R = _RunSsh(Target, Probe, Timeout=15)
    if R.returncode != 0:
        Out["_error"] = f"SSH probe failed: {(R.stderr or R.stdout).strip()[:300]}"
        return False, Out

    for Line in R.stdout.strip().splitlines():
        if "=" in Line:
            K, _, V = Line.partition("=")
            Out[K.strip().lower()] = V.strip()

    Required = ["hostname", "docker", "db_reachable",
                "mount_media_tv", "mount_movies", "mount_xxx"]
    Problems = []
    if Out.get("docker", "NONE") == "NONE":
        Problems.append("Docker not installed on target; install Docker CE.")
    if Out.get("db_reachable") != "YES":
        Problems.append("DB unreachable at 10.0.0.15:5432; check pg_hba.conf and routing.")
    for K in ["mount_media_tv", "mount_movies", "mount_xxx"]:
        if Out.get(K) != "OK":
            Problems.append(f"{K.replace('mount_', '/mnt/')} is empty or missing -- fix the NFS mount.")

    if Problems:
        Out["_error"] = " | ".join(Problems)
        return False, Out

    return True, Out


# see worker-deploy-linux.ST1.5 -- deploy owns disk hygiene per worker-deploy.C4a
_MIN_FREE_BYTES_AFTER_PRUNE = 5 * 1024 * 1024 * 1024  # 5 GB build workspace floor
_BUILD_CACHE_KEEP = "3g"


def StepDiskHygiene(Target: str) -> tuple[bool, str]:
    """Prune docker cache the deploy itself created, then verify enough free space to build."""
    PruneBuilder = _RunSsh(Target, f"docker builder prune --keep-storage {_BUILD_CACHE_KEEP} -f 2>&1 | tail -3", Timeout=180)
    if PruneBuilder.returncode != 0:
        return False, f"docker builder prune failed: {(PruneBuilder.stderr or PruneBuilder.stdout).strip()[:300]}"
    BuilderTail = (PruneBuilder.stdout or '').strip().splitlines()[-1] if PruneBuilder.stdout else 'no output'

    PruneImages = _RunSsh(Target, "docker image prune -f 2>&1 | tail -1", Timeout=60)
    if PruneImages.returncode != 0:
        return False, f"docker image prune failed: {(PruneImages.stderr or PruneImages.stdout).strip()[:300]}"
    ImagesTail = (PruneImages.stdout or '').strip().splitlines()[-1] if PruneImages.stdout else 'no output'

    Df = _RunSsh(Target, "df -B1 / | tail -1 | awk '{print $4}'", Timeout=15)
    if Df.returncode != 0:
        return False, f"df probe failed: {(Df.stderr or Df.stdout).strip()[:200]}"
    try:
        FreeBytes = int((Df.stdout or '0').strip())
    except ValueError:
        return False, f"df output not parseable: {(Df.stdout or '').strip()[:200]!r}"
    FreeGb = FreeBytes / (1024 ** 3)
    if FreeBytes < _MIN_FREE_BYTES_AFTER_PRUNE:
        return False, (
            f"free space {FreeGb:.2f} GB below required {_MIN_FREE_BYTES_AFTER_PRUNE / (1024**3):.0f} GB after prune. "
            f"Non-docker artifacts filled the disk -- check `du -sh /var/lib/*` and `/tmp` on {Target}."
        )
    return True, f"builder-prune: {BuilderTail} | image-prune: {ImagesTail} | free={FreeGb:.2f} GB"


def StepSyncSource(Target: str) -> bool:
    SyncSource = DeployDir / "SyncSource.py"
    if not SyncSource.exists():
        print(f"    SyncSource.py missing at {SyncSource}")
        return False
    R = subprocess.run(
        [sys.executable, str(SyncSource), Target, "/tmp/mediavortex-build"],
        capture_output=False, text=True, timeout=900,
    )
    return R.returncode == 0


def _ResolveLocalHeadSha() -> str:
    """Return the dev workstation's git HEAD, or empty string on any failure."""
    try:
        R = subprocess.run(
            ["git", "-C", str(MediaVortexRoot), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if R.returncode == 0:
            return R.stdout.strip()
    except Exception:
        pass
    return ""


# directive: worker-runtime-state
def _LoadFfmpegPin() -> tuple[str, str]:
    PinFile = DeployDir / "ffmpeg-release.txt"
    if not PinFile.exists():
        raise SystemExit(f"deploy/ffmpeg-release.txt missing -- create it with TAG= and ASSET= lines")
    Tag, Asset = "", ""
    for Line in PinFile.read_text(encoding='utf-8').splitlines():
        L = Line.strip()
        if L.startswith('TAG='):
            Tag = L.split('=', 1)[1].strip()
        elif L.startswith('ASSET='):
            Asset = L.split('=', 1)[1].strip()
    if not Tag or not Asset:
        raise SystemExit(f"deploy/ffmpeg-release.txt must contain both TAG=<release-tag> and ASSET=<filename> lines")
    return Tag, Asset


# directive: transcode-flow-canonical | # see worker-deploy.C1
def _DetectTorchVariant(Target: str) -> str:
    R = _RunSsh(Target, "nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1", Timeout=10)
    Out = (R.stdout or '').strip()
    if Out:
        return "cu124"
    return "cpu"


# directive: audio-dialog-boost-real | # see audio-normalization.C14
def StepDockerBuild(Target: str, Sha: str) -> bool:
    FfmpegTag, FfmpegAsset = _LoadFfmpegPin()
    TorchVariant = _DetectTorchVariant(Target)
    BuildArgs = [f"--build-arg FFMPEG_TAG={FfmpegTag}", f"--build-arg FFMPEG_ASSET={FfmpegAsset}", f"--build-arg TORCH_VARIANT={TorchVariant}"]
    if Sha:
        BuildArgs.append(f"--build-arg COMMIT_SHA={Sha}")
    print(f"  [..]   build args: TORCH_VARIANT={TorchVariant}", flush=True)
    Cmd = (
        f"docker build {' '.join(BuildArgs)} "
        f"-t mediavortex-worker:latest "
        f"-f /tmp/mediavortex-build/deploy/Dockerfile "
        f"/tmp/mediavortex-build/"
    )
    R = _RunSsh(Target, Cmd, Timeout=1800, CaptureOutput=False)
    return R.returncode == 0


# directive: worker-runtime-state
def StepNvencProbe(Target: str, Friendly: str) -> tuple[bool, str]:
    NvidiaCheck = _RunSsh(Target, "nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null || echo NO_NVIDIA", Timeout=10)
    Out = (NvidiaCheck.stdout or '').strip()
    if 'NO_NVIDIA' in Out or NvidiaCheck.returncode != 0 or not Out:
        return (True, f"no Nvidia GPU on {Friendly}; av1_nvenc probe skipped")
    Driver = Out.split('\n')[0].strip()
    Container = f"mediavortex-worker-1-1"
    ProbeCmd = (
        f"docker exec {Container} ffmpeg -hide_banner -loglevel error "
        f"-f lavfi -i testsrc=duration=1:size=320x240:rate=30 -pix_fmt yuv420p "
        f"-c:v av1_nvenc -t 1 -f null - 2>&1"
    )
    R = _RunSsh(Target, ProbeCmd, Timeout=30)
    if R.returncode == 0:
        return (True, f"av1_nvenc initialized cleanly on {Friendly} (driver {Driver})")
    Stderr = ((R.stdout or '') + (R.stderr or '')).strip()[:400]
    return (False, f"av1_nvenc FAILED on {Friendly} (driver {Driver}). Upgrade host driver OR pick an older BtbN tag in deploy/ffmpeg-release.txt. stderr: {Stderr}")


STALE_PYC_PROBE_SCRIPT = (
    "import sys\n"
    "from pathlib import Path\n"
    "root = Path(sys.argv[1] if len(sys.argv) > 1 else '/opt/mediavortex')\n"
    "stale = []\n"
    "for pyc in root.rglob('__pycache__/*.pyc'):\n"
    "    stem = pyc.name.split('.', 1)[0]\n"
    "    src = pyc.parent.parent / (stem + '.py')\n"
    "    try:\n"
    "        src_m = src.stat().st_mtime\n"
    "    except FileNotFoundError:\n"
    "        continue\n"
    "    if pyc.stat().st_mtime + 1 < src_m:\n"
    "        stale.append(str(pyc))\n"
    "if stale:\n"
    "    print('STALE_PYC_COUNT=' + str(len(stale)))\n"
    "    for p in stale[:5]:\n"
    "        print('STALE=' + p)\n"
    "    sys.exit(2)\n"
    "print('STALE_PYC_COUNT=0')\n"
)


# directive: transcode-flow-canonical
def StepReconcileCapabilities(Target: str, Friendly: str) -> tuple[bool, str]:
    """Probe each running container for av1_nvenc + av1_qsv; reconcile Workers.{nvenccapable,qsvcapable} (BUG-0087 durable fix)."""
    ScriptsDir = Path(__file__).resolve().parent.parent / "Scripts"
    NvR = subprocess.run(
        [sys.executable, str(ScriptsDir / "ReconcileNvencCapability.py"), Target],
        capture_output=True, text=True, timeout=180,
    )
    if NvR.returncode != 0:
        return False, f"nvenc reconcile failed: {(NvR.stderr or NvR.stdout).strip()[:300]}"
    QsvR = subprocess.run(
        [sys.executable, str(ScriptsDir / "ReconcileQsvCapability.py"), Target],
        capture_output=True, text=True, timeout=180,
    )
    if QsvR.returncode != 0:
        return False, f"qsv reconcile failed: {(QsvR.stderr or QsvR.stdout).strip()[:300]}"
    NvTail = (NvR.stdout or '').strip().splitlines()[-1] if NvR.stdout else ''
    QsvTail = (QsvR.stdout or '').strip().splitlines()[-1] if QsvR.stdout else ''
    return True, f"nvenc: {NvTail} | qsv: {QsvTail}"


# directive: transcode-flow-canonical
def StepStalePycProbe(Target: str, Friendly: str) -> tuple[bool, str]:
    """Assert no .pyc predates its source .py inside any running worker container (BUG-0085)."""
    R = _RunSsh(Target, "docker ps --filter 'name=mediavortex-worker-' --format '{{.Names}}'", Timeout=15)
    if R.returncode != 0:
        return False, f"docker ps failed: {(R.stderr or R.stdout).strip()[:200]}"
    Containers = [L.strip() for L in (R.stdout or '').splitlines() if L.strip()]
    if not Containers:
        return False, f"no running mediavortex-worker-N containers on {Friendly}"
    Encoded = base64.b64encode(STALE_PYC_PROBE_SCRIPT.encode('utf-8')).decode('ascii')
    Findings: list[str] = []
    for C in Containers:
        Cmd = f"docker exec {C} sh -c 'echo {Encoded} | base64 -d | python3 -'"
        Rp = _RunSsh(Target, Cmd, Timeout=60)
        Output = ((Rp.stdout or '') + (Rp.stderr or '')).strip()
        if Rp.returncode != 0:
            Findings.append(f"{C}: {Output[:400]}")
    if Findings:
        Head = Findings[0]
        if len(Findings) > 1:
            return False, f"stale-pyc detected: {Head} (+ {len(Findings) - 1} more)"
        return False, f"stale-pyc detected: {Head}"
    return True, f"clean across {len(Containers)} container(s)"


def StepPushCompose(Target: str, Friendly: str) -> bool:
    """Ensure /opt/mediavortex exists, then scp the per-host compose file."""
    R = _RunSsh(Target, "mkdir -p /opt/mediavortex", Timeout=15)
    if R.returncode != 0:
        print(f"    mkdir /opt/mediavortex failed: {(R.stderr or R.stdout).strip()[:200]}")
        return False

    Template = ComposeTemplatesDir / f"{Friendly}.yml"
    R = subprocess.run(
        ["scp", *SshOpts, str(Template),
         f"{Target}:/opt/mediavortex/docker-compose.yml"],
        capture_output=True, text=True, timeout=30,
    )
    if R.returncode != 0:
        print(f"    scp compose failed: {(R.stderr or R.stdout).strip()[:200]}")
        return False
    return True


def StepComposeUp(Target: str) -> bool:
    Cmd = "cd /opt/mediavortex && docker compose up -d"
    R = _RunSsh(Target, Cmd, Timeout=180, CaptureOutput=False)
    return R.returncode == 0


def StepCleanupBuild(Target: str) -> bool:
    R = _RunSsh(Target, "rm -rf /tmp/mediavortex-build", Timeout=30)
    return R.returncode == 0


def StepVerifyWorkers(Friendly: str, ExpectedSha: str) -> tuple[bool, str]:
    """Poll Workers rows until all <friendly>-worker-N are healthy on the expected version.

    A worker is healthily deployed when:
      - row exists, FFmpegPath resolved
      - Status IN ('Online','Paused')   (Paused is preserved by UPSERT for previously-paused rows)
      - heartbeat fresh
      - no mount-validation error
      - Workers.Version equals the SHA baked into the image at build time
    """
    QueryDb = MediaVortexRoot / "Scripts" / "SQLScripts" / "QueryDatabase.py"
    if not QueryDb.exists():
        return False, f"QueryDatabase.py missing at {QueryDb}"

    Sql = (
        f"SELECT WorkerName, Status, FFmpegPath, Version, "
        f"EXTRACT(EPOCH FROM (NOW() - LastHeartbeat))::int AS heartbeat_age_sec, "
        f"MountValidationError "
        f"FROM Workers "
        f"WHERE WorkerName LIKE '{Friendly}-worker-%' "
        f"ORDER BY WorkerName"
    )

    Deadline = time.time() + VerificationTimeoutSec
    LastSummary = "no rows yet"
    while time.time() < Deadline:
        R = subprocess.run(
            [sys.executable, str(QueryDb), "sql", Sql],
            capture_output=True, text=True, timeout=15,
        )
        if R.returncode != 0:
            LastSummary = (R.stderr or R.stdout).strip()[:200]
            time.sleep(VerificationPollSec)
            continue

        Rows = _ParseQueryRows(R.stdout)
        if not Rows:
            LastSummary = f"no Workers rows matching {Friendly}-worker-%"
            time.sleep(VerificationPollSec)
            continue

        SteadyStates = ("Online", "Paused")
        Unhealthy = [r for r in Rows if r.get("status") not in SteadyStates]
        Stale = [r for r in Rows if int(r.get("heartbeat_age_sec") or 9999) > HeartbeatStaleThresholdSec]
        NullFfmpeg = [r for r in Rows if not r.get("ffmpegpath")]
        MountErrors = [r for r in Rows if r.get("mountvalidationerror")]
        WrongVersion = [r for r in Rows if (r.get("version") or "") != ExpectedSha] if ExpectedSha else []

        if not Unhealthy and not Stale and not NullFfmpeg and not MountErrors and not WrongVersion:
            Lines = [
                f"{r['workername']}: {r['status']}, FFmpeg={r['ffmpegpath']}, "
                f"heartbeat={r.get('heartbeat_age_sec')}s, version={(r.get('version') or '?')[:7]}"
                for r in Rows
            ]
            PausedCount = sum(1 for r in Rows if r.get("status") == "Paused")
            Footer = ""
            if PausedCount:
                Footer = (
                    f" -- {PausedCount} worker(s) Paused (expected on redeploy "
                    f"against rows that were previously paused). Flip to Online "
                    f"via Activity UI or `UPDATE Workers SET Status='Online' "
                    f"WHERE WorkerName LIKE '{Friendly}-worker-%'`"
                )
            return True, "; ".join(Lines) + Footer

        if MountErrors:
            Errs = "; ".join(
                f"{r['workername']}: {r['mountvalidationerror']}"
                for r in MountErrors
            )
            LastSummary = f"mount validation failed: {Errs}"
        elif NullFfmpeg:
            LastSummary = "Workers with NULL FFmpegPath -- check Dockerfile FFmpeg layer"
        elif Unhealthy:
            States = ", ".join(f"{r['workername']}={r.get('status')}" for r in Unhealthy)
            LastSummary = f"unexpected status (expected Online or Paused): {States}"
        elif Stale:
            States = ", ".join(f"{r['workername']}={r.get('heartbeat_age_sec')}s" for r in Stale)
            LastSummary = f"stale heartbeat: {States}"
        elif WrongVersion:
            States = ", ".join(
                f"{r['workername']}={(r.get('version') or 'NULL')[:7]}"
                for r in WrongVersion
            )
            LastSummary = (
                f"version mismatch: stamped {ExpectedSha[:7]} but workers report {States} "
                f"(containers likely not recreated -- re-run with no --skip flags)"
            )

        time.sleep(VerificationPollSec)

    return False, (
        f"verification timed out after {VerificationTimeoutSec}s; last state: {LastSummary}"
        f" -- see deploy/worker-deploy-linux.flow.md Troubleshooting for the matching symptom"
    )


def _ParseQueryRows(Stdout: str) -> list[dict]:
    """Parse the ASCII-table output of Scripts/SQLScripts/QueryDatabase.py."""
    Lines = [L for L in Stdout.splitlines() if L.strip()]
    HeaderIdx = next(
        (I for I, L in enumerate(Lines) if "|" in L and "workername" in L.lower()),
        None,
    )
    if HeaderIdx is None:
        return []
    HeaderCells = [C.strip().lower() for C in Lines[HeaderIdx].split("|")]
    if HeaderIdx + 1 >= len(Lines):
        return []
    Rows = []
    for L in Lines[HeaderIdx + 2:]:
        if "|" not in L or set(L.strip()) <= {"-", "+", " "}:
            continue
        Cells = [C.strip() for C in L.split("|")]
        if len(Cells) != len(HeaderCells):
            continue
        # QueryDatabase.py renders PostgreSQL NULL as the literal "None";
        # convert back to Python None so truthiness checks work as expected.
        Row = {
            K: (None if V == "None" else V)
            for K, V in zip(HeaderCells, Cells)
        }
        Rows.append(Row)
    return Rows


def Main(Argv: Optional[list] = None) -> int:
    Parser = argparse.ArgumentParser(
        description="Deploy a MediaVortex worker fleet to a Linux host.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    Parser.add_argument("target", help="Friendly name from inventory.toml or IP literal.")
    Parser.add_argument("--user", dest="UserOverride", default=None,
                        help="Override the ssh_user from inventory.toml.")
    Parser.add_argument("--inventory", default=str(DefaultInventoryToml),
                        help=f"Path to inventory.toml (default: {DefaultInventoryToml}).")
    Parser.add_argument("--check", action="store_true",
                        help="Run pre-flight checks only; do not deploy.")
    Parser.add_argument("--skip-sync", action="store_true",
                        help="Assume source is already on target at /tmp/mediavortex-build.")
    Parser.add_argument("--skip-build", action="store_true",
                        help="Skip docker build (image already present).")
    Args = Parser.parse_args(Argv)

    try:
        Friendly, Ip, User = _ResolveTarget(
            Args.target, Path(Args.inventory), Args.UserOverride,
        )
    except (FileNotFoundError, ValueError) as Exc:
        print(f"[FAIL] target resolution: {Exc}", file=sys.stderr)
        return 1

    Target = _SshTarget(User, Ip)
    Sha = _ResolveLocalHeadSha()
    print(f"Target: {Friendly} ({Target})")
    print(f"Compose template: deploy/compose-templates/{Friendly}.yml")
    print(f"Stamping image with COMMIT_SHA={Sha[:7] if Sha else '(unresolved)'}")
    print()

    if not Sha and not Args.check:
        print("[FAIL] dev workstation `git rev-parse HEAD` did not resolve. "
              "Deploy refuses to stamp an unknown version.", file=sys.stderr)
        return 2

    Total = 1 if Args.check else 11
    print("Pre-flight:")
    Ok, Diag = StepPreflight(Friendly, Target)
    if not Ok:
        _Status(1, Total, "preflight", "FAILED", Diag.get("_error", "see diagnostics"))
        for K, V in Diag.items():
            if K != "_error":
                print(f"    {K} = {V}")
        return 1
    _Status(1, Total, "preflight", "OK",
            f"hostname={Diag.get('hostname')}, docker present, db reachable, mounts non-empty")

    if Args.check:
        print("\nPre-flight only -- not deploying.")
        return 0

    print("\nDeploy:")
    HygOk, HygDetail = StepDiskHygiene(Target)
    if not HygOk:
        _Status(2, Total, "disk hygiene", "FAILED", HygDetail)
        return 2
    _Status(2, Total, "disk hygiene", "OK", HygDetail)

    if Args.skip_sync:
        _Status(3, Total, "sync source", "SKIPPED", "--skip-sync")
    else:
        if not StepSyncSource(Target):
            _Status(3, Total, "sync source", "FAILED")
            return 2
        _Status(3, Total, "sync source", "OK")

    if Args.skip_build:
        _Status(4, Total, "docker build", "SKIPPED", "--skip-build")
    else:
        if not StepDockerBuild(Target, Sha):
            _Status(4, Total, "docker build", "FAILED")
            return 2
        _Status(4, Total, "docker build", "OK")

    if not StepPushCompose(Target, Friendly):
        _Status(5, Total, "push compose", "FAILED")
        return 2
    _Status(5, Total, "push compose", "OK",
            f"compose-templates/{Friendly}.yml -> /opt/mediavortex/docker-compose.yml")

    if not StepComposeUp(Target):
        _Status(6, Total, "docker compose up", "FAILED")
        return 2
    _Status(6, Total, "docker compose up", "OK")

    # directive: worker-runtime-state
    NvOk, NvDetail = StepNvencProbe(Target, Friendly)
    if NvOk:
        _Status(7, Total, "nvenc probe", "OK", NvDetail)
    else:
        _Status(7, Total, "nvenc probe", "FAILED", NvDetail)
        return 2

    StaleOk, StaleDetail = StepStalePycProbe(Target, Friendly)
    if StaleOk:
        _Status(8, Total, "stale-pyc probe", "OK", StaleDetail)
    else:
        _Status(8, Total, "stale-pyc probe", "FAILED", StaleDetail)
        return 2

    CapOk, CapDetail = StepReconcileCapabilities(Target, Friendly)
    if CapOk:
        _Status(9, Total, "capability reconcile", "OK", CapDetail)
    else:
        _Status(9, Total, "capability reconcile", "FAILED", CapDetail)
        return 2

    if not StepCleanupBuild(Target):
        _Status(10, Total, "cleanup build", "FAILED",
                "non-fatal; /tmp/mediavortex-build may persist")
    else:
        _Status(10, Total, "cleanup build", "OK")

    print("\nVerify:")
    Ok, Summary = StepVerifyWorkers(Friendly, Sha)
    if Ok:
        _Status(11, Total, "workers online", "OK", Summary)
        return 0
    _Status(11, Total, "workers online", "FAILED", Summary)
    return 3


if __name__ == "__main__":
    sys.exit(Main())
