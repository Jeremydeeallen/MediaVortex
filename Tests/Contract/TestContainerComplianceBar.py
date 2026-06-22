import unittest
from dataclasses import dataclass
from typing import Optional

from Features.Profiles.EffectiveProfile import EffectiveProfile
from Features.ContainerFormat.ContainerVertical import ContainerVertical


# directive: compliance-symmetry
@dataclass
class _FakeMf:
    Id: int = 1
    ContainerFormat: Optional[str] = 'mov,mp4,m4a,3gp,3g2,mj2'
    AssignedProfile: Optional[str] = 'Test'


# directive: compliance-symmetry
class _StubResolver:
    def __init__(self, P): self._P = P
    def Resolve(self, _): return self._P


# directive: compliance-symmetry
def _Vert(Container):
    Profile = EffectiveProfile(ProfileName='Test', Container=Container)
    return ContainerVertical(ProfileResolver=_StubResolver(Profile))


class TestContainerComplianceBar(unittest.TestCase):

    # directive: compliance-symmetry
    def test_mp4_source_against_mp4_profile_is_compliant(self):
        C, R = _Vert('mp4').Evaluate(_FakeMf(ContainerFormat='mov,mp4,m4a,3gp,3g2,mj2'))
        self.assertTrue(C)
        self.assertIsNone(R)

    # directive: compliance-symmetry
    def test_mkv_source_against_mp4_profile_is_noncompliant(self):
        C, R = _Vert('mp4').Evaluate(_FakeMf(ContainerFormat='matroska,webm'))
        self.assertFalse(C)
        self.assertIn('container:', R)

    # directive: compliance-symmetry
    def test_mkv_source_against_mkv_profile_is_compliant(self):
        C, _ = _Vert('mkv').Evaluate(_FakeMf(ContainerFormat='matroska,webm'))
        self.assertTrue(C)

    # directive: compliance-symmetry
    def test_mp4_universe_mp4_mkv_m4v_mov(self):
        for Profile in ('mp4', 'mkv', 'm4v', 'mov'):
            with self.subTest(Profile=Profile):
                C, _ = _Vert(Profile).Evaluate(_FakeMf(ContainerFormat=Profile))
                self.assertTrue(C)

    # directive: compliance-symmetry
    def test_no_profile_returns_undecidable(self):
        Vert = ContainerVertical(ProfileResolver=_StubResolver(None))
        C, R = Vert.Evaluate(_FakeMf())
        self.assertIsNone(C)
        self.assertEqual(R, 'no_effective_profile')


if __name__ == '__main__':
    unittest.main()
