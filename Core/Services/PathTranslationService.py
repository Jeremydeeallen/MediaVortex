import os
import platform


class PathTranslationService:
    """Translates file paths between canonical (DB) format and local worker format.

    Canonical paths use the ShareCanonicalPrefix (e.g. 'T:\\') as stored in the database.
    Local paths use the ShareMountPrefix for the current worker (e.g. '/mnt/media/' on Linux
    or 'T:\\' on Windows if the share is mounted at the same letter).
    """

    def __init__(self, ShareMountPrefix: str, ShareCanonicalPrefix: str = "T:\\"):
        self.ShareMountPrefix = ShareMountPrefix
        self.ShareCanonicalPrefix = ShareCanonicalPrefix
        self.IsLinux = platform.system().lower() != 'windows'

    def ToLocalPath(self, CanonicalPath: str) -> str:
        """Convert a canonical (DB) path to the local worker path.

        Example (Linux worker):
            'T:\\Shows\\Breaking Bad\\S01E01.mkv' -> '/mnt/media/Shows/Breaking Bad/S01E01.mkv'
        Example (Windows worker with same mount):
            'T:\\Shows\\Breaking Bad\\S01E01.mkv' -> 'T:\\Shows\\Breaking Bad\\S01E01.mkv' (unchanged)
        """
        if not CanonicalPath:
            return CanonicalPath

        # Replace canonical prefix with local mount prefix (case-insensitive on the prefix)
        LocalPath = CanonicalPath
        if CanonicalPath.upper().startswith(self.ShareCanonicalPrefix.upper()):
            LocalPath = self.ShareMountPrefix + CanonicalPath[len(self.ShareCanonicalPrefix):]

        # Convert path separators for the target platform
        if self.IsLinux:
            LocalPath = LocalPath.replace('\\', '/')

        return LocalPath

    def ToCanonicalPath(self, LocalPath: str) -> str:
        """Convert a local worker path back to canonical (DB) format.

        Example (Linux worker):
            '/mnt/media/Shows/Breaking Bad/S01E01.mkv' -> 'T:\\Shows\\Breaking Bad\\S01E01.mkv'
        """
        if not LocalPath:
            return LocalPath

        # Replace local mount prefix with canonical prefix
        CanonicalPath = LocalPath
        if LocalPath.startswith(self.ShareMountPrefix):
            CanonicalPath = self.ShareCanonicalPrefix + LocalPath[len(self.ShareMountPrefix):]

        # Canonical paths always use backslashes (Windows format for DB consistency)
        CanonicalPath = CanonicalPath.replace('/', '\\')

        return CanonicalPath
