# directive: audio-dialog-boost-real | # see audio-normalization.C8
from typing import Optional

from Core.Database.DatabaseService import DatabaseService


RULES_SELECT = (
    "SELECT Id, TargetIntegratedLufs, TargetTruePeakDbtp, AcceptableAudioCodecsCsv, "
    "DialogBoostTargetLufs, DialogBoostTargetLra, SampleLimitHeadroomDb, "
    "Track0Codec, Track1Codec, "
    "Track0BitratePerChannelKbps, Track0MinPerChannelKbps, "
    "Track1StereoBitrateKbps, Track1VocalsRmsFallbackDbfs, "
    "VocalsBoostDb, InstrumentalAttenDb, "
    "PremixCompressorThreshold, PremixCompressorRatio, PremixCompressorMakeupDb, "
    "PremixDynaudnormFrameLen, PremixDynaudnormGaussSize, LastUpdated "
    "FROM AudioComplianceRules WHERE Id = 1"
)


RULES_UPDATE = (
    "UPDATE AudioComplianceRules SET "
    "TargetIntegratedLufs=%s, TargetTruePeakDbtp=%s, AcceptableAudioCodecsCsv=%s, "
    "DialogBoostTargetLufs=%s, DialogBoostTargetLra=%s, SampleLimitHeadroomDb=%s, "
    "Track0Codec=%s, Track1Codec=%s, "
    "Track0BitratePerChannelKbps=%s, Track0MinPerChannelKbps=%s, "
    "Track1StereoBitrateKbps=%s, Track1VocalsRmsFallbackDbfs=%s, "
    "VocalsBoostDb=%s, InstrumentalAttenDb=%s, "
    "PremixCompressorThreshold=%s, PremixCompressorRatio=%s, PremixCompressorMakeupDb=%s, "
    "PremixDynaudnormFrameLen=%s, PremixDynaudnormGaussSize=%s, "
    "LastUpdated=NOW() WHERE Id = 1"
)


RULE_FIELDS = [
    'TargetIntegratedLufs', 'TargetTruePeakDbtp', 'AcceptableAudioCodecsCsv',
    'DialogBoostTargetLufs', 'DialogBoostTargetLra', 'SampleLimitHeadroomDb',
    'Track0Codec', 'Track1Codec',
    'Track0BitratePerChannelKbps', 'Track0MinPerChannelKbps',
    'Track1StereoBitrateKbps', 'Track1VocalsRmsFallbackDbfs',
    'VocalsBoostDb', 'InstrumentalAttenDb',
    'PremixCompressorThreshold', 'PremixCompressorRatio', 'PremixCompressorMakeupDb',
    'PremixDynaudnormFrameLen', 'PremixDynaudnormGaussSize',
]


