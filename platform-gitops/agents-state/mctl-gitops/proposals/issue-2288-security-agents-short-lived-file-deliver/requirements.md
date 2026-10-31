# Short-lived file-delivered credentials for agent pods, without claiming file mounts isolate model Bash (807 G2)

## Context

The mctl-agents ClusterWorkflowTemplates
(`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-*.yaml`)
hand credentials to the agent container (`image: "{{workflow.parameters.agent_image}}"`)
as environment variables via `env[].valueFrom.secretKeyRef` against the
`mctl-agents-secrets` Secret. An environment variable is fixed at container
start, is inherited by every child process (including the `claude` CLI and
the model-driven `Bash` tool), and cannot follow a rotation. Spike
mctlhq/mctl-agents#807 ranks this as gap G2 (high while agent egress is open,
mctl-gitops#2159; medium once egress is enforced).

This proposal covers the mctl-gitops side only: inventory and classify every
credential in the agent CWFTs, remove the long-lived `secretKeyRef` env seed
for `github-token` only (phase 1; every other credential moves in
mctl-gitops#2296 once its mctlhq/mctl-agents#920 reader ships), deliver it as a
least-readable mounted file, add a CI check
that fails if a migrated credential regains an env seed, and record every
credential that has no short-lived or rotatable form as an open gap. It
explicitly does not claim that a Secret file in the same model-readable
container stops model `Bash` from reading credential bytes; that boundary is
owned by mctlhq/mctl-agents#869.

## User stories

- AS a platform security owner I WANT agent pods to stop receiving
  long-lived credentials through `secretKeyRef` environment variables SO THAT
  a credential is not frozen into, and inherited by, every process of the
  agent container for the whole run.
- AS a platform security owner I WANT each agent credential classified as
  short-lived/rotatable, file-capable but long-lived, or neither SO THAT the
  completion report never counts a residual credential as fixed.
- AS an operator I WANT a rotated GitHub installation token to be picked up
  on the next credentialed call of a running agent pod SO THAT a run longer
  than the token TTL keeps working without an env seed.
- AS a reviewer of mctl-gitops PRs I WANT CI to fail when a migrated
  credential's `secretKeyRef` env entry reappears in an agent step SO THAT
  the migration cannot silently regress.

## Acceptance criteria (EARS)

- THE SYSTEM SHALL keep a machine-readable inventory
  (`platform-gitops/governance/agent-credential-delivery.yaml`) listing, for
  every `secretKeyRef` env entry and credential volume in
  `cwft-mctl-agents-*.yaml`, the CWFT, template, variable name, Secret key,
  whether the template runs the agent image, its classification
  (`short-lived-rotatable`, `file-capable-long-lived`, `no-file-or-rotation-form`),
  its delivery (`env-seed` or `file`), and the tracking issue for any
  residual gap. It SHALL contain names only, never values.
- WHEN a credential is marked `delivery: file` in the inventory THE SYSTEM
  SHALL have no `env[].valueFrom.secretKeyRef` entry for that Secret key in
  any agent-image template of any `cwft-mctl-agents-*.yaml`.
- WHEN a credential is marked `delivery: file` THE SYSTEM SHALL deliver it
  through a Secret volume item (or projected source) mounted `readOnly: true`
  with `defaultMode`/`mode` no wider than `0440`, and SHALL set the
  corresponding `*_FILE` path variable defined by the mctlhq/mctl-agents#920
  reader contract.
- THE SYSTEM SHALL mount a credential file only into the templates whose
  inventory entry names them; init containers and exit handlers SHALL NOT
  mount a credential volume they do not use.
- IF the mctlhq/mctl-agents#920 reader for a credential is not released in
  the pinned `agent_image` THEN THE SYSTEM SHALL keep that credential's
  current env wiring and its inventory entry SHALL stay `delivery: env-seed`
  with the blocking issue named.
- WHEN an agent-image template in `cwft-mctl-agents-*.yaml` gains a
  `secretKeyRef` env entry whose key is `delivery: file`, or a `secretKeyRef`
  env entry that is not in the inventory at all, THEN the
  `validate-manifests.yml` job SHALL fail.
- WHEN the new validator runs with `--selftest` THE SYSTEM SHALL prove it
  goes red on a synthetic mutation that restores the env seed of a migrated
  credential, and green on the unmutated fixture.
- WHILE `github-token` is delivered by file THE SYSTEM SHALL keep it
  sourced from the `mctl-agents-secrets` Secret that
  `rotate-github-app-tokens` (`cwft-rotate-github-token.yaml`, every 30 min)
  refreshes, so a rotated token is observed on the next credentialed gh/git
  call without a pod restart.
- WHEN in-script shell guards in a migrated template test a credential's
  presence (for example `[ -n "$GITHUB_TOKEN" ]` in
  `cwft-mctl-agents-implement.yaml`) THE SYSTEM SHALL test the mounted file
  instead (`[ -s "$GITHUB_TOKEN_FILE" ]`), so removing the env seed does not
  change control flow.
- WHEN a migrated template runs `gh auth setup-git` before the Python
  entrypoint THE SYSTEM SHALL pass the token from `$GITHUB_TOKEN_FILE` to that
  single command without exporting it to the shell, because setup-git exits 1
  without a token and the scripts run under `set -e`.
- THE completion report SHALL state three claims separately per credential:
  `NO_LONG_LIVED_SECRET_ENV_SEED` (this proposal), `SHORT_LIVED_OR_ROTATABLE`
  (only where true per the inventory), and
  `MODEL_SHELL_CANNOT_READ_CREDENTIAL_BYTES` (never claimed by this proposal;
  only when mctlhq/mctl-agents#869 proves it).
- IF a credential has no short-lived or rotatable form THEN THE SYSTEM SHALL
  list it in the inventory and on issue #2288 as an open or accepted gap
  with its limitation, and SHALL NOT count it as fixed.

## Out of scope

- A credential-injecting proxy.
- Redesigning model-shell mediation or moving model `Bash` out of the
  credential read boundary (mctlhq/mctl-agents#869).
- Runtime reader code in mctl-agents (mctlhq/mctl-agents#920); this
  proposal only consumes it.
- Agent egress default-deny (mctl-gitops#2159).
- Long-running services outside the CWFTs (for example
  `services/admins/mctl-agents-worker`, which already mounts its GitHub
  token as a file) and non-agent platform jobs that read
  `mctl-agents-secrets` (`config/pvc-janitor.yaml`,
  `config/stuck-pv-janitor.yaml`, `config/mutex-forensics-watchdog.yaml`,
  `wft-lifecycle-bootstrap.yaml`).
- Replacing static credentials with new short-lived issuers (for example
  extending the mctl-api run-token exchange to implement/shepherd/run, or
  changing the Claude OAuth token model). These are recorded as residual
  gaps with follow-up owners.

## Open questions

- Which credentials does mctlhq/mctl-agents#920 actually support, under
  which `*_FILE` variable names, and from which mctl-agents release? This
  proposal assumes `GITHUB_TOKEN_FILE` (already read by
  `orchestrator/github_token.py:refresh_github_token` per the CWFT comments)
  is usable without the env seed, and that `CLAUDE_CODE_OAUTH_TOKEN_FILE`,
  `MCTL_TOKEN_FILE`, `MCTL_USAGE_WRITER_TOKEN_FILE` and
  `MCTL_EVIDENCE_WRITER_TOKEN_FILE` are the #920 names. Each migration is
  gated on confirming its name and release; until then the credential stays
  `env-seed` in the inventory.
- `refresh_github_token()` writes the re-read token into the orchestrator's
  `os.environ["GITHUB_TOKEN"]` (implied by the mctl-agents-worker values
  comment: gh "picks up GITHUB_TOKEN on its own"). That means child
  processes, potentially including the model shell, can still see it as an
  environment variable after the first refresh. This proposal removes the
  pod-level seed only; whether the runtime should stop exporting it to the
  model's process tree belongs to #920/#869 and is not claimed here.
- The Claude Code CLI authenticates from `CLAUDE_CODE_OAUTH_TOKEN` in its
  own environment. Unless #920 provides a launcher that reads a file and
  passes the token only to the CLI process, this credential cannot leave the
  model's process environment, and the token itself is long-lived (manual
  `claude setup-token`). It is expected to remain a residual gap.
- The live contents of the `mctl-agents-secrets` Secret (which optional keys
  exist, e.g. `usage-writer-token`, `evidence-writer-token`,
  `claude-code-oauth-token-2`) were not observed in this run. Secret volumes
  for optional keys are therefore declared `optional: true`.
- Whether the effective file mode of a `0440` Secret volume item under
  `fsGroup: 1000` is readable by the agent container (uid 1000) must be
  confirmed on a real run; kubelet sets group ownership to the fsGroup on
  secret volumes, so `0440` is expected to work and `0400` is expected not to.
