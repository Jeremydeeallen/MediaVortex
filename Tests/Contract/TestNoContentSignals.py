# directive: bug-0086-content-signals-remove
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE_DIR = REPO_ROOT / "Features" / "MediaProbe"
CLASSIFIER_DIR = REPO_ROOT / "Features" / "ContentClassifier"
PROD_DIRS = ["Features", "Workers", "WorkerService", "WebService", "Repositories", "Core"]


def _grep_count(pattern: str, *paths: str) -> int:
    Args = ["git", "grep", "-l", "-E", pattern, "--"]
    for P in paths:
        Args.append(f"{P}/*.py")
    Result = subprocess.run(Args, cwd=str(REPO_ROOT), capture_output=True, text=True)
    return len([L for L in Result.stdout.splitlines() if L.strip()])


def test_probe_does_not_import_content_signals():
    assert _grep_count(r"ContentSignalsService|ContentSignalsRepository|ContentSignalsModel", "Features/MediaProbe") == 0


def test_content_signals_vertical_deleted():
    assert not (REPO_ROOT / "Features" / "ContentSignals").exists()


def test_classifier_has_no_signal_fields():
    assert _grep_count(r"MotionFraction|SceneChangeRatePerMin|LumaVariance", "Features/ContentClassifier") == 0


def test_no_scenedetect_imports_in_production():
    assert _grep_count(r"^\s*from scenedetect|^\s*import scenedetect", *PROD_DIRS) == 0


def test_scenedetect_removed_from_requirements():
    Text = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "scenedetect" not in Text.lower()