# directive: audio-dialog-boost-real | # see audio-normalization.C8
class AudioComplianceRulesRepository:

    # directive: audio-dialog-boost-real | # see audio-normalization.C8
    def __init__(self, Db: Optional[DatabaseService] = None):
        self._Db = Db or DatabaseService()

    # directive: audio-dialog-boost-real | # see audio-normalization.C8
    def GetRules(self) -> dict:
        Rows = self._Db.ExecuteQuery(RULES_SELECT)
        if not Rows:
            raise RuntimeError('AudioComplianceRules has no rows -- migration not applied')
        R = Rows[0]
        return {
            'Id': int(R.get('Id') if 'Id' in R else R.get('id')),
            'TargetIntegratedLufs': float(R.get('TargetIntegratedLufs') if 'TargetIntegratedLufs' in R else R.get('targetintegratedlufs')),
            'TargetTruePeakDbtp': float(R.get('TargetTruePeakDbtp') if 'TargetTruePeakDbtp' in R else R.get('targettruepeakdbtp')),
            'AcceptableAudioCodecsCsv': (R.get('AcceptableAudioCodecsCsv') or R.get('acceptableaudiocodecscsv') or '').strip(),
            'DialogBoostTargetLufs': float(R.get('DialogBoostTargetLufs') if 'DialogBoostTargetLufs' in R else R.get('dialogboosttargetlufs')),
            'DialogBoostTargetLra': float(R.get('DialogBoostTargetLra') if 'DialogBoostTargetLra' in R else R.get('dialogboosttargetlra')),
            'SampleLimitHeadroomDb': float(R.get('SampleLimitHeadroomDb') if 'SampleLimitHeadroomDb' in R else R.get('samplelimitheadroomdb')),
            'Track0Codec': str(R.get('Track0Codec') or R.get('track0codec') or 'aac').strip().lower(),
            'Track1Codec': str(R.get('Track1Codec') or R.get('track1codec') or 'aac').strip().lower(),
            'Track0BitratePerChannelKbps': int(R.get('Track0BitratePerChannelKbps') if 'Track0BitratePerChannelKbps' in R else R.get('track0bitrateperchannelkbps')),
            'Track0MinPerChannelKbps': int(R.get('Track0MinPerChannelKbps') if 'Track0MinPerChannelKbps' in R else R.get('track0minperchannelkbps')),
            'Track1StereoBitrateKbps': int(R.get('Track1StereoBitrateKbps') if 'Track1StereoBitrateKbps' in R else R.get('track1stereobitratekbps')),
            'Track1VocalsRmsFallbackDbfs': float(R.get('Track1VocalsRmsFallbackDbfs') if 'Track1VocalsRmsFallbackDbfs' in R else R.get('track1vocalsrmsfallbackdbfs')),
            'VocalsBoostDb': float(R.get('VocalsBoostDb') if 'VocalsBoostDb' in R else R.get('vocalsboostdb')),
            'InstrumentalAttenDb': float(R.get('InstrumentalAttenDb') if 'InstrumentalAttenDb' in R else R.get('instrumentalattendb')),
            'PremixCompressorThreshold': float(R.get('PremixCompressorThreshold') if 'PremixCompressorThreshold' in R else R.get('premixcompressorthreshold')),
            'PremixCompressorRatio': float(R.get('PremixCompressorRatio') if 'PremixCompressorRatio' in R else R.get('premixcompressorratio')),
            'PremixCompressorMakeupDb': float(R.get('PremixCompressorMakeupDb') if 'PremixCompressorMakeupDb' in R else R.get('premixcompressormakeupdb')),
            'PremixDynaudnormFrameLen': int(R.get('PremixDynaudnormFrameLen') if 'PremixDynaudnormFrameLen' in R else R.get('premixdynaudnormframelen')),
            'PremixDynaudnormGaussSize': int(R.get('PremixDynaudnormGaussSize') if 'PremixDynaudnormGaussSize' in R else R.get('premixdynaudnormgausssize')),
        }

    # directive: audio-dialog-boost-real | # see audio-normalization.C8
    def UpdateRules(self, R: dict) -> None:
        self._Db.ExecuteNonQuery(
            RULES_UPDATE,
            (
                float(R['TargetIntegratedLufs']),
                float(R['TargetTruePeakDbtp']),
                str(R['AcceptableAudioCodecsCsv']).strip(),
                float(R['DialogBoostTargetLufs']),
                float(R['DialogBoostTargetLra']),
                float(R['SampleLimitHeadroomDb']),
                str(R['Track0Codec']).strip().lower(),
                str(R['Track1Codec']).strip().lower(),
                int(R['Track0BitratePerChannelKbps']),
                int(R['Track0MinPerChannelKbps']),
                int(R['Track1StereoBitrateKbps']),
                float(R['Track1VocalsRmsFallbackDbfs']),
                float(R['VocalsBoostDb']),
                float(R['InstrumentalAttenDb']),
                float(R['PremixCompressorThreshold']),
                float(R['PremixCompressorRatio']),
                float(R['PremixCompressorMakeupDb']),
                int(R['PremixDynaudnormFrameLen']),
                int(R['PremixDynaudnormGaussSize']),
            ),
        )
