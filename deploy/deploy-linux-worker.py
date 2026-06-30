"""End-to-end deploy automation for a Linux MediaVortex worker fleet.

Wraps the four-step sequence in deploy/worker-deploy-linux.flow.md
"Build and Deploy" into one idempotent invocation. Run from the dev
workstation against any Linux host (LXC or bare-metal) that has Docker
installed and the required NFS mounts.

WHEN TO USE THIS SCRIPT:
  - Fresh host bring-up.
  - Code-only redeploys (FFmpeg build layer is cached, ~30-60s).
  - Compose-template changes (new cpuset, hostname tweaks).
  - After a host rebuild.

For mid-job avoidance: workers receive SIGTERM during `docker compose up -d`
and the SignalHandler resets in-flight TranscodeQueue rows to Pending. If
you want zero re-transcoding, drain workers first:
  py Scripts/SQLScripts/QueryDatabase.py sql \\
    "UPDATE Workers SET Status='Paused' WHERE WorkerName LIKE '<friendly>-worker-%'"

Steps:
  1. Resolve target via infrastructure/terraform/inventory.toml (or IP literal)
  2. Pre-flight checks (SSH, Docker, DB reachable, mounts non-empty, compose template exists)
  3. Sync source tree via deploy/SyncSource.py (tar-over-ssh + .deployignore)
  4. docker build on the target (with --build-arg COMMIT_SHA)
  5. Push deploy/compose-templates/<friendly>.yml -> /opt/mediavortex/docker-compose.yml
  6. docker compose up -d
  7. Clean up build source
  8. Poll Workers rows until Status='Online' with fresh heartbeat (or fail at 90s)

Idempotent: re-running completes only what changed and reports each step
as OK / SKIPPED accordingly.

Usage:
  py deploy/deploy-linux-worker.py wakko
  py deploy/deploy-linux-worker.py dot
  py deploy/deploy-linux-worker.py 10.0.0.193           # IP literal
  py deploy/deploy-linux-worker.py wakko --check        # pre-flight only
  py deploy/deploy-linux-worker.py wakko --skip-build   # source already on host
  py deploy/deploy-linux-worker.py wakko --user root    # override ssh_user

Exit codes:
  0  success (verified Online with fresh heartbeat)
  1  pre-flight check failed (host unreachable, missing prereqs)
  2  deploy step failed (sync / build / compose up)
  3  verification failed (workers not Online within 90s, or stale heartbeat)
"""

from __future__ import annotations

import argparse
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
    """Return (Friendly, Ip, SshUser).

    TargetArg may be:
      - A friendly compose-template basename (e.g. 'larry', 'wakko') -- mapped
        first against the optional `compose_template` field, then against `name`.
        The returned Friendly is always TargetArg so the caller picks
        `compose-templates/<TargetArg>.yml` deterministically.
      - An inventory entry `name` (e.g. 'mediavortex-workers'). Friendly is
        that name unless the entry declares `compose_template`, in which case
        Friendly becomes the compose_template value.
      - An IPv4 literal. The script reverse-looks-up the inventory by primary
        IP. If no entry matches, Friendly = the IP (caller still needs a
        matching compose template).

    The script honors the inventory schema's backward-compat clause: if an
    entry has no `nics` array, the top-level `ip` field is used as the
    primary IP (see infrastructure/terraform/inventory-schema.md line 186).
    """
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
            f"Copy from a sibling (larry.yml/wakko.yml) and adjust "
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


# directive: audio-dialog-boost-real | # see audio-normalization.C14
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

    Total = 1 if Args.check else 8
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
    if Args.skip_sync:
        _Status(2, Total, "sync source", "SKIPPED", "--skip-sync")
    else:
        if not StepSyncSource(Target):
            _Status(2, Total, "sync source", "FAILED")
            return 2
        _Status(2, Total, "sync source", "OK")

    if Args.skip_build:
        _Status(3, Total, "docker build", "SKIPPED", "--skip-build")
    else:
        if not StepDockerBuild(Target, Sha):
            _Status(3, Total, "docker build", "FAILED")
            return 2
        _Status(3, Total, "docker build", "OK")

    if not StepPushCompose(Target, Friendly):
        _Status(4, Total, "push compose", "FAILED")
        return 2
    _Status(4, Total, "push compose", "OK",
            f"compose-templates/{Friendly}.yml -> /opt/mediavortex/docker-compose.yml")

    if not StepComposeUp(Target):
        _Status(5, Total, "docker compose up", "FAILED")
        return 2
    _Status(5, Total, "docker compose up", "OK")

    # directive: worker-runtime-state
    NvOk, NvDetail = StepNvencProbe(Target, Friendly)
    if NvOk:
        _Status(6, Total, "nvenc probe", "OK", NvDetail)
    else:
        _Status(6, Total, "nvenc probe", "FAILED", NvDetail)
        return 2

    if not StepCleanupBuild(Target):
        _Status(7, Total, "cleanup build", "FAILED",
                "non-fatal; /tmp/mediavortex-build may persist")
    else:
        _Status(7, Total, "cleanup build", "OK")

    print("\nVerify:")
    Ok, Summary = StepVerifyWorkers(Friendly, Sha)
    if Ok:
        _Status(8, Total, "workers online", "OK", Summary)
        return 0
    _Status(8, Total, "workers online", "FAILED", Summary)
    return 3


if __name__ == "__main__":
    sys.exit(Main())
