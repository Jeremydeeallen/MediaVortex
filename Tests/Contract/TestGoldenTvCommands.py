# directive: target-policy-1a-tables | # see policy.C6, policy.S3 -- one TV fixture's Transcode + AudioFix argv must not move across the program's phases
import json
import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.AudioDispositionResolver import AudioDispositionResolver
from Features.AudioNormalization.AudioFilterEmitter import AudioFilterEmitter
from Features.AudioNormalization.Policies.IAudioDefaultLanguagePolicy import RankPreferredDefaultPolicy
from Features.TranscodeJob.Emit.CommandComposer import CommandComposer
from Features.TranscodeJob.Emit.HwAccelResolver import HwAccelResolver
from Features.TranscodeJob.Emit.Slots.AudioSlot import AudioSlot
from Features.TranscodeJob.Emit.Slots.VideoSlot import VideoSlot
from Features.TranscodeJob.Emit.VideoFilterBuilder import VideoFilterBuilder


GOLDEN = Path(__file__).resolve().parent / 'Golden'
_MASK = re.compile(r'(-metadata "mediavortex_(?:worker|commit|ts)=)[^"]*"')


# directive: target-policy-1a-tables | # see policy.C6
def _LoadJson(Name):
    with open(GOLDEN / Name, 'r', encoding='utf-8') as F:
        return json.load(F)


# directive: target-policy-1a-tables | # see policy.C6
def _LoadArgv(Name):
    with open(GOLDEN / Name, 'r', encoding='utf-8') as F:
        return F.read().strip()


# directive: target-policy-1a-tables | # see policy.C6 -- worker, commit and timestamp encode the run, not the policy; the test host is Windows, the workers are Linux
def Mask(Command):
    return _MASK.sub(r'\1<masked>"', Command).replace('\\', '/')


# directive: target-policy-1a-tables | # see policy.S3
class _RowsStub:

    # directive: target-policy-1a-tables | # see policy.S3
    def __init__(self, Rows):
        self._Rows = Rows

    # directive: target-policy-1a-tables | # see policy.S3
    def ExecuteQuery(self, Query, Parameters=()):
        return list(self._Rows)


# directive: target-policy-1a-tables | # see policy.S3
class _RulesStub:

    # directive: target-policy-1a-tables | # see policy.S3
    def __init__(self, Rules):
        self._Rules = Rules

    # directive: target-policy-1a-tables | # see policy.S3
    def GetRules(self):
        return dict(self._Rules)


# directive: target-policy-1a-tables | # see policy.S3
class _PolicyStub:

    # directive: target-policy-1a-tables | # see policy.S3
    def __init__(self, Policy):
        self._Policy = Policy

    # directive: target-policy-1a-tables | # see policy.S3
    def GetEffectivePolicy(self, MediaFile):
        return dict(self._Policy)


# directive: target-policy-1a-tables | # see policy.S3
class _StreamProbeStub:

    # directive: target-policy-1a-tables | # see policy.S3
    def __init__(self, Streams):
        self._Streams = Streams

    # directive: target-policy-1a-tables | # see policy.S3
    def Probe(self, LocalSourcePath):
        return [dict(S) for S in self._Streams]


# directive: target-policy-1a-tables | # see policy.S3
def _BuildComposer(Fixture, Label):
    Rules = Fixture['AudioComplianceRules']
    Rank = _RowsStub([{'SettingValue': Fixture['PreferredDefaultLanguageRank']}])
    Emitter = AudioFilterEmitter(
        DispositionResolver=AudioDispositionResolver(DefaultLanguagePolicy=RankPreferredDefaultPolicy(Db=Rank)),
        RulesRepo=_RulesStub(Rules),
    )
    Audio = AudioSlot(
        Resolver=_PolicyStub(Fixture['AudioPolicy']),
        Emitter=Emitter,
        StreamProbe=_StreamProbeStub(_LoadJson('tv-streams.json')[Label]['Audio']),
        RulesRepository=_RulesStub(Rules),
    )
    return CommandComposer(
        VideoSlotInstance=VideoSlot(VideoFilterBuilder=VideoFilterBuilder()),
        AudioSlotInstance=Audio,
        MediaProbeAdapterInstance=None,
        HwAccelResolverInstance=HwAccelResolver(Db=_RowsStub([{'hwacceldecodeenabled': False}])),
    )


# directive: target-policy-1a-tables | # see policy.S3
def _Context(Fixture, Label):
    Section = dict(Fixture[Label])
    Section.pop('ProfileSettings')
    Ctx = {
        'FFmpegPath': Fixture['FFmpegPath'],
        'FfmpegLogLevel': Fixture['FfmpegLogLevel'],
        'ProfileSettings': dict(Fixture[Label]['ProfileSettings']),
        'SubtitleStreams': [tuple(S) for S in _LoadJson('tv-streams.json')[Label]['Subtitles']],
    }
    Ctx.update(Section)
    return Ctx


# directive: target-policy-1a-tables | # see policy.S3
def BuildGolden(Label):
    Fixture = _LoadJson('tv-context.json')
    MediaFile = SimpleNamespace(**{K: V for K, V in _LoadJson(f'tv-mediafile-{Label.lower()}.json').items() if not K.startswith('_')})
    Job = SimpleNamespace(Id=0, ProcessingMode=Label, FilePath=Fixture[Label]['InputPath'])
    Spec = _BuildComposer(Fixture, Label).Build(MediaFile, Job, _Context(Fixture, Label))
    if Spec is None:
        raise AssertionError(f'CommandComposer.Build returned None for the {Label} golden fixture')
    return Spec


# directive: target-policy-1a-tables | # see policy.C6
class TestGoldenTvCommands(unittest.TestCase):

    # directive: target-policy-1a-tables | # see policy.C6
    def test_tv_transcode_argv_is_byte_identical(self):
        self.assertEqual(Mask(BuildGolden('Transcode').Command), Mask(_LoadArgv('tv-transcode.argv')))

    # directive: target-policy-1a-tables | # see policy.C6
    def test_tv_audiofix_argv_is_byte_identical(self):
        self.assertEqual(Mask(BuildGolden('AudioFix').Command), Mask(_LoadArgv('tv-audiofix.argv')))

    # directive: target-policy-1a-tables | # see policy.C6
    def test_mask_touches_only_the_three_provenance_values(self):
        Raw = _LoadArgv('tv-transcode.argv')
        self.assertEqual(Raw.count('<masked>'), 3)
        self.assertIn('"mediavortex_profile=AV1 Tier 1 Efficient"', Mask(Raw))
        self.assertIn('"mediavortex_encoder=av1_nvenc"', Mask(Raw))


if __name__ == '__main__':
    unittest.main()
