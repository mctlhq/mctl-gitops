# Control matrix — tests of design (Type I)

Operating effectiveness over a period is Type II and is out of scope.
Each row is: the control as designed, where a CPA samples it, what still
fails a design test.

| TSC | Control as designed | Evidence | Test of design (point in time) | Hole |
|---|---|---|---|---|
| CC1 | Solo founder + AGENTS.md + SECURITY.md + Contributor Covenant | `AGENTS.md`, `SECURITY.md`, `ROADMAP.md` | Inspect policies exist and name an owner | No org chart, no CoC ack, no CODEOWNERS on core repos |
| CC2 | Privacy + runbooks + docs.mctl.ai | `mctl-web` privacy, `docs/runbooks/*`, this binder | Read description vs live cluster | Privacy source lists subprocessors as of 2026-08-24; live mctl.ai/privacy follows the next web release |
| CC3 | Engineering F-register, ROADMAP, `docs/soc2/risk-register.md` | this binder | Confirm residuals are listed | Fraud memo exists; no annual signed risk assessment |
| CC4 | Grafana / Alertmanager / VaultBackupStale | `monitoring.yaml`, `backup-alerts.yaml` | Confirm rules exist in git | Infra monitoring ≠ control monitoring; no internal audit |
| CC5 | Branch + PR + Claude P1/P2 + GitOps | `claude-review.yml`, Argo CD apps | Open one merged PR; confirm merge commit | Pass for design |
| CC6 | GitHub OAuth, Dex, Vault K8s/JWT, tenant NP, joiner/leaver WFTs, org MFA | overlays, `networkpolicy.yaml`, `evidence/github-org-mfa.md` | Probe auth; `two_factor_requirement_enabled` | MFA on 2026-08-19; `2fa_disabled` count 0; open DCR is product choice |
| CC7 | R2 backups, drills, responder CronWorkflow, api audit, k8s AuditPolicy | `restore.md`, `audit-policy.yaml`, CronWorkflow | CronJob lastSuccessful; suspend=false | audit.log node-local; no IR customer-notification SLA |
| CC8 | No direct main; live branch protection; bot tag bumps only | GitHub rulesets; `gitops-bump.yaml`; `CLAUDE.md` | `gh api repos/.../rulesets` | Pass for design |
| CC9 | Restore runbook; dual GitHub Apps | `restore.md`, `github-app-scope-audit.md` | Read runbook | No vendor SOC file (this `vendors.md`) |
| A1 | PDBs, Vault raft 3, Traefik 3, etcd S3, single-CP runbook | `control-plane.md`, PDBs | Nodes + CronJob backup | No SLOs; replicaCount 1 on api; F21 wait is vault-backup only |
| C1 | Edge TLS, sslmode=require, Vault+ESO, audit redaction, preview paths | overlays, `redact.go`, F2 preview | TLS at edge; Vault tls_disable=1 documented | No classification policy; F15 residual |

## Product choices that are not Type I defects

- Leaving `OAUTH_REGISTRATION_TOKEN` unset (self-service MCP DCR).
- docs `style-src 'unsafe-inline'` (VitePress inline styles; nginx.conf:15).
- Not spraying a NetworkPolicy wait onto CronJobs that do not lose the race.
