import re
from dataclasses import dataclass
from typing import List, Optional


_TITLE_ENGLISH_REGEX = re.compile(r'english|eng\b|en-us|en-gb', re.IGNORECASE)


KEEP_ALL = 'keep-all'

LAYER_ISO_TAG = 'iso_tag'
LAYER_TITLE_REGEX = 'title_regex'
LAYER_SINGLE_STREAM = 'single_stream'
LAYER_DEFAULT_FLAG = 'default_flag'
LAYER_LIBRARY_DEFAULT = 'library_default'
LAYER_SPEECH_CACHE = 'speech_cache'
LAYER_KEEP_ALL = 'keep_all'


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C11
@dataclass
class StreamLanguage:
    """Per-stream detection result: index, language code (3-letter), layer that fired."""
    StreamIndex: int
    Language: str
    Layer: str


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C11
@dataclass
class DetectionResult:
    """Per-stream language tags + KeepPolicy ('keep-all' when no layer resolved)."""
    StreamLanguages: List[StreamLanguage]
    KeepPolicy: str


# directive: audio-vertical-live-encode-gaps | # see audio-normalization.C11
def _GetTagsLanguage(Stream):
    """Layer (a): ISO 639-2 tags.language; returns lowercase 3-letter code or None ('und' / empty are treated as not-detected so library default fires)."""
    Tags = Stream.get('tags') or {}
    Lang = Tags.get('language')
    if Lang and isinstance(Lang, str) and len(Lang.strip()) >= 2:
        Normalized = Lang.strip().lower()
        if Normalized in ('und', 'undef', 'undetermined'):
            return None
        return Normalized
    return None


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C11
def _GetTitleRegexLanguage(Stream):
    """Layer (b): regex against tags.title; returns 'eng' on match or None."""
    Tags = Stream.get('tags') or {}
    Title = Tags.get('title') or ''
    if _TITLE_ENGLISH_REGEX.search(Title):
        return 'eng'
    return None


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C11
def _GetDefaultFlagLanguage(Stream, LibraryDefault):
    """Layer (d): disposition.default == 1; returns LibraryDefault when default flag set."""
    Disposition = Stream.get('disposition') or {}
    if Disposition.get('default') in (1, True, '1'):
        return (LibraryDefault or 'und').lower()
    return None


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C19
def _GetSpeechCacheLanguage(Stream, SpeechCache):
    """Layer (f -- C19): consult cached Whisper-class detection; returns lowercase code or None."""
    if not SpeechCache:
        return None
    Idx = Stream.get('index')
    if Idx is None:
        return None
    Hit = SpeechCache.get(str(Idx)) or SpeechCache.get(Idx)
    if not Hit:
        return None
    Lang = Hit.get('Language') if isinstance(Hit, dict) else Hit
    if Lang and isinstance(Lang, str):
        return Lang.strip().lower()
    return None


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C11
class LanguageDetector:
    """Layered detection per C11: iso_tag -> title_regex -> single_stream -> default_flag -> library_default -> speech_cache."""

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C11
    def Detect(self, StreamMetadata, LibraryDefault=None, SpeechCache=None, EnableSpeechLayer=False):
        """Apply layers in order across audio streams; return per-stream tags + KeepPolicy."""
        Streams = list(StreamMetadata or [])
        if not Streams:
            return DetectionResult(StreamLanguages=[], KeepPolicy=KEEP_ALL)

        Results = []
        SingleStreamShortCircuit = len(Streams) == 1
        AnyResolvedNonTrivially = False

        for Stream in Streams:
            Idx = Stream.get('index')
            Lang = _GetTagsLanguage(Stream)
            Layer = LAYER_ISO_TAG if Lang else None

            if Lang is None:
                Lang = _GetTitleRegexLanguage(Stream)
                if Lang:
                    Layer = LAYER_TITLE_REGEX

            if Lang is None and SingleStreamShortCircuit and LibraryDefault:
                Lang = LibraryDefault.lower()
                Layer = LAYER_SINGLE_STREAM

            if Lang is None:
                Lang = _GetDefaultFlagLanguage(Stream, LibraryDefault)
                if Lang:
                    Layer = LAYER_DEFAULT_FLAG

            if Lang is None and LibraryDefault:
                Lang = LibraryDefault.lower()
                Layer = LAYER_LIBRARY_DEFAULT

            if Lang is None and EnableSpeechLayer:
                Lang = _GetSpeechCacheLanguage(Stream, SpeechCache)
                if Lang:
                    Layer = LAYER_SPEECH_CACHE

            if Lang is None:
                Lang = 'und'
                Layer = LAYER_KEEP_ALL
            else:
                AnyResolvedNonTrivially = AnyResolvedNonTrivially or (
                    Layer not in (LAYER_KEEP_ALL,)
                )

            Results.append(StreamLanguage(StreamIndex=Idx, Language=Lang, Layer=Layer))

        KeepPolicy = 'detected' if AnyResolvedNonTrivially else KEEP_ALL
        return DetectionResult(StreamLanguages=Results, KeepPolicy=KeepPolicy)
