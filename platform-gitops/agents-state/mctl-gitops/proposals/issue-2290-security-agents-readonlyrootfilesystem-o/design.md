# Design: issue-2290-security-agents-readonlyrootfilesystem-o

## Current state

### Agent steps (re-inventoried on mctl-gitops main at 633112e)

An "agent step" is a template whose container image is
`{{workflow.parameters.agent_image}}`. This is the same marker
`scripts/validate-agent-pod-security.py` uses (`MARKER =
"workflow.parameters.agent_image"`). There are 7 today, all `container:`
templates that start `/entrypoint.sh`:

| CWFT | Template | Writable volumes today | Writes seen in the template that would hit the root FS |
|---|---|---|---|
| `cwft-mctl-agents-implement.yaml` | `run-implementer` | `workdir` (emptyDir 10Gi) at `/workdir`; `github-token-file` at `/var/run/gh` | `/tmp/state-out` (output artifact), `/tmp/onexit`, `gh auth setup-git` (writes `~/.gitconfig`), the entrypoint symlink into `/app/agents/<svc>/proposals`, Claude Code state in `$HOME`, toolchain caches (`GOPATH=$HOME/go`, comment at line ~174), `/tmp` toolchain downloads (comment at line ~190). `TMPDIR=/workdir/clones` already moves Python `tempfile` onto the volume. |
| `cwft-mctl-agents-investigate.yaml` | `run-investigator` | `workdir`, `/var/run/gh`, `/var/run/secrets/mctl-api` | `/tmp/proposal-out` (output artifact), `gh auth setup-git`, `$HOME`. `TMPDIR` is set. |
| `cwft-mctl-agents-shepherd.yaml` | `run-shepherd` | `workdir`, `/var/run/gh` | `/tmp/state-out`, `/tmp/onexit`, `gh auth setup-git`, entrypoint symlink (STATE_DIR comment at line ~740), `$HOME`. `TMPDIR` is set. |
| `cwft-mctl-agents-run.yaml` | `run-orchestrator` | `workdir` | `/tmp/state-out`, entrypoint symlink, `$HOME`. |
| `cwft-mctl-agents-reconcile.yaml` | `run-reconcile` | `workdir` | `$HOME`, `/tmp` (to be confirmed). |
| `cwft-mctl-agents-scout.yaml` | `scout` | `workdir` (emptyDir 256Mi) | `$HOME`, `/tmp` (to be confirmed). |
| `cwft-mctl-agents-usage-collector.yaml` | `collect-usage` | `workdir` | `$HOME`, `/tmp` (to be confirmed). |

Every one of these steps already has:

- a template-level pod `securityContext` with `runAsNonRoot: true`,
  `runAsUser: 1000`, `runAsGroup: 1000`, `fsGroup: 1000` and
  `seccompProfile: RuntimeDefault`;
- a container `securityContext` with `runAsNonRoot: true`,
  `allowPrivilegeEscalation: false` and `capabilities.drop: [ALL]`.

None sets `readOnlyRootFilesystem`.

`cwft-mctl-agents-approve.yaml` has no agent step (only `alpine/git` scripts).
The CronWorkflows (`cronworkflow-mctl-agents-*.yaml`, `cwft-mctl-agents-daily.yaml`)
only use `workflowTemplateRef` and define no inline templates.

### Init containers and sidecars in the same CWFTs

- `wait-egress-proxy` (`alpine:3.19`) runs on every agent step and on most helper
  steps. It is already `runAsNonRoot`, uid 65534, `readOnlyRootFilesystem: true`
  and `drop: [ALL]`.
- `clone-gitops` (`alpine/git:2.43.0`) runs on every agent step except `scout`
  and `collect-usage`. It runs explicitly as root (uid 0) with
  `allowPrivilegeEscalation: false`, `drop: [ALL]`, and `add: [CHOWN,
  DAC_OVERRIDE, FOWNER, SETGID, SETUID]`. It writes `/workdir` and runs
  `chown -R 1000:1000 /workdir`. Making it non-root is tracked in mctl-gitops#1720.
- Argo's controller-injected `init` and `wait` containers. They run under the
  `mctl-agents-executor` SA (see `platform-gitops/argo-workflows/config/sa-and-rbac.yaml`).
  `platform-gitops/bootstrap/templates/core-infra/argo-workflows.yaml` sets no
  controller `executor.securityContext`, so their posture is the Argo default.
- No template defines `sidecars:`.
- Helper `script:` steps on `alpine:3.19`, `alpine/git` or `alpine/k8s` have no
  `securityContext`: `commit-and-push`, `flip-status`, `notify-telegram`,
  `assert-attempt`, `assert-exit-code` and `post-deploy-verify`. Some of their
  pods carry their own `clone-gitops` init container with no `securityContext`.
  These are not agent steps.

### Validator and CI

