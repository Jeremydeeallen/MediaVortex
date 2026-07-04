import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService


NVENC_CANARY = 'NVENC AV1 CANARY'
QSV_CANARY = 'QSV AV1 CANARY'


# directive: transcode-flow-canonical | # see transcode.ST5
def SurveyNonCanary(Db: DatabaseService) -> None:
    Rows = Db.ExecuteQuery(
        "SELECT p.Id, p.ProfileName, p.Codec, COUNT(mf.Id) AS n_media "
        "FROM Profiles p "
        "LEFT JOIN MediaFiles mf ON mf.AssignedProfile = p.ProfileName "
        "WHERE p.Codec IN ('av1_nvenc','av1_qsv','libsvtav1') "
        "  AND (p.Family IS NULL OR p.Family NOT IN (%s, %s)) "
        "GROUP BY p.Id, p.ProfileName, p.Codec "
        "ORDER BY n_media DESC, p.Id",
        (NVENC_CANARY, QSV_CANARY),
    )
    print(f"Non-CANARY AV1 profiles ({len(Rows)}):")
    for R in Rows:
        print(f"  Id={R['id']:3d}  n_media={R['n_media']:4d}  {R['profilename']} ({R['codec']})")


# directive: transcode-flow-canonical | # see transcode.ST5
def ReassignOrphanedMediaFiles(Db: DatabaseService) -> int:
    Rows = Db.ExecuteQuery(
        "SELECT p.ProfileName, COUNT(mf.Id) AS n_media "
        "FROM Profiles p "
        "JOIN MediaFiles mf ON mf.AssignedProfile = p.ProfileName "
        "WHERE p.Codec IN ('av1_nvenc','av1_qsv','libsvtav1') "
        "  AND (p.Family IS NULL OR p.Family NOT IN (%s, %s)) "
        "GROUP BY p.ProfileName",
        (NVENC_CANARY, QSV_CANARY),
    )
    Orphans = sum(int(R['n_media']) for R in Rows)
    if Orphans == 0:
        print("No orphaned MediaFiles.AssignedProfile references. Safe to delete.")
        return 0
    print(f"REFUSING TO DELETE: {Orphans} MediaFiles rows reference non-CANARY profiles.")
    print("Reassignment requires ContentClassifier tuple-lookup (Reset 10 T12).")
    print("Rerun this script after T12 lands + ContentClassifier reassigns orphans.")
    return Orphans


# directive: transcode-flow-canonical | # see transcode.ST5
def DeleteNonCanaryProfiles(Db: DatabaseService) -> None:
    Orphans = ReassignOrphanedMediaFiles(Db)
    if Orphans > 0:
        return
    Rows = Db.ExecuteQuery(
        "SELECT Id, ProfileName FROM Profiles "
        "WHERE Codec IN ('av1_nvenc','av1_qsv','libsvtav1') "
        "  AND (Family IS NULL OR Family NOT IN (%s, %s))",
        (NVENC_CANARY, QSV_CANARY),
    )
    for R in Rows:
        Db.ExecuteNonQuery("DELETE FROM ProfileThresholds WHERE ProfileId = %s", (R['id'],))
        Db.ExecuteNonQuery("DELETE FROM Profiles WHERE Id = %s", (R['id'],))
        print(f"Deleted Profile {R['id']} ({R['profilename']})")


# directive: transcode-flow-canonical | # see transcode.ST5
def Summary(Db: DatabaseService) -> None:
    Rows = Db.ExecuteQuery(
        "SELECT Family, COUNT(*) AS n FROM Profiles "
        "WHERE Codec IN ('av1_nvenc','av1_qsv','libsvtav1') "
        "GROUP BY Family ORDER BY Family NULLS LAST"
    )
    print("\n--- Summary ---")
    for R in Rows:
        print(f"  Family={R['family']}: {R['n']} AV1 profiles")


# directive: transcode-flow-canonical | # see transcode.ST5
def RunMigration() -> None:
    Db = DatabaseService()
    SurveyNonCanary(Db)
    print()
    DeleteNonCanaryProfiles(Db)
    Summary(Db)


if __name__ == '__main__':
    RunMigration()
