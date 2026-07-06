import os
import subprocess
import tempfile
from Core.Logging.LoggingService import LoggingService
from Core.WorkerContext import WorkerContext


# directive: path-schema-migration | # see path.S8
def LocalExists(Value):
    """Existence on a worker-local string."""
    return bool(Value) and os.path.exists(Value)


def _ResolveFFmpegPath():
    """Resolve FFmpeg from WorkerContext (set at worker startup from Workers.FFmpegPath).
    Raises if no context is available so misconfigurations fail loudly instead of using a stale hardcoded path."""
    Ctx = WorkerContext.TryCurrent()
    if not Ctx or not Ctx.FFmpegPath:
        raise RuntimeError(
            "FFmpeg path not configured. ClipBuilder requires WorkerContext.FFmpegPath to be set "
            "from the Workers.FFmpegPath column. Configure the worker row before retrying."
        )
    return Ctx.FFmpegPath


class ClipBuilderBusinessService:

    def ExtractAndConcatenate(self, InputPath, StartTimes, ClipDuration, Outputs, OutputName):
        """Extract clips once at primary (longest) duration, concatenate for primary output,
        then trim those same clips for the half output — avoids re-encoding from source twice.

        Outputs: list of (Suffix, DurationMultiplier, OutputFolder) tuples.
        First entry is primary (1x), second (if present) is half (0.5x).
        """
        TempDir = tempfile.mkdtemp(prefix="clipbuilder_")
        PrimaryClips = []

        try:
            # Step 1: Extract clips at primary (full) duration
            PrimarySuffix = Outputs[0][0]
            for Index, StartTime in enumerate(StartTimes):
                TempClipPath = os.path.join(TempDir, f"clip_primary_{Index}.mp4")
                PrimaryClips.append(TempClipPath)

                Cmd = [
                    _ResolveFFmpegPath(),
                    "-ss", StartTime,
                    "-t", str(ClipDuration),
                    "-i", InputPath,
                    "-map", "0:v:0", "-map", "0:a:0",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-g", "120", "-keyint_min", "120",
                    "-c:a", "aac", "-ac", "2", "-b:a", "192k",
                    "-movflags", "+faststart",
                    "-y", TempClipPath
                ]

                LoggingService.LogInfo(f"[{PrimarySuffix}] Extracting clip {Index + 1}/{len(StartTimes)} at {StartTime} ({ClipDuration}s)", "ClipBuilderBusinessService", "ExtractAndConcatenate")
                Result = subprocess.run(Cmd, capture_output=True, text=True, timeout=300)

                if Result.returncode != 0:
                    raise RuntimeError(f"FFmpeg clip extraction failed (clip {Index + 1}): {Result.stderr[-500:]}")

            OutputPaths = []

            # Step 2: Concatenate primary clips (stream copy — same encoding)
            PrimaryFolder = Outputs[0][2]
            PrimaryOutput = self._ConcatenateClips(PrimaryClips, TempDir, PrimaryFolder, OutputName, PrimarySuffix)
            OutputPaths.append(PrimaryOutput)

            # Step 3: If half output requested, trim each primary clip to half duration then concatenate
            if len(Outputs) > 1:
                HalfSuffix = Outputs[1][0]
                HalfDuration = ClipDuration * Outputs[1][1]
                HalfFolder = Outputs[1][2]
                HalfClips = []

                for Index, PrimaryClip in enumerate(PrimaryClips):
                    HalfClipPath = os.path.join(TempDir, f"clip_half_{Index}.mp4")
                    HalfClips.append(HalfClipPath)

                    # Stream copy trim — no re-encode needed since clips share encoding
                    TrimCmd = [
                        _ResolveFFmpegPath(),
                        "-i", PrimaryClip,
                        "-t", str(HalfDuration),
                        "-c", "copy",
                        "-movflags", "+faststart",
                        "-y", HalfClipPath
                    ]

                    LoggingService.LogInfo(f"[{HalfSuffix}] Trimming clip {Index + 1}/{len(PrimaryClips)} to {HalfDuration}s", "ClipBuilderBusinessService", "ExtractAndConcatenate")
                    Result = subprocess.run(TrimCmd, capture_output=True, text=True, timeout=60)

                    if Result.returncode != 0:
                        raise RuntimeError(f"FFmpeg trim failed ({HalfSuffix} clip {Index + 1}): {Result.stderr[-500:]}")

                HalfOutput = self._ConcatenateClips(HalfClips, TempDir, HalfFolder, OutputName, HalfSuffix)
                OutputPaths.append(HalfOutput)

                # Clean up half clips
                for ClipPath in HalfClips:
                    try:
                        if LocalExists(ClipPath):
                            os.remove(ClipPath)
                    except Exception:
                        pass

            return {"Success": True, "OutputPaths": OutputPaths}

        finally:
            # Clean up temp files
            for ClipPath in PrimaryClips:
                try:
                    if LocalExists(ClipPath):
                        os.remove(ClipPath)
                except Exception:
                    pass
            try:
                for F in os.listdir(TempDir):
                    os.remove(os.path.join(TempDir, F))
                os.rmdir(TempDir)
            except Exception:
                pass

    def _ConcatenateClips(self, ClipPaths, TempDir, OutputFolder, OutputName, Suffix):
        """Concatenate a list of clip files into a single MP4 via stream copy."""
        ConcatListPath = os.path.join(TempDir, f"filelist_{Suffix}.txt")
        with open(ConcatListPath, "w") as F:
            for ClipPath in ClipPaths:
                F.write(f"file '{ClipPath}'\n")

        os.makedirs(OutputFolder, exist_ok=True)
        OutputPath = os.path.join(OutputFolder, f"{OutputName}_{Suffix}.mp4")

        ConcatCmd = [
            _ResolveFFmpegPath(),
            "-f", "concat", "-safe", "0",
            "-i", ConcatListPath,
            "-c", "copy",
            "-movflags", "+faststart",
            "-y", OutputPath
        ]

        LoggingService.LogInfo(f"[{Suffix}] Concatenating {len(ClipPaths)} clips to {OutputPath}", "ClipBuilderBusinessService", "_ConcatenateClips")
        Result = subprocess.run(ConcatCmd, capture_output=True, text=True, timeout=120)

        if Result.returncode != 0:
            raise RuntimeError(f"FFmpeg concat failed ({Suffix}): {Result.stderr[-500:]}")

        LoggingService.LogInfo(f"[{Suffix}] Export complete: {OutputPath}", "ClipBuilderBusinessService", "_ConcatenateClips")
        return OutputPath
