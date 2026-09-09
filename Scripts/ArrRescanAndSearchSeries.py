import argparse
import json
import os
import sys
import urllib.request


SONARR_URL = 'http://10.0.0.137:8989/sonarr'
SONARR_KEY = 'aeeda73d7ac94af7bd71c98045b21695'


def _Get(Url):
    Req = urllib.request.Request(Url, headers={'X-Api-Key': SONARR_KEY})
    with urllib.request.urlopen(Req, timeout=30) as R:
        return json.loads(R.read().decode('utf-8'))


def _Post(Url, Body):
    Req = urllib.request.Request(
        Url, method='POST', data=json.dumps(Body).encode('utf-8'),
        headers={'X-Api-Key': SONARR_KEY, 'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(Req, timeout=30) as R:
        return R.status, json.loads(R.read().decode('utf-8'))


def _Put(Url, Body):
    Req = urllib.request.Request(
        Url, method='PUT', data=json.dumps(Body).encode('utf-8'),
        headers={'X-Api-Key': SONARR_KEY, 'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(Req, timeout=30) as R:
        return R.status, json.loads(R.read().decode('utf-8'))


def _MatchSeries(All, TitleSubstring, AllMonitored):
    if AllMonitored:
        return [S for S in All if S.get('monitored')]
    Sub = (TitleSubstring or '').lower()
    return [S for S in All if Sub in (S.get('title') or '').lower()]


def _ResolveQualityProfileId(NameOrId):
    Profiles = _Get(f'{SONARR_URL}/api/v3/qualityprofile')
    try:
        Wanted = int(NameOrId)
        Match = next((P for P in Profiles if P['id'] == Wanted), None)
        if Match:
            return Match['id'], Match['name']
        raise SystemExit(f'No quality profile with id={Wanted}')
    except ValueError:
        pass
    Sub = str(NameOrId).lower()
    Matches = [P for P in Profiles if Sub in P['name'].lower()]
    if not Matches:
        print(f'No quality profile matches {NameOrId!r}. Available:')
        for P in Profiles:
            print(f'  id={P["id"]:3d}  {P["name"]!r}')
        raise SystemExit(2)
    if len(Matches) > 1:
        print(f'Ambiguous profile name {NameOrId!r}. Matched:')
        for P in Matches:
            print(f'  id={P["id"]:3d}  {P["name"]!r}')
        raise SystemExit(2)
    return Matches[0]['id'], Matches[0]['name']


def Main():
    P = argparse.ArgumentParser(description='Rescan + search Sonarr series by title substring or all monitored.')
    G = P.add_mutually_exclusive_group(required=True)
    G.add_argument('--title', help='Match series with this substring in the title (case-insensitive).')
    G.add_argument('--all-monitored', action='store_true', help='Every monitored series.')
    P.add_argument('--no-rescan', action='store_true', help='Skip RescanSeries.')
    P.add_argument('--no-search', action='store_true', help='Skip SeriesSearch.')
    P.add_argument('--set-quality-profile', metavar='NAME_OR_ID', help='Assign this quality profile (name substring or id) to every matched series before rescan/search.')
    P.add_argument('--execute', action='store_true', help='Fire commands. Default is dry-run.')
    Args = P.parse_args()

    print(f'Fetching Sonarr series list from {SONARR_URL} ...')
    All = _Get(f'{SONARR_URL}/api/v3/series')
    print(f'  {len(All)} series total in Sonarr.')

    Targets = _MatchSeries(All, Args.title, Args.all_monitored)
    Profiles = _Get(f'{SONARR_URL}/api/v3/qualityprofile')
    ProfileName = {P['id']: P['name'] for P in Profiles}
    print(f'\nMatched {len(Targets)} target series:')
    for S in Targets:
        Mon = 'monitored' if S.get('monitored') else 'unmonitored'
        Qp = ProfileName.get(S['qualityProfileId'], f'?id={S["qualityProfileId"]}')
        print(f'  id={S["id"]:4d}  {Mon:12s}  qp={Qp!r:35s}  {S["title"]!r}')

    if not Targets:
        print('\nNothing to do.')
        return

    Rescan = not Args.no_rescan
    Search = not Args.no_search
    Ops = []
    if Rescan:
        Ops.append('RescanSeries')
    if Search:
        Ops.append('SeriesSearch')
    print(f'\nOperations to run per series: {", ".join(Ops) if Ops else "(none)"}')

    TargetProfileId = None
    TargetProfileName = None
    if Args.set_quality_profile:
        TargetProfileId, TargetProfileName = _ResolveQualityProfileId(Args.set_quality_profile)
        NeedSwitch = [S for S in Targets if S['qualityProfileId'] != TargetProfileId]
        print(f'\nWill switch {len(NeedSwitch)}/{len(Targets)} series to quality profile id={TargetProfileId} name={TargetProfileName!r}')

    if not Args.execute:
        Total = len(Targets) * len(Ops)
        if TargetProfileId is not None:
            Total += len([S for S in Targets if S['qualityProfileId'] != TargetProfileId])
        print(f'\nDRY RUN. Would fire {Total} operations.')
        print('Re-run with --execute to send.')
        return

    if TargetProfileId is not None:
        Switched = 0
        for S in Targets:
            if S['qualityProfileId'] == TargetProfileId:
                continue
            S['qualityProfileId'] = TargetProfileId
            try:
                Status, Body = _Put(f'{SONARR_URL}/api/v3/series/{S["id"]}', S)
                if Status in (200, 202):
                    Switched += 1
                    print(f'  [qp-set] id={S["id"]}  -> {TargetProfileName!r}  {S["title"]!r}')
                else:
                    print(f'  [FAIL qp-set] id={S["id"]}  rc={Status}  {S["title"]!r}')
            except Exception as Ex:
                print(f'  [FAIL qp-set] id={S["id"]}  exception: {Ex}  {S["title"]!r}')
        print(f'  Quality-profile switch summary: {Switched} switched')

    Fired = 0
    Errors = []
    for S in Targets:
        for Op in Ops:
            try:
                Status, Body = _Post(f'{SONARR_URL}/api/v3/command', {'name': Op, 'seriesId': S['id']})
                if Status in (200, 201):
                    print(f'  [{Op}] id={S["id"]}  cmdId={Body.get("id")}  {S["title"]!r}')
                    Fired += 1
                else:
                    Errors.append((S['title'], Op, f'status {Status}'))
                    print(f'  [FAIL {Op}] id={S["id"]}  rc={Status}  {S["title"]!r}')
            except Exception as Ex:
                Errors.append((S['title'], Op, str(Ex)))
                print(f'  [FAIL {Op}] id={S["id"]}  exception: {Ex}  {S["title"]!r}')

    print(f'\nSummary: fired {Fired}, errors {len(Errors)}')
    if Errors:
        for T, O, E in Errors:
            print(f'  {T!r} {O}: {E}')


if __name__ == '__main__':
    Main()
