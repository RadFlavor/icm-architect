# Reliability layer

Read this when a workspace repeats, has more than one contributor, needs an audit trail, or the user asks to keep an ICM tight. Small one-off workspaces may omit it.

The reliability layer makes five facts explicit without introducing a service or database: workspace policy, run identity, artifact provenance, approval state, and exceptions. The files remain the interface.

## Root manifest

Copy `assets/templates/icm.yaml` to `icm.yaml`. It declares policy; it does not duplicate the routing table.

```yaml
icm_version: 1
form: pipeline
entrypoint: AGENTS.md
run_policy: isolated
human_gate: required
max_entry_lines: 60
max_context_tokens: 8000
```

- `run_policy: single` keeps one current set of outputs and permits overwrite. Use for one-off work or a continuously maintained product.
- `run_policy: isolated` stores every execution under `runs/<run-id>/`. Use when history, reproducibility, or multiple active runs matter.
- `human_gate: required` blocks the next stage until approval. `risk-based` permits a contract to mark a deterministic, reversible stage `gate: auto`. `none` is appropriate only when the workspace has no consequential handoff.

The manifest is intentionally small. If a setting does not change validation or execution, it does not belong here.

## Run identity

For isolated runs, copy `assets/templates/RUN.md` to `runs/<run-id>/RUN.md`. Use a sortable id such as `2026-08-25-client-slug`; add a counter when two runs can share a day and slug.

Each run manifest records:

- lifecycle status: `planned | active | blocked | complete | archived`
- the contract version or Git commit used
- creation and completion times
- current stage
- declared exceptions

Stage outputs live at `runs/<run-id>/<NN_stage>/output/`. Contracts may use `{run}` as the run-id placeholder. A run id must be selected before execution; never infer “latest” when writing.

For `single`, outputs may remain at `stages/<NN_stage>/output/`. Provenance is still useful when stale work would be costly.

## Artifact provenance and approval

Use YAML frontmatter on consequential Markdown outputs; use a same-basename `.meta.yaml` sidecar for binary or machine-owned artifacts.

```yaml
---
icm_artifact: 1
run_id: 2026-08-25-client-slug
stage: 02_script
status: approved
contract_version: 3
created_at: 2026-08-25T19:40:00-04:00
approved_at: 2026-08-25T20:05:00-04:00
inputs:
  - path: ../01_research/output/research.md
    sha256: "..."
---
```

Artifact status is `draft | ready-for-review | approved | rejected | superseded`. Existence means only “present”; approval means the declared gate passed. When a required input's current SHA-256 differs from the recorded hash, the artifact is stale regardless of status.

For low-risk work, `inputs` may record `path` without a hash; the checker reports weaker provenance rather than inventing certainty.

## Gates

Each stage contract declares one of:

- `Gate: required` — a person approves the output.
- `Gate: auto` — allowed only when root policy is `risk-based`; the contract states why the operation is deterministic, reversible, and low consequence.
- `Gate: none` — terminal or observational step with no downstream consumer.

Human checks remain concrete acts. A gate is state; the check says how a person decides it.

## Exceptions, retries, and branches

Normal flow stays visible through numbering. Do not encode exceptional control flow by renaming folders or silently skipping outputs.

Copy `assets/templates/exception.md` into the run's `exceptions/` folder for a skip, retry, branch, waiver, or blocked dependency. It records the affected stage, reason, decision owner, downstream consequence, and resolution. A branch writes to a named folder inside the run; it does not mutate the factory contract unless the branch becomes the normal process.

## Non-text payloads

Markdown, YAML, and JSON are the preferred control interfaces, not a ban on appropriate storage. Large tables, media, databases, APIs, and Parquet files may hold payloads. Give each an adjacent Markdown description or `.meta.yaml` sidecar that names ownership, schema or interface, provenance, and how the current stage accesses it.

## Checker

Run:

```bash
python3 scripts/icm_check.py <workspace>
python3 scripts/icm_check.py <workspace> --strict
```

The checker is read-only and dependency-free. It checks routing size and drift, manifest values, stage contracts, declared input paths, broken relative Markdown links, run manifests, artifact metadata, approvals, and input hashes. It cannot prove that two prose files duplicate the same fact or that a human made a sound judgment; those remain walk-test questions.

Exit codes: `0` no errors, `1` structural or state errors, `2` invalid invocation. Warnings become errors under `--strict`.
