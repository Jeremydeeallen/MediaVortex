# directive: e2e-bug-fixes -- one-off Sonarr delete + re-search for Heroes S01E08-E23
import json
import sys
import urllib.request


SONARR_URL = 'http://10.0.0.137:8989/sonarr'
SONARR_KEY = 'aeeda73d7ac94af7bd71c98045b21695'
SERIES_FOLDER = 'Heroes'
SEASON = 1
EPISODE_RANGE = range(8, 24)


def _Get(Url):
    Req = urllib.request.Request(Url, headers={'X-Api-Key': SONARR_KEY})
    with urllib.request.urlopen(Req, timeout=30) as R:
        return json.loads(R.read().decode('utf-8'))


def _Delete(Url):
    Req = urllib.request.Request(Url, method='DELETE', headers={'X-Api-Key': SONARR_KEY})
    with urllib.request.urlopen(Req, timeout=30) as R:
        return R.status


def _Post(Url, Body):
    Req = urllib.request.Request(
        Url, method='POST', data=json.dumps(Body).encode('utf-8'),
        headers={'X-Api-Key': SONARR_KEY, 'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(Req, timeout=30) as R:
        return R.status, json.loads(R.read().decode('utf-8'))


def Main():
    Execute = '--execute' in sys.argv
    print(f"Mode: {'EXECUTE' if Execute else 'DRY-RUN'}")
    Series = _Get(f"{SONARR_URL}/api/v3/series")
    Match = next((S for S in Series if (S.get('path') or '').rstrip('/').split('/')[-1] == SERIES_FOLDER), None)
    if not Match:
        raise SystemExit(f"Sonarr series folder {SERIES_FOLDER!r} not found")
    SeriesId = Match['id']
    print(f"Sonarr seriesId={SeriesId} ({Match.get('title')})")
    Eps = _Get(f"{SONARR_URL}/api/v3/episode?seriesId={SeriesId}")
    Targets = [E for E in Eps if E.get('seasonNumber') == SEASON and E.get('episodeNumber') in EPISODE_RANGE]
    print(f"Matched {len(Targets)} episodes (S{SEASON:02d}E{min(EPISODE_RANGE):02d}-E{max(EPISODE_RANGE):02d})")
    EpisodeIds = [E['id'] for E in Targets]
    FileIds = [E['episodeFileId'] for E in Targets if E.get('episodeFileId')]
    print(f"  Existing episodeFileIds to delete: {len(FileIds)}")
    print(f"  All episode ids: {len(EpisodeIds)}")
    if not Execute:
        print("Dry-run. Pass --execute to actually delete + search.")
        return
    Deleted = 0
    for Fid in FileIds:
        Status = _Delete(f"{SONARR_URL}/api/v3/episodefile/{Fid}")
        print(f"  DELETE episodefile/{Fid} -> {Status}")
        Deleted += 1 if Status in (200, 204) else 0
    print(f"Deleted {Deleted}/{len(FileIds)} files.")
    Status, Body = _Post(f"{SONARR_URL}/api/v3/command", {"name": "EpisodeSearch", "episodeIds": EpisodeIds})
    print(f"EpisodeSearch triggered -> status={Status} commandId={Body.get('id')}")


if __name__ == '__main__':
    Main()
