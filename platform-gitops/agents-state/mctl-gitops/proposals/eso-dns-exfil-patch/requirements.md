# External Secrets Operator CVE-2026-34984 — DNS-based Secret Exfiltration via v2 Template Engine

## Context
CVE-2026-34984 (High severity) affects External Secrets Operator (ESO) v2.0.0 through v2.2.0. The
v2 template engine leaves the `getHostByName` Sprig function accessible inside user-controlled
ExternalSecret templates. An attacker who can create or modify a templated ExternalSecret can craft
a template that encodes a secret value into a DNS hostname and trigger a controller-side DNS lookup,
causing the ESO controller to exfiltrate secret material through DNS queries — bypassing egress
firewall rules that allow DNS traffic.

On this platform, ESO is deployed with the ClusterSecretStore `vault-backend` that bridges Vault
(`secrets.mctl.ai`) to all tenant namespaces. ExternalSecret manifests live under
`platform-gitops/argo-workflows/secrets/` and are managed via GitOps. Any contributor who can
submit a pull request with a malicious ExternalSecret template could trigger exfiltration of
secrets they otherwise cannot read directly. The fix is present in ESO v2.2.1 and later, and the
already-released Helm chart `helm-chart-2.4.1` is the target upgrade vehicle pending patch
confirmation.

## User stories
- AS a platform security engineer I WANT ESO upgraded to a version that removes `getHostByName`
  from user-accessible templates SO THAT secret values cannot be exfiltrated via DNS side-channels.
- AS a tenant developer I WANT ExternalSecret templates to continue supporting all legitimate
  Sprig functions SO THAT my secret-rendering logic is not broken by the patch.
- AS a platform operator I WANT the ESO upgrade applied with zero downtime for existing
  ExternalSecret reconciliation SO THAT tenant services do not lose secret access during the
  change window.

## Acceptance criteria (EARS)
- WHEN a templated ExternalSecret references `getHostByName` in its template body, THE SYSTEM SHALL
  reject the ExternalSecret with a validation error and not perform any DNS lookup.
- WHEN ESO v2.2.1+ is running, THE SYSTEM SHALL successfully reconcile all existing ExternalSecret
  manifests in `platform-gitops/argo-workflows/secrets/` that do not use `getHostByName`.
- WHILE ESO is performing a secret reconciliation cycle, THE SYSTEM SHALL not issue DNS queries
  whose hostnames encode Vault secret values.
- IF an ExternalSecret template contains any call to `getHostByName`, THEN THE SYSTEM SHALL set the
  ExternalSecret status condition to `Ready=False` with a reason of `TemplateFunctionDenied`.
- WHEN the ESO Helm chart is upgraded to `helm-chart-2.4.1` (or the confirmed patched version),
  THE SYSTEM SHALL retain the existing `vault-backend` ClusterSecretStore configuration without
  requiring manual re-creation.

## Out of scope
- Changes to Vault server configuration or Vault policies (see `vault-cve-2026-token-exposure`
  proposal).
- Modification of which secrets are stored in Vault or their key paths.
- Restricting who can submit pull requests to the GitOps repository (an access-control concern
  tracked separately).
- Upgrading ESO past v2.2.1 beyond what is needed to fix this CVE in this change window.
