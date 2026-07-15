import json
from dataclasses import dataclass
from typing import Optional


READY_LINE = "DEMUCS_DAEMON_READY"
END_MARKER = "DEMUCS_RESPONSE_END"


@dataclass(frozen=True)
class IsolateRequest:
    RequestId: str
    InputWavPath: str
    OutputDir: str
    ModelName: str


@dataclass(frozen=True)
class IsolateResponse:
    RequestId: str
    Success: bool
    VocalsWavPath: Optional[str] = None
    InstrumentalWavPath: Optional[str] = None
    ErrorMessage: Optional[str] = None


def EncodeRequest(Req: IsolateRequest) -> str:
    return json.dumps({
        'RequestId': Req.RequestId,
        'InputWavPath': Req.InputWavPath,
        'OutputDir': Req.OutputDir,
        'ModelName': Req.ModelName,
    })


def DecodeRequest(Line: str) -> IsolateRequest:
    D = json.loads(Line)
    return IsolateRequest(
        RequestId=D['RequestId'],
        InputWavPath=D['InputWavPath'],
        OutputDir=D['OutputDir'],
        ModelName=D['ModelName'],
    )


def EncodeResponse(Resp: IsolateResponse) -> str:
    return json.dumps({
        'RequestId': Resp.RequestId,
        'Success': Resp.Success,
        'VocalsWavPath': Resp.VocalsWavPath,
        'InstrumentalWavPath': Resp.InstrumentalWavPath,
        'ErrorMessage': Resp.ErrorMessage,
    })


def DecodeResponse(Line: str) -> IsolateResponse:
    D = json.loads(Line)
    return IsolateResponse(
        RequestId=D['RequestId'],
        Success=D['Success'],
        VocalsWavPath=D.get('VocalsWavPath'),
        InstrumentalWavPath=D.get('InstrumentalWavPath'),
        ErrorMessage=D.get('ErrorMessage'),
    )
