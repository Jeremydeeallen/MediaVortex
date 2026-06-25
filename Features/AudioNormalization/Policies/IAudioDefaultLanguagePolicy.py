from abc import ABC, abstractmethod
from typing import List, Optional, Union

from Core.Database.DatabaseService import DatabaseService
from Features.AudioNormalization.AudioStrategyResult import Accept, Reject


# directive: audio-pipeline-fail-loud
class IAudioDefaultLanguagePolicy(ABC):

    # directive: audio-pipeline-fail-loud
    @abstractmethod
    def Decide(
        self,
        PresentLanguages: List[str],
        LibraryDefault: Optional[str],
    ) -> Union[Accept, Reject]:
        ...


# directive: audio-pipeline-fail-loud
class RankPreferredDefaultPolicy(IAudioDefaultLanguagePolicy):

    # directive: audio-pipeline-fail-loud
    def __init__(self, Db: Optional[DatabaseService] = None):
        self._Db = Db or DatabaseService()

    # directive: audio-pipeline-fail-loud
    def _ReadRank(self) -> List[str]:
        Rows = self._Db.ExecuteQuery(
            "SELECT SettingValue FROM SystemSettings WHERE SettingKey = 'PreferredDefaultLanguageRank' LIMIT 1"
        )
        if not Rows:
            return ['eng', 'en']
        Raw = (Rows[0].get('SettingValue') or Rows[0].get('settingvalue') or '').strip()
        if not Raw:
            return ['eng', 'en']
        return [P.strip().lower() for P in Raw.split(',') if P.strip()]

    # directive: audio-pipeline-fail-loud
    def Decide(self, PresentLanguages, LibraryDefault):
        Name = 'RankPreferredDefaultPolicy'
        Present = [(L or '').strip().lower() for L in (PresentLanguages or []) if (L or '').strip()]
        Present = [L for L in Present if L not in ('und', '')]

        if not Present:
            return Reject('no_tagged_present_languages', Name)

        if LibraryDefault:
            LibLower = LibraryDefault.strip().lower()
            if LibLower in Present:
                return Accept({'Language': LibLower, 'Reason': 'library_default_present'}, Name)

        Rank = self._ReadRank()
        for Tag in Rank:
            if Tag in Present:
                return Accept({'Language': Tag, 'Reason': f'rank_match:{Tag}'}, Name)

        First = Present[0]
        return Accept({'Language': First, 'Reason': 'first_source_order_present'}, Name)
