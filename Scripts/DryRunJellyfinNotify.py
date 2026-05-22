"""One-shot dry-run of JellyfinNotifyService against real DB paths.

Forces `JellyfinNotifyDryRun=true` for the duration of this script (via a
patch of `_ReadSetting`) so the rendered payload is visible without
flipping the SystemSettings row or producing any outbound HTTP. No
DB state is mutated.

Owns jellyfin-push-notify.feature.md criterion 2 verification step:
confirm the notify payload for a replaced file matches the absolute path
on the Jellyfin host.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from Core.Logging.LoggingService import LoggingService
from Services import JellyfinNotifyService
from Services.JellyfinNotifyService import NotifyJellyfin, TranslateForJellyfin


# Force DryRun=true regardless of what SystemSettings currently says, so
# this script can never POST. URL/Token are irrelevant in dry-run path.
def _ForcedSettingRead(SettingKey: str) -> str:
    if SettingKey == JellyfinNotifyService.SETTING_DRY_RUN:
        return 'true'
    return ''


JellyfinNotifyService._ReadSetting = _ForcedSettingRead


# Echo log calls to stdout so we can see the rendered payload.
_OrigInfo = LoggingService.LogInfo
_OrigWarn = LoggingService.LogWarning


def _EchoInfo(cls_or_msg, *Args, **Kwargs):
    if isinstance(cls_or_msg, type):
        Msg = Args[0] if Args else ''
    else:
        Msg = cls_or_msg
    print(f"[INFO ] {Msg}")
    return _OrigInfo(cls_or_msg, *Args, **Kwargs)


def _EchoWarn(cls_or_msg, *Args, **Kwargs):
    if isinstance(cls_or_msg, type):
        Msg = Args[0] if Args else ''
    else:
        Msg = cls_or_msg
    print(f"[WARN ] {Msg}")
    return _OrigWarn(cls_or_msg, *Args, **Kwargs)


LoggingService.LogInfo = classmethod(lambda cls, Msg, *a, **kw: (print(f"[INFO ] {Msg}"), _OrigInfo(Msg, *a, **kw))[1])
LoggingService.LogWarning = classmethod(lambda cls, Msg, *a, **kw: (print(f"[WARN ] {Msg}"), _OrigWarn(Msg, *a, **kw))[1])


# --- Test set: one real path per StorageRoot, plus deliberate edge cases. ---
SAMPLES = [
    # (Description, Updates)
    (
        "1. Single Modified, media_tv (T:)",
        [{
            'Path': r"T:\The Walking Dead\Season 1\The Walking Dead - S01E04 - Vatos Bluray-720p-mv.mp4",
            'UpdateType': 'Modified',
        }],
    ),
    (
        "2. Single Modified, movies (M:)",
        [{
            'Path': r"M:\Saving Private Ryan (1998)\Saving Private Ryan (1998) Bluray-2160p.mkv",
            'UpdateType': 'Modified',
        }],
    ),
    (
        "3. Single Modified, xxx (Z:)",
        [{
            'Path': r"Z:\Videos\Anal\Anal-Beauty.25.12.26.Olivia.Westsun.XXX.720p.MP4-WRB.28.mp4",
            'UpdateType': 'Modified',
        }],
    ),
    (
        "4. Batched: Deleted (old extension) + Created (new extension), media_tv",
        [
            {'Path': r"T:\Bluey (2018)\Season 1\Bluey (2018) - S01E50 - Shaun.mkv", 'UpdateType': 'Deleted'},
            {'Path': r"T:\Bluey (2018)\Season 1\Bluey (2018) - S01E50 - Shaun SDTV-mv.mp4", 'UpdateType': 'Created'},
        ],
    ),
    (
        "5. Non-canonical path (not under any StorageRoot)",
        [{'Path': r"C:\Some\Other\Path\file.mkv", 'UpdateType': 'Modified'}],
    ),
    (
        "6. Path with non-ASCII characters",
        [{
            'Path': r"T:\Pokémon\Season 9\Pokémon - S09E22 - What I Did For Love! DVD-mv.mp4",
            'UpdateType': 'Modified',
        }],
    ),
    (
        "7. Invalid UpdateType",
        [{'Path': r"T:\foo.mkv", 'UpdateType': 'Updated'}],
    ),
    (
        "8. Empty input",
        [],
    ),
]


def _Header(Text):
    print()
    print("=" * 80)
    print(Text)
    print("=" * 80)


def Main():
    _Header("Per-path translation check (TranslateForJellyfin -> Jellyfin host path)")
    for Description, Updates in SAMPLES[:6]:
        if not Updates:
            continue
        for Entry in Updates:
            Translated = TranslateForJellyfin(Entry['Path'])
            print(f"  {Entry['Path']}")
            print(f"    -> {Translated}")

    for Description, Updates in SAMPLES:
        _Header(Description)
        NotifyJellyfin(Updates)


if __name__ == '__main__':
    Main()
