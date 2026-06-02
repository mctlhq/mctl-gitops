## Summary

Pipeline snapshot for **2026-06-02 09:00 UTC** — first daily-report run (no prior report to diff against). **46 proposals tracked** across 10 repos: 39 merged, 5 rejected, **2 stuck in `proposed`** with `requires_human_approval: true` since 2026-05-25 (8 days). No bot commits from `mctl-agents` in the last 26 h. Heavy activity on `mctl-pairdesk` (9 PRs merged in 24 h) and `mctl-loyalty`/`mctl-design`. 15 open PRs are inactive >7 days; stand-alone issues filed for non-auto PRs inactive >14 days (blocked — see §Errors).

---

## Proposal pipeline state

| repo | slug | status | pr | changed\_since\_yesterday |
|------|------|--------|----|--------------------------|
| mctl-agent | incident-auto-cleanup-phase1 | merged | [#11](https://github.com/mctlhq/mctl-agent/pull/11) | — |
| mctl-agent | incident-auto-cleanup-phase2 | merged | [#13](https://github.com/mctlhq/mctl-agent/pull/13) | — |
| mctl-agent | incident-auto-cleanup-phase3 | merged | [#12](https://github.com/mctlhq/mctl-agent/pull/12) | — |
| mctl-agent | incident-auto-cleanup-phase4a-metrics-wiring | merged | [#16](https://github.com/mctlhq/mctl-agent/pull/16) | — |
| mctl-agent | incident-auto-cleanup-phase4b-metrics-full | merged | [#17](https://github.com/mctlhq/mctl-agent/pull/17) | — |
| mctl-agent | incident-auto-cleanup-phase4-metrics | **rejected** | — | — |
| mctl-agent | sqlite-cve-patch | merged | [#9](https://github.com/mctlhq/mctl-agent/pull/9) | — |
| mctl-agents | tier3-pr-shepherd | merged | [#12](https://github.com/mctlhq/mctl-agents/pull/12) | — |
| mctl-api | chi-security-patch | merged | [#39](https://github.com/mctlhq/mctl-api/pull/39) | — |
| mctl-api | pgx-sqli-cve-2025-54236 | merged | [#40](https://github.com/mctlhq/mctl-api/pull/40) | — |
| mctl-design | issue-3-change-the-storybook-overview-brand-icon | merged | [#8](https://github.com/mctlhq/mctl-design/pull/8) | — |
| mctl-design | issue-4-rename-storybook-brand-title-to-mctl-ui | merged | [#5](https://github.com/mctlhq/mctl-design/pull/5) | — |
| mctl-design | issue-6-align-storybook-page-title-og-title-with | merged | [#7](https://github.com/mctlhq/mctl-design/pull/7) | — |
| mctl-docs | fix-broken-mctl-ai-mcp-links | merged | [#6](https://github.com/mctlhq/mctl-docs/pull/6) | — |
| mctl-docs | mcp-agents-tools | merged | [#7](https://github.com/mctlhq/mctl-docs/pull/7) | — |
| mctl-gitops | argo-workflows-cve-patch-v2 | merged | [#85](https://github.com/mctlhq/mctl-gitops/pull/85) | — |
| mctl-gitops | argocd-informer-cache-patch | merged | [#90](https://github.com/mctlhq/mctl-gitops/pull/90) | — |
| mctl-gitops | eso-cve-patch | merged | [#87](https://github.com/mctlhq/mctl-gitops/pull/87) | — |
| mctl-gitops | grafana-sql-rce-patch | merged | [#89](https://github.com/mctlhq/mctl-gitops/pull/89) | — |
| mctl-openclaw | issue-25-ci-add-claude-review-yml-automated-pr-re | merged | [#26](https://github.com/mctlhq/mctl-openclaw/pull/26) | — |
| mctl-openclaw | upgrade-to-2026-4-27 | **rejected** | [#15](https://github.com/mctlhq/mctl-openclaw/pull/15) | — |
| mctl-portal | scaffolder-path-traversal | **rejected** | [#10](https://github.com/mctlhq/mctl-portal/pull/10) | — |
| mctl-portal | scaffolder-secret-leak | **rejected** | [#12](https://github.com/mctlhq/mctl-portal/pull/12) | — |
| mctl-telegram | issue-59-add-observability-and-alerting-for-mctl | merged | [#61](https://github.com/mctlhq/mctl-telegram/pull/61) | — |
| mctl-telegram | issue-66-scalability-audit-and-hardening-for-100 | merged | [#72](https://github.com/mctlhq/mctl-telegram/pull/72) | — |
| mctl-telegram | issue-67-build-browser-based-telegram-account-onb | merged | [#73](https://github.com/mctlhq/mctl-telegram/pull/73) | — |
| mctl-telegram | issue-68-redesign-tg-mctl-ai-landing-page-for-cli | merged | [#74](https://github.com/mctlhq/mctl-telegram/pull/74) | — |
| mctl-telegram | issue-69-improve-mobile-responsiveness-of-tg-mctl | merged | [#75](https://github.com/mctlhq/mctl-telegram/pull/75) | — |
| mctl-telegram | issue-70-add-user-friendly-error-message-catalog | merged | [#76](https://github.com/mctlhq/mctl-telegram/pull/76) | — |
| mctl-telegram | issue-71-test-smoke-test-log-build-version-git-sh | **rejected** | — | — |
| mctl-telegram | issue-86-ship-prometheusrule-manifests-for-produc | merged | [#112](https://github.com/mctlhq/mctl-telegram/pull/112) | — |
| mctl-telegram | issue-87-grafana-dashboard-for-beta-operations | merged | [#95](https://github.com/mctlhq/mctl-telegram/pull/95) | — |
| mctl-telegram | issue-88-define-beta-slos-and-burn-rate-alerts | merged | [#113](https://github.com/mctlhq/mctl-telegram/pull/113) | — |
| mctl-telegram | issue-89-synthetic-end-to-end-canary-oauth-list-d | merged | [#96](https://github.com/mctlhq/mctl-telegram/pull/96) | — |
| mctl-telegram | issue-90-beta-capacity-profile-load-test-tuned-co | merged | [#114](https://github.com/mctlhq/mctl-telegram/pull/114) | — |
| mctl-telegram | issue-91-sticky-routing-by-user-id-for-multi-repl | merged | [#132](https://github.com/mctlhq/mctl-telegram/pull/132) | — |
| mctl-telegram | issue-92-operational-runbook-for-beta-top-n-incid | merged | [#115](https://github.com/mctlhq/mctl-telegram/pull/115) | — |
| mctl-telegram | issue-93-unified-connect-wizard-oidc-enable-acces | merged | [#99](https://github.com/mctlhq/mctl-telegram/pull/99) | — |
| mctl-telegram | issue-94-local-bridge-m4-finish-community-release | merged | [#125](https://github.com/mctlhq/mctl-telegram/pull/125) | — |
| mctl-telegram | issue-154-nav-replace-github-text-link-with-a-gith | merged | [#157](https://github.com/mctlhq/mctl-telegram/pull/157) | — |
| mctl-telegram | issue-158-non-deterministic-safety-block-on-get-me | merged | [#162](https://github.com/mctlhq/mctl-telegram/pull/162) | — |
| mctl-telegram | issue-159-live-send-unusable-when-prepare-send-mes | merged | [#163](https://github.com/mctlhq/mctl-telegram/pull/163) | — |
| mctl-telegram | issue-202-mctl-telegram-canary-cronjob-stuck-on-im | merged | [#211](https://github.com/mctlhq/mctl-telegram/pull/211) | — |
| mctl-telegram | **issue-213-deploy-canary-prometheusrule-to-cluster** | **proposed** | — | new |
| mctl-telegram | **issue-214-self-service-canonicalize-client-tier-in** | **proposed** | — | new |
| mctl-web | wrangler-upgrade-security | merged | [#9](https://github.com/mctlhq/mctl-web/pull/9) | — |

**Totals:** 46 proposals — 39 merged · 5 rejected · 2 proposed · 0 in-progress

---

## Pipeline diff (vs yesterday)

> **First run** — no prior `daily-report` issue found in `mctlhq/mctl-agents`. Full state shown above; diff will appear from tomorrow onward.

---

## Recent merged PRs (24 h)

Merged since 2026-06-01 00:00 UTC:

| repo | PR | title | merged at |
|------|----|-------|-----------|
| mctlhq/mctl-pairdesk | [#18](https://github.com/mctlhq/mctl-pairdesk/pull/18) | fix(admin): show creator username instead of internal user id in orders list | 2026-06-02 06:04 |
| mctlhq/mctl-pairdesk | [#17](https://github.com/mctlhq/mctl-pairdesk/pull/17) | Telegram Mini App UX overhaul + review fixes | 2026-06-01 23:07 |
| mctlhq/mctl-pairdesk | [#16](https://github.com/mctlhq/mctl-pairdesk/pull/16) | feat: surface community member count in UI | 2026-06-01 20:09 |
| mctlhq/mctl-pairdesk | [#15](https://github.com/mctlhq/mctl-pairdesk/pull/15) | feat: richer deal info — bot notifications + tappable contacts | 2026-06-01 18:47 |
| mctlhq/mctl-pairdesk | [#14](https://github.com/mctlhq/mctl-pairdesk/pull/14) | feat: add Wirex and Wise as payment methods | 2026-06-01 16:36 |
| mctlhq/mctl-pairdesk | [#13](https://github.com/mctlhq/mctl-pairdesk/pull/13) | feat(ux): clearer deals card and bot notification copy | 2026-06-01 16:04 |
| mctlhq/mctl-pairdesk | [#12](https://github.com/mctlhq/mctl-pairdesk/pull/12) | feat: admin deals view, auto-reject notifications, tap-to-chat | 2026-06-01 15:54 |
| mctlhq/mctl-pairdesk | [#11](https://github.com/mctlhq/mctl-pairdesk/pull/11) | fix(deals): notify responder when deal rejected | 2026-06-01 15:14 |
| mctlhq/mctl-pairdesk | [#4](https://github.com/mctlhq/mctl-pairdesk/pull/4) | feat(web): implement Direction C design system | 2026-06-01 09:21 |
| mctlhq/mctl-design | [#13](https://github.com/mctlhq/mctl-design/pull/13) | feat: MCTL Mini App Kit — Telegram section in ui.mctl.ai | 2026-06-01 07:18 |
| mctlhq/mctl-loyalty | [#19](https://github.com/mctlhq/mctl-loyalty/pull/19) | feat(landing): real device screenshots in place of CSS mockups | 2026-06-01 07:19 |
| mctlhq/mctl-loyalty | [#18](https://github.com/mctlhq/mctl-loyalty/pull/18) | feat(landing): refresh admin mockups + copy for tabbed role-based admin | 2026-06-01 06:51 |
| mctlhq/mctl-loyalty | [#17](https://github.com/mctlhq/mctl-loyalty/pull/17) | feat(web): redesign admin Mini App to Direction C, role-based tabs | 2026-06-01 06:18 |
| mctlhq/mctl-gitops | [#367](https://github.com/mctlhq/mctl-gitops/pull/367) | fix(pairdesk): inject SERVICE_VERSION env var | 2026-06-01 06:09 |
| mctlhq/mctl-pairdesk | [#3](https://github.com/mctlhq/mctl-pairdesk/pull/3) | feat: Stage 4-5 — subscription matching, pagination, rate limit, bot hardening | 2026-06-01 05:53 |

---

## Bot commits (24 h)

`git log --author="mctl-agents" --since="26 hours ago"` returned **no results**. No automated commits from the agent pipeline in the last 26 h.

---

## Detected problems

### Stuck proposals (>7 days in `proposed`, `requires_human_approval: true`)

Both proposals below have been awaiting human approval since **2026-05-25** (8 days). Stand-alone issues could not be filed — see §Errors.

| proposal | source issue | since | requires\_human\_approval |
|----------|-------------|-------|--------------------------|
| issue-213-deploy-canary-prometheusrule-to-cluster | [mctl-telegram#213](https://github.com/mctlhq/mctl-telegram/issues/213) | 2026-05-25 | true |
| issue-214-self-service-canonicalize-client-tier-in | [mctl-telegram#214](https://github.com/mctlhq/mctl-telegram/issues/214) | 2026-05-25 | true |

### Stale open PRs (>7 days no activity)

| repo | PR | title | last activity | days |
|------|----|-------|--------------|------|
| mctlhq/mctl-gitops | [#84](https://github.com/mctlhq/mctl-gitops/pull/84) | [wip] feat(agents): per-proposal claim mechanism | 2026-04-30 | ~33 |
| mctlhq/mctl-portal | [#7](https://github.com/mctlhq/mctl-portal/pull/7) | feat(app): add /proposals page for agents review | 2026-05-10 | ~23 |
| mctlhq/mctl-api | [#47](https://github.com/mctlhq/mctl-api/pull/47) | feat(mcp): mctl_create_preview — build from branch support | 2026-05-10 | ~23 |
| mctlhq/mctl-agents | [#15](https://github.com/mctlhq/mctl-agents/pull/15) | feat(orchestrator): Tier 2 implementer agents | 2026-05-09 | ~24 |
| mctlhq/mctl-agents | [#16](https://github.com/mctlhq/mctl-agents/pull/16) | feat(orchestrator): rotate mentor digests older than 8 weeks | 2026-05-09 | ~24 |
| mctlhq/mctl-agents | [#17](https://github.com/mctlhq/mctl-agents/pull/17) | feat(mctl-docs): fallback to GitHub API when sibling clones absent | 2026-05-09 | ~24 |
| mctlhq/mctl-gitops | [#217](https://github.com/mctlhq/mctl-gitops/pull/217) | feat(argo): add incident responder CronWorkflow | 2026-05-16 | ~17 |
| mctlhq/mctl-agent | [#20](https://github.com/mctlhq/mctl-agent/pull/20) | feat(skills): add statefulset-replicas-mismatch YAML skill | 2026-05-16 | ~17 |
| mctlhq/mctl-telegram | [#146](https://github.com/mctlhq/mctl-telegram/pull/146) | Enhance landing page UX: card animations, SVG icons, and social meta tags | 2026-05-22 | ~11 |
| mctlhq/mctl-gitops | [#306](https://github.com/mctlhq/mctl-gitops/pull/306) | fix(observability): bring prometheus-pushgateway into gitops + fix scrape | 2026-05-25 | ~8 |

Also inactive >7 days but auto-generated (not filed): `mctlhq/mctl-api` #51, #55–#58 (deps bumps, 15–22 d).

Stand-alone issues for the above could not be filed — see §Errors.

---

## Cluster health

Skipped: api.mctl.ai MCP connector not attached yet. See TODO at the bottom of this issue.

---

## Errors during run

- **`mctlhq/mctl-agents` write access denied.** The GitHub MCP token for this cloud session is scoped to `mctlhq/mctl-gitops` only (`list_issues` returned *"Access denied: repository not configured for this session"*). As a result:
  - The daily-report issue itself was posted to `mctlhq/mctl-gitops` (fallback).
  - Stand-alone `stuck-proposal` issues for `issue-213` and `issue-214` could not be filed.
  - Stand-alone `stale-pr` issues for the 8+ stale PRs listed above could not be filed.
  - **Action required:** Add `mctlhq/mctl-agents` to the allowed-repository list for this scheduled agent session (see session config at https://code.claude.com/docs/en/claude-code-on-the-web).

---

## TODO

Attach the api.mctl.ai MCP connector to this routine to unlock workflow-run counts (`mctl_list_workflows`), MinIO PVC % (`mctl_get_resource_usage`), per-service restart counts (`mctl_get_service_status`), and ArgoCD app sync state.
