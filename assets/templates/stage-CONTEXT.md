# {NN}_{stage-name} — {the job in five words}

One job: {the single thing this stage does}.

Contract version: {integer or Git commit}
Gate: required {or auto / none, according to root icm.yaml}

## Inputs
- Single policy working input: ../{NN-1}_{prev-stage}/output/{file}
- Isolated policy working input: ../../runs/{run}/{NN-1}_{prev-stage}/output/{file}
- Reference (every run): ../../_shared/{rules-file}.md
- Reference (every run): references/{stage-specific-guide}.md

Do NOT load: {anything an eager agent would wrongly pull in — other stages' references, prior runs, the whole _shared folder}.

## Process
1. {Read the inputs.}
2. {Transform, following the reference constraints.}
3. {Hard limits worth restating: length, count, format.}

## Outputs
- Single-run policy: {artifact}.md → output/
- Isolated-run policy: {artifact}.md → ../../runs/{run}/{NN}_{stage-name}/output/
- Consequential outputs use artifact frontmatter or a `.meta.yaml` sidecar.

Keep only the working-input and output lines for the policy selected in `icm.yaml`. Without `icm.yaml`, keep the single-policy lines.

## Human check
{One concrete act: read it aloud / verify the numbers against X / confirm the order survived. Edit the output in place — the next stage reads whatever is here.}

## Exceptions
Under `isolated`, record skips, retries, branches, waivers, or blockers in `runs/{run}/exceptions/`. Never silently bypass this contract.
