# directive: linux-nvenc-passthrough | # see linux-nvenc-passthrough.C5

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Core.Database.DatabaseService import DatabaseService, EscapeLikePattern


PROBE_ARGS = ['ffmpeg', '-hide_banner', '-h', 'encoder=av1_nvenc']
PROBE_TIMEOUT_SEC = 15


def _ListMediaVortexContainers(SshTarget):
    """Return mediavortex-worker container names on the target host via docker ps."""
    Result = subprocess.run(
        ['ssh', SshTarget, "docker ps --format '{{.Names}}'"],
        capture_output=True, text=True, timeout=30,
    )
    if Result.returncode != 0:
        raise RuntimeError(f'ssh+docker ps failed on {SshTarget}: {Result.stderr.strip()}')
    return [Line.strip() for Line in Result.stdout.splitlines() if Line.strip() and 'mediavortex' in Line.lower()]


def _ContainerHostname(SshTarget, Container):
    """Return the container's hostname (matches Workers.WorkerName)."""
    Result = subprocess.run(
        ['ssh', SshTarget, f'docker exec {Container} hostname'],
        capture_output=True, text=True, timeout=10,
    )
    return Result.stdout.strip() if Result.returncode == 0 else ''


def _ProbeNvencInContainer(SshTarget, Container):
    """Return True iff ffmpeg in the container can encode with av1_nvenc."""
    Cmd = ['ssh', SshTarget, 'docker', 'exec', Container] + PROBE_ARGS
    try:
        Result = subprocess.run(Cmd, capture_output=True, text=True, timeout=PROBE_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        return False
    Output = (Result.stdout or '') + (Result.stderr or '')
    return Result.returncode == 0 and 'av1_nvenc' in Output


def Main():
    """Probe each worker container on a Linux host and idempotently reconcile Workers.nvenccapable."""
    Parser = argparse.ArgumentParser(description='Reconcile Workers.nvenccapable via per-container ffmpeg probe.')
    Parser.add_argument('host', help='Friendly host (passed to ssh) e.g. root@dot or 10.0.0.193')
    Parser.add_argument('--ssh-user', default='root', help='Override ssh user when host is bare hostname/IP')
    Parser.add_argument('--dry-run', action='store_true', help='Print planned UPDATEs without executing')
    Parser.add_argument('--worker-prefix', default=None, help='Bare-metal fallback: WorkerName prefix (e.g. wakko-worker); required when no containers found and hostname does not match friendly name')
    Args = Parser.parse_args()

    SshTarget = Args.host if '@' in Args.host else f'{Args.ssh_user}@{Args.host}'
    print(f'Target: {SshTarget}')

    Containers = _ListMediaVortexContainers(SshTarget)
    Db = DatabaseService()
    Changes = 0
    if Containers:
        Probes = [(_ContainerHostname(SshTarget, C), _ProbeNvencInContainer(SshTarget, C)) for C in Containers]
    else:
        # directive: transcode-flow-canonical -- bare-metal (wakko): SSH+probe directly, apply to <hostprefix>-worker-*
        Probe = subprocess.run(['ssh', SshTarget] + PROBE_ARGS, capture_output=True, text=True, timeout=PROBE_TIMEOUT_SEC)
        Output = (Probe.stdout or '') + (Probe.stderr or '')
        Capable = Probe.returncode == 0 and 'av1_nvenc' in Output
        if Args.worker_prefix:
            Prefix = Args.worker_prefix
        else:
            HostR = subprocess.run(['ssh', SshTarget, 'hostname -s'], capture_output=True, text=True, timeout=10)
            Prefix = (HostR.stdout.strip().split('-')[0] + '-worker') if HostR.returncode == 0 and HostR.stdout.strip() else ''
            if not Prefix:
                print(f'Could not resolve hostname on {SshTarget}; nothing to reconcile.')
                return 0
        Rows = Db.ExecuteQuery(
            "SELECT WorkerName FROM Workers WHERE WorkerName LIKE %s ESCAPE '!'",
            (EscapeLikePattern(f'{Prefix}-') + '%',),
        ) or []
        if not Rows:
            print(f'No containers and no bare-metal workers matching {Prefix}-* found. Nothing to reconcile.')
            return 0
        Probes = [(R.get('WorkerName') or R.get('workername'), Capable) for R in Rows]
        print(f'  bare-metal probe on {SshTarget}: av1_nvenc={Capable}')

    for WorkerName, Capable in Probes:
        if not WorkerName:
            print('  <no worker name>: skipped.')
            continue
        StoredRows = Db.ExecuteQuery('SELECT nvenccapable FROM Workers WHERE WorkerName = %s', (WorkerName,))
        Stored = bool(StoredRows[0].get('nvenccapable')) if StoredRows else False
        if Stored == Capable:
            print(f'  {WorkerName}: probe={Capable}, stored={Stored} -- no change')
            continue
        if Args.dry_run:
            print(f'  {WorkerName}: probe={Capable}, stored={Stored} -- would UPDATE (dry-run)')
            Changes += 1
            continue
        Db.ExecuteNonQuery('UPDATE Workers SET nvenccapable = %s WHERE WorkerName = %s', (Capable, WorkerName))
        print(f'  {WorkerName}: probe={Capable}, stored={Stored} -- UPDATED to {Capable}')
        Changes += 1

    print(f'Done. {Changes} change(s) applied.' if not Args.dry_run else f'Done. {Changes} change(s) planned (dry-run).')
    return 0


if __name__ == '__main__':
    sys.exit(Main())
