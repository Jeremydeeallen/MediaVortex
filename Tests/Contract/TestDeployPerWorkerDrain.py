# see .claude/rules/worker-deploy-drain.md
import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent


class TestDeployPerWorkerDrain(unittest.TestCase):

    def test_C1_rule_file_exists(self):
        RulePath = ROOT / ".claude" / "rules" / "worker-deploy-drain.md"
        self.assertTrue(RulePath.exists(), f"rule missing: {RulePath}")
        Content = RulePath.read_text(encoding="utf-8")
        for D in ("D1.", "D2.", "D3.", "D4.", "D5.", "D6."):
            self.assertIn(D, Content, f"rule missing {D}")
        self.assertIn("pause -> drain -> deploy -> back Online", Content)

    def test_C20_deploy_worker_source_prints_step_timings(self):
        Src = (ROOT / "deploy" / "deploy-worker.py").read_text(encoding="utf-8")
        for Marker in ("[1/6] pause:", "[2/6] drain:", "[5/6] verify:", "[6/6] online:", "back Online in"):
            self.assertIn(Marker, Src, f"deploy-worker.py missing timing marker: {Marker!r}")
        self.assertIn("flush=True", Src)

    def test_C2_no_optout_flags_in_deploy_tree(self):
        Hits = []
        DeployDir = ROOT / "deploy"
        for FilePath in DeployDir.rglob("*.py"):
            Text = FilePath.read_text(encoding="utf-8", errors="ignore")
            for Bad in ("--no-drain", "no_drain", "--skip-drain", "skip_drain"):
                if Bad in Text:
                    Hits.append(f"{FilePath.name}: {Bad}")
        self.assertEqual(Hits, [], f"opt-out flags found: {Hits}")

    def test_C3_feature_doc_reflects_golden_standard(self):
        DocPath = ROOT / "deploy" / "worker-deploy.feature.md"
        self.assertTrue(DocPath.exists())
        Content = DocPath.read_text(encoding="utf-8")
        self.assertIn("deploy-worker.py", Content)
        self.assertIn("pause -> drain -> deploy -> back Online", Content)
        self.assertNotIn("--no-drain", Content)

    def test_C4_deploy_worker_help_exits_zero_and_names_no_bypass(self):
        Script = ROOT / "deploy" / "deploy-worker.py"
        self.assertTrue(Script.exists())
        R = subprocess.run(
            [sys.executable, str(Script), "--help"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(R.returncode, 0, f"stderr={R.stderr}")
        Help = R.stdout.lower()
        for Bad in ("--no-drain", "--skip-drain", "--force"):
            self.assertNotIn(Bad, Help, f"help mentions bypass flag: {Bad}")


if __name__ == "__main__":
    unittest.main()
