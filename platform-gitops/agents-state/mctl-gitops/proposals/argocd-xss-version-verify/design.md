# Design: argocd-xss-version-verify

## Current state

ArgoCD v3.3.9 is deployed in the `admins` tenant via the App-of-Apps ApplicationSet pattern
(see `context/architecture.md`). The ArgoCD Application manifest lives under
`platform-gitops/apps/`. No version-floor constraint exists in that manifest, and no
committed artifact confirms the running version. An engineer or automated process could
unintentionally lower the pinned image tag to a value within the CVE-2025-47933 affected
range (v1.2.0-rc1 through v3.0.3) without any documented guard catching it.

Reference: CVE-2025-47933, GHSA-2hj5-g64g-fp6p, Critical CVSS 9.0 XSS in ArgoCD UI.

## Proposed solution

The proposal has two parts, both read-only or comment-level with respect to runtime state.

**Part 1 — Version verification artifact.**
A one-time `argocd version --server` command is run against the live cluster and its output
is committed verbatim to `platform-gitops/agents-state/argocd-xss-version-verify/version-check.txt`.
This creates a time-stamped audit record in git. The artifact includes: ArgoCD server version,
date of check, operator identity, and a statement that CVE-2025-47933 does not apply.

**Part 2 — Version-floor annotation in the Application manifest.**
A structured YAML comment block is added to the ArgoCD Application manifest in
`platform-gitops/apps/` immediately above the `spec.source.targetRevision` (or equivalent
image tag field). The comment documents:
- `# CVE-2025-47933 — minimum safe version: v3.0.4`
- `# Do NOT set targetRevision below v3.0.4`
- A link to GHSA-2hj5-g64g-fp6p

This is a human-readable guard. If ArgoCD ever gains a `minVersion` field in its CRD, the
comment can be replaced by a machine-enforced constraint with no logic change.

Neither part modifies the running ArgoCD version or any ApplicationSet resource, so there is
zero risk of reconciliation disruption.

## Alternatives

**Do nothing.**
The platform is not currently vulnerable because v3.3.9 is safe. However, this leaves no
audit evidence, making security reviews manual and error-prone. Rejected because the effort
is minimal and the audit value is high.

**Automated image scanning (e.g., Trivy in CI).**
A scanner could continuously verify the image tag. This is correct for long-term hygiene but
is over-engineered for the narrow goal of documenting a point-in-time CVE exemption.
Rejected for this proposal; may be addressed separately.

**Admission webhook version-floor enforcement.**
An OPA/Kyverno policy could block any ArgoCD Application that references an image tag below
v3.0.4. This provides a hard enforcement guarantee but requires a policy engine to be deployed
and maintained. Over-engineered relative to the effort budget (Effort: 1). Rejected; the
comment-based guard is sufficient for now and can be upgraded later.

## Platform impact

- **Migrations:** None. No running resource is modified.
- **Backward compatibility:** The annotation comment is inert YAML. ArgoCD ignores it.
- **Resource impact:** Zero. No new pods, no new memory consumption. No `labs` risk.
- **Risks and mitigations:** The only risk is human error in running the version command
  against the wrong cluster context. Mitigation: the task specifies `kubectl config
  current-context` must be verified before running `argocd version`.
