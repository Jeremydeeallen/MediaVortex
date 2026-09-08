# directive: bug-0090-subtitle-codec-filter | # see command-composer.C4
import unittest

from Features.TranscodeJob.Emit.Slots.SubtitleSlot import SubtitleSlot


# directive: bug-0090-subtitle-codec-filter | # see command-composer.C4
class TestSubtitleSlotCodecFilter(unittest.TestCase):
    """BUG-0090: SubtitleSlot must whitelist decodable text codecs for mp4; drop image, unknown, none, null, and any other undecodable subtitle formats before -c:s mov_text binding."""

    def setUp(self):
        self.Slot = SubtitleSlot()

    def test_a_subrip_plus_unknown_keeps_only_subrip(self):
        Argv = self.Slot.Emit('mp4', SubtitleStreams=[(4, 'subrip'), (5, 'unknown')])
        self.assertIn('-map', Argv)
        self.assertIn('0:4?', Argv)
        self.assertNotIn('0:5?', Argv)
        self.assertIn('mov_text', Argv)

    def test_b_all_unknown_drops_all(self):
        Argv = self.Slot.Emit('mp4', SubtitleStreams=[(4, 'unknown'), (5, 'unknown'), (6, 'unknown')])
        self.assertEqual(Argv, [])

    def test_c_subrip_plus_pgs_keeps_only_subrip(self):
        Argv = self.Slot.Emit('mp4', SubtitleStreams=[(4, 'subrip'), (5, 'hdmv_pgs_subtitle')])
        self.assertIn('0:4?', Argv)
        self.assertNotIn('0:5?', Argv)
        self.assertIn('mov_text', Argv)

    def test_d_all_text_uses_permissive_shortcut_when_no_streams(self):
        Argv = self.Slot.Emit('mp4', SubtitleFormats='subrip,ass', SubtitleStreams=None)
        self.assertEqual(Argv, ['-map', '0:s?', '-c:s', 'mov_text'])

    def test_e_mkv_target_unchanged_with_unknown(self):
        Argv = self.Slot.Emit('mkv', SubtitleStreams=[(4, 'unknown'), (5, 'hdmv_pgs_subtitle')])
        self.assertEqual(Argv, ['-map', '0:s?', '-c:s', 'copy'])

    def test_null_codec_treated_as_undecodable(self):
        Argv = self.Slot.Emit('mp4', SubtitleStreams=[(4, 'subrip'), (5, 'null'), (6, '')])
        self.assertIn('0:4?', Argv)
        self.assertNotIn('0:5?', Argv)
        self.assertNotIn('0:6?', Argv)

    def test_unrecognized_codec_dropped(self):
        Argv = self.Slot.Emit('mp4', SubtitleStreams=[(4, 'subrip'), (5, 'some_proprietary_codec')])
        self.assertIn('0:4?', Argv)
        self.assertNotIn('0:5?', Argv)

    def test_all_text_streams_all_mapped(self):
        Argv = self.Slot.Emit('mp4', SubtitleStreams=[(4, 'subrip'), (5, 'ass'), (6, 'mov_text')])
        self.assertIn('0:4?', Argv)
        self.assertIn('0:5?', Argv)
        self.assertIn('0:6?', Argv)
        self.assertIn('mov_text', Argv)


if __name__ == '__main__':
    unittest.main()
