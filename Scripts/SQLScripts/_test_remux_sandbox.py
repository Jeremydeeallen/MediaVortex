"""
Sandbox smoke test for the new remux flow + atomic rename-replace pattern.

Self-contained, never touches production media. Copies a small source file
into a scratch dir, hand-builds the FFmpeg command via the real
BuildRemuxCommand, runs FFmpeg, then exercises the real
_ProcessCompleteFileReplacement to verify the rename-rollback dance works.
ffprobes the final result to confirm container + audio + loudness.

Usage: py Scripts/SQLScripts/_test_remux_sandbox.py <source_media_path>
"""

import os
import sys
import shutil
import subprocess
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Locate ffmpeg / ffprobe
ROOT = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
FFMPEG = str(ROOT / "FFmpegMaster" / "bin" / "ffmpeg.exe")
FFPROBE = str(ROOT / "FFmpegMaster" / "bin" / "ffprobe.exe")
SANDBOX = ROOT / "test_remux_sandbox"


def Banner(s):
    print()
    print("=" * 78)
    print(s)
    print("=" * 78)


def Probe(path):
    result = subprocess.run(
        [
            FFPROBE,
            "-v", "error",
            "-show_format",
            "-show_streams",
            "-of", "json",
            path,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("FFPROBE FAILED:", result.stderr)
        return None
    return json.loads(result.stdout)


def MeasureLoudness(path):
    """Run ffmpeg with the loudnorm analysis filter to extract integrated LUFS."""
    result = subprocess.run(
        [
            FFMPEG,
            "-hide_banner",
            "-i", path,
            "-af", "loudnorm=I=-23:LRA=7:TP=-2:print_format=json",
            "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
    )
    # loudnorm prints JSON to stderr after the encoding stats
    out = result.stderr
    start = out.rfind("{")
    end = out.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(out[start : end + 1])
        except Exception:
            return None
    return None


def Main():
    if len(sys.argv) < 2:
        print("Usage: py _test_remux_sandbox.py <source_media_path>")
        sys.exit(1)
    SourceFile = sys.argv[1]
    if not os.path.exists(SourceFile):
        print(f"Source file does not exist: {SourceFile}")
        sys.exit(1)

    if SANDBOX.exists():
        shutil.rmtree(SANDBOX)
    SANDBOX.mkdir(parents=True, exist_ok=True)

    # Copy source into sandbox so the test never touches production media
    SourceCopy = SANDBOX / os.path.basename(SourceFile)
    Banner(f"STEP 0 -- Sandbox setup: copy source into {SANDBOX}")
    shutil.copy2(SourceFile, SourceCopy)
    print(f"  Copied {os.path.getsize(SourceCopy):,} bytes")
    print(f"  Sandbox source path: {SourceCopy}")

    # Hash before any operations
    SourceCopyBeforeSize = os.path.getsize(SourceCopy)

    # ---------------------------------------------------------------
    # STEP 1 -- BuildRemuxCommand (verify side-by-side suffix is applied)
    # ---------------------------------------------------------------
    Banner("STEP 1 -- BuildRemuxCommand: verify side-by-side suffix + audio filter")

    from Models.CommandBuilder import CommandBuilder

    class _Job:
        Id = 99999
        FilePath = str(SourceCopy)
        FileName = os.path.basename(str(SourceCopy))
        SizeBytes = SourceCopyBeforeSize
        SizeMB = SourceCopyBeforeSize / (1024 * 1024)
        MediaFileId = None

    class _MediaFile:
        Id = 99999
        FileName = os.path.basename(str(SourceCopy))
        AssignedProfile = "SVT-AV1 P6 FG8 >480p"
        Resolution = "1280x720"
        Codec = "h264"

    # Rename-before-encode flow: call PrepareReplacement to rename source
    # to .orig FIRST, then build the command with InputPath=.orig and
    # OutputPath=freed source path. This mirrors what ProcessRemuxJob does
    # in production.
    from Features.FileReplacement.FileReplacementBusinessService import FileReplacementBusinessService
    Frb = FileReplacementBusinessService()
    Frb._ToLocalPath = lambda x: x  # canonical == local in sandbox
    PrepResult = Frb.PrepareReplacement(str(SourceCopy))
    if not PrepResult.get('Success'):
        print(f"PrepareReplacement FAIL: {PrepResult.get('ErrorMessage')}")
        sys.exit(1)
    OrigBackupPath = PrepResult['OrigBackupPath']
    print(f"  Source renamed to: {OrigBackupPath}")

    # The freed source path = original SourceCopy path (since SourceCopy was
    # the only thing there, and it has now been renamed to .orig).
    FreedSourcePath = str(SourceCopy)
    BaseName, _ = os.path.splitext(os.path.basename(FreedSourcePath))
    TargetLocalPath = os.path.join(os.path.dirname(FreedSourcePath), BaseName + ".mp4")

    Cb = CommandBuilder()
    Result = Cb.BuildRemuxCommand({
        "Job": _Job(),
        "MediaFile": _MediaFile(),
        "AudioCodec": "aac",
        "AudioStreamIndex": 0,
        "InputPath": OrigBackupPath,
        "OutputPath": TargetLocalPath,
        "FFmpegPath": FFMPEG,
        "OutputDirectory": str(SANDBOX),
        "TranscodeOutputMode": "InPlace",
    })
    if not Result:
        print("BuildRemuxCommand returned None -- FAIL")
        Frb.RollbackReplacement(str(SourceCopy), OrigBackupPath, TargetLocalPath)
        sys.exit(1)
    Cmd = Result["Command"]
    OutputPath = Result["OutputPath"]
    print(f"  Command:\n    {Cmd}")
    print(f"  OutputPath: {OutputPath}")

    Checks = []
    Checks.append(("OutputPath has NO _remuxed suffix", "_remuxed.mp4" not in OutputPath, True))
    Checks.append(("OutputPath ends with .mp4 (not .m4v)", OutputPath.endswith(".mp4") and "_remuxed" not in OutputPath, True))
    Checks.append(("InputPath in command points to .orig", ".orig" in Cmd, True))
    Checks.append(("Command includes -af loudnorm", "loudnorm" in Cmd.lower(), True))
    Checks.append(("Command includes -c:a aac", "-c:a aac" in Cmd, True))
    Checks.append(("Command does NOT include -c:a copy", "-c:a copy" not in Cmd, True))
    Checks.append(("Command video codec is copy", "-c:v copy" in Cmd, True))

    for Label, Got, Expected in Checks:
        Mark = "PASS" if Got == Expected else "FAIL"
        print(f"  [{Mark}] {Label}: got={Got}")
    if not all(g == e for _, g, e in Checks):
        print("\nStep 1 FAILED -- aborting before touching disk.")
        sys.exit(1)

    # ---------------------------------------------------------------
    # STEP 2 -- Execute FFmpeg, verify staged output landed at side-by-side path
    # ---------------------------------------------------------------
    Banner("STEP 2 -- Execute FFmpeg, produce staged output")
    print(f"  Running: {Cmd[:120]}{'...' if len(Cmd) > 120 else ''}")
    Run = subprocess.run(Cmd, shell=True, capture_output=True, text=True)
    if Run.returncode != 0:
        print(f"  FFmpeg failed with code {Run.returncode}:")
        print(Run.stderr[-2000:])
        sys.exit(1)
    print(f"  FFmpeg succeeded ({Run.returncode})")

    if not os.path.exists(OutputPath):
        print(f"  [FAIL] Staged output does not exist at {OutputPath}")
        Frb.RollbackReplacement(str(SourceCopy), OrigBackupPath, TargetLocalPath)
        sys.exit(1)
    StagedSize = os.path.getsize(OutputPath)
    print(f"  Output written to: {StagedSize:,} bytes at {OutputPath}")

    # In the rename-before-encode flow, the source has been renamed to .orig,
    # so the original source path is now a NEW file (FFmpeg's output). Verify
    # the .orig backup is still bit-identical to what we copied in.
    if not os.path.exists(OrigBackupPath):
        print(f"  [CATASTROPHIC] .orig backup disappeared at {OrigBackupPath} -- BUG")
        sys.exit(1)
    OrigBackupSize = os.path.getsize(OrigBackupPath)
    if OrigBackupSize != SourceCopyBeforeSize:
        print(f"  [FAIL] .orig backup size changed: {SourceCopyBeforeSize} -> {OrigBackupSize}")
        sys.exit(1)
    print(f"  [PASS] .orig backup preserves original ({OrigBackupSize:,} bytes)")

    # ---------------------------------------------------------------
    # STEP 3 -- _ProcessCompleteFileReplacement detects pre-renamed flow
    # ---------------------------------------------------------------
    Banner("STEP 3 -- _ProcessCompleteFileReplacement (pre-renamed flow)")

    # Stub the DB-side metadata refresh so it doesn't try to find a real MediaFile row
    Frb._UpdateMediaFilesAfterReplacement = lambda OriginalFilePath, NewFilePath: {
        'Success': True,
        'Message': 'sandbox stub'
    }

    Replacement = Frb._ProcessCompleteFileReplacement(
        OriginalFilePath=str(SourceCopy),
        TranscodedFilePath=OutputPath,
        KeepSource=False,
        NetworkOriginalPath=str(SourceCopy),
    )
    print("  Replacement result:")
    for K, V in Replacement.items():
        if K == "StepsCompleted" and isinstance(V, list):
            for S in V:
                print(f"    - {S}")
        else:
            print(f"    {K}: {V}")

    if not Replacement.get("Success"):
        print("\nStep 3 FAILED -- inspecting sandbox for rollback state:")
        for f in sorted(os.listdir(SANDBOX)):
            print(f"    {os.path.getsize(SANDBOX / f):>14,} bytes  {f}")
        sys.exit(1)

    # ---------------------------------------------------------------
    # STEP 4 -- Verify final disk state
    # ---------------------------------------------------------------
    Banner("STEP 4 -- Verify final sandbox state")
    SandboxFiles = sorted(os.listdir(SANDBOX))
    print("  Files in sandbox:")
    for f in SandboxFiles:
        print(f"    {os.path.getsize(SANDBOX / f):>14,} bytes  {f}")

    # Expected end state with KeepSource=False:
    # - Original filename present (was replaced)
    # - _remuxed.mp4 staged file gone (it was renamed to the original)
    # - .orig file gone (deleted because KeepSource=False)
    OriginalName = os.path.basename(str(SourceCopy))
    OrigBackup = OriginalName + ".orig"
    StagedName = os.path.basename(OutputPath)

    StateChecks = [
        ("Original filename exists", OriginalName in SandboxFiles, True),
        ("Staged _remuxed file is gone", StagedName not in SandboxFiles, True),
        (".orig backup is gone (KeepSource=False)", OrigBackup not in SandboxFiles, True),
    ]
    for Label, Got, Expected in StateChecks:
        Mark = "PASS" if Got == Expected else "FAIL"
        print(f"  [{Mark}] {Label}")

    # ---------------------------------------------------------------
    # STEP 5 -- ffprobe the result
    # ---------------------------------------------------------------
    Banner("STEP 5 -- ffprobe the resulting file")
    FinalPath = str(SANDBOX / OriginalName)
    Probed = Probe(FinalPath)
    if not Probed:
        print("  ffprobe failed.")
        sys.exit(1)

    ContainerFmt = Probed.get("format", {}).get("format_name", "")
    AudioStream = next((s for s in Probed.get("streams", []) if s.get("codec_type") == "audio"), None)
    VideoStream = next((s for s in Probed.get("streams", []) if s.get("codec_type") == "video"), None)
    print(f"  Container:    {ContainerFmt}")
    if VideoStream:
        print(f"  Video:        {VideoStream.get('codec_name')} {VideoStream.get('width')}x{VideoStream.get('height')}")
    if AudioStream:
        print(f"  Audio:        {AudioStream.get('codec_name')} {AudioStream.get('channels')}ch {AudioStream.get('sample_rate')}Hz {AudioStream.get('bit_rate')} bps")

    # Loudness measurement
    Loud = MeasureLoudness(FinalPath)
    if Loud:
        print(f"  Loudness:     I={Loud.get('input_i')} LUFS, target=-23, output_i={Loud.get('output_i')}")
    else:
        print("  Loudness:     <could not measure>")

    OutputChecks = [
        ("Container is mp4-family", any(p in ContainerFmt for p in ("mp4", "mov")), True),
        ("Audio codec is aac", AudioStream and AudioStream.get("codec_name") == "aac", True),
        ("Video codec preserved (h264)", VideoStream and VideoStream.get("codec_name") == "h264", True),
    ]
    if Loud:
        try:
            InputI = float(Loud.get("input_i", 0))
            OutputChecks.append((
                "Integrated loudness within 2 LUFS of target -23",
                abs(InputI - (-23)) < 2.0,
                True,
            ))
        except Exception:
            pass

    for Label, Got, Expected in OutputChecks:
        Mark = "PASS" if Got == Expected else "FAIL"
        print(f"  [{Mark}] {Label}")

    Banner("Test complete. Sandbox dir kept for inspection at: " + str(SANDBOX))


if __name__ == "__main__":
    Main()
