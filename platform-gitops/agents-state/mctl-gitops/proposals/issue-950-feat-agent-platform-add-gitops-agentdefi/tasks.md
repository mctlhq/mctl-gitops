# Tasks: issue-950-feat-agent-platform-add-gitops-agentdefi

- [ ] 1. Create `platform-gitops/agent-platform/policy.yaml` with
      `maxBudgetUsd`, `maxTimeoutSeconds`, and `writeToolPatterns` (seeded
      from the concrete pattern list in design.md) — DoD: file exists,
      values are documented with a one-line rationale comment each (mirrors
      `platform-skills/policy.yaml`'s minimal shape).

- [ ] 2. Write the JSON-Schema-equivalent field contract as a short
      reference doc, `platform-gitops/agent-platform/README.md`: field list
      + type + required/optional for `ExecutionProfile`, `AgentDefinition`,
      and the `releases/<environment>/<agent>.yaml` shape, plus the
      lifecycle state table copied from ADR-226's design.md (draft →
      published → active → deprecated → disabled) and the source-of-truth
      boundary table ((a) `mctl-agents` `agent.yaml`, (b) `mctl-gitops`
      `agent-platform/`, (c) `mctl-api` registry) — DoD: a reader can author
      a new profile/definition/release file correctly without reading this
      proposal.

- [ ] 3. Add the three `ExecutionProfile` fixtures under
      `platform-gitops/agent-platform/execution-profiles/{issue-investigator,implementer,shepherd}/profile.yaml`,
      with `budgetUsd`/`timeoutSeconds`/`runtime.clusterWorkflowTemplateRef`/
      resource limits transcribed exactly from
      `cwft-mctl-agents-investigate.yaml` (`ISSUE_INVESTIGATOR_BUDGET_USD:
      "3.00"`), `cwft-mctl-agents-implement.yaml`
      (`IMPLEMENTER_BUDGET_USD: "20.00"`, `IMPLEMENTER_TIMEOUT_SECONDS:
      "2400"`), and `cwft-mctl-agents-shepherd.yaml`
      (`SHEPHERD_BUDGET_USD: "5.00"`) (depends on 1) — DoD: every numeric
      field in each fixture has a matching value in the cited CWFT file,
      confirmed by a `grep` cross-check in the PR description.

- [ ] 4. Add the three `AgentDefinition` catalog snapshots under
      `platform-gitops/agent-platform/definitions/{issue-investigator,implementer,shepherd}/definition.yaml`,
      each with `sourceManifest: {repo: mctlhq/mctl-agents, path:
      agents/_manifests/<name>/agent.yaml, gitSha: <placeholder, to be
      pinned by the follow-up sync task>}` and `executionProfileRef`
      pointing at task 3's profiles (depends on 3) — DoD: no
      `promptSources`/`runtimeContextInputs`/`triggers` field is present in
      these files (thin-pointer only, per design.md's rejected-alternative
      1).

- [ ] 5. Add `platform-gitops/agent-platform/releases/production/{issue-investigator,implementer,shepherd}.yaml`
      referencing task 3/4's names, with a header comment stating this file
      is reviewed intent only and not yet wired to `mctl_promote_agent`
      (depends on 3, 4) — DoD: file's header comment matches the wording
      decided in design.md's Risk mitigation for this exact confusion.

- [ ] 6. Write `scripts/validate-agent-platform.py`, structured like
      `scripts/validate-platform-skills.py`: load every profile/definition,
      enforce every EARS rule from requirements.md (owner required, tools
      default `[]`, write-tool-without-approval rejected, budget/timeout
      bounded by `policy.yaml`, `clusterWorkflowTemplateRef` resolved
      against `argo-workflows/cluster-templates/*.yaml` `metadata.name`,
      `skills` resolved against `platform-skills/catalog/*/metadata.yaml`
      with `status` in `{active,deprecated}`), then load every
      `releases/*/*.yaml` and cross-check `definitionRef`/`profileRef`
      resolve to `published`/`active` catalog entries (depends on 1) — DoD:
      script exits 0 against task 3-5's fixtures and non-zero against every
      negative fixture in task 7.

