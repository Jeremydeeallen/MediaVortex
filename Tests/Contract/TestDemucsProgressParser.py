from Features.AudioNormalization.Services.DemucsDaemonClient import _TQDM_LINE_RE


def _parse(Line):
    Match = _TQDM_LINE_RE.match(Line.rstrip())
    if not Match:
        return None
    return int(Match.group(1)), float(Match.group(2)), float(Match.group(3))


def test_start_tick():
    assert _parse("  0%|                                                                     | 0.0/35.099999999999994 [00:00<?, ?seconds/s]") == (0, 0.0, 35.099999999999994)


def test_mid_tick():
    assert _parse(" 17%|██████████                                                  | 5.85/35.099999999999994 [00:01<00:09,  2.96seconds/s]") == (17, 5.85, 35.099999999999994)


def test_end_tick():
    assert _parse("100%|██████████████████████████████████████████████| 35.099999999999994/35.099999999999994 [00:06<00:00,  5.45seconds/s]") == (100, 35.099999999999994, 35.099999999999994)


def test_leading_whitespace_optional():
    assert _parse("50%|xxx| 5/10") == (50, 5.0, 10.0)


def test_non_tqdm_line_rejected():
    assert _parse("Selected model is a bag of 1 models.") is None
    assert _parse("Separating track C:\\Windows\\Temp\\probe30.wav") is None
    assert _parse("") is None
    assert _parse("some torch warning about deprecated api") is None


def test_percent_not_at_start_rejected():
    assert _parse("some prefix 42%|bar| 4/10") is None
