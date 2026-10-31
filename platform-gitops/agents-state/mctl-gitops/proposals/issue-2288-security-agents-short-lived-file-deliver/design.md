# Design: issue-2288-security-agents-short-lived-file-deliver

## Current state

### Where credentials come from

- `platform-gitops/argo-workflows/secrets/mctl-agents-secrets.yaml` is an
  ExternalSecret (`refreshInterval: 1h`, `dataFrom: extract` of Vault
  `platform/mctl-agents`) producing the Secret `mctl-agents-secrets` in
  `argo-workflows`. Documented keys: `claude-code-oauth-token` (long-lived
  Pro/Max OAuth from `claude setup-token`, re-seeded by hand),
  `mctl-token` (static admin bearer), `github-token`, `usage-writer-token`.
  The CWFTs additionally reference `evidence-writer-token`,
  `telegram-bot-token`, `telegram-chat-id` and, through the `oauth-key`
  input parameter, a fallback `claude-code-oauth-token-2`.
- `platform-gitops/argo-workflows/cluster-templates/cwft-rotate-github-token.yaml`
  (CronWorkflow `rotate-github-app-tokens`, `*/30 * * * *`) mints a GitHub
  App installation token (App id 4450852, 60 min TTL) into Vault
  `secret/platform/mctl-agents` key `github-token` and force-syncs
  `argo-workflows/mctl-agents-secrets`. Its own description notes that
  `secretKeyRef` consumers never see the new value; only a mounted Secret
  volume propagates. So `github-token` is the one CWFT credential that is
  genuinely short-lived and rotated today.

### How the CWFTs deliver them

Inventory of `env[].valueFrom.secretKeyRef` entries (line numbers from the
clone at the time of investigation):

