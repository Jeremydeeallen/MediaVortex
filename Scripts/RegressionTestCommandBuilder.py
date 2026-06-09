import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from Repositories.DatabaseManager import DatabaseManager
from Features.TranscodeQueue.Models.TranscodeQueueModel import TranscodeQueueModel
from Models.CommandBuilder import CommandBuilder

SAMPLE_IDS = [620274, 19661, 620280, 11148]
MOCK_FFMPEG = r"C:\ffmpeg\bin\ffmpeg.exe"
MOCK_FFPROBE = r"C:\ffmpeg\bin\ffprobe.exe"


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def make_job(media_file_id, processing_mode, storage_root_id, relative_path):
    """Synthesize a Pending TranscodeQueueModel for a given mode + typed pair."""
    return TranscodeQueueModel(
        Id=9999,
        StorageRootId=storage_root_id,
        RelativePath=relative_path,
        ProcessingMode=processing_mode,
        Status="Pending",
    )


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def check_command(name, cmd_dict, expect_audio_copy):
    """Five-contract command-shape check; returns issues list, empty if all pass."""
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
    quoted = re.findall(r'"([^"]+)"', cmd)
    for q in quoted:
        if "\\" in q and "/" in q:
            issues.append(f"mixed slashes in path: {q}")
    return issues


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def dispatch_label(builder_method_called, job):
    """Map a Job to the CommandBuilder dispatch method it should hit."""
    if job.IsSubtitleFix:
        return "_BuildSubtitleFixShape"
    if job.IsRemux:
        return "_BuildRemuxShape"
    return "_BuildTranscodeShape"


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def _ModeForBucket(WorkBucket):
    """Translate compliance WorkBucket to a ProcessingMode the regression test should exercise."""
    if WorkBucket == 'Transcode':
        return 'Transcode'
    if WorkBucket in ('Remux', 'AudioFixOnly'):
        return 'Quick'
    return 'Transcode'


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def run():
    """Smoke-test CommandBuilder.BuildFFmpegCommand for a fixed set of MediaFileIds; no FFmpeg invocation, no disk writes."""
    dm = DatabaseManager()
    print("=" * 72)
    print("Command Builder Smoke Test")
    print("=" * 72)
    for mid in SAMPLE_IDS:
        mf = dm.GetMediaFileById(mid)
        if not mf:
            print(f"\n!! MediaFile {mid} not found, skipping")
            continue
        mode = _ModeForBucket(getattr(mf, 'WorkBucket', None))
        job = make_job(mid, mode, mf.StorageRootId, mf.RelativePath or "")
        print(f"\n--- MediaFile {mid} ---")
        print(f"  Resolution={mf.Resolution} Codec={mf.Codec} AudioCodec={mf.AudioCodec} AudioChannels={getattr(mf, 'AudioChannels', '?')}")
        print(f"  AudioComplete={mf.AudioComplete} WorkBucket={getattr(mf, 'WorkBucket', None)}")
        print(f"  ProcessingMode={mode}  IsRemux={job.IsRemux}  IsSubtitleFix={job.IsSubtitleFix}")
        print(f"  Expected dispatch: {dispatch_label(None, job)}")

        Context = {
            "FFmpegPath": MOCK_FFMPEG,
            "FFprobePath": MOCK_FFPROBE,
            "InputPath": mf.FilePath,
            "OutputDirectory": r"C:\tmp",
            "AudioStreamIndex": 0,
            "HasAudio": True,
        }
        if mode == "Transcode":
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
            Context["TargetResolution"] = mf.Resolution

        result = CommandBuilder.BuildFFmpegCommand(mf, job, Context)
        expect_audio_copy = bool(mf.AudioComplete)
        issues = check_command(f"id-{mid}", result, expect_audio_copy)
        if result:
            cmd = result.get("Command", "")
            print(f"  Command (len={len(cmd)}):")
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
