import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.AudioFilterEmitter import AudioFilterEmitter


FFMPEG = r'C:\Code\MediaVortex\FFmpegMaster\bin\ffmpeg.exe'
FFPROBE = r'C:\Code\MediaVortex\FFmpegMaster\bin\ffprobe.exe'


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.L2
def _ProbeStreamTags(Mp4Path):
    """Return list of stream-tag dicts via ffprobe -of json."""
    Result = subprocess.run(
        [FFPROBE, '-v', 'error',
         '-show_entries', 'stream=index:stream_tags',
         '-of', 'json', Mp4Path],
        capture_output=True, text=True, check=True,
    )
    return json.loads(Result.stdout)['streams']


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.L2
class TestMp4TitleResolution(unittest.TestCase):
    """L2: MP4 muxer silently drops -metadata:s:a:N title=. handler_name persists; assert that contract."""

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.L2
    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(FFMPEG) or not os.path.isfile(FFPROBE):
            raise unittest.SkipTest(f'ffmpeg/ffprobe not at {FFMPEG}')

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.L2
    def test_mp4_drops_title_but_keeps_handler_name(self):
        with tempfile.TemporaryDirectory() as Tmp:
            Out = str(Path(Tmp) / 'roundtrip.mp4')
            Cmd = [
                FFMPEG, '-y',
                '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1',
                '-f', 'lavfi', '-i', 'sine=frequency=880:duration=1',
                '-map', '0:a', '-map', '1:a',
                '-c:a:0', 'eac3', '-c:a:1', 'eac3',
                '-metadata:s:a:0', 'language=eng',
                '-metadata:s:a:1', 'language=jpn',
                '-metadata:s:a:0', 'title=Original',
                '-metadata:s:a:1', 'title=Dialog Boost',
                '-metadata:s:a:0', 'handler_name=Original (eng)',
                '-metadata:s:a:1', 'handler_name=Dialog Boost (jpn)',
                Out,
            ]
            subprocess.run(Cmd, capture_output=True, check=True)
            Streams = _ProbeStreamTags(Out)
        self.assertEqual(len(Streams), 2)
        for S in Streams:
            self.assertNotIn('title', S.get('tags', {}),
                             'MP4 contract: title silently dropped (L2 outcome (c) -- documented in feature.md)')
        self.assertEqual(Streams[0]['tags']['handler_name'], 'Original (eng)')
        self.assertEqual(Streams[1]['tags']['handler_name'], 'Dialog Boost (jpn)')

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.L2
    def test_emitter_emits_handler_name_per_output_track(self):
        Mf = {
            'Id': 1, 'SourceIntegratedLufs': -30.0, 'SourceLoudnessRangeLU': 9.0,
            'SourceTruePeakDbtp': -10.0, 'SourceIntegratedThresholdLufs': -40.0,
            'AudioCodec': 'aac', 'AudioCorruptSuspect': False,
        }
        Policy = {
            'Enabled': True, 'TargetIntegratedLufs': -23.0, 'TargetTruePeakDbtp': -2.0,
            'LoudnessTolerance': 4.0, 'UngainablePolicy': 'adaptive',
            'EmitTracks': [
                {'Label': 'Original', 'TargetLufs': -23.0, 'TargetLra': None,
                 'Channels': 'source', 'Codec': 'eac3', 'Bitrate': 384,
                 'SampleRateHz': 48000, 'BitDepth': 16,
                 'LanguageFilter': 'keep-all', 'IsDefaultTrack': False},
            ],
        }
        Streams = [{'index': 0, 'tags': {'language': 'eng'}, 'disposition': {}}]
        Blocks = AudioFilterEmitter().EmitTracks(Mf, Policy, AudioStreams=Streams)
        Md = ' '.join(Blocks[0].MetadataArgs)
        self.assertIn('handler_name=Original (eng)', Md)


if __name__ == '__main__':
    unittest.main()
