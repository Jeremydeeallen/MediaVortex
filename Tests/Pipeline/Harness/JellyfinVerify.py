"""Capture Jellyfin notify payloads in tests without firing real notifications.

Wraps `JellyfinNotifyService.NotifyJellyfin` with an intercepting proxy
that records every Updates payload to an in-memory list AND mirrors it
to a file under `Tests/Pipeline/_jellyfin_capture/`. The original
function is NOT called -- the intercept replaces the POST entirely so
tests never reach the live Jellyfin host.

The intercept is installed at `CaptureNotifyEvents()` and removed by
`NotifyCapture.Stop()`. Use as a context manager or stop explicitly.

See Tests/Pipeline/pipeline-test-harness.feature.md criteria 13-14.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Services import JellyfinNotifyService


CAPTURE_ROOT = Path(__file__).resolve().parent.parent / '_jellyfin_capture'


@dataclass
class NotifyCapture:
    """Holds the captured notify events for a test.

    Each Event is the literal Updates list passed to NotifyJellyfin
    (a list of {Path, UpdateType} dicts), plus a CapturedAt epoch.
    """
    Events: List[Dict[str, Any]] = field(default_factory=list)
    StartedAt: float = field(default_factory=time.time)
    CaptureFilePath: str = ""
    _OriginalNotify: Optional[Any] = None

    def Stop(self) -> None:
        """Restore the original NotifyJellyfin function."""
        if self._OriginalNotify is not None:
            JellyfinNotifyService.NotifyJellyfin = self._OriginalNotify
            self._OriginalNotify = None
        # Persist final state to file
        if self.CaptureFilePath:
            try:
                with open(self.CaptureFilePath, 'w', encoding='utf-8') as F:
                    json.dump({'Events': self.Events, 'StartedAt': self.StartedAt}, F, indent=2)
            except OSError as Ex:
                LoggingService.LogWarning(
                    f"Could not persist capture file {self.CaptureFilePath}: {Ex}",
                    "JellyfinVerify", "Stop",
                )

    def __enter__(self):
        return self

    def __exit__(self, ExcType, ExcVal, ExcTb):
        self.Stop()
        return False


def CaptureNotifyEvents() -> NotifyCapture:
    """Start a capture: intercept NotifyJellyfin calls.

    The intercept replaces `JellyfinNotifyService.NotifyJellyfin` with
    a recorder that captures the Updates payload and does NOT call the
    original function -- so no HTTP request reaches Jellyfin during the
    test. Returns a `NotifyCapture` handle. Call `.Stop()` (or use as a
    context manager) to restore the original function.
    """
    Capture = NotifyCapture()

    CAPTURE_ROOT.mkdir(parents=True, exist_ok=True)
    Stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    Capture.CaptureFilePath = str(CAPTURE_ROOT / f"capture-{Stamp}.json")

    Capture._OriginalNotify = JellyfinNotifyService.NotifyJellyfin
    EventsRef = Capture.Events

    def Intercept(Updates: List[Dict[str, str]], Db: Optional[DatabaseService] = None) -> None:
        try:
            EventsRef.append({
                'Updates': [dict(U) for U in (Updates or [])],
                'CapturedAt': time.time(),
            })
        except Exception:
            pass

    JellyfinNotifyService.NotifyJellyfin = Intercept
    LoggingService.LogInfo(
        f"NotifyCapture started; events will go to {Capture.CaptureFilePath}",
        "JellyfinVerify", "CaptureNotifyEvents",
    )
    return Capture


def AssertNotifyFired(
    Capture: NotifyCapture,
    CanonicalPath: str,
    UpdateType: str = 'Modified',
    SinceTs: Optional[float] = None,
) -> None:
    """Assert at least one captured event matches the canonical path + type.

    `CanonicalPath` is the path BEFORE Jellyfin translation. The intercept
    captures the raw Updates list passed to NotifyJellyfin (pre-translate).
    """
    if SinceTs is None:
        SinceTs = 0.0
    Matches = []
    Normalized = CanonicalPath.lower()
    for Event in Capture.Events:
        if Event.get('CapturedAt', 0.0) < SinceTs:
            continue
        for U in Event.get('Updates', []):
            UPath = (U.get('Path') or '').lower()
            UType = U.get('UpdateType') or ''
            if UPath == Normalized and UType == UpdateType:
                Matches.append(U)
    if not Matches:
        AllPaths = sorted({
            (U.get('Path') or '', U.get('UpdateType') or '')
            for E in Capture.Events for U in E.get('Updates', [])
            if E.get('CapturedAt', 0.0) >= SinceTs
        })
        raise AssertionError(
            f"No captured Jellyfin notify for path={CanonicalPath!r}, "
            f"UpdateType={UpdateType!r}, since={SinceTs}. "
            f"Captured events since that timestamp: {AllPaths!r}"
        )
