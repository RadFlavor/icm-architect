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

    def test_terminal_none_gate_allowed_under_required_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_workspace(root)
            contract = root / "stages/01_research/CONTEXT.md"
            contract.write_text(contract.read_text().replace("Gate: required", "Gate: none"))
            result = self.run_checker(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_complete_run_rejects_draft_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_workspace(root)
            artifact = root / "runs/2026-08-25-demo/01_research/output/result.md"
            artifact.write_text(artifact.read_text().replace("status: approved", "status: draft"))
            result = self.run_checker(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("ERROR run.unapproved", result.stdout)

    def test_artifact_identity_must_match_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_workspace(root)
            artifact = root / "runs/2026-08-25-demo/01_research/output/result.md"
            artifact.write_text(artifact.read_text().replace("stage: 01_research", "stage: 02_wrong"))
            result = self.run_checker(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("ERROR artifact.stage", result.stdout)

    def test_valid_exception_is_not_treated_as_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_workspace(root)
            exceptions = root / "runs/2026-08-25-demo/exceptions"
            exceptions.mkdir()
            (exceptions / "retry.md").write_text(
                "---\nicm_exception: 1\nrun_id: 2026-08-25-demo\nstage: 01_research\n"
                "type: retry\nstatus: resolved\nowner: Rad\ncreated_at: 2026-08-25T10:00:00Z\n"
                "resolved_at: 2026-08-25T10:10:00Z\n---\n# Retry\n"
            )
            result = self.run_checker(root, "--strict")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_binary_sidecar_is_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_workspace(root)
            output = root / "runs/2026-08-25-demo/01_research/output"
            (output / "clip.mp4").write_bytes(b"video")
            (output / "clip.mp4.meta.yaml").write_text(
                "icm_artifact: 1\nrun_id: 2026-08-25-demo\nstage: 01_research\n"
                "status: approved\ncontract_version: 1\ncreated_at: 2026-08-25T10:30:00Z\n"
                "approved_at: 2026-08-25T10:45:00Z\ninputs: []\n"
            )
            result = self.run_checker(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            (output / "clip.mp4.meta.yaml").write_text(
                (output / "clip.mp4.meta.yaml").read_text().replace("stage: 01_research", "stage: wrong")
            )
            result = self.run_checker(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("ERROR artifact.stage", result.stdout)

    def test_binary_artifact_requires_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_workspace(root)
            output = root / "runs/2026-08-25-demo/01_research/output"
            (output / "clip.mp4").write_bytes(b"video")
            result = self.run_checker(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("ERROR sidecar.missing", result.stdout)

    def test_context_budget_is_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_workspace(root)
            manifest = root / "icm.yaml"
            manifest.write_text(manifest.read_text() + "max_context_tokens: 1\n")
            result = self.run_checker(root, "--strict")
            self.assertEqual(result.returncode, 1)
            self.assertIn("WARN context.large", result.stdout)

    def test_invalid_numeric_config_reports_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_workspace(root)
            manifest = root / "icm.yaml"
            manifest.write_text(
                manifest.read_text() + "max_entry_lines: nope\nmax_context_tokens: nope\n"
            )
            result = self.run_checker(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("ERROR manifest.number", result.stdout)
            self.assertNotIn("Traceback", result.stderr)

    def test_complete_run_rejects_open_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_workspace(root)
            exceptions = root / "runs/2026-08-25-demo/exceptions"
            exceptions.mkdir()
            (exceptions / "blocked.md").write_text(
                "---\nicm_exception: 1\nrun_id: 2026-08-25-demo\nstage: 01_research\n"
                "type: blocked\nstatus: open\nowner: Rad\ncreated_at: 2026-08-25T10:00:00Z\n"
                "resolved_at:\n---\n# Blocked\n"
            )
            result = self.run_checker(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("ERROR run.open-exception", result.stdout)


if __name__ == "__main__":
    unittest.main()
