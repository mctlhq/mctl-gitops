# Tasks: argo-workflows-strict-mode-bypass-ghsa-3775

- [ ] 1. Audit all existing manifests under `platform-gitops/argo-workflows/cluster-templates/`
  for use of `hostNetwork`, `securityContext`, or non-default `serviceAccountName` — DoD:
  a written inventory (PR description or issue) listing every offending manifest, with a
  reviewer decision recorded for each (either remove the field or annotate as reviewed).
- [ ] 2. Add the CI validation check (script or CI-pipeline step) that scans
  WorkflowTemplate/CronWorkflow manifests for the three guarded fields and fails the build
  unless a `mctl.ai/security-reviewed: "<ref>"` annotation is present (depends on 1, so the
  existing baseline doesn't immediately fail CI) — DoD: CI step merged, running on every PR
  touching `platform-gitops/argo-workflows/cluster-templates/`, verified to fail on a
  deliberately-introduced test manifest with an unreviewed guarded field.
- [ ] 3. Apply the review annotation (or remove the field) to every manifest flagged in task 1
  (depends on 1, 2) — DoD: CI passes cleanly on `main`/default branch with the new check active,
  no manifest is silently exempted without a recorded reviewer decision.
- [ ] 4. Document the mitigation and manual-review process (what the annotation means, who can
  approve it, when to use it) in a short note alongside `context/architecture.md` conventions
  (e.g. a new entry under `context/decisions/` as an ADR, since this is a security-relevant
  process decision) — DoD: ADR merged and referenced from this proposal.
- [ ] 5. Open and link a tracking task/issue for GHSA-3775-99mw-8rp4 upstream fix status —
  DoD: tracking issue exists, linked from this proposal's `requirements.md` Source link and
  from the ADR in task 4, with an owner assigned to check upstream status on a recurring
  (e.g. weekly) basis until resolved.
- [ ] 6. (Stretch, optional) Evaluate feasibility of a runtime admission-policy backstop
  (Gatekeeper/Kyverno) for the same three fields, factoring in `labs` tenant capacity —
  DoD: a short written recommendation (adopt now / defer / not needed) added to this proposal's
  `design.md` Risks section or a follow-up proposal, not blocking tasks 1-5.
- [ ] 7. Once GHSA-3775-99mw-8rp4 has an upstream fix, open a follow-up Argo Workflows upgrade
  proposal (depends on 5) and, after it is adopted and verified, revisit whether the CI gate
  from task 2 should be relaxed or kept as defense-in-depth — DoD: follow-up proposal created
  and this proposal's tracking issue (task 5) closed with a decision recorded.

## Tests
- [ ] T1. Negative test: a WorkflowTemplate manifest setting `hostNetwork: true` without the
  review annotation fails CI validation.
- [ ] T2. Negative test: a CronWorkflow manifest setting a non-default `serviceAccountName`
  without the review annotation fails CI validation.
- [ ] T3. Positive test: the same manifests, with a valid `mctl.ai/security-reviewed`
  annotation, pass CI validation.
- [ ] T4. Regression test: existing (legitimate, unmodified) manifests in
  `cluster-templates/` continue to pass CI after the check is added (i.e. no false positives
  against the audited baseline from task 1/3).

## Rollback
The CI validation check is additive and repo-local: if it produces excessive false positives or
blocks a time-sensitive deploy, revert the CI-pipeline-step commit (task 2) to disable the gate
immediately, while keeping the documentation (task 4) and tracking issue (task 5) in place. No
cluster-side state changes are made by this proposal, so there is nothing to roll back at the
runtime/cluster level — rollback is a simple git revert of the CI check.
