import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

import pytest

from Features.TranscodeJob.Emit.Slots.SubtitleSlot import SubtitleSlot


# directive: transcode-flow-canonical | # see transcode.ST5
class TestSubtitleSlot:

    # directive: transcode-flow-canonical | # see transcode.ST5
    def test_no_subs_emits_optional_map_mov_text_for_mp4(self):
        Args = SubtitleSlot().Emit('mp4', None)
        assert Args == ['-map', '0:s?', '-c:s', 'mov_text']

    # directive: transcode-flow-canonical | # see transcode.ST5
    def test_empty_subtitle_formats_emits_optional_map_mov_text(self):
        Args = SubtitleSlot().Emit('mp4', '')
        assert Args == ['-map', '0:s?', '-c:s', 'mov_text']

    # directive: transcode-flow-canonical | # see transcode.ST5
    def test_text_srt_subs_emit_optional_map_mov_text(self):
        Args = SubtitleSlot().Emit('mp4', 'subrip')
        assert Args == ['-map', '0:s?', '-c:s', 'mov_text']

    # directive: transcode-flow-canonical | # see transcode.ST5
    def test_ass_subs_emit_optional_map_mov_text(self):
        Args = SubtitleSlot().Emit('mp4', 'ass')
        assert Args == ['-map', '0:s?', '-c:s', 'mov_text']

    # directive: transcode-flow-canonical | # see transcode.ST5
    def test_multiple_text_langs_emit_optional_map_mov_text(self):
        Args = SubtitleSlot().Emit('mp4', 'subrip,ass')
        assert Args == ['-map', '0:s?', '-c:s', 'mov_text']

    # directive: transcode-flow-canonical | # see transcode.ST5
    def test_pgs_only_drops_with_warn(self):
        Args = SubtitleSlot().Emit('mp4', 'hdmv_pgs_subtitle')
        assert Args == []

    # directive: transcode-flow-canonical | # see transcode.ST5
    def test_dvd_only_drops_with_warn(self):
        Args = SubtitleSlot().Emit('mp4', 'dvd_subtitle')
        assert Args == []

    # directive: transcode-flow-canonical | # see transcode.ST5
    def test_pgs_mixed_with_text_still_emits_optional_map_mov_text(self):
        Args = SubtitleSlot().Emit('mp4', 'hdmv_pgs_subtitle,subrip')
        assert Args == ['-map', '0:s?', '-c:s', 'mov_text']

    # directive: transcode-flow-canonical | # see transcode.ST5
    def test_mkv_target_emits_copy(self):
        Args = SubtitleSlot().Emit('mkv', 'subrip')
        assert Args == ['-map', '0:s?', '-c:s', 'copy']

    # directive: transcode-flow-canonical | # see transcode.ST5
    def test_mkv_target_with_pgs_still_copies(self):
        Args = SubtitleSlot().Emit('mkv', 'hdmv_pgs_subtitle')
        assert Args == ['-map', '0:s?', '-c:s', 'copy']

    # directive: transcode-flow-canonical | # see transcode.ST5
    def test_none_container_defaults_to_mp4_behavior(self):
        Args = SubtitleSlot().Emit(None, 'subrip')
        assert Args == ['-map', '0:s?', '-c:s', 'mov_text']

    # directive: transcode-flow-canonical | # see transcode.ST5
    def test_case_insensitive_container(self):
        Args = SubtitleSlot().Emit('MP4', 'subrip')
        assert Args == ['-map', '0:s?', '-c:s', 'mov_text']

    # directive: transcode-flow-canonical | # see transcode.ST5
    def test_case_insensitive_codec(self):
        Args = SubtitleSlot().Emit('mp4', 'HDMV_PGS_SUBTITLE')
        assert Args == []


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
