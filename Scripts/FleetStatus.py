import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from Core.Database.DatabaseService import DatabaseService, EscapeLikePattern

SSH_OPTS = ['-o', 'ConnectTimeout=4', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=accept-new']

HOSTS = [
    ('I9-2024', None, 'windows', 'NVENC + Intel iGPU'),
    ('wakko',   '10.0.0.230', 'linux',   'Intel Arc B580 (QSV)'),
    ('dot',     '10.0.0.193', 'linux',   'NVIDIA RTX 4060 (NVENC)'),
]


def _RunSsh(Ip, Cmd, Timeout=10):
    try:
        R = subprocess.run(['ssh', *SSH_OPTS, f'root@{Ip}', Cmd], capture_output=True, text=True, timeout=Timeout)
        return (R.stdout or R.stderr or '').strip()
    except subprocess.TimeoutExpired:
        return '<ssh-timeout>'
    except Exception as Ex:
        return f'<ssh-err:{Ex}>'


def _RunLocal(Cmd, Timeout=10):
    try:
        R = subprocess.run(['powershell', '-NoProfile', '-Command', Cmd], capture_output=True, text=True, timeout=Timeout)
        return (R.stdout or R.stderr or '').strip()
    except Exception as Ex:
        return f'<local-err:{Ex}>'


def _WorkersForHost(Db, Prefix):
    if Prefix == 'I9-2024':
        Where, Params = "workername = %s", ('I9-2024',)
    else:
        Pat = EscapeLikePattern(f'{Prefix}-worker-') + '%'
        Where, Params = "workername LIKE %s ESCAPE '!'", (Pat,)
    return Db.ExecuteQuery(
        "SELECT workername, status, LEFT(version,7) AS ver, transcodeenabled, nvenccapable, qsvcapable, "
        "EXTRACT(EPOCH FROM (NOW()-lastheartbeat))::int AS hb "
        f"FROM Workers WHERE {Where} ORDER BY workername", Params)


def _InFlightForWorkers(Db, WorkerNames):
    if not WorkerNames:
        return []
    NamesSql = ', '.join(f"'{N}'" for N in WorkerNames)
    return Db.ExecuteQuery(
        f"SELECT ta.id, ta.workername, ta.mediafileid, tp.currentphase, tp.progresspercent, "
        f"EXTRACT(EPOCH FROM (NOW()-ta.attemptdate))::int AS age_s, "
        f"EXTRACT(EPOCH FROM (NOW()-tp.lastprogressupdate))::int AS since_upd_s "
        f"FROM TranscodeAttempts ta LEFT JOIN TranscodeProgress tp ON tp.transcodeattemptid=ta.id "
        f"WHERE ta.success IS NULL AND ta.workername IN ({NamesSql}) "
        f"ORDER BY ta.id DESC", ())


def _RecentCompletions(Db, WorkerNames, WindowMin=15):
    if not WorkerNames:
        return {'ok': 0, 'fail': 0, 'replaced': 0}
    NamesSql = ', '.join(f"'{N}'" for N in WorkerNames)
    R = Db.ExecuteQuery(
        f"SELECT SUM(CASE WHEN success=TRUE THEN 1 ELSE 0 END) AS ok, "
        f"SUM(CASE WHEN success=FALSE THEN 1 ELSE 0 END) AS fail, "
        f"SUM(CASE WHEN filereplaced=TRUE THEN 1 ELSE 0 END) AS replaced "
        f"FROM TranscodeAttempts WHERE workername IN ({NamesSql}) "
        f"AND attemptdate > NOW() - INTERVAL '{WindowMin} minutes'", ())
    Row = R[0] if R else {}
    return {'ok': int(Row.get('ok') or 0), 'fail': int(Row.get('fail') or 0), 'replaced': int(Row.get('replaced') or 0)}


def _LinuxProcInfo(Ip):
    Cmd = (
        "echo '::procs::'; ps -eo pid,etime,pcpu,rss,cmd --no-headers "
        "| awk '/ffmpeg|WorkerService|DemucsDaemon/ && !/awk/' | sort -k2 -r | head -12; "
        "echo '::gpu::'; nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader 2>/dev/null | head -1; "
        "echo '::gpu-procs::'; nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader 2>/dev/null | head -6"
    )
    return _RunSsh(Ip, Cmd, Timeout=8)


def _WindowsProcInfo():
    Ps = (
        "Get-CimInstance Win32_Process -Filter \"Name='ffmpeg.exe' OR Name='python.exe'\" | "
        "Where-Object { $_.CommandLine -match 'MediaVortex|ffmpeg' } | "
        "Select-Object ProcessId,@{n='ElapsedSec';e={[int]((Get-Date)-$_.CreationDate).TotalSeconds}}, "
        "@{n='RssMB';e={[int]($_.WorkingSetSize/1MB)}},Name,@{n='Cmd';e={ if ($_.CommandLine.Length -gt 90) {$_.CommandLine.Substring(0,90)} else {$_.CommandLine} }} | "
        "Sort-Object ElapsedSec -Descending | Select-Object -First 12 | Format-Table -AutoSize | Out-String -Width 200; "
        "Write-Output '::gpu::'; "
        "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader 2>$null | Select-Object -First 1; "
        "Write-Output '::gpu-procs::'; "
        "nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader 2>$null | Select-String -Pattern 'ffmpeg|python' | Select-Object -First 6"
    )
    return _RunLocal(Ps, Timeout=15)


def _PrintHostBlock(Friendly, Ip, Kind, HwLabel, WorkerRows, InFlight, Recent, ProcInfo):
    Print = lambda S='': print(S, flush=True)
    Header = f'== {Friendly} ({Kind}, {HwLabel}) '
    Print(Header + '=' * max(0, 78 - len(Header)))
    if not WorkerRows:
        Print('  (no worker rows)')
    else:
        for W in WorkerRows:
            Caps = f"nvenc={'T' if W['nvenccapable'] else 'F'} qsv={'T' if W['qsvcapable'] else 'F'} tx={'T' if W['transcodeenabled'] else 'F'}"
            Print(f"  {W['workername']:<18} {W['status']:<7} v={W['ver']} hb={W['hb']}s  [{Caps}]")
    Print(f"  Recent(15min): ok={Recent['ok']} fail={Recent['fail']} replaced={Recent['replaced']}")
    if InFlight:
        for A in InFlight:
            Phase = A.get('currentphase') or '?'
            Pct = A.get('progresspercent')
            PctStr = f"{Pct:.0f}%" if Pct is not None else '-'
            Since = A.get('since_upd_s')
            SinceStr = f"upd={Since}s" if Since is not None else 'upd=-'
            Print(f"  IN-FLIGHT  attempt={A['id']} worker={A['workername']:<16} mfid={A['mediafileid']} phase={Phase:<16} {PctStr:<5} age={A['age_s']}s {SinceStr}")
    else:
        Print("  IN-FLIGHT  (none)")
    Print("  ---- host processes ----")
    for L in (ProcInfo or '').splitlines():
        Print(f"    {L}")


def Main():
    Db = DatabaseService()
    print(f"\n============ FLEET STATUS @ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ============\n", flush=True)
    for Friendly, Ip, Kind, HwLabel in HOSTS:
        WorkerRows = _WorkersForHost(Db, Friendly)
        Names = [W['workername'] for W in WorkerRows]
        InFlight = _InFlightForWorkers(Db, Names)
        Recent = _RecentCompletions(Db, Names)
        if Kind == 'windows':
            ProcInfo = _WindowsProcInfo()
        else:
            ProcInfo = _LinuxProcInfo(Ip)
        _PrintHostBlock(Friendly, Ip, Kind, HwLabel, WorkerRows, InFlight, Recent, ProcInfo)
        print(flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(Main())
