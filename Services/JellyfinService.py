import re
import json
from typing import Dict, Any, List, Optional
from Services.LoggingService import LoggingService

try:
    import paramiko
    PARAMIKO_AVAILABLE = True
except ImportError:
    PARAMIKO_AVAILABLE = False


class JellyfinService:
    """Service for connecting to Jellyfin server via SSH and REST API."""

    JELLYFIN_LOG_DIR = "/var/log/jellyfin"
    JELLYFIN_DB_PATH = "/var/lib/jellyfin/data/jellyfin.db"

    # Log filename patterns: FFmpeg.DirectStream-*, FFmpeg.Transcode-*, FFmpeg.Remux-*
    OP_TYPES = {
        "DirectStream": "FFmpeg.DirectStream-",
        "Transcode": "FFmpeg.Transcode-",
        "Remux": "FFmpeg.Remux-"
    }

    def __init__(self, Host: str = "", SSHPort: int = 22, SSHUser: str = "root",
                 SSHKeyPath: str = "", ApiKey: str = "", ApiPort: int = 8096):
        self.Host = Host
        self.SSHPort = SSHPort
        self.SSHUser = SSHUser
        self.SSHKeyPath = SSHKeyPath
        self.ApiKey = ApiKey
        self.ApiPort = ApiPort

    def TestConnection(self) -> Dict[str, Any]:
        """Test SSH connection to Jellyfin server."""
        try:
            if not PARAMIKO_AVAILABLE:
                return {"Success": False, "ErrorMessage": "paramiko is not installed. Run: pip install paramiko"}
            if not self.Host:
                return {"Success": False, "ErrorMessage": "Jellyfin host is not configured"}

            client = self._GetSSHClient()
            try:
                stdin, stdout, stderr = client.exec_command("echo ok")
                result = stdout.read().decode().strip()
                if result == "ok":
                    return {"Success": True, "Message": f"SSH connection to {self.Host} successful"}
                else:
                    return {"Success": False, "ErrorMessage": f"Unexpected response: {result}"}
            finally:
                client.close()
        except Exception as e:
            LoggingService.LogException("Error testing Jellyfin connection", e, "JellyfinService", "TestConnection")
            return {"Success": False, "ErrorMessage": str(e)}

    def GetFFmpegOperationCounts(self) -> Dict[str, Any]:
        """Get counts of FFmpeg operations from Jellyfin log filenames."""
        try:
            if not PARAMIKO_AVAILABLE:
                return {"Success": False, "ErrorMessage": "paramiko is not installed"}

            client = self._GetSSHClient()
            try:
                cmd = f"ls -1 {self.JELLYFIN_LOG_DIR}/ 2>/dev/null"
                stdin, stdout, stderr = client.exec_command(cmd)
                files = [f.strip() for f in stdout.read().decode().strip().split('\n') if f.strip()]

                counts = {}
                for opName, prefix in self.OP_TYPES.items():
                    counts[opName] = sum(1 for f in files if f.startswith(prefix))

                return {
                    "Success": True,
                    "DirectStream": counts.get("DirectStream", 0),
                    "Transcode": counts.get("Transcode", 0),
                    "Remux": counts.get("Remux", 0),
                    "Total": sum(counts.values())
                }
            finally:
                client.close()
        except Exception as e:
            LoggingService.LogException("Error getting FFmpeg operation counts", e, "JellyfinService", "GetFFmpegOperationCounts")
            return {"Success": False, "ErrorMessage": str(e)}

    def GetOperationDetails(self, OperationType: str, Limit: int = 100) -> Dict[str, Any]:
        """Get details for a specific operation type by parsing log files.

        Each Jellyfin FFmpeg log has:
          Line 1: JSON with media info (Path, Name, MediaStreams, Container, etc.)
          Line 2: The FFmpeg command
        """
        try:
            if not PARAMIKO_AVAILABLE:
                return {"Success": False, "ErrorMessage": "paramiko is not installed"}

            prefix = self.OP_TYPES.get(OperationType)
            if not prefix:
                return {"Success": False, "ErrorMessage": f"Unknown operation type: {OperationType}"}

            client = self._GetSSHClient()
            try:
                # Get log files sorted by most recent first
                cmd = f"ls -1t {self.JELLYFIN_LOG_DIR}/{prefix}*.log 2>/dev/null | head -{Limit}"
                stdin, stdout, stderr = client.exec_command(cmd)
                logFiles = [f.strip() for f in stdout.read().decode().strip().split('\n') if f.strip()]

                if not logFiles:
                    return {"Success": True, "Files": [], "Count": 0, "OperationType": OperationType,
                            "TotalLogs": 0, "OldestDate": None, "NewestDate": None}

                # Extract date range from log filenames
                # Format: FFmpeg.Transcode-2026-01-15_14-30-00_hash_hash.log
                dates = []
                for lf in logFiles:
                    basename = lf.split('/')[-1]
                    match = re.search(r'-(\d{4}-\d{2}-\d{2})_', basename)
                    if match:
                        dates.append(match.group(1))
                oldestDate = min(dates) if dates else None
                newestDate = max(dates) if dates else None

                # Parse each log file's first 3 lines (line 1: JSON media info, line 2: blank, line 3: FFmpeg command)
                fileList = "' '".join(logFiles)
                cmd = f"for f in '{fileList}'; do head -3 \"$f\" 2>/dev/null; echo '|||SEPARATOR|||'; done"
                stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
                output = stdout.read().decode()

                chunks = output.split('|||SEPARATOR|||')
                fileDetails = {}  # Deduplicate by file path

                for i, chunk in enumerate(chunks):
                    chunk = chunk.strip()
                    if not chunk:
                        continue

                    # Split into lines: line 1 = JSON, line 2 = blank, line 3 = FFmpeg command
                    logLines = chunk.split('\n')
                    jsonLine = logLines[0].strip()
                    ffmpegCmd = ""
                    for line in logLines[1:]:
                        stripped = line.strip()
                        if stripped and stripped.startswith('/'):
                            ffmpegCmd = stripped
                            break

                    info = self._ParseLogJson(jsonLine)
                    if not info:
                        continue

                    filePath = info.get("Path", "")
                    fileName = info.get("Name", filePath.split('/')[-1] if filePath else "unknown")

                    reason = ""
                    if OperationType == "Transcode":
                        reason = self._ClassifyTranscodeReason(info, ffmpegCmd)

                    key = filePath or fileName
                    if key not in fileDetails:
                        fileDetails[key] = {
                            "FileName": fileName,
                            "FilePath": filePath,
                            "Container": info.get("Container", ""),
                            "VideoCodec": info.get("VideoCodec", ""),
                            "AudioCodec": info.get("AudioCodec", ""),
                            "Resolution": info.get("Resolution", ""),
                            "Reason": reason,
                            "Count": 1,
                            "LogFile": logFiles[i].split('/')[-1] if i < len(logFiles) else ""
                        }
                    else:
                        fileDetails[key]["Count"] += 1

                # Sort by count descending (most frequent first)
                sortedFiles = sorted(fileDetails.values(), key=lambda x: x["Count"], reverse=True)

                # Aggregate reasons for transcode
                reasons = {}
                if OperationType == "Transcode":
                    for f in sortedFiles:
                        r = f.get("Reason", "other")
                        reasons[r] = reasons.get(r, 0) + f["Count"]

                return {
                    "Success": True,
                    "Files": sortedFiles,
                    "Count": len(sortedFiles),
                    "TotalLogs": len(logFiles),
                    "OperationType": OperationType,
                    "Reasons": reasons,
                    "OldestDate": oldestDate,
                    "NewestDate": newestDate
                }
            finally:
                client.close()
        except Exception as e:
            LoggingService.LogException("Error getting operation details", e, "JellyfinService", "GetOperationDetails")
            return {"Success": False, "ErrorMessage": str(e)}

    def GetRecentTranscodeLogs(self, Limit: int = 50) -> Dict[str, Any]:
        """Parse recent transcode logs to identify transcode reasons."""
        result = self.GetOperationDetails("Transcode", Limit)
        if not result.get("Success"):
            return result
        return {
            "Success": True,
            "Reasons": result.get("Reasons", {}),
            "Details": result.get("Files", [])[:20],
            "TotalAnalyzed": result.get("TotalLogs", 0)
        }

    def GetPlaybackActivity(self, Days: int = 30) -> Dict[str, Any]:
        """Query Jellyfin DB for recent playback activity via SSH."""
        try:
            if not PARAMIKO_AVAILABLE:
                return {"Success": False, "ErrorMessage": "paramiko is not installed"}

            client = self._GetSSHClient()
            try:
                cmd = (
                    f"sqlite3 -json {self.JELLYFIN_DB_PATH} "
                    f"\"SELECT Name, Type, COUNT(*) as Count FROM ActivityLogs "
                    f"WHERE DateCreated >= NOW() - INTERVAL '{Days} days' "
                    f"GROUP BY Name, Type ORDER BY Count DESC LIMIT 50\""
                )
                stdin, stdout, stderr = client.exec_command(cmd)
                output = stdout.read().decode().strip()
                error = stderr.read().decode().strip()

                if error:
                    return {"Success": False, "ErrorMessage": error}

                try:
                    activities = json.loads(output) if output else []
                except json.JSONDecodeError:
                    activities = []

                return {"Success": True, "Activities": activities, "Days": Days}
            finally:
                client.close()
        except Exception as e:
            LoggingService.LogException("Error getting playback activity", e, "JellyfinService", "GetPlaybackActivity")
            return {"Success": False, "ErrorMessage": str(e)}

    def GetServerInfo(self) -> Dict[str, Any]:
        """Get Jellyfin server info via REST API."""
        try:
            if not self.Host:
                return {"Success": False, "ErrorMessage": "Jellyfin host is not configured"}

            import requests
            url = f"http://{self.Host}:{self.ApiPort}/System/Info/Public"
            response = requests.get(url, timeout=5)

            if response.status_code == 200:
                data = response.json()
                return {
                    "Success": True,
                    "ServerName": data.get("ServerName", ""),
                    "Version": data.get("Version", ""),
                    "OperatingSystem": data.get("OperatingSystem", ""),
                    "Id": data.get("Id", "")
                }
            else:
                return {"Success": False, "ErrorMessage": f"HTTP {response.status_code}"}
        except Exception as e:
            LoggingService.LogException("Error getting server info", e, "JellyfinService", "GetServerInfo")
            return {"Success": False, "ErrorMessage": str(e)}

    def GetActiveSessions(self) -> Dict[str, Any]:
        """Get active playback sessions via REST API."""
        try:
            if not self.Host or not self.ApiKey:
                return {"Success": False, "ErrorMessage": "Jellyfin host or API key not configured"}

            import requests
            url = f"http://{self.Host}:{self.ApiPort}/Sessions"
            headers = {"X-Emby-Token": self.ApiKey}
            response = requests.get(url, headers=headers, timeout=5)

            if response.status_code == 200:
                sessions = response.json()
                activeSessions = []
                for s in sessions:
                    nowPlaying = s.get("NowPlayingItem")
                    if nowPlaying:
                        activeSessions.append({
                            "DeviceName": s.get("DeviceName", ""),
                            "Client": s.get("Client", ""),
                            "NowPlaying": nowPlaying.get("Name", ""),
                            "PlayMethod": s.get("PlayState", {}).get("PlayMethod", "")
                        })
                return {"Success": True, "Sessions": activeSessions, "TotalSessions": len(sessions)}
            else:
                return {"Success": False, "ErrorMessage": f"HTTP {response.status_code}"}
        except Exception as e:
            LoggingService.LogException("Error getting active sessions", e, "JellyfinService", "GetActiveSessions")
            return {"Success": False, "ErrorMessage": str(e)}

    def GetRegisteredDevices(self) -> Dict[str, Any]:
        """Get all registered devices from Jellyfin via REST API."""
        try:
            if not self.Host or not self.ApiKey:
                return {"Success": False, "ErrorMessage": "Jellyfin host or API key not configured"}

            import requests
            url = f"http://{self.Host}:{self.ApiPort}/Devices"
            headers = {"X-Emby-Token": self.ApiKey}
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                items = data.get("Items", data) if isinstance(data, dict) else data
                devices = []
                for d in items:
                    devices.append({
                        "Id": d.get("Id", ""),
                        "Name": d.get("Name", ""),
                        "AppName": d.get("AppName", ""),
                        "AppVersion": d.get("AppVersion", ""),
                        "LastUserName": d.get("LastUserName", ""),
                        "DateLastActivity": d.get("DateLastActivity", ""),
                    })
                return {"Success": True, "Devices": devices}
            else:
                return {"Success": False, "ErrorMessage": f"HTTP {response.status_code}"}
        except Exception as e:
            LoggingService.LogException("Error getting registered devices", e, "JellyfinService", "GetRegisteredDevices")
            return {"Success": False, "ErrorMessage": str(e)}

    def GetDevicePlaybackSummary(self) -> Dict[str, Any]:
        """Query Jellyfin DB via SSH for playback activity grouped by device.
        Correlates ActivityLog entries with device names to show per-device transcode patterns."""
        try:
            if not PARAMIKO_AVAILABLE:
                return {"Success": False, "ErrorMessage": "paramiko is not installed"}

            client = self._GetSSHClient()
            try:
                # Query ActivityLog for playback events with device/item info
                # Jellyfin ActivityLog: Id, Name, Overview, ShortOverview, Type, ItemId, DateCreated, UserId, Severity, LogSeverity
                # Also check if there are any tables with device-playback correlation
                cmd = (
                    f"sqlite3 -json {self.JELLYFIN_DB_PATH} "
                    f"\"SELECT Name, ShortOverview, Type, COUNT(*) as Count "
                    f"FROM ActivityLog "
                    f"WHERE Type IN ('VideoPlayback', 'VideoPlaybackStopped', 'SessionStarted') "
                    f"GROUP BY Name, ShortOverview, Type "
                    f"ORDER BY Count DESC LIMIT 100\""
                )
                stdin, stdout, stderr = client.exec_command(cmd, timeout=15)
                output = stdout.read().decode().strip()
                error = stderr.read().decode().strip()

                activities = []
                if output and not error:
                    try:
                        activities = json.loads(output)
                    except json.JSONDecodeError:
                        pass

                # Also try to get device info from Jellyfin's Devices2 table (newer versions)
                cmd2 = (
                    f"sqlite3 -json {self.JELLYFIN_DB_PATH} "
                    f"\"SELECT * FROM sqlite_master WHERE type='table' AND name LIKE '%evice%'\""
                )
                stdin2, stdout2, stderr2 = client.exec_command(cmd2, timeout=10)
                tablesOutput = stdout2.read().decode().strip()

                deviceTables = []
                if tablesOutput:
                    try:
                        deviceTables = [t.get("name", "") for t in json.loads(tablesOutput)]
                    except json.JSONDecodeError:
                        pass

                # If Devices table exists, query it
                deviceRecords = []
                for tableName in deviceTables:
                    cmd3 = (
                        f"sqlite3 -json {self.JELLYFIN_DB_PATH} "
                        f"\"SELECT * FROM [{tableName}] LIMIT 20\""
                    )
                    stdin3, stdout3, stderr3 = client.exec_command(cmd3, timeout=10)
                    tableOutput = stdout3.read().decode().strip()
                    if tableOutput:
                        try:
                            deviceRecords = json.loads(tableOutput)
                        except json.JSONDecodeError:
                            pass

                return {
                    "Success": True,
                    "Activities": activities,
                    "DeviceTables": deviceTables,
                    "DeviceRecords": deviceRecords
                }
            finally:
                client.close()
        except Exception as e:
            LoggingService.LogException("Error getting device playback summary", e, "JellyfinService", "GetDevicePlaybackSummary")
            return {"Success": False, "ErrorMessage": str(e)}

    def InspectLogJsonFields(self) -> Dict[str, Any]:
        """Read one raw FFmpeg transcode log JSON to discover all available fields.
        This helps determine if device/session identifiers are present in log data."""
        try:
            if not PARAMIKO_AVAILABLE:
                return {"Success": False, "ErrorMessage": "paramiko is not installed"}

            client = self._GetSSHClient()
            try:
                # Get one transcode log
                cmd = f"ls -1t {self.JELLYFIN_LOG_DIR}/FFmpeg.Transcode-*.log 2>/dev/null | head -1"
                stdin, stdout, stderr = client.exec_command(cmd)
                logFile = stdout.read().decode().strip()

                if not logFile:
                    return {"Success": False, "ErrorMessage": "No transcode logs found"}

                # Read the first line (JSON)
                cmd = f"head -1 '{logFile}'"
                stdin, stdout, stderr = client.exec_command(cmd)
                jsonLine = stdout.read().decode().strip()

                try:
                    data = json.loads(jsonLine)
                    # Return all top-level keys and their types, plus sample values for non-list/dict fields
                    fields = {}
                    for key, value in data.items():
                        if isinstance(value, (list, dict)):
                            fields[key] = f"({type(value).__name__}, {len(value)} items)"
                        elif isinstance(value, str) and len(value) > 100:
                            fields[key] = value[:100] + "..."
                        else:
                            fields[key] = value
                    return {"Success": True, "Fields": fields, "LogFile": logFile.split('/')[-1]}
                except json.JSONDecodeError:
                    return {"Success": False, "ErrorMessage": "Failed to parse log JSON"}
            finally:
                client.close()
        except Exception as e:
            LoggingService.LogException("Error inspecting log JSON", e, "JellyfinService", "InspectLogJsonFields")
            return {"Success": False, "ErrorMessage": str(e)}

    def _GetSSHClient(self) -> 'paramiko.SSHClient':
        """Create and return a connected SSH client."""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connectArgs = {
            "hostname": self.Host,
            "port": self.SSHPort,
            "username": self.SSHUser,
            "timeout": 10
        }
        if self.SSHKeyPath:
            connectArgs["key_filename"] = self.SSHKeyPath

        client.connect(**connectArgs)
        return client

    def _ParseLogJson(self, JsonLine: str) -> Optional[Dict[str, Any]]:
        """Parse the JSON first line of a Jellyfin FFmpeg log file."""
        try:
            data = json.loads(JsonLine)
            result = {
                "Path": data.get("Path", ""),
                "Name": data.get("Name", ""),
                "Container": data.get("Container", ""),
                "Bitrate": data.get("Bitrate", 0),
            }

            # Extract codec info from MediaStreams
            # Jellyfin MediaStreamType: 0=Audio, 1=Video, 2=Subtitle, 3=EmbeddedImage, 4=Data
            streams = data.get("MediaStreams", [])
            subtitleCodecs = []
            for stream in streams:
                streamType = stream.get("Type", 0)
                if streamType == 1:  # Video
                    result["VideoCodec"] = stream.get("Codec", "")
                    result["Resolution"] = f"{stream.get('Width', '')}x{stream.get('Height', '')}"
                    result["VideoProfile"] = stream.get("Profile", "")
                elif streamType == 0:  # Audio
                    if "AudioCodec" not in result:
                        result["AudioCodec"] = stream.get("Codec", "")
                        result["AudioChannels"] = stream.get("Channels", 0)
                        result["AudioLayout"] = stream.get("ChannelLayout", "")
                elif streamType == 2:  # Subtitle
                    subCodec = stream.get("Codec", "")
                    if subCodec:
                        subtitleCodecs.append(subCodec.lower())

            result["SubtitleCodecs"] = subtitleCodecs

            return result
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

    def _ParseFfmpegCommand(self, FfmpegCommand: str) -> Dict[str, Any]:
        """Parse a Jellyfin FFmpeg command to extract what actions it performs.
        Returns a dict with: VideoAction, AudioAction, SubtitleBurnIn, VideoEncoder, AudioEncoder,
        and destination format fields: DestResolution, DestProfile, DestLevel, DestPixelFormat, DestFormat."""
        result = {
            "VideoAction": "unknown",     # "copy" or "transcode"
            "AudioAction": "unknown",     # "copy" or "transcode"
            "SubtitleBurnIn": False,       # True if subtitles are being burned into video
            "VideoEncoder": "",            # e.g. "libx264", "copy"
            "AudioEncoder": "",            # e.g. "aac", "copy"
            "DestResolution": "",          # e.g. "1920x1080"
            "DestProfile": "",             # e.g. "main", "high"
            "DestLevel": "",               # e.g. "4.1", "5.1"
            "DestPixelFormat": "",         # e.g. "yuv420p", "yuv420p10le"
            "DestFormat": "",              # e.g. "mp4", "hls", "matroska"
        }
        if not FfmpegCommand:
            return result

        import re
        cmd = FfmpegCommand

        # Extract video codec: -c:v, -codec:v:0, or -vcodec
        videoMatch = re.search(r'(?:-c:v\s+|-codec:v(?::\d+)?\s+|-vcodec\s+)(\S+)', cmd)
        if videoMatch:
            encoder = videoMatch.group(1)
            result["VideoEncoder"] = encoder
            result["VideoAction"] = "copy" if encoder == "copy" else "transcode"

        # Extract audio codec: -c:a, -codec:a:0, or -acodec
        audioMatch = re.search(r'(?:-c:a\s+|-codec:a(?::\d+)?\s+|-acodec\s+)(\S+)', cmd)
        if audioMatch:
            encoder = audioMatch.group(1)
            result["AudioEncoder"] = encoder
            result["AudioAction"] = "copy" if encoder == "copy" else "transcode"

        # Check for subtitle burn-in filters
        # Jellyfin uses: -filter_complex with subtitles= or sub2video, or -vf with subtitles=
        if re.search(r'subtitles=|sub2video|ass=', cmd):
            result["SubtitleBurnIn"] = True

        # Destination format: resolution from overlay/scale w=W:h=H, scale_vaapi, or -s WxH
        # Jellyfin uses overlay_qsv=...w=1280:h=720 or scale_vaapi=w=1920:h=1080 or alphasrc=s=WxH
        overlayMatch = re.search(r'(?:overlay_\w+|scale_\w+)=[^]]*?w=(\d+):h=(\d+)', cmd)
        if overlayMatch:
            result["DestResolution"] = f"{overlayMatch.group(1)}x{overlayMatch.group(2)}"
        else:
            alphasrcMatch = re.search(r'alphasrc=s=(\d+x\d+)', cmd)
            if alphasrcMatch:
                result["DestResolution"] = alphasrcMatch.group(1)
            else:
                sizeMatch = re.search(r'-s\s+(\d+x\d+)', cmd)
                if sizeMatch:
                    result["DestResolution"] = sizeMatch.group(1)

        # Destination format: profile from -profile:v or -profile:v:0
        profileMatch = re.search(r'-profile:v(?::\d+)?\s+(\S+)', cmd)
        if profileMatch:
            result["DestProfile"] = profileMatch.group(1)

        # Destination format: level from -level or -level:v
        levelMatch = re.search(r'-level(?::v)?(?::\d+)?\s+(\S+)', cmd)
        if levelMatch:
            levelVal = levelMatch.group(1)
            # Jellyfin uses integer levels (31=3.1, 41=4.1, 51=5.1) — convert to dot notation
            if levelVal.isdigit() and len(levelVal) == 2:
                levelVal = f"{levelVal[0]}.{levelVal[1]}"
            result["DestLevel"] = levelVal

        # Destination format: pixel format from -pix_fmt
        pixFmtMatch = re.search(r'-pix_fmt\s+(\S+)', cmd)
        if pixFmtMatch:
            result["DestPixelFormat"] = pixFmtMatch.group(1)

        # Destination format: output format from the last -f flag (skip input -f flags before -i)
        # Find the position of -i to only look at output flags
        iPos = cmd.find(' -i ')
        if iPos > 0:
            outputPart = cmd[iPos:]
            fmtMatch = re.search(r'-f\s+(\S+)', outputPart)
            if fmtMatch:
                result["DestFormat"] = fmtMatch.group(1)
        else:
            fmtMatch = re.search(r'-f\s+(\S+)', cmd)
            if fmtMatch:
                result["DestFormat"] = fmtMatch.group(1)

        return result

    def _ClassifyTranscodeReason(self, Info: Dict[str, Any], FfmpegCommand: str = "") -> str:
        """Classify transcode reason. Uses FFmpeg command (definitive) with media info fallback."""
        videoCodec = (Info.get("VideoCodec") or "").lower()
        container = (Info.get("Container") or "").lower()
        audioCodec = (Info.get("AudioCodec") or "").lower()

        # Parse the actual FFmpeg command for definitive classification
        cmdInfo = self._ParseFfmpegCommand(FfmpegCommand)

        # 1. Subtitle burn-in (definitive from FFmpeg command)
        if cmdInfo["SubtitleBurnIn"]:
            return "subtitle_transcode"

        # 2. Legacy codec (identifiable from source media info)
        if videoCodec in ("mpeg4", "msmpeg4v3", "msmpeg4v2", "mpeg2video", "wmv3", "wmv2", "rv40"):
            return "legacy_codec"
        if container in ("avi",) and videoCodec in ("mpeg4",):
            return "legacy_codec"

        # 3. If we have command info, use it for precise classification
        if cmdInfo["VideoAction"] == "transcode":
            # Video is being re-encoded. Why?
            if videoCodec in ("hevc", "h265"):
                return "hevc_incompatible"
            return "video_transcode"

        if cmdInfo["VideoAction"] == "copy" and cmdInfo["AudioAction"] == "transcode":
            return "audio_transcode"

        # 4. Container-only issue: compatible codecs but MKV container forces transcode on some clients
        if container in ("matroska", "matroska,webm") and videoCodec in ("h264", "hevc", "h265", "av1") and audioCodec in ("aac", "ac3", "eac3", "mp3", "opus"):
            return "container_incompatible"

        # 5. Fallback: no FFmpeg command available, guess from media info
        if not FfmpegCommand:
            if videoCodec in ("hevc", "h265"):
                return "hevc_incompatible"
            if audioCodec in ("dts", "truehd", "flac", "pcm_s16le", "pcm_s24le"):
                return "audio_transcode"
            # MKV with compatible codecs but no command info — likely container issue
            if container in ("matroska", "matroska,webm"):
                return "container_incompatible"

        return "other"

    def FetchNewLogEntries(self, ExistingLogNames: set) -> Dict[str, Any]:
        """Fetch only new FFmpeg log entries from Jellyfin server.

        Compares against ExistingLogNames to skip already-imported logs.
        Parses new logs and returns entries ready for DB insertion.
        """
        try:
            if not PARAMIKO_AVAILABLE:
                return {"Success": False, "ErrorMessage": "paramiko is not installed"}
            if not self.Host:
                return {"Success": False, "ErrorMessage": "Jellyfin host is not configured"}

            client = self._GetSSHClient()
            try:
                # List all FFmpeg log files
                cmd = f"ls -1 {self.JELLYFIN_LOG_DIR}/FFmpeg.*.log 2>/dev/null"
                stdin, stdout, stderr = client.exec_command(cmd)
                allFiles = [f.strip() for f in stdout.read().decode().strip().split('\n') if f.strip()]

                if not allFiles:
                    return {"Success": True, "Entries": [], "NewCount": 0, "TotalOnServer": 0}

                # Filter to only new files
                newFiles = []
                for f in allFiles:
                    basename = f.split('/')[-1]
                    if basename not in ExistingLogNames:
                        newFiles.append(f)

                if not newFiles:
                    return {"Success": True, "Entries": [], "NewCount": 0, "TotalOnServer": len(allFiles)}

                # Batch read first 3 lines of new files (line 1: JSON, line 2: blank, line 3: FFmpeg command)
                fileList = "' '".join(newFiles)
                cmd = f"for f in '{fileList}'; do head -3 \"$f\" 2>/dev/null; echo '|||SEPARATOR|||'; done"
                stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
                output = stdout.read().decode()

                chunks = output.split('|||SEPARATOR|||')
                entries = []

                for i, chunk in enumerate(chunks):
                    chunk = chunk.strip()
                    if not chunk or i >= len(newFiles):
                        continue

                    fullPath = newFiles[i]
                    basename = fullPath.split('/')[-1]

                    # Determine operation type from filename prefix
                    opType = ""
                    for opName, prefix in self.OP_TYPES.items():
                        if basename.startswith(prefix):
                            opType = opName
                            break
                    if not opType:
                        continue

                    # Extract date from filename
                    logDate = ""
                    match = re.search(r'-(\d{4}-\d{2}-\d{2})_', basename)
                    if match:
                        logDate = match.group(1)

                    # Split into lines: line 1 = JSON, line 2 = blank, line 3 = FFmpeg command
                    logLines = chunk.split('\n')
                    jsonLine = logLines[0].strip()
                    # FFmpeg command is on line 3 (index 2), line 2 is blank
                    ffmpegCmd = ""
                    for line in logLines[1:]:
                        stripped = line.strip()
                        if stripped and stripped.startswith('/'):
                            ffmpegCmd = stripped
                            break

                    # Parse media info JSON
                    info = self._ParseLogJson(jsonLine)
                    if not info:
                        continue

                    filePath = info.get("Path", "")
                    fileName = info.get("Name", filePath.split('/')[-1] if filePath else "unknown")

                    reason = ""
                    transcodeActions = ""
                    destResolution = ""
                    destProfile = ""
                    destLevel = ""
                    destPixelFormat = ""
                    destFormat = ""
                    if opType == "Transcode":
                        reason = self._ClassifyTranscodeReason(info, ffmpegCmd)
                        # Store condensed command summary for debugging/display
                        cmdInfo = self._ParseFfmpegCommand(ffmpegCmd)
                        parts = []
                        if cmdInfo["VideoAction"] != "unknown":
                            parts.append(f"v:{cmdInfo['VideoEncoder']}")
                        if cmdInfo["AudioAction"] != "unknown":
                            parts.append(f"a:{cmdInfo['AudioEncoder']}")
                        if cmdInfo["SubtitleBurnIn"]:
                            parts.append("sub:burn-in")
                        transcodeActions = " | ".join(parts)
                        destResolution = cmdInfo.get("DestResolution", "")
                        destProfile = cmdInfo.get("DestProfile", "")
                        destLevel = cmdInfo.get("DestLevel", "")
                        destPixelFormat = cmdInfo.get("DestPixelFormat", "")
                        destFormat = cmdInfo.get("DestFormat", "")

                    subtitleCodecs = info.get("SubtitleCodecs", [])

                    entries.append({
                        "LogFileName": basename,
                        "OperationType": opType,
                        "FilePath": filePath,
                        "FileName": fileName,
                        "VideoCodec": info.get("VideoCodec", ""),
                        "AudioCodec": info.get("AudioCodec", ""),
                        "Container": info.get("Container", ""),
                        "Resolution": info.get("Resolution", ""),
                        "SubtitleCodecs": ",".join(subtitleCodecs),
                        "Reason": reason,
                        "TranscodeActions": transcodeActions,
                        "LogDate": logDate,
                        "DestResolution": destResolution,
                        "DestProfile": destProfile,
                        "DestLevel": destLevel,
                        "DestPixelFormat": destPixelFormat,
                        "DestFormat": destFormat
                    })

                return {
                    "Success": True,
                    "Entries": entries,
                    "NewCount": len(entries),
                    "TotalOnServer": len(allFiles)
                }
            finally:
                client.close()
        except Exception as e:
            LoggingService.LogException("Error fetching new log entries", e, "JellyfinService", "FetchNewLogEntries")
            return {"Success": False, "ErrorMessage": str(e)}