| CWFT | Template (image) | Env var -> Secret key |
|---|---|---|
| implement | `run-implementer` (agent_image, model) | `CLAUDE_CODE_OAUTH_TOKEN` -> `{{inputs.parameters.oauth-key}}` (l.738), `GITHUB_TOKEN` -> `github-token` (l.752), `MCTL_TOKEN` -> `mctl-token` (l.766), `MCTL_USAGE_WRITER_TOKEN` (l.787), `MCTL_EVIDENCE_WRITER_TOKEN` (l.798) |
| implement | `notify-telegram` (non-agent) | `TG_BOT_TOKEN`, `TG_CHAT_ID`, `MCTL_TOKEN` (l.1316-1328) |
| investigate | `run-investigator` (agent_image, model) | `CLAUDE_CODE_OAUTH_TOKEN` (l.826), `GITHUB_TOKEN` (l.839), `MCTL_USAGE_WRITER_TOKEN` (l.882), `MCTL_EVIDENCE_WRITER_TOKEN` (l.893). No `MCTL_TOKEN`: replaced by the projected-SA run-token exchange (`mctl-api-run-token` volume, `MCTL_RUN_TOKEN_MODE=enforce`, mctlhq/mctl-agents#717/#737). |
| investigate | `notify-telegram` | `TG_BOT_TOKEN`, `TG_CHAT_ID`, `MCTL_TOKEN` (l.1403-1415) |
| shepherd | `run-shepherd` (agent_image, model) | `CLAUDE_CODE_OAUTH_TOKEN` (l.758), `GITHUB_TOKEN` (l.769), `MCTL_TOKEN` (l.784), `MCTL_USAGE_WRITER_TOKEN` (l.810), `MCTL_EVIDENCE_WRITER_TOKEN` (l.821) |
| shepherd | `notify-telegram` | `TG_BOT_TOKEN`, `TG_CHAT_ID`, `MCTL_TOKEN` (l.1717-1729) |
| run | agent step running `orchestrator.run_all` (agent_image, model) | `CLAUDE_CODE_OAUTH_TOKEN` (l.513), `MCTL_TOKEN` (l.521), `GITHUB_TOKEN` (l.545) |
| run | `notify-telegram` | `TG_BOT_TOKEN`, `TG_CHAT_ID`, `MCTL_TOKEN` (l.989-1001) |
| scout | `scout` (agent_image, model, `orchestrator.run_scout`) | `CLAUDE_CODE_OAUTH_TOKEN` (l.133), `GITHUB_TOKEN` (l.139), `SCOUT_TELEGRAM_BOT_TOKEN` -> Secret `mctl-agents-scout-telegram` key `bot-token` (l.148), `SCOUT_TELEGRAM_CHAT_ID` (l.157) |
| scout | `notify-telegram` | `TG_BOT_TOKEN`, `TG_CHAT_ID` (l.221-227) |
| reconcile | agent_image, no model (`orchestrator.run_shepherd --reconcile`; description: "never runs a model") | `GITHUB_TOKEN` (l.413) |
| reconcile | `notify-telegram` | `TG_BOT_TOKEN`, `TG_CHAT_ID` (l.754-760) |
| usage-collector | agent_image, no model (`orchestrator.run_usage_collector`) | `GITHUB_TOKEN` (l.142), `MCTL_USAGE_WRITER_TOKEN` (l.151) |
| usage-collector | `notify-telegram` | `TG_BOT_TOKEN`, `TG_CHAT_ID` (l.216-222) |
| approve, daily | — | no `secretKeyRef` env (approve uses the `mctl-gitops-deploy-key` volume, `defaultMode: 0600`, in non-agent containers) |

The existing file pattern: implement, investigate and shepherd already
declare a spec-level `github-token-file` Secret volume (items
`github-token` -> `github-token`, mounted `readOnly` at `/var/run/gh`) and
set `GITHUB_TOKEN_FILE=/var/run/gh/github-token`. The comments say
`orchestrator/github_token.py:refresh_github_token()` re-reads the file
before every gh/git subprocess and that the `GITHUB_TOKEN` env entry "only
seeds the very first call before any refresh happens". So the env seed is
redundant for those three, and it is still the only delivery on run, scout,
reconcile and usage-collector. The `github-token-file` volume sets no
`defaultMode`, so the file is created with the Kubernetes default `0644`.

Shell guards in the model-step scripts read credential env vars directly and
would change behaviour if the seed were removed:
`cwft-mctl-agents-investigate.yaml:480` (`[ -z "$GITHUB_TOKEN" ]`),
`cwft-mctl-agents-implement.yaml:517` and `cwft-mctl-agents-shepherd.yaml:538`
(`[ -n "$GITHUB_TOKEN" ]` before `gh auth setup-git`), and the fallback
guards on `$CLAUDE_CODE_OAUTH_TOKEN` (`implement:497`, `investigate:467`,
`run:339`, `shepherd:522`).

Agent pods run as uid 1000 / `fsGroup: 1000` with `seccompProfile:
RuntimeDefault` (enforced by `scripts/validate-agent-pod-security.py`,
wired in `.github/workflows/validate-manifests.yml` l.265-266 with a
`--selftest` step). The model `Bash` tool runs as the same uid in the same
container, so any file the orchestrator can read the model can read too.
That is why this design never claims model-shell isolation.

There is no existing check that prevents a `secretKeyRef` env entry from
being (re)added to an agent step. `tests/test_policy_checkpoint_coverage.py`
with `platform-gitops/governance/policy-checkpoint-coverage.yaml` is the
precedent for a manifest-driven governance check over the CWFTs.

### Precedent outside the CWFTs

`services/admins/mctl-agents-worker/values.yaml` (read from
`$MCTL_GITOPS_ROOT`) mounts `GITHUB_TOKEN` from a Secret volume at
`/var/run/secrets/github` and sets `GITHUB_TOKEN_FILE`; it also records
that `GH_TOKEN` must not be set because gh prefers it over the refreshed
`GITHUB_TOKEN`, and that `CLAUDE_CODE_OAUTH_TOKEN` stays env-delivered
because it is long-lived and hand-rotated.

### Deployed state checked

- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`:
  confirms the deployed worker uses the file-backed `GITHUB_TOKEN_FILE`
  pattern and env-delivered `CLAUDE_CODE_OAUTH_TOKEN` / `MCTL_TOKEN`
  (out of scope, used as precedent).
- Clone `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-*.yaml`
  and `secrets/mctl-agents-secrets.yaml`: these are ArgoCD-synced cluster
  objects; the table above is what ArgoCD applies.
- `agent_image` pin on investigate: `ghcr.io/mctlhq/mctl-agents:1.112.2`
  (`cwft-mctl-agents-investigate.yaml:83`).
- Not observed: the live keys present in the `mctl-agents-secrets` Secret,
  and the release status/variable names of mctlhq/mctl-agents#920. No mctl
  MCP tool was used to read them (Secret contents are not exposed by the
  read-only tools). Both are recorded as open questions, not assumed absent.

## Proposed solution

### 1. Credential inventory as data

Add `platform-gitops/governance/agent-credential-delivery.yaml`: one entry
per (CWFT, template, env var) from the table above, with fields
`secret`, `key`, `agent_image` (bool), `model_driven` (bool),
`classification`, `delivery` (`env-seed` | `file`), `file_env`
(the `*_FILE` var), `mount_path`, `reader` (e.g. `mctl-agents#920 >= x.y.z`),
`residual` (limitation text, tracked issue). Names only, never values.

Initial classification:

| Credential (key) | Classification | Target delivery | Notes |
|---|---|---|---|
| `github-token` | short-lived-rotatable (App installation token, 60 min TTL, rotated every 30 min) | file, all agent-image steps | Reader exists (`refresh_github_token`). Phase 1. |
| `claude-code-oauth-token`, `-2` | file-capable-long-lived (manual `claude setup-token`) | env-seed until #920 provides a file reader that passes the token only to the CLI process; then file | Residual: no short-lived form; CLI reads env. |
| `mctl-token` (implement, shepherd, run model steps) | file-capable-long-lived (static admin bearer) | file when #920 supports `MCTL_TOKEN_FILE` | Residual: the short-lived replacement is the run-token exchange already enforced on investigate; extending it is a separate mctl-agents/mctl-api follow-up. |
| `usage-writer-token`, `evidence-writer-token` | file-capable-long-lived (static, narrowly scoped bearer) | file when #920 supports the `_FILE` names | Residual: not short-lived. |
| `mctl-agents-scout-telegram/bot-token` (+ chat id) | no-file-or-rotation-form (Telegram bot tokens are static; chat id is not a secret) | file if #920 supports it, else env-seed | Residual. |
| `telegram-bot-token`, `telegram-chat-id`, `mctl-token` in `notify-telegram` | not agent image, no model shell | unchanged (env-seed) | Listed for completeness; out of model-step scope. |

### 2. Phase 1: `github-token` (reader already present)

For every agent-image step that has `GITHUB_TOKEN` (implement, investigate,
shepherd, run, scout, reconcile, usage-collector):

- Remove the `GITHUB_TOKEN` `secretKeyRef` entry.
- Ensure a `github-token-file` Secret volume (items `github-token` ->
  `github-token`) with `defaultMode: 0440`, mounted `readOnly: true` at
  `/var/run/gh` only in that step's container (not init containers, not
  `notify-telegram`), and `GITHUB_TOKEN_FILE=/var/run/gh/github-token`.
  Add the volume to run, scout, reconcile and usage-collector, which lack it.
