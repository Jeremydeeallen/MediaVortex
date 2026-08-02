# see jellyfin-push-notify.feature.md

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


# directive: path-schema-migration | # see path.S8
def TranslateForJellyfin(CanonicalPath: str, Db=None) -> Optional[str]:
    """Translate a canonical (Windows-shaped) DB path to the Jellyfin-host path via the synthetic `__jellyfin__` Worker. Returns None on no match / no resolution (caller logs + skips, never raises)."""
    if not CanonicalPath:
        return None
    try:
        from Core.Path.Path import Path, PathError
        from Core.Path.Worker import Worker
        from Core.Path.PathStorageRoots import GetStorageRoots
        try:
            Parsed = Path.FromLegacyString(CanonicalPath, GetStorageRoots())
        except PathError:
            return None
        JellyfinWorker = Worker(Name=_JELLYFIN_WORKER_NAME, Platform="linux", Db=Db)
        try:
            return Parsed.Resolve(JellyfinWorker)
        except PathError:
            return None
    except Exception as Ex:
        LoggingService.LogException(
            f"{_LOG_PREFIX} translate failed for {CanonicalPath!r}",
            Ex, _COMPONENT, "TranslateForJellyfin",
        )
        return None


def NotifyReplaced(OldCanonicalPath: str, NewCanonicalPath: str, Db=None) -> None:
    # see jellyfin-push-notify.C1 -- domain event = "file replaced". Wire shape depends on Jellyfin quirks and lives here, not in callers. Same-ext (re-transcode) uses Modified-only to avoid the same-ext orphan bug (30 Rock S02E10, commit 464d9f7d). Different-ext (mkv->mp4 first-time transcode) uses Deleted(old)+Created(new) because Jellyfin's coalescing sweep does not strip the stale old-ext entry (Heroes S02E08, 2026-08-02).
    if not NewCanonicalPath:
        return
    OldNorm = (OldCanonicalPath or '').strip()
    NewNorm = NewCanonicalPath.strip()
    if OldNorm and _ExtensionOf(OldNorm) != _ExtensionOf(NewNorm):
        NotifyJellyfin([
            {'Path': OldNorm, 'UpdateType': 'Deleted'},
            {'Path': NewNorm, 'UpdateType': 'Created'},
        ], Db)
    else:
        NotifyJellyfin([{'Path': NewNorm, 'UpdateType': 'Modified'}], Db)


def _ExtensionOf(CanonicalPath: str) -> str:
    Dot = CanonicalPath.rfind('.')
    Slash = max(CanonicalPath.rfind('/'), CanonicalPath.rfind('\\'))
    if Dot <= Slash:
        return ''
    return CanonicalPath[Dot:].lower()


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
