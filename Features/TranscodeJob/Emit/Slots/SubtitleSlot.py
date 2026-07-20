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
    def Emit(self, TargetContainer: str, SubtitleFormats: Optional[str] = None, SubtitleStreams: Optional[list] = None) -> List[str]:
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
                # Mixed: -map 0:s? would grab bitmap streams too and ffmpeg refuses bitmap->mov_text (rc=234). Need per-index maps for text streams only. Requires probe-supplied (index, codec) list; ffmpeg map syntax doesn't support codec_name selector.
                if SubtitleStreams:
                    TextIndices = [Idx for (Idx, Codec) in SubtitleStreams if (Codec or '').lower() not in IMAGE_SUB_CODECS]
                    if TextIndices:
                        LoggingService.LogInfo(
                            f"SubtitleSlot: mixed subtitle formats ({','.join(Formats)}) targeting mp4; mapping text stream indices {TextIndices}, dropping bitmap (BUG-0083 slot).",
                            "SubtitleSlot", "Emit",
                        )
                        Parts: List[str] = []
                        for Idx in TextIndices:
                            Parts.extend(['-map', f'0:{Idx}?'])
                        Parts.extend(['-c:s', 'mov_text'])
                        return Parts
                    LoggingService.LogWarning(
                        f"SubtitleSlot: mixed subtitle formats ({','.join(Formats)}) but probe returned no text stream indices; dropping all subs.",
                        "SubtitleSlot", "Emit",
                    )
                    return []
                # Fallback (no probe indices): drop all -- previous permissive path shipped `-map 0:s?` and ffmpeg errored rc=234 (BUG-0083).
                LoggingService.LogWarning(
                    f"SubtitleSlot: mixed subtitle formats ({','.join(Formats)}) targeting mp4 without stream-index probe; dropping all to avoid ffmpeg rc=234. Pass SubtitleStreams=[(idx,codec),...] to preserve text streams.",
                    "SubtitleSlot", "Emit",
                )
                return []
            return ['-map', '0:s?', '-c:s', 'mov_text']
        return ['-map', '0:s?', '-c:s', 'copy']
