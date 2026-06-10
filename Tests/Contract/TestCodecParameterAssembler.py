# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C4

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.TranscodeJob.Emit.CodecParameterAssembler import CodecParameterAssembler


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C4
class TestCodecParameterAssembler:
    """Verify codec parameter assembly ported from CommandBuilder."""

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C4
    def test_software_crf_param_appended_when_crf_known(self):
        """Software path emits -crf when 'crf' is in CodecParameters lookup."""
        Assembler = CodecParameterAssembler()
        Parts = []
        Assembler.AddCodecParameters(
            Parts,
            CodecParameters=[{'ParameterName': 'crf'}, {'ParameterName': 'preset'}],
            ProfileSettings={'UseNvidiaHardware': 0, 'Quality': 28, 'Preset': '4'},
        )
        assert '-crf' in Parts
        assert '28' in Parts
        assert '-preset' in Parts
        assert '4' in Parts

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C4
    def test_nvenc_emits_preset_pN_and_cq(self):
        """NVENC path adds preset 'pN' form and -cq when quality set."""
        Assembler = CodecParameterAssembler()
        Parts = []
        Assembler.AddCodecParameters(
            Parts,
            CodecParameters=[],
            ProfileSettings={
                'UseNvidiaHardware': 1,
                'Preset': '7',
                'Quality': 32,
                'RateControlMode': 'cq',
            },
        )
        assert '-preset' in Parts
        assert 'p7' in Parts
        assert '-cq' in Parts
        assert '32' in Parts
        assert '-rc' in Parts
        assert 'vbr' in Parts

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C4
    def test_film_grain_skipped_for_nvenc(self):
        """NVIDIA path skips film grain emit."""
        Assembler = CodecParameterAssembler()
        Parts = []
        Assembler.AddFilmGrainParameter(
            Parts,
            CodecParameters=[{'ParameterName': 'film-grain'}],
            ProfileSettings={'UseNvidiaHardware': 1, 'FilmGrain': 8},
        )
        assert Parts == []

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C4
    def test_film_grain_emitted_for_software_when_above_zero(self):
        """SVT path emits svtav1-params film-grain when FilmGrain > 0 and supported."""
        Assembler = CodecParameterAssembler()
        Parts = []
        Assembler.AddFilmGrainParameter(
            Parts,
            CodecParameters=[{'ParameterName': 'film-grain'}],
            ProfileSettings={'UseNvidiaHardware': 0, 'FilmGrain': 8},
        )
        assert '-svtav1-params' in Parts
        assert 'film-grain=8' in Parts

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C4
    def test_pixel_format_emitted_when_set(self):
        """ProfileSettings.PixelFormat -> -pix_fmt arg pair."""
        Assembler = CodecParameterAssembler()
        Parts = []
        Assembler.AddPixelFormatParameter(
            Parts,
            CodecParameters=[],
            ProfileSettings={'PixelFormat': 'yuv420p10le'},
        )
        assert Parts == ['-pix_fmt', 'yuv420p10le']

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C4
    def test_pixel_format_omitted_when_unset(self):
        """No PixelFormat => nothing appended."""
        Assembler = CodecParameterAssembler()
        Parts = []
        Assembler.AddPixelFormatParameter(Parts, CodecParameters=[], ProfileSettings={})
        assert Parts == []
