# Tasks: issue-881-spike-does-mctl-need-a-stronger-pod-sand

The owner amendments in `requirements.md` are authoritative. In particular, the current DevLoop owns
**Phase A only**. It must not attempt to dispatch a workflow that does not yet exist on `main`.

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
  #868/#869/#870, and apply the threat gate. T1 is material when model-driven untrusted code can be
  co-located with other tenant/platform workloads on a worker while sharing the host kernel. T8 by itself
  does not force adoption. — DoD: every row states whether a sandbox runtime reduces the threat and the
  gate verdict is written down.

  **Early-exit branch:** if the threat gate fails, skip tasks 4-6, write the cost/operations note that no
  extra runtime is justified, set the proposed result to `KEEP_HARDENED_RUNC`, complete task 7 and task 8,
  and stop. No benchmark or measurement is required on this branch.

- [ ] 4. **Phase A only, threat gate passed:** add `experiments/sandbox-runtime-881/`:
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
  dry run of `collect.py` on canned/sample output produces the expected scorecard table and the workflow
  lints clean. **Do not dispatch this workflow in the Phase A PR.**

- [ ] 5. **Phase A report and handoff:** write `## 4`-`## 7` as a DRAFT measurement plan with explicit
  not-exercised cells where appropriate. Record the adoption gates before any measurement:
  - all critical DevLoop operations must pass under gVisor: git/gh, uv/pytest/mypy/ruff, npm,
    `go test`, `go test -race`, C compile, DNS/HTTPS/proxy, Argo executor, artifact/log collection and
    cancellation;
  - N=10 must have zero runtime-caused failures;
  - median representative fixture wall-clock overhead versus runc must be <=25%;
  - startup p50/p95, CPU, RSS and I/O deltas are reported but are not substitutes for the wall-clock gate;
  - `activeDeadlineSeconds: 7200` is only a safety ceiling, not an adoption criterion.

  Also cover the containerd-template upgrade/rollback burden and the dedicated KVM-capable pool cost if a
  VM-grade boundary remains justified. Any unknown price is written as "unknown". — DoD: no blank cost
  cells and no zero cost without a source.

- [ ] 6. **Create exactly one Phase B measurement follow-up only if the threat gate passed.** The follow-up
  must state that it starts after the Phase A PR is merged to `main`, then dispatches
  `.github/workflows/spike-881-sandbox.yml`, runs N=10 alternating runc/gVisor passes, commits
  `docs/spikes/881/measurements/` with run id + head SHA, fills the scorecard/performance/probes from that
  run and finalizes the outcome in a separate PR. It inherits every invariant and adoption gate from this
  proposal. — DoD: no paid/KVM host and no production mutation are authorized by this follow-up; a VM
  benchmark still requires a separate owner approval.

- [ ] 7. Write `## 8. Decision`:
  - if task 3 took the early exit, record proposed outcome `KEEP_HARDENED_RUNC` and explain why measurement
    was skipped;
  - if task 3 passed, leave `STATUS: DRAFT`, state that Phase B measurement is required before the final
    outcome, and link the one Phase B follow-up from task 6.
  — DoD: the report never claims `ADOPT_GVISOR`, `ADOPT_KATA` or `ADOPT_FIRECRACKER` without the required
  measurements; runc remains the default/rollback path.

- [ ] 8. Add `tests/test_spike_881_report.py`. — DoD: `uv run pytest tests/test_spike_881_report.py`
  passes. The guard must permit the explicit early-exit form and the Phase-A `DRAFT` form without requiring
  fabricated measurement rows.

## Phase B acceptance criteria (follow-up, not this DevLoop)

- [ ] B1. The Phase A workflow file is present on `main` before dispatch.
- [ ] B2. Run N=10 alternating runc/gVisor passes using the committed workflow; save run id and head SHA.
- [ ] B3. Populate compatibility, performance and negative-probe evidence from the run. Every failure names
  the syscall/filesystem/network behaviour when identifiable.
- [ ] B4. `ADOPT_GVISOR` is allowed only if every critical operation passes, runtime-caused failures are 0/10
  and median fixture wall-clock overhead is <=25% versus runc.
- [ ] B5. `ADOPT_KATA` or `ADOPT_FIRECRACKER` is allowed only after KVM was observed on an MCTL host or an
  owner-approved disposable KVM host and the candidate was actually measured there.
- [ ] B6. Open a separate results PR that changes the report from `DRAFT` to exactly one final outcome token.

## Tests

- [ ] T1. `STATUS:` appears once and its value is in {`DRAFT`, `KEEP_HARDENED_RUNC`, `ADOPT_GVISOR`,
  `ADOPT_KATA`, `ADOPT_FIRECRACKER`, `DEFER_NEEDS_KVM_NODEPOOL`}.
- [ ] T2. Feasibility matrix rows have 8 cells, non-empty evidence, and a `status` in {`measured`,
  `infeasible-no-kvm`, `not-exercised`}. Rows K2 and F1 are both present.
- [ ] T3. No row with `needs_kvm=yes` and `kvm_observed` not equal to `yes` has `status=measured`.
- [ ] T4. Threat rows T1-T8 are present with 5 cells each, and `sandbox_reduces` is non-empty.
- [ ] T5. For a final measured verdict, scorecard cells match `pass`, `fail:<text>` or `not-exercised`.
  Phase A `DRAFT` and the explicit `KEEP_HARDENED_RUNC` early exit may leave measurement cells
  `not-exercised`; they must not invent pass/fail evidence.
- [ ] T6. The report contains no token-shaped strings (`ghp_`, `gho_`, `github_pat_`, `sk-ant-`,
  `-----BEGIN`).
- [ ] T7. `collect.py` unit check on canned fixture output produces the expected JSON and markdown rows,
  including a `fail:` entry carrying the stderr tail.

## Rollback

Phase A changes only `mctl-agents`: a docs report, `experiments/sandbox-runtime-881/`, one manually
-dispatched workflow and one guard test. Revert that PR to roll back. It does not touch production,
mctl-gitops runtime manifests, nodes or containerd. Phase B is a separate measurement/results PR and is
independently revertible. Any later runtime adoption remains a separate opt-in `runtimeClassName` change
with runc kept as the default rollback path.
