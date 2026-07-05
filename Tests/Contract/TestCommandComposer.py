import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.AudioStrategyResult import AudioPolicyUnresolvedError
from Features.TranscodeJob.Emit.CommandComposer import CommandComposer
from Features.TranscodeJob.Emit.CommandSpec import CommandSpec
from Features.TranscodeJob.Emit.Plan import Plan, PlanFactory
from Features.TranscodeJob.Emit.Slots.AudioSlot import AudioEmission, AudioSlot
from Features.TranscodeJob.Emit.Slots.ContainerSlot import ContainerSlot
from Features.TranscodeJob.Emit.Slots.SubtitleSlot import SubtitleSlot
from Features.TranscodeJob.Emit.Slots.VideoSlot import VideoSlot


# directive: transcode-flow-canonical | # see transcode.ST5
def _MediaFile(**Overrides):
    Mf = MagicMock()
    Mf.Id = 1
    Mf.FileName = 'Test.mkv'
    Mf.Codec = Overrides.get('Codec', 'h264')
    Mf.AudioCodec = 'aac'
    Mf.AudioChannels = 2
    Mf.Resolution = '1920x1080'
    Mf.SubtitleFormats = Overrides.get('SubtitleFormats', 'subrip')
    Mf.IsInterlaced = None
    return Mf


# directive: transcode-flow-canonical | # see transcode.ST5
def _Job(ProcessingMode='Transcode'):
    J = MagicMock()
    J.Id = 42
    J.ProcessingMode = ProcessingMode
    J.FilePath = 'T:/Test.mkv'
    return J


# directive: transcode-flow-canonical | # see transcode.ST5
def _Context(**Overrides):
    Ctx = {
        'FFmpegPath': 'C:/ffmpeg.exe',
        'InputPath': 'T:/Test.mkv',
        'ProfileSettings': {
            'ContainerType': 'mp4',
            'Codec': 'av1_nvenc',
            'UseNvidiaHardware': 1,
            'RateControlMode': 'vbr',
            'TargetKbps': 2400,
            'MaxBitrateMultiplier': 1.5,
            'Preset': 7,
        },
        'CodecParameters': [],
        'MaxCpuThreads': 4,
        'SourceResolution': '1920x1080',
    }
    Ctx.update(Overrides)
    return Ctx


# directive: transcode-flow-canonical | # see transcode.ST5
class TestPlanFactory(unittest.TestCase):

    def test_transcode_mode_returns_reencode_plan(self):
        P = PlanFactory().FromProcessingMode('Transcode')
        self.assertEqual(P, Plan(VideoOp='Reencode', AudioOp='Reencode', SubtitleOp='Preserve', ContainerOp='Mp4'))

    def test_remux_mode_returns_copy_plan(self):
        P = PlanFactory().FromProcessingMode('Remux')
        self.assertEqual(P, Plan(VideoOp='Copy', AudioOp='Reencode', SubtitleOp='Preserve', ContainerOp='Mp4'))

    def test_quick_mode_returns_copy_plan(self):
        P = PlanFactory().FromProcessingMode('Quick')
        self.assertEqual(P.VideoOp, 'Copy')

    def test_audiofix_mode_returns_copy_plan(self):
        P = PlanFactory().FromProcessingMode('AudioFix')
        self.assertEqual(P.VideoOp, 'Copy')

    def test_subtitlefix_mode_returns_copy_plan(self):
        P = PlanFactory().FromProcessingMode('SubtitleFix')
        self.assertEqual(P.VideoOp, 'Copy')

    def test_unknown_mode_raises_value_error(self):
        with self.assertRaises(ValueError):
            PlanFactory().FromProcessingMode('NotAMode')


