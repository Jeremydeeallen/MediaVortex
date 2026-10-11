import re
import wave

import numpy as np

from Core.Path.LocalPath import LocalJoin


CHUNK_SECONDS = 1200
OVERLAP_SECONDS = 10
MIN_TAIL_SECONDS = 60
CHUNKS_MARKER = 'MV_DEMUCS_CHUNKS'
CHUNKS_LINE_RE = re.compile(r"^MV_DEMUCS_CHUNKS (\d+) ([\d.]+)$")
TRACK_START_PREFIX = 'Separating track'


# directive: demucs-liveness | # see demucs-daemon.C12 -- (StartFrame, FrameCount) per piece; every piece but the last carries OVERLAP_SECONDS of the next; a remainder under MIN_TAIL_SECONDS is folded into the previous piece
def PlanChunks(TotalFrames, SampleRate):
    Step = CHUNK_SECONDS * SampleRate
    Overlap = OVERLAP_SECONDS * SampleRate
    MinTail = MIN_TAIL_SECONDS * SampleRate
    if TotalFrames <= Step + MinTail:
        return [(0, TotalFrames)]
    Starts = list(range(0, TotalFrames, Step))
    if TotalFrames - Starts[-1] < MinTail:
        Starts.pop()
    Plan = []
    for Index, Start in enumerate(Starts):
        IsLast = Index == len(Starts) - 1
        Plan.append((Start, TotalFrames - Start if IsLast else Step + Overlap))
    return Plan


# directive: demucs-liveness | # see demucs-daemon.C12 -- returns ([], seconds) when the input fits one piece so the caller separates it whole
def SplitWav(InputWavPath, ChunkDir):
    with wave.open(InputWavPath, 'rb') as Source:
        Params = Source.getparams()
        Plan = PlanChunks(Params.nframes, Params.framerate)
        TotalSeconds = Params.nframes / float(Params.framerate)
        if len(Plan) == 1:
            return [], TotalSeconds
        ChunkPaths = []
        for Index, (Start, Count) in enumerate(Plan):
            Source.setpos(Start)
            Frames = Source.readframes(Count)
            ChunkPath = LocalJoin(ChunkDir, f'c{Index:02d}.wav')
            with wave.open(ChunkPath, 'wb') as Out:
                Out.setnchannels(Params.nchannels)
                Out.setsampwidth(Params.sampwidth)
                Out.setframerate(Params.framerate)
                Out.writeframes(Frames)
            ChunkPaths.append(ChunkPath)
        return ChunkPaths, TotalSeconds


# directive: demucs-liveness | # see demucs-daemon.C12 -- streams pieces into one file; holds one piece in memory; each piece's last OVERLAP_SECONDS is crossfaded into the next piece's first
def JoinStem(ChunkStemPaths, OutputWavPath):
    Tail = None
    Out = None
    try:
        for Index, ChunkStemPath in enumerate(ChunkStemPaths):
            with wave.open(ChunkStemPath, 'rb') as Piece:
                if Piece.getsampwidth() != 2:
                    raise RuntimeError(f'JoinStem expects 16-bit PCM, got sampwidth={Piece.getsampwidth()} in {ChunkStemPath}')
                Channels = Piece.getnchannels()
                Rate = Piece.getframerate()
                Data = np.frombuffer(Piece.readframes(Piece.getnframes()), dtype='<i2').reshape(-1, Channels).astype(np.float32)
            Overlap = OVERLAP_SECONDS * Rate
            if len(Data) < Overlap:
                raise RuntimeError(f'JoinStem piece shorter than overlap: {len(Data)} frames < {Overlap} in {ChunkStemPath}')
            if Out is None:
                Out = wave.open(OutputWavPath, 'wb')
                Out.setnchannels(Channels)
                Out.setsampwidth(2)
                Out.setframerate(Rate)
            if Tail is not None:
                FadeIn = np.linspace(0.0, 1.0, Overlap, dtype=np.float32)[:, None]
                Data[:Overlap] = Tail * (1.0 - FadeIn) + Data[:Overlap] * FadeIn
            IsLast = Index == len(ChunkStemPaths) - 1
            Body = Data if IsLast else Data[:-Overlap]
            Tail = None if IsLast else Data[-Overlap:].copy()
            Out.writeframes(np.clip(np.rint(Body), -32768, 32767).astype('<i2').tobytes())
    finally:
        if Out is not None:
            Out.close()


# directive: demucs-liveness | # see demucs-daemon.S4 -- maps a tick inside piece ChunkIndex (1-based) to whole-input (percent, done_seconds, total_seconds)
def ScaleChunkProgress(ChunkIndex, ChunkTotal, TotalSeconds, Percent):
    Overall = ((max(ChunkIndex, 1) - 1) * 100.0 + Percent) / ChunkTotal
    Overall = min(Overall, 100.0)
    return int(Overall), Overall / 100.0 * TotalSeconds, TotalSeconds
