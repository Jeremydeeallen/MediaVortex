# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C3

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.TranscodeJob.Emit.OutputFilenameBuilder import OutputFilenameBuilder


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C3
class TestOutputFilenameBuilder:
    """Verify filename builder ported from CommandBuilder (single source of truth)."""

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C3
    def test_same_resolution_emits_mv_mp4_inprogress(self):
        """Identical src/target => '<base>-mv.mp4.inprogress'."""
        Builder = OutputFilenameBuilder()
        Result = Builder.GenerateOutputFileName('Show.S01E01.mkv', '1080p', '1080p')
        assert Result == 'Show.S01E01-mv.mp4.inprogress'

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C3
    def test_mv_suffix_collapses_when_source_ends_in_mv(self):
        """Input with `-mv` suffix collapses to single `-mv` in output."""
        Builder = OutputFilenameBuilder()
        Result = Builder.GenerateOutputFileName('Show-mv.mkv', '1080p', '1080p')
        assert Result == 'Show-mv.mp4.inprogress'

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C3
    def test_mv_suffix_collapses_greedily(self):
        """Multiple `-mv` suffixes collapse greedily to single `-mv`."""
        Builder = OutputFilenameBuilder()
        Result = Builder.GenerateOutputFileName('Show-mv-mv.mkv', '1080p', '1080p')
        assert Result == 'Show-mv.mp4.inprogress'

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C3
    def test_resolution_token_replaced_when_present_in_filename(self):
        """Source resolution token in filename replaced with target token."""
        Builder = OutputFilenameBuilder()
        Result = Builder.GenerateOutputFileName('Show-1080p.mkv', '1080p', '720p')
        assert Result == 'Show-720p-mv.mp4.inprogress'

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C3
    def test_resolution_token_appended_when_absent(self):
        """Source resolution token absent => target token appended to basename."""
        Builder = OutputFilenameBuilder()
        Result = Builder.GenerateOutputFileName('Show.mkv', '1080p', '720p')
        assert Result == 'Show720p-mv.mp4.inprogress'

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C3
    def test_extract_resolution_from_filename_finds_720p(self):
        """'Show-720p.mkv' => '720p'."""
        assert OutputFilenameBuilder().ExtractResolutionFromFilename('Show-720p.mkv') == '720p'

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C3
    def test_extract_resolution_returns_none_when_absent(self):
        """No resolution token => None."""
        assert OutputFilenameBuilder().ExtractResolutionFromFilename('Show.mkv') is None

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C3
    def test_format_resolution_for_filename_canonical(self):
        """Canonical resolution tokens passed through unchanged."""
        Builder = OutputFilenameBuilder()
        assert Builder.FormatResolutionForFilename('1080p') == '1080p'
        assert Builder.FormatResolutionForFilename('720p') == '720p'

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C3
    def test_format_resolution_for_filename_wxh_pattern(self):
        """'1920x1080' => '1080p' (height + 'p')."""
        assert OutputFilenameBuilder().FormatResolutionForFilename('1920x1080') == '1080p'

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C3
    def test_normalize_ffmpeg_path_strips_quotes_and_whitespace(self):
        """Quotes + leading/trailing whitespace removed by normalize."""
        Builder = OutputFilenameBuilder()
        assert Builder.NormalizeFfmpegPath('  "C:/foo.mp4"  ') == 'C:/foo.mp4'

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C3
    def test_collapse_mv_suffix_strips_all_trailing(self):
        """Greedy strip of trailing -mv segments."""
        Builder = OutputFilenameBuilder()
        assert Builder.CollapseMvSuffix('Show-mv-mv-mv') == 'Show'
        assert Builder.CollapseMvSuffix('Show') == 'Show'
