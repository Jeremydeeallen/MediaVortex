# directive: probe-loudness-remove
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE_DIR = REPO_ROOT / "Features" / "MediaProbe"


def _grep_count(pattern: str, path: Path) -> int:
    Result = subprocess.run(
        ["git", "grep", "-l", "-E", pattern, "--", f"{path}/*.py"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    return len([L for L in Result.stdout.splitlines() if L.strip()])


def test_probe_does_not_import_ebur128():
    assert _grep_count(r"EbuR128MeasurementService|MeasureAndPersist", PROBE_DIR) == 0


def test_probe_does_not_call_maybe_auto_mark_audio_complete():
    assert _grep_count(r"_MaybeAutoMarkAudioCompleteAtTarget", PROBE_DIR) == 0


def test_transcode_still_writes_source_loudness():
    Facade = REPO_ROOT / "Features" / "AudioNormalization" / "Services" / "AudioPreEncodeFacade.py"
    Text = Facade.read_text(encoding="utf-8")
    assert "SourceIntegratedLufs=%s" in Text
