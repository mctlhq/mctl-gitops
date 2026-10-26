# Tasks: issue-807-spike-which-kubernetes-primitives-rbac-n

- [ ] 1. Add fixtures under `tests/fixtures/agent_isolation/`: a minimal `platform-gitops`-shaped tree with
  one compliant agent CWFT (`mctl-agents-runner`, automount false, seccomp RuntimeDefault, drop ALL,
  `{{workflow.parameters.agent_image}}`, labels `app.kubernetes.io/name: mctl-agents`), one non-compliant
  CWFT, `sa-and-rbac.yaml`, an ingress-only `networkpolicy.yaml`, an optional egress-policy variant, a quota
  file, and two profiles (`network: approved-providers-only`). — DoD: fixtures load with
  `yaml.safe_load_all` and contain no real secret names beyond env var identifiers.
- [ ] 2. Implement `tools/agent_isolation_audit.py` (depends on 1). It has pure functions
  `load_inputs(root)`, `classify_templates(cwft_docs)`, `check_identity`, `check_pod_security`,
  `check_runtime_class`, `check_resources`, `check_credentials_env`, `check_egress`, `check_east_west`,
  `check_profile_network`, a `Row` dataclass `{primitive, scope, status, severity, source, field, detail,
  recommendation}`, and a `main()` with `--gitops-root` and `--format json|md`. — DoD: no imports from
  `orchestrator/`, and no network, subprocess or Kubernetes client. A missing input yields `not-observed`.
  Exit code is 0 on a successful audit whatever the findings, and 2 on unreadable input.
- [ ] 3. Add `tests/test_agent_isolation_audit.py` (depends on 2). — DoD: covers T1-T7 below and passes
  under `uv run pytest`.
- [ ] 4. Run the auditor against the current mctl-gitops `platform-gitops/` and record the gitops commit SHA
  (depends on 2). — DoD: the JSON and Markdown outputs are captured into the report. The rows match the
  "Deployed state checked" evidence in design.md, or any difference is explained.
- [ ] 5. Write `docs/spikes/807-agent-isolation-k8s.md` (depends on 4). Sections: Environment and versions;
  Primitive catalogue (RBAC/SA tokens, NetworkPolicy egress, east-west, Pod Security / PSA,
  readOnlyRootFilesystem, RuntimeClass sandbox, ResourceQuota/LimitRange/limits/deadlines/concurrency,
  credential exposure); Current-state matrix; Ranked gaps G1-G6; Layering with ADR 011/014/017 app-layer
  controls; Follow-ups; Open questions (CNI, live namespace labels, Temporal worker shell use, legitimate
  egress inventory, #747/#670 overlap); Decision. — DoD: every matrix row cites a source path. Rows that
  could not be read say `not-observed`. The Decision section carries `STATUS: DRAFT` or exactly one of
  `NO_CHANGE`, `HARDEN_IN_PLACE`, `DEDICATED_AGENT_NAMESPACE`, `SANDBOX_RUNTIME_REQUIRED`.
- [ ] 6. Draft follow-up issue bodies in the report's Follow-ups section (depends on 5): (a) default-deny
  egress NetworkPolicy for `app.kubernetes.io/name: mctl-agents` with an allowlist and an FQDN-or-proxy
  choice; (b) env tokens to short-lived file-mounted or proxy-injected credentials; (c) east-west narrowing,
  including the Vault netpol selector; (d) PSA `restricted` on agent pods via a dedicated namespace, plus
  `readOnlyRootFilesystem`; (e) agent-namespace ResourceQuota/LimitRange; (f) gVisor RuntimeClass evaluation;
  (g) run the auditor in mctl-gitops CI. — DoD: each has a target repo, the files to change, an
  expected-traffic list where relevant, and a rollback note.
- [ ] 7. Add `tests/test_spike_807_report.py`, modelled on `tests/test_spike_796_report.py` (depends on 5).
  — DoD: the guard enforces the draft-or-one-token rule, checks that no file under `orchestrator/`,
  `config/` or `agents/_manifests/` changed versus the merge base, and checks that every matrix table row has
  a non-empty source column.
- [ ] 8. Link the report from issue #807 and add a CHANGELOG-neutral PR description (depends on 5-7).
  — DoD: the PR lists the decision token (or DRAFT) and the follow-up issues.

## Tests

- [ ] T1. A compliant fixture CWFT produces `enforced` rows for identity, seccomp, drop ALL and privilege
  escalation, and `absent` for `runtimeClassName` and `readOnlyRootFilesystem`.
- [ ] T2. An ingress-only NetworkPolicy fixture produces an `absent` egress row with severity `high`, plus a
  `declared-not-enforced` row for each profile declaring `approved-providers-only`.
- [ ] T3. Adding a fixture NetworkPolicy with `policyTypes: [Egress]` and `podSelector.matchLabels`
  `app.kubernetes.io/name: mctl-agents` flips the egress row to `enforced` and removes `declared-not-enforced`.
- [ ] T4. A fixture CWFT missing `capabilities.drop: [ALL]` or using `argo-workflow-sa` on an agent step is
  reported with the template name and the missing field.
- [ ] T5. Deleting `networkpolicy.yaml` from the fixture tree yields `not-observed`, never `absent`.
- [ ] T6. The credentials check lists env var names from `secretKeyRef` and never outputs a value. A fixture
  with a literal `value:` secret-like string still prints only the name.
- [ ] T7. The auditor makes no network or subprocess calls: `socket.socket` and `subprocess.run` are
  monkeypatched to raise, and the audit still succeeds. Output is deterministic (same input, byte-identical
  JSON).
- [ ] T8. `tests/test_spike_807_report.py` passes on the committed report.

## Rollback

Everything is additive and isolated: one tool, its fixtures and tests, one report, one guard test. Rollback
is a revert of the spike PR. No runtime code, manifest, profile, CWFT or cluster object is touched, so
nothing needs to be undone in mctl-gitops or the cluster. If the report's gap detail is judged too sensitive
before G1 is fixed, revert or redact only `docs/spikes/807-agent-isolation-k8s.md`, keep the auditor, and
reintroduce the report after the egress follow-up lands.
