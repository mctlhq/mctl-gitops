# Design: issue-1717-security-agents-set-a-restricted-securit

## Current state

All agent-image steps live in ClusterWorkflowTemplates under
`platform-gitops/argo-workflows/cluster-templates/`. Each file has exactly one
template whose `container.image` is `"{{workflow.parameters.agent_image}}"`
(verified with `grep -c 'agent_image}}'`):

| File | Template | initContainer |
|---|---|---|
| `cwft-mctl-agents-implement.yaml` | `run-implementer` | `clone-gitops` (`alpine/git:2.43.0`) |
| `cwft-mctl-agents-investigate.yaml` | `run-investigator` | `clone-gitops` |
| `cwft-mctl-agents-run.yaml` | `run-orchestrator` | `clone-gitops` |
| `cwft-mctl-agents-shepherd.yaml` | `run-shepherd` | `clone-gitops` |
| `cwft-mctl-agents-reconcile.yaml` | `run-reconcile` | `clone-gitops` |
| `cwft-mctl-agents-usage-collector.yaml` | `collect-usage` | none |

`cwft-mctl-agents-daily.yaml` (and `cronworkflow-mctl-agents-*.yaml`) are
CronWorkflows that only use `workflowTemplateRef` + `clusterScope: true`; they
define no containers and inherit whatever the referenced CWFT sets.
`cwft-mctl-agents-approve.yaml` uses only `alpine/git`.

Each agent template already carries template-level isolation:
`serviceAccountName: mctl-agents-runner`, `automountServiceAccountToken: false`,
`executor.serviceAccountName: mctl-agents-executor` (see
`config/sa-and-rbac.yaml`). None sets `securityContext` at the template
(pod) level or on `container`. The workflow-level `spec` likewise has none.

The `clone-gitops` initContainer (e.g. `cwft-mctl-agents-implement.yaml`
around line 326) runs as root in `alpine/git`: it runs
`apk add --no-cache openssh-client ca-certificates`, writes `~/.ssh` (root's
HOME), copies the deploy key from the `deploy-key` Secret volume
(`defaultMode: 0600`), clones into the `workdir` emptyDir and ends with
`chown -R 1000:1000 /workdir` so uid 1000 (the image `USER`) can write
`STATE_DIR` and `TMPDIR=/workdir/clones`. That chown string is asserted by
`scripts/validate-local-workdir.py::validate_agents_workdir_nonroot_handoff`
for five of the templates (`AGENT_TEMPLATES`).

Precedent in this repo for container-level hardening:
`cwft-argo-local-workdir-canary.yaml` and `wft-otel-trace-fixture.yaml` set
`allowPrivilegeEscalation: false`, `capabilities.drop: ["ALL"]`,
`runAsNonRoot: true` on their containers. Tenant namespaces already run
`audit`/`warn: restricted` via `helm-charts/tenant/templates/namespace.yaml`;
`argo-workflows` has no PSS label.

CI: `.github/workflows/validate-manifests.yml` runs a series of
`scripts/validate-*.py` detectors, each normally `--selftest` first and then
against the repo (e.g. `validate-implement-worker-singleton.py`).

## Proposed solution

### 1. Template-level pod securityContext on each agent template

Argo's `Template` has a `securityContext` field (a `PodSecurityContext`) that
applies only to the pod created for that template. Set it on the six agent
templates, not at workflow `spec` level, so `commit-and-push`,
`notify-telegram`, `assert-attempt` and `post-deploy-verify` (root
`alpine`/`alpine/git`/`alpine/k8s` helpers that run `apk add`) are unaffected:

```yaml
    - name: run-implementer
      serviceAccountName: mctl-agents-runner
      automountServiceAccountToken: false
      # Restricted pod posture for the step that runs model-driven shell
      # (mctl-gitops#1717). Template-level, not spec-level: the helper steps in
      # this file are root alpine images that install packages.
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        runAsGroup: 1000
        fsGroup: 1000
        seccompProfile:
          type: RuntimeDefault
```

A one-block-per-template copy is chosen over a YAML anchor because each file
has only one agent template, so there is nothing to share within a file, and
anchors do not cross files.

### 2. Container-level securityContext on the agent container

```yaml
      container:
        image: "{{workflow.parameters.agent_image}}"
        securityContext:
          runAsNonRoot: true
          allowPrivilegeEscalation: false
          capabilities:
            drop: ["ALL"]
```

The agent already runs as uid 1000 with HOME `/home/app` from the image, so
`runAsUser: 1000` changes no effective identity; it only makes it mandatory.
`readOnlyRootFilesystem` is not set (SDK, `uv`, Go toolchain bootstrap write to
`$HOME` and `/tmp`).

### 3. Explicit exception on the `clone-gitops` initContainer

With pod-level `runAsUser: 1000`, the initContainer would otherwise run as
uid 1000 and fail at `apk add`, at `~/.ssh` (no passwd entry, HOME=`/`) and at
`chown`. Rather than rewriting the clone step, give it an explicit
container-level override that is still tighter than today:

