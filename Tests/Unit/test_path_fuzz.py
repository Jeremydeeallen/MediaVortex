from hypothesis import given, settings, strategies as st
from Core.Path.Path import Path, PathError


ROOTS = [
    {"Id": 1, "CanonicalPrefix": "\\\\10.0.0.61\\xxx\\"},
    {"Id": 2, "CanonicalPrefix": "T:\\"},
    {"Id": 3, "CanonicalPrefix": "/mnt/media_tv/"},
    {"Id": 4, "CanonicalPrefix": "Z:\\"},
]
ROOTS_SORTED = sorted(ROOTS, key=lambda r: len(r["CanonicalPrefix"]), reverse=True)
PREFIX_MAP = {r["Id"]: r["CanonicalPrefix"] for r in ROOTS}
VALID_IDS = [r["Id"] for r in ROOTS]


_DOS_NAMES = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}


def _is_safe_segment(s: str) -> bool:
    if not s:
        return False
    if s.endswith(".") or s.endswith(" "):
        return False
    if s.startswith("."):
        return False
    if ".." in s:
        return False
    stem = s.split(".", 1)[0].upper()
    if stem in _DOS_NAMES:
        return False
    return True


_SAFE_CHARS = st.characters(
    whitelist_categories=("Ll", "Lu", "Nd"),
    whitelist_characters="-_ .",
    max_codepoint=126,
)
_safe_segment = st.text(alphabet=_SAFE_CHARS, min_size=1, max_size=20).filter(_is_safe_segment)
_rel_path = st.lists(_safe_segment, min_size=0, max_size=5).map(lambda segs: "/".join(segs))
_storage_id = st.sampled_from(VALID_IDS)


# directive: path-class-perfection | # see path.C23
@given(sid=_storage_id, rel=_rel_path)
@settings(max_examples=1000)
def test_round_trip_canonical_display_to_legacy_string(sid, rel):
    p = Path(sid, rel)
    canonical = p.CanonicalDisplay(PREFIX_MAP)
    parsed = Path.FromLegacyString(canonical, ROOTS_SORTED)
    assert parsed == p


# directive: path-class-perfection | # see path.C23
@given(sid=_storage_id, rel=_rel_path)
@settings(max_examples=1000)
def test_round_trip_json_dict(sid, rel):
    p = Path(sid, rel)
    restored = Path.FromJsonDict(p.ToJsonDict())
    assert restored == p


# directive: path-class-perfection | # see path.C23
@given(sid=_storage_id, rel=_rel_path)
@settings(max_examples=1000)
def test_round_trip_from_row(sid, rel):
    p = Path(sid, rel)
    row = {"StorageRootId": sid, "RelativePath": rel}
    restored = Path.FromRow(row)
    assert restored == p


# directive: path-class-perfection | # see path.C23
def test_fromlegacy_raises_on_unknown_prefix():
    import pytest
    with pytest.raises(PathError):
        Path.FromLegacyString(r"X:\unknown\path.mkv", ROOTS_SORTED)
    with pytest.raises(PathError):
        Path.FromLegacyString("", ROOTS_SORTED)
