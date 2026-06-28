from typing import Optional
from Core.Database.DatabaseService import DatabaseService


# directive: work-transcode-unified
class InvalidProfileError(ValueError):
    # see work-bucket.C3
    pass


# directive: work-transcode-unified
class ProfileName:

    __slots__ = ('Value',)

    # directive: work-transcode-unified
    def __init__(self, RawName: str, Db: Optional[DatabaseService] = None):
        # see work-bucket.C3
        Name = (RawName or '').strip()
        if not Name:
            raise InvalidProfileError("Profile name is empty")
        DbInstance = Db or DatabaseService()
        Rows = DbInstance.ExecuteQuery(
            "SELECT Draft, Active FROM Profiles WHERE ProfileName = %s LIMIT 1",
            (Name,),
        )
        if not Rows:
            raise InvalidProfileError(f"Profile {Name!r} does not exist")
        R = Rows[0]
        if bool(R.get('draft')):
            raise InvalidProfileError(f"Profile {Name!r} is a draft")
        if not bool(R.get('active')):
            raise InvalidProfileError(f"Profile {Name!r} is not active")
        object.__setattr__(self, 'Value', Name)

    # directive: work-transcode-unified
    def __setattr__(self, *_args):
        # see work-bucket.C3
        raise AttributeError("ProfileName is immutable")

    # directive: work-transcode-unified
    def __eq__(self, Other):
        # see work-bucket.C3
        return isinstance(Other, ProfileName) and self.Value == Other.Value

    # directive: work-transcode-unified
    def __hash__(self):
        # see work-bucket.C3
        return hash(self.Value)

    # directive: work-transcode-unified
    def __repr__(self):
        # see work-bucket.C3
        return f"ProfileName({self.Value!r})"