```yaml
        - name: clone-gitops
          image: alpine/git:2.43.0
          # Root on purpose: apk add + chown -R 1000:1000 /workdir hand-off
          # (validate-local-workdir.py). Every capability except the file-
          # ownership ones is dropped and escalation is off (mctl-gitops#1717).
          securityContext:
            runAsUser: 0
            runAsGroup: 0
            runAsNonRoot: false
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]
              add: ["CHOWN", "DAC_OVERRIDE", "FOWNER", "SETGID", "SETUID"]
```

The init container inherits pod-level `seccompProfile: RuntimeDefault`,
which `apk`, `ssh` and `git` run under fine. The capability `add` list
starts conservative; the implementer may trim it if a real run passes without
some of them (`CHOWN` is certainly required). The deploy key is mounted only
into this initContainer, so the `fsGroup`-induced group-read on the Secret
volume does not expose it to the agent container.

`fsGroup: 1000` makes the `workdir` emptyDir group-owned by gid 1000 with the
setgid bit, so everything the agent creates stays writable to it; the root
init's `chown -R` still converts the root-owned clone.

### 4. Argo executor containers

The pod-level context also applies to Argo's `init`/`wait` containers
(emissary executor, chart `argo-workflows` 0.47.5 in
`bootstrap/templates/core-infra/argo-workflows.yaml`). `argoexec` is built to
run non-root and needs no capabilities under emissary, so uid 1000 +
RuntimeDefault is compatible. The issue does not require hardening their
container-level contexts, and this proposal does not touch the controller's
`executor`/`mainContainer` config.

### 5. CI validator `scripts/validate-agent-pod-security.py`

New Python detector (PyYAML only, same style as
`validate-implement-worker-singleton.py`):

- Globs `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-*.yaml`
  (so new agent templates are covered automatically), loads every document,
  and for every `spec.templates[*]` whose `container.image` or
  `script.image` contains `workflow.parameters.agent_image`:
  - pod level (`template.securityContext`, falling back to
    `spec.securityContext`): `runAsNonRoot is True`, `runAsUser == 1000`,
    `fsGroup == 1000`, `seccompProfile.type == "RuntimeDefault"`;
  - container level: `allowPrivilegeEscalation is False`,
    `"ALL" in capabilities.drop`, and container `runAsNonRoot` not `False`;
  - every initContainer in that template must have
    `allowPrivilegeEscalation: false` and `capabilities.drop` containing
    `ALL` (root via explicit `runAsUser: 0` is allowed, implicit is not).
- Fails if it finds zero agent-image templates (guards against the glob or the
  image expression silently changing).
- `--selftest` builds fixtures in a `tempfile.TemporaryDirectory`: one
  hardened template (must pass) and variants with the pod block removed, with
  `allowPrivilegeEscalation` removed, and with `capabilities.drop` removed
  (each must fail). Accepts a `--dir` override so selftest points at the
  fixtures.
- Wired into `.github/workflows/validate-manifests.yml` next to
  "Validate Argo local workdir invariants":
  `scripts/validate-agent-pod-security.py --selftest` then
  `scripts/validate-agent-pod-security.py`.

## Alternatives

1. **Workflow-level `spec.securityContext` (+ `podSpecPatch`).** One block
   per file, but it applies to every pod in the workflow, including the root
   `alpine/git` `commit-and-push` and `alpine` `notify-telegram` steps that
   run `apk add`; those would break or each need overrides. Template-level is
   the narrower, more explicit choice. `podSpecPatch` is a JSON string that
   the validator and reviewers cannot read structurally.
2. **Make `clone-gitops` fully non-root now** (drop `apk add`, `HOME=/tmp`,
   rely on `fsGroup`, remove `chown`). Cleaner and PSS-restricted compliant,
   but rewrites a clone step that five templates and
   `validate-local-workdir.py` depend on, and couples a security tightening
   with a functional change. Deferred to a follow-up that must precede any
   `enforce: restricted`.
3. **Namespace PSS `enforce: restricted` / k3s `seccompDefault`.** Explicitly
   out of scope; would affect every platform workflow in `argo-workflows`
   (deploy-service, create-tenant, ...) and every pod on the nodes.

## Platform impact

- **No migration.** Argo snapshots templates at submit time; in-flight
  workflows keep the old spec, new submissions pick up the new one after
  ArgoCD syncs (~3 min, per CLAUDE.md).
- **Backward compatibility:** effective agent uid/gid is unchanged (1000). A
  future `agent_image` built with a different `USER` will still be forced to
  1000; an image that needs root will now fail fast instead of silently
  running privileged — intended.
- **Risks and mitigations:**
  - `apk add` / `chown` in the root initContainer failing because of the
    capability drop: start with the five-capability add list; verify with one
    real run per template before trimming.
  - Agent tooling relying on a capability (e.g. `ping`, binding <1024) or a
    syscall blocked by RuntimeDefault (Go/Zig toolchain, `uv`): RuntimeDefault
    on containerd allows the normal build syscalls; the acceptance runs
    (implement on a Go service such as mctl-telegram if possible) catch it.
  - `fsGroup` recursive chown of the 10Gi emptyDir: emptyDir is empty at pod
    start, so the ownership walk is trivial.
  - The Secret volumes become group-readable by gid 1000; `deploy-key` is
    mounted only in `clone-gitops`, `github-token-file` is already intended
    for the agent.
- **Resource impact:** none.
