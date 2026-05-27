"""Outbound Jellyfin push-notify on file mutations.

Owns jellyfin-push-notify.feature.md. The public surface is two functions:

    TranslateForJellyfin(CanonicalPath) -> Optional[str]
    NotifyJellyfin(Updates) -> None

Callers in Features/Services that mutate a media file (rename, replace,
delete) pass canonical (Windows-shaped) paths plus an UpdateType; this
module translates them to the path Jellyfin sees on its own host (via the
synthetic `__jellyfin__` worker in StorageRootResolutions) and POSTs one
batched request to Jellyfin's `/Library/Media/Updated` endpoint.

Failure is non-fatal by design (criterion 4). MediaVortex correctness does
NOT depend on Jellyfin acknowledging the notify -- a missed notify just
means Jellyfin will pick the change up on its next safety-net scan.

Config (SystemSettings rows, criterion 6 -- shares the credentials with
Features/Optimization/JellyfinService so the operator manages one set of
Jellyfin creds, not two):
    JellyfinHost             hostname or IP (e.g. 10.0.0.179)
    JellyfinApiPort          HTTP API port (e.g. 8096, default if blank)
    JellyfinApiKey           X-Emby-Token value

Settings are read fresh from the DB on every NotifyJellyfin call. Cached
snapshots are not used -- per the "don't cache DB-backed settings" rule,
they have caused silent bugs in the past (operator flips a setting and
the running process keeps the old value).
"""

from typing import Dict, List, Optional

from Core.Logging.LoggingService import LoggingService

_COMPONENT = "JellyfinNotifyService"
_JELLYFIN_WORKER_NAME = "__jellyfin__"
_LOG_PREFIX = "JellyfinNotify:"
_HTTP_TIMEOUT_SECONDS = 5
_DEFAULT_API_PORT = "8096"

UPDATE_TYPES = ("Created", "Modified", "Deleted")

SETTING_HOST = "JellyfinHost"
SETTING_API_PORT = "JellyfinApiPort"
SETTING_API_KEY = "JellyfinApiKey"


def _ReadSetting(SettingKey: str) -> str:
    """Read a SystemSettings row fresh. Returns '' on miss or error -- the
    caller treats empty-string the same as missing."""
    try:
        from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository
        Value = SystemSettingsRepository().GetSystemSetting(SettingKey)
        return (Value or '').strip()
    except Exception as Ex:
        LoggingService.LogException(
            f"{_LOG_PREFIX} failed to read SystemSettings.{SettingKey}",
            Ex, _COMPONENT, "_ReadSetting",
        )
        return ''


def TranslateForJellyfin(CanonicalPath: str, Db=None) -> Optional[str]:
    """Translate a canonical (Windows-shaped) DB path to the path Jellyfin
    sees on its own host. Returns None when the path does not match any
    StorageRoot or no `__jellyfin__` resolution exists for that root
    (caller should log + skip, never raise)."""
    if not CanonicalPath:
        return None
    try:
        from Core.PathStorage import LoadStorageRoots, Parse as PathParse, Resolve as PathResolve, PathStorageError
        SrId, Rel = PathParse(CanonicalPath, LoadStorageRoots(Db))
        if SrId is None:
            return None
        try:
            return PathResolve(SrId, Rel or '', _JELLYFIN_WORKER_NAME, Db)
        except PathStorageError:
            return None
    except Exception as Ex:
        LoggingService.LogException(
            f"{_LOG_PREFIX} translate failed for {CanonicalPath!r}",
            Ex, _COMPONENT, "TranslateForJellyfin",
        )
        return None


def NotifyJellyfin(Updates: List[Dict[str, str]], Db=None) -> None:
    """POST a batched library-update notification to Jellyfin.

    Each Update is `{"Path": <canonical path>, "UpdateType": "Created"|"Modified"|"Deleted"}`.
    Canonical paths are translated to Jellyfin-host paths before the POST.
    Entries that cannot be translated are dropped with a WARNING (the rest
    of the batch is still sent). All failure modes are swallowed: this
    function never raises and never blocks the caller's business logic."""
    if not Updates:
        return

    Translated: List[Dict[str, str]] = []
    Skipped: List[Dict[str, str]] = []
    for Entry in Updates:
        CanonicalPath = Entry.get('Path') or ''
        UpdateType = Entry.get('UpdateType') or ''
        if UpdateType not in UPDATE_TYPES:
            LoggingService.LogWarning(
                f"{_LOG_PREFIX} dropping entry with invalid UpdateType={UpdateType!r} "
                f"for path {CanonicalPath!r} (expected one of {UPDATE_TYPES})",
                _COMPONENT, "NotifyJellyfin",
            )
            continue
        JellyfinPath = TranslateForJellyfin(CanonicalPath, Db)
        if JellyfinPath is None:
            Skipped.append({'Path': CanonicalPath, 'UpdateType': UpdateType})
            continue
        Translated.append({'Path': JellyfinPath, 'UpdateType': UpdateType})

    if Skipped:
        LoggingService.LogWarning(
            f"{_LOG_PREFIX} skipped {len(Skipped)} update(s) with no __jellyfin__ "
            f"resolution: {Skipped!r}",
            _COMPONENT, "NotifyJellyfin",
        )

    if not Translated:
        return

    Host = _ReadSetting(SETTING_HOST)
    ApiKey = _ReadSetting(SETTING_API_KEY)
    if not Host or not ApiKey:
        LoggingService.LogWarning(
            f"{_LOG_PREFIX} SystemSettings.{SETTING_HOST} or .{SETTING_API_KEY} unset; "
            f"dropping {len(Translated)} update(s)",
            _COMPONENT, "NotifyJellyfin",
        )
        return

    Port = _ReadSetting(SETTING_API_PORT) or _DEFAULT_API_PORT

    try:
        import requests
        Endpoint = f"http://{Host}:{Port}/Library/Media/Updated"
        Response = requests.post(
            Endpoint,
            headers={'X-Emby-Token': ApiKey},
            json={'Updates': Translated},
            timeout=_HTTP_TIMEOUT_SECONDS,
        )
        if 200 <= Response.status_code < 300:
            LoggingService.LogInfo(
                f"{_LOG_PREFIX} sent {len(Translated)} update(s), status={Response.status_code}",
                _COMPONENT, "NotifyJellyfin",
            )
        else:
            LoggingService.LogWarning(
                f"{_LOG_PREFIX} non-2xx status={Response.status_code} for "
                f"{len(Translated)} update(s); body={Response.text[:200]!r}",
                _COMPONENT, "NotifyJellyfin",
            )
    except Exception as Ex:
        LoggingService.LogWarning(
            f"{_LOG_PREFIX} POST failed ({type(Ex).__name__}: {Ex}); "
            f"dropping {len(Translated)} update(s)",
            _COMPONENT, "NotifyJellyfin",
        )
