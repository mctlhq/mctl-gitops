# Accept optional work_item_id and execution_id on the investigate CWFT

## Context

`mctlhq/mctl-agents#267` resumes the issue-investigator from a canonical
`WorkItem` rather than from a bare issue URL. Its proposal (already committed
here at `platform-gitops/agents-state/mctl-agents/proposals/issue-267-feat-work-context-resume-investigator-fr/`)
adds `--work-item-id` and `--execution-id` to
`orchestrator/run_issue_investigator.py` (task 10 of that proposal's
`tasks.md`) and threads a `WorkContextRef` through `investigate()`. Those
flags are only reachable if something can pass them, and the only production
caller is the Argo `ClusterWorkflowTemplate` `mctl-agents-investigate` at
`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml`.
That template today declares exactly three workflow parameters — `issue_url`,
`agent_image`, `agent_version` — and builds its command line as
`python -m orchestrator.run_issue_investigator --issue-url "$WORKFLOW_ISSUE_URL"`
with nothing else appendable (lines 331-342). So the two identifiers have no
route from a submit to the script.

This proposal closes that gap and nothing else: two new optional workflow
parameters, bound as environment variables, conditionally appended to the
argv the template already builds. It is a cross-repo prerequisite, deliberately
inert on its own — until a caller supplies a value, the command line the
container runs is byte-identical to today's. The change is small but
sequencing-sensitive in both directions: it cannot be exercised until
`mctlhq/mctl-api#335` lets the operation registry carry the two parameters
through a submit, and it must not be exercised until the pinned `agent_image`
contains a `run_issue_investigator.py` that recognises the flags, because
argparse rejects an unknown flag and fails the run.

## User stories

- AS the dev-loop control plane I WANT to pass a canonical `work_item_id` and
  `execution_id` on an investigate submit SO THAT the investigator can bind its
  run to a `WorkItem` and correlate its execution instead of re-deriving
  identity from the issue URL.
- AS a platform operator I WANT a submit that omits both identifiers to behave
  exactly as it does today SO THAT every existing caller (`mctl_trigger_issue`,
  a hand-submitted `Workflow`, the DevLoopWorkflow) keeps working unchanged
  while the consumer lands.
- AS a platform reviewer I WANT the two identifiers bound through `env:` and
  appended via `set --` SO THAT a crafted value cannot be spliced into the
  shell of a pod that holds `GITHUB_TOKEN` and a scratch clone.
- AS an on-call engineer I WANT the resolved command line echoed before the
  investigator runs SO THAT the archived step log shows whether the
  identifiers actually reached the script.

## Acceptance criteria (EARS)

- WHEN a workflow is submitted against `mctl-agents-investigate` carrying
  non-empty `work_item_id` and `execution_id` THE SYSTEM SHALL invoke
  `python -m orchestrator.run_issue_investigator --issue-url <url>
  --work-item-id <work_item_id> --execution-id <execution_id>`.
- WHEN a workflow is submitted carrying neither `work_item_id` nor
  `execution_id` THE SYSTEM SHALL invoke
  `python -m orchestrator.run_issue_investigator --issue-url <url>` with no
  additional flags — the argv unchanged from the current template.
- WHEN exactly one of the two parameters is non-empty THE SYSTEM SHALL append
  only that one flag and omit the other entirely.
- IF a parameter is supplied as the empty string THEN THE SYSTEM SHALL treat it
  as absent and omit its flag, because Argo cannot distinguish an omitted
  parameter from one defaulted to `""`.
- WHILE neither parameter is declared on a submit THE SYSTEM SHALL resolve both
  to the empty string and SHALL NOT substitute any generated, derived, or
  placeholder identifier.
- WHEN either parameter is referenced inside the container's shell body THE
  SYSTEM SHALL read it from an environment variable
  (`WORKFLOW_WORK_ITEM_ID` / `WORKFLOW_EXECUTION_ID`) and SHALL NOT interpolate
  `{{workflow.parameters.*}}` into that shell text, so that
  `scripts/validate-shell-param-interpolation.py` passes without a new
  `BASELINE` or `CONSTRAINED` entry.
