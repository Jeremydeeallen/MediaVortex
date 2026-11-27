# directive: target-policy-1a-tables | # see policy.W1, policy.S1 -- the only Python that reads MediaFileTargets for a decision
from typing import Dict, Iterable, Optional, Union

from Core.Database.DatabaseService import DatabaseService
from Features.Policy.Target import Target, Undecided

VIEW_COLUMNS = (
    'MediaFileId', 'StorageRootId', 'Tier', 'TierOrigin', 'ContentClass', 'ClassOrigin', 'FrameRateClass', 'SourceResolution',
    'TargetResolution', 'TargetKbps', 'IcqQ', 'QualityLabel', 'QualityTestRequired', 'VmafMin', 'VmafMax',
    'HeldFrameDetectionThreshold', 'HeldFrameP25Min', 'HeldFrameMeanMin', 'LiveActionP10Min', 'AudioPolicyId',
    'OutputContainer', 'AcceptableContainersCsv', 'AcceptableAudioCodecsCsv', 'CeilingMultiplier', 'ReviewBeforeReplace', 'Undecided',
)
_SELECT = "SELECT " + ", ".join(VIEW_COLUMNS) + " FROM MediaFileTargets"


# directive: target-policy-1a-tables | # see policy.S1
def _OptFloat(Value) -> Optional[float]:
    return None if Value is None else float(Value)


# directive: target-policy-1a-tables | # see policy.S1 -- a view row becomes a Target only when Undecided IS NULL; every other field is then non-null by the view's definition
def FromRow(R) -> Union[Target, Undecided]:
    MediaFileId = int(R['MediaFileId'])
    if R['Undecided'] is not None:
        return Undecided(MediaFileId=MediaFileId, Reason=str(R['Undecided']))
    return Target(
        MediaFileId=MediaFileId,
        StorageRootId=int(R['StorageRootId']),
        Tier=int(R['Tier']),
        TierOrigin=str(R['TierOrigin']),
        ContentClass=str(R['ContentClass']),
        ClassOrigin=str(R['ClassOrigin']),
        FrameRateClass=str(R['FrameRateClass']),
        SourceResolution=str(R['SourceResolution']),
        TargetResolution=str(R['TargetResolution']),
        TargetKbps=int(R['TargetKbps']),
        IcqQ=None if R['IcqQ'] is None else int(R['IcqQ']),
        QualityLabel=str(R['QualityLabel']),
        QualityTestRequired=bool(R['QualityTestRequired']),
        VmafMin=float(R['VmafMin']),
        VmafMax=_OptFloat(R['VmafMax']),
        HeldFrameDetectionThreshold=_OptFloat(R['HeldFrameDetectionThreshold']),
        HeldFrameP25Min=_OptFloat(R['HeldFrameP25Min']),
        HeldFrameMeanMin=_OptFloat(R['HeldFrameMeanMin']),
        LiveActionP10Min=_OptFloat(R['LiveActionP10Min']),
        AudioPolicyId=int(R['AudioPolicyId']),
        OutputContainer=str(R['OutputContainer']),
        AcceptableContainersCsv=str(R['AcceptableContainersCsv']),
        AcceptableAudioCodecsCsv=str(R['AcceptableAudioCodecsCsv']),
        CeilingMultiplier=float(R['CeilingMultiplier']),
        ReviewBeforeReplace=bool(R['ReviewBeforeReplace']),
    )


# directive: target-policy-1a-tables | # see policy.W1
class TargetResolver:

    # directive: target-policy-1a-tables | # see policy.W1
    def __init__(self, Db: Optional[DatabaseService] = None):
        self.Db = Db or DatabaseService()

    # directive: target-policy-1a-tables | # see policy.W1
    def Resolve(self, MediaFileId: int) -> Union[Target, Undecided]:
        Rows = self.Db.ExecuteQuery(_SELECT + " WHERE MediaFileId = %s", (int(MediaFileId),))
        if not Rows:
            raise LookupError(f"MediaFileTargets has no row for MediaFileId={MediaFileId}")
        return FromRow(Rows[0])

    # directive: target-policy-1a-tables | # see policy.S2 -- one SELECT per batch for RecomputeForFiles
    def ResolveMany(self, MediaFileIds: Iterable[int]) -> Dict[int, Union[Target, Undecided]]:
        Ids = sorted({int(I) for I in MediaFileIds})
        if not Ids:
            return {}
        Rows = self.Db.ExecuteQuery(_SELECT + " WHERE MediaFileId = ANY(%s)", (Ids,))
        Out = {int(R['MediaFileId']): FromRow(R) for R in Rows}
        Missing = [I for I in Ids if I not in Out]
        if Missing:
            raise LookupError(f"MediaFileTargets has no row for MediaFileIds={Missing[:10]}{'...' if len(Missing) > 10 else ''}")
        return Out
