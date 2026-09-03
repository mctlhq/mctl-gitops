# Subservice organizations

Vendor files on disk as of 2026-09-04: see
[evidence/vendors/](evidence/vendors/). Live privacy policy
`https://mctl.ai/privacy` (mctl-web 7.5.2, text dated 2026-08-24)
names the processors below.

| Org | Role | In privacy policy? | Report on file? |
|---|---|---|---|
| Hetzner Cloud | Compute, volumes, network (Frankfurt) | Yes | ISO/IEC 27001:2022 cert (no SOC 2 — Hetzner does not issue one) |
| Cloudflare | R2 (backups, Loki, Terraform state), Workers, DNS | Yes | No — SOC 2 Type II is dashboard-only |
| GitHub | Identity, git, Actions, GitHub Apps | Yes | SOC 3 (to 2026-03-31) + CSA STAR; not SOC 2 Type 2 |
| Anthropic | Claude PR review, mctl-agents inference | Yes | No |
| Let's Encrypt | Public certificates via cert-manager | Yes | No |
| Telegram | Operator paging; landing tenant-request and contact-form notifications | Yes | No |
| Resend | Transactional welcome email after tenant provision | Yes | No |

Self-hosted, not subservice orgs: Vault, CNPG, Argo CD, Argo Workflows,
Traefik, Dex, VictoriaMetrics, Loki, Grafana.

## Review cadence

Annual: pull Hetzner, Cloudflare, and GitHub trust packages; record the
date here. Last pull: 2026-09-04 (GitHub org Compliance zip + public
Hetzner ISO). Cloudflare still outstanding.
