#!/usr/bin/env python3

import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path


CHECKER = Path(__file__).with_name("icm_check.py")


class CheckerTests(unittest.TestCase):
    def make_workspace(self, root: Path, *, stale: bool = False) -> None:
        (root / "stages/01_research").mkdir(parents=True)
        (root / "runs/2026-08-25-demo/01_research/output").mkdir(parents=True)
        (root / "AGENTS.md").write_text("# Demo\n\nSee [pipeline](CONTEXT.md).\n")
        (root / "CONTEXT.md").write_text("# Demo pipeline\n")
        (root / "icm.yaml").write_text(
            "icm_version: 1\nform: pipeline\nentrypoint: AGENTS.md\n"
            "run_policy: isolated\nhuman_gate: required\nmax_entry_lines: 60\n"
        )
        (root / "stages/01_research/CONTEXT.md").write_text(
            "# 01_research\n\nContract version: 1\nGate: required\n\n"
            "## Inputs\n\n- Working (this run): input.md\n\n"
            "## Process\n\n1. Read.\n\n## Outputs\n\n- result.md\n\n"
            "## Human check\n\nVerify it.\n"
        )
        source = root / "stages/01_research/input.md"
        source.write_text("source\n")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        (root / "runs/2026-08-25-demo/RUN.md").write_text(
            "---\nicm_run: 1\nrun_id: 2026-08-25-demo\nstatus: complete\n"
            "contract_version: 1\ncreated_at: 2026-08-25T10:00:00Z\n"
            "completed_at: 2026-08-25T11:00:00Z\ncurrent_stage: 01_research\n---\n# Run\n"
        )
        artifact = root / "runs/2026-08-25-demo/01_research/output/result.md"
        artifact.write_text(
            "---\nicm_artifact: 1\nrun_id: 2026-08-25-demo\nstage: 01_research\n"
            "status: approved\ncontract_version: 1\ncreated_at: 2026-08-25T10:30:00Z\n"
            "approved_at: 2026-08-25T10:45:00Z\ninputs:\n"
            f"  - path: ../../../../stages/01_research/input.md\n    sha256: {digest}\n"
            "---\n# Result\n"
        )
        if stale:
            source.write_text("changed\n")

    def run_checker(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(CHECKER), str(root), *args],
            text=True, capture_output=True, check=False,
        )

    def test_valid_isolated_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_workspace(root)
            result = self.run_checker(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("0 error(s), 0 warning(s)", result.stdout)

    def test_stale_artifact_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_workspace(root, stale=True)
            result = self.run_checker(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("ERROR artifact.stale", result.stdout)

    def test_broken_link_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_workspace(root)
            (root / "AGENTS.md").write_text("[missing](nope.md)\n")
            result = self.run_checker(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("ERROR link.broken", result.stdout)

    def test_strict_promotes_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_workspace(root)
            artifact = root / "runs/2026-08-25-demo/01_research/output/result.md"
            artifact.write_text("# No metadata\n")
            result = self.run_checker(root, "--strict")
            self.assertEqual(result.returncode, 1)
            self.assertIn("WARN artifact.metadata", result.stdout)

    def test_entrypoint_drift_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_workspace(root)
            (root / "CLAUDE.md").write_text("# Different hand-maintained entry\n")
            result = self.run_checker(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("ERROR entry.drift", result.stdout)

    def test_auto_gate_requires_risk_based_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_workspace(root)
            contract = root / "stages/01_research/CONTEXT.md"
            contract.write_text(contract.read_text().replace("Gate: required", "Gate: auto"))
            result = self.run_checker(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("ERROR contract.auto-gate", result.stdout)


if __name__ == "__main__":
    unittest.main()