# directive: transcode-flow-canonical | # see transcode.ST5
class TestVideoSlot(unittest.TestCase):

    def test_copy_emits_map_and_stream_copy(self):
        Argv = VideoSlot().Emit('Copy', _MediaFile(), {}, [], None, None)
        self.assertEqual(Argv[:4], ['-map', '0:v:0', '-c:v', 'copy'])

    def test_copy_tags_hvc1_on_hevc_source(self):
        Argv = VideoSlot().Emit('Copy', _MediaFile(Codec='hevc'), {}, [], None, None)
        self.assertIn('-tag:v', Argv)
        self.assertIn('hvc1', Argv)

    def test_copy_omits_hvc1_tag_on_non_hevc(self):
        Argv = VideoSlot().Emit('Copy', _MediaFile(Codec='h264'), {}, [], None, None)
        self.assertNotIn('-tag:v', Argv)

    def test_reencode_nvenc_vbr_emits_target_kbps(self):
        Argv = VideoSlot().Emit(
            'Reencode', _MediaFile(),
            {'Codec': 'av1_nvenc', 'UseNvidiaHardware': 1, 'RateControlMode': 'vbr',
             'TargetKbps': 2400, 'MaxBitrateMultiplier': 1.5, 'Preset': 7},
            [], None, 4,
        )
        self.assertIn('-c:v', Argv)
        self.assertIn('av1_nvenc', Argv)
        self.assertIn('-b:v', Argv)
        self.assertIn('2400k', Argv)
        self.assertIn('-threads', Argv)

    def test_reencode_nvenc_vbr_raises_without_target_kbps(self):
        with self.assertRaises(ValueError):
            VideoSlot().Emit(
                'Reencode', _MediaFile(),
                {'Codec': 'av1_nvenc', 'UseNvidiaHardware': 1, 'RateControlMode': 'vbr',
                 'MaxBitrateMultiplier': 1.5},
                [], None, None,
            )

    def test_reencode_qsv_icq_emits_global_quality(self):
        Argv = VideoSlot().Emit(
            'Reencode', _MediaFile(),
            {'Codec': 'av1_qsv', 'UseNvidiaHardware': 0, 'RateControlMode': 'icq', 'IcqQ': 30},
            [], None, None,
        )
        self.assertIn('av1_qsv', Argv)
        self.assertIn('-global_quality:v', Argv)
        self.assertIn('30', Argv)

    def test_reencode_qsv_icq_raises_without_icq_q(self):
        with self.assertRaises(ValueError):
            VideoSlot().Emit(
                'Reencode', _MediaFile(),
                {'Codec': 'av1_qsv', 'UseNvidiaHardware': 0, 'RateControlMode': 'icq'},
                [], None, None,
            )

    def test_unknown_op_raises(self):
        with self.assertRaises(ValueError):
            VideoSlot().Emit('Weird', _MediaFile(), {}, [], None, None)


# directive: transcode-flow-canonical | # see transcode.ST5
class TestAudioSlot(unittest.TestCase):

    def test_reencode_raises_on_missing_policy(self):
        Resolver = MagicMock()
        Resolver.GetEffectivePolicy = lambda Mf: None
        Slot = AudioSlot(Resolver=Resolver, Emitter=MagicMock(), StreamProbe=MagicMock())
        with self.assertRaises(AudioPolicyUnresolvedError):
            Slot.Emit('Reencode', _MediaFile(), {'InputPath': 'x'})

    def test_reencode_raises_on_empty_blocks(self):
        Resolver = MagicMock()
        Resolver.GetEffectivePolicy = lambda Mf: MagicMock()
        Emitter = MagicMock()
        Emitter.EmitTracks.return_value = []
        Probe = MagicMock()
        Probe.Probe = lambda P: []
        Slot = AudioSlot(Resolver=Resolver, Emitter=Emitter, StreamProbe=Probe)
        with self.assertRaises(AudioPolicyUnresolvedError):
            Slot.Emit('Reencode', _MediaFile(), {'InputPath': 'x'})

    def test_reencode_folds_blocks_into_input_and_stream_args(self):
        Block = MagicMock()
        Block.InputArgs = ['-i', 'C:/premix.wav']
        Block.MapArgs = ['-map', '1:a:0']
        Block.CodecArgs = ['-c:a:0', 'libopus', '-b:a:0', '128k']
        Block.FilterArgs = []
        Block.MetadataArgs = ['-metadata:s:a:0', 'title=Original']
        Block.DispositionArgs = ['-disposition:a:0', 'default']
        Resolver = MagicMock()
        Resolver.GetEffectivePolicy = lambda Mf: MagicMock()
        Emitter = MagicMock()
        Emitter.EmitTracks.return_value = [Block]
        Probe = MagicMock()
        Probe.Probe = lambda P: []
        Slot = AudioSlot(Resolver=Resolver, Emitter=Emitter, StreamProbe=Probe)
        Emission = Slot.Emit('Reencode', _MediaFile(), {'InputPath': 'x'})
        self.assertIn('-i', Emission.InputArgs)
        self.assertEqual(Emission.InputArgs[0], '-i')
        self.assertTrue(Emission.InputArgs[1].startswith('"'))
        self.assertIn('-map', Emission.StreamArgs)
        self.assertIn('libopus', Emission.StreamArgs)

    def test_copy_emits_stream_copy_no_inputs(self):
        Emission = AudioSlot().Emit('Copy', _MediaFile(), {})
        self.assertEqual(Emission.InputArgs, [])
        self.assertIn('-c:a', Emission.StreamArgs)
        self.assertIn('copy', Emission.StreamArgs)

    def test_unknown_op_raises(self):
        with self.assertRaises(ValueError):
            AudioSlot().Emit('Weird', _MediaFile(), {})


# directive: transcode-flow-canonical | # see transcode.ST5
class TestContainerSlot(unittest.TestCase):

    def test_mp4_emits_f_mp4_and_faststart(self):
        Argv = ContainerSlot().Emit('Mp4')
        self.assertEqual(Argv, ['-f', 'mp4', '-movflags', '+faststart'])

    def test_unknown_op_raises(self):
        with self.assertRaises(ValueError):
            ContainerSlot().Emit('Mkv')


