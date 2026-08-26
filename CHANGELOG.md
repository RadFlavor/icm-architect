# Changelog

Notable changes to ICM Architect are recorded here.

## Unreleased

### Added

- A lightweight framework-design guideline: deterministic systems handle reliable, repeatable work; AI handles bounded interpretation and judgment. The 60/30/10 split is a design prompt, not a quota.
- Reliability checker coverage for isolated product paths, required artifact identity and provenance, completed-run approval, binary sidecars, exception records, open exceptions, and approximate context budgets.

### Fixed

- Unified pipeline handoffs under one product root for both single and isolated run policies.
- Prevented valid exception records from being misclassified as artifacts.
- Made checker installation and invocation explicit for generated workspaces.
- Removed contradictory assumptions about optional manifests and canonical entry filenames.

## 2026-08-25 — Reliability layer

### Added

- Dependency-free, read-only `scripts/icm_check.py` validator with strict mode.
- Validation for manifest policy, entrypoint drift and size, stage contracts, declared inputs, relative Markdown links, run state, artifact approval, provenance, and stale input hashes.
- Behavioral tests covering valid isolated runs, stale artifacts, broken links, missing metadata, entrypoint drift, and gate-policy enforcement.
- Optional `icm.yaml` workspace manifest with run, gate, and context-size policies.
- Templates for isolated run manifests, artifact provenance, and explicit exceptions.
- Reliability guidance for run identity, approval state, retries, branches, waivers, blockers, and non-text payloads.

### Changed

- Distinguished artifact presence from approval and freshness.
- Reframed plain text as the control interface while allowing appropriate external or binary payload storage.
- Made human gates configurable for required, risk-based, and terminal or observational work.
- Preferred one canonical, portable entrypoint with generated twins or pointer files.
- Treated the 2,000–8,000-token range as a diagnostic guideline rather than a universal limit.
- Updated pipeline and stage templates to support both single and isolated run policies.
