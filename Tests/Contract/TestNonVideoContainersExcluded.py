import unittest
from dataclasses import dataclass
from typing import Optional
from unittest.mock import MagicMock

from Features.AudioNormalization.AudioVertical import AudioVertical
from Features.ContainerFormat.ContainerVertical import ContainerVertical
from Features.MediaFile.Domain.MediaFileScope import AUDIO_ONLY_CONTAINERS, IsAudioOnlyContainer
from Features.TranscodeJob.Emit.CommandComposer import CommandComposer, NonVideoSourceError
from Features.VideoEncoding.VideoVertical import VideoVertical


# directive: transcode-flow-canonical -- C34
@dataclass
class _FakeMf:
    Id: int = 1
    Codec: Optional[str] = 'mjpeg'
    Resolution: Optional[str] = '600x600'
    ResolutionCategory: Optional[str] = None
    VideoBitrateKbps: Optional[int] = 178
    FrameRate: Optional[float] = 90000.0
    ContainerFormat: Optional[str] = 'mp3'
    AudioCodec: Optional[str] = 'mp3'
    AudioCorruptSuspect: Optional[bool] = None
    AudioComplete: Optional[bool] = None
    AssignedProfile: Optional[str] = None
    TranscodedByMediaVortex: bool = False
    FileName: str = '01 Song.mp3'


class _StubVideoDb:
    def ExecuteQuery(self, _Sql, _Params=None):
        return [{'acceptablevideocodecscsv': 'av1,hevc', 'bpptranscodethreshold': 0.05}]


class _StubContainerDb:
    def ExecuteQuery(self, _Sql, _Params=None):
        return [{'acceptablecontainerscsv': 'mp4,mkv'}]


class _StubAudioDb:
    def ExecuteQuery(self, _Sql, _Params=None):
        return [{
            'targetintegratedlufs': -23.0,
            'targettruepeakdbtp': -2.0,
            'acceptableaudiocodecscsv': 'opus,aac',
        }]


# directive: transcode-flow-canonical -- C34
class TestNonVideoContainersExcluded(unittest.TestCase):

    def test_audio_only_containers_set_covers_common_formats(self):
        self.assertIn('mp3', AUDIO_ONLY_CONTAINERS)
        self.assertIn('flac', AUDIO_ONLY_CONTAINERS)
        self.assertIn('wav', AUDIO_ONLY_CONTAINERS)
        self.assertIn('ogg', AUDIO_ONLY_CONTAINERS)
        self.assertIn('aac', AUDIO_ONLY_CONTAINERS)
        self.assertIn('opus', AUDIO_ONLY_CONTAINERS)
        self.assertIn('dsf', AUDIO_ONLY_CONTAINERS)
        self.assertIn('dff', AUDIO_ONLY_CONTAINERS)
        self.assertIn('ape', AUDIO_ONLY_CONTAINERS)
        self.assertIn('wma', AUDIO_ONLY_CONTAINERS)

    def test_video_containers_not_flagged(self):
        for Container in ('mp4', 'mov', 'mkv', 'matroska,webm', 'mov,mp4,m4a,3gp,3g2,mj2', 'avi', 'mpegts', 'asf'):
            Mf = _FakeMf(ContainerFormat=Container)
            self.assertFalse(IsAudioOnlyContainer(Mf), f"{Container} misclassified as audio-only")

    def test_mp3_container_flagged(self):
        Mf = _FakeMf(ContainerFormat='mp3')
        self.assertTrue(IsAudioOnlyContainer(Mf))

    def test_empty_container_not_flagged(self):
        self.assertFalse(IsAudioOnlyContainer(_FakeMf(ContainerFormat=None)))
        self.assertFalse(IsAudioOnlyContainer(_FakeMf(ContainerFormat='')))

    def test_video_vertical_returns_none_for_mp3(self):
        Mf = _FakeMf(ContainerFormat='mp3')
        Compliant, Reason = VideoVertical(Db=_StubVideoDb()).Evaluate(Mf)
        self.assertIsNone(Compliant)
        self.assertEqual(Reason, 'non_video_scope')

    def test_container_vertical_returns_none_for_mp3(self):
        Mf = _FakeMf(ContainerFormat='mp3')
        Compliant, Reason = ContainerVertical(Db=_StubContainerDb()).Evaluate(Mf)
        self.assertIsNone(Compliant)
        self.assertEqual(Reason, 'non_video_scope')

    def test_audio_vertical_returns_none_for_mp3(self):
        Mf = _FakeMf(ContainerFormat='mp3')
        Vertical = AudioVertical(Gate=MagicMock(), Db=_StubAudioDb())
        Compliant, Reason = Vertical.Evaluate(Mf)
        self.assertIsNone(Compliant)
        self.assertEqual(Reason, 'non_video_scope')

    def test_command_composer_raises_for_mp3(self):
        Mf = _FakeMf(ContainerFormat='mp3')
        Job = MagicMock(Id=42, ProcessingMode='Transcode', FilePath='/x.mp3')
        Composer = CommandComposer(MediaProbeAdapterInstance=MagicMock())
        with self.assertRaises(NonVideoSourceError):
            Composer.Build(Mf, Job, Context={'FFmpegPath': '/usr/bin/ffmpeg'})


class TestTranscodeQueueRefusesAudioOnlyLive(unittest.TestCase):

    def setUp(self):
        from Core.Database.DatabaseService import DatabaseService
        self.Db = DatabaseService()
        Rows = self.Db.ExecuteQuery(
            "SELECT Id, StorageRootId, RelativePath, FileName, SizeMB "
            "FROM MediaFiles "
            "WHERE ContainerFormat = 'mp3' "
            "LIMIT 1"
        )
        if not Rows:
            self.skipTest("no mp3 MediaFile present for live test")
        self.Row = Rows[0]

    def test_direct_insert_raises(self):
        import psycopg2
        Params = (
            int(self.Row.get('storagerootid') or 2),
            self.Row.get('relativepath') or 'test.mp3',
            self.Row.get('filename') or 'test.mp3',
            '',
            1_000_000,
            float(self.Row.get('sizemb') or 1.0),
            1,
            'Pending',
            'Transcode',
            int(self.Row.get('id')),
        )
        Sql = (
            "INSERT INTO TranscodeQueue "
            "(StorageRootId, RelativePath, FileName, Directory, "
            "SizeBytes, SizeMB, Priority, Status, ProcessingMode, MediaFileId, DateAdded) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())"
        )
        with self.assertRaises(psycopg2.errors.RaiseException):
            self.Db.ExecuteNonQuery(Sql, Params)

    def test_add_job_refuses_forceadd(self):
        from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
        Svc = QueueManagementBusinessService()
        Result = Svc.AddJobToQueue(int(self.Row.get('id')), Priority=200, ForceAdd=True)
        self.assertFalse(Result.get('Success'))
        self.assertIn('audio-only', (Result.get('ErrorMessage') or '').lower())


if __name__ == '__main__':
    unittest.main()
