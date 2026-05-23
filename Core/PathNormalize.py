r"""Path normalization for the canonical FilePath format stored in MediaFiles
and every other path column.

Canonical shape: `<DriveLetter>:\<segment>\<segment>\...\<filename>` with
exactly one backslash between segments. No POSIX separators, no doubled
separators, no leading separator after the drive marker.

Two callers:
  - Insert-side: NormalizeCanonical(path) before every write to a path column.
    Defensive against doubled separators from os.walk over UNC roots,
    string concatenations that join a trailing-sep prefix with a leading-sep
    remainder, mixed separator styles, etc.
  - Read-side: ExtractShowFolder(path) for surfaces that group files by
    show. Returns the show-folder segment regardless of input shape; never
    returns empty string for a well-formed path.
"""

import re


_CANONICAL_DRIVE_RX = re.compile(r'^([A-Za-z]):[\\/]+')
_UNC_PREFIX_RX = re.compile(r'^[\\/]{2,}')


def NormalizeCanonical(Path: str) -> str:
    """Return Path in the canonical FilePath shape.

    Accepts drive-letter, UNC, POSIX, and malformed (doubled-separator)
    inputs. Returns drive-letter shape with single backslash separators.
    UNC inputs are returned unchanged in their leading `\\\\host\\share`
    portion but normalized internally. POSIX inputs are returned with
    backslashes.

    Idempotent: NormalizeCanonical(NormalizeCanonical(p)) == NormalizeCanonical(p).
    Empty / None input returns the input unchanged.
    """
    if not Path:
        return Path

    IsUnc = bool(_UNC_PREFIX_RX.match(Path))
    if IsUnc:
        Body = _UNC_PREFIX_RX.sub('', Path).replace('/', '\\')
        Collapsed = re.sub(r'\\+', r'\\', Body)
        return '\\\\' + Collapsed

    DriveMatch = _CANONICAL_DRIVE_RX.match(Path)
    if DriveMatch:
        Drive = DriveMatch.group(1).upper()
        Remainder = Path[DriveMatch.end():].replace('/', '\\').lstrip('\\')
        Collapsed = re.sub(r'\\+', r'\\', Remainder)
        return Drive + ':\\' + Collapsed

    Backslashed = Path.replace('/', '\\')
    return re.sub(r'\\+', r'\\', Backslashed)


def ExtractShowFolder(Path: str) -> str:
    """Return the show-folder segment from a canonical FilePath.

    By repository convention, the show folder is the segment immediately
    below the share root (drive letter or UNC share). Returns 'Unknown'
    if the path has no segment in that slot.
    """
    if not Path:
        return 'Unknown'

    Normalized = NormalizeCanonical(Path)

    if Normalized.startswith('\\\\'):
        Parts = Normalized[2:].split('\\')
        return Parts[2] if len(Parts) >= 3 and Parts[2] else 'Unknown'

    DriveMatch = _CANONICAL_DRIVE_RX.match(Normalized)
    if DriveMatch:
        Remainder = Normalized[DriveMatch.end():]
        Parts = Remainder.split('\\')
        return Parts[0] if Parts and Parts[0] else 'Unknown'

    Parts = Normalized.split('\\')
    return Parts[0] if Parts and Parts[0] else 'Unknown'
