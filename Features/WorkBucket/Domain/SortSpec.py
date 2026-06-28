from enum import Enum


# directive: work-transcode-unified
class SortSpec(Enum):
    # see work-bucket.C2
    TotalGbDesc = 'TotalGB.desc'
    FileCountDesc = 'FileCount.desc'
    NameAsc = 'Name.asc'

    # directive: work-transcode-unified
    def ToSql(self) -> str:
        # see work-bucket.C2
        if self is SortSpec.TotalGbDesc:
            return "TotalGB DESC NULLS LAST"
        if self is SortSpec.FileCountDesc:
            return "FileCount DESC NULLS LAST"
        return "ShowName ASC"

    @classmethod
    # directive: work-transcode-unified
    def FromString(cls, RawValue: str) -> "SortSpec":
        # see work-bucket.C2
        if not RawValue:
            return cls.TotalGbDesc
        for Member in cls:
            if Member.value == RawValue:
                return Member
        return cls.TotalGbDesc