# directive: transcode-flow-canonical | # see transcode.ST5
def _MakeComposer(AudioSlotOverride=None):
    Video = VideoSlot()
    Audio = AudioSlotOverride or _StubAudioSlot()
    Subtitle = SubtitleSlot()
    Container = ContainerSlot()
    Resolution = MagicMock()
    Resolution.CalculateTargetResolution = lambda Ps, Src: '1280x720'
    Resolution.CalculateScaleFilter = lambda Src, Tgt, Mf, Ps: None
    Filename = MagicMock()
    Filename.NormalizeFfmpegPath = lambda P: (P or '').strip().strip('"')
    Filename.GenerateOutputFileName = lambda Fn, Sr, Tr, Ct, Crf: 'Test-mv.mp4.inprogress'
    Filename.CollapseMvSuffix = lambda B: B
    Probe = MagicMock()
    Probe.RunAnalysis = lambda P: None
    return CommandComposer(
        VideoSlotInstance=Video,
        AudioSlotInstance=Audio,
        SubtitleSlotInstance=Subtitle,
        ContainerSlotInstance=Container,
        ResolutionCalculatorInstance=Resolution,
        OutputFilenameBuilderInstance=Filename,
        MediaProbeAdapterInstance=Probe,
        PlanFactoryInstance=PlanFactory(),
    )


# directive: transcode-flow-canonical | # see transcode.ST5
def _StubAudioSlot():
    Slot = MagicMock(spec=AudioSlot)
    Slot.Emit = lambda Op, Mf, Ctx: AudioEmission(
        InputArgs=[],
        StreamArgs=['-map', '0:a:0', '-c:a:0', 'libopus', '-b:a:0', '96k'],
    )
    return Slot


# directive: transcode-flow-canonical | # see transcode.ST5
class TestCommandComposer(unittest.TestCase):

    def test_transcode_plan_produces_reencode_argv(self):
        Composer = _MakeComposer()
        Spec = Composer.Build(_MediaFile(), _Job('Transcode'), _Context())
        self.assertIsInstance(Spec, CommandSpec)
        self.assertIn('av1_nvenc', Spec.Command)
        self.assertIn('-b:v', Spec.Command)
        self.assertIn('2400k', Spec.Command)

    def test_remux_plan_produces_stream_copy_argv(self):
        Composer = _MakeComposer()
        Spec = Composer.Build(_MediaFile(), _Job('Remux'), _Context())
        self.assertIn('-c:v copy', Spec.Command)

    def test_container_slot_always_emits_faststart(self):
        Composer = _MakeComposer()
        Spec1 = Composer.Build(_MediaFile(), _Job('Transcode'), _Context())
        Spec2 = Composer.Build(_MediaFile(), _Job('Remux'), _Context())
        for Spec in (Spec1, Spec2):
            self.assertIn('-f mp4', Spec.Command)
            self.assertIn('-movflags +faststart', Spec.Command)

    def test_subtitle_slot_always_fires_mov_text_on_mp4(self):
        Composer = _MakeComposer()
        for Mode in ('Transcode', 'Remux', 'Quick', 'AudioFix', 'SubtitleFix'):
            Spec = Composer.Build(_MediaFile(SubtitleFormats='subrip'), _Job(Mode), _Context())
            self.assertIn('-map 0:s?', Spec.Command, f"SubtitleSlot missing on mode {Mode}")
            self.assertIn('-c:s mov_text', Spec.Command, f"mov_text codec missing on mode {Mode}")

    def test_subtitle_slot_drops_pgs_with_warn_on_mp4(self):
        Composer = _MakeComposer()
        Spec = Composer.Build(_MediaFile(SubtitleFormats='hdmv_pgs_subtitle'), _Job('Transcode'), _Context())
        self.assertNotIn('-c:s mov_text', Spec.Command)
        self.assertNotIn('-c:s copy', Spec.Command)

    def test_missing_ffmpeg_path_returns_none(self):
        Composer = _MakeComposer()
        Spec = Composer.Build(_MediaFile(), _Job('Transcode'), _Context(FFmpegPath=None))
        self.assertIsNone(Spec)

    def test_start_time_prepends_ss(self):
        Composer = _MakeComposer()
        Ctx = _Context(StartTime='00:00:30')
        Spec = Composer.Build(_MediaFile(), _Job('Transcode'), Ctx)
        self.assertIn('-ss 00:00:30', Spec.Command)

    def test_output_path_is_inprogress_side_by_side_for_streamcopy(self):
        Composer = _MakeComposer()
        Spec = Composer.Build(_MediaFile(), _Job('Remux'), _Context())
        self.assertTrue(Spec.OutputPath.endswith('-mv.mp4.inprogress'))


if __name__ == '__main__':
    unittest.main()
