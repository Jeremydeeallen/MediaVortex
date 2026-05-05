import platform


class PathTranslationService:
    """Translates file paths between canonical (DB) format and local worker format.

    DB paths use Windows drive letters (e.g. T:\Shows\file.mkv). Linux workers
    need those mapped to mount points (e.g. /mnt/media_tv/Shows/file.mkv).

    MountMap stores {DriveLetter: LocalMountPrefix} -- no backslashes in the map.
    The service owns the ':\' separator knowledge.

    Windows workers with no mappings pass paths through unchanged.
    """

    def __init__(self, MountMap: dict = None, **_):
        """Initialize with drive letter to mount path mappings.

        Args:
            MountMap: Dict of {DriveLetter: LocalMountPrefix}.
                      e.g. {'T': '/mnt/media_tv/', 'M': '/mnt/movies/'}
        """
        self.IsLinux = platform.system().lower() != 'windows'
        self.MountMap = {k.upper(): v for k, v in (MountMap or {}).items()}

    def ToLocalPath(self, CanonicalPath: str) -> str:
        """Convert a canonical (DB) path to the local worker path.

        Parses the drive letter from position 0 and looks up the mount point.

        Example (Linux worker):
            'T:\\Shows\\Breaking Bad\\S01E01.mkv' -> '/mnt/media_tv/Shows/Breaking Bad/S01E01.mkv'
            'M:\\Movie Name\\movie.mkv'           -> '/mnt/movies/Movie Name/movie.mkv'
        """
        if not CanonicalPath or not self.MountMap:
            return CanonicalPath

        DriveLetter = CanonicalPath[0].upper()
        if DriveLetter in self.MountMap:
            # Strip drive letter + ':\'  (3 chars), prepend mount path
            LocalPath = self.MountMap[DriveLetter] + CanonicalPath[3:]
        else:
            LocalPath = CanonicalPath

        if self.IsLinux:
            LocalPath = LocalPath.replace('\\', '/')

        return LocalPath

    def ToCanonicalPath(self, LocalPath: str) -> str:
        """Convert a local worker path back to canonical (DB) format.

        Finds the mount prefix that matches, replaces with drive letter + ':\'

        Example (Linux worker):
            '/mnt/media_tv/Shows/Breaking Bad/S01E01.mkv' -> 'T:\\Shows\\Breaking Bad\\S01E01.mkv'
        """
        if not LocalPath or not self.MountMap:
            return LocalPath

        for DriveLetter, MountPrefix in self.MountMap.items():
            if LocalPath.startswith(MountPrefix):
                CanonicalPath = DriveLetter + ':\\' + LocalPath[len(MountPrefix):]
                return CanonicalPath.replace('/', '\\')

        return LocalPath.replace('/', '\\')
