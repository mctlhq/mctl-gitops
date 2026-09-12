# Design: argocd-annotation-xss-privesc

## Current state
Argo CD runs in the `admins` tenant as the platform's sole GitOps sync engine (`ops.mctl.ai`),
deployed via the App-of-Apps / ApplicationSet pattern described in `context/architecture.md`
and ADR `0001-app-of-apps-pattern.md`. Its Helm chart version is pinned in
`platform-gitops/bootstrap/` (the bootstrap App-of-Apps that deploys Argo CD itself as a
self-managed Application). Application resources across all tenants
(`platform-gitops/services/<tenant>/<svc>/`) can carry `link.argocd.argoproj.io/*`
annotations to surface external links (e.g. runbooks, dashboards) in the Argo CD UI.

The exact currently-pinned Argo CD version is recorded wherever the chart tag lives in
`platform-gitops/bootstrap/`; other in-flight proposals (`argocd-secret-leakage-patch`,
`argocd-v3-4-2-stability-patch`) target the same 3.2.x/3.3.x/3.4.x patch train for a
different CVE class (ServerSideDiff Secret disclosure). Any version currently below 3.2.12
(3.2.x line), 3.3.10 (3.3.x line), or 3.4.2 (3.4.x line) is vulnerable to CVE-2026-45738:
link annotations are rendered without adequate sanitization, allowing stored XSS that
executes in the session of whoever next views the Application in the UI.

## Proposed solution
Bump the Argo CD Helm chart / image tag pinned in `platform-gitops/bootstrap/` to the
smallest patched release on the currently-deployed minor line (3.2.12, 3.3.10, or 3.4.2 —
whichever matches what is running today), or to 3.4.2 directly if a coordinated bump with
the other in-flight ServerSideDiff patch proposals is preferred. Commit the version change
to this repo; Argo CD's self-managed Application detects the drift and performs a rolling
restart of `argocd-server` (the component responsible for UI rendering).

No changes to Application manifests, annotation conventions, or RBAC are required: the fix
is contained entirely in how `argocd-server` sanitizes/encodes annotation values before
rendering them in the UI. Existing `link.argocd.argoproj.io/*` annotations across all
tenants continue to render as clickable links; only script-injection payloads are
neutralized.

Why this approach:
- Matches the established pattern for every other CVE proposal in this repo: a pure
  version-pin bump through the GitOps promotion path, no architecture change.
- Keeps the fix scoped to the smallest patch step, consistent with the platform's
  "no combination/major upgrades on patch day" guidance.
- If the version bump is coordinated with the already-planned ServerSideDiff patch (same
  fix versions), this closes both CVE classes in a single rollout — reducing the number of
  `argocd-server` restarts needed this cycle.

## Alternatives
**a. Web Application Firewall / reverse-proxy response sanitization in front of the Argo CD
UI.**
Rejected: adds a new network component and ongoing maintenance burden to strip a specific
annotation pattern; does not fix the root cause and would need constant tuning against
future annotation-based payloads. A vendor patch already exists.

**b. Strip or block `link.argocd.argoproj.io/*` annotations platform-wide via an admission
policy until the upgrade lands.**
Rejected: this annotation is legitimately used across tenants for runbook/dashboard links;
blocking it breaks a used feature for a bug that already has a proper upstream fix landing
in the same patch train as an existing planned bump. Considered only as a stop-gap; not
needed given the low effort of the real fix.

**c. Defer this fix and rely solely on the existing ServerSideDiff-focused version bump
(`argocd-secret-leakage-patch`) to "happen to" cover it.**
Rejected: while the fix versions overlap, treating this only as a side effect risks the
acceptance criteria for the XSS-specific behavior (annotation rendering, privilege-escalation
path) never being explicitly verified. This proposal keeps its own acceptance criteria and
test plan so the annotation-sanitization behavior is checked independently, even if the
deployment step is combined operationally.

## Platform impact
**Migrations:** None. Patch-level Argo CD releases within the same minor line make no
Application/ApplicationSet CRD schema changes.

**Backward compatibility:** Full. Existing Application manifests and their
`link.argocd.argoproj.io/*` annotations across all tenants continue to work unchanged; only
the rendering path is hardened.

**Resource impact (`labs`):** None. Argo CD runs entirely in the `admins` tenant control
plane; this is a version bump of the sync engine itself, not a tenant workload. `labs`
memory usage is unaffected — this proposal is not flagged as risky for the `labs` memory
constraint.

**Risks and mitigations:**
- Risk: `argocd-server` rolling restart causes a brief UI/API blip. Mitigation: rolling
  update keeps at least one replica available; schedule during a low-traffic window.
- Risk: coordinating this bump with the separate ServerSideDiff proposal creates
  merge/ordering confusion. Mitigation: land whichever proposal's PR is ready first; the
  other should rebase onto the resulting version rather than re-bump independently.
- Risk: a regression in link rendering (e.g. legitimate links stop rendering as clickable).
  Mitigation: manual smoke test of an Application with a real runbook link post-upgrade;
  rollback via `kubectl rollout undo` if broken.
