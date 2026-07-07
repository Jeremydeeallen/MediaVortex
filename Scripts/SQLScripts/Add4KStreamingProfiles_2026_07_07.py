# directive: transcode-flow-canonical
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


# from: Docs/Codecs/4K-AV1-Streaming-Sweep-2026-07-06.md
PROFILES = [
    dict(
        ProfileName='STREAMING NVENC AV1 P6 Default -2160p',
        Family='STREAMING NVENC',
        QualityTier=1,
        ContentClass='live_action',
        Codec='av1_nvenc',
        Preset=6,
        RateControlMode='vbr',
        UseNvidiaHardware=1,
        UseIntelHardware=0,
        TargetResolutionCategory='2160p',
        Container='mp4',
        PixelFormat='p010le',
        StreamCodecName='av1',
        AudioCodec='libopus',
        AudioBitrateKbps=128,
        AudioChannels=2,
        FastStart=True,
        AllowUpscale=False,
        SortOrder=100,
        Active=True,
        Draft=False,
    ),
    dict(
        ProfileName='STREAMING NVENC AV1 P6 HQ -2160p',
        Family='STREAMING NVENC',
        QualityTier=2,
        ContentClass='live_action',
        Codec='av1_nvenc',
        Preset=6,
        RateControlMode='vbr',
        UseNvidiaHardware=1,
        UseIntelHardware=0,
        TargetResolutionCategory='2160p',
        Container='mp4',
        PixelFormat='p010le',
        StreamCodecName='av1',
        AudioCodec='libopus',
        AudioBitrateKbps=128,
        AudioChannels=2,
        FastStart=True,
        AllowUpscale=False,
        SortOrder=101,
        Active=True,
        Draft=False,
    ),
    dict(
        ProfileName='STREAMING QSV AV1 P1 Default -2160p',
        Family='STREAMING QSV',
        QualityTier=1,
        ContentClass='live_action',
        Codec='av1_qsv',
        Preset=1,
        RateControlMode='icq',
        UseNvidiaHardware=0,
        UseIntelHardware=1,
        TargetResolutionCategory='2160p',
        Container='mp4',
        PixelFormat='p010le',
        StreamCodecName='av1',
        AudioCodec='libopus',
        AudioBitrateKbps=128,
        AudioChannels=2,
        FastStart=True,
        AllowUpscale=False,
        SortOrder=102,
        Active=True,
        Draft=False,
    ),
    dict(
        ProfileName='STREAMING QSV AV1 P1 HQ -2160p',
        Family='STREAMING QSV',
        QualityTier=2,
        ContentClass='live_action',
        Codec='av1_qsv',
        Preset=1,
        RateControlMode='icq',
        UseNvidiaHardware=0,
        UseIntelHardware=1,
        TargetResolutionCategory='2160p',
        Container='mp4',
        PixelFormat='p010le',
        StreamCodecName='av1',
        AudioCodec='libopus',
        AudioBitrateKbps=128,
        AudioChannels=2,
        FastStart=True,
        AllowUpscale=False,
        SortOrder=103,
        Active=True,
        Draft=False,
    ),
]


# from: Docs/Codecs/4K-AV1-Streaming-Sweep-2026-07-06.md
THRESHOLDS_2160P = {
    'STREAMING NVENC AV1 P6 Default -2160p': dict(TargetKbps=1500, IcqQ=None),
    'STREAMING NVENC AV1 P6 HQ -2160p':      dict(TargetKbps=2250, IcqQ=None),
    'STREAMING QSV AV1 P1 Default -2160p':   dict(TargetKbps=None, IcqQ=34),
    'STREAMING QSV AV1 P1 HQ -2160p':        dict(TargetKbps=None, IcqQ=30),
}


# from: Docs/Codecs/4K-AV1-Streaming-Sweep-2026-07-06.md
Resolution = '2160p'
# from: Docs/Codecs/4K-AV1-Streaming-Sweep-2026-07-06.md
ThresholdAudioKbps = 128
# from: Docs/Codecs/4K-AV1-Streaming-Sweep-2026-07-06.md
ThresholdSizeBand = 0
# from: Docs/Codecs/4K-AV1-Streaming-Sweep-2026-07-06.md
ThresholdFallbackKbps = 0
# from: Docs/Codecs/4K-AV1-Streaming-Sweep-2026-07-06.md
ThresholdVideoBitrateKbps = 0
# from: Docs/Codecs/4K-AV1-Streaming-Sweep-2026-07-06.md
ThresholdContainer = 'mp4'
# from: Docs/Codecs/4K-AV1-Streaming-Sweep-2026-07-06.md
ThresholdTranscodeDownTo = ''
# from: Docs/Codecs/4K-AV1-Streaming-Sweep-2026-07-06.md
ThresholdMaxBitrateMultiplier = 2.00


# directive: transcode-flow-canonical
def Main():
    Db = DatabaseService()
    for P in PROFILES:
        Cols = list(P.keys())
        Vals = [P[C] for C in Cols]
        Placeholders = ', '.join(['%s'] * len(Vals))
        Sql = (
            f"INSERT INTO Profiles ({', '.join(Cols)}) "
            f"VALUES ({Placeholders}) "
            f"ON CONFLICT (ProfileName) DO NOTHING"
        )
        Db.ExecuteNonQuery(Sql, tuple(Vals))
        print(f"Profile inserted or existing: {P['ProfileName']}")

    ProfileRows = Db.ExecuteQuery(
        "SELECT Id, ProfileName FROM Profiles WHERE ProfileName = ANY(%s)",
        (list(THRESHOLDS_2160P.keys()),),
    )
    for R in ProfileRows:
        ProfileId = R['Id']
        Name = R['ProfileName']
        Th = THRESHOLDS_2160P[Name]
        Db.ExecuteNonQuery(
            "INSERT INTO ProfileThresholds "
            "(ProfileId, Resolution, TargetKbps, IcqQ, VideoBitrateKbps, "
            " Under30MinMb, Under65MinMb, Over65MinMb, "
            " AudioBitrateKbps, FallbackVideoBitrateKbps, FallbackAudioBitrateKbps, "
            " TranscodeDownTo, ContainerType, MaxBitrateMultiplier) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (ProfileId, Resolution) DO NOTHING",
            (
                ProfileId,
                Resolution,
                Th['TargetKbps'],
                Th['IcqQ'],
                ThresholdVideoBitrateKbps,
                ThresholdSizeBand,
                ThresholdSizeBand,
                ThresholdSizeBand,
                ThresholdAudioKbps,
                ThresholdFallbackKbps,
                ThresholdFallbackKbps,
                ThresholdTranscodeDownTo,
                ThresholdContainer,
                ThresholdMaxBitrateMultiplier,
            ),
        )
        print(f"Threshold inserted or existing: {Name} (id={ProfileId}) TargetKbps={Th['TargetKbps']} IcqQ={Th['IcqQ']}")

    print("Done.")


if __name__ == '__main__':
    Main()
