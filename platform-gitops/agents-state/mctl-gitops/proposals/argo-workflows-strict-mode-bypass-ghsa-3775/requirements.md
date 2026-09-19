# Argo Workflows templateReferencing Strict/Secure-mode bypass (GHSA-3775-99mw-8rp4) — interim mitigation

## Context
Argo Workflows' `templateReferencing` Strict/Secure mode is the primary guardrail we rely on
to stop untrusted `WorkflowTemplate`/`ClusterWorkflowTemplate` references from escalating
privileges when a workflow is submitted from a source we do not fully trust (e.g. a
scaffolded pipeline, a PR-triggered CronWorkflow, or a template authored outside the
`platform-gitops/argo-workflows/cluster-templates/` tree). GHSA-3775-99mw-8rp4 reports that
the earlier fix for CVE-2026-31892 is incomplete: Strict/Secure mode can still be bypassed by
setting `hostNetwork`, `securityContext`, or `serviceAccountName` on a `WorkflowTemplate` or
`CronWorkflow`, letting a submitted workflow escape its intended sandbox even when strict
template referencing is enabled.

As of this cycle, upstream has **not** published a fix version for GHSA-3775-99mw-8rp4. We
run Argo Workflows for all cron and on-demand pipelines per `context/architecture.md`, so this
gap is directly exploitable in our environment today. Because there is no patched version to
adopt, this proposal is about an interim compensating control plus a tracking mechanism for
the eventual upstream fix — not a version bump.

## User stories
- AS a platform operator I WANT untrusted WorkflowTemplates/CronWorkflows to be blocked from
  setting `hostNetwork`, `securityContext`, or `serviceAccountName` SO THAT the known
  Strict/Secure-mode bypass cannot be exploited before an upstream fix exists.
- AS a security reviewer I WANT a documented manual-review gate for any template that
  legitimately needs one of these fields SO THAT there is an auditable exception path instead
  of a silent bypass.
- AS the mctl-gitops owner I WANT a tracked follow-up task for the upstream patch SO THAT the
  interim mitigation is removed/reconciled once GHSA-3775-99mw-8rp4 is actually fixed upstream.

## Acceptance criteria (EARS)
- WHEN a `WorkflowTemplate` or `CronWorkflow` manifest under
  `platform-gitops/argo-workflows/cluster-templates/` sets `hostNetwork: true`,
  a non-default `securityContext`, or an explicit `serviceAccountName` other than the
  namespace's designated restricted service account, THE SYSTEM SHALL reject the manifest at
  admission/CI-validation time unless it carries an explicit allow annotation set by manual
  review.
- WHEN a template author needs one of the three guarded fields for a legitimate use case,
  THE SYSTEM SHALL require a documented manual-review approval (recorded as an annotation or
  PR-review artifact) before the manifest is allowed to sync.
- WHILE GHSA-3775-99mw-8rp4 remains unfixed upstream, THE SYSTEM SHALL keep the admission
  rule / CI gate active for all WorkflowTemplates and CronWorkflows sourced from outside the
  reviewed `cluster-templates/` baseline.
- IF upstream publishes a fix version for GHSA-3775-99mw-8rp4, THEN THE SYSTEM SHALL trigger a
  follow-up review to evaluate upgrading and to retire or relax the interim mitigation once the
  version bump is adopted and verified.
- IF a manifest is rejected by the interim mitigation, THEN THE SYSTEM SHALL surface a clear
  error identifying which of the three guarded fields triggered the rejection.

## Out of scope
- Upgrading Argo Workflows to a version that fixes GHSA-3775-99mw-8rp4 — no such version
  exists yet; this is tracked as a follow-up task, not delivered by this proposal.
- Re-addressing CVE-2026-31892's original fix, already covered by the existing
  `argo-workflows-cve-bundle-upgrade` and `argo-workflows-cve-patch` proposals.
- Broader migration of Argo Workflows admission policy tooling (e.g. adopting a new
  OPA/Gatekeeper deployment platform-wide) — this proposal scopes only the rule(s) needed for
  this specific bypass.
- Changes to Argo CD or ArgoCD ApplicationSet behavior.
