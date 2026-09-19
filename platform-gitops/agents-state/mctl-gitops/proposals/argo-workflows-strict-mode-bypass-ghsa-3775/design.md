# Design: argo-workflows-strict-mode-bypass-ghsa-3775

## Current state
Per `context/architecture.md`, Argo Workflows runs all cron and on-demand pipelines for the
platform. WorkflowTemplates and ClusterWorkflowTemplates live under
`platform-gitops/argo-workflows/cluster-templates/`, and `templateReferencing` Strict/Secure
mode is our existing control against a submitted Workflow referencing an untrusted or
tampered template. GHSA-3775-99mw-8rp4 documents that this control is incomplete: setting
`hostNetwork`, `securityContext`, or `serviceAccountName` directly on a WorkflowTemplate or
CronWorkflow lets the referencing workflow escape the intended sandbox even with Strict/Secure
mode enabled. There is no published fix version for this advisory as of 2026-09-19.

## Proposed solution
Because no upstream patch exists yet, we introduce an interim, repo-local compensating control
rather than a version bump:

1. **CI-time admission check.** Add a validation step to the existing manifest-validation
   pipeline (the same CI gate that already lints `platform-gitops/argo-workflows/` YAML) that
   inspects every `WorkflowTemplate` and `CronWorkflow` manifest under
   `platform-gitops/argo-workflows/cluster-templates/` for the three guarded fields:
   `spec.template.hostNetwork` (and nested template-level `hostNetwork`), any
   `securityContext` override, and any `serviceAccountName` other than the namespace's
   designated restricted default. Any of these present without an explicit
   `mctl.ai/security-reviewed: "<PR-or-ticket-ref>"` annotation fails CI.
2. **Manual-review escape hatch.** Templates with a genuine need for one of these fields (e.g.
   a build workflow that legitimately needs `hostNetwork` for a specific network integration)
   can carry the review annotation once a human reviewer has signed off in the PR. This keeps
   the exception auditable and git-tracked rather than silently bypassed.
3. **Runtime backstop (optional, same mechanism family).** If the platform later adopts
   OPA Gatekeeper or Kyverno for other purposes, the same rule can be expressed as a
   `ValidatingAdmissionPolicy`/Kyverno `ClusterPolicy` for defense-in-depth against manifests
   that reach the cluster outside of this repo's CI path (e.g. Backstage-scaffolded templates
   under `platform-gitops/backstage-templates/`, which render through
   `platform-gitops/argo-workflows/service-templates/`). This proposal scopes the CI-time check
   as the primary, immediately deliverable control; the runtime backstop is called out as an
   explicit stretch task, not a hard requirement.
4. **Upstream tracking.** A dedicated task tracks GHSA-3775-99mw-8rp4 for a published fix.
   Once available, we re-run our normal Argo Workflows upgrade proposal flow (see
   `argo-workflows-cve-bundle-upgrade`/`argo-workflows-cve-patch` as precedent) and, upon
   verified adoption, revisit whether the CI gate can be relaxed or should remain as
   defense-in-depth.

This keeps the change scoped to our own repo (CI validation script + documented review
process), requires no new cluster-side dependency, and does not touch Argo Workflows' own
version — consistent with there being no fix to adopt yet.

## Alternatives
- **Do nothing until upstream ships a fix.** Rejected: we run Argo Workflows for all cron/
  on-demand pipelines, and the bypass is a known, described exploit path today. Leaving it
  open is an unmanaged risk for an unknown amount of time.
- **Fork/patch Argo Workflows' controller ourselves to reject the bypass fields at runtime.**
  Rejected: high effort and maintenance burden (tracking and rebasing a controller patch)
  for a problem that is better solved at the manifest-authoring boundary we already control
  via CI on this repo.
- **Immediately stand up a full OPA Gatekeeper deployment platform-wide as the fix.** Rejected
  as the primary mechanism: broader scope than this specific bypass needs, and a full
  Gatekeeper rollout is a bigger platform decision than a single-CVE mitigation warrants. Kept
  as an optional future defense-in-depth layer (see step 3 above), not the initial delivery.

## Platform impact
- **Migrations:** None. No CRD or version changes; only a CI validation addition and a
  documentation/annotation convention.
- **Backward compatibility:** Existing WorkflowTemplates/CronWorkflows that do not set
  `hostNetwork`, `securityContext`, or a non-default `serviceAccountName` are unaffected. Any
  existing manifest that *does* set one of these fields will need the review annotation added
  before its next CI run passes — this is a one-time audit pass over
  `platform-gitops/argo-workflows/cluster-templates/`.
- **Resource impact (labs):** None. This is a CI-time/documentation control with no new
  running workload, so it does not add CPU or memory pressure to the `labs` tenant, which is
  already near its memory limit (~83% of the memory-limit quota per this cycle's metrics
  snapshot). If the optional runtime backstop (Gatekeeper/Kyverno) is pursued later, it must be
  re-evaluated against `labs` capacity at that time, since an admission controller runs
  cluster-wide.
- **Risks and mitigations:**
  - Risk: CI gate has false positives on legitimate uses of the guarded fields, blocking valid
    deploys. Mitigation: the manual-review annotation escape hatch, plus a fast-follow PR
    process for reviewers.
  - Risk: manifests reaching the cluster outside this repo's CI (e.g. via a compromised direct
    kubectl apply) bypass the control entirely. Mitigation: documented as a known limitation;
    the optional runtime backstop (step 3) is the mitigation path if this risk is judged
    unacceptable, but is out of this proposal's minimum scope.
  - Risk: the interim mitigation is forgotten once upstream ships a fix, leaving stale CI
    friction. Mitigation: explicit tracking task (see `tasks.md`) tied to the GHSA advisory.
