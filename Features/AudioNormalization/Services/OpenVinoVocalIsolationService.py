# directive: audio-dialog-boost-real | # see audio-normalization.C14
import os
import subprocess
import sys

from Core.Logging.LoggingService import LoggingService
from Core.Path.LocalPath import LocalBasename, LocalExists, LocalJoin, LocalSplitExt
from Features.AudioNormalization.Services.DemucsVocalIsolationService import DemucsIsolationResult, SILENCE_FLOOR_DBFS


DEFAULT_ONNX_MODEL = "UVR-MDX-NET-Voc_FT.onnx"


# directive: audio-dialog-boost-real | # see audio-normalization.C14
class OpenVinoVocalIsolationService:

    # directive: audio-dialog-boost-real | # see audio-normalization.C14
    def __init__(self, FfmpegPath, ModelFilename=DEFAULT_ONNX_MODEL, DeviceType="GPU", ModelFileDir=None):
        self.FfmpegPath = FfmpegPath
        self.ModelFilename = ModelFilename
        self.DeviceType = DeviceType
        self.ModelFileDir = ModelFileDir or "/tmp/audio-separator-models"

    # directive: audio-dialog-boost-real | # see audio-normalization.C14
    def _BuildRunnerScript(self, StereoInputWavPath, OutputDir):
        return (
            "import torch\n"
            "from audio_separator.separator import Separator\n"
            "class OvSep(Separator):\n"
            "    def setup_torch_device(self, system_info):\n"
            "        self.torch_device_cpu = torch.device('cpu')\n"
            "        self.torch_device = self.torch_device_cpu\n"
            f"        self.onnx_execution_provider = [('OpenVINOExecutionProvider', {{'device_type': {self.DeviceType!r}}})]\n"
            "        self.logger.info('OpenVINO GPU execution provider forced')\n"
            f"sep = OvSep(output_dir={OutputDir!r}, output_format='WAV', model_file_dir={self.ModelFileDir!r}, log_level=30)\n"
            f"sep.load_model(model_filename={self.ModelFilename!r})\n"
            f"outs = sep.separate({StereoInputWavPath!r})\n"
            "print('SEPARATED:', outs)\n"
        )

    # directive: audio-dialog-boost-real | # see audio-normalization.C14
    def IsolateVocals(self, StereoInputWavPath, OutputDir):
        os.makedirs(OutputDir, exist_ok=True)
        LoggingService.LogInfo(
            f"OpenVINO separating {StereoInputWavPath} -> {OutputDir} (device={self.DeviceType})",
            "OpenVinoVocalIsolationService", "IsolateVocals",
        )
        Script = self._BuildRunnerScript(StereoInputWavPath, OutputDir)
        Result = subprocess.run(
            [sys.executable, "-c", Script],
            capture_output=True, text=True, timeout=3600,
        )
        if Result.returncode != 0:
            raise RuntimeError(
                f"openvino audio-separator failed (exit {Result.returncode}): {Result.stderr[-500:]}"
            )
        Base, _ = LocalSplitExt(LocalBasename(StereoInputWavPath))
        VocalsPath = self._FindStem(OutputDir, Base, "Vocals")
        InstrumentalPath = self._FindStem(OutputDir, Base, "Instrumental")
        if not VocalsPath or not InstrumentalPath:
            raise RuntimeError(f"openvino output missing (vocals={VocalsPath} instrumental={InstrumentalPath})")
        VocalsRms = self._MeasureWavRmsDbfs(VocalsPath)
        return DemucsIsolationResult(
            VocalsWavPath=VocalsPath,
            InstrumentalWavPath=InstrumentalPath,
            VocalsRmsDbfs=VocalsRms,
        )

    # directive: audio-dialog-boost-real | # see audio-normalization.C14
    def MixBoostedPremix(self, IsolationResult, OutputWavPath, VocalsBoostDb=5.0, InstrumentalAttenDb=3.0):
        Filter = (
            f"[0:a:0]volume={VocalsBoostDb:+.1f}dB[v];"
            f"[1:a:0]volume={-abs(InstrumentalAttenDb):+.1f}dB[i];"
            f"[v][i]amix=inputs=2:duration=longest:dropout_transition=0[out]"
        )
        Cmd = [
            self.FfmpegPath, "-y",
            "-i", IsolationResult.VocalsWavPath,
            "-i", IsolationResult.InstrumentalWavPath,
            "-filter_complex", Filter,
            "-map", "[out]",
            "-c:a", "pcm_s16le",
            "-ar", "48000",
            OutputWavPath,
        ]
        R = subprocess.run(Cmd, capture_output=True, text=True, timeout=1800)
        if R.returncode != 0:
            raise RuntimeError(f"premix ffmpeg failed: {R.stderr[-400:]}")
        IsolationResult.PremixWavPath = OutputWavPath
        return IsolationResult

    # directive: audio-dialog-boost-real | # see audio-normalization.C14
    def _FindStem(self, OutputDir, Base, Stem):
        for Name in os.listdir(OutputDir):
            if Base in Name and Stem in Name and Name.lower().endswith((".wav", ".flac")):
                return LocalJoin(OutputDir, Name)
        return None

    # directive: audio-dialog-boost-real | # see audio-normalization.C14
    def _MeasureWavRmsDbfs(self, WavPath):
        Result = subprocess.run(
            [self.FfmpegPath, "-i", WavPath, "-map", "0:a:0", "-af", "astats", "-f", "null", "-"],
            capture_output=True, text=True, timeout=120,
        )
        Values = []
        for Line in Result.stderr.splitlines():
            if "RMS level dB:" in Line:
                Token = Line.split("RMS level dB:")[1].strip()
                if Token == "-inf":
                    Values.append(SILENCE_FLOOR_DBFS)
                else:
                    try:
                        Values.append(float(Token))
                    except ValueError:
                        pass
        return Values[-1] if Values else SILENCE_FLOOR_DBFS
