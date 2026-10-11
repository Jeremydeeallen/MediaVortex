import json
import os
import shutil
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from Core.Path.LocalPath import LocalJoin
from Features.AudioNormalization.Services.DemucsChunking import CHUNKS_MARKER, JoinStem, SplitWav

from Features.AudioNormalization.Services.DemucsDaemonProtocol import (
    DecodeRequest,
    EncodeResponse,
    IsolateResponse,
    READY_LINE,
)


def _DetectDevice():
    try:
        import torch
        if torch.cuda.is_available():
            return 'cuda'
        if hasattr(torch, 'xpu') and torch.xpu.is_available():
            return 'xpu'
    except ImportError:
        pass
    return 'cpu'


def _PreWarmXpu(Device):
    if Device != 'xpu':
        return
    try:
        import intel_extension_for_pytorch
    except ImportError:
        pass


# directive: transcode-flow-canonical -- demucs.separate.main + torch print() to stdout; those bytes MUST NOT reach our protocol stdout or clients read them as garbage responses
def _RunDemucs(Args):
    from demucs.separate import main as _DemucsMain
    OrigArgv = sys.argv
    OrigStdout = sys.stdout
    sys.argv = ['demucs.separate'] + Args
    sys.stdout = sys.stderr
    try:
        _DemucsMain()
    finally:
        sys.stdout = OrigStdout
        sys.argv = OrigArgv


# directive: demucs-liveness | # see demucs-daemon.C12 -- separates every piece in one demucs call, joins each stem into the paths the caller reads, then drops the piece directory
def _IsolateChunked(Req, Device, ChunkPaths, ChunkDir, TotalSeconds, Sub):
    sys.stderr.write(f'{CHUNKS_MARKER} {len(ChunkPaths)} {TotalSeconds:.1f}\n')
    sys.stderr.flush()
    _RunDemucs([
        '-n', Req.ModelName,
        '-d', Device,
        '--two-stems', 'vocals',
        '-o', ChunkDir,
        '--filename', '{track}/{stem}.{ext}',
    ] + ChunkPaths)
    os.makedirs(Sub, exist_ok=True)
    PieceNames = [f'c{Index:02d}' for Index in range(len(ChunkPaths))]
    for Stem in ('vocals', 'no_vocals'):
        JoinStem(
            [LocalJoin(ChunkDir, Req.ModelName, Name, f'{Stem}.wav') for Name in PieceNames],
            LocalJoin(Sub, f'{Stem}.wav'),
        )
    shutil.rmtree(ChunkDir)


# directive: demucs-liveness | # see demucs-daemon.C12 -- an input that fits one piece is separated whole; a longer one goes through _IsolateChunked
def _IsolateOnce(Req, Device):
    Sub = os.path.join(Req.OutputDir, Req.ModelName)
    ChunkDir = LocalJoin(Req.OutputDir, 'demucs_chunks')
    os.makedirs(ChunkDir, exist_ok=True)
    ChunkPaths, TotalSeconds = SplitWav(Req.InputWavPath, ChunkDir)
    if ChunkPaths:
        _IsolateChunked(Req, Device, ChunkPaths, ChunkDir, TotalSeconds, Sub)
    else:
        shutil.rmtree(ChunkDir)
        _RunDemucs([
            '-n', Req.ModelName,
            '-d', Device,
            '--two-stems', 'vocals',
            '-o', Req.OutputDir,
            '--filename', '{stem}.{ext}',
            Req.InputWavPath,
        ])
    Vocals = os.path.join(Sub, 'vocals.wav')
    Instrumental = os.path.join(Sub, 'no_vocals.wav')
    if not os.path.exists(Vocals) or not os.path.exists(Instrumental):
        raise RuntimeError(
            f"demucs output missing: vocals_exists={os.path.exists(Vocals)} "
            f"instrumental_exists={os.path.exists(Instrumental)} dir={Sub}"
        )
    return Vocals, Instrumental


def Main():
    Device = _DetectDevice()
    _PreWarmXpu(Device)
    sys.stdout.write(READY_LINE + '\n')
    sys.stdout.flush()
    for Line in sys.stdin:
        Line = Line.strip()
        if not Line:
            continue
        RequestId = None
        try:
            Req = DecodeRequest(Line)
            RequestId = Req.RequestId
            Vocals, Instrumental = _IsolateOnce(Req, Device)
            Resp = IsolateResponse(
                RequestId=RequestId,
                Success=True,
                VocalsWavPath=Vocals,
                InstrumentalWavPath=Instrumental,
            )
        # directive: transcode-flow-canonical -- demucs.separate.main calls sys.exit on fatal(); catch SystemExit so daemon survives one bad request
        except (Exception, SystemExit) as Ex:
            Resp = IsolateResponse(
                RequestId=RequestId or 'unknown',
                Success=False,
                ErrorMessage=f'{type(Ex).__name__}: {Ex} :: {traceback.format_exc()[-1000:]}',
            )
        sys.stdout.write(EncodeResponse(Resp) + '\n')
        sys.stdout.flush()
    return 0


if __name__ == '__main__':
    sys.exit(Main())
