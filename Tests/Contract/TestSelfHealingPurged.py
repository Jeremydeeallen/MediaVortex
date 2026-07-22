import unittest
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# directive: transcode-flow-canonical -- C33k
class TestSelfHealingPurged(unittest.TestCase):

    def test_selfhealing_directory_does_not_exist(self):
        SelfHealDir = _REPO_ROOT / 'Features' / 'AudioNormalization' / 'SelfHealing'
        self.assertFalse(SelfHealDir.exists(),
            f"SelfHealing directory must be deleted per C33; found at {SelfHealDir}")

    def test_webservice_main_has_no_audio_vertical_health_loop(self):
        Src = (_REPO_ROOT / 'WebService' / 'Main.py').read_text(encoding='utf-8')
        self.assertNotIn('PrivateAudioVerticalHealthLoop', Src,
            "WebService/Main.py must not carry PrivateAudioVerticalHealthLoop per C33")
        self.assertNotIn('PrivateStartAudioVerticalHealth', Src,
            "WebService/Main.py must not carry PrivateStartAudioVerticalHealth per C33")
        self.assertNotIn('AudioVerticalHealthComposition', Src,
            "WebService/Main.py must not import SelfHealing composition per C33")

    def test_activity_repository_has_no_get_audio_vertical_health(self):
        Src = (_REPO_ROOT / 'Features' / 'Activity' / 'ActivityRepository.py').read_text(encoding='utf-8')
        self.assertNotIn('GetAudioVerticalHealth', Src,
            "ActivityRepository must not carry GetAudioVerticalHealth per C33")


if __name__ == '__main__':
    unittest.main()
