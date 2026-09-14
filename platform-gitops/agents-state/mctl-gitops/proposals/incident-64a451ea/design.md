# Design: incident-64a451ea

## Diagnosis
No mctl-agent skill matched this alert (generic burn-rate rule, no dedicated diagnostic).
Comparing the two mctl-telegram tracks in the same log window: the stable/production
track (job=labs/base-service, instance=labs-mctl-telegram) is fully healthy — canary
probes and every `mcp tool call` line report `status:ok` throughout. The preview track
(instance=labs-mctl-telegram-preview) shows a tight, continuously repeating failure loop
for the whole 6h window covered by the alert: the "Google Antigravity" MCP client performs
OAuth dynamic client registration (RFC 7591), which succeeds ("client_registration audit",
outcome=accepted), and within ~200-800ms two subsequent authenticated requests fail with
"invalid JWT signature". The client then repeats the same registration a little under a
minute later, i.e. it never ends up with a token the server accepts, so it keeps retrying
from scratch. Both `labs/base-service` (stable) and preview publish under the same
Prometheus job label (`job=labs/base-service`), so a burn-rate rule scoped to that job mixes
preview's continuous auth failures into the tenant's aggregate tool-call error rate, which
is consistent with a "slow burn" (low but sustained error ratio) rather than a hard outage.

Root cause (best available evidence, not directly confirmed against Vault or the running
pod's actual environment): `labs-mctl-telegram-preview` reads OAUTH_JWT_SIGNING_KEY from
its own Vault path (secret/data/platform/mctl-telegram-preview/oauth) via an
ExternalSecret with a `refreshInterval: 1h` and an explicit
`argocd.argoproj.io/sync-options: ServerSideApply=false` annotation, noted in-repo as a
workaround for an ArgoCD v3.3.8 ServerSideApply bug affecting ExternalSecrets on this exact
object. The signing key reaches the pod via `envFrom: secretRef` (values.yaml), and
Kubernetes does not live-update a running container's environment when the backing Secret
changes — a new value only takes effect on the next pod (re)start. If that key was rotated
or re-synced (routine ExternalSecret refresh, or a resync after the noted SSA issue) after
the current preview pod started, the running pod would keep signing/verifying against a
now-stale key, producing exactly this signature-mismatch pattern for every request until
the pod restarts and re-reads the current Secret content. The base-service Deployment
template only forces a rollout on `.Values.configMaps` changes (via a checksum annotation)
or `.Values.podAnnotations`; there is no equivalent checksum wired to the OAuth
ExternalSecret's Secret, so a key rotation there does not, by itself, trigger a pod restart
on either preview or stable.

## Confidence: LOW
This explains the observed symptom precisely (registration succeeds, every subsequent
authenticated call signature-fails, indefinitely, only on preview) and points to a concrete,
minimal, reversible action, but nothing available to this responder (no shell, no Vault
access, no kubectl) can directly confirm the preview pod's in-memory signing key is actually
stale relative to the current Vault value. The implementer should verify pod age vs. the
`labs-mctl-telegram-preview-oauth` Secret's last-updated time before/while applying this, and
treat the proposed fix as "force a fresh read of the current secret," which is safe and a
no-op if the key was never actually stale.

## Proposed Fix
File: `platform-gitops/services/labs/mctl-telegram-preview/values.yaml`

Add a `podAnnotations` block that forces a rollout so the preview Deployment's pods restart
and re-read the current `labs-mctl-telegram-preview-oauth` Secret content (current value:
field absent today; new value: a rollout-marker annotation):

```yaml
podAnnotations:
  mctl.me/oauth-secret-rollout: "incident-64a451ea-2026-09-14"
```

This only adds a pod template annotation (picked up by the existing `.Values.podAnnotations`
template block already present in `helm-charts/base-service/templates/deployment.yaml`); it
does not change any other field, secret, or the strategy (`Recreate`) already in place for
this service. On sync, ArgoCD recreates the preview pod(s), which re-read
OAUTH_JWT_SIGNING_KEY and TELEGRAM_OIDC_CLIENT_SECRET from the Secret's current content via
`envFrom`.

If this does not resolve the alert (i.e. the signing key was never stale and this was a
no-op), the next step — out of scope for this minimal proposal — is comparing the value at
`secret/data/platform/mctl-telegram-preview/oauth` (property `jwt-signing-key`) against what
the preview pod is actually presenting, and checking whether the "Google Antigravity" client
itself is holding and replaying a JWT signed under a different key entirely (e.g. cached from
before a legitimate rotation), which would need a client-side fix instead.

## Scope
Minimal. Only adds a `podAnnotations` entry to the preview service's values.yaml to force a
pod rollout. No image, resource, ingress, or other config field is touched. Stable
(`labs/mctl-telegram`) is not touched.
