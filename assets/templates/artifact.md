---
icm_artifact: 1
run_id: {run-id or single}
stage: {NN_stage-name}
status: draft # draft | ready-for-review | approved | rejected | superseded
contract_version: {git commit or version}
created_at: {ISO-8601 timestamp}
approved_at:
inputs:
  - path: {relative input path}
    sha256: {optional hash}
---

# {Artifact name}

{Artifact content.}
