# Patch Argo CD Stored XSS in Application Link Annotations (CVE-2026-45738)

## Context
Argo CD renders user-supplied `link.argocd.argoproj.io/*` annotations on Application resources
directly in the UI. An app-write-scoped user (e.g. a developer who can edit their own
Application's annotations via a GitOps commit or the API) can inject a crafted annotation
value containing JavaScript. When a higher-privileged user (an admin) views that Application
in the Argo CD UI, the injected script executes in the admin's authenticated session — a
stored XSS that becomes a developer-to-admin privilege-escalation path. This is
CVE-2026-45738, fixed upstream in Argo CD 3.2.12, 3.3.10, and 3.4.2.

This platform's Argo CD instance is the sole GitOps sync engine (see `context/architecture.md`)
and is shared across all tenants including `admins` and `labs`; any developer with write
access to a `services/<tenant>/<svc>/` Application manifest can set these annotations, so the
blast radius includes every tenant, not just `admins`.

## User stories
- AS a platform security engineer I WANT the Argo CD stored-XSS vulnerability in link
  annotations patched SO THAT a developer with app-write access cannot escalate to an
  admin's authenticated session.
- AS an Argo CD admin I WANT link annotations to be rendered safely in the UI SO THAT viewing
  any Application, regardless of who authored its annotations, cannot execute arbitrary
  script in my session.

## Acceptance criteria (EARS)
- WHEN the Argo CD Helm chart is synced THE SYSTEM SHALL run a version at or above 3.4.2 (or
  the equivalent patched point release on the 3.2.x/3.3.x line: 3.2.12 or 3.3.10).
- WHEN an Application manifest contains a `link.argocd.argoproj.io/*` annotation with an
  embedded script payload THE SYSTEM SHALL render the annotation value as inert text in the
  Argo CD UI, not as executable markup.
- WHEN the patched version is deployed THE SYSTEM SHALL preserve existing valid
  (non-malicious) external-link annotations exactly as before, with no visible change to
  legitimate Application links.
- IF the running Argo CD version is confirmed below 3.2.12/3.3.10/3.4.2 THEN THE SYSTEM SHALL
  treat this as a high-priority security gap and prioritize the version bump ahead of
  routine patch-day scheduling.
- WHILE the fix is pending or being rolled out THE SYSTEM SHALL NOT grant any new app-write
  role bindings beyond what already exists, to avoid enlarging the exposed attacker
  population.

## Out of scope
- CVE-2026-43824 / CVE-2026-42880 (ServerSideDiff plaintext-Secret disclosure) — already
  tracked in `argocd-serversidediff-secret-exposure`, `argocd-serversidediff-secret-leak`,
  and `argocd-secret-leakage-patch`; this proposal does not duplicate that work, though the
  version bump target overlaps.
- The unpatched Argo CD repo-server unauthenticated RCE report — tracked separately in
  `argocd-repo-server-rce-network-isolation`.
- Any Argo CD minor/major upgrade beyond the smallest patch release that closes this CVE.
- Browser-side hardening (e.g. CSP headers) beyond what ships in the upstream fix — a
  potential follow-up if the upstream annotation-sanitization fix is judged insufficient
  after review.
