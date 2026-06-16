from Features.AudioNormalization.Repositories.AudioNormalizationConfigRepository import (
    AudioNormalizationConfigRepository,
)


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C9
def _GetField(MediaFile, FieldName):
    """Read FieldName off a MediaFile dict/object/CaseInsensitiveDict and return the value or None."""
    if hasattr(MediaFile, FieldName):
        return getattr(MediaFile, FieldName)
    if hasattr(MediaFile, 'get'):
        Val = MediaFile.get(FieldName)
        if Val is not None:
            return Val
        return MediaFile.get(FieldName.lower())
    return None


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C9
def _DeriveFolderScopeKey(MediaFile):
    """Return parent dirname of the file's RelativePath as the folder scope key or None."""
    Rel = _GetField(MediaFile, 'RelativePath')
    if not Rel:
        return None
    from Core.Path.LocalPath import LocalDirname
    Parent = LocalDirname(Rel)
    return Parent if Parent else None


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C9
class AudioPolicyResolver:
    """Walks item > folder > library > global; returns the most-specific AudioNormalizationConfig row."""

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C9
    def __init__(self, Repository=None):
        """Inject the repository; default to a fresh AudioNormalizationConfigRepository per db-is-authority."""
        self._Repository = Repository or AudioNormalizationConfigRepository()

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C9
    def GetEffectivePolicy(self, MediaFile):
        """Return the most-specific config row for MediaFile across item > folder > library > global."""
        ItemKey = _GetField(MediaFile, 'Id')
        if ItemKey is not None:
            Row = self._Repository.Get('item', str(ItemKey))
            if Row:
                return Row

        FolderKey = _DeriveFolderScopeKey(MediaFile)
        if FolderKey:
            Row = self._Repository.Get('folder', FolderKey)
            if Row:
                return Row

        LibraryKey = _GetField(MediaFile, 'StorageRootId')
        if LibraryKey is not None:
            Row = self._Repository.Get('library', str(LibraryKey))
            if Row:
                return Row

        return self._Repository.Get('global', None)