- Rewrite shell guards to test the file: `investigate:480`
  -> `[ ! -s "$GITHUB_TOKEN_FILE" ]`; `implement:517`, `shepherd:538`
  -> `[ -s "$GITHUB_TOKEN_FILE" ]`. `gh auth setup-git` installs
  `gh auth git-credential`, which reads `GITHUB_TOKEN` from the process env at
  push time; that env is the one `refresh_github_token()` maintains in the
  orchestrator, so push keeps working (validated by the real-run task).
- Gate: confirm with mctlhq/mctl-agents#920 that every entrypoint in those
  steps (`run_issue_investigator`, `run_implementer`, `run_shepherd`
  including `--reconcile`, `run_all`, `run_scout`, `run_usage_collector`)
  calls `refresh_github_token()` before its first gh/git/HTTP call with no env
  seed. Any entrypoint that does not stays `env-seed` and is listed.
- Comment changes: replace "GITHUB_TOKEN above only seeds the very first
  call" with a note citing #2288 and that the file is the only delivery.

### 3. Phase 2: remaining file-capable credentials, gated on #920

Per credential, once the pinned `agent_image` contains the #920 reader:
replace the `secretKeyRef` entry with a Secret volume item from
`mctl-agents-secrets` (`optional: true` for optional keys,
`defaultMode: 0440`), a `readOnly` mount under `/var/run/mctl-agents/creds`,
and the `*_FILE` variable. The `oauth-key` parameter selects the key, so the
OAuth volume is declared template-level (`templates[].volumes`, where
`{{inputs.parameters.oauth-key}}` resolves) rather than spec-level. Shell
guards on `$CLAUDE_CODE_OAUTH_TOKEN` move to `[ -s "$CLAUDE_CODE_OAUTH_TOKEN_FILE" ]`.
Each credential flips to `delivery: file` in the inventory in the same PR
that changes the manifest. Credentials without reader support stay
`env-seed` with the residual recorded.

