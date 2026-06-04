# directive: path-security-audit | # see path.C1
from dataclasses import dataclass

import pytest
from hypothesis import given, strategies as st

from Core.Path.Path import Path, PathError


_PrintableNoSep = st.characters(
    min_codepoint=0x20,
    max_codepoint=0x7E,
    blacklist_characters="/\\:",
)


@given(
    Prefix=st.text(alphabet=_PrintableNoSep, min_size=0, max_size=8),
    Suffix=st.text(alphabet=_PrintableNoSep, min_size=0, max_size=8),
)
# directive: path-security-audit | # see path.C3
def test_nul_byte_rejected_anywhere(Prefix, Suffix):
    """C3: NUL byte rejected regardless of position in RelativePath."""
    Rel = Prefix + "\x00" + Suffix
    with pytest.raises(PathError):
        Path(7, Rel)


@given(
    Prefix=st.text(alphabet=_PrintableNoSep, min_size=0, max_size=8),
    Suffix=st.text(alphabet=_PrintableNoSep, min_size=0, max_size=8),
    Cp=st.integers(min_value=0x01, max_value=0x1F),
)
# directive: path-security-audit | # see path.C4
def test_low_control_char_rejected_anywhere(Prefix, Suffix, Cp):
    """C4: any control char x01-x1f rejected regardless of position."""
    Rel = Prefix + chr(Cp) + Suffix
    with pytest.raises(PathError):
        Path(7, Rel)


@given(
    Prefix=st.text(alphabet=_PrintableNoSep, min_size=0, max_size=8),
    Suffix=st.text(alphabet=_PrintableNoSep, min_size=0, max_size=8),
)
# directive: path-security-audit | # see path.C4
def test_del_char_rejected_anywhere(Prefix, Suffix):
    """C4: x7f DEL rejected regardless of position."""
    Rel = Prefix + "\x7f" + Suffix
    with pytest.raises(PathError):
        Path(7, Rel)


@given(
    Tail=st.text(alphabet=_PrintableNoSep, min_size=0, max_size=15),
    Ns=st.sampled_from(["\\\\?\\", "\\\\.\\", "//?/", "//./"]),
)
# directive: path-security-audit | # see path.C5
def test_win32_namespace_rejected(Tail, Ns):
    """C5: Win32 device namespace prefix rejected at construction."""
    Rel = Ns + Tail
    with pytest.raises(PathError):
        Path(7, Rel)


@given(
    Host=st.text(alphabet=_PrintableNoSep, min_size=1, max_size=8),
    Share=st.text(alphabet=_PrintableNoSep, min_size=1, max_size=8),
    Tail=st.text(alphabet=_PrintableNoSep, min_size=0, max_size=10),
    Sep=st.sampled_from(["\\", "/"]),
)
# directive: path-security-audit | # see path.C6
def test_unc_prefix_rejected(Host, Share, Tail, Sep):
    """C6: UNC prefix (\\\\host\\share or //host/share) rejected at constructor."""
    Rel = Sep + Sep + Host + Sep + Share + Sep + Tail
    with pytest.raises(PathError):
        Path(7, Rel)


_NFC_NFD_CASES = [
    ("nfc_precomposed_e_acute", "café.mkv"),
    ("nfd_combining_e_acute", "café.mkv"),
    ("turkish_dotless_i", "Istanbul̇.txt"),
    ("rtl_override", "foo‮bar.mkv"),
    ("zero_width_joiner", "foo‍bar.mkv"),
    ("emoji_segment", "Show \U0001F600 - file.mkv"),
    ("cyrillic", "Привет.txt"),
]


@pytest.mark.parametrize("CaseName,Rel", _NFC_NFD_CASES)
# directive: path-security-audit | # see path.C10
def test_unicode_accepted_byte_wise(CaseName, Rel):
    """C10/D13: Path accepts any Unicode without normalization (byte-wise)."""
    P = Path(7, Rel)
    assert P.RelativePath == Rel


# directive: path-security-audit | # see path.C10
def test_nfc_nfd_compare_unequal():
    """C10/D13: NFC and NFD encodings of cafe.mkv compare unequal (byte equality, no normalization)."""
    Nfc = Path(7, "café.mkv")
    Nfd = Path(7, "café.mkv")
    assert Nfc != Nfd
    assert Nfc.RelativePath != Nfd.RelativePath


@dataclass(frozen=True)
# directive: path-security-audit | # see path.C7
class _FakeWorker:
    """Minimal Worker protocol stand-in for Resolve tests; Platform field drives platform-aware checks."""

    Name: str = "test-worker"
    Platform: str = "windows"
    Prefix: str = "T:\\"

    # directive: path-security-audit | # see path.C7
    def ResolveStorageRoot(self, Sid):
        """Return configured prefix when Sid==7; None otherwise (simulates orphan)."""
        return self.Prefix if Sid == 7 else None


# directive: path-security-audit | # see path.C7
def _WinWorker():
    """Build a fake Windows worker for Resolve-time tests."""
    return _FakeWorker(Platform="windows", Prefix="T:\\")


# directive: path-security-audit | # see path.C7
def _LinuxWorker():
    """Build a fake Linux worker for Resolve-time tests."""
    return _FakeWorker(Platform="linux", Prefix="/mnt/media/")


_DOS_DEVICE_HAZARDS = [
    "CON", "con", "Con", "CON.txt", "CON.mkv",
    "PRN", "AUX", "NUL", "NUL.txt",
    "COM1", "COM5", "COM9", "LPT1", "LPT9",
    "Show/CON.mkv", "Show/season 1/AUX.txt",
]


