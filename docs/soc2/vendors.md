# Subservice organizations

No vendor SOC reports are on file as of 2026-08-17. Privacy policy
(`mctl-web` `/privacy`) names GitHub, Anthropic, and Cloudflare only.

| Org | Role | In privacy policy? | SOC report on file? |
|---|---|---|---|
| Hetzner Cloud | Compute, volumes, network (Frankfurt) | No | No |
| Cloudflare | R2 (backups, Loki, Terraform state), Workers, DNS | Partial (CDN / network) | No |
| GitHub | Identity, git, Actions, GitHub Apps | Partial (OAuth only) | No |
| Anthropic | Claude PR review, mctl-agents inference | Yes | No |
| Let's Encrypt | Public certificates via cert-manager | No | No |
| Telegram | Operator paging (mctl-agent) | No | No |

Self-hosted, not subservice orgs: Vault, CNPG, Argo CD, Argo Workflows,
Traefik, Dex, VictoriaMetrics, Loki, Grafana.

## Review cadence (intended)

Annual: pull Hetzner, Cloudflare, and GitHub trust/SOC packages; record
the date in this table. Not started.

## Privacy gap

Updating mctl-web privacy subprocessors (Hetzner, R2, Dex, Telegram) is
a separate repository and is not part of this binder PR.
