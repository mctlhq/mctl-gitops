# Subservice organizations

No vendor SOC reports are on file as of 2026-08-24. Privacy policy source
(`mctl-web` `app/pages/privacy/index.vue`) names the processors below.
Live `https://mctl.ai/privacy` follows the next mctl-web release.

| Org | Role | In privacy policy? | SOC report on file? |
|---|---|---|---|
| Hetzner Cloud | Compute, volumes, network (Frankfurt) | Yes | No |
| Cloudflare | R2 (backups, Loki, Terraform state), Workers, DNS | Yes | No |
| GitHub | Identity, git, Actions, GitHub Apps | Yes | No |
| Anthropic | Claude PR review, mctl-agents inference | Yes | No |
| Let's Encrypt | Public certificates via cert-manager | Yes | No |
| Telegram | Operator paging (mctl-agent) | Yes | No |

Self-hosted, not subservice orgs: Vault, CNPG, Argo CD, Argo Workflows,
Traefik, Dex, VictoriaMetrics, Loki, Grafana.

## Review cadence (intended)

Annual: pull Hetzner, Cloudflare, and GitHub trust/SOC packages; record
the date in this table. Not started.
