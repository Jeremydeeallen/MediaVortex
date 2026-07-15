import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.Services.DemucsDaemonProtocol import (
    DecodeRequest,
    DecodeResponse,
    EncodeRequest,
    EncodeResponse,
    IsolateRequest,
    IsolateResponse,
    READY_LINE,
)


class DemucsDaemonProtocolTest(unittest.TestCase):

    def test_request_roundtrip(self):
        Req = IsolateRequest(
            RequestId='abc-123',
            InputWavPath='/tmp/in.wav',
            OutputDir='/tmp/out',
            ModelName='htdemucs',
        )
        Encoded = EncodeRequest(Req)
        Decoded = DecodeRequest(Encoded)
        self.assertEqual(Decoded, Req)

    def test_response_success_roundtrip(self):
        Resp = IsolateResponse(
            RequestId='abc-123',
            Success=True,
            VocalsWavPath='/tmp/out/htdemucs/vocals.wav',
            InstrumentalWavPath='/tmp/out/htdemucs/no_vocals.wav',
        )
        Decoded = DecodeResponse(EncodeResponse(Resp))
        self.assertEqual(Decoded, Resp)

    def test_response_failure_roundtrip(self):
        Resp = IsolateResponse(
            RequestId='xyz-999',
            Success=False,
            ErrorMessage='RuntimeError: model missing',
        )
        Decoded = DecodeResponse(EncodeResponse(Resp))
        self.assertEqual(Decoded, Resp)
        self.assertIsNone(Decoded.VocalsWavPath)

    def test_ready_line_constant(self):
        self.assertEqual(READY_LINE, 'DEMUCS_DAEMON_READY')


if __name__ == '__main__':
    unittest.main()