### 4. GitOps check

Add `scripts/validate-agent-credential-delivery.py` (style of
`scripts/validate-agent-pod-security.py`: PyYAML, `--selftest`, exit 1 on
findings). For every template in `cwft-mctl-agents-*.yaml` whose container
or script image contains `workflow.parameters.agent_image`:

1. Every `env[].valueFrom.secretKeyRef` (container and initContainers) must
   match an inventory entry; unknown entries fail (no unclassified
   credential can be added silently).
2. A `secretKeyRef` whose `(secret, key)` is `delivery: file` fails, naming
   the CWFT, template and variable.
3. For each `delivery: file` entry, the template must mount a volume whose
   Secret item selects that key, with `readOnly: true` and
   `defaultMode`/item `mode` <= `0440`, and set the `file_env` variable to a
   path under that mount.
4. A credential volume must not be mounted in an initContainer or in a
   template the inventory does not list.

`--selftest` builds an in-memory fixture with one migrated credential,
asserts it passes, then re-adds the `secretKeyRef` env seed and asserts it
fails (the "proved red on a mutation" requirement). Wire both
`--selftest` and the real run into `.github/workflows/validate-manifests.yml`
next to the pod-security step. Add `tests/test_agent_credential_delivery.py`
that runs the validator against the real repo plus a copied-and-mutated CWFT
in a temp dir.

### 5. Completion report

The PR description and a comment on #2288 list each inventory row with
three independent claims: `NO_LONG_LIVED_SECRET_ENV_SEED` (true only for
`delivery: file` rows), `SHORT_LIVED_OR_ROTATABLE` (true only for
`github-token`), `MODEL_SHELL_CANNOT_READ_CREDENTIAL_BYTES` (false for all
rows; owned by mctlhq/mctl-agents#869). Residual rows are listed with their
limitation, never a value.

## Alternatives

- **Mount the whole `mctl-agents-secrets` Secret as a directory.** Simple,
  but mounts every key (including ones a step never uses) into every agent
  container, which is wider than today's env wiring. Dropped in favour of
  per-key `items`.
- **Keep the env seed but also mount the file (status quo for three CWFTs).**
  Provides rotation but not `NO_LONG_LIVED_SECRET_ENV_SEED`; the stale seed
  remains in `/proc/<pid>/environ` of every process for the whole run.
  Dropped: that is the gap.
- **Fetch credentials from Vault at runtime (Vault agent / CSI driver).**
  Gives short-lived leases for Vault-native secrets, but none of these
  credentials is a dynamic Vault secret (they are KV values), the agent
  container would need a Vault role, and the bytes still land in the same
  model-readable filesystem. Not better than a Secret volume for this issue;
  revisit with #869.
- **Credential-injecting proxy.** Explicitly out of scope per the issue and
  overlaps #869.

## Platform impact

- **Migration:** phase 1 touches seven CWFTs; ArgoCD syncs them in ~3 min.
  In-flight workflows keep the template snapshotted at submit, so there is
  no mid-run change. Phase 2 lands per credential behind an `agent_image`
  bump that carries the #920 reader.
- **Backward compatibility:** an `agent_image` older than the reader would
  run without `GITHUB_TOKEN` and fail its first gh call. Mitigation: the
  phase-1 PR must not lower any `agent_image` pin and must be preceded by a
  check that all pinned images contain the file reader; rollback restores
  the env entry.
- **Optional keys:** a Secret volume item for an absent key blocks pod
  start unless the volume is `optional: true`; every optional credential
  volume sets it, matching the current `optional: true` on `secretKeyRef`.
- **File permissions:** `0440` with `fsGroup: 1000` is expected to be
  readable by uid 1000; verified on the first real run (an unreadable file
  shows as a gh auth failure, rollback is immediate).
- **Rotation latency:** kubelet refreshes Secret volumes on its sync period
  (about 1 min) after ESO updates the Secret; `rotate-github-app-tokens`
  force-syncs the ExternalSecret every 30 min, inside the 60 min TTL.
- **Security claim limits:** the file is readable by the model's `Bash`.
  `refresh_github_token()` also exports the token into the orchestrator's
  environment for gh/git, which children may inherit. This issue removes the
  pod-level long-lived seed and enables rotation; it does not close
  model-shell exfiltration (#869), and egress (#2159) stays the main
  mitigation for the residual.
- **Resource impact:** none beyond one small Secret volume per step.
