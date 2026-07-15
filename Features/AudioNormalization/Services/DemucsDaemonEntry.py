import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

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


def _IsolateOnce(Req, Device):
    from demucs.separate import main as _DemucsMain
    Args = [
        '-n', Req.ModelName,
        '-d', Device,
        '--two-stems', 'vocals',
        '-o', Req.OutputDir,
        '--filename', '{stem}.{ext}',
        Req.InputWavPath,
    ]
    OrigArgv = sys.argv
    sys.argv = ['demucs.separate'] + Args
    try:
        _DemucsMain()
    finally:
        sys.argv = OrigArgv
    Sub = os.path.join(Req.OutputDir, Req.ModelName)
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
        except Exception as Ex:
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
