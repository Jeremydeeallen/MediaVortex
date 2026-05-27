"""One-shot dry-run of JellyfinNotifyService against real DB paths.

Renders what NotifyJellyfin WOULD send for a set of sample paths, without
firing any HTTP. Uses `TranslateForJellyfin` directly so the only thing
exercised is the per-StorageRoot mapping -- no requests.post call is made.

Owns jellyfin-push-notify.feature.md criterion 2 verification step:
confirm the notify payload for a replaced file matches the absolute path
on the Jellyfin host.

This is the supported "preview" path -- the runtime `JellyfinNotifyDryRun`
SystemSettings gate was removed 2026-05-27 because a downstream-of-state-
change notification must not be silenceable. Operator preview belongs in
an off-pipeline script (this file), not in production code.
"""

import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from Services.JellyfinNotifyService import TranslateForJellyfin, UPDATE_TYPES


SAMPLES = [
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


def _RenderWouldBeBatch(Updates: List[Dict[str, str]]) -> None:
    """Show what NotifyJellyfin would send, without sending it."""
    if not Updates:
        print("  (no updates)")
        return
    Translated, Dropped = [], []
    for Entry in Updates:
        Path = Entry.get('Path') or ''
        UpdateType = Entry.get('UpdateType') or ''
        if UpdateType not in UPDATE_TYPES:
            Dropped.append((Path, UpdateType, 'invalid UpdateType'))
            continue
        JellyfinPath = TranslateForJellyfin(Path)
        if JellyfinPath is None:
            Dropped.append((Path, UpdateType, 'no __jellyfin__ resolution'))
            continue
        Translated.append({'Path': JellyfinPath, 'UpdateType': UpdateType})
    for Path, UpdateType, Reason in Dropped:
        print(f"  DROP  {Path!r} (UpdateType={UpdateType!r}): {Reason}")
    if Translated:
        print(f"  WOULD POST {len(Translated)} update(s): {{'Updates': {Translated!r}}}")
    else:
        print("  (no translatable updates -- would skip POST entirely)")


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
        _RenderWouldBeBatch(Updates)


if __name__ == '__main__':
    Main()