- [ ] 7. Add negative fixtures under
      `scripts/testdata/agent-platform/negative/` — one file per rejected
      case: missing owner, unknown `clusterWorkflowTemplateRef`, unknown
      skill, `budgetUsd` above `policy.yaml`'s ceiling, a `writeToolPatterns`-
      matching tool without `approval.required: true`, a `disabled`-state
      profile referenced by a `releases/` entry (depends on 6) — DoD: each
      fixture is paired with a one-line comment stating which EARS rule it
      exercises.

- [ ] 8. Wire `scripts/validate-agent-platform.py` into
      `.github/workflows/validate-manifests.yml` as a new step, "Validate
      agent platform catalog", placed after the existing "Validate platform
      skill registry" step, plus a preceding step that runs the validator
      against every fixture in task 7's `negative/` directory and fails the
      job if any of them exits 0 (depends on 6, 7) — DoD: a PR that
      reintroduces any of task 7's negative cases into a real catalog file
      fails CI.

- [ ] 9. Write the migration/import doc,
      `platform-gitops/agent-platform/MIGRATION.md`: how the three fixtures
      map onto `mctl-agents`' current `agents/_manifests/*/agent.yaml` and
      registry versions, the explicit statement that CWFTs still hold the
      actual hardcoded values today (drift risk, per design.md), and the
      named follow-up issue scope that would make CWFTs resolve from a
      published `ExecutionProfile` instead (depends on 3, 4, 5) — DoD: a
      reader can answer "if I bump `implementer`'s budget today, which
      file(s) must I edit for the change to actually take effect" correctly
      (CWFT env var — the catalog is not yet load-bearing) from this doc
      alone.

## Tests

- [ ] T1. `python3 scripts/validate-agent-platform.py` exits 0 against the
      real catalog added in tasks 1-5.
- [ ] T2. `python3 scripts/validate-agent-platform.py` exits non-zero for
      each fixture under `scripts/testdata/agent-platform/negative/`,
      checked individually (not just "the whole batch fails") so a future
      regression that silently stops checking one rule is caught.
- [ ] T3. `helm lint` / `kubeconform` continue to pass unchanged —
      `agent-platform/` is plain YAML with no Helm chart or Kubernetes
      `kind`, so it must not be picked up by the existing kubeconform globs
      (confirm `validate-manifests.yml`'s "Validate raw manifests" find/xargs
      scope does not include `platform-gitops/agent-platform/`).
- [ ] T4. Manual conformance check: for each EARS acceptance criterion in
      requirements.md, locate the exact validator rule (function/branch in
      `scripts/validate-agent-platform.py`) that enforces it and record the
      mapping in the PR description, same discipline as ADR-226's own T2.
- [ ] T5. Diff review: confirm no file outside `platform-gitops/agent-platform/`,
      `scripts/validate-agent-platform.py`, `scripts/testdata/agent-platform/`,
      and `.github/workflows/validate-manifests.yml` changed — this proposal
      must not touch any `cwft-mctl-agents-*.yaml`, `agents-state/`, or
      `mctl-api`-facing code, per the "no behavior change" requirement.

## Rollback

Every file this proposal adds is new (`platform-gitops/agent-platform/**`,
`scripts/validate-agent-platform.py`, `scripts/testdata/agent-platform/**`)
plus one additive step in `validate-manifests.yml`. Nothing reads from
`agent-platform/` at runtime yet (see design.md — the catalog is
documentation-grade until the resolver follow-up lands), so no running agent,
CWFT, or mctl-api registry row depends on it existing. Rollback is `git
revert` of the merge commit, or deleting `platform-gitops/agent-platform/`,
`scripts/validate-agent-platform.py`, `scripts/testdata/agent-platform/`, and
the one added CI step. If a later PR has already added new profiles/
definitions on top of this proposal's fixtures, revert only this proposal's
commit and let CI's own diff surface any now-broken reference in the
follow-up PR — the validator added in task 6 will fail closed on a dangling
reference rather than silently accept it.
