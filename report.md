> **Routing note:** This issue was intended for `mctlhq/mctl-agents` but was posted here because the GitHub MCP session is scoped to `mctlhq/mctl-gitops` only. To fix: expand the MCP allowed-repositories list to include `mctlhq/mctl-agents`.

---

## Summary

20 proposals tracked across 7 repos: **16 merged**, **4 rejected**, **0 in-progress**, **0 proposed**. The pipeline is fully drained with no change since the 2026-05-15 report (issue #213). Zero `mctl-agents` bot commits in the last 26 h. Very active human/deploy day: **21 PRs merged** on 2026-05-16, spanning mctl-telegram OAuth hardening (7 PRs), mctl-design launch, mctl-web redesign promotion then same-day rollback, and Claude PR-review CI rollout across repos. **3 active cluster incidents** (api.mctl.ai connector attached this run for the first time): `admins-mctl-agent` ArgoCD OutOfSync fired twice and `admins` namespace quota pressure. Follow-up comment posted on stale-pr issue [#188](https://github.com/mctlhq/mctl-gitops/issues/188) for `mctl-gitops#84` (now 17 days with no activity).

---

## Proposal pipeline state

| repo | slug | status | pr | changed\_since\_yesterday |
|------|------|--------|----|--------------------------|
| mctl-agents | tier3-pr-shepherd | merged | [mctl-agents#12](https://github.com/mctlhq/mctl-agents/pull/12) | — |
| mctl-agent | sqlite-cve-patch | merged | [mctl-agent#9](https://github.com/mctlhq/mctl-agent/pull/9) | — |
| mctl-agent | incident-auto-cleanup-phase1 | merged | [mctl-agent#11](https://github.com/mctlhq/mctl-agent/pull/11) | — |
| mctl-agent | incident-auto-cleanup-phase2 | merged | [mctl-agent#13](https://github.com/mctlhq/mctl-agent/pull/13) | — |
| mctl-agent | incident-auto-cleanup-phase3 | merged | [mctl-agent#12](https://github.com/mctlhq/mctl-agent/pull/12) | — |
| mctl-agent | incident-auto-cleanup-phase4-metrics | rejected | [mctl-agent#17](https://github.com/mctlhq/mctl-agent/pull/17) | — |
| mctl-agent | incident-auto-cleanup-phase4a-metrics-wiring | merged | [mctl-agent#16](https://github.com/mctlhq/mctl-agent/pull/16) | — |
| mctl-agent | incident-auto-cleanup-phase4b-metrics-full | merged | [mctl-agent#17](https://github.com/mctlhq/mctl-agent/pull/17) | — |
| mctl-api | chi-security-patch | merged | [mctl-api#39](https://github.com/mctlhq/mctl-api/pull/39) | — |
| mctl-api | pgx-sqli-cve-2025-54236 | merged | [mctl-api#40](https://github.com/mctlhq/mctl-api/pull/40) | — |
| mctl-docs | fix-broken-mctl-ai-mcp-links | merged | [mctl-docs#6](https://github.com/mctlhq/mctl-docs/pull/6) | — |
| mctl-docs | mcp-agents-tools | merged | [mctl-docs#7](https://github.com/mctlhq/mctl-docs/pull/7) | — |
| mctl-portal | scaffolder-path-traversal | rejected | [mctl-portal#10](https://github.com/mctlhq/mctl-portal/pull/10) | — |
| mctl-portal | scaffolder-secret-leak | rejected | [mctl-portal#12](https://github.com/mctlhq/mctl-portal/pull/12) | — |
| mctl-openclaw | upgrade-to-2026-4-27 | rejected | [mctl-openclaw#15](https://github.com/mctlhq/mctl-openclaw/pull/15) | — |
| mctl-web | wrangler-upgrade-security | merged | [mctl-web#9](https://github.com/mctlhq/mctl-web/pull/9) | — |
| mctl-gitops | argo-workflows-cve-patch-v2 | merged | [mctl-gitops#85](https://github.com/mctlhq/mctl-gitops/pull/85) | — |
| mctl-gitops | argocd-informer-cache-patch | merged | [mctl-gitops#90](https://github.com/mctlhq/mctl-gitops/pull/90) | — |
| mctl-gitops | grafana-sql-rce-patch | merged | [mctl-gitops#89](https://github.com/mctlhq/mctl-gitops/pull/89) | — |
| mctl-gitops | eso-cve-patch | merged | [mctl-gitops#87](https://github.com/mctlhq/mctl-gitops/pull/87) | — |

---

## Pipeline diff (vs yesterday — issue #213, 2026-05-15)

- **Newly merged:** none
- **Newly rejected:** none
- **Newly proposed:** none
- **Still in-progress:** none
- **Still proposed:** none

Pipeline is fully terminal. No delta from yesterday.

---

## Recent merged PRs (24h — 2026-05-16)

21 PRs merged across 5 repos:

**mctlhq/mctl-gitops (7):**
- [#222](https://github.com/mctlhq/mctl-gitops/pull/222) fix: roll mctl-web back to pre-redesign (6.0.0)
- [#221](https://github.com/mctlhq/mctl-gitops/pull/221) deploy: admins/mctl-web → 5.1.0 (redesign) _(immediately reverted by #222)_
- [#220](https://github.com/mctlhq/mctl-gitops/pull/220) ci: add automated Claude PR review workflow
- [#219](https://github.com/mctlhq/mctl-gitops/pull/219) ci: optional github_token build secret in build-image
- [#218](https://github.com/mctlhq/mctl-gitops/pull/218) chore: raise admins namespace CPU quota to 10
- [#216](https://github.com/mctlhq/mctl-gitops/pull/216) feat: add ui.mctl.ai host to mctl-design
- [#215](https://github.com/mctlhq/mctl-gitops/pull/215) feat(mctl-agent): disable LLM diagnosis, add MAX_ANALYZING_AGE

**mctlhq/mctl-telegram (10):**
- [#46](https://github.com/mctlhq/mctl-telegram/pull/46) fix(oauth): replace broken account-switch control with help block
- [#45](https://github.com/mctlhq/mctl-telegram/pull/45) fix(oauth): run widget logout in an iframe, not a popup
- [#44](https://github.com/mctlhq/mctl-telegram/pull/44) fix(oauth): add origin to the Login Widget logout link
- [#43](https://github.com/mctlhq/mctl-telegram/pull/43) fix(oauth): drop write-access request from the Login Widget
- [#42](https://github.com/mctlhq/mctl-telegram/pull/42) feat(oauth): switch-account control on the authorize page
- [#41](https://github.com/mctlhq/mctl-telegram/pull/41) feat: hands-off client onboarding — open auto-approve + daily digest
- [#33](https://github.com/mctlhq/mctl-telegram/pull/33) fix: add Dependabot and CodeQL for Scorecard compliance
- [#32](https://github.com/mctlhq/mctl-telegram/pull/32) fix: pin GHA actions to SHA and restrict workflow permissions
- [#31](https://github.com/mctlhq/mctl-telegram/pull/31) feat(oauth): client scope tier + DB-backed client management
- [#27](https://github.com/mctlhq/mctl-telegram/pull/27) feat(oauth): in-browser enable_access flow for MTProto session onboarding

**mctlhq/mctl-web (2):**
- [#16](https://github.com/mctlhq/mctl-web/pull/16) ci: add automated Claude PR review workflow
- [#15](https://github.com/mctlhq/mctl-web/pull/15) feat: consume @mctlhq/css design tokens as single source of truth

**mctlhq/mctl-agent (1):**
- [#19](https://github.com/mctlhq/mctl-agent/pull/19) feat(skill): add DISABLE_LLM_DIAGNOSIS + MaxAnalyzingAge force-resolve

**mctlhq/mctl-design (1):**
- [#1](https://github.com/mctlhq/mctl-design/pull/1) feat(storybook): MCTL chrome branding + light/dark chrome switcher

---

## Bot commits (26h)

**`mctl-agents` author:** 0 commits.

Other automated activity in `mctl-gitops` during the same window (not mctl-agents):
- `argo-workflows[bot]` — 6 deploy commits (mctl-telegram 0.11–0.13, mctl-design 0.1–0.3 + onboard)
- `mctl-deploy` — 7 commits (CI build secrets, quota bump, mctl-agent env vars, mctl-design domain, Claude review CI)
- `Claude` — 1 commit: `chore(daily-report): 2026-05-16 pipeline snapshot`

---

## Detected problems

### Stale PRs

| PR | Days inactive | Stable? | Action |
|----|--------------|---------|--------|
| [mctl-gitops#84](https://github.com/mctlhq/mctl-gitops/pull/84) [DRAFT] per-proposal claim mechanism | **17 days** (since 2026-04-30) | ✓ flagged in 6+ reports | Follow-up comment → [#188](https://github.com/mctlhq/mctl-gitops/issues/188#issuecomment-4470049848) |
| [mctl-agents#15](https://github.com/mctlhq/mctl-agents/pull/15) Tier 2 implementer agents | 8 days | First day >7d | Watching — will flag tomorrow if still stale |
| [mctl-agents#16](https://github.com/mctlhq/mctl-agents/pull/16) rotate mentor digests >8w | 8 days | First day >7d | Watching |
| [mctl-agents#17](https://github.com/mctlhq/mctl-agents/pull/17) mctl-docs GitHub API fallback | 8 days | First day >7d | Watching |
| [mctl-api#47](https://github.com/mctlhq/mctl-api/pull/47) mctl_create_preview build-from-branch | 7 days | First day >7d | Watching |
| [mctl-portal#7](https://github.com/mctlhq/mctl-portal/pull/7) [DRAFT] /proposals page | 7 days since 2026-05-10 | Reset by May-10 activity | Watching; tracked by existing issue [#121](https://github.com/mctlhq/mctl-gitops/issues/121) |

**mctl-api dep bumps approaching threshold:** PRs [#50](https://github.com/mctlhq/mctl-api/pull/50), [#51](https://github.com/mctlhq/mctl-api/pull/51), [#52](https://github.com/mctlhq/mctl-api/pull/52), [#53](https://github.com/mctlhq/mctl-api/pull/53) last updated 2026-05-11 (6 days). Cross 7d threshold on 2026-05-18 if still open.

### No stuck proposals

All 20 proposals are in terminal state (merged or rejected). No `in-progress` or `proposed` items.

---

## Cluster health

_api.mctl.ai MCP connector attached this run for the first time — partial cluster data below._

### Active incidents (3)

| severity | service | summary | status | created (UTC) |
|----------|---------|---------|--------|---------------|
| warning | admins / admins-mctl-agent | ArgoCD app OutOfSync for 1h | analyzing | 2026-05-17 04:16 |
| warning | admins / admins-mctl-agent | ArgoCD app OutOfSync for 1h _(duplicate alert)_ | analyzing | 2026-05-16 12:57 |
| warning | admins / monitoring-kube-state-metrics | Namespace quota going to be full | analyzing | 2026-05-16 10:49 |

**Context:** The namespace quota warning fired at 10:49 — ~7 h before the CPU quota raise (PR #218, merged ~17:38 UTC). The quota-pressure alert may still be open because ArgoCD hasn't fully synced the new quota object, or because the raise hasn't been sufficient. The `admins-mctl-agent` OutOfSync alert is notable: the mctl-agent image was bumped to 1.14.0 in PR #215 (merged ~11:16 UTC) and a fix commit followed at ~11:16 UTC, but ArgoCD still reports OutOfSync as of 04:16 today. None of the three incidents has a proposed fix or open PR from `mctl-agent` (all at MEDIUM confidence, `analyzing` status).

### Workflow runs (last 26h — via mctl_list_workflows)

12 `deploy-service` workflows submitted on 2026-05-16, all triggered by `mashkovd`:
- **labs** (7): mctl-telegram deployments across multiple versions + mctl-design
- **admins** (5): mctl-design, mctl-agent, mctl-web redesign + rollback

All return status `submitted`. Per-workflow completion status requires `mctl_get_workflow_status` per run — not fetched this cycle to limit API calls.

_MinIO PVC %, per-service restart counts: not available via current MCP tool set._

---

## Errors during run

- `gh` CLI not present in PATH — all GitHub operations performed via MCP tools instead.
- GitHub MCP session scoped to `mctlhq/mctl-gitops` only. Cannot read/write `mctlhq/mctl-agents`. Daily report posted to `mctlhq/mctl-gitops`; stand-alone stale-pr issues for `mctlhq/mctl-agents` PRs cannot be filed until MCP scope is expanded.
- Previous daily report retrieved from `mctlhq/mctl-gitops` (issue #213, 2026-05-15) — same workaround as prior runs.

---

## TODO

- **MCP scope:** Expand GitHub MCP allowed-repositories to include `mctlhq/mctl-agents` to enable posting daily reports and stand-alone issues to the correct repo.
- **Workflow completion:** Add `mctl_get_workflow_status` calls per-run to surface failed workflow runs in the daily report (currently all show `submitted`).
- **ArgoCD sync state:** Use `mctl_get_service_status` to pull per-service sync/health state rather than relying solely on AlertManager incidents.
- **Cluster resource usage:** Wire in `mctl_get_resource_usage` for MinIO PVC % and namespace quota fill rates now that the connector is available.