- IF a supplied value contains shell metacharacters (for example
  `; rm -rf /` or an embedded quote) THEN THE SYSTEM SHALL pass it to the
  script as one quoted argv token and SHALL NOT execute any part of it.
- WHILE the primary attempt has failed and the account-2 fallback runs THE
  SYSTEM SHALL pass the same two identifier values to the fallback attempt,
  because both attempts share the `run-investigator` template and the caller
  minted exactly one pair.
- WHEN the template builds its argv THE SYSTEM SHALL echo the resolved command
  line through the existing `printf '→' / printf ' %s' "$@"` block before
  running it.
- WHEN `scripts/validate-shell-param-interpolation.py`, `yamllint`, and
  `kubeconform` run over the edited template in `validate-manifests.yml` THE
  SYSTEM SHALL pass all three with no new suppression.

## Out of scope

- Any change to `orchestrator/run_issue_investigator.py` or anything else in
  `mctlhq/mctl-agents` — that is `mctl-agents#267`, the consumer.
- Any change to the operation registry in `mctlhq/mctl-api` that would let a
  submit carry the two parameters — that is `mctl-api#335`, the dependency.
- Threading the identifiers into `commit-and-push` (commit message) or
  `notify-telegram` (subject line, incident `fingerprint`). The notify step's
  fingerprint is keyed on `WORKFLOW_ISSUE_URL`; changing it would break dedup
  continuity against already-open incidents, for no stated benefit.
- Adding the identifiers to any other agent template
  (`cwft-mctl-agents-implement.yaml`, `-shepherd.yaml`, `-run.yaml`,
  `-reconcile.yaml`) or to the `mctl-dev-loop-*` Temporal path.
- Bumping the `agent_image` default pin (currently
  `ghcr.io/mctlhq/mctl-agents:1.51.0`). The bump that makes the flags actually
  understood is a separate, deliberately separate, commit — see Platform impact.
- Validating the *shape* of either identifier (a UUID check, a length cap, a
  charset filter). Neither value becomes a path component or a git ref in this
  template, so there is nothing here for a malformed value to escape into; the
  argv is already injection-safe by construction.
- Declaring the two parameters as `CONSTRAINED` in
  `scripts/validate-shell-param-interpolation.py`. That set is a claim that
  mctl-api anchors the value with a `Pattern` or `Enum`; making that claim is
  `mctl-api#335`'s to earn, and nothing in this design needs it.

## Open questions

- **Does the account-2 fallback attempt deserve a distinct `execution_id`?**
  `mctl-agents#267`'s `design.md` defines
  `execution_id_for(work_item_id, sequence, attempt)` with `attempt` in the
  hash, which reads as though a retry should carry a fresh id. The CWFT has no
  way to derive one — it would have to invent a value, which acceptance
  criterion 3 of the issue forbids. Proceeding with the reasonable
  interpretation: the template forwards the caller's single pair verbatim to
  both attempts. That is safe rather than a fork, because the same design's
  resume table states that a repeated `execution_id` "is a no-op (idempotent)".
  If a per-attempt id is later wanted, the caller — not this template — should
  mint it.
- **Are the identifiers wanted on the commit message or the Telegram/incident
  legs?** The issue's scope names only `run_issue_investigator.py`, so those
  steps are left alone. Correlating a commit back to a `WorkItem` is a plausible
  follow-up but would change the incident fingerprint, so it is recorded here
  rather than assumed.
- **Does `mctl-api#335` constrain the two values with an anchored pattern?**
  Unknowable from this repo. The design does not depend on it — the argv is
  injection-safe regardless — but it decides whether a future contributor may
  add the names to the `CONSTRAINED` set in
  `scripts/validate-shell-param-interpolation.py`. Until that is confirmed,
  they must not be added.
