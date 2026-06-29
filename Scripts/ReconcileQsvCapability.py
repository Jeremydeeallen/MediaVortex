# Probes per-container ffmpeg av1_qsv presence; reconciles Workers.qsvcapable. Mirrors ReconcileNvencCapability.py.
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Core.Database.DatabaseService import DatabaseService


PROBE_ARGS = ['ffmpeg', '-hide_banner', '-h', 'encoder=av1_qsv']
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


def _ProbeQsvInContainer(SshTarget, Container):
    """Return True iff ffmpeg in the container exposes av1_qsv encoder."""
    Cmd = ['ssh', SshTarget, 'docker', 'exec', Container] + PROBE_ARGS
    try:
        Result = subprocess.run(Cmd, capture_output=True, text=True, timeout=PROBE_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        return False
    Output = (Result.stdout or '') + (Result.stderr or '')
    return Result.returncode == 0 and 'av1_qsv' in Output


def Main():
    """Probe each worker container on a Linux host and idempotently reconcile Workers.qsvcapable."""
    Parser = argparse.ArgumentParser(description='Reconcile Workers.qsvcapable via per-container ffmpeg probe.')
    Parser.add_argument('host', help='Friendly host (passed to ssh) e.g. root@wakko or 10.0.0.230')
    Parser.add_argument('--ssh-user', default='root', help='Override ssh user when host is bare hostname/IP')
    Parser.add_argument('--dry-run', action='store_true', help='Print planned UPDATEs without executing')
    Args = Parser.parse_args()

    SshTarget = Args.host if '@' in Args.host else f'{Args.ssh_user}@{Args.host}'
    print(f'Target: {SshTarget}')

    Containers = _ListMediaVortexContainers(SshTarget)
    if not Containers:
        print('No mediavortex-worker containers running on this host. Nothing to reconcile.')
        return 0

    Db = DatabaseService()
    Changes = 0
    for Container in Containers:
        WorkerName = _ContainerHostname(SshTarget, Container)
        if not WorkerName:
            print(f'  {Container}: could not read hostname; skipping.')
            continue
        Capable = _ProbeQsvInContainer(SshTarget, Container)
        StoredRows = Db.ExecuteQuery(
            'SELECT qsvcapable FROM Workers WHERE WorkerName = %s', (WorkerName,)
        )
        Stored = bool(StoredRows[0].get('qsvcapable')) if StoredRows else False
        if Stored == Capable:
            print(f'  {WorkerName}: probe={Capable}, stored={Stored} -- no change')
            continue
        if Args.dry_run:
            print(f'  {WorkerName}: probe={Capable}, stored={Stored} -- would UPDATE (dry-run)')
            Changes += 1
            continue
        Db.ExecuteNonQuery(
            'UPDATE Workers SET qsvcapable = %s WHERE WorkerName = %s', (Capable, WorkerName)
        )
        print(f'  {WorkerName}: probe={Capable}, stored={Stored} -- UPDATED to {Capable}')
        Changes += 1

    print(f'Done. {Changes} change(s) applied.' if not Args.dry_run else f'Done. {Changes} change(s) planned (dry-run).')
    return 0


if __name__ == '__main__':
    sys.exit(Main())
