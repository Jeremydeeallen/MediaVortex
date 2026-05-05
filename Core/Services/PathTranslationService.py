import platform


class PathTranslationService:
    """Translates file paths between canonical (DB) format and local worker format.

    Supports multiple share mappings so a single worker can access files across
    different drive letters / network shares (e.g. T:\, M:\, Z:\ each mounted
    at different Linux paths).

    Accepts either:
      - A list of (CanonicalPrefix, LocalMountPrefix) tuples  (multi-prefix)
      - A single ShareMountPrefix + ShareCanonicalPrefix       (legacy single-prefix)
    """

    def __init__(self, ShareMountPrefix: str = None, ShareCanonicalPrefix: str = "T:\\",
                 Mappings: list = None):
        """Initialize with share mappings.

        Args:
            Mappings: List of (CanonicalPrefix, LocalMountPrefix) tuples.
                      Takes priority over the single-prefix arguments.
            ShareMountPrefix: Single local mount prefix (legacy, used if Mappings is empty).
            ShareCanonicalPrefix: Single canonical prefix (legacy, used if Mappings is empty).
        """
        self.IsLinux = platform.system().lower() != 'windows'

        if Mappings:
            self.Mappings = [(c, l) for c, l in Mappings]
        elif ShareMountPrefix:
            self.Mappings = [(ShareCanonicalPrefix, ShareMountPrefix)]
        else:
            self.Mappings = []

    def ToLocalPath(self, CanonicalPath: str) -> str:
        """Convert a canonical (DB) path to the local worker path.

        Tries each mapping in order; first matching canonical prefix wins.

        Example (Linux worker with multiple mappings):
            'T:\\Shows\\Breaking Bad\\S01E01.mkv' -> '/mnt/media_tv/Shows/Breaking Bad/S01E01.mkv'
            'M:\\Movie Name\\movie.mkv'           -> '/mnt/movies/Movie Name/movie.mkv'
        """
        if not CanonicalPath:
            return CanonicalPath

        LocalPath = CanonicalPath
        for CanonicalPrefix, LocalMountPrefix in self.Mappings:
            if CanonicalPath.upper().startswith(CanonicalPrefix.upper()):
                LocalPath = LocalMountPrefix + CanonicalPath[len(CanonicalPrefix):]
                break

        if self.IsLinux:
            LocalPath = LocalPath.replace('\\', '/')

        return LocalPath

    def ToCanonicalPath(self, LocalPath: str) -> str:
        """Convert a local worker path back to canonical (DB) format.

        Tries each mapping in order; first matching local prefix wins.

        Example (Linux worker):
            '/mnt/media_tv/Shows/Breaking Bad/S01E01.mkv' -> 'T:\\Shows\\Breaking Bad\\S01E01.mkv'
        """
        if not LocalPath:
            return LocalPath

        CanonicalPath = LocalPath
        for CanonicalPrefix, LocalMountPrefix in self.Mappings:
            if LocalPath.startswith(LocalMountPrefix):
                CanonicalPath = CanonicalPrefix + LocalPath[len(LocalMountPrefix):]
                break

        CanonicalPath = CanonicalPath.replace('/', '\\')

        return CanonicalPath
