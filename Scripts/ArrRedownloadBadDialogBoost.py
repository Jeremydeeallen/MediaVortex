# Dry-run + delete-and-redownload for the 88 files with bad Dialog Boost content.

import argparse
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Core.Database.DatabaseService import DatabaseService, EscapeLikePattern

SONARR_URL = 'http://10.0.0.137:8989/sonarr'
SONARR_KEY = 'aeeda73d7ac94af7bd71c98045b21695'
RADARR_URL = 'http://10.0.0.137:7878/radarr'
RADARR_KEY = 'e4fadd3674b44df6b432e96cede83935'


def _Get(Url, Key):
    Req = urllib.request.Request(Url, headers={'X-Api-Key': Key})
    with urllib.request.urlopen(Req, timeout=30) as R:
        return json.loads(R.read().decode('utf-8'))


def _Delete(Url, Key):
    Req = urllib.request.Request(Url, method='DELETE', headers={'X-Api-Key': Key})
    with urllib.request.urlopen(Req, timeout=30) as R:
        return R.status, R.read().decode('utf-8')


def _Post(Url, Key, Body):
    Req = urllib.request.Request(
        Url, method='POST', data=json.dumps(Body).encode('utf-8'),
        headers={'X-Api-Key': Key, 'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(Req, timeout=30) as R:
        return R.status, json.loads(R.read().decode('utf-8'))


def _ExtractSE(FileName):
    M = re.search(r'S(\d+)E(\d+)', FileName)
    if M:
        return int(M.group(1)), int(M.group(2))
    return None, None


def Main():
    P = argparse.ArgumentParser()
    P.add_argument('--execute', action='store_true', help='Actually delete + trigger search (default is dry-run).')
    Args = P.parse_args()

    Db = DatabaseService()
    # Underscore in dialog_boost_premix.wav is a LIKE wildcard; escape it with ESCAPE '!' per rule R9.
    Needle = '%' + EscapeLikePattern('dialog_boost_premix.wav') + '%'
    Rows = Db.ExecuteQuery(
        "SELECT mf.Id, mf.RelativePath "
        "FROM TranscodeAttempts ta "
        "JOIN MediaFiles mf ON mf.Id = ta.MediaFileId "
        "WHERE ta.Success = TRUE "
        "  AND ta.FfpmpegCommand LIKE %s ESCAPE '!' "
        "  AND ta.FfpmpegCommand ~ %s "
        "  AND ta.Id = (SELECT MAX(ta2.Id) FROM TranscodeAttempts ta2 WHERE ta2.MediaFileId = ta.MediaFileId AND ta2.Success = TRUE) "
        "ORDER BY mf.RelativePath",
        (Needle, '-metadata:s:a:0 "language=(?!eng)[a-z]{3}"'),
    )
    print(f"Loaded {len(Rows)} affected MediaFiles from DB.")

    print("Fetching Sonarr series index...")
    Series = _Get(f"{SONARR_URL}/api/v3/series", SONARR_KEY)
    # Index by disk-folder tail (Sonarr sanitizes ':', '?', etc.). MediaVortex RelativePath first segment is the on-disk folder; match against Sonarr's series.path last component.
    TitleToId = {}
    for S in Series:
        Folder = (S.get('path') or '').replace('\\', '/').rstrip('/').split('/')[-1]
        if Folder:
            TitleToId[Folder] = S['id']
    print(f"  Sonarr series indexed by disk folder: {len(TitleToId)}")

    SeriesEpisodeCache = {}

    Actions = []
    NotMatched = []
    for R in Rows:
        Rel = R['RelativePath']
        Parts = Rel.replace('\\', '/').split('/')
        if len(Parts) < 3:
            NotMatched.append((Rel, 'path-shape (too shallow)'))
            continue
        SeriesFolder = Parts[0]
        FileName = Parts[-1]
        SeriesId = TitleToId.get(SeriesFolder)
        if SeriesId is None:
            NotMatched.append((Rel, f'series title not in Sonarr: {SeriesFolder!r}'))
            continue
        Season, Episode = _ExtractSE(FileName)
        if Season is None:
            NotMatched.append((Rel, f'no SxxExx in filename'))
            continue
        if SeriesId not in SeriesEpisodeCache:
            SeriesEpisodeCache[SeriesId] = _Get(f"{SONARR_URL}/api/v3/episode?seriesId={SeriesId}", SONARR_KEY)
        Eps = SeriesEpisodeCache[SeriesId]
        Match = next((E for E in Eps if E['seasonNumber'] == Season and E['episodeNumber'] == Episode), None)
        if Match is None:
            NotMatched.append((Rel, f'S{Season:02d}E{Episode:02d} not in Sonarr for seriesId={SeriesId}'))
            continue
        Actions.append({
            'MediaFileId': R['Id'],
            'Rel': Rel,
            'SeriesId': SeriesId,
            'SeriesTitle': SeriesFolder,
            'Season': Season,
            'Episode': Episode,
            'EpisodeId': Match['id'],
            'EpisodeFileId': Match.get('episodeFileId') or 0,
        })

    print(f"\nMatched {len(Actions)} in Sonarr; unmatched {len(NotMatched)}.")
    print("\n=== Unmatched (skipped) ===")
    for Rel, Reason in NotMatched:
        print(f"  {Reason}: {Rel[:90]}")

    print("\n=== Sonarr actions (first 20) ===")
    for A in Actions[:20]:
        print(f"  {A['SeriesTitle'][:30]:30s} S{A['Season']:02d}E{A['Episode']:02d}  epFileId={A['EpisodeFileId']:7d}  mfId={A['MediaFileId']}")
    if len(Actions) > 20:
        print(f"  ... and {len(Actions) - 20} more")

    if not Args.execute:
        print(f"\nDRY RUN. Would DELETE {sum(1 for A in Actions if A['EpisodeFileId'])} episodefiles + trigger {len(Actions)} EpisodeSearch commands.")
        print("Re-run with --execute to perform.")
        return

    print(f"\n=== EXECUTING on {len(Actions)} episodes ===")
    Deleted = 0
    Searched = 0
    Errors = []
    for A in Actions:
        Prefix = f"{A['SeriesTitle'][:30]:30s} S{A['Season']:02d}E{A['Episode']:02d}"
        if A['EpisodeFileId']:
            try:
                Status, _Body = _Delete(f"{SONARR_URL}/api/v3/episodefile/{A['EpisodeFileId']}", SONARR_KEY)
                if Status in (200, 202):
                    Deleted += 1
                    print(f"  [DEL ] {Prefix}  epFileId={A['EpisodeFileId']}")
                else:
                    Errors.append((Prefix, f"delete status {Status}"))
                    print(f"  [FAIL] {Prefix}  delete rc={Status}")
                    continue
            except Exception as Ex:
                Errors.append((Prefix, f"delete exception: {Ex}"))
                print(f"  [FAIL] {Prefix}  delete exception: {Ex}")
                continue
        else:
            print(f"  [SKIP-DEL] {Prefix}  no episodeFileId (already missing)")

        try:
            Status, Body = _Post(f"{SONARR_URL}/api/v3/command", SONARR_KEY, {'name': 'EpisodeSearch', 'episodeIds': [A['EpisodeId']]})
            if Status in (200, 201):
                Searched += 1
                print(f"  [SRCH] {Prefix}  cmdId={Body.get('id')}")
            else:
                Errors.append((Prefix, f"search status {Status}"))
                print(f"  [FAIL] {Prefix}  search rc={Status}")
        except Exception as Ex:
            Errors.append((Prefix, f"search exception: {Ex}"))
            print(f"  [FAIL] {Prefix}  search exception: {Ex}")

    print(f"\nSummary: deleted {Deleted}, searched {Searched}, errors {len(Errors)}")
    if Errors:
        print("Errors:")
        for Prefix, Reason in Errors:
            print(f"  {Prefix}: {Reason}")


if __name__ == '__main__':
    Main()
