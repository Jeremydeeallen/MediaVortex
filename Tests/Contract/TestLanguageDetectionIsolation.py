import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


FORBIDDEN_IMPORTS = [
    r'\bAudioVertical\b',
    r'\bAudioPolicyAdmissionGate\b',
    r'\b_SpawnAudioBackfill\b',
    r'\bQueueManagementBusinessService\b',
    r'\bWorkBucket\b',
    r'\bAudioComplianceRules\w*\b',
]


TARGET_FILES = [
    'WorkerService/LanguageWorker.py',
    'Features/AudioNormalization/Services/LanguageEnrichmentService.py',
    'Features/AudioNormalization/Services/FasterWhisperBackend.py',
    'Features/AudioNormalization/Services/LanguageEnrichmentError.py',
    'Features/AudioNormalization/Repositories/MediaFileLanguageDetectionsRepository.py',
]


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# directive: audio-language-detection C5
class TestLanguageDetectionIsolation(unittest.TestCase):

    def test_no_forbidden_imports(self):
        Violations = []
        for RelPath in TARGET_FILES:
            P = REPO_ROOT / RelPath
            if not P.exists():
                continue
            Src = P.read_text(encoding='utf-8')
            for Pattern in FORBIDDEN_IMPORTS:
                if re.search(Pattern, Src):
                    Violations.append(f'{RelPath}: matches {Pattern}')
        self.assertEqual(Violations, [], msg=f'forbidden imports in language-detection files: {Violations}')


if __name__ == '__main__':
    unittest.main()
