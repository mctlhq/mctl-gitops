# Tasks: issue-1096-spike-devloop-evaluate-claude-code-code

**Disposition: CHANGES REQUESTED — RESEARCH INTAKE ONLY.** This is a revision
of the GitOps *proposal*, not an authorization to execute the proposed tasks.
Do NOT call Temporal approval; it triggers the implementer. No target-repo PR,
fixture generation, CLI Code Mode run, config toggle, deployment or merge.

## Authorized research/review work (in the PROPOSED intake)

- [x] R1. Inspect the MCTL headless SDK architecture, hooks, policy checkpoint,
  durable decision records and capability gateway at the pinned repository
  revision. Findings are documented in `design.md`; unobserved interactive
  operator hooks remain `UNKNOWN`.
- [x] R2. Map the six orchestration surfaces and issue ownership. Interactive
  Claude Code Mode is not treated as a current headless DevLoop arm; #597 owns
  benchmark reports; #63 remains PARK/M8 FAIL.
- [x] R3. Define the candidate offline, read-only three-task experiment protocol
  (3 tasks x 2 CLI modes x >=5 reps = 30 planned runs), independent oracles,
  negative scenarios and metrics. Every run remains `NOT_RUN`.
- [x] R4. Record the P1/P2/P3 corrections and non-substitution requirements
  in `requirements.md` and `design.md`.
- [ ] R5. Re-fetch first-party Claude Code documentation before any *final*
  compatibility verdict. The current investigator did not independently fetch
  it; statements inherited from the issue must remain `VENDOR_CLAIM` or
  `UNKNOWN` rather than observed results.
- [ ] R6. Independent reviewer confirms the revised proposal is research-only,
  that no source claims were promoted without evidence, and that code/PR
  tasks are not authorized.

## Candidate future execution — separate explicit owner GO required

This section is a **scope proposal**, not a Tier-2 work queue.

- [ ] F1. If approved separately, write the docs-only spike report
  `docs/spikes/1096-claude-code-code-mode.md`, plus
  `docs/spikes/1096/{protocol,negative-matrix,surface-matrix}.yaml`.
  All experiment-result and negative-test fields start `NOT_RUN`.
- [ ] F2. If approved separately, add an offline YAML structural check. Static
  fixture files contain no secret-shaped values; any adversarial canary must
  be created in RAM and checked for absence in output/durable evidence.
- [ ] F3. Only after a **separate benchmark GO** that pins model, CLI build,
  permission profile, owner/account, fixtures, sample plan and USD cap:
  consider synthetic/offline task runs. Real MCTL access remains blocked
  until per-child server-side policy/audit enforcement is demonstrated.
- [ ] F4. After actual approved measurements, request a new independent
  decision review. `FURTHER_RESEARCH` is provisional, not a benchmark PASS.

## Acceptance gates

- [ ] Every vendor/implementation claim has a pinned URL/date or repository
  path/commit and evidence class; unsupported statements are `UNKNOWN`.
- [ ] Each child call's proposed contract has stable parent/call IDs, sealed
  actor/tenant, exact argument digest, action-time decision ID, outcome and
  durable trace link; absent evidence is `UNPROVEN`/DENY.
- [ ] All unexecuted cells remain `NOT_RUN`; 5-rep exploratory p95 does
  not constitute proof of performance or safety.
- [ ] No implementation file, test, production service, organization/CLI
  setting, portal mode or `.status.yaml` approval changes as a result
  of this research-only proposal.

**Rollback:** Revert the GitOps proposal-review amendment if required.
No runtime or benchmark state is changed.
