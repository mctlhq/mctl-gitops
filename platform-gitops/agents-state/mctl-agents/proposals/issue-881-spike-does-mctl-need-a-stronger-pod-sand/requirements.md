# Spike #881: does DevLoop need a stronger pod sandbox than hardened runc (gVisor, Kata or Firecracker)?

## Context

DevLoop agent steps (`mctl-agents-implement`, `mctl-agents-investigate`) run model-driven shell against
untrusted repository content, issue text and tool output. Spike #852 (`docs/spikes/852-sandbox-isolation-delta.md`)
mapped the "kernel sharing" category to #807 gap G5 ("no sandbox runtime") and left the runtime choice to a
separate owner decision. Today those steps run under the default runc handler of the k3s-embedded containerd,
with a restricted posture added by mctl-gitops#1717. That posture is non-root uid 1000, `seccompProfile: RuntimeDefault`,
`capabilities.drop: [ALL]`, `allowPrivilegeEscalation: false`, `automountServiceAccountToken: false` and a
per-pod `emptyDir`. The workers are Hetzner Cloud `cx43` VMs (`mctl-preprod-worker-cx43-fsn1-*`) on k3s 1.34.

The issue asks for a bounded spike, not a rollout. The spike first checks whether stronger kernel isolation
reduces a real MCTL threat that #807 follow-ups (egress, short-lived credentials, PSA, quotas) and the #852
follow-ups (#868, #869, #870) do not already cover. It then checks which candidates the current substrate
can run at all: Kata and Firecracker need `/dev/kvm`. It measures the candidates that can actually be
exercised on a disposable environment and records exactly one outcome:
`KEEP_HARDENED_RUNC | ADOPT_GVISOR | ADOPT_KATA | ADOPT_FIRECRACKER | DEFER_NEEDS_KVM_NODEPOOL`.

## User stories

- AS the platform owner I WANT a measured, evidence-backed answer to #807 G5 SO THAT I can decide whether
  to adopt a sandbox runtime without guessing about compatibility, cost or KVM availability.
- AS a DevLoop operator I WANT a compatibility scorecard for real DevLoop operations under each candidate
  runtime SO THAT a later opt-in rollout does not break implement or investigate runs.
- AS a security reviewer I WANT a threat-to-control map SO THAT I can see what a sandbox runtime fixes
  after #807/#852 hardening and what it does not fix.
- AS a cost owner I WANT an explicit cost and operations delta for any KVM-capable node pool SO THAT a VM
  runtime is never recommended at an unstated price.

## Acceptance criteria (EARS)

- WHEN the spike is complete THE SYSTEM SHALL provide `docs/spikes/881-pod-sandbox-runtime.md` with exactly
  one `STATUS:` line whose value is `DRAFT` or one of the five outcome tokens.
- WHEN the report is written THE SYSTEM SHALL include a host/runtime feasibility matrix covering runc,
  gVisor (runsc), Kata (with QEMU or Cloud Hypervisor as VMM), Kata with Firecracker as VMM, and direct
  firecracker-containerd as separate rows. Each row SHALL record the k3s/containerd integration point
  (runtime handler in the k3s containerd config template plus a `RuntimeClass`), the KVM requirement and
  whether it was observed.
- WHEN the report is written THE SYSTEM SHALL include a threat-to-control map. Each threat row SHALL name
  the controls that already address it (#807 G1-G4/G6, #830, #852 follow-ups #868/#869/#870) and state
  whether a sandbox runtime adds material reduction.
- IF the threat-to-control map shows no material reduction from kernel isolation THEN THE SYSTEM SHALL
  allow the report to conclude `KEEP_HARDENED_RUNC` without running the gVisor benchmark, and SHALL state
  that the measurement phase was skipped by the first gate.
- WHEN the gVisor comparison runs THE SYSTEM SHALL execute the same compatibility fixture under runc and
  under the `gvisor` RuntimeClass on a disposable k3s cluster at the production minor (1.34). The fixture
  SHALL use the production agent image and the implement step's pod securityContext. Results SHALL be one
  pass/fail row per operation: git/gh, uv/pytest/mypy/ruff, npm, `go test` with and without `-race`, a C
  compile, emptyDir workdir, DNS, HTTPS direct and via proxy, Argo executor (init/wait/emissary) behaviour,
  log/artifact collection and cancellation.
- WHEN an operation fails under a candidate THE SYSTEM SHALL record the failing syscall, filesystem or
  network behaviour explicitly, not just "fail".
- WHEN performance is measured THE SYSTEM SHALL report sandbox/pod startup p50 and p95, fixture wall-clock
  delta, CPU, peak RSS, disk I/O overhead and failure/retry rate, each with the run count and run id.
- WHEN negative probes run THE SYSTEM SHALL use only safe, read-only probes: kernel version as seen by the
  workload, `/dev` visibility, `/proc` and `/sys` host information exposure, and mount and namespace view.
  It SHALL NOT use exploit code or attempt a container escape.
- IF `/dev/kvm` and the vmx/svm CPU flag were not observed on an MCTL worker THEN THE SYSTEM SHALL record
  Kata and Firecracker as infeasible on the current pool and SHALL NOT present any number for them as
  measured on MCTL hosts.
- IF a VM runtime still looks justified after the KVM gate THEN THE SYSTEM SHALL record the cost and
  operations delta of a dedicated KVM-capable node pool, with any unknown price written as "unknown", never
  as zero. Running a VM-runtime benchmark SHALL require a separate, recorded owner approval.
- WHILE the spike runs THE SYSTEM SHALL NOT modify production nodes, the production containerd
  configuration, the default runtime, CWFTs in mctl-gitops, or the worker pool size or type.
- WHEN a candidate is recommended THE SYSTEM SHALL describe its rollout as opt-in per agent workload through
  a `RuntimeClass` (`runtimeClassName` on the CWFT template). runc SHALL stay available for rollback and for
  workloads that cannot run under the sandbox.
- WHEN the report is merged THE SYSTEM SHALL have a guard test, `tests/test_spike_881_report.py`, that checks
  the status token, the matrix and scorecard row shape, non-empty evidence cells, the rule that VM rows are
  not marked measured without observed KVM, and the absence of token-shaped strings.

## Out of scope

- Any production rollout, default RuntimeClass switch, worker rescale or new node purchase.
- Reopening #807 G1-G4/G6 (RBAC, NetworkPolicy, credentials, PSA, quotas) or the #852 follow-ups.
- Building a custom sandbox orchestrator, a second agent runtime or a control plane.
- Migrating non-DevLoop Kubernetes workloads to another runtime.
- Exploit development, production escape testing, or weakening pod security so that a candidate passes.
- Provisioning a paid KVM-capable host without a separate owner gate.

## Open questions

- KVM availability on the current `cx43` workers has not been observed. The provider documents shared-vCPU
  cloud servers as having no nested virtualization, but the issue requires observation. A read-only check
  (`ls -l /dev/kvm`, `grep -cE 'vmx|svm' /proc/cpuinfo`) needs either an operator shell on a worker or a
  short-lived node-debug pod in production. Which one the owner permits is open. If neither is permitted,
  the matrix records "not observed" and Kata and Firecracker stay infeasible by default.
- Whether a GitHub-hosted runner is an acceptable "disposable environment matching k3s/containerd as closely
  as practical" for the gVisor comparison, or whether the owner prefers a disposable Hetzner cx43 matching
  the production instance type. That option is a paid resource and needs an owner gate. This proposal uses
  the free runner by default and records the difference in CPU model and kernel as a known limit.
- Which DevLoop agent the first opt-in follow-up would target (implement versus investigate) if gVisor wins.
  The default is implement, because it runs the most untrusted code (builds and tests).
- Whether nodes shared with other tenant workloads and Vault (single cluster) is an accepted risk or a hard
  requirement. This drives the weight of the kernel-escape threat at the first gate.
