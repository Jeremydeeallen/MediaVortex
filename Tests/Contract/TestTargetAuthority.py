# directive: target-policy-1a-tables | # see policy.C2 -- only Features/Policy/ reads the policy tables and the view; a reader anywhere else is a second authority
import os
import re
import unittest


_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_POLICY_TABLES = ('TargetOverrides', 'FrameRateClasses', 'EncoderSettings', 'LadderCells', 'MediaFileTargets')
_SCAN_ROOTS = ('Features', 'Core', 'Repositories', 'Services', 'WorkerService', 'WebService', 'Controllers', 'Models', 'ViewModels', 'Scripts', 'deploy')
_ALLOWED_PREFIXES = (
    os.path.join('Features', 'Policy') + os.sep,
    os.path.join('Scripts', 'SQLScripts') + os.sep,
)


# directive: target-policy-1a-tables | # see policy.C2
def _ScanPyFiles():
    for Subtree in _SCAN_ROOTS:
        Abs = os.path.join(_REPO_ROOT, Subtree)
        if not os.path.isdir(Abs):
            continue
        for DirName, _Dirs, Files in os.walk(Abs):
            if 'venv' in DirName or '__pycache__' in DirName:
                continue
            for F in Files:
                if not F.endswith('.py'):
                    continue
                Filename = os.path.join(DirName, F)
                with open(Filename, 'r', encoding='utf-8', errors='ignore') as Fh:
                    yield os.path.relpath(Filename, _REPO_ROOT), Fh.read()


# directive: target-policy-1a-tables | # see policy.C2
class TestTargetAuthority(unittest.TestCase):

    # directive: target-policy-1a-tables | # see policy.C2
    def test_policy_tables_are_read_only_inside_features_policy(self):
        Pattern = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE|DELETE\s+FROM)\s+(" + '|'.join(_POLICY_TABLES) + r")\b", re.IGNORECASE)
        Offenders = []
        for Rel, Content in _ScanPyFiles():
            if Rel.startswith(_ALLOWED_PREFIXES):
                continue
            for M in Pattern.finditer(Content):
                Line = Content.count('\n', 0, M.start()) + 1
                Offenders.append(f"  {Rel}:{Line}: {M.group(0)}")
        self.assertEqual(Offenders, [], "Policy tables touched outside Features/Policy/:\n" + '\n'.join(Offenders))

    # directive: target-policy-1a-tables | # see policy.C2
    def test_features_policy_owns_the_resolver_and_selector(self):
        for Name in ('Target.py', 'TargetResolver.py', 'EncoderSelector.py'):
            self.assertTrue(os.path.exists(os.path.join(_REPO_ROOT, 'Features', 'Policy', Name)), f"Features/Policy/{Name} must exist")
        self.assertFalse(os.path.isdir(os.path.join(_REPO_ROOT, 'Features', 'Profiles')), "Features/Profiles must not exist after the rename")


if __name__ == '__main__':
    unittest.main()
