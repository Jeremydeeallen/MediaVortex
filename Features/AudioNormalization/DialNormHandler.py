DOLBY_DIALNORM_MIN = 1
DOLBY_DIALNORM_MAX = 31


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C20
def _ClampDialNorm(Value):
    """Clamp DialNorm to Dolby spec range [1, 31]."""
    if Value is None:
        return None
    Iv = int(round(Value))
    if Iv < DOLBY_DIALNORM_MIN:
        return DOLBY_DIALNORM_MIN
    if Iv > DOLBY_DIALNORM_MAX:
        return DOLBY_DIALNORM_MAX
    return Iv


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C20
def _ExtractSourceDialNorm(Stream):
    """Return the source DialNorm value (int) from ffprobe stream metadata, or None when absent."""
    if not Stream:
        return None
    Tags = Stream.get('tags') or {}
    for Key in ('DialNorm', 'dialnorm', 'DIALNORM'):
        Val = Tags.get(Key)
        if Val is not None:
            try:
                return _ClampDialNorm(int(Val))
            except (TypeError, ValueError):
                continue
    SideData = Stream.get('side_data_list') or []
    for Sd in SideData:
        if isinstance(Sd, dict):
            Val = Sd.get('dialnorm')
            if Val is not None:
                try:
                    return _ClampDialNorm(int(Val))
                except (TypeError, ValueError):
                    continue
    return None


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C20
class DialNormHandler:
    """Pass through source DialNorm on stream-copy of Original; compute fresh on re-encode."""

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C20
    def GetSourceDialNorm(self, Stream):
        """Return int 1..31 read from ffprobe stream metadata, or None when absent."""
        return _ExtractSourceDialNorm(Stream)

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C20
    def ComputeForLoudness(self, AchievedLufs):
        """Compute DialNorm from a target/achieved integrated loudness in LUFS (DialNorm = round(-1 * LUFS))."""
        if AchievedLufs is None:
            return None
        return _ClampDialNorm(-1 * AchievedLufs)

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C20
    def ResolveForTrack(self, TrackStrategy, SourceDialNorm, IsOriginalStreamCopy):
        """Pick the DialNorm value to emit: preserve source on Original stream-copy, otherwise compute from EffectiveTargetLufs."""
        if IsOriginalStreamCopy and SourceDialNorm is not None:
            return _ClampDialNorm(SourceDialNorm)
        if TrackStrategy is not None and TrackStrategy.EffectiveTargetLufs is not None:
            return self.ComputeForLoudness(TrackStrategy.EffectiveTargetLufs)
        return None
