# Tasks: issue-830-spike-what-runtime-observability-and-egr

- [ ] 1. Re-verify the evidence at implementation time. Check the open/merged state of mctl-gitops#2161
  and #2163, and the stage table in `docs/runbooks/mctl-agents-egress.md`. Check the
  `HTTPS_PROXY` presence per `cwft-mctl-agents-*.yaml`, the Squid `access_log`/`http_access` lines in
  `infra-components/mctl-platform/mctl-agents-egress-proxy/proxy.yaml`, and the PR #810 head SHA.
  Check `orchestrator/options.py` `_audit_pre_tool_use`/`_command_audit_hooks` line numbers. — DoD:
  every citation in the report matches the current trees, or the report says what changed.
- [ ] 2. (depends on 1) Write `docs/spikes/830-runtime-egress-detection.md`. It has these sections:
  1. Source and limits (article cited, live state not observed).
  2. Escape-path matrix with rows X1 to X7. The columns are
     `id | path | layer | signal | producer | attribution | state | unblocked_by | follow_up`, and the
     state vocabulary is `emitted | partial | missing | blind | out-of-scope`.
  3. Egress policy and runtime audit plan ordered by proxy stage A, B, C, including the
     package-registry decision for stage B and the residual risk.
  4. Decision, with `STATUS: DRAFT` and recommended token `ADOPT_PLAN` (allowed: `ADOPT_PLAN`,
     `ADOPT_SUBSET`, `RESEARCH_ONLY`).
  5. Follow-ups F1 to F6 as draft issue bodies, each with `Repo:`, priority, dependency, scope and
     rollback.

  — DoD: the report states that X2 cannot be detected before stage C. Every proposed signal states
  its run attribution. No proposed telemetry carries argv, hostnames or tool arguments as attributes
  or labels.
- [ ] 3. (depends on 2) In the matrix, cross-reference #852 rows N1, D1-WebSearch and D1-WebFetch, and
  #807 G1 and G2. Note that #854 has no egress gap. Do not edit the #852 or #854 reports. — DoD: X1,
  X2 and X4 cite `#852`, and the report names `N1`.
- [ ] 4. (depends on 2) List every unobserved source under a "Not observed" subsection: the live Squid
  log, the Loki ruler, kube-router drop logging, the CoreDNS log plugin, executor egress, and the
  `mctl_get_workflow_logs` versus Promtail `argo-workflows` ingestion discrepancy. — DoD: no unobserved
  source is reported as absent.
- [ ] 5. (depends on 2) Add `tests/test_spike_830_report.py`, modelled on
  `tests/test_spike_852_report.py`. — DoD: the tests T1 to T5 below pass under
  `uv run pytest tests/test_spike_830_report.py`.
- [ ] 6. (depends on 5) Run `uv run pytest tests/test_spike_830_report.py tests/test_spike_852_report.py
  tests/test_tracing_coverage.py` and the repo's lint and type-check targets. — DoD: all green, and no
  file outside `docs/spikes/` and `tests/` is changed.

## Tests

- [ ] T1. `test_status_line`: there is exactly one `STATUS:` line, and its value is `DRAFT` or one of
  `ADOPT_PLAN`, `ADOPT_SUBSET`, `RESEARCH_ONLY`.
- [ ] T2. `test_matrix_rows`: every row of the escape-path matrix has 9 cells, a non-empty producer
  and a non-empty attribution, and a state in `{emitted, partial, missing, blind, out-of-scope}`. Ids
  X1 to X7 are all present.
- [ ] T3. `test_cross_references`: the report mentions `#852`, `N1`, `#807` and `G1`, and row X2's
  `unblocked_by` names stage C.
- [ ] T4. `test_follow_ups`: every `### F<n>` heading is followed, within its section, by a `Repo:`
  line naming `mctl-agents` or `mctl-gitops`, and by a `Rollback` line.
- [ ] T5. `test_no_token_shaped_strings`: the report contains none of `ghp_`, `gho_`, `github_pat_`,
  `sk-ant-` or `-----BEGIN`.

## Rollback

The change is docs and tests only, so reverting the PR removes
`docs/spikes/830-runtime-egress-detection.md` and `tests/test_spike_830_report.py`. No runtime,
gitops or profile state depends on them, and no follow-up is filed by this PR.
