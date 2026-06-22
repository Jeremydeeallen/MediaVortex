import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: compliance-symmetry
ENCODER_TO_STREAM_CODEC = {
    'libsvtav1': 'av1',
    'av1_nvenc': 'av1',
    'libx265': 'hevc',
    'hevc_nvenc': 'hevc',
    'libx264': 'h264',
    'h264_nvenc': 'h264',
}


# directive: compliance-symmetry
def _InferStreamCodec(Codec):
    if not Codec:
        return None
    return ENCODER_TO_STREAM_CODEC.get(Codec.lower())


# directive: compliance-symmetry
def _InferResolutionCategory(DB, ProfileId):
    Rows = DB.ExecuteQuery(
        "SELECT TranscodeDownTo, Resolution FROM ProfileThresholds "
        "WHERE ProfileId = %s AND TranscodeDownTo IS NOT NULL "
        "AND TranscodeDownTo NOT IN ('', 'No downscaling') "
        "ORDER BY CASE TranscodeDownTo "
        "  WHEN '2160p' THEN 4 WHEN '1440p' THEN 3 WHEN '1080p' THEN 3 "
        "  WHEN '720p' THEN 2 WHEN '540p' THEN 1 WHEN '480p' THEN 1 ELSE 0 END DESC "
        "LIMIT 1",
        (ProfileId,),
    )
    if Rows:
        return Rows[0]['transcodedownto']
    return '720p'


# directive: compliance-symmetry
def _InferContainer(DB, ProfileId):
    Rows = DB.ExecuteQuery(
        "SELECT ContainerType FROM ProfileThresholds "
        "WHERE ProfileId = %s AND ContainerType IS NOT NULL AND ContainerType <> '' "
        "ORDER BY Id LIMIT 1",
        (ProfileId,),
    )
    if Rows and Rows[0].get('containertype'):
        return Rows[0]['containertype']
    return 'mp4'


# directive: compliance-symmetry
def Run():
    DB = DatabaseService()

    Profiles = DB.ExecuteQuery(
        "SELECT Id, ProfileName, Codec, Draft FROM Profiles "
        "WHERE Draft = TRUE AND ProfileName <> '_PreMigrationDefault'"
    )
    print(f"Auto-finalizing {len(Profiles)} draft profile(s)...")

    UpdatedCount = 0
    SkippedCount = 0
    Failures = []
    for P in Profiles:
        Pid = P['id']
        Name = P['profilename']
        Codec = P['codec']
        StreamCodec = _InferStreamCodec(Codec)
        if not StreamCodec:
            Failures.append(f"  {Name}: cannot infer StreamCodecName from Codec={Codec!r}")
            SkippedCount += 1
            continue
        ResCat = _InferResolutionCategory(DB, Pid)
        Container = _InferContainer(DB, Pid)
        try:
            DB.ExecuteNonQuery(
                "UPDATE Profiles SET "
                "StreamCodecName = COALESCE(StreamCodecName, %s), "
                "TargetResolutionCategory = COALESCE(TargetResolutionCategory, %s), "
                "AudioCodec = COALESCE(AudioCodec, 'aac'), "
                "TargetAudioKbps = COALESCE(TargetAudioKbps, 128), "
                "Container = COALESCE(Container, %s), "
                "AllowUpscale = COALESCE(AllowUpscale, FALSE), "
                "Draft = FALSE "
                "WHERE Id = %s",
                (StreamCodec, ResCat, Container, Pid),
            )
            UpdatedCount += 1
            print(f"  {Name}: codec={Codec} -> stream={StreamCodec}, res={ResCat}, container={Container}")
        except Exception as Ex:
            Failures.append(f"  {Name}: {Ex}")
            SkippedCount += 1

    print(f"Auto-finalized {UpdatedCount}; skipped {SkippedCount}.")
    if Failures:
        print("Skipped detail:")
        for F in Failures:
            print(F)

    Counts = DB.ExecuteQuery(
        "SELECT COUNT(*) FILTER (WHERE Draft = TRUE) AS draft_cnt, "
        "COUNT(*) FILTER (WHERE Draft = FALSE) AS final_cnt, "
        "COUNT(*) AS total FROM Profiles"
    )
    if Counts:
        C = Counts[0]
        print(f"Post-state: total={C['total']} drafts={C['draft_cnt']} finalized={C['final_cnt']}")


if __name__ == '__main__':
    Run()
