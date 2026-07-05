from enum import Enum


# directive: transcode-flow-canonical
class JobPhase(str, Enum):
    """Domain phase of an in-flight job; each phase has distinct stuck-detection semantics."""

    Setup = "Setup"
    Encoding = "Encoding"
    PostEncode = "PostEncode"
    Verifying = "Verifying"

    # directive: transcode-flow-canonical
    @classmethod
    def FromString(cls, Value):
        if Value is None:
            return None
        if isinstance(Value, cls):
            return Value
        for Member in cls:
            if Member.value == Value:
                return Member
        raise ValueError(f"Unknown JobPhase value: {Value!r}")
