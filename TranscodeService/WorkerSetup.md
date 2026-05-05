# TranscodeService Worker Setup

How to add a new transcoding worker to MediaVortex. Each worker runs the same `TranscodeService/Main.py` and connects directly to the shared PostgreSQL database. Workers claim jobs atomically -- no coordinator needed.

## Prerequisites

- Network access to the PostgreSQL database (default: `10.0.0.15:5432`)
- Network access to the media share (same files the WebService scans)
- Python 3.11+ with pip
- FFmpeg installed (with libsvtav1 support for AV1 encoding)

---

## Windows Worker Setup

### 1. Clone the repo

```powershell
git clone <repo-url> C:\Code\Automation\MediaVortex
cd C:\Code\Automation\MediaVortex
```

### 2. Create venv and install dependencies

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r TranscodeService/requirements.txt
```

### 3. Mount the media share

Map the network share to the same drive letter used by the primary machine (default: `T:\`). If using a different letter, you'll configure that in the Workers table.

```powershell
net use T: \\server\media /persistent:yes
```

### 4. Set environment variables

```powershell
# User-level env vars (persist across reboots)
[Environment]::SetEnvironmentVariable("MEDIAVORTEX_DB_HOST", "10.0.0.15", "User")
[Environment]::SetEnvironmentVariable("MEDIAVORTEX_DB_PORT", "5432", "User")
[Environment]::SetEnvironmentVariable("MEDIAVORTEX_DB_NAME", "mediavortex", "User")
[Environment]::SetEnvironmentVariable("MEDIAVORTEX_DB_USER", "mediavortex", "User")
[Environment]::SetEnvironmentVariable("MEDIAVORTEX_DB_PASSWORD", "mediavortex", "User")
```

### 5. Run the migration (first time only)

```powershell
python Scripts\SQLScripts\AddDistributedColumns.py
```

### 6. Register the worker in the database

```powershell
python Scripts\SQLScripts\QueryDatabase.py sql "INSERT INTO Workers (WorkerName, Platform, FFmpegPath, StagingDirectory, ShareMountPrefix, ShareCanonicalPrefix, MaxConcurrentJobs) VALUES ('<HOSTNAME>', 'windows', 'C:\Path\To\ffmpeg.exe', 'T:\MediaVortex\Staging\', 'T:\', 'T:\', 1) ON CONFLICT (WorkerName) DO UPDATE SET FFmpegPath = EXCLUDED.FFmpegPath, StagingDirectory = EXCLUDED.StagingDirectory, ShareMountPrefix = EXCLUDED.ShareMountPrefix, MaxConcurrentJobs = EXCLUDED.MaxConcurrentJobs"
```

Replace `<HOSTNAME>` with the machine's hostname (run `hostname` to check). Replace paths as appropriate.

**Column reference:**

| Column | Purpose | Example |
|--------|---------|---------|
| WorkerName | `socket.gethostname()` -- must match exactly | `DESKTOP-ABC123` |
| Platform | `windows` or `linux` | `windows` |
| FFmpegPath | Absolute path to ffmpeg binary | `C:\ffmpeg\bin\ffmpeg.exe` |
| StagingDirectory | Where transcoded output files are written | `T:\MediaVortex\Staging\` |
| ShareMountPrefix | How the media share appears on this machine | `T:\` |
| ShareCanonicalPrefix | How the share appears in the DB (primary machine) | `T:\` |
| MaxConcurrentJobs | How many parallel FFmpeg jobs (1-5) | `1` |

### 7. Create the staging directory

```powershell
mkdir T:\MediaVortex\Staging
```

### 8. Start the service

```powershell
python TranscodeService\Main.py
```

The service will:
- Auto-register with hostname in the Workers table
- Load its config (FFmpegPath, StagingDirectory, etc.)
- Start claiming and processing jobs from the queue
- Send heartbeats every 30 seconds

---

## Linux Worker Setup

### 1. Clone the repo

```bash
git clone <repo-url> /opt/mediavortex
cd /opt/mediavortex
```

### 2. Create venv and install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r TranscodeService/requirements.txt
```

### 3. Mount the media share

Add to `/etc/fstab` for persistent mount:

```
//server/media  /mnt/media  cifs  credentials=/root/.smbcredentials,uid=1000,gid=1000,iocharset=utf8  0  0
```

Or mount manually:

```bash
sudo mkdir -p /mnt/media
sudo mount -t cifs //server/media /mnt/media -o credentials=/root/.smbcredentials,uid=1000,gid=1000
```

### 4. Install FFmpeg

```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# Or build from source for latest SVT-AV1 support
# See: https://trac.ffmpeg.org/wiki/CompilationGuide/Ubuntu
```

Verify SVT-AV1 support:

```bash
ffmpeg -encoders | grep svtav1
# Should show: V..... libsvtav1
```

### 5. Set environment variables

Add to `/etc/environment` or create `/opt/mediavortex/.env` sourced by your service manager:

```bash
export MEDIAVORTEX_DB_HOST=10.0.0.15
export MEDIAVORTEX_DB_PORT=5432
export MEDIAVORTEX_DB_NAME=mediavortex
export MEDIAVORTEX_DB_USER=mediavortex
export MEDIAVORTEX_DB_PASSWORD=mediavortex
```

### 6. Run the migration (first time only)

```bash
python3 Scripts/SQLScripts/AddDistributedColumns.py
```

### 7. Register the worker in the database

