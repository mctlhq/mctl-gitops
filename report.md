# [daily-report] 2026-06-16 pipeline summary

> **⚠️ POSTING BLOCKED**: This report could not be posted to `mctlhq/mctl-agents` because the GitHub MCP session is scoped to `mctlhq/mctl-gitops` only. The full report is included here. See §8 Errors for details and remediation.

---

## 1. Summary

- **57 proposals** tracked across 10 repos; **49 merged**, **6 rejected**, **4 stuck in `proposed`** (no in-progress).
- **0 bot commits** and **0 merged PRs** in the last 24 h — pipeline quiet since June 12 (security/docs fixes) and June 3 (mctl-pairdesk sprint wave).
- **4 proposals stuck in `proposed` > 7 days**: 2 in mctl-telegram (~22 d), 2 in mctl-pairdesk (~12 d).
- **Active cluster alert**: `mctl-telegram` fired "no tool invocations for 15 minutes" at 08:36 UTC today. Five Vmagent scrape-pool warnings open since May 21–22 without resolution.
- **This is the first run** — no previous `daily-report` issue exists to diff against.

---

## 2. Proposal pipeline state

| repo | slug | status | pr | changed |
|------|------|--------|----|---------|
| mctl-agent | incident-auto-cleanup-phase1 | merged | [#11](https://github.com/mctlhq/mctl-agent/pull/11) | new |
| mctl-agent | incident-auto-cleanup-phase2 | merged | [#13](https://github.com/mctlhq/mctl-agent/pull/13) | new |
| mctl-agent | incident-auto-cleanup-phase3 | merged | [#12](https://github.com/mctlhq/mctl-agent/pull/12) | new |
| mctl-agent | incident-auto-cleanup-phase4-metrics | rejected | — | new |
| mctl-agent | incident-auto-cleanup-phase4a-metrics-wiring | merged | [#16](https://github.com/mctlhq/mctl-agent/pull/16) | new |
| mctl-agent | incident-auto-cleanup-phase4b-metrics-full | merged | [#17](https://github.com/mctlhq/mctl-agent/pull/17) | new |
| mctl-agent | sqlite-cve-patch | merged | [#9](https://github.com/mctlhq/mctl-agent/pull/9) | new |
| mctl-agents | tier3-pr-shepherd | merged | [#12](https://github.com/mctlhq/mctl-agents/pull/12) | new |
| mctl-api | chi-security-patch | merged | [#39](https://github.com/mctlhq/mctl-api/pull/39) | new |
| mctl-api | pgx-sqli-cve-2025-54236 | merged | [#40](https://github.com/mctlhq/mctl-api/pull/40) | new |
| mctl-design | issue-3-change-the-storybook-overview-brand-icon | merged | [#8](https://github.com/mctlhq/mctl-design/pull/8) | new |
| mctl-design | issue-4-rename-storybook-brand-title-to-mctl-ui | merged | [#5](https://github.com/mctlhq/mctl-design/pull/5) | new |
| mctl-design | issue-6-align-storybook-page-title-og-title-with | merged | [#7](https://github.com/mctlhq/mctl-design/pull/7) | new |
| mctl-docs | fix-broken-mctl-ai-mcp-links | merged | [#6](https://github.com/mctlhq/mctl-docs/pull/6) | new |
| mctl-docs | mcp-agents-tools | merged | [#7](https://github.com/mctlhq/mctl-docs/pull/7) | new |
| mctl-gitops | argo-workflows-cve-patch-v2 | merged | [#85](https://github.com/mctlhq/mctl-gitops/pull/85) | new |
| mctl-gitops | argocd-informer-cache-patch | merged | [#90](https://github.com/mctlhq/mctl-gitops/pull/90) | new |
| mctl-gitops | eso-cve-patch | merged | [#87](https://github.com/mctlhq/mctl-gitops/pull/87) | new |
| mctl-gitops | grafana-sql-rce-patch | merged | [#89](https://github.com/mctlhq/mctl-gitops/pull/89) | new |
| mctl-openclaw | issue-25-ci-add-claude-review-yml | merged | [#26](https://github.com/mctlhq/mctl-openclaw/pull/26) | new |
| mctl-openclaw | upgrade-to-2026-4-27 | rejected | [#15](https://github.com/mctlhq/mctl-openclaw/pull/15) | new |
| mctl-pairdesk | issue-22-feat-web-create-order-step-1-currency-pa | merged | [#27](https://github.com/mctlhq/mctl-pairdesk/pull/27) | new |
| mctl-pairdesk | issue-23-feat-web-create-order-step-2-coupled-dua | merged | [#30](https://github.com/mctlhq/mctl-pairdesk/pull/30) | new |
| mctl-pairdesk | issue-24-feat-redesign-create-order-into-a-t-bank | merged | [#31](https://github.com/mctlhq/mctl-pairdesk/pull/31) | new |
| mctl-pairdesk | issue-28-fix-web-create-order-step-1-collision-au | merged | [#29](https://github.com/mctlhq/mctl-pairdesk/pull/29) | new |
| mctl-pairdesk | issue-33-fix-web-hide-app-tab-bar-during-create-o | merged | [#41](https://github.com/mctlhq/mctl-pairdesk/pull/41) | new |
| mctl-pairdesk | issue-34-fix-web-rework-create-order-step-navigat | merged | [#42](https://github.com/mctlhq/mctl-pairdesk/pull/42) | new |
| mctl-pairdesk | issue-35-fix-web-city-notes-section-layout-overfl | merged | [#39](https://github.com/mctlhq/mctl-pairdesk/pull/39) | new |
| mctl-pairdesk | issue-36-fix-web-entered-city-missing-from-live-p | merged | [#40](https://github.com/mctlhq/mctl-pairdesk/pull/40) | new |
| mctl-pairdesk | issue-37-feat-web-one-currency-pair-per-order-rem | merged | [#43](https://github.com/mctlhq/mctl-pairdesk/pull/43) | new |
| mctl-pairdesk | issue-38-fix-web-rate-slider-must-anchor-the-last | merged | [#44](https://github.com/mctlhq/mctl-pairdesk/pull/44) | new |
| mctl-pairdesk | issue-45-add-web-test-harness-rateslider-anchorin | merged | [#46](https://github.com/mctlhq/mctl-pairdesk/pull/46) | new |
| mctl-pairdesk | issue-5-feat-add-landing-page-astro-like-mctl-lo | merged | [#32](https://github.com/mctlhq/mctl-pairdesk/pull/32) | new |
| mctl-pairdesk | **issue-52-p3-add-native-showconfirm-for-destructiv** | **⚠️ proposed** | — | new · 12d |
| mctl-pairdesk | **issue-53-p3-create-order-has-no-ttl-expiry-picker** | **⚠️ proposed** | — | new · 12d |
| mctl-portal | scaffolder-path-traversal | rejected | [#10](https://github.com/mctlhq/mctl-portal/pull/10) | new |
| mctl-portal | scaffolder-secret-leak | rejected | [#12](https://github.com/mctlhq/mctl-portal/pull/12) | new |
| mctl-telegram | issue-154-nav-replace-github-text-link-with-a-gith | merged | [#157](https://github.com/mctlhq/mctl-telegram/pull/157) | new |
| mctl-telegram | issue-158-non-deterministic-safety-block-on-get-me | merged | [#162](https://github.com/mctlhq/mctl-telegram/pull/162) | new |
| mctl-telegram | issue-159-live-send-unusable-when-prepare-send-mes | merged | [#163](https://github.com/mctlhq/mctl-telegram/pull/163) | new |
| mctl-telegram | issue-202-mctl-telegram-canary-cronjob-stuck-on-im | merged | [#211](https://github.com/mctlhq/mctl-telegram/pull/211) | new |
| mctl-telegram | **issue-213-deploy-canary-prometheusrule-to-cluster** | **⚠️ proposed** | — | new · 22d |
| mctl-telegram | **issue-214-self-service-canonicalize-client-tier-in** | **⚠️ proposed** | — | new · 22d |
| mctl-telegram | issue-59-add-observability-and-alerting-for-mctl | merged | [#61](https://github.com/mctlhq/mctl-telegram/pull/61) | new |
| mctl-telegram | issue-66-scalability-audit-and-hardening-for-100 | merged | [#72](https://github.com/mctlhq/mctl-telegram/pull/72) | new |
| mctl-telegram | issue-67-build-browser-based-telegram-account-onb | merged | [#73](https://github.com/mctlhq/mctl-telegram/pull/73) | new |
| mctl-telegram | issue-68-redesign-tg-mctl-ai-landing-page-for-cli | merged | [#74](https://github.com/mctlhq/mctl-telegram/pull/74) | new |
| mctl-telegram | issue-69-improve-mobile-responsiveness-of-tg-mctl | merged | [#75](https://github.com/mctlhq/mctl-telegram/pull/75) | new |
| mctl-telegram | issue-70-add-user-friendly-error-message-catalog | merged | [#76](https://github.com/mctlhq/mctl-telegram/pull/76) | new |
| mctl-telegram | issue-71-test-smoke-test-log-build-version-git-sh | rejected | — | new |
| mctl-telegram | issue-86-ship-prometheusrule-manifests-for-produc | merged | [#112](https://github.com/mctlhq/mctl-telegram/pull/112) | new |
| mctl-telegram | issue-87-grafana-dashboard-for-beta-operations | merged | [#95](https://github.com/mctlhq/mctl-telegram/pull/95) | new |
| mctl-telegram | issue-88-define-beta-slos-and-burn-rate-alerts | merged | [#113](https://github.com/mctlhq/mctl-telegram/pull/113) | new |
| mctl-telegram | issue-89-synthetic-end-to-end-canary-oauth-list-d | merged | [#96](https://github.com/mctlhq/mctl-telegram/pull/96) | new |
| mctl-telegram | issue-90-beta-capacity-profile-load-test-tuned-co | merged | [#114](https://github.com/mctlhq/mctl-telegram/pull/114) | new |
| mctl-telegram | issue-91-sticky-routing-by-user-id-for-multi-repl | merged | [#132](https://github.com/mctlhq/mctl-telegram/pull/132) | new |
| mctl-telegram | issue-92-operational-runbook-for-beta-top-n-incid | merged | [#115](https://github.com/mctlhq/mctl-telegram/pull/115) | new |
| mctl-telegram | issue-93-unified-connect-wizard-oidc-enable-acces | merged | [#99](https://github.com/mctlhq/mctl-telegram/pull/99) | new |
| mctl-telegram | issue-94-local-bridge-m4-finish-community-release | merged | [#125](https://github.com/mctlhq/mctl-telegram/pull/125) | new |
| mctl-web | wrangler-upgrade-security | merged | [#9](https://github.com/mctlhq/mctl-web/pull/9) | new |

---

## 3. Pipeline diff (vs yesterday)

**First run** — no previous `daily-report` issue found. All entries are baseline.

- Newly merged: n/a (first snapshot)
- Newly rejected: n/a (first snapshot)
- Newly proposed: n/a (first snapshot)
- Still in-progress: none
- Still proposed (needing action):
  - `mctl-telegram/issue-213` — 22 d in `proposed`, no PR
  - `mctl-telegram/issue-214` — 22 d in `proposed`, no PR
  - `mctl-pairdesk/issue-52` — 12 d in `proposed`, no PR
  - `mctl-pairdesk/issue-53` — 12 d in `proposed`, no PR

---

## 4. Recent merged PRs (24 h)

No merged PRs detected across `mctlhq/*` in the last 24 h (GitHub search `merged:>=2026-06-15` returned 0).

Most recent activity was 2026-06-12: batch of security/docs/gitops fixes across mctl-portal, mctl-web, mctl-docs, mctl-gitops, mctl-agents.

---

## 5. Bot commits (24 h)

No commits by `mctl-agents` in the past 26 h (`git log --author="mctl-agents" --since="26 hours ago"` — empty).

Agent cron is healthy: 9 of last 10 `mctl-agents-implement` cron runs succeeded; 1 currently `submitted` (09:10 UTC).

---

## 6. Detected problems

### Stuck proposals (>7 d in `proposed`, no PR)

| proposal | repo | days | source issue |
|----------|------|------|-------------|
| issue-213-deploy-canary-prometheusrule-to-cluster | mctl-telegram | **22 d** | [#213](https://github.com/mctlhq/mctl-telegram/issues/213) |
| issue-214-self-service-canonicalize-client-tier-in | mctl-telegram | **22 d** | [#214](https://github.com/mctlhq/mctl-telegram/issues/214) |
| issue-52-p3-add-native-showconfirm-for-destructiv | mctl-pairdesk | **12 d** | [#52](https://github.com/mctlhq/mctl-pairdesk/issues/52) |
| issue-53-p3-create-order-has-no-ttl-expiry-picker | mctl-pairdesk | **12 d** | [#53](https://github.com/mctlhq/mctl-pairdesk/issues/53) |

Stand-alone issues NOT created — `mctlhq/mctl-agents` write access blocked (see §8).

### Stale open PRs (>30 days no activity)

| repo | PR | days | title |
|------|----|------|-------|
| mctlhq/mctl-gitops | [#84](https://github.com/mctlhq/mctl-gitops/pull/84) | **46 d** | [wip] per-proposal claim mechanism for parallel implementer |
| mctlhq/mctl-api | [#47](https://github.com/mctlhq/mctl-api/pull/47) | **37 d** | feat(mcp): mctl_create_preview — build from branch support |
| mctlhq/mctl-agents | [#15](https://github.com/mctlhq/mctl-agents/pull/15) | **37 d** | feat(orchestrator): Tier 2 implementer agents |
| mctlhq/mctl-agents | [#16](https://github.com/mctlhq/mctl-agents/pull/16) | **37 d** | feat(orchestrator): rotate mentor digests older than 8 weeks |
| mctlhq/mctl-agents | [#17](https://github.com/mctlhq/mctl-agents/pull/17) | **37 d** | feat(mctl-docs): fallback to GitHub API when sibling clones absent |
| mctlhq/mctl-portal | [#7](https://github.com/mctlhq/mctl-portal/pull/7) | **36 d** | feat(app): add /proposals page for agents review |
| mctlhq/mctl-api | [#51](https://github.com/mctlhq/mctl-api/pull/51) | **36 d** | deps: bump coreos/go-oidc/v3 |
| mctlhq/mctl-gitops | [#217](https://github.com/mctlhq/mctl-gitops/pull/217) | **30 d** | feat(argo): add incident responder CronWorkflow |
| mctlhq/mctl-agent | [#20](https://github.com/mctlhq/mctl-agent/pull/20) | **30 d** | feat(skills): add statefulset-replicas-mismatch YAML skill |

25 additional PRs are stale 7–29 d (mostly Dependabot and release-please). Stale-PR issues NOT created due to same access block.

---

## 7. Cluster health

**api.mctl.ai MCP connector attached** (c4e6fa5a). Data collected directly.

### Active incidents (7)

| # | severity | tenant/service | summary | since |
|---|----------|---------------|---------|-------|
| 1 | ⚠️ warning | labs / mctl-telegram | **No tool invocations for 15 min** | 2026-06-16 08:36 UTC ← NEW |
| 2 | ⚠️ warning | monitoring | Vmagent scrape_pool with 0 targets | 2026-06-16 08:22 UTC |
| 3–7 | ⚠️ warning | monitoring | Vmagent scrape_pool with 0 targets | 2026-05-21–22 (×5, unresolved 25d) |

The 5 May 21–22 Vmagent warnings are chronically unresolved. This likely relates to a missing prometheus-pushgateway scrape target; see also stale PR [mctlhq/mctl-gitops#306](https://github.com/mctlhq/mctl-gitops/pull/306) (21 d stale, brings pushgateway into gitops).

### Agent pipeline cron (last 10 runs)

| operation | status | triggered | timestamp |
|-----------|--------|-----------|-----------|
| mctl-agents-implement | submitted | cron | 2026-06-16 09:10 |
| mctl-agents-implement | ✅ succeeded | cron | 2026-06-16 09:05 |
| mctl-agents-implement | ✅ succeeded | cron | 2026-06-16 09:00 |
| mctl-agents-issue-poll | ✅ succeeded | cron | 2026-06-16 09:00 |
| mctl-agents-shepherd | ✅ succeeded | cron | 2026-06-16 09:00 |
| mctl-agents-implement | ✅ succeeded | cron | 2026-06-16 08:55 |
| mctl-agents-implement | ✅ succeeded | cron | 2026-06-16 08:50 |
| mctl-agents-implement | ✅ succeeded | cron | 2026-06-16 08:45 |
| mctl-agents-issue-poll | ✅ succeeded | cron | 2026-06-16 08:45 |
| mctl-agents-implement | ✅ succeeded | cron | 2026-06-16 08:40 |

Last operator deploy: 2026-06-09 (mashkoffdmitry, team labs).
Last operator mctl-agents-investigate: 2026-06-04 (mashkovd).

### Resource usage / ArgoCD sync state

Not collected this run (requires per-team iteration). Can be added next run.

---

## 8. Errors during run

### CRITICAL: Cannot post report to `mctlhq/mctl-agents`

```
Access denied: repository "mctlhq/mctl-agents" is not configured for this session.
Allowed repositories: mctlhq/mctl-gitops
```

**Impact**: Daily-report issue not created. 4 stuck-proposal issues and 9+ stale-PR issues could not be posted. This report exists only in the session transcript (ephemeral).

**Fix**: Add `mctlhq/mctl-agents` to the allowed repositories for this routine's GitHub App installation/session scope.

### Merged PR search returned 0 results

Queries for `merged:>=2026-06-15` returned 0. Either no merges occurred in the last 24 h, or GitHub search index lag.

---

## 9. TODO

- **[BLOCKING]** Add `mctlhq/mctl-agents` write access to this routine's GitHub MCP session — without it the report cannot be posted and no issues can be tracked.
- Create stuck-proposal issues for: mctl-telegram/issue-213, mctl-telegram/issue-214, mctl-pairdesk/issue-52, mctl-pairdesk/issue-53.
- Create stale-PR issues for 9 PRs stale >30 d.
- Investigate mctl-telegram "no tool invocations" alert (fired 08:36 UTC today).
- Resolve Vmagent 5× scrape-pool warnings (open since May 21 — 25 d). Review [mctlhq/mctl-gitops#306](https://github.com/mctlhq/mctl-gitops/pull/306).
- Review and close/merge 9 stale PRs >30 d. Oldest: [mctlhq/mctl-gitops#84](https://github.com/mctlhq/mctl-gitops/pull/84) (46 d, [wip]).
- Add per-team `mctl_get_resource_usage` and `mctl_get_service_status` polling to the next run.
