# SOC 2 Type I binder

Internal package for a point-in-time test of design. Not a report. Not a
badge. Not on docs.mctl.ai.

**As of:** 2026-08-17
**System:** MCTL platform on cluster `mctl-preprod`
**Criteria in scope:** Security (CC1–CC9), Availability (A1), Confidentiality (C1)
**Out of scope:** Type II observation window, HIPAA, ISO 27001, tenant
application logic and tenant-owned data

## Boundary

**In:** platform control plane and GitOps path — mctl-api, mctl-agent,
mctl-agents, mctl-portal, mctl-web, mctl-docs, mctl-gitops, in-cluster
Vault / CNPG / Argo CD / Argo Workflows / Traefik / observability.

**Out:** customer-deployed workloads in tenant namespaces (isolation is in
scope; the apps are not), mctl-academy, mctl-telegram product, mctl-openclaw,
loyalty, pairdesk.

## Index

| Document | Role |
|---|---|
| [system-description.md](system-description.md) | People, software, infra, procedures, data |
| [management-assertion.md](management-assertion.md) | Draft assertion — human signs later |
| [cuecs.md](cuecs.md) | Complementary user entity and inherited controls |
| [vendors.md](vendors.md) | Subservice organizations |
| [control-matrix.md](control-matrix.md) | TSC → control → evidence → test of design |
| [evidence/github-org-mfa.md](evidence/github-org-mfa.md) | Org MFA probe |

Procedures (risk register, SoD memo, access review, emergency change) land
in a follow-up commit under this directory.

## Honest residuals (do not hide)

Single control-plane (F11). Vault east-west `tls_disable=1` (F15). PSS
`enforce=baseline` (F18). Open RFC 7591 DCR (product choice). docs
`style-src 'unsafe-inline'` (rejected in nginx.conf). apiserver audit.log
on the CP disk, not Loki (F20). `gitops-bump` / `release-deploy` write
`image.tag` to main. GitHub rulesets allow admin bypass. Org MFA
requirement was `false` on 2026-08-17 (see evidence file).

## What this is not

A CPA opinion. A Type II period. Permission to put "SOC 2" on mctl.ai.
