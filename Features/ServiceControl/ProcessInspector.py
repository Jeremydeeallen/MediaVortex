import psutil

from Core.Logging.LoggingService import LoggingService


FFMPEG_PROCESS_NAMES = ("ffmpeg", "ffmpeg.exe", "cmd.exe", "sh", "bash")


# directive: transcode-flow-canonical
class ProcessInspector:
    """Read-only OS-level process queries used by phase detectors + cleanup."""

    # directive: transcode-flow-canonical
    def GetProcessName(self, Pid):
        if not Pid:
            return None
        try:
            return psutil.Process(int(Pid)).name()
        except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
            return None
        # fail-loud-ok: unknown psutil errors return None (=treat as gone); safer than crashing loop
        except Exception as Ex:
            LoggingService.LogException(
                f"ProcessInspector.GetProcessName({Pid}) failed",
                Ex, "ProcessInspector", "GetProcessName",
            )
            return None

    # directive: transcode-flow-canonical
    def IsFFmpegProcessName(self, Name):
        if not Name:
            return False
        return Name.lower() in FFMPEG_PROCESS_NAMES
