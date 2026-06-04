# directive: path-property-and-fuzz | # see path.C1
from hypothesis import given, strategies as st

from Core.Path.Path import Path, PathError


_SegAlphabet = st.characters(
    min_codepoint=0x20,
    max_codepoint=0x7E,
    blacklist_characters="/\\",
)


# directive: path-property-and-fuzz | # see path.C4
def _SafeSegment(Seg: str) -> bool:
    """Segment is non-empty, not '.' or '..', and not drive-letter-prefixed (D9)."""
    if Seg == "" or Seg == "." or Seg == "..":
        return False
    if len(Seg) >= 2 and Seg[0].isalpha() and Seg[0].isascii() and Seg[1] == ":":
        return False
    return True


_Segments = st.text(alphabet=_SegAlphabet, min_size=1, max_size=8).filter(_SafeSegment)


@st.composite
# directive: path-property-and-fuzz | # see path.C3
def StorageRootIds(draw):
    """StorageRootId strategy: int 1..10000, no booleans."""
    return draw(st.integers(min_value=1, max_value=10_000))


@st.composite
# directive: path-property-and-fuzz | # see path.C4
def RelPathNormalized(draw):
    """Forward-slash-only RelativePath (post-normalization form). May be empty (root)."""
    if draw(st.booleans()):
        return ""
    N = draw(st.integers(min_value=1, max_value=6))
    Parts = [draw(_Segments) for _ in range(N)]
    return "/".join(Parts)


@st.composite
# directive: path-property-and-fuzz | # see path.C4
def RelPathMixedSeparators(draw):
    """RelativePath input that mixes '/' and '\\\\'; constructor must normalize to forward."""
    if draw(st.booleans()):
        return ""
    N = draw(st.integers(min_value=1, max_value=6))
    Parts = [draw(_Segments) for _ in range(N)]
    if N == 1:
        return Parts[0]
    Seps = [draw(st.sampled_from(["/", "\\"])) for _ in range(N - 1)]
    Out = Parts[0]
    for Sep, Part in zip(Seps, Parts[1:]):
        Out += Sep + Part
    return Out


@st.composite
# directive: path-property-and-fuzz | # see path.C1
def Paths(draw):
    """Any constructible Path (root or non-root)."""
    return Path(draw(StorageRootIds()), draw(RelPathNormalized()))


@st.composite
# directive: path-property-and-fuzz | # see path.C12
def PathsNonRoot(draw):
    """Non-root Path (RelativePath non-empty, at least one segment)."""
    Sid = draw(StorageRootIds())
    N = draw(st.integers(min_value=1, max_value=6))
    Parts = [draw(_Segments) for _ in range(N)]
    return Path(Sid, "/".join(Parts))


@st.composite
# directive: path-property-and-fuzz | # see path.S6
def LegacyCanonicalTriple(draw):
    """Synthetic (sid, prefix, canonical, expected_rel) over UNC/drive/POSIX shapes (S6 zoo)."""
    Sid = draw(StorageRootIds())
    Shape = draw(st.sampled_from(["unc", "drive", "posix"]))
    Alpha = st.text(
        alphabet=st.characters(min_codepoint=ord("a"), max_codepoint=ord("z")),
        min_size=1,
        max_size=8,
    )
    if Shape == "unc":
        Host = draw(Alpha)
        Share = draw(Alpha)
        Prefix = f"\\\\{Host}\\{Share}\\"
        TailSep = "\\"
    elif Shape == "drive":
        Letter = draw(st.sampled_from(list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")))
        Prefix = f"{Letter}:\\"
        TailSep = "\\"
    else:
        Root = draw(Alpha)
        Prefix = f"/{Root}/"
        TailSep = "/"
    N = draw(st.integers(min_value=0, max_value=5))
    Parts = [draw(_Segments) for _ in range(N)]
    Tail = TailSep.join(Parts)
    Canonical = Prefix + Tail
    ExpectedRel = "/".join(Parts)
    return Sid, Prefix, Canonical, ExpectedRel


@given(P=Paths())
# directive: path-property-and-fuzz | # see path.C1
def test_equality_reflexivity(P):
    """C3: p == p for every constructible Path."""
    assert P == P


@given(Sid=StorageRootIds(), Rel=RelPathNormalized())
# directive: path-property-and-fuzz | # see path.C1
def test_equality_symmetry(Sid, Rel):
    """C4: (a == b) iff (b == a) for paths sharing the same typed pair."""
    A = Path(Sid, Rel)
    B = Path(Sid, Rel)
    assert (A == B) == (B == A)
    assert A == B and B == A


@given(Sid=StorageRootIds(), Rel=RelPathNormalized())
# directive: path-property-and-fuzz | # see path.C1
def test_equality_transitivity(Sid, Rel):
    """C5: a == b and b == c implies a == c."""
    A = Path(Sid, Rel)
    B = Path(Sid, Rel)
    C = Path(Sid, Rel)
    assert A == B and B == C
    assert A == C


@given(Sid=StorageRootIds(), Rel=RelPathNormalized())
# directive: path-property-and-fuzz | # see path.C1
def test_hash_consistent_with_equality(Sid, Rel):
    """C6: a == b implies hash(a) == hash(b); usable as dict / set key."""
    A = Path(Sid, Rel)
    B = Path(Sid, Rel)
    assert A == B
    assert hash(A) == hash(B)
    assert {A, B} == {A}


@given(P=Paths())
# directive: path-property-and-fuzz | # see path.S2
def test_json_round_trip(P):
    """C7 / S2: FromJsonDict(p.ToJsonDict()) == p for any constructible Path."""
    Payload = P.ToJsonDict()
    assert set(Payload.keys()) == {"StorageRootId", "RelativePath"}
    assert Path.FromJsonDict(Payload) == P


@given(T=LegacyCanonicalTriple())
# directive: path-property-and-fuzz | # see path.S6
def test_legacy_string_round_trip(T):
    """C8 / S6: prefix + shape-correct tail parses to Path(id, normalized_tail)."""
    Sid, Prefix, Canonical, ExpectedRel = T
    Roots = [{"Id": Sid, "CanonicalPrefix": Prefix}]
    Result = Path.FromLegacyString(Canonical, Roots)
    assert Result == Path(Sid, ExpectedRel)


@given(Sid=StorageRootIds(), Raw=RelPathMixedSeparators())
# directive: path-property-and-fuzz | # see path.C4
def test_normalization_idempotent(Sid, Raw):
    """C9 / D9: re-feeding the post-normalization RelativePath into the constructor is a no-op."""
    P1 = Path(Sid, Raw)
    P2 = Path(Sid, P1.RelativePath)
    assert P2.RelativePath == P1.RelativePath
    assert P2 == P1


@given(P=PathsNonRoot())
# directive: path-property-and-fuzz | # see path.C12
def test_parentdir_join_identity(P):
    """C10 / C12: p.ParentDir().Join(p.LastSegment()) == p for any non-root Path."""
    Parent = P.ParentDir()
    Last = P.LastSegment()
    assert Parent.Join(Last) == P


@given(P=Paths())
# directive: path-property-and-fuzz | # see path.C14
def test_splitext_structure(P):
    """C11 / C14: SplitExt reconstructs by concat, preserves root, and ext is dotted-or-empty."""
    Base, Ext = P.SplitExt()
    assert Base.RelativePath + Ext == P.RelativePath
    assert Base.StorageRootId == P.StorageRootId
    if Ext != "":
        assert Ext.startswith(".")
        assert "/" not in Ext
        assert "\\" not in Ext
        assert "." not in Ext[1:]
