# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.O2
PRE_VERTICAL_POLICY_VALUES = ('aggressive', 'lazy', 'none')


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.O2
def ValidatePreVerticalPolicy(Value):
    """Reject anything outside the CHECK constraint set so the API envelope explains it instead of the DB."""
    Lowered = (Value or 'lazy').strip().lower()
    if Lowered not in PRE_VERTICAL_POLICY_VALUES:
        raise ValueError(f"PreVerticalReNormalizePolicy must be one of {PRE_VERTICAL_POLICY_VALUES}, got {Value!r}")
    return Lowered
