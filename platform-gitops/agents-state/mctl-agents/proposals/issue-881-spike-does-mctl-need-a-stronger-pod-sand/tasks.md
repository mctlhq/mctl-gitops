# Tasks: issue-881-spike-does-mctl-need-a-stronger-pod-sand

- [ ] 1. Record substrate facts in `docs/spikes/881-pod-sandbox-runtime.md` `## 1` and `## 2`. Facts: k3s
  patch version, containerd version, node kernel, worker type `cx43`, and `/dev/kvm` plus vmx/svm presence
  from a read-only operator check, if the owner permits it. — DoD: every fact cites its source. Facts that
  were not observed are written "not observed", and K1/K2/F1/G2 are marked `infeasible-no-kvm` unless
  KVM was observed.
- [ ] 2. Write the feasibility matrix with rows R0, G1, G2, K1, K2 and F1. Each row names the exact
  k3s integration point: the `config.toml.tmpl` runtime handler, plus a `RuntimeClass` with `handler` and
  an optional `scheduling.nodeSelector`. (depends on 1) — DoD: K2 (Kata+Firecracker VMM) and F1 (direct
  firecracker-containerd) are separate rows, and each row has evidence.
- [ ] 3. Write the threat-to-control map with rows T1-T8, mapping each threat to #807 G1-G4/G6, #830 and
  #868/#869/#870, and apply the threat gate. — DoD: every row states whether a sandbox runtime reduces the
  threat. The gate verdict is written down. If it fails, the report goes straight to task 7 with
  `KEEP_HARDENED_RUNC`.
- [ ] 4. Add `experiments/sandbox-runtime-881/`:
  - `fixture/run-fixture.sh` with vendored tiny Python, Node, Go and C fixtures;
  - `probes/negative-probes.sh`;
  - `k8s/runtimeclass-gvisor.yaml`;
  - `k8s/containerd-config.toml.tmpl.patch`;
  - `k8s/fixture-workflow.yaml`, mirroring the implement template's securityContext, emptyDir and
    limits, with `runtimeClassName` parameterised;
  - `k8s/squid.yaml`;
  - `collect.py`;
  - a `README.md`.

  Add `.github/workflows/spike-881-sandbox.yml` (`workflow_dispatch` only, `contents: read`, pinned k3s
  v1.34.x, gVisor and Argo chart 0.47.5 with checksums). (depends on 3 passing the gate) — DoD: a local
  dry run of `collect.py` on sample output produces the scorecard table. The workflow lints clean.
- [ ] 5. Dispatch the workflow and run N=10 alternating runc/gVisor passes. Commit
  `docs/spikes/881/measurements/` with the run id and head SHA. (depends on 4) — DoD: the scorecard (`## 4`),
  performance (`## 5`) and negative probes (`## 6`) are filled from that run. Every `fail` names the
  syscall, filesystem or network behaviour.
- [ ] 6. Write the cost and operations delta (`## 7`). Cover the containerd template surviving k3s/SUC
  upgrades, the rollback path, observability changes, and, if a VM runtime is still justified, the
  dedicated KVM-capable pool size and monthly price, with any unknown price written as "unknown". (depends
  on 2, 3, 5) — DoD: no blank cost cells, and no cost written as zero without a source.
- [ ] 7. Write `## 8. Decision`: set `STATUS:` to `DRAFT` pending the owner, and propose exactly one
  outcome token and at most one follow-up for a proven winner or gap. For example: an mctl-gitops issue to
  add a `gvisor` RuntimeClass and set `runtimeClassName` opt-in on the implement agent template only.
  (depends on 3, 5, 6) — DoD: the token is one of the five, and the follow-up keeps runc as the default
  and the rollback.
- [ ] 8. Add `tests/test_spike_881_report.py`. (depends on 7) — DoD: `uv run pytest
  tests/test_spike_881_report.py` passes.

## Tests

- [ ] T1. `STATUS:` appears once and its value is in {`DRAFT`, `KEEP_HARDENED_RUNC`, `ADOPT_GVISOR`,
  `ADOPT_KATA`, `ADOPT_FIRECRACKER`, `DEFER_NEEDS_KVM_NODEPOOL`}.
- [ ] T2. Feasibility matrix rows have 8 cells, non-empty evidence, and a `status` in {`measured`,
  `infeasible-no-kvm`, `not-exercised`}. Rows K2 and F1 are both present.
- [ ] T3. No row with `needs_kvm=yes` and `kvm_observed` not equal to `yes` has `status=measured`.
- [ ] T4. Threat rows T1-T8 are present with 5 cells each, and `sandbox_reduces` is non-empty.
- [ ] T5. Scorecard cells match `pass`, `fail:<text>` or `not-exercised`. If STATUS is `ADOPT_KATA` or
  `ADOPT_FIRECRACKER`, the matching column contains no `not-exercised`.
- [ ] T6. The report contains no token-shaped strings (`ghp_`, `gho_`, `github_pat_`, `sk-ant-`,
  `-----BEGIN`).
- [ ] T7. `collect.py` unit check on a canned fixture output: it produces the expected JSON and markdown
  rows, including a `fail:` entry carrying the stderr tail.

## Rollback

The spike changes only this repository: a docs report, a `experiments/sandbox-runtime-881/` harness, one
manually dispatched workflow and one guard test. To roll back, revert the PR. Nothing in production, in
mctl-gitops, on the nodes or in the containerd configuration is touched, so nothing needs undoing there.
The disposable k3s cluster lives only for the length of the GitHub runner job. Any later adoption is a
separate, opt-in `runtimeClassName` change with runc as the default and the rollback.
