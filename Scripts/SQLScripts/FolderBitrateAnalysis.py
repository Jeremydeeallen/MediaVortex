"""Group MediaFiles by folder (last directory in FilePath) and rank by bitrate.

Surfaces candidate test sources for the EncodeAndVmaf harness: folders where
files cluster tightly at high bitrate are likely single-release-team packs.
"""

import os
import sys
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from Core.Database.DatabaseService import DatabaseService


def FolderOf(P):
    if not P:
        return ''
    Idx = max(P.rfind('\\'), P.rfind('/'))
    return P[:Idx] if Idx > 0 else ''


def Main(MinFiles=3, MinMeanKbps=0, Resolution=None, Limit=40):
    Db = DatabaseService()
    Sql = """
        SELECT FilePath, VideoBitrateKbps, ResolutionCategory, FileSize
        FROM MediaFiles
        WHERE VideoBitrateKbps > 0 AND TranscodedByMediaVortex IS NOT TRUE
    """
    Args = ()
    if Resolution:
        Sql += " AND ResolutionCategory = %s"
        Args = (Resolution,)
    Rows = Db.ExecuteQuery(Sql, Args)
    print(f"Surveyed {len(Rows)} files.")

    Buckets = {}
    for R in Rows:
        F = FolderOf(R['FilePath'])
        if not F:
            continue
        Buckets.setdefault(F, []).append({
            'Bitrate': R['VideoBitrateKbps'],
            'Resolution': R['ResolutionCategory'],
            'FilePath': R['FilePath'],
        })

    Stats = []
    for F, Files in Buckets.items():
        if len(Files) < MinFiles:
            continue
        Brs = [X['Bitrate'] for X in Files]
        Mean = sum(Brs) / len(Brs)
        if Mean < MinMeanKbps:
            continue
        Var = sum((B - Mean) ** 2 for B in Brs) / len(Brs)
        Std = math.sqrt(Var)
        Cv = Std / Mean if Mean else 0
        Resolutions = list(set(X['Resolution'] for X in Files))
        Stats.append({
            'Folder': F,
            'FileCount': len(Files),
            'MeanKbps': round(Mean),
            'MinKbps': min(Brs),
            'MaxKbps': max(Brs),
            'Cv': round(Cv, 3),
            'Resolutions': ','.join(R for R in Resolutions if R),
            'Files': Files,
        })

    Stats.sort(key=lambda S: (-S['MeanKbps'], S['Cv']))

    print(f"\nTop {Limit} folders (>= {MinFiles} files, mean >= {MinMeanKbps} kbps"
          + (f", res={Resolution}" if Resolution else "")
          + "), ranked by mean bitrate DESC then CV ASC:\n")
    print(f"{'MeanKbps':>9} {'Cv':>5} {'Min':>6} {'Max':>6} {'N':>3} {'Res':<14} Folder")
    print(f"{'-'*9} {'-'*5} {'-'*6} {'-'*6} {'-'*3} {'-'*14} {'-'*80}")
    for S in Stats[:Limit]:
        FolderDisplay = S['Folder']
        if len(FolderDisplay) > 80:
            FolderDisplay = '...' + FolderDisplay[-77:]
        print(f"{S['MeanKbps']:>9} {S['Cv']:>5.3f} {S['MinKbps']:>6} {S['MaxKbps']:>6} "
              f"{S['FileCount']:>3} {S['Resolutions'][:14]:<14} {FolderDisplay}")

    return Stats


if __name__ == "__main__":
    Res = None
    MinMean = 0
    for Arg in sys.argv[1:]:
        if Arg.startswith('--res='):
            Res = Arg.split('=', 1)[1]
        elif Arg.startswith('--min='):
            MinMean = int(Arg.split('=', 1)[1])
    Main(Resolution=Res, MinMeanKbps=MinMean)
