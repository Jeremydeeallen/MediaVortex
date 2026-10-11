import os
import tempfile
import unittest
import wave

import numpy as np

from Features.AudioNormalization.Services import DemucsChunking
from Features.AudioNormalization.Services.DemucsChunking import (
    CHUNK_SECONDS,
    CHUNKS_LINE_RE,
    CHUNKS_MARKER,
    MIN_TAIL_SECONDS,
    OVERLAP_SECONDS,
    JoinStem,
    PlanChunks,
    ScaleChunkProgress,
    SplitWav,
)

RATE = 8000


# directive: demucs-liveness | # see demucs-daemon.C12
def _WriteWav(WavPath, Samples):
    with wave.open(WavPath, 'wb') as Out:
        Out.setnchannels(Samples.shape[1])
        Out.setsampwidth(2)
        Out.setframerate(RATE)
        Out.writeframes(Samples.astype('<i2').tobytes())


# directive: demucs-liveness | # see demucs-daemon.C12
def _ReadWav(WavPath):
    with wave.open(WavPath, 'rb') as In:
        return np.frombuffer(In.readframes(In.getnframes()), dtype='<i2').reshape(-1, In.getnchannels())


# directive: demucs-liveness | # see demucs-daemon.C12
class TestDemucsChunking(unittest.TestCase):

    # directive: demucs-liveness | # see demucs-daemon.C12
    def test_short_input_is_one_piece(self):
        Total = (CHUNK_SECONDS + MIN_TAIL_SECONDS) * RATE
        self.assertEqual(PlanChunks(Total, RATE), [(0, Total)])

    # directive: demucs-liveness | # see demucs-daemon.C12
    def test_long_input_pieces_overlap_and_cover_everything(self):
        Total = int(84.3 * 60) * RATE
        Plan = PlanChunks(Total, RATE)
        self.assertEqual(len(Plan), 5)
        Step = CHUNK_SECONDS * RATE
        Overlap = OVERLAP_SECONDS * RATE
        for Index, (Start, Count) in enumerate(Plan[:-1]):
            self.assertEqual(Start, Index * Step)
            self.assertEqual(Count, Step + Overlap)
        LastStart, LastCount = Plan[-1]
        self.assertEqual(LastStart + LastCount, Total)

    # directive: demucs-liveness | # see demucs-daemon.C12
    def test_small_remainder_folds_into_previous_piece(self):
        Total = (2 * CHUNK_SECONDS + MIN_TAIL_SECONDS - 1) * RATE
        Plan = PlanChunks(Total, RATE)
        self.assertEqual(len(Plan), 2)
        self.assertEqual(Plan[-1][0] + Plan[-1][1], Total)

    # directive: demucs-liveness | # see demucs-daemon.C12
    def test_split_then_join_returns_the_source_signal(self):
        Frames = int(2.5 * CHUNK_SECONDS) * RATE
        Rng = np.random.default_rng(7)
        Source = Rng.integers(-20000, 20000, size=(Frames, 2), dtype=np.int16)
        with tempfile.TemporaryDirectory() as Dir:
            SourcePath = os.path.join(Dir, 'source.wav')
            _WriteWav(SourcePath, Source)
            ChunkPaths, TotalSeconds = SplitWav(SourcePath, Dir)
            self.assertEqual(len(ChunkPaths), 3)
            self.assertAlmostEqual(TotalSeconds, Frames / RATE)
            JoinedPath = os.path.join(Dir, 'joined.wav')
            JoinStem(ChunkPaths, JoinedPath)
            Joined = _ReadWav(JoinedPath)
        self.assertEqual(Joined.shape, Source.shape)
        self.assertLessEqual(int(np.max(np.abs(Joined.astype(np.int32) - Source.astype(np.int32)))), 1)

    # directive: demucs-liveness | # see demucs-daemon.C12
    def test_short_input_is_not_split(self):
        Source = np.zeros((60 * RATE, 2), dtype=np.int16)
        with tempfile.TemporaryDirectory() as Dir:
            SourcePath = os.path.join(Dir, 'source.wav')
            _WriteWav(SourcePath, Source)
            ChunkPaths, _ = SplitWav(SourcePath, Dir)
            self.assertEqual(ChunkPaths, [])
            self.assertEqual(os.listdir(Dir), ['source.wav'])

    # directive: demucs-liveness | # see demucs-daemon.C12
    def test_join_refuses_non_16_bit_input(self):
        with tempfile.TemporaryDirectory() as Dir:
            Bad = os.path.join(Dir, 'bad.wav')
            with wave.open(Bad, 'wb') as Out:
                Out.setnchannels(2)
                Out.setsampwidth(3)
                Out.setframerate(RATE)
                Out.writeframes(b'\x00' * 6 * RATE * 20)
            with self.assertRaises(RuntimeError):
                JoinStem([Bad, Bad], os.path.join(Dir, 'out.wav'))

    # directive: demucs-liveness | # see demucs-daemon.S4
    def test_marker_line_round_trips(self):
        Match = CHUNKS_LINE_RE.match(f'{CHUNKS_MARKER} 5 5058.0')
        self.assertEqual((int(Match.group(1)), float(Match.group(2))), (5, 5058.0))

    # directive: demucs-liveness | # see demucs-daemon.S4
    def test_progress_scales_across_pieces(self):
        self.assertEqual(ScaleChunkProgress(1, 4, 4000.0, 0), (0, 0.0, 4000.0))
        self.assertEqual(ScaleChunkProgress(3, 4, 4000.0, 50), (62, 2500.0, 4000.0))
        self.assertEqual(ScaleChunkProgress(4, 4, 4000.0, 100), (100, 4000.0, 4000.0))
        self.assertEqual(ScaleChunkProgress(0, 4, 4000.0, 40)[0], 10)

    # directive: demucs-liveness | # see demucs-daemon.C12
    def test_module_constants_match_the_contract(self):
        self.assertEqual((DemucsChunking.CHUNK_SECONDS, DemucsChunking.OVERLAP_SECONDS, DemucsChunking.MIN_TAIL_SECONDS), (1200, 10, 60))


if __name__ == '__main__':
    unittest.main()
