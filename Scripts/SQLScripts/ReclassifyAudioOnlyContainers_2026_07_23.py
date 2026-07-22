import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService
from Features.MediaFile.Domain.MediaFileScope import AUDIO_ONLY_CONTAINERS


# directive: transcode-flow-canonical -- C34
def Main() -> int:
    Db = DatabaseService()
    Placeholders = ','.join(['%s'] * len(AUDIO_ONLY_CONTAINERS))
    Params = tuple(sorted(AUDIO_ONLY_CONTAINERS))

    Before = Db.ExecuteQuery(
        f"SELECT COUNT(*) AS N FROM MediaFiles "
        f"WHERE ContainerFormat IN ({Placeholders}) "
        f"AND WorkBucket IN ('Transcode','Remux','AudioFix')",
        Params,
    )
    BeforeCount = int((Before[0].get('N') if Before else 0) or 0)
    print(f"[C34] mp3-family rows currently in Transcode/Remux/AudioFix: {BeforeCount}")

    Db.ExecuteNonQuery(
        f"UPDATE MediaFiles SET "
        f"VideoCompliant = NULL, VideoCompliantReason = 'non_video_scope', "
        f"ContainerCompliant = NULL, ContainerCompliantReason = 'non_video_scope', "
        f"AudioCompliant = NULL, AudioCompliantReason = 'non_video_scope' "
        f"WHERE ContainerFormat IN ({Placeholders})",
        Params,
    )

    After = Db.ExecuteQuery(
        f"SELECT COUNT(*) AS N FROM MediaFiles "
        f"WHERE ContainerFormat IN ({Placeholders}) "
        f"AND WorkBucket IN ('Transcode','Remux','AudioFix')",
        Params,
    )
    AfterCount = int((After[0].get('N') if After else 0) or 0)
    print(f"[C34] mp3-family rows in Transcode/Remux/AudioFix after reclassify: {AfterCount}")

    if AfterCount != 0:
        print(f"[C34] FAIL: expected 0, got {AfterCount}")
        return 1

    Buckets = Db.ExecuteQuery(
        f"SELECT WorkBucket, COUNT(*) AS N FROM MediaFiles "
        f"WHERE ContainerFormat IN ({Placeholders}) "
        f"GROUP BY WorkBucket ORDER BY N DESC",
        Params,
    )
    for Row in Buckets:
        print(f"[C34]   {Row.get('workbucket')}: {int(Row.get('n') or 0)}")
    return 0


if __name__ == '__main__':
    sys.exit(Main())
