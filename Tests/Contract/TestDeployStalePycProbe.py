import importlib.util
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEPLOY_SCRIPT = REPO_ROOT / 'deploy' / 'deploy-linux-worker.py'


# directive: transcode-flow-canonical
def _LoadProbeScript() -> str:
    Spec = importlib.util.spec_from_file_location('deploy_linux_worker', DEPLOY_SCRIPT)
    Module = importlib.util.module_from_spec(Spec)
    Spec.loader.exec_module(Module)
    return Module.STALE_PYC_PROBE_SCRIPT


# directive: transcode-flow-canonical
def _MakeSourceTree(Root: Path, Files: list) -> None:
    for RelPy, PySeconds, PycSeconds in Files:
        PyPath = Root / RelPy
        PyPath.parent.mkdir(parents=True, exist_ok=True)
        PyPath.write_text('# stub\n', encoding='utf-8')
        os.utime(PyPath, (PySeconds, PySeconds))
        Stem = PyPath.stem
        CacheDir = PyPath.parent / '__pycache__'
        CacheDir.mkdir(exist_ok=True)
        PycPath = CacheDir / f'{Stem}.cpython-312.pyc'
        PycPath.write_bytes(b'\x00' * 16)
        os.utime(PycPath, (PycSeconds, PycSeconds))


class StalePycProbeTest(unittest.TestCase):

    # directive: transcode-flow-canonical
    def test_clean_tree_returns_zero(self):
        Script = _LoadProbeScript()
        with tempfile.TemporaryDirectory() as Tmp:
            Root = Path(Tmp)
            Now = time.time()
            _MakeSourceTree(Root, [
                ('Features/Foo/Bar.py', Now - 100, Now - 50),
                ('Core/Baz.py', Now - 100, Now - 100),
            ])
            R = subprocess.run(
                [sys.executable, '-c', Script, str(Root)],
                capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(R.returncode, 0, f'stdout={R.stdout} stderr={R.stderr}')
            self.assertIn('STALE_PYC_COUNT=0', R.stdout)

    # directive: transcode-flow-canonical
    def test_stale_pyc_returns_two_and_names_file(self):
        Script = _LoadProbeScript()
        with tempfile.TemporaryDirectory() as Tmp:
            Root = Path(Tmp)
            Now = time.time()
            _MakeSourceTree(Root, [
                ('Features/Foo/Bar.py', Now - 10, Now - 100),
                ('Core/Baz.py', Now - 100, Now - 100),
            ])
            R = subprocess.run(
                [sys.executable, '-c', Script, str(Root)],
                capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(R.returncode, 2, f'stdout={R.stdout} stderr={R.stderr}')
            self.assertIn('STALE_PYC_COUNT=1', R.stdout)
            self.assertIn('STALE=', R.stdout)
            self.assertIn('Bar.cpython-312.pyc', R.stdout)

    # directive: transcode-flow-canonical
    def test_missing_source_ignored(self):
        Script = _LoadProbeScript()
        with tempfile.TemporaryDirectory() as Tmp:
            Root = Path(Tmp)
            Now = time.time()
            CacheDir = Root / 'Features' / 'Foo' / '__pycache__'
            CacheDir.mkdir(parents=True)
            Orphan = CacheDir / 'Orphan.cpython-312.pyc'
            Orphan.write_bytes(b'\x00' * 16)
            os.utime(Orphan, (Now - 200, Now - 200))
            R = subprocess.run(
                [sys.executable, '-c', Script, str(Root)],
                capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(R.returncode, 0, f'stdout={R.stdout} stderr={R.stderr}')
            self.assertIn('STALE_PYC_COUNT=0', R.stdout)


if __name__ == '__main__':
    unittest.main()
