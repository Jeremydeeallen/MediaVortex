"""Capture Jellyfin notify payloads in tests without firing real notifications.

Wraps the JellyfinNotifyService.NotifyJellyfin function with an
intercepting proxy that records every Updates payload to an in-memory
list AND mirrors it to a file under Tests/Pipeline/_jellyfin_capture/.
The original function is still called -- but with the operator's
configured dry-run state respected via the existing service (so by
default no HTTP request goes out during tests).

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
    _PriorDryRunSetting: Optional[str] = None

    def Stop(self) -> None:
        """Restore the original NotifyJellyfin function + SystemSetting."""
        if self._OriginalNotify is not None:
            JellyfinNotifyService.NotifyJellyfin = self._OriginalNotify
            self._OriginalNotify = None
        if self._PriorDryRunSetting is not None:
            try:
                Db = DatabaseService()
                Db.ExecuteNonQuery(
                    "UPDATE SystemSettings SET SettingValue = %s "
                    "WHERE SettingKey = 'JellyfinNotifyDryRun'",
                    (self._PriorDryRunSetting,),
                )
            except Exception as Ex:
                LoggingService.LogException(
                    "Failed to restore JellyfinNotifyDryRun setting",
                    Ex, "JellyfinVerify", "Stop",
                )
            self._PriorDryRunSetting = None
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


def _ReadDryRunSetting() -> Optional[str]:
    Db = DatabaseService()
    Rows = Db.ExecuteQuery(
        "SELECT SettingValue FROM SystemSettings WHERE SettingKey = 'JellyfinNotifyDryRun'",
    )
    if not Rows:
        return None
    return str(Rows[0].get('SettingValue', '')) or None


def _SetDryRun(Value: str) -> None:
    Db = DatabaseService()
    # Insert if absent, update otherwise -- mirrors how other settings are seeded.
    Existing = _ReadDryRunSetting()
    if Existing is None:
        Now = datetime.now(timezone.utc)
        Db.ExecuteNonQuery(
            "INSERT INTO SystemSettings (SettingKey, SettingValue, DataType, Description, LastModified) "
            "VALUES ('JellyfinNotifyDryRun', %s, 'boolean', "
            "'When true, log notify payloads instead of POSTing to Jellyfin', %s)",
            (Value, Now),
        )
    else:
        Db.ExecuteNonQuery(
            "UPDATE SystemSettings SET SettingValue = %s "
            "WHERE SettingKey = 'JellyfinNotifyDryRun'",
            (Value,),
        )


def CaptureNotifyEvents() -> NotifyCapture:
    """Start a capture: enable dry-run, intercept NotifyJellyfin calls.

    Returns a NotifyCapture handle. Call `.Stop()` (or use as a context
    manager) to restore state. The capture's `.Events` list accumulates
    every Updates payload passed to NotifyJellyfin between Start and Stop.
    """
    Capture = NotifyCapture()
    Capture._PriorDryRunSetting = _ReadDryRunSetting()
    _SetDryRun('1')

    CAPTURE_ROOT.mkdir(parents=True, exist_ok=True)
    Stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    Capture.CaptureFilePath = str(CAPTURE_ROOT / f"capture-{Stamp}.json")

    Capture._OriginalNotify = JellyfinNotifyService.NotifyJellyfin

    OriginalNotify = Capture._OriginalNotify
    EventsRef = Capture.Events

    def Intercept(Updates: List[Dict[str, str]], Db: Optional[DatabaseService] = None) -> None:
        # Record first, then let the real function handle dry-run logging.
        try:
            EventsRef.append({
                'Updates': [dict(U) for U in (Updates or [])],
                'CapturedAt': time.time(),
            })
        except Exception:
            pass
        OriginalNotify(Updates, Db)

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
        # Build a helpful error showing what WAS captured
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
