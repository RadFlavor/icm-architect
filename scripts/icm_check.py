#!/usr/bin/env python3
"""Read-only, dependency-free structural checker for ICM workspaces."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ALLOWED_FORMS = {
    "pipeline", "umbrella", "record-library", "knowledge-bundle",
    "context-map", "system-map",
}
ALLOWED_RUN_POLICIES = {"single", "isolated"}
ALLOWED_GATES = {"required", "risk-based", "none"}
ALLOWED_RUN_STATUS = {"planned", "active", "blocked", "complete", "archived"}
ALLOWED_ARTIFACT_STATUS = {
    "draft", "ready-for-review", "approved", "rejected", "superseded",
}
ALLOWED_EXCEPTION_TYPES = {"skip", "retry", "branch", "waiver", "blocked"}
ALLOWED_EXCEPTION_STATUS = {"open", "resolved"}
STAGE_RE = re.compile(r"^\d{2}[_-][a-z0-9][a-z0-9-]*$")
LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


@dataclass
class Finding:
    level: str
    code: str
    path: Path
    message: str


class Check:
    def __init__(self, root: Path, strict: bool = False) -> None:
        self.root = root.resolve()
        self.strict = strict
        self.findings: list[Finding] = []
        self.run_artifacts: dict[str, list[str]] = {}

    def add(self, level: str, code: str, path: Path, message: str) -> None:
        self.findings.append(Finding(level, code, path, message))

    def error(self, code: str, path: Path, message: str) -> None:
        self.add("ERROR", code, path, message)

    def warn(self, code: str, path: Path, message: str) -> None:
        self.add("WARN", code, path, message)

    def rel(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.root)) or "."
        except ValueError:
            return str(path)

    def run(self) -> int:
        if not self.root.is_dir():
            self.error("root.missing", self.root, "workspace is not a directory")
            return self.report()

        manifest = self.check_manifest()
        self.check_entrypoints(manifest)
        self.check_stages(manifest)
        self.check_links()
        self.check_artifacts(manifest)
        self.check_runs(manifest)
        return self.report()

    def check_manifest(self) -> dict[str, str]:
        path = self.root / "icm.yaml"
        if not path.exists():
            self.warn(
                "manifest.missing", path,
                "no icm.yaml; reliability checks use conservative defaults",
            )
            return {
                "entrypoint": "",
                "run_policy": "single",
                "human_gate": "required",
                "max_entry_lines": "60",
            }

        data = parse_flat_yaml(path)
        required = {"icm_version", "form", "entrypoint", "run_policy", "human_gate"}
        for key in sorted(required - data.keys()):
            self.error("manifest.required", path, f"missing required key: {key}")
        if data.get("icm_version") != "1":
            self.error("manifest.version", path, "icm_version must be 1")
        if data.get("form") not in ALLOWED_FORMS:
            self.error("manifest.form", path, f"unknown form: {data.get('form', '')}")
        if data.get("run_policy") not in ALLOWED_RUN_POLICIES:
            self.error("manifest.run-policy", path, "run_policy must be single or isolated")
        if data.get("human_gate") not in ALLOWED_GATES:
            self.error("manifest.gate", path, "human_gate must be required, risk-based, or none")
        for key in ("max_entry_lines", "max_context_tokens"):
            if key in data and not positive_int(data[key]):
                self.error("manifest.number", path, f"{key} must be a positive integer")
        return data

    def check_entrypoints(self, manifest: dict[str, str]) -> None:
        candidates = [self.root / name for name in ("AGENTS.md", "CLAUDE.md", "routing.md")]
        existing = [path for path in candidates if path.exists()]
        declared = manifest.get("entrypoint", "")
        entry = self.root / declared if declared else (existing[0] if existing else self.root / "AGENTS.md")
        if not entry.exists():
            self.error("entry.missing", entry, "declared or conventional entrypoint does not exist")
            return

        if not inside(entry.resolve(), self.root):
            self.error("entry.escape", entry, "entrypoint must stay inside the workspace")
            return
        max_lines = config_int(manifest, "max_entry_lines", 60)
        count = len(entry.read_text(encoding="utf-8").splitlines())
        if count > max_lines:
            self.warn("entry.large", entry, f"{count} lines exceeds configured maximum {max_lines}")

        if len(existing) > 1:
            contents = {path.read_bytes() for path in existing}
            if len(contents) > 1 and not all(is_pointer(path) for path in existing if path != entry):
                self.error(
                    "entry.drift", entry,
                    "multiple entry files differ; generate twins or make non-canonical files pointers",
                )

    def stage_dirs(self) -> list[Path]:
        base = self.root / "stages"
        if base.is_dir():
            return sorted(path for path in base.iterdir() if path.is_dir() and STAGE_RE.match(path.name))
        return sorted(path for path in self.root.iterdir() if path.is_dir() and STAGE_RE.match(path.name))

    def check_stages(self, manifest: dict[str, str]) -> None:
        stages = self.stage_dirs()
        if manifest.get("form") == "pipeline" and not stages:
            self.error("stage.none", self.root, "pipeline declares no numbered stage folders")
        seen_numbers: set[str] = set()
        for stage in stages:
            number = stage.name[:2]
            if number in seen_numbers:
                self.error("stage.number", stage, f"duplicate stage ordinal {number}")
            seen_numbers.add(number)
            contract = stage / "CONTEXT.md"
            if not contract.exists():
                self.error("contract.missing", contract, "numbered stage has no CONTEXT.md")
                continue
            text = contract.read_text(encoding="utf-8")
            for heading in ("## Inputs", "## Process", "## Outputs"):
                if heading not in text:
                    self.error("contract.section", contract, f"missing {heading}")
            if "## Human check" not in text and manifest.get("human_gate") != "none":
                self.error("contract.human-check", contract, "missing ## Human check")
            gate = parse_contract_value(text, "Gate")
            if manifest.get("human_gate") == "risk-based" and gate == "auto":
                if not re.search(r"(?im)^Auto gate reason:\s*\S", text):
                    self.error("contract.auto-gate", contract, "auto gate needs an Auto gate reason")
            elif gate == "auto" and manifest.get("human_gate") != "risk-based":
                self.error("contract.auto-gate", contract, "auto gate requires human_gate: risk-based")
            elif manifest.get("human_gate") == "required" and gate not in {"required", "none", ""}:
                self.error("contract.gate", contract, "root policy requires a required gate")
            self.check_declared_paths(contract, text)
            self.check_context_budget(contract, text, manifest)

    def check_declared_paths(self, contract: Path, text: str) -> None:
        for value in declared_input_paths(text):
            candidate = (contract.parent / value).resolve()
            if not inside(candidate, self.root):
                self.error("input.escape", contract, f"input escapes workspace: {value}")
            elif not candidate.exists():
                self.warn("input.missing", contract, f"declared input does not exist: {value}")

    def check_context_budget(self, contract: Path, text: str, manifest: dict[str, str]) -> None:
        limit = config_int(manifest, "max_context_tokens", 8000)
        entry_name = manifest.get("entrypoint", "")
        entry = self.root / entry_name if entry_name else None
        characters = len(text)
        if entry and entry.is_file():
            characters += len(entry.read_text(encoding="utf-8"))
        for value in declared_input_paths(text):
            candidate = (contract.parent / value).resolve()
            if candidate.is_file() and candidate.suffix.lower() in {".md", ".txt", ".json", ".yaml", ".yml", ".csv"}:
                try:
                    characters += len(candidate.read_text(encoding="utf-8"))
                except UnicodeDecodeError:
                    continue
        estimate = (characters + 3) // 4
        if estimate > limit:
            self.warn(
                "context.large", contract,
                f"estimated context {estimate} tokens exceeds configured maximum {limit}",
            )

    def check_links(self) -> None:
        for path in markdown_files(self.root):
            text = path.read_text(encoding="utf-8")
            for target in LINK_RE.findall(text):
                target = target.strip().split("#", 1)[0]
                if not target or "://" in target or target.startswith(("mailto:", "#")):
                    continue
                candidate = (path.parent / target).resolve()
                if not inside(candidate, self.root):
                    self.warn("link.escape", path, f"relative link leaves workspace: {target}")
                elif not candidate.exists():
                    self.error("link.broken", path, f"broken relative Markdown link: {target}")

    def check_runs(self, manifest: dict[str, str]) -> None:
        if manifest.get("run_policy") != "isolated":
            return
        runs = self.root / "runs"
        if not runs.is_dir():
            self.error("runs.missing", runs, "isolated policy requires runs/")
            return
        for run_dir in sorted(path for path in runs.iterdir() if path.is_dir()):
            run_file = run_dir / "RUN.md"
            if not run_file.exists():
                self.error("run.manifest", run_file, "run folder has no RUN.md")
                continue
            meta, _ = parse_frontmatter(run_file)
            if meta.get("icm_run") != "1":
                self.error("run.version", run_file, "icm_run must be 1")
            if meta.get("run_id") != run_dir.name:
                self.error("run.id", run_file, "run_id must match its folder name")
            if meta.get("status") not in ALLOWED_RUN_STATUS:
                self.error("run.status", run_file, "invalid run status")
            if meta.get("status") == "complete" and not meta.get("completed_at"):
                self.error("run.completed-at", run_file, "complete run needs completed_at")
            has_open_exception = self.check_exceptions(run_dir)
            for key in ("run_id", "status", "contract_version", "created_at", "current_stage"):
                if not meta.get(key):
                    self.error("run.required", run_file, f"missing required metadata: {key}")
            if meta.get("status") == "complete" and has_open_exception:
                self.error("run.open-exception", run_file, "complete run contains an open exception")
            if meta.get("status") == "complete" and manifest.get("human_gate") != "none":
                statuses = self.run_artifacts.get(run_dir.name, [])
                if not statuses:
                    self.error("run.no-artifacts", run_file, "complete run has no validated artifacts")
                elif any(status not in {"approved", "superseded"} for status in statuses):
                    self.error("run.unapproved", run_file, "complete run contains unapproved artifacts")

    def check_exceptions(self, run_dir: Path) -> bool:
        base = run_dir / "exceptions"
        if not base.is_dir():
            return False
        has_open = False
        for path in markdown_files(base):
            meta, _ = parse_frontmatter(path)
            required = {"icm_exception", "run_id", "stage", "type", "status", "owner", "created_at"}
            for key in sorted(required):
                if not meta.get(key):
                    self.error("exception.required", path, f"missing required metadata: {key}")
            if meta.get("icm_exception") != "1":
                self.error("exception.version", path, "icm_exception must be 1")
            if meta.get("run_id") != run_dir.name:
                self.error("exception.run-id", path, "run_id must match its enclosing run")
            if meta.get("type") not in ALLOWED_EXCEPTION_TYPES:
                self.error("exception.type", path, "invalid exception type")
            if meta.get("status") not in ALLOWED_EXCEPTION_STATUS:
                self.error("exception.status", path, "invalid exception status")
            if meta.get("status") == "open":
                has_open = True
            if meta.get("status") == "resolved" and not meta.get("resolved_at"):
                self.error("exception.resolved-at", path, "resolved exception needs resolved_at")
        return has_open

    def check_artifacts(self, manifest: dict[str, str]) -> None:
        locations: list[tuple[Path, str, str]] = []
        if manifest.get("run_policy") == "isolated" and (self.root / "runs").exists():
            for run_dir in sorted(path for path in (self.root / "runs").iterdir() if path.is_dir()):
                for stage_dir in sorted(path for path in run_dir.iterdir() if path.is_dir() and STAGE_RE.match(path.name)):
                    locations.append((stage_dir / "output", run_dir.name, stage_dir.name))
        else:
            locations.extend((stage / "output", "single", stage.name) for stage in self.stage_dirs())

        for base, expected_run, expected_stage in locations:
            if not base.exists():
                continue
            for payload in sorted(path for path in base.rglob("*") if path.is_file()):
                if payload.suffix.lower() == ".md" or payload.name.endswith(".meta.yaml") or payload.name == ".gitkeep":
                    continue
                sidecar = payload.with_name(payload.name + ".meta.yaml")
                if not sidecar.is_file():
                    self.error("sidecar.missing", payload, f"non-Markdown artifact needs sidecar: {sidecar.name}")
            artifacts = markdown_files(base) + sorted(base.rglob("*.meta.yaml"))
            for path in artifacts:
                is_sidecar = path.name.endswith(".meta.yaml")
                if is_sidecar:
                    payload = path.with_name(path.name[:-10])
                    if not payload.is_file():
                        self.error("sidecar.payload", path, f"sidecar payload does not exist: {payload.name}")
                    meta = parse_flat_yaml(path)
                else:
                    meta, _ = parse_frontmatter(path)
                if not meta:
                    self.warn("artifact.metadata", path, "output has no artifact frontmatter")
                    continue
                if meta.get("icm_artifact") != "1":
                    self.warn("artifact.version", path, "output metadata lacks icm_artifact: 1")
                    continue
                status = meta.get("status", "")
                for key in ("run_id", "stage", "status", "contract_version", "created_at"):
                    if not meta.get(key):
                        self.error("artifact.required", path, f"missing required metadata: {key}")
                if meta.get("run_id") != expected_run:
                    self.error("artifact.run-id", path, f"run_id must be {expected_run}")
                if meta.get("stage") != expected_stage:
                    self.error("artifact.stage", path, f"stage must be {expected_stage}")
                if status not in ALLOWED_ARTIFACT_STATUS:
                    self.error("artifact.status", path, f"invalid artifact status: {status}")
                if status == "approved" and not meta.get("approved_at"):
                    self.error("artifact.approved-at", path, "approved artifact needs approved_at")
                if manifest.get("human_gate") == "required" and status == "ready-for-review":
                    self.warn("artifact.awaiting", path, "required gate is awaiting approval")
                self.run_artifacts.setdefault(expected_run, []).append(status)
                self.check_input_hashes(path, is_sidecar)

    def check_input_hashes(self, artifact: Path, is_sidecar: bool = False) -> None:
        for item in parse_input_items(artifact, frontmatter=not is_sidecar):
            raw_path = item.get("path", "")
            if not raw_path or any(mark in raw_path for mark in ("{", "}")):
                continue
            source = (artifact.parent / raw_path).resolve()
            if not inside(source, self.root):
                self.error("artifact.input-escape", artifact, f"input escapes workspace: {raw_path}")
                continue
            if not source.is_file():
                self.error("artifact.input-missing", artifact, f"recorded input missing: {raw_path}")
                continue
            expected = item.get("sha256", "").strip('"\'')
            if not expected:
                self.warn("artifact.weak-provenance", artifact, f"input has no SHA-256: {raw_path}")
                continue
            actual = hashlib.sha256(source.read_bytes()).hexdigest()
            if actual != expected:
                self.error("artifact.stale", artifact, f"input changed since artifact creation: {raw_path}")

    def report(self) -> int:
        order = {"ERROR": 0, "WARN": 1}
        for finding in sorted(self.findings, key=lambda f: (order[f.level], str(f.path), f.code)):
            print(f"{finding.level} {finding.code} {self.rel(finding.path)}: {finding.message}")
        errors = sum(item.level == "ERROR" for item in self.findings)
        warnings = sum(item.level == "WARN" for item in self.findings)
        print(f"ICM check: {errors} error(s), {warnings} warning(s)")
        return 1 if errors or (self.strict and warnings) else 0


def positive_int(value: str) -> bool:
    try:
        return int(value) > 0
    except ValueError:
        return False


def config_int(data: dict[str, str], key: str, default: int) -> int:
    value = data.get(key, str(default))
    return int(value) if positive_int(value) else default


def strip_comment(value: str) -> str:
    return value.split(" #", 1)[0].strip().strip("\"'")


def parse_flat_yaml(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw or raw[0].isspace() or raw.lstrip().startswith("#") or ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        result[key.strip()] = strip_comment(value)
    return result


def parse_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        return {}, text
    data: dict[str, str] = {}
    for raw in text[4:end].splitlines():
        if raw and not raw[0].isspace() and ":" in raw:
            key, value = raw.split(":", 1)
            data[key.strip()] = strip_comment(value)
    return data, text[end + 4:]


def parse_input_items(path: Path, *, frontmatter: bool = True) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    if frontmatter:
        if not text.startswith("---\n"):
            return []
        end = text.find("\n---", 4)
        if end < 0:
            return []
        lines = text[4:end].splitlines()
    else:
        lines = text.splitlines()
    items: list[dict[str, str]] = []
    in_inputs = False
    current: dict[str, str] | None = None
    for raw in lines:
        if raw == "inputs:":
            in_inputs = True
            continue
        if in_inputs and raw and not raw[0].isspace():
            break
        if not in_inputs:
            continue
        match = re.match(r"\s*-\s+path:\s*(.+)$", raw)
        if match:
            current = {"path": strip_comment(match.group(1))}
            items.append(current)
            continue
        match = re.match(r"\s+sha256:\s*(.*)$", raw)
        if match and current is not None:
            current["sha256"] = strip_comment(match.group(1))
    return items


def declared_input_paths(text: str) -> list[str]:
    paths: list[str] = []
    for raw in section_text(text, "Inputs").splitlines():
        if not raw.lstrip().startswith("-") or ":" not in raw:
            continue
        value = raw.split(":", 1)[-1].strip().strip("`\"")
        value = value.split(" #", 1)[0].strip()
        if value and not any(mark in value for mark in ("{", "}", "*")):
            paths.append(value)
    return paths


def parse_contract_value(text: str, key: str) -> str:
    match = re.search(rf"(?im)^{re.escape(key)}:\s*([^\s{{]+)", text)
    return match.group(1).lower() if match else ""


def section_text(text: str, heading: str) -> str:
    match = re.search(rf"(?ms)^## {re.escape(heading)}\s*$\n(.*?)(?=^## |\Z)", text)
    return match.group(1) if match else ""


def is_pointer(path: Path) -> bool:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return len(lines) <= 3 and any(name in " ".join(lines) for name in ("AGENTS.md", "CLAUDE.md", "routing.md"))


def inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def markdown_files(root: Path):
    return sorted(
        path for path in root.rglob("*.md")
        if ".git" not in path.parts and "_archive" not in path.parts
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    args = parser.parse_args(argv)
    return Check(args.workspace, args.strict).run()


if __name__ == "__main__":
    sys.exit(main())
