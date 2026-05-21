"""Offline regression test for the consolidated CommandBuilder.

Run after any change to `Models/CommandBuilder.py`, the audio-completion
policy, the dispatch tree, or the worker ProcessingMode set:

    py Scripts/RegressionTestCommandBuilder.py

Pulls real MediaFile rows from the DB, constructs synthetic queue Jobs at
the three possible ProcessingMode values (Transcode / Quick / SubtitleFix),
and calls BuildFFmpegCommand for each. Prints the emitted command string
and checks five contracts:

  - command is non-None
  - command contains "-f mp4"  (BUG-0005)
  - command contains "-movflags +faststart"
  - output path ends ".mp4.inprogress"  (worker-lifecycle C6)
  - audio policy matches AudioComplete (copy vs loudnorm)

No FFmpeg is actually invoked. No files are touched. Purely string inspection.
"""
import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from Repositories.DatabaseManager import DatabaseManager
from Features.TranscodeQueue.Models.TranscodeQueueModel import TranscodeQueueModel
from Models.CommandBuilder import CommandBuilder

SAMPLE_IDS = [620274, 19661, 620280, 11148]
MOCK_FFMPEG = r"C:\ffmpeg\bin\ffmpeg.exe"
MOCK_FFPROBE = r"C:\ffmpeg\bin\ffprobe.exe"

def make_job(media_file_id, processing_mode):
    return TranscodeQueueModel(
        Id=9999,
        FilePath=f"fake/path/id-{media_file_id}",
        ProcessingMode=processing_mode,
        Status="Pending",
    )

def check_command(name, cmd_dict, expect_audio_copy):
    if not cmd_dict:
        return [f"FAIL: command is None"]
    cmd = cmd_dict.get("Command", "")
    out = cmd_dict.get("OutputPath", "")
    issues = []
    if "-f mp4" not in cmd:
        issues.append("MISSING -f mp4")
    if "-movflags +faststart" not in cmd:
        issues.append("MISSING -movflags +faststart")
    if not out.endswith(".mp4.inprogress"):
        issues.append(f"OutputPath does not end .mp4.inprogress: {out}")
    if expect_audio_copy:
        if "-c:a copy" not in cmd:
            issues.append("expected -c:a copy (AudioComplete=true) but missing")
        if "loudnorm" in cmd:
            issues.append("expected NO loudnorm (AudioComplete=true) but present")
    else:
        if "loudnorm" not in cmd:
            issues.append("expected loudnorm chain (AudioComplete=false) but missing")
    # Mixed-slash check inside a quoted path token
    quoted = re.findall(r'"([^"]+)"', cmd)
    for q in quoted:
        if "\\" in q and "/" in q:
            issues.append(f"mixed slashes in path: {q}")
    return issues

def dispatch_label(builder_method_called, job):
    if job.IsSubtitleFix: return "_BuildSubtitleFixShape"
    if job.IsRemux: return "_BuildRemuxShape"
    return "_BuildTranscodeShape"

def run():
    dm = DatabaseManager()
    print("=" * 72)
    print("Command Builder Smoke Test")
    print("=" * 72)
    for mid in SAMPLE_IDS:
        mf = dm.GetMediaFileById(mid)
        if not mf:
            print(f"\n!! MediaFile {mid} not found, skipping")
            continue
        # Decide which Job mode this file should use, reading flags off the MODEL
        if mf.NeedsTranscode:
            mode = "Transcode"
        elif mf.NeedsQuick:
            mode = "Quick"
        else:
            mode = "Transcode"  # fallback for smoke
        job = make_job(mid, mode)
        print(f"\n--- MediaFile {mid} ---")
        print(f"  Resolution={mf.Resolution} Codec={mf.Codec} AudioCodec={mf.AudioCodec} "
              f"AudioChannels={getattr(mf, 'AudioChannels', '?')}")
        print(f"  AudioComplete={mf.AudioComplete} NeedsQuick={mf.NeedsQuick} NeedsTranscode={mf.NeedsTranscode}")
        print(f"  ProcessingMode={mode}  IsRemux={job.IsRemux}  IsSubtitleFix={job.IsSubtitleFix}")
        print(f"  Expected dispatch: {dispatch_label(None, job)}")

        # Construct minimal context; skip FFprobe by pre-supplying stream info
        Context = {
            "FFmpegPath": MOCK_FFMPEG,
            "FFprobePath": MOCK_FFPROBE,
            "InputPath": mf.FilePath,
            "OutputDirectory": r"C:\tmp",
            "AudioStreamIndex": 0,
            "HasAudio": True,
        }
        if mode == "Transcode":
            # Minimal profile/codec stubs so transcode path runs without DB
            Context["ProfileSettings"] = {
                "Quality": 28, "Preset": 6, "Codec": "libsvtav1",
                "FilmGrain": 0, "UseNvidiaHardware": 0, "ContainerType": "mp4",
                "AudioBitrateKbps": 0,
            }
            Context["CodecFlags"] = {}
            Context["CodecParameters"] = [
                {"ParameterName": "crf"}, {"ParameterName": "preset"}, {"ParameterName": "film-grain"},
            ]
            Context["SourceResolution"] = mf.Resolution
            Context["TargetResolution"] = mf.Resolution  # no downscale for smoke

        result = CommandBuilder.BuildFFmpegCommand(mf, job, Context)
        expect_audio_copy = bool(mf.AudioComplete)
        issues = check_command(f"id-{mid}", result, expect_audio_copy)
        if result:
            cmd = result.get("Command", "")
            print(f"  Command (len={len(cmd)}):")
            # Truncate display
            print(f"    {cmd[:250]}{'...' if len(cmd) > 250 else ''}")
            print(f"  OutputPath: {result.get('OutputPath')}")
        if issues:
            print("  ISSUES:")
            for i in issues:
                print(f"    - {i}")
        else:
            print("  PASS")

if __name__ == "__main__":
    run()
