# Design: argocd-serversidediff-secret-exposure

## Current state
Per `context/architecture.md`, Argo CD (`ops.mctl.ai`) is the sync engine
that reconciles this repo's manifests onto the cluster, using the
App-of-Apps pattern with ApplicationSets (`apps`, `tenants`,
`openclaw-skills`) generated from the bootstrap chart
(`platform-gitops/bootstrap/`). Argo CD's own version/image is pinned
somewhere in the bootstrap chart or a dedicated Argo CD Application
definition under `platform-gitops/apps/`; `context/current-version.md`
tracks the `mctl-gitops` repo tag (4.10.1) but does not record the exact
Argo CD build. CVE-2026-43824 and CVE-2026-42880 affect the ServerSideDiff
feature in Argo CD 3.2.0–3.2.11 and 3.3.0–3.3.9, letting cleartext Secret
data leak to read-only users. Secrets in this platform are exclusively
rendered by External Secrets Operator from Vault
(`platform-gitops/argo-workflows/secrets/`), so an Argo CD-level Secret leak
bypasses that isolation model entirely.

## Proposed solution
1. Locate the Argo CD control-plane manifest/Application definition in
   `platform-gitops/apps/` (or bootstrap chart) that pins the Argo CD image
   tag/Helm chart version.
2. Determine the currently deployed version. If it is not recorded, treat
   this as the first task (query the running Argo CD instance or the pinned
   chart version in git).
3. If the version is inside the affected ranges, bump the pin to a patched
   release. Prefer the smallest safe bump (3.2.12+/3.3.10+) unless the fleet
   is already tracking a newer minor line, in which case align to that
   line's patched build (the researcher noted upstream is already at 3.5.2).
4. Record the confirmed/patched version explicitly in
   `context/current-version.md` (or a dedicated note) so future CVE triage
   does not need to re-derive it.
5. Do not touch ApplicationSet generators, directory patterns, or the
   Application CRD's `apiVersion` — this is strictly an image/chart version
   bump for the Argo CD control plane itself.

## Alternatives
- **Do nothing until confirmed exploited** — rejected: CVSS 9.6 with a
  concrete exploitation path (read-only user extracting Secrets) against a
  platform whose entire secret-delivery model depends on Secret
  confidentiality; the fix is a low-effort version pin, so waiting has no
  offsetting benefit.
- **Jump straight to the newest Argo CD major/minor without confirming the
  affected range first** — rejected: skips verification, and ADR context
  explicitly warns against Argo major upgrades on patch-day without cause
  (see the Argo Workflows 3.7.10 archive bug precedent in
  `context/architecture.md`); we want the minimal patched version, not an
  opportunistic major bump bundled with unrelated risk.
- **Disable ServerSideDiff entirely as a workaround instead of patching** —
  rejected: loses a useful diffing feature platform-wide and is a
  behavioral change to the sync engine's diff strategy, whereas the
  upstream patch is already available and targeted.

## Platform impact
- **Migrations:** None. This is a container image/chart version bump for
  the Argo CD control plane; no CRD schema changes, no ApplicationSet
  generator changes.
- **Backward compatibility:** Patched Argo CD minors listed
  (3.2.12+/3.3.10+/3.5.x) are within the same major line and do not change
  the Application API; existing Applications reconcile unchanged.
- **Resource impact (labs):** None. Argo CD control-plane components run in
  the ArgoCD/ops namespace, not in `labs`; this change does not add
  workloads or increase memory requests/limits for `labs`.
- **Risks and mitigations:**
  - Risk: patched version introduces unrelated regressions (e.g. sync
    behavior changes). Mitigation: pin to a patch release within the same
    minor line where possible; validate against a non-critical tenant's
    Applications before rolling out platform-wide if a minor bump is
    required.
  - Risk: the deployed version turns out to already be safe, making the
    "fix" a no-op. Mitigation: task 1 explicitly requires confirmation
    before any version-pin edit is made.
