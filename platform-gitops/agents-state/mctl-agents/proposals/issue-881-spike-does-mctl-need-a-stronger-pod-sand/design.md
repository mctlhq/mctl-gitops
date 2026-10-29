# Design: issue-881-spike-does-mctl-need-a-stronger-pod-sand

## Current state

DevLoop agent steps are Argo `ClusterWorkflowTemplate`s in mctl-gitops. Their posture, read from the
gitops checkout:

- `argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`, agent template:
  - `serviceAccountName: mctl-agents-runner` with `automountServiceAccountToken: false`. Only the
    Argo executor gets a token, through `executor.serviceAccountName: mctl-agents-executor`.
  - Pod `securityContext`: `runAsNonRoot: true`, `runAsUser/runAsGroup/fsGroup: 1000`,
    `seccompProfile: RuntimeDefault` (comment cites mctl-gitops#1717).
  - Agent container: `allowPrivilegeEscalation: false`, `capabilities.drop: ["ALL"]`, image
    `{{workflow.parameters.agent_image}}`.
  - Resources: requests `200m/3Gi/10Gi ephemeral`, limits `3000m/8Gi/11Gi ephemeral`.
    `activeDeadlineSeconds: 7200`.
  - The workdir is a per-pod `emptyDir` (spec-level, "no shared workdir volume").
  - A root clone init container (`alpine/git:2.43.0`) has escalation off and adds back only
    `CHOWN, DAC_OVERRIDE, FOWNER, SETGID, SETUID`.
  - Egress goes through `HTTPS_PROXY`/`http_proxy` (Squid, per #830).
- `argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml`: the same pattern (`runAsNonRoot`,
  `seccompProfile`, `emptyDir`, `activeDeadlineSeconds: 7200`).
- No `RuntimeClass` exists. A search for `kind: RuntimeClass`, `runtimeClassName`, `runsc`, `gvisor` and
  `kata` in mctl-gitops `platform-gitops/` and in this repository returns nothing. Every agent pod
  therefore runs under the k3s-embedded containerd's default runc handler and shares the node kernel.
- Substrate: workers are `mctl-preprod-worker-cx43-fsn1-{ftx,hnn,xgf}`
  (`bootstrap/templates/core-infra/local-path-provisioner.yaml`). The cluster is k3s 1.34
  (`argocd/values.yaml` comment on the #2068 upgrade, `bootstrap/templates/core-infra/descheduler.yaml`).
  containerd is the k3s-embedded one at `unix:///run/k3s/containerd/containerd.sock`
  (`bootstrap/templates/core-infra/image-prune.yaml`). Argo Workflows chart is `0.47.5`
  (`bootstrap/templates/core-infra/argo-workflows.yaml`).
- Agent image (`Dockerfile` in this repo): `python:3.12-slim` base with `gcc`/`libc6-dev` (for Go cgo and
  `-race`), NodeSource `nodejs`, `gh`, pinned `uv` 0.11.11, and a pinned Go toolchain. These are exactly the
  toolchains the fixture must exercise.
- Prior analysis in this repo:
  - `docs/spikes/852-sandbox-isolation-delta.md` maps K1 "shared node kernel" to #807 G5 and lists the
    in-process gaps D1-WebSearch (#870), D2 audit-only Bash (#869) and D3 project settings from target
    clones (#868). None of these is a kernel-isolation problem.
  - `docs/spikes/830-runtime-egress-detection.md` covers egress detection.
  - Spike reports are guarded by tests such as `tests/test_spike_852_report.py`, which checks the
    `STATUS:` token, the table row shape and token-shaped strings.
  - Measured spikes keep their harness under `experiments/` and run it from a manually dispatched workflow
    (`experiments/portable-runtime-rs/`, `.github/workflows/portable-runtime-spike.yml`,
    `docs/spikes/746-portable-runtime.md`).

Deployed state checked:
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`: securityContext,
  SA, emptyDir, resources and proxy env as listed above. No `runtimeClassName`.
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml`: same pattern.
  No `runtimeClassName`.
- `grep -rn "kind: RuntimeClass"` over `$MCTL_GITOPS_ROOT`: no match.
- `$MCTL_GITOPS_ROOT/bootstrap/templates/core-infra/local-path-provisioner.yaml`: three `cx43` worker
  names in `fsn1`.
- `$MCTL_GITOPS_ROOT/argocd/values.yaml` and `bootstrap/templates/core-infra/descheduler.yaml`: k3s 1.34.
- `$MCTL_GITOPS_ROOT/bootstrap/templates/core-infra/argo-workflows.yaml`: chart `0.47.5`.
- `$MCTL_GITOPS_ROOT/argo-workflows/config/networkpolicy.yaml`: an ingress allow policy for the Argo
  namespace. Egress posture is tracked under #807 G1 and is not re-derived here.
- Not observed:
  - Exact k3s patch and containerd versions on the live nodes.
  - Whether `/dev/kvm` exists on the workers, and the vmx/svm CPU flag.
  - The live node kernel version.
  The mctl MCP tools in this run are read-only service/tenant views and do not expose node facts. The
  Terraform for the cluster (`infrastructure/k3s-preview/kube.tf`, referenced from
  `argo-workflows/config/stuck-pv-janitor.yaml`) is outside the `platform-gitops/` checkout available to
  this run. These gaps are recorded under Open questions and become task 1.

## Proposed solution

A docs-plus-experiment spike in this repository, following the #746/#852 conventions. Nothing changes in
mctl-gitops or on any production node.

### Deliverables in `mctl-agents`

1. **`docs/spikes/881-pod-sandbox-runtime.md`**, with these sections:
   - `STATUS:` line: `DRAFT` until the owner decides, then exactly one outcome token.
   - `## 1. Source and limits`: what was observed and what was not, with run ids and head SHA.
   - `## 2. Feasibility matrix`, one row per integration path. Columns: `id | runtime | vmm | needs_kvm |
     kvm_observed | k3s_integration | status | evidence`. Rows:
     - R0 runc (baseline).
     - G1 gVisor runsc, systrap platform (no KVM needed).
     - G2 gVisor runsc, KVM platform.
     - K1 Kata with QEMU or Cloud Hypervisor.
     - K2 Kata with Firecracker VMM (devmapper snapshotter required).
     - F1 direct firecracker-containerd.

     K2 and F1 are separate rows, as the issue requires. `k3s_integration` names the exact point: a
     runtime handler added through `/var/lib/rancher/k3s/agent/etc/containerd/config.toml.tmpl` (or k3s
     alternative-runtime auto-detection where it applies, to be verified for the k3s 1.34 build) plus a
     `node.k8s.io/v1 RuntimeClass` with `handler`, and `scheduling.nodeSelector` when the runtime is only
     on some nodes. `status` is in {`measured`, `infeasible-no-kvm`, `not-exercised`}.
   - `## 3. Threat-to-control map`. Columns: `id | threat | existing_controls | sandbox_reduces | residual`.
     Rows:
     - T1 kernel or container-runtime escape to the node, and from there to co-located tenant pods, Vault,
       kubelet credentials and other pods' emptyDirs. Only a sandbox runtime reduces this.
     - T2 credential exfiltration over egress: #807 G1/G2, #830. The sandbox does not reduce it.
     - T3 repository-supplied hooks and settings: #868. The sandbox does not reduce it (in-pod).
     - T4 Kubernetes API lateral movement: `automountServiceAccountToken: false`, #807 G3/RBAC. The
       sandbox does not reduce it.
     - T5 shell misuse inside the pod: #869. The sandbox does not reduce it.
     - T6 node resource exhaustion and noisy neighbour: #807 G6 and limits. The sandbox gives partial
       reduction (VM memory overhead accounting).
     - T7 provider-side WebSearch exfiltration: #870. The sandbox does not reduce it.
     - T8 host information disclosure through `/proc`, `/sys` and the kernel version. The sandbox reduces
       it.

     The first gate passes only if T1 or T8 is judged material for MCTL's shared, multi-tenant cluster.
   - `## 4. Compatibility scorecard`. Columns: `op | runc | gvisor | kata | firecracker | notes`. Cells are
     in {`pass`, `fail:<behaviour>`, `not-exercised`}.
   - `## 5. Performance`: startup p50/p95, fixture wall-clock, CPU, peak RSS and I/O, each per runtime with
     N and run id.
   - `## 6. Negative probes`: expected and observed per runtime.
   - `## 7. Cost and operations delta`. Node mutation, upgrade and rollback burden (k3s upgrades rewrite
     the containerd config, so the template must survive SUC/k3s upgrades), observability (gVisor hides
     host-level process views), and the KVM pool cost. Any unknown price is written as "unknown".
   - `## 8. Decision`: one outcome token and, for a winner, one concrete follow-up issue. For example, an
     mctl-gitops change adding a `gvisor` RuntimeClass, a handler on the workers, and `runtimeClassName`
     on only the implement agent template, behind an explicit opt-in parameter.

2. **`experiments/sandbox-runtime-881/`**: the disposable harness.
   - `fixture/run-fixture.sh`: runs inside the production agent image as uid 1000 in an emptyDir workdir.
     It runs these steps and prints one JSON line per op with `op`, `ok`, `seconds` and `stderr_tail`:
     - `git clone` and `gh --version`
     - `uv venv` + `uv pip install pytest mypy ruff` from a local wheel cache
     - `pytest`, `mypy` and `ruff` on a tiny bundled package
     - `npm ci` on a tiny bundled lockfile
     - `go test ./...` and `go test -race ./...` on a tiny bundled module
     - `cc hello.c`
     - a large-file write/read for I/O
     - DNS lookup
     - `curl` HTTPS directly and through `HTTPS_PROXY`
     - a `sleep` target for the cancellation test

     Fixtures are vendored so that network use is limited to the explicit DNS/HTTPS ops.
   - `probes/negative-probes.sh`: read-only checks. `uname -r`, `ls /dev`,
     `/proc/{version,kallsyms,modules}` readability, `/sys/kernel` and `/sys/firmware` visibility,
     `/proc/self/mountinfo`, `cat /proc/1/cgroup`, and `ls -l /dev/kvm`. No exploit code.
   - `k8s/runtimeclass-gvisor.yaml`: a `RuntimeClass` named `gvisor` with handler `runsc`.
   - `k8s/containerd-config.toml.tmpl.patch`: the runsc handler stanza for the k3s template.
   - `k8s/fixture-workflow.yaml`: an Argo `Workflow` whose pod copies the implement template's
     securityContext, emptyDir and limits, with `runtimeClassName` parameterised. It exercises the
     executor init/wait path, output artifacts (to an in-cluster MinIO), log collection and
     `argo stop`/`terminate` cancellation.
   - `k8s/squid.yaml`: a minimal proxy pod for the proxy path.
   - `collect.py`: parses the JSON lines and pod timestamps (`PodScheduled`, then sandbox ready, then
     container started) into `measurements/<runtime>.json` and a markdown table. It is run with
     `python -I`.

3. **`.github/workflows/spike-881-sandbox.yml`**: `workflow_dispatch` only, on `ubuntu-latest`.
   1. Installs pinned k3s `v1.34.x`. Installs a pinned gVisor release (`runsc`, `containerd-shim-runsc-v1`)
      and verifies the published SHA-512.
   2. Applies the containerd template and restarts k3s. Installs Argo Workflows chart `0.47.5`.
   3. Builds the agent image from this repo's `Dockerfile` (or pulls the pinned production tag).
   4. Runs the fixture workflow N=10 times per runtime, alternating runtimes to reduce drift.
   5. Runs the probes, records `/dev/kvm` presence on the runner as informational only, and uploads
      `measurements/`.

   It holds no secrets, and its permissions are `contents: read`.

4. **`tests/test_spike_881_report.py`**: a guard in the `test_spike_852_report.py` style:
   - one `STATUS:` line with a value in `DRAFT` or the five tokens;
   - matrix rows have 8 cells with non-empty evidence, and `status` is in the allowed set;
   - every row with `needs_kvm=yes` and `kvm_observed` not equal to `yes` has `status` not equal to
     `measured`;
   - rows K2 and F1 are both present (the paths are distinct);
   - threat rows have 5 cells;
   - scorecard cells match `pass|fail:.+|not-exercised`;
   - no `ghp_|gho_|github_pat_|sk-ant-|-----BEGIN`.

### Gates and decision logic

1. **Feasibility gate (KVM).** An operator records `/dev/kvm` and the vmx/svm flag on one worker read-only,
   with the owner's permission. Without that, the matrix says `not observed`. If KVM is absent or not
   observed, rows K1, K2, F1 and G2 are `infeasible-no-kvm`.
2. **Threat gate.** Fill in the threat-to-control map. If only T2-T7 remain after the #807/#852 follow-ups
   and T1/T8 are judged non-material, the decision is `KEEP_HARDENED_RUNC` and measurement is skipped.
3. **gVisor measurement** (systrap platform, no KVM) on the disposable runner cluster.
4. **Decision.**
   - `ADOPT_GVISOR` if every fixture op that the implement and investigate steps need passes and the
     overhead is within the run's deadline headroom (`activeDeadlineSeconds: 7200`).
   - `DEFER_NEEDS_KVM_NODEPOOL` if a VM-grade boundary is judged necessary but KVM is unavailable. This
     comes with the cost and operations delta, and any VM benchmark is left to a separate owner gate.
   - Otherwise `KEEP_HARDENED_RUNC`.
   - `ADOPT_KATA` or `ADOPT_FIRECRACKER` only if KVM was observed on an MCTL host or on an owner-approved
     disposable KVM host, and was measured there.

## Alternatives

- **Desk-only recommendation (no experiment).** It is cheap but contradicts the issue's "measured
  scorecard" deliverable. gVisor's known gaps (some ioctls, `/proc` differences, ptrace, and I/O overhead
  from the gofer/directfs path) matter specifically for `go test -race`, npm and uv. Dropped.
- **Run the comparison on a disposable Hetzner cx43 with k3s.** This matches the production CPU and
  hypervisor exactly and would also observe KVM on the same instance type. But it is a paid resource, and
  the issue requires an owner gate for new nodes. It is kept as an optional, owner-gated variant of task 4.
  The default is the free GitHub runner, with the CPU and kernel difference recorded as a limit.
- **Test a RuntimeClass directly on a production worker with a canary pod.** This mutates the production
  containerd config and violates the "no node mutation" invariant. Dropped.
- **Kata or Firecracker on a GitHub runner, since it exposes `/dev/kvm`.** That would give a number that
  says nothing about MCTL hosts, and it invites a recommendation that assumes KVM where MCTL never
  observed it. It is allowed only after an explicit owner gate, and is labelled "non-MCTL host" in the
  report.

## Platform impact

- **Production:** none. There are no changes to mctl-gitops, nodes, CWFTs, the RuntimeClass or the worker
  pool. All new files live in this repo under `docs/`, `experiments/` and `tests/`, plus one
  manually-dispatched workflow.
- **CI cost:** one manual run of about 60-90 minutes on a free GitHub runner. Nothing is scheduled.
- **Supply chain:** k3s, gVisor and Argo artifacts are pinned by version and checksum, in the same spirit as
  the `Dockerfile`'s pinned uv and Go. The workflow has no secrets and is read-only.
- **Risks and mitigations:**
  - Runner versus cx43 mismatch: kernel, CPU and nested hypervisor differences skew performance numbers.
    Mitigation: report them as relative deltas with the environment table. Do not quote them as production
    timings.
  - k3s alternative-runtime detection may differ by version. Mitigation: use the explicit
    `config.toml.tmpl`, and record which path worked.
  - A false sense of safety: the report must state that a sandbox runtime is defence in depth. It does not
    replace the #868/#869/#870 fixes or the MCTL policy, approval and lifecycle controls.
  - Report drift: the guard test pins the report's shape and the KVM honesty rule.
- **Backward compatibility:** not applicable. Any follow-up rollout is opt-in through `runtimeClassName` on
  one CWFT template, with runc kept as the default and the rollback.
