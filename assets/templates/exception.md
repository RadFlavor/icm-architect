---
icm_exception: 1
run_id: {run-id}
stage: {NN_stage-name}
type: blocked # skip | retry | branch | waiver | blocked
status: open # open | resolved
owner: {decision owner}
created_at: {ISO-8601 timestamp}
resolved_at:
---

# Exception — {short name}

## Reason
{Why normal flow cannot continue.}

## Decision and downstream effect
{What changes, what remains valid, and who approved it.}

## Resolution
{What closes this exception, or the named branch path.}
