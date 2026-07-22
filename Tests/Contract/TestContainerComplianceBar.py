import unittest
from dataclasses import dataclass
from typing import Optional

from Features.ContainerFormat.ContainerVertical import ContainerVertical


# directive: transcode-flow-canonical -- C33 profile-independent baseline
@dataclass
class _FakeMf:
    Id: int = 1
    ContainerFormat: Optional[str] = 'mov,mp4,m4a,3gp,3g2,mj2'
    AssignedProfile: Optional[str] = None


# directive: transcode-flow-canonical -- C33 baseline rules injected via stub Db
class _StubDb:
    def __init__(self, AllowedCsv: str = 'mp4'):
        self._Csv = AllowedCsv

    def ExecuteQuery(self, _Sql, _Params=None):
        return [{'acceptablecontainerscsv': self._Csv}]


# directive: transcode-flow-canonical -- C33
class TestContainerComplianceBar(unittest.TestCase):

    def test_mp4_source_against_mp4_baseline_is_compliant(self):
        C, R = ContainerVertical(Db=_StubDb('mp4')).Evaluate(_FakeMf(ContainerFormat='mov,mp4,m4a,3gp,3g2,mj2'))
        self.assertTrue(C)
        self.assertIsNone(R)

    def test_mkv_source_against_mp4_baseline_is_noncompliant(self):
        C, R = ContainerVertical(Db=_StubDb('mp4')).Evaluate(_FakeMf(ContainerFormat='matroska,webm'))
        self.assertFalse(C)
        self.assertIn('container:', R)

    def test_mkv_source_against_mkv_baseline_is_compliant(self):
        C, _ = ContainerVertical(Db=_StubDb('mkv')).Evaluate(_FakeMf(ContainerFormat='matroska,webm'))
        self.assertTrue(C)

    def test_mp4_and_mkv_both_allowed(self):
        for Ctr in ('mp4', 'mkv', 'm4v', 'mov'):
            with self.subTest(Container=Ctr):
                C, _ = ContainerVertical(Db=_StubDb('mp4,mkv')).Evaluate(_FakeMf(ContainerFormat=Ctr))
                self.assertTrue(C)

    def test_no_source_container_returns_none(self):
        C, R = ContainerVertical(Db=_StubDb('mp4')).Evaluate(_FakeMf(ContainerFormat=None))
        self.assertIsNone(C)
        self.assertEqual(R, 'no_source_container')

    def test_empty_rules_raises(self):
        with self.assertRaises(RuntimeError):
            ContainerVertical(Db=_StubDb('')).Evaluate(_FakeMf())


if __name__ == '__main__':
    unittest.main()
