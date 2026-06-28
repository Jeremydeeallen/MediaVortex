from typing import Optional
from Core.Database.DatabaseService import DatabaseService
from Features.Profiles.ProfileRepository import ProfileRepository


# directive: work-transcode-unified | # see work-bucket.C3
class InvalidProfileError(ValueError):
    # see work-bucket.C3
    pass


# directive: work-transcode-unified | # see work-bucket.C3
class ProfileName:
    # see work-bucket.C3

    __slots__ = ('Value',)

    # directive: work-transcode-unified | # see work-bucket.G6
    def __init__(self, RawName: str, Db: Optional[DatabaseService] = None, Repo: Optional[ProfileRepository] = None):
        # see work-bucket.G6
        Name = (RawName or '').strip()
        if not Name:
            raise InvalidProfileError("Profile name is empty")
        ProfileRepo = Repo or ProfileRepository()
        State = ProfileRepo.GetProfileState(Name)
        if State is None:
            raise InvalidProfileError(f"Profile {Name!r} does not exist")
        if State['Draft']:
            raise InvalidProfileError(f"Profile {Name!r} is a draft")
        if not State['Active']:
            raise InvalidProfileError(f"Profile {Name!r} is not active")
        object.__setattr__(self, 'Value', Name)

    # directive: work-transcode-unified | # see work-bucket.C3
    def __setattr__(self, *_args):
        # see work-bucket.C3
        raise AttributeError("ProfileName is immutable")

    # directive: work-transcode-unified | # see work-bucket.C3
    def __eq__(self, Other):
        # see work-bucket.C3
        return isinstance(Other, ProfileName) and self.Value == Other.Value

    # directive: work-transcode-unified | # see work-bucket.C3
    def __hash__(self):
        # see work-bucket.C3
        return hash(self.Value)

    # directive: work-transcode-unified | # see work-bucket.C3
    def __repr__(self):
        # see work-bucket.C3
        return f"ProfileName({self.Value!r})"
