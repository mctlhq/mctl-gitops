# System description

Draft for a SOC 2 Type I Section III. Seeded from
`mctl-docs/docs/platform/architecture.md`,
`infrastructure/k3s-preview/README.md`, and live cluster `mctl-preprod`
on 2026-08-17. Not customer marketing copy.

## 1. People

MCTL is operated by a single founder (`@mashkovd`) plus automated agents
(Claude PR review, mctl-agents implementer/shepherd, mctl-agent incident
pipeline). There is no board, no security team, and no separate change
approver. Compensating controls are documented in
`compensating-controls.md` once that file exists.

Humans authenticate with GitHub. Agents authenticate with GitHub Apps,
Vault Kubernetes auth, or Vault JWT (GitHub Actions OIDC).

## 2. Infrastructure

| Item | Fact |
|---|---|
| Cluster | `mctl-preprod`, k3s v1.33, Hetzner Cloud Frankfurt (`eu-central`) |
| Nodes | 1 control-plane (cx33) + 3 workers (cx43). OS auto-upgrade off |
| Ingress | Traefik, cert-manager / Let's Encrypt |
| Secrets | HashiCorp Vault (3-node Raft), External Secrets Operator |
| Data | CloudNative-PG `shared-pg`, backups to Cloudflare R2 |
| GitOps | Argo CD reconciles this repository |
| Jobs | Argo Workflows |
| Metrics / logs | VictoriaMetrics, Loki (R2), Grafana, Alertmanager |

There is no separate production cluster. Preprod *is* the running platform.
A second control plane is Horizon 2 (F11).

## 3. Software (in-scope)

| Component | Role | Typical image |
|---|---|---|
| mctl-api | REST + MCP + OAuth | `ghcr.io/mctlhq/mctl-api` (live 4.32.7 on 2026-08-19) |
| mctl-agent | Tickets, alerts, dispatch | `ghcr.io/mctlhq/mctl-agent` (live 1.16.1) |
| mctl-agents | Implementer / shepherd workers | `ghcr.io/mctlhq/mctl-agents` |
| mctl-portal | Backstage at app.mctl.ai | `ghcr.io/mctlhq/mctl-portal` |
| mctl-web | Landing + Cloudflare Worker | `ghcr.io/mctlhq/mctl-web` |
| mctl-docs | VitePress at docs.mctl.ai | `ghcr.io/mctlhq/mctl-docs` |
| mctl-gitops | Desired state | this repo |

Write path: client → mctl-api → Argo Workflow → git commit in this repo →
Argo CD sync → cluster.

## 4. Procedures

- No direct human commits to `main`. Feature branch, pull request, merge
  commit. Claude review is the P1/P2 gate on non-trivial PRs
  (`AGENTS.md`, `.github/workflows/claude-review.yml`).
- Exceptions: `gitops-bump.yaml` and `release-deploy.yaml` push a single
  `image.tag` to main (documented in `CLAUDE.md`).
- Tenant create/delete are ClusterWorkflowTemplates
  (`wft-create-tenant.yaml`, `wft-delete-tenant-safe.yaml`).
- Restore procedures and drill journal: `docs/runbooks/restore.md`.
- Accepted availability/encryption residuals: `docs/runbooks/control-plane.md`.

## 5. Data

| Class | Examples | Where | Retention (as designed) |
|---|---|---|---|
| Identity | GitHub username, email | mctl-api / portal | While account is active; privacy says 30 days after deletion |
| Platform audit | Operation execute rows (IP, UA, request id; secrets redacted) | CNPG `audit_events` | Privacy says 90 days; table has no sweeper — residual |
| Secrets | Tokens, DB passwords | Vault raft; ESO materializes K8s Secrets | Vault snapshots 30 copies; not in git |
| Backups | Postgres, Vault, etcd, metrics | Cloudflare R2 | 14d Postgres/etcd; 30 Vault copies |
| Tenant app data | Customer databases | CNPG per-DB; out of Type I app-logic scope | 14d barman |

Edge TLS terminates at Traefik. Postgres audit DSN uses `sslmode=require`.
Vault Raft listener is `tls_disable=1` (F15, Horizon 2). Privacy policy
§6 overclaims "all data in transit is TLS 1.2+" relative to east-west Vault.

## 6. Subservice organizations

See [vendors.md](vendors.md). Physical datacenter access is Hetzner's, not
ours.

## 7. Complementary controls

See [cuecs.md](cuecs.md).