`scripts/validate-agent-pod-security.py` globs `*.yaml` in the cluster-templates
dir and runs `check_template` on each agent-image template. `--selftest` mutates
an in-memory `_fixture()` (pod block, `allowPrivilegeEscalation`, container
drop, init drop) and asserts which mutations fail. CI runs both modes in
`.github/workflows/validate-manifests.yml` ("Validate agent pod security
context"). The validator does not look at `readOnlyRootFilesystem`.

### Deployed state checked

- `mctl_list_recent_agent_runs`: failed with "admin group membership required".
  Recent agent run history, and with it any live evidence of writable paths,
  could not be observed. This is recorded under Open questions; it is not taken
  to mean "no writes".
- `$MCTL_GITOPS_ROOT` / `platform-gitops/services`, `tenants`: not relevant.
  Agent CWFTs are cluster-scoped templates in this repo, not tenant services. The
  repo clone at 633112e was used as the deployed source of truth for templates,
  since ArgoCD reconciles them from main.
- The agent image (`ghcr.io/mctlhq/mctl-agents:1.112.1`, the default
  `agent_image` in `cwft-mctl-agents-implement.yaml`) was not inspected. Its
  `HOME`, the contents of `/app/agents/*/proposals` and the behaviour of
  `/entrypoint.sh` are known only from comments in these templates.

## Proposed solution

### 1. Discover writable paths before adding mounts

On a branch, submit each agent kind with `readOnlyRootFilesystem: true` and only
`/tmp` and `$HOME` mounted, using the CWFTs through a test Workflow or a template
copy that uses the same `agent_image` pin. Then:

- collect every `Read-only file system` / EROFS error from the step logs
  (`mctl_get_workflow_logs`);
- as a cross-check, run `find / -xdev -newer /proc/1 -type f` in a debug run
  without the flag, to list paths the step writes to the image layer.

Record the result as a per-kind writable-path table in a new runbook,
`docs/runbooks/agent-readonly-rootfs.md`.

### 2. Template changes, per agent step

- Add `readOnlyRootFilesystem: true` to `container.securityContext`.
- Add the minimum `emptyDir` volumes. Each gets a `sizeLimit` and a comment
  naming the mount path, its consumer and the evidence. The planned baseline,
  to be narrowed by step 1:
  - `agent-tmp` at `/tmp`. Consumers: output-artifact dirs `/tmp/state-out`,
    `/tmp/proposal-out` and `/tmp/onexit`, plus tool temp files. Size: 1Gi for
    the implementer, which downloads toolchains into `/tmp`; 256Mi elsewhere.
    Argo mirrors the main container's volume mounts into the `wait` container,
    so output artifacts on this volume are still collected. A real run must
    confirm this (T5).
  - `agent-home` at the image's `$HOME` (expected `/home/<user>`, uid 1000;
    confirm from the image). Consumers: Claude Code state (`~/.claude`,
    `~/.claude.json`), `~/.gitconfig` from `gh auth setup-git`,
    `~/.config/gh`, and for the implementer `~/go` and `~/.cache` (Go, pip and
    npm caches used by repository tests). Size: 4Gi for the implementer, 256Mi
    elsewhere. If step 1 shows that only `~/.claude*` and `~/.gitconfig` are
    written for a kind, that kind should get narrower mounts or env redirects
    instead (`GIT_CONFIG_GLOBAL`, `XDG_CONFIG_HOME`, `XDG_CACHE_HOME` onto
    `/workdir`).
  - Entrypoint writes under `/app` (inbox, proposals and `_mentor/digest`
    links, under `set -e`): fixed by the prerequisite mctlhq/mctl-agents#947.
    This proposal only pins `agent_image` to the #947 release. It opens no
    mctl-agents PR and mounts nothing over `/app` or `/app/agents`.
- Do not change `workdir` sizing. Keep `TMPDIR=/workdir/clones` where it is
  already set.
- Do not touch the `clone-gitops` or `wait-egress-proxy` specs (see inventory).

All 7 steps get the same pattern. A YAML anchor is not available across
templates in these files, so the pattern is repeated with a pointer comment to
the runbook.

### 3. Validator

Extend `check_template` in `scripts/validate-agent-pod-security.py`:

- `sc.get("readOnlyRootFilesystem") is not True` becomes
  `"{where}: container readOnlyRootFilesystem must be true"`.

Extend `_fixture()` with `readOnlyRootFilesystem: True` and an `emptyDir` `/tmp`
mount, then add these selftest cases:

- `no readOnlyRootFilesystem`: delete the field. Expect a failure.
- `readOnlyRootFilesystem false`. Expect a failure.
- `new unprotected agent step`: append a second template `agent-new`, a copy of
  the hardened one without the field. Expect a failure. This is the "newly
  introduced agent step" mutation the issue asks for.
- `hardened`: still passes.

Optionally (it is cheap and closes a blind spot), also scan
`spec.workflowSpec.templates` so that a CronWorkflow with an inline agent step
cannot bypass the check. Today none has one.