@pytest.mark.parametrize("Rel", _DOS_DEVICE_HAZARDS)
# directive: path-security-audit | # see path.C7
def test_windows_resolve_rejects_dos_device_names(Rel):
    """C7: Windows worker Resolve raises on any segment whose basename matches a DOS device name (case-insensitive)."""
    P = Path(7, Rel)
    with pytest.raises(PathError):
        P.Resolve(_WinWorker())


@pytest.mark.parametrize("Rel", ["CON", "CON.txt", "NUL", "COM1", "Show/CON.mkv"])
# directive: path-security-audit | # see path.C7
def test_linux_resolve_accepts_dos_device_names(Rel):
    """C7: Non-Windows worker accepts DOS device names -- they are legitimate filenames on Linux/macOS."""
    P = Path(7, Rel)
    Result = P.Resolve(_LinuxWorker())
    assert Result.startswith("/mnt/media/")


_TRAILING_DOT_SPACE_HAZARDS = ["foo.", "foo ", "Show. /file.mkv", "Show /file.mkv"]


@pytest.mark.parametrize("Rel", _TRAILING_DOT_SPACE_HAZARDS)
# directive: path-security-audit | # see path.C8
def test_windows_resolve_rejects_trailing_dot_space(Rel):
    """C8: Windows worker Resolve raises on any segment ending in '.' or ' '."""
    P = Path(7, Rel)
    with pytest.raises(PathError):
        P.Resolve(_WinWorker())


@pytest.mark.parametrize("Rel", ["foo.", "foo ", "Show. /file.mkv"])
# directive: path-security-audit | # see path.C8
def test_linux_resolve_accepts_trailing_dot_space(Rel):
    """C8: Non-Windows worker accepts trailing dot or space -- legitimate on Linux."""
    P = Path(7, Rel)
    Result = P.Resolve(_LinuxWorker())
    assert Result.startswith("/mnt/media/")


_ADS_COLON_HAZARDS = ["foo:bar", "Show:S01E01.mkv", "track1:stream", "dir/file:hidden.dat"]


@pytest.mark.parametrize("Rel", _ADS_COLON_HAZARDS)
# directive: path-security-audit | # see path.C9
def test_windows_resolve_rejects_mid_segment_colon(Rel):
    """C9: Windows worker Resolve raises on any segment containing ':' (NTFS ADS marker)."""
    P = Path(7, Rel)
    with pytest.raises(PathError):
        P.Resolve(_WinWorker())


@pytest.mark.parametrize("Rel", ["foo:bar", "track1:stream", "dir/file:hidden.dat"])
# directive: path-security-audit | # see path.C9
def test_linux_resolve_accepts_mid_segment_colon(Rel):
    """C9: Non-Windows worker accepts mid-segment colons -- ADS is Windows-only."""
    P = Path(7, Rel)
    Result = P.Resolve(_LinuxWorker())
    assert Result.startswith("/mnt/media/")


_ADVERSARIAL_CONSTRUCTION_CASES = [
    ("nul_byte", "foo\x00bar"),
    ("control_01", "foo\x01bar"),
    ("control_1f", "foo\x1fbar"),
    ("control_7f", "foo\x7fbar"),
    ("win32_q", "\\\\?\\C:\\foo"),
    ("win32_dot", "\\\\.\\COM1"),
    ("unc_back", "\\\\host\\share\\foo"),
    ("unc_forward", "//host/share/foo"),
    ("leading_slash", "/abs/path"),
    ("leading_backslash", "\\abs\\path"),
    ("drive_letter_abs", "C:\\foo"),
    ("drive_letter_rel", "C:foo"),
    ("dotdot_start", "../escape"),
    ("dotdot_mid", "ok/../escape"),
]


# directive: path-security-audit | # see path.C11
def _construct_via_constructor(Rel):
    """Entry point: direct Path(7, Rel) construction."""
    Path(7, Rel)


# directive: path-security-audit | # see path.C11
def _construct_via_frompair(Rel):
    """Entry point: Path.FromPair(7, Rel) alias."""
    Path.FromPair(7, Rel)


# directive: path-security-audit | # see path.C11
def _construct_via_fromjson(Rel):
    """Entry point: Path.FromJsonDict reading RelativePath from a JSON payload."""
    Path.FromJsonDict({"StorageRootId": 7, "RelativePath": Rel})


# directive: path-security-audit | # see path.C11
def _construct_via_fromrow(Rel):
    """Entry point: Path.FromRow reading RelativePath from a DB row dict."""
    Path.FromRow({"StorageRootId": 7, "RelativePath": Rel})


_ENTRY_POINTS = [
    ("constructor", _construct_via_constructor),
    ("FromPair", _construct_via_frompair),
    ("FromJsonDict", _construct_via_fromjson),
    ("FromRow", _construct_via_fromrow),
]


@pytest.mark.parametrize("CaseName,Rel", _ADVERSARIAL_CONSTRUCTION_CASES)
@pytest.mark.parametrize("EntryName,EntryFn", _ENTRY_POINTS)
# directive: path-security-audit | # see path.C11
def test_cross_path_validation_symmetry(CaseName, Rel, EntryName, EntryFn):
    """C12: every adversarial RelativePath rejected by every direct construction entry point."""
    with pytest.raises(PathError):
        EntryFn(Rel)
