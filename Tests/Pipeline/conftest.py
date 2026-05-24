"""Pytest fixtures and session bootstrap for pipeline tests.

Initializes WorkerContext once per session, gates the session on
candidate availability, and exposes shared `notify_capture` and
`db_state_snapshot` helpers to tests.

See Tests/Pipeline/pipeline-test-harness.feature.md criterion 19, 22.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make MediaVortex modules importable when pytest is invoked from anywhere.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pytest

from Tests.Pipeline.Harness.Invocation import _EnsureWorkerContext
from Tests.Pipeline.Harness.JellyfinVerify import CaptureNotifyEvents
from Tests.Pipeline.Harness import Fixtures


@pytest.fixture(scope="session", autouse=True)
def worker_context():
    """Initialize WorkerContext for I9-2024 once per session."""
    _EnsureWorkerContext("I9-2024")
    yield


@pytest.fixture(scope="session", autouse=True)
def precondition_gate():
    """Abort the session if no candidates exist for the planned tests.

    Cheaper to know up front than to fail with a confusing error mid-test.
    Per criterion 22.
    """
    Failures = []
    try:
        Fixtures.QuickFixCandidate(MaxSizeMB=500, Limit=10)
    except Fixtures.NoCandidatesError as Ex:
        Failures.append(f"QuickFixCandidate: {Ex}")
    try:
        Fixtures.TranscodeCandidate(MaxSizeMB=500, Limit=10)
    except Fixtures.NoCandidatesError as Ex:
        Failures.append(f"TranscodeCandidate: {Ex}")
    if Failures:
        pytest.exit(
            "Pipeline test harness precondition failed -- no eligible "
            "candidates in the live DB:\n  " + "\n  ".join(Failures) +
            "\n\nRun the threshold backfill and verify that some MediaFiles "
            "have RecommendedMode set."
        )
    yield


@pytest.fixture
def notify_capture():
    """Per-test Jellyfin notify capture (auto-stops on test exit)."""
    Capture = CaptureNotifyEvents()
    yield Capture
    Capture.Stop()
