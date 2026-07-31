from Core.DateTimeHelpers import FormatDuration


def test_zero_seconds():
    assert FormatDuration(0) == "00:00:00"


def test_under_one_minute():
    assert FormatDuration(45) == "00:00:45"


def test_hour_boundary():
    assert FormatDuration(3600) == "01:00:00"
    assert FormatDuration(3661) == "01:01:01"


def test_two_digit_hours():
    assert FormatDuration(99 * 3600 + 59 * 60 + 59) == "99:59:59"


def test_overflow_three_digit_hours():
    assert FormatDuration(100 * 3600 + 4 * 60 + 5) == "100:04:05"


def test_none_passthrough():
    assert FormatDuration(None) is None


def test_negative_floors_to_zero():
    assert FormatDuration(-5) == "00:00:00"


def test_float_seconds_truncated():
    assert FormatDuration(90.7) == "00:01:30"
