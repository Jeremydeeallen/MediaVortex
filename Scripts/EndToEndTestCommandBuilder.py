r"""End-to-end test that actually invokes FFmpeg against a built command.

Three test cases against real files on T:\, clamped to -t 10 (10 seconds of
media) so each run finishes in seconds:

  1. Quick path, AudioComplete=true   (-c:v copy + -c:a copy)
  2. Quick path, AudioComplete=false  (-c:v copy + audio normalize)
  3. Transcode path, AudioComplete=true (full re-encode with -c:a copy)

For each case:
  - Build the command via BuildFFmpegCommand
  - Inject -t 10 to clamp media duration
  - Run ffmpeg, capture stdout/stderr/exitcode
  - Verify output file exists, is non-empty, FFprobe parses it
  - Clean up the .inprogress file
  - Report PASS / FAIL with diagnostic
"""
import os, sys, subprocess, json, shlex, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from Repositories.DatabaseManager import DatabaseManager
from Features.TranscodeQueue.Models.TranscodeQueueModel import TranscodeQueueModel
from Models.CommandBuilder import CommandBuilder

I9_FFMPEG  = r"C:\Code\MediaVortex\FFmpegMaster\bin\ffmpeg.exe"
I9_FFPROBE = r"C:\Code\MediaVortex\FFmpegMaster\bin\ffprobe.exe"

TEST_CASES = [
    {"id": 4241,  "mode": "Quick",     "label": "Quick AudioComplete=true  (-c:a copy)"},
    {"id": 22326, "mode": "Quick",     "label": "Quick AudioComplete=false (audio normalize)"},
    {"id": 4241,  "mode": "Transcode", "label": "Transcode AudioComplete=true (-c:a copy)"},
]


def inject_clamp(cmd, seconds=10):
    """Insert -t <seconds> after the first '-i \"<path>\"' so we only process N seconds."""
    # The command is space-separated tokens; find -i and insert -t after the input path
    match = re.search(r'(-i\s+"[^"]+")', cmd)
    if not match:
        return cmd
    before = cmd[:match.end()]
    after  = cmd[match.end():]
    return f"{before} -t {seconds}{after}"


def ffprobe_parse(path):
    """Return (ok, summary) — ffprobe parses the file's header without decoding."""
    try:
        result = subprocess.run(
            [I9_FFPROBE, "-v", "error", "-show_format", "-show_streams",
             "-print_format", "json", path],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return False, f"ffprobe exit={result.returncode}: {result.stderr.strip()[:200]}"
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        video = [s for s in streams if s.get("codec_type") == "video"]
        audio = [s for s in streams if s.get("codec_type") == "audio"]
        return True, f"video={len(video)} audio={len(audio)} format={data.get('format', {}).get('format_name', '?')}"
    except Exception as e:
        return False, f"ffprobe failed: {e}"


# directive: path-schema-migration | # see path.S8
def make_job(media_file_id, mode, storage_root_id, relative_path):
    return TranscodeQueueModel(
        Id=99000 + media_file_id,
        StorageRootId=storage_root_id,
        RelativePath=relative_path,
        ProcessingMode=mode,
        Status="Pending",
    )


def run_case(dm, case):
    print("=" * 78)
    print(f"CASE: {case['label']}")
    print("=" * 78)

    mf = dm.GetMediaFileById(case["id"])
    if not mf:
        print(f"  SKIP: MediaFile {case['id']} not in DB")
        return False

    print(f"  File: {mf.FilePath}")
    print(f"  {mf.Resolution} {mf.Codec}/{mf.AudioCodec} {mf.AudioChannels}ch  "
          f"AudioComplete={mf.AudioComplete} SizeMB={mf.SizeMB:.1f}")

    if not os.path.exists(mf.FilePath):
        print(f"  SKIP: file not accessible from I9: {mf.FilePath}")
        return False

    job = make_job(case["id"], case["mode"], mf.StorageRootId, mf.RelativePath or "")
    Context = {
        "FFmpegPath": I9_FFMPEG,
        "FFprobePath": I9_FFPROBE,
        "InputPath": mf.FilePath,
        "OutputDirectory": os.path.dirname(mf.FilePath),
    }
    if case["mode"] == "Transcode":
        Context["ProfileSettings"] = {
            "Quality": 28, "Preset": 8, "Codec": "libsvtav1",
            "FilmGrain": 0, "UseNvidiaHardware": 0, "ContainerType": "mp4",
            "AudioBitrateKbps": 0,
        }
        Context["CodecFlags"] = {}
        Context["CodecParameters"] = [
            {"ParameterName": "crf"}, {"ParameterName": "preset"}, {"ParameterName": "film-grain"},
        ]
        Context["SourceResolution"] = mf.Resolution
        Context["TargetResolution"] = mf.Resolution

    result = CommandBuilder.BuildFFmpegCommand(mf, job, Context)
    if not result:
        print("  FAIL: BuildFFmpegCommand returned None")
        return False

    cmd = result["Command"]
    out = result["OutputPath"]
    clamped = inject_clamp(cmd, seconds=10)

    print(f"  Output target: {out}")
    print(f"  Running FFmpeg (clamped -t 10) ...")

    try:
        run = subprocess.run(clamped, shell=True, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        print("  FAIL: ffmpeg timed out after 180s")
        try: os.unlink(out)
        except Exception: pass
        return False

    if run.returncode != 0:
        print(f"  FAIL: ffmpeg exited with code {run.returncode}")
        stderr_tail = "\n    ".join(run.stderr.strip().splitlines()[-15:])
        print(f"    ---stderr tail---")
        print(f"    {stderr_tail}")
        try: os.unlink(out)
        except Exception: pass
        return False

    if not os.path.exists(out):
        print("  FAIL: ffmpeg exited 0 but output file is missing")
        return False

    size = os.path.getsize(out)
    if size < 1024:
        print(f"  FAIL: output too small ({size} bytes)")
        os.unlink(out)
        return False

    ok, summary = ffprobe_parse(out)
    if not ok:
        print(f"  FAIL: output is not a valid MP4: {summary}")
        os.unlink(out)
        return False

    print(f"  PASS: ffmpeg exit=0, output {size/1024:.1f}KB, ffprobe: {summary}")
    os.unlink(out)
    return True


def main():
    dm = DatabaseManager()
    passed = 0
    failed = 0
    for case in TEST_CASES:
        if run_case(dm, case):
            passed += 1
        else:
            failed += 1
        print()
    print("=" * 78)
    print(f"RESULT: {passed} passed, {failed} failed")
    print("=" * 78)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
