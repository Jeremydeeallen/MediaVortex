import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.AudioFilterEmitter import (
    AudioFilterEmitter,
    TrackBlock,
)


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C1
def _Mf(**Kwargs):
    """Build a MediaFile dict with gainable defaults (-30 LUFS source, ample headroom)."""
    Defaults = {
        'Id': 1,
        'SourceIntegratedLufs': -30.0,
        'SourceLoudnessRangeLU': 9.0,
        'SourceTruePeakDbtp': -10.0,
        'SourceIntegratedThresholdLufs': -40.0,
        'AudioCodec': 'eac3',
        'AudioCorruptSuspect': False,
    }
    Defaults.update(Kwargs)
    return Defaults


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C1
def _Policy(**Kwargs):
    """Build a Policy dict matching the seeded global default."""
    Defaults = {
        'Enabled': True,
        'TargetIntegratedLufs': -23.0,
        'TargetTruePeakDbtp': -2.0,
        'LoudnessTolerance': 4.0,
        'UngainablePolicy': 'adaptive',
        'KeepCommentaryTracks': True,
        'EnableSpeechLanguageDetection': False,
        'EmitTracks': [
            {
                'Label': 'Original', 'TargetLufs': -23.0, 'TargetLra': None,
                'Channels': 'source', 'Codec': 'eac3', 'Bitrate': 384,
                'SampleRateHz': 48000, 'BitDepth': 16,
                'LanguageFilter': 'keep-all', 'IsDefaultTrack': False,
            },
            {
                'Label': 'Dialog Boost', 'TargetLufs': -23.0, 'TargetLra': 11.0,
                'Channels': 'source', 'Codec': 'eac3', 'Bitrate': 384,
                'SampleRateHz': 48000, 'BitDepth': 16,
                'LanguageFilter': 'keep-all', 'IsDefaultTrack': True,
            },
        ],
    }
    Defaults.update(Kwargs)
    return Defaults


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C1
def _Stream(Index=0, Language='eng', Default=False, Commentary=False, Title=''):
    """Build an ffprobe-shaped audio stream dict."""
    return {
        'index': Index,
        'tags': {'language': Language, 'title': Title},
        'disposition': {'default': 1 if Default else 0, 'comment': 1 if Commentary else 0},
    }


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C1
class TestAudioFilterEmitter(unittest.TestCase):
    """C1/C2/C3/C4/C8/C14/C17/C20/C22/C23: emitter contract across the 9 fixtures."""

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C1
    def test_a_single_language_dual_track_gainable(self):
        Emitter = AudioFilterEmitter()
        Streams = [_Stream(Index=0, Language='eng')]
        Blocks = Emitter.EmitTracks(_Mf(), _Policy(), AudioStreams=Streams)
        self.assertEqual(len(Blocks), 2)
        self.assertEqual([B.Label for B in Blocks], ['Original', 'Dialog Boost'])
        self.assertTrue(any('loudnorm' in ' '.join(B.FilterArgs) for B in Blocks))

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C2
    def test_a_dialog_boost_is_default_track(self):
        Emitter = AudioFilterEmitter()
        Streams = [_Stream(Index=0, Language='eng')]
        Blocks = Emitter.EmitTracks(_Mf(), _Policy(), AudioStreams=Streams)
        Boost = [B for B in Blocks if B.Label == 'Dialog Boost'][0]
        Original = [B for B in Blocks if B.Label == 'Original'][0]
        self.assertIn('default', ' '.join(Boost.DispositionArgs))
        self.assertNotIn('default', ' '.join(Original.DispositionArgs))

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C4
    def test_b_multi_language_dual_track_each_language(self):
        Emitter = AudioFilterEmitter()
        Streams = [_Stream(Index=0, Language='eng'), _Stream(Index=1, Language='jpn')]
        Blocks = Emitter.EmitTracks(_Mf(), _Policy(), AudioStreams=Streams)
        self.assertEqual(len(Blocks), 4)
        Langs = [B.Language for B in Blocks]
        self.assertEqual(sorted(set(Langs)), ['eng', 'jpn'])

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C8
    def test_c_ungainable_skip_no_filter(self):
        Emitter = AudioFilterEmitter()
        Streams = [_Stream(Index=0, Language='eng')]
        Mf = _Mf(SourceIntegratedLufs=-30.0, SourceTruePeakDbtp=-3.0)
        Pol = _Policy(UngainablePolicy='skip')
        Blocks = Emitter.EmitTracks(Mf, Pol, AudioStreams=Streams)
        for B in Blocks:
            self.assertEqual(B.FilterArgs, [])
            self.assertIn('copy', ' '.join(B.CodecArgs))

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C5
    def test_d_ungainable_adaptive_lowers_target(self):
        Emitter = AudioFilterEmitter()
        Streams = [_Stream(Index=0, Language='eng')]
        Mf = _Mf(SourceIntegratedLufs=-28.0, SourceTruePeakDbtp=-3.0)
        Pol = _Policy(UngainablePolicy='adaptive')
        Blocks = Emitter.EmitTracks(Mf, Pol, AudioStreams=Streams)
        Original = [B for B in Blocks if B.Label == 'Original'][0]
        self.assertIn('loudnorm', ' '.join(Original.FilterArgs))

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C17
    def test_e_channels_downmix(self):
        Emitter = AudioFilterEmitter()
        Streams = [_Stream(Index=0, Language='eng')]
        Pol = _Policy(EmitTracks=[
            {'Label': 'Stereo', 'TargetLufs': -23.0, 'TargetLra': None,
             'Channels': 2, 'Codec': 'aac', 'Bitrate': 192,
             'SampleRateHz': 48000, 'BitDepth': 16,
             'LanguageFilter': 'keep-all', 'IsDefaultTrack': True},
        ])
        Blocks = Emitter.EmitTracks(_Mf(), Pol, AudioStreams=Streams)
        self.assertEqual(len(Blocks), 1)
        self.assertIn('-ac:0', Blocks[0].CodecArgs)
        Idx = Blocks[0].CodecArgs.index('-ac:0')
        self.assertEqual(Blocks[0].CodecArgs[Idx + 1], '2')

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C11
    def test_f_language_detection_fails_keeps_all_original_only(self):
        Emitter = AudioFilterEmitter()
        Streams = [_Stream(Index=0, Language=''), _Stream(Index=1, Language='')]
        Pol = _Policy(EmitTracks=[
            {'Label': 'Original', 'TargetLufs': -23.0, 'TargetLra': None,
             'Channels': 'source', 'Codec': 'eac3', 'Bitrate': 384,
             'SampleRateHz': 48000, 'BitDepth': 16,
             'LanguageFilter': 'keep-all', 'IsDefaultTrack': True},
        ])
        Blocks = Emitter.EmitTracks(_Mf(), Pol, AudioStreams=Streams)
        self.assertEqual(len(Blocks), 2)
        Langs = [B.Language for B in Blocks]
        self.assertTrue(all(L == 'und' for L in Langs))

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C22
    def test_g_mp4_compat_codec_with_original_only_streams_copy(self):
        Emitter = AudioFilterEmitter()
        Streams = [_Stream(Index=0, Language='eng')]
        Pol = _Policy(Enabled=False, EmitTracks=[
            {'Label': 'Original', 'TargetLufs': -23.0, 'TargetLra': None,
             'Channels': 'source', 'Codec': 'eac3', 'Bitrate': 384,
             'SampleRateHz': 48000, 'BitDepth': 16,
             'LanguageFilter': 'keep-all', 'IsDefaultTrack': True},
        ])
        Mf = _Mf(AudioCodec='aac')
        Blocks = Emitter.EmitTracks(Mf, Pol, AudioStreams=Streams)
        self.assertEqual(len(Blocks), 1)
        self.assertIn('copy', ' '.join(Blocks[0].CodecArgs))
        self.assertEqual(Blocks[0].FilterArgs, [])

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C20
    def test_h_source_dialnorm_preserved_on_original_stream_copy(self):
        Emitter = AudioFilterEmitter()
        Stream = _Stream(Index=0, Language='eng')
        Stream['tags']['DialNorm'] = '24'
        Pol = _Policy(Enabled=False, EmitTracks=[
            {'Label': 'Original', 'TargetLufs': -23.0, 'TargetLra': None,
             'Channels': 'source', 'Codec': 'eac3', 'Bitrate': 384,
             'SampleRateHz': 48000, 'BitDepth': 16,
             'LanguageFilter': 'keep-all', 'IsDefaultTrack': True},
        ])
        Mf = _Mf(AudioCodec='eac3')
        Blocks = Emitter.EmitTracks(Mf, Pol, AudioStreams=[Stream])
        self.assertEqual(len(Blocks), 1)
        Cd = ' '.join(Blocks[0].CodecArgs)
        self.assertIn('copy', Cd)
        self.assertNotIn('-dialnorm', Cd)

    # directive: audio-vertical-live-encode-gaps | # see audio-normalization.C20
    def test_h2_dialnorm_emitted_as_codec_option_on_reencode(self):
        Emitter = AudioFilterEmitter()
        Stream = _Stream(Index=0, Language='eng')
        Stream['tags']['DialNorm'] = '24'
        Pol = _Policy(EmitTracks=[
            {'Label': 'Original', 'TargetLufs': -23.0, 'TargetLra': None,
             'Channels': 'source', 'Codec': 'eac3', 'Bitrate': 384,
             'SampleRateHz': 48000, 'BitDepth': 16,
             'LanguageFilter': 'keep-all', 'IsDefaultTrack': True},
        ])
        Blocks = Emitter.EmitTracks(_Mf(), Pol, AudioStreams=[Stream])
        self.assertEqual(len(Blocks), 1)
        Cd = ' '.join(Blocks[0].CodecArgs)
        self.assertIn('-dialnorm:0', Cd)
        Md = ' '.join(Blocks[0].MetadataArgs)
        self.assertNotIn('dialnorm', Md)

    # directive: audio-vertical-live-encode-gaps | # see audio-normalization.C11
    def test_und_falls_through_to_policy_language_default(self):
        Emitter = AudioFilterEmitter()
        Stream = _Stream(Index=0, Language='und')
        Pol = _Policy(EmitTracks=[
            {'Label': 'Original', 'TargetLufs': -23.0, 'TargetLra': None,
             'Channels': 'source', 'Codec': 'eac3', 'Bitrate': 384,
             'SampleRateHz': 48000, 'BitDepth': 16,
             'LanguageFilter': 'keep-all', 'IsDefaultTrack': True},
        ])
        Pol['LanguageDefault'] = 'eng'
        Blocks = Emitter.EmitTracks(_Mf(), Pol, AudioStreams=[Stream])
        self.assertEqual(len(Blocks), 1)
        Md = ' '.join(Blocks[0].MetadataArgs)
        self.assertIn('language=eng', Md)

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C23
    def test_i_commentary_filtered_when_keep_commentary_false(self):
        Emitter = AudioFilterEmitter()
        Streams = [
            _Stream(Index=0, Language='eng'),
            _Stream(Index=1, Language='eng', Commentary=True, Title='Director Commentary'),
        ]
        Pol = _Policy(KeepCommentaryTracks=False, EmitTracks=[
            {'Label': 'Original', 'TargetLufs': -23.0, 'TargetLra': None,
             'Channels': 'source', 'Codec': 'eac3', 'Bitrate': 384,
             'SampleRateHz': 48000, 'BitDepth': 16,
             'LanguageFilter': 'keep-all', 'IsDefaultTrack': True},
        ])
        Blocks = Emitter.EmitTracks(_Mf(), Pol, AudioStreams=Streams)
        self.assertEqual(len(Blocks), 1)

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C14
    def test_returns_empty_when_no_emit_tracks(self):
        Emitter = AudioFilterEmitter()
        Pol = _Policy(EmitTracks=[])
        Blocks = Emitter.EmitTracks(_Mf(), Pol, AudioStreams=[_Stream()])
        self.assertEqual(Blocks, [])

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C5
    def test_review_strategy_skips_track_emission(self):
        Emitter = AudioFilterEmitter()
        Streams = [_Stream(Index=0, Language='eng')]
        Mf = _Mf(SourceIntegratedLufs=None)
        Blocks = Emitter.EmitTracks(Mf, _Policy(), AudioStreams=Streams)
        self.assertEqual(Blocks, [])


if __name__ == '__main__':
    unittest.main()
