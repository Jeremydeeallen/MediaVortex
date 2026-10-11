import json
import os
import platform
import shutil
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from Core.Path.LocalPath import LocalJoin
from Features.AudioNormalization.Services.DemucsChunking import CHUNKS_MARKER, JoinStem, SplitWav

from Features.AudioNormalization.Services.DemucsDaemonProtocol import (
    DEVICE_ERROR_MARKER,
    DecodeRequest,
    EncodeResponse,
    IsolateResponse,
    READY_LINE,
)


# directive: demucs-liveness | # see demucs-daemon.C5 -- the caller names the device; the daemon proves torch can use it or exits before READY
def _RequireDevice(Argv):
    if len(Argv) != 3 or Argv[1] != '--device' or Argv[2] not in ('cuda', 'xpu', 'cpu'):
        raise SystemExit(f'{DEVICE_ERROR_MARKER} daemon must be started with --device cuda|xpu|cpu; got {Argv[1:]!r}')
    Required = Argv[2]
    import torch
    Available = {
        'cuda': torch.cuda.is_available,
        'xpu': lambda: hasattr(torch, 'xpu') and torch.xpu.is_available(),
        'cpu': lambda: True,
    }[Required]()
    if not Available:
        raise SystemExit(
            f"{DEVICE_ERROR_MARKER} required device '{Required}' is not usable by torch {torch.__version__} on {platform.node()}; refusing to separate on any other device")
    return Required


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


# directive: demucs-liveness | # see demucs-daemon.C5
def Main():
    Device = _RequireDevice(sys.argv)
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
