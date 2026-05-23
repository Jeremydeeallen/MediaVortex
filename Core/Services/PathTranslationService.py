import platform

from Core.PathNormalize import NormalizeCanonical


class PathTranslationService:
    """Translates file paths between canonical (DB) format and local worker format.

    DB paths use Windows drive letters (e.g. T:\\Shows\\file.mkv). Each worker
    has its own MountMap that says where each drive letter actually resolves on
    THIS host. The translation is the same shape on every platform -- only the
    prefix string differs:

      Linux worker:    {'T': '/mnt/media_tv/'}
        T:\\Shows\\foo.mkv -> /mnt/media_tv/Shows/foo.mkv

      Windows worker:  {'T': '\\\\10.0.0.43\\srv\\nfs-media-_tv\\'}
        T:\\Shows\\foo.mkv -> \\\\10.0.0.43\\srv\\nfs-media-_tv\\Shows\\foo.mkv

    The Windows UNC case is what resolves BUG-0008: the worker hands UNC strings
    to ffmpeg instead of drive-letter paths, bypassing the per-logon-session
    drive-letter binding that intermittently unbinds on the Microsoft NFS client.
    See WorkerService/windows-unc-path-translation.feature.md.

    MountMap stores {DriveLetter: LocalMountPrefix}. The prefix INCLUDES the
    trailing separator (POSIX '/' or Windows '\\'). The service owns the
    ':\\' separator knowledge on the canonical side.

    A worker with no mappings passes paths through unchanged -- legacy
    fallback for Windows hosts pre-BUG-0008-fix, where the drive letter is
    used directly. This fallback is intentional rollback safety.
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
        """Convert a canonical (DB) path to this worker's local path.

        Parses the drive letter from position 0 and looks up the mount prefix.

        Linux worker example:
            'T:\\Shows\\Breaking Bad\\S01E01.mkv' -> '/mnt/media_tv/Shows/Breaking Bad/S01E01.mkv'

        Windows worker example (with UNC MountMap):
            'T:\\Shows\\Breaking Bad\\S01E01.mkv' -> '\\\\10.0.0.43\\srv\\nfs-media-_tv\\Shows\\Breaking Bad\\S01E01.mkv'

        Returns the input unchanged if the MountMap is empty or the drive
        letter is not in the map.
        """
        if not CanonicalPath or not self.MountMap:
            return CanonicalPath

        DriveLetter = CanonicalPath[0].upper()
        if DriveLetter in self.MountMap:
            # Strip drive letter + colon + backslash (3 chars), prepend mount prefix
            LocalPath = self.MountMap[DriveLetter] + CanonicalPath[3:]
        else:
            LocalPath = CanonicalPath

        if self.IsLinux:
            LocalPath = LocalPath.replace('\\', '/')

        return LocalPath

    def ToCanonicalPath(self, LocalPath: str) -> str:
        """Convert a local worker path back to canonical (DB) format.

        Finds the mount prefix that matches, replaces with drive letter + colon + backslash.

        Example (Linux worker):
            '/mnt/media_tv/Shows/Breaking Bad/S01E01.mkv' -> 'T:\\Shows\\Breaking Bad\\S01E01.mkv'
        """
        if not LocalPath or not self.MountMap:
            return NormalizeCanonical(LocalPath) if LocalPath else LocalPath

        for DriveLetter, MountPrefix in self.MountMap.items():
            if LocalPath.startswith(MountPrefix):
                CanonicalPath = DriveLetter + ':\\' + LocalPath[len(MountPrefix):]
                return NormalizeCanonical(CanonicalPath)

        return NormalizeCanonical(LocalPath)
