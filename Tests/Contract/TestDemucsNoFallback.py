import os
import sys
import types
import unittest

from Features.AudioNormalization.Services import DemucsDaemonEntry
from Features.AudioNormalization.Services.DemucsDaemonClient import (
    DemucsDaemonClient,
    DemucsDaemonUnavailableError,
)
from Features.AudioNormalization.Services.DemucsDaemonProtocol import DEVICE_ERROR_MARKER
from Features.AudioNormalization.Services.DemucsVocalIsolationService import (
    SILENCE_FLOOR_DBFS,
    DeviceForCapabilities,
    ParseAstatsRmsDbfs,
    ParseLoudnormMeasurement,
)

SERVICES_DIR = os.path.dirname(os.path.abspath(DemucsDaemonEntry.__file__))
LOUDNORM_BLOCK = '{\n"input_i" : "-23.5",\n"input_tp" : "-4.1",\n"input_lra" : "7.2",\n"input_thresh" : "-33.9"\n}'


# directive: demucs-liveness | # see demucs-daemon.C5
def _FakeTorch(Cuda, Xpu):
    Torch = types.ModuleType('torch')
    Torch.__version__ = 'fake'
    Torch.cuda = types.SimpleNamespace(is_available=lambda: Cuda)
    Torch.xpu = types.SimpleNamespace(is_available=lambda: Xpu)
    return Torch


# directive: demucs-liveness | # see demucs-daemon.C5
class TestDemucsDeviceIsRequired(unittest.TestCase):

    # directive: demucs-liveness | # see demucs-daemon.C5
    def _Require(self, Device, Cuda, Xpu):
        Saved = sys.modules.get('torch')
        sys.modules['torch'] = _FakeTorch(Cuda, Xpu)
        try:
            return DemucsDaemonEntry._RequireDevice(['entry', '--device', Device])
        finally:
            if Saved is None:
                del sys.modules['torch']
            else:
                sys.modules['torch'] = Saved

    # directive: demucs-liveness | # see demucs-daemon.C5
    def test_hardware_flags_decide_the_device(self):
        self.assertEqual(DeviceForCapabilities(True, False), 'cuda')
        self.assertEqual(DeviceForCapabilities(True, True), 'cuda')
        self.assertEqual(DeviceForCapabilities(False, True), 'xpu')
        self.assertEqual(DeviceForCapabilities(False, False), 'cpu')

    # directive: demucs-liveness | # see demucs-daemon.C5
    def test_usable_required_device_is_accepted(self):
        self.assertEqual(self._Require('cuda', True, False), 'cuda')
        self.assertEqual(self._Require('xpu', False, True), 'xpu')
        self.assertEqual(self._Require('cpu', False, False), 'cpu')

    # directive: demucs-liveness | # see demucs-daemon.C5
    def test_unusable_gpu_exits_instead_of_using_cpu(self):
        for Device in ('cuda', 'xpu'):
            with self.assertRaises(SystemExit) as Raised:
                self._Require(Device, False, False)
            self.assertIn(DEVICE_ERROR_MARKER, str(Raised.exception))
            self.assertIn(Device, str(Raised.exception))

    # directive: demucs-liveness | # see demucs-daemon.C5
    def test_gpu_present_does_not_satisfy_a_different_required_gpu(self):
        with self.assertRaises(SystemExit):
            self._Require('xpu', True, False)

    # directive: demucs-liveness | # see demucs-daemon.C5
    def test_missing_or_unknown_device_argument_exits(self):
        for Argv in (['entry'], ['entry', '--device'], ['entry', '--device', 'auto']):
            with self.assertRaises(SystemExit) as Raised:
                DemucsDaemonEntry._RequireDevice(Argv)
            self.assertIn(DEVICE_ERROR_MARKER, str(Raised.exception))

    # directive: demucs-liveness | # see demucs-daemon.C5
    def test_client_start_raises_with_the_daemons_reason(self):
        Client = DemucsDaemonClient('auto', StartTimeoutSec=30)
        with self.assertRaises(DemucsDaemonUnavailableError) as Raised:
            Client.Start()
        self.assertIn(DEVICE_ERROR_MARKER, str(Raised.exception))
        self.assertIn("'auto'", str(Raised.exception))

    # directive: demucs-liveness | # see demucs-daemon.C5
    def test_no_device_detection_left_in_the_daemon(self):
        with open(os.path.join(SERVICES_DIR, 'DemucsDaemonEntry.py'), encoding='utf-8') as F:
            Source = F.read()
        for Banned in ('_DetectDevice', "return 'cpu'", '_PreWarmXpu', 'intel_extension_for_pytorch'):
            self.assertNotIn(Banned, Source)


# directive: demucs-liveness | # see demucs-daemon.C13
class TestMeasurementsFailInsteadOfDefaulting(unittest.TestCase):

    # directive: demucs-liveness | # see demucs-daemon.C13
    def test_loudnorm_block_is_parsed(self):
        Text = 'frame=...\n[Parsed_loudnorm_0 @ 0x1] \n' + LOUDNORM_BLOCK + '\n'
        self.assertEqual(ParseLoudnormMeasurement(Text, 'x'), (-23.5, 7.2, -4.1, -33.9))

    # directive: demucs-liveness | # see demucs-daemon.C13
    def test_loudnorm_without_block_raises(self):
        with self.assertRaises(RuntimeError) as Raised:
            ParseLoudnormMeasurement('Conversion failed!', 'Premix loudness of p.wav')
        self.assertIn('Premix loudness of p.wav', str(Raised.exception))
        self.assertIn('Conversion failed!', str(Raised.exception))

    # directive: demucs-liveness | # see demucs-daemon.C13
    def test_loudnorm_block_missing_a_field_raises(self):
        with self.assertRaises(RuntimeError):
            ParseLoudnormMeasurement('{"input_i" : "-23.5", "input_tp" : "-4.1"}', 'x')

    # directive: demucs-liveness | # see demucs-daemon.C13
    def test_astats_level_is_parsed_and_last_value_wins(self):
        Text = '[Parsed_astats_0] RMS level dB: -30.1\n[Parsed_astats_0] RMS level dB: -24.7\n'
        self.assertEqual(ParseAstatsRmsDbfs(Text, 'x'), -24.7)

    # directive: demucs-liveness | # see demucs-daemon.C13
    def test_astats_true_silence_is_a_value(self):
        self.assertEqual(ParseAstatsRmsDbfs('RMS level dB: -inf\n', 'x'), SILENCE_FLOOR_DBFS)

    # directive: demucs-liveness | # see demucs-daemon.C13
    def test_astats_without_a_level_raises_instead_of_reporting_silence(self):
        with self.assertRaises(RuntimeError) as Raised:
            ParseAstatsRmsDbfs('Error opening input file', 'Vocals level of v.wav')
        self.assertIn('Vocals level of v.wav', str(Raised.exception))

    # directive: demucs-liveness | # see demucs-daemon.C13
    def test_astats_unreadable_value_raises(self):
        with self.assertRaises(ValueError):
            ParseAstatsRmsDbfs('RMS level dB: garbage\n', 'x')

    # directive: demucs-liveness | # see demucs-daemon.C13
    def test_no_default_returns_left_in_the_service(self):
        with open(os.path.join(SERVICES_DIR, 'DemucsVocalIsolationService.py'), encoding='utf-8') as F:
            Source = F.read()
        for Banned in ('None, None, None, None', 'falling back', 'return SILENCE_FLOOR_DBFS'):
            self.assertNotIn(Banned, Source)


if __name__ == '__main__':
    unittest.main()
