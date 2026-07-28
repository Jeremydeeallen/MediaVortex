# directive: audio-language-detection
class LanguageEnrichmentError(Exception):

    def __init__(self, MediaFileId, Reason, Detail=None):
        self.MediaFileId = MediaFileId
        self.Reason = Reason
        self.Detail = Detail
        super().__init__(f"MediaFileId={MediaFileId} Reason={Reason} Detail={Detail}")
