SILENCE_FLOOR_LUFS = -60.0


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
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


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
class LoudnessMeasurementValidator:
    """Returns False when any of the four ebur128 measurements is NULL or SourceIntegratedLufs <= -60."""

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
    def IsValid(self, MediaFile):
        """True when the four ebur128 columns are populated and SourceIntegratedLufs is above the silence floor."""
        Integrated = _GetField(MediaFile, 'SourceIntegratedLufs')
        LoudnessRange = _GetField(MediaFile, 'SourceLoudnessRangeLU')
        TruePeak = _GetField(MediaFile, 'SourceTruePeakDbtp')
        Threshold = _GetField(MediaFile, 'SourceIntegratedThresholdLufs')
        if Integrated is None or LoudnessRange is None or TruePeak is None or Threshold is None:
            return False
        return Integrated > SILENCE_FLOOR_LUFS

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
    def Reason(self, MediaFile):
        """Return 'invalid_loudness_measurement' when invalid, None when valid."""
        return None if self.IsValid(MediaFile) else 'invalid_loudness_measurement'
