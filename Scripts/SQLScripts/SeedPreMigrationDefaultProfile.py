import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: compliance-symmetry
PRE_MIGRATION_DEFAULT_NAME = '_PreMigrationDefault'
SOURCE_PROFILE_NAME = 'NVENC AV1 P7 CANARY VBR -720p'


# directive: compliance-symmetry
def Run():
    DB = DatabaseService()

    DB.ExecuteNonQuery("CREATE UNIQUE INDEX IF NOT EXISTS uq_profiles_profilename ON Profiles (ProfileName)")

    Existing = DB.ExecuteQuery("SELECT Id FROM Profiles WHERE ProfileName = %s", (PRE_MIGRATION_DEFAULT_NAME,))
    if Existing:
        print(f"{PRE_MIGRATION_DEFAULT_NAME} already exists (Id={Existing[0]['id']}); ensuring Draft=FALSE and compliance bar populated.")
        DB.ExecuteNonQuery(
            "UPDATE Profiles SET Draft = FALSE, Active = TRUE, "
            "StreamCodecName = COALESCE(StreamCodecName, 'av1'), "
            "TargetResolutionCategory = COALESCE(TargetResolutionCategory, '720p'), "
            "TargetVideoKbps = NULL, "
            "AllowUpscale = FALSE, "
            "AudioCodec = COALESCE(AudioCodec, 'aac'), "
            "TargetAudioKbps = COALESCE(TargetAudioKbps, 128), "
            "Container = COALESCE(Container, 'mp4') "
            "WHERE ProfileName = %s",
            (PRE_MIGRATION_DEFAULT_NAME,),
        )
    else:
        SourceRows = DB.ExecuteQuery("SELECT * FROM Profiles WHERE ProfileName = %s", (SOURCE_PROFILE_NAME,))
        if not SourceRows:
            print(f"ERROR: source profile {SOURCE_PROFILE_NAME} not found; cannot clone encoder section.")
            return
        Src = SourceRows[0]
        DB.ExecuteNonQuery(
            "INSERT INTO Profiles "
            "(ProfileName, Description, Codec, Preset, FilmGrain, YadifMode, YadifParity, YadifDeint, UseNvidiaHardware, SortOrder, "
            " Draft, Active, StreamCodecName, TargetResolutionCategory, TargetVideoKbps, AllowUpscale, AudioCodec, TargetAudioKbps, Container) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, TRUE, 'av1', '720p', NULL, FALSE, 'aac', 128, 'mp4') "
            "ON CONFLICT (ProfileName) DO NOTHING",
            (
                PRE_MIGRATION_DEFAULT_NAME,
                'Pre-migration fallback. Compliance bar matches NVENC AV1 P7 CANARY VBR -720p. Operator-locked default while other profiles finalize.',
                Src.get('codec') or 'av1_nvenc',
                Src.get('preset') if Src.get('preset') is not None else 7,
                Src.get('filmgrain') if Src.get('filmgrain') is not None else 0,
                Src.get('yadifmode') if Src.get('yadifmode') is not None else 1,
                Src.get('yadifparity') if Src.get('yadifparity') is not None else 1,
                Src.get('yadifdeint') if Src.get('yadifdeint') is not None else 1,
                Src.get('usenvidiahardware') if Src.get('usenvidiahardware') is not None else 1,
                0,
            ),
        )
        print(f"Inserted {PRE_MIGRATION_DEFAULT_NAME} (cloned encoder section from {SOURCE_PROFILE_NAME}).")

    Updated = DB.ExecuteNonQuery(
        "UPDATE Profiles SET Draft = TRUE "
        "WHERE ProfileName <> %s AND Draft IS DISTINCT FROM TRUE",
        (PRE_MIGRATION_DEFAULT_NAME,),
    )
    print(f"Flipped existing profiles to Draft=TRUE.")

    Verify = DB.ExecuteQuery(
        "SELECT ProfileName, Draft, Active, StreamCodecName, TargetResolutionCategory, TargetVideoKbps, "
        "AllowUpscale, AudioCodec, TargetAudioKbps, Container "
        "FROM Profiles WHERE ProfileName = %s",
        (PRE_MIGRATION_DEFAULT_NAME,),
    )
    if Verify:
        R = Verify[0]
        print(f"{PRE_MIGRATION_DEFAULT_NAME} state:")
        for K in ['draft', 'active', 'streamcodecname', 'targetresolutioncategory', 'targetvideokbps',
                  'allowupscale', 'audiocodec', 'targetaudiokbps', 'container']:
            print(f"  {K}={R.get(K)!r}")

    Counts = DB.ExecuteQuery(
        "SELECT COUNT(*) FILTER (WHERE Draft = TRUE) AS draft_count, "
        "COUNT(*) FILTER (WHERE Draft = FALSE) AS finalized_count, "
        "COUNT(*) AS total FROM Profiles"
    )
    if Counts:
        C = Counts[0]
        print(f"Profile counts: total={C['total']} draft={C['draft_count']} finalized={C['finalized_count']}")


if __name__ == '__main__':
    Run()
