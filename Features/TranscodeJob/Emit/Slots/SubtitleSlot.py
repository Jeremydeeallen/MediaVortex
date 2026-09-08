from typing import List, Optional

from Core.Logging.LoggingService import LoggingService


IMAGE_SUB_CODECS = frozenset({
    'hdmv_pgs_subtitle', 'pgssub', 'pgs',
    'dvd_subtitle', 'dvdsub',
    'dvb_subtitle', 'dvbsub', 'dvb_teletext',
    'xsub',
})

# directive: bug-0090-subtitle-codec-filter
TEXT_SUB_CODECS = frozenset({
    'subrip', 'srt',
    'ass', 'ssa',
    'mov_text', 'tx3g',
    'webvtt', 'vtt',
    'microdvd',
    'text',
})

# directive: bug-0090-subtitle-codec-filter
UNDECODABLE_SUB_CODECS = frozenset({'unknown', 'none', 'null', ''})


# directive: bug-0090-subtitle-codec-filter | # see command-composer.C4
class SubtitleSlot:

    # directive: bug-0090-subtitle-codec-filter | # see command-composer.C4
    def Emit(self, TargetContainer: str, SubtitleFormats: Optional[str] = None, SubtitleStreams: Optional[list] = None) -> List[str]:
        Target = (TargetContainer or 'mp4').lower()
        if Target != 'mp4':
            return ['-map', '0:s?', '-c:s', 'copy']

        if SubtitleStreams:
            Kept = []
            DroppedImage = []
            DroppedUndecodable = []
            DroppedOther = []
            for Idx, Codec in SubtitleStreams:
                C = (Codec or '').lower()
                if C in TEXT_SUB_CODECS:
                    Kept.append((Idx, C))
                elif C in IMAGE_SUB_CODECS:
                    DroppedImage.append((Idx, C))
                elif C in UNDECODABLE_SUB_CODECS:
                    DroppedUndecodable.append((Idx, C))
                else:
                    DroppedOther.append((Idx, C))

            if DroppedImage or DroppedUndecodable or DroppedOther:
                LoggingService.LogInfo(
                    f"SubtitleSlot: kept={len(Kept)} dropped_image={len(DroppedImage)} dropped_undecodable={len(DroppedUndecodable)} dropped_other={len(DroppedOther)}; drop_detail={DroppedImage + DroppedUndecodable + DroppedOther}",
                    "SubtitleSlot", "Emit",
                )
            if not Kept:
                return []
            Parts: List[str] = []
            for Idx, _ in Kept:
                Parts.extend(['-map', f'0:{Idx}?'])
            Parts.extend(['-c:s', 'mov_text'])
            return Parts

        Formats = [F.strip().lower() for F in (SubtitleFormats or '').split(',') if F.strip()]
        if not Formats:
            return ['-map', '0:s?', '-c:s', 'mov_text']

        HasImage = any(F in IMAGE_SUB_CODECS for F in Formats)
        HasUndecodable = any(F in UNDECODABLE_SUB_CODECS for F in Formats)
        HasText = any(F in TEXT_SUB_CODECS for F in Formats)

        if HasText and not HasImage and not HasUndecodable:
            return ['-map', '0:s?', '-c:s', 'mov_text']

        LoggingService.LogWarning(
            f"SubtitleSlot: mixed/undecodable subtitle formats ({','.join(Formats)}) targeting mp4 without per-stream probe; dropping all to avoid ffmpeg rc=234. Pass SubtitleStreams=[(idx,codec),...] to preserve text streams.",
            "SubtitleSlot", "Emit",
        )
        return []
