# directive: transcode-flow-canonical | # see transcode.ST2
"""Mode metadata mirror of ProcessingModes table; source of truth is the DB row (per db-is-authority.md). Code mirror exists so callers outside claim-SQL can look up policy without a per-call DB roundtrip; drift is caught by TestProcessingModeMetadataMirror."""
from typing import Optional


_METADATA = {
    'Transcode':   {'WorkBucket': 'Transcode',   'WorkBucketFilterSql': "m.WorkBucket = 'Transcode'",            'SupportsFocus': False, 'RequiresProfileGates': True,  'RequiresInterlacedFilter': True,  'RequiresVmaf': True,  'DefaultProfileNameFallback': 'Transcode'},
    'Remux':       {'WorkBucket': 'Remux',       'WorkBucketFilterSql': "m.WorkBucket = 'Remux'",                'SupportsFocus': False, 'RequiresProfileGates': False, 'RequiresInterlacedFilter': False, 'RequiresVmaf': False, 'DefaultProfileNameFallback': 'Remux'},
    'AudioFix':    {'WorkBucket': 'AudioFix',    'WorkBucketFilterSql': "m.WorkBucket = 'AudioFix'",             'SupportsFocus': False, 'RequiresProfileGates': False, 'RequiresInterlacedFilter': False, 'RequiresVmaf': False, 'DefaultProfileNameFallback': 'AudioFix'},
    'SubtitleFix': {'WorkBucket': 'SubtitleFix', 'WorkBucketFilterSql': "m.WorkBucket = 'SubtitleFix'",          'SupportsFocus': False, 'RequiresProfileGates': False, 'RequiresInterlacedFilter': False, 'RequiresVmaf': False, 'DefaultProfileNameFallback': 'SubtitleFix'},
    'Quick':       {'WorkBucket': None,          'WorkBucketFilterSql': "m.WorkBucket IN ('Remux', 'AudioFix')", 'SupportsFocus': True,  'RequiresProfileGates': False, 'RequiresInterlacedFilter': False, 'RequiresVmaf': False, 'DefaultProfileNameFallback': 'Quick'},
}

VALID_MODES = frozenset(_METADATA.keys())


# directive: transcode-flow-canonical | # see transcode.ST2
def Get(Mode: str) -> Optional[dict]:
    """Return metadata dict for Mode, or None if unknown; caller decides fallback."""
    return _METADATA.get(Mode)


# directive: transcode-flow-canonical | # see transcode.ST2
def GetOrDefault(Mode: str, DefaultMode: str = 'Transcode') -> dict:
    """Return metadata for Mode; falls back to DefaultMode metadata when Mode is unknown."""
    return _METADATA.get(Mode) or _METADATA[DefaultMode]


# directive: transcode-flow-canonical | # see transcode.ST2
def IsKnown(Mode: str) -> bool:
    """Predicate for orchestration-mode sentinels; replaces `Mode in ('Transcode',...)` literal-string enumerations."""
    return Mode in VALID_MODES


# directive: transcode-flow-canonical | # see transcode.ST2
def WorkBucketFor(Mode: str) -> Optional[str]:
    """Return the m.WorkBucket value(s) a queue candidate must have for this Mode's candidate query; None means the Mode has no single-bucket admission filter (e.g. Quick spans Remux+AudioFix)."""
    Meta = _METADATA.get(Mode)
    return Meta.get('WorkBucket') if Meta else None
