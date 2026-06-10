# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C2

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.TranscodeJob.Emit.ResolutionCalculator import ResolutionCalculator


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C2
def _MakeMediaFile(Resolution=None):
    """Build a stub MediaFile exposing Resolution attribute."""
    return SimpleNamespace(Resolution=Resolution)


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C2
class TestResolutionCalculator:
    """Verify resolution-math methods ported from CommandBuilder."""

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C2
    def test_calculate_target_resolution_uses_profile_when_set(self):
        """ProfileSettings.TargetResolution wins over SourceResolution."""
        Calc = ResolutionCalculator()
        Result = Calc.CalculateTargetResolution({'TargetResolution': '720p'}, '1080p')
        assert Result == '720p'

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C2
    def test_calculate_target_resolution_falls_back_to_source(self):
        """No TargetResolution => returns SourceResolution unchanged."""
        Calc = ResolutionCalculator()
        Result = Calc.CalculateTargetResolution({}, '1080p')
        assert Result == '1080p'

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C2
    def test_calculate_scale_filter_emits_tier_width_for_720p(self):
        """Different src/target => width-anchored scale string at the target tier."""
        Calc = ResolutionCalculator()
        Filter = Calc.CalculateScaleFilter('1080p', '720p', _MakeMediaFile('1080p'))
        assert Filter == 'scale=w=1280:h=-2'

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C2
    def test_calculate_scale_filter_returns_none_when_src_equals_target(self):
        """Equal src/target => no scaling required."""
        Calc = ResolutionCalculator()
        assert Calc.CalculateScaleFilter('720p', '720p', _MakeMediaFile('720p')) is None

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C2
    def test_extract_height_from_resolution_handles_p_suffix(self):
        """'1080p' => 1080."""
        assert ResolutionCalculator().ExtractHeightFromResolution('1080p') == 1080

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C2
    def test_extract_height_from_resolution_handles_wxh_pattern(self):
        """'1920x1080' => 1080."""
        assert ResolutionCalculator().ExtractHeightFromResolution('1920x1080') == 1080

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C2
    def test_extract_height_default_on_garbage(self):
        """Unparseable input => 720 default per CommandBuilder behavior."""
        assert ResolutionCalculator().ExtractHeightFromResolution('garbage') == 720

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C2
    def test_get_source_dimensions_pillarbox_pattern(self):
        """'1920x802' (letterbox 2.40:1) => parsed as (1920,802)."""
        Calc = ResolutionCalculator()
        assert Calc.GetSourceDimensions(_MakeMediaFile('1920x802')) == (1920, 802)

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C2
    def test_get_source_dimensions_canonical_1080p(self):
        """'1080p' => canonical (1920,1080)."""
        Calc = ResolutionCalculator()
        assert Calc.GetSourceDimensions(_MakeMediaFile('1080p')) == (1920, 1080)

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C2
    def test_get_source_dimensions_safe_default_when_unset(self):
        """No Resolution => safe (1920,1080) default."""
        Calc = ResolutionCalculator()
        assert Calc.GetSourceDimensions(_MakeMediaFile(None)) == (1920, 1080)

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C2
    def test_calculate_width_from_height_canonical_tiers(self):
        """Canonical heights map to canonical widths."""
        Calc = ResolutionCalculator()
        assert Calc.CalculateWidthFromHeight(2160) == 3840
        assert Calc.CalculateWidthFromHeight(1080) == 1920
        assert Calc.CalculateWidthFromHeight(720) == 1280
        assert Calc.CalculateWidthFromHeight(480) == 854

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C2
    def test_calculate_width_from_height_with_aspect_ratio(self):
        """Custom aspect ratio scales width and forces even result."""
        Calc = ResolutionCalculator()
        Result = Calc.CalculateWidthFromHeight(802, AspectRatio=2.40)
        assert Result % 2 == 0
        assert Result == 1924