Proof that the check fails on real input: in the PR, run the validator with
`--dir` pointed at a temp copy of the cluster-templates dir where
`readOnlyRootFilesystem` was removed from `run-implementer`. Paste the non-zero
output. Update the module docstring to cite mctl-gitops#2290.

### 4. Init container / sidecar inventory

Document this in `docs/runbooks/agent-readonly-rootfs.md`, with a short pointer
comment in each CWFT:

| Container | Where | Classification |
|---|---|---|
| agent step containers (7) | all agent CWFTs | Inside this issue's invariant (validator-enforced). |
| `wait-egress-proxy` | all agent and most helper pods | Already hardened (non-root 65534, read-only root, drop ALL). Recommendation: add it to the validator as a follow-up assertion. Not in this issue's invariant. |
| `clone-gitops` on agent pods | implement, investigate, shepherd, run, reconcile | Hardened elsewhere: drop ALL and no escalation enforced by the #1717 validator. Root plus a writable root FS remains a residual, owned by mctl-gitops#1720. It finishes before the agent container starts and shares only `/workdir` with it. |
| Argo `init` / `wait` (injected) | every pod | Documented residual. The controller has no `executor.securityContext`. Owned by the #1719 sweep. They do not run model-driven code. |
| Helper `script:` steps and their `clone-gitops` | `commit-and-push`, `flip-status`, `notify-telegram`, `assert-*`, `post-deploy-verify` | Documented residual. Separate pods with no agent code. Covered by the #1719 sweep. |
| `sidecars:` | none | None present. The validator could reject `sidecars` on agent steps unless they are hardened (follow-up). |

### 5. Real-run verification

After merge and the ArgoCD sync (about 3 minutes), trigger one run of each kind:

- investigate, via `mctl_trigger_issue` on a low-risk issue;
- implement, on an accepted proposal whose repo has tests (for example a Go or
  Python repo), and confirm that the test command ran in the logs;
- shepherd, via `mctl_trigger_shepherd`;
- reconcile, via `mctl_trigger_reconcile` with `dry_run=true`;
- run, via `mctl_trigger_single_service`;
- scout and usage-collector, by submitting from their CronWorkflows.

Record the workflow names in the PR or runbook.

## Alternatives

1. **Mount one large `emptyDir` over `$HOME`'s parent, or over `/app`.** This is
   the fastest way to green, but it re-opens the exact surface the control is
   meant to close (`/app` holds agent code and prompts). The issue rejects it
   explicitly.
2. **Enforce through namespace PSA `restricted` instead of per-template fields.**
   `restricted` does not even require `readOnlyRootFilesystem`. Enforcing it on
   `argo-workflows` would also break the root helper steps. That work is tracked
   in mctl-gitops#1719 and mctl-agents#807, so it was dropped.
3. **Kyverno/Gatekeeper admission policy requiring `readOnlyRootFilesystem` on
   agent pods.** This is a stronger runtime guarantee. It adds a new
   cluster-level policy component and a way of selecting agent pods (labels)
   that does not exist yet. Deferred: the per-template validator meets this
   issue's acceptance, and admission can follow on top of it.
4. **Put every writable path under `/workdir` with env redirects (`HOME=/workdir/home`)
   and no new volumes.** Fewer volumes, but it mixes home and caches into the
   10Gi `workdir` that `clone-gitops` chowns and that STATE_DIR lives on. It also
   changes `HOME` semantics for Claude Code. It stays available as a per-kind
   narrowing option, not as the default.

## Platform impact

- **Migration / compatibility**: template-only change in mctl-gitops, plus
  (likely) one mctl-agents image bump for the entrypoint symlink. In-flight
  workflows keep their snapshotted templates. New submissions pick up the change
  after the ArgoCD sync.
- **Resources**: new `emptyDir` volumes count against node ephemeral storage.
  Worst case per implementer pod is about +5Gi on top of the existing 10Gi
  `workdir`. Others add about 512Mi. `sizeLimit` bounds each one; going over it
  evicts the pod, and that eviction shows up in run logs. Check this against
  `platform-gitops/argo-workflows/config/local-workdir-quota.yaml` if
  ephemeral-storage quota applies to `argo-workflows`.
- **Risks**:
  - A missed write path makes the step fail with EROFS. Mitigation: discovery
    runs (step 1), real runs of every kind, and a per-template rollback.
  - The entrypoint symlink is a hard blocker if mctl-agents is not changed first.
    Mitigation: sequence the image change before the gitops PR, or use the
    verified-empty fallback.
  - Output artifacts on an `emptyDir` are not collected. Mitigation: T5 checks
    that `/tmp/state-out`, `/tmp/proposal-out` and `/tmp/onexit` artifacts
    arrive.
  - Repository tests in the implementer write outside `$HOME` and `/tmp` (for
    example into the repo itself, which is on `/workdir` and already writable).
    Those are covered.
- **Security**: the model-driven shell can no longer modify `/app`, `/usr` or
  `/etc` in its container. Writable state is limited to declared, size-limited
  scratch volumes that are discarded with the pod.