```bash
python3 Scripts/SQLScripts/QueryDatabase.py sql "INSERT INTO Workers (WorkerName, Platform, FFmpegPath, StagingDirectory, ShareMountPrefix, ShareCanonicalPrefix, MaxConcurrentJobs) VALUES ('$(hostname)', 'linux', '/usr/bin/ffmpeg', '/mnt/media/MediaVortex/Staging/', '/mnt/media/', 'T:\', 1) ON CONFLICT (WorkerName) DO UPDATE SET FFmpegPath = EXCLUDED.FFmpegPath, StagingDirectory = EXCLUDED.StagingDirectory, ShareMountPrefix = EXCLUDED.ShareMountPrefix, MaxConcurrentJobs = EXCLUDED.MaxConcurrentJobs"
```

**Key difference from Windows:** Linux workers need path translation because the DB stores Windows drive letters (T:\, M:\, Z:\) but Linux mounts the same shares at different paths.

### 8. Configure share mappings (multi-share workers)

If the DB has files on multiple drive letters (e.g. T:\, M:\, Z:\), each backed by a different network share, you need a mapping row per share in `WorkerShareMappings`:

```bash
python3 Scripts/SQLScripts/QueryDatabase.py sql "INSERT INTO WorkerShareMappings (WorkerName, CanonicalPrefix, LocalMountPrefix) VALUES
    ('$(hostname)', 'T:\', '/mnt/media_tv/'),
    ('$(hostname)', 'M:\', '/mnt/movies/'),
    ('$(hostname)', 'Z:\', '/mnt/xxx/')
ON CONFLICT (WorkerName, CanonicalPrefix) DO UPDATE SET LocalMountPrefix = EXCLUDED.LocalMountPrefix"
```

Adjust the LocalMountPrefix values to match your actual mount points. Each CanonicalPrefix is the Windows drive letter as stored in the DB. The PathTranslationService uses these mappings to convert DB paths to local paths and back.

To check which drive letters are in use:

```bash
python3 Scripts/SQLScripts/QueryDatabase.py sql "SELECT DISTINCT LEFT(filepath, 3) AS drive, COUNT(*) AS cnt FROM mediafiles GROUP BY LEFT(filepath, 3)"
```

**Single-share workers:** If you only need one share (all DB files are on T:\), you can either use WorkerShareMappings with one row, or set ShareMountPrefix/ShareCanonicalPrefix on the Workers row directly (legacy approach).

### 9. Create the staging directory

The staging directory should be on a network share so the WebService can access output files for VMAF and file replacement.

```bash
sudo mkdir -p /mnt/media_tv/MediaVortex/Staging
sudo chown $(whoami) /mnt/media_tv/MediaVortex/Staging
```

### 10. Start the service

```bash
python3 TranscodeService/Main.py
```

### 11. (Optional) Create a systemd service

For a dedicated container (no venv), point ExecStart at the system python3:

```ini
# /etc/systemd/system/mediavortex-transcode.service
[Unit]
Description=MediaVortex TranscodeService
After=network-online.target remote-fs.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/mediavortex
Environment=MEDIAVORTEX_DB_HOST=10.0.0.15
Environment=MEDIAVORTEX_DB_PORT=5432
Environment=MEDIAVORTEX_DB_NAME=mediavortex
Environment=MEDIAVORTEX_DB_USER=mediavortex
Environment=MEDIAVORTEX_DB_PASSWORD=mediavortex
ExecStart=/usr/bin/python3 TranscodeService/Main.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

If using a venv, change ExecStart to `/opt/mediavortex/venv/bin/python TranscodeService/Main.py`.

```bash
sudo systemctl daemon-reload
sudo systemctl enable mediavortex-transcode
sudo systemctl start mediavortex-transcode
```

---

## Verification

After starting the worker, verify it's registered and healthy:

```bash
python Scripts/SQLScripts/QueryDatabase.py workers --columns "WorkerName, Platform, Status, LastHeartbeat, MaxConcurrentJobs"
```

Expected output shows your worker with Status=Online and a recent LastHeartbeat.

### Test job claiming

1. Queue a file via the web UI
2. Watch the worker log -- it should claim and start processing the job
3. Verify in the DB: `python Scripts/SQLScripts/QueryDatabase.py sql "SELECT Id, FileName, Status, ClaimedBy FROM TranscodeQueue WHERE Status = 'Running'"`

The `ClaimedBy` column should show your worker's hostname.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Worker starts but never claims jobs | Workers table not configured or hostname mismatch | Check `hostname` matches WorkerName in DB |
| FFmpeg command fails | Wrong FFmpegPath in Workers table | Update the row: `UPDATE Workers SET FFmpegPath = '/correct/path' WHERE WorkerName = '...'` |
| Output file not found after transcode | StagingDirectory doesn't exist or wrong path | Create the directory, verify write permissions |
| "connection refused" on startup | DB not reachable from this machine | Check firewall, verify `pg_hba.conf` allows connections from worker IP |
| Files not accessible | Share not mounted or wrong mount prefix | Verify mount with `ls /mnt/media/` (Linux) or `dir T:\` (Windows) |
| "file not found" but worker claims job | Missing share mapping for that drive letter | Check `WorkerShareMappings` has a row for each drive letter in the DB. Run the drive letter query in step 8 to find all in use. |
| Worker shows as Offline in stuck detection | Heartbeat not updating | Check if service crashed, look at logs |

---

## Architecture Notes

- Workers talk directly to PostgreSQL -- no REST intermediary needed
- Job claiming uses `SELECT FOR UPDATE SKIP LOCKED` -- multiple workers never claim the same job
- Heartbeat (30-second interval) enables remote stuck-job detection
- Path translation is automatic based on WorkerShareMappings (multi-share) or ShareMountPrefix/ShareCanonicalPrefix (single-share)
- StagingDirectory should be ON the network share so VMAF and file replacement can access output files from any machine
