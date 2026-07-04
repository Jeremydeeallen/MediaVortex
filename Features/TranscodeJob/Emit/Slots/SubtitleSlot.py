from typing import List, Optional

from Core.Logging.LoggingService import LoggingService


IMAGE_SUB_CODECS = frozenset({
    'hdmv_pgs_subtitle', 'pgssub', 'pgs',
    'dvd_subtitle', 'dvdsub',
    'dvb_subtitle', 'dvbsub', 'dvb_teletext',
    'xsub',
})


# directive: transcode-flow-canonical | # see transcode.ST5
class SubtitleSlot:

    # directive: transcode-flow-canonical | # see transcode.ST5
    def Emit(self, TargetContainer: str, SubtitleFormats: Optional[str] = None) -> List[str]:
        Target = (TargetContainer or 'mp4').lower()
        Formats = [F.strip().lower() for F in (SubtitleFormats or '').split(',') if F.strip()]
        HasImage = any(F in IMAGE_SUB_CODECS for F in Formats)
        HasText = any(F and F not in IMAGE_SUB_CODECS for F in Formats)
        if Target == 'mp4':
            if HasImage and not HasText:
                LoggingService.LogWarning(
                    f"SubtitleSlot: dropping image-based subtitles ({','.join(Formats)}) targeting mp4; OCR-to-text conversion deferred (BUG-0083 slot).",
                    "SubtitleSlot", "Emit",
                )
                return []
            if HasImage:
                LoggingService.LogWarning(
                    f"SubtitleSlot: mixed subtitle formats ({','.join(Formats)}) targeting mp4; ffmpeg will keep text streams and may drop image streams under mov_text muxer.",
                    "SubtitleSlot", "Emit",
                )
            return ['-map', '0:s?', '-c:s', 'mov_text']
        return ['-map', '0:s?', '-c:s', 'copy']
