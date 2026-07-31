# Probes ffmpeg av1_qsv presence via SSH; reconciles Workers.qsvcapable. Mirrors ReconcileNvencCapability.py.
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Core.Database.DatabaseService import DatabaseService, EscapeLikePattern


PROBE_ARGS = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i', 'color=black:s=320x240:d=0.2', '-c:v', 'av1_qsv', '-f', 'null', '-']
PROBE_TIMEOUT_SEC = 20


def _ProbeQsv(SshTarget):
    try:
        Result = subprocess.run(['ssh', SshTarget] + PROBE_ARGS, capture_output=True, text=True, timeout=PROBE_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        return False
    Stderr = Result.stderr or ''
    return Result.returncode == 0 and 'error' not in Stderr.lower() and 'Nothing was written' not in Stderr


def Main():
    Parser = argparse.ArgumentParser(description='Reconcile Workers.qsvcapable via SSH ffmpeg probe on bare-metal Linux hosts.')
    Parser.add_argument('host', help='Friendly host (passed to ssh) e.g. root@wakko or 10.0.0.230')
    Parser.add_argument('--ssh-user', default='root', help='Override ssh user when host is bare hostname/IP')
    Parser.add_argument('--dry-run', action='store_true', help='Print planned UPDATEs without executing')
    Parser.add_argument('--worker-prefix', default=None, help='WorkerName prefix (e.g. wakko-worker); required when hostname does not match friendly name')
    Args = Parser.parse_args()

    SshTarget = Args.host if '@' in Args.host else f'{Args.ssh_user}@{Args.host}'
    print(f'Target: {SshTarget}')

    Capable = _ProbeQsv(SshTarget)
    print(f'  probe on {SshTarget}: av1_qsv={Capable}')

    if Args.worker_prefix:
        Prefix = Args.worker_prefix
    else:
        HostR = subprocess.run(['ssh', SshTarget, 'hostname -s'], capture_output=True, text=True, timeout=10)
        Prefix = (HostR.stdout.strip().split('-')[0] + '-worker') if HostR.returncode == 0 and HostR.stdout.strip() else ''
        if not Prefix:
            print(f'Could not resolve hostname on {SshTarget}; nothing to reconcile.')
            return 0

    Db = DatabaseService()
    Rows = Db.ExecuteQuery(
        "SELECT WorkerName FROM Workers WHERE WorkerName LIKE %s ESCAPE '!'",
        (EscapeLikePattern(f'{Prefix}-') + '%',),
    ) or []
    if not Rows:
        print(f'No workers matching {Prefix}-* found. Nothing to reconcile.')
        return 0

    Changes = 0
    for R in Rows:
        WorkerName = R.get('WorkerName') or R.get('workername')
        if not WorkerName:
            continue
        StoredRows = Db.ExecuteQuery('SELECT qsvcapable FROM Workers WHERE WorkerName = %s', (WorkerName,))
        Stored = bool(StoredRows[0].get('qsvcapable')) if StoredRows else False
        if Stored == Capable:
            print(f'  {WorkerName}: probe={Capable}, stored={Stored} -- no change')
            continue
        if Args.dry_run:
            print(f'  {WorkerName}: probe={Capable}, stored={Stored} -- would UPDATE (dry-run)')
            Changes += 1
            continue
        Db.ExecuteNonQuery('UPDATE Workers SET qsvcapable = %s WHERE WorkerName = %s', (Capable, WorkerName))
        print(f'  {WorkerName}: probe={Capable}, stored={Stored} -- UPDATED to {Capable}')
        Changes += 1

    print(f'Done. {Changes} change(s) applied.' if not Args.dry_run else f'Done. {Changes} change(s) planned (dry-run).')
    return 0


if __name__ == '__main__':
    sys.exit(Main())
