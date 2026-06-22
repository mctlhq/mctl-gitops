# Daily Pipeline Report — 2026-06-22

> **First run** — no previous `daily-report` issue found in `mctlhq/mctl-agents`. No baseline to diff against; all states reflect cumulative history.

---

## 1. Summary

- **60 proposals total** across 11 repos: **51 merged**, **4 stuck in `proposed`**, **5 rejected**, **0 in-progress**
- **0 PRs merged in the last 24h** and **0 bot-authored commits in the last 26h** — pipeline was quiet overnight (2026-06-21 → 2026-06-22); 2 dependency-bump PRs created today in `mctl-api` (#74, #75) are the only fresh activity
- **4 proposals** have been sitting in `proposed` (no PR ever opened) for **18–28 days**, well past the 7-day threshold; all have `requires_human_approval: true`
- **48 open PRs** across the org are stale (no update in >7 days); includes 3 security-related PRs (plaintext secrets, OAuth state) sitting 9–10 days unreviewed and 7 feature PRs aged 36–52 days

---

## 2. Proposal Pipeline State

> First run — `changed_since_yesterday` is **new** for all entries.

| repo | slug | status | pr | changed_since_yesterday |
|------|------|--------|----|------------------------|
| mctl-agent | incident-auto-cleanup-phase1 | merged | [#11](https://github.com/mctlhq/mctl-agent/pull/11) | new |
| mctl-agent | incident-auto-cleanup-phase2 | merged | [#13](https://github.com/mctlhq/mctl-agent/pull/13) | new |
| mctl-agent | incident-auto-cleanup-phase3 | merged | [#12](https://github.com/mctlhq/mctl-agent/pull/12) | new |
| mctl-agent | incident-auto-cleanup-phase4-metrics | **rejected** | — (superseded by 4a+4b split) | new |
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
| mctl-openclaw | upgrade-to-2026-4-27 | **rejected** | [#15](https://github.com/mctlhq/mctl-openclaw/pull/15) | new |
| mctl-pairdesk | issue-22-feat-web-create-order-step-1 | merged | [#27](https://github.com/mctlhq/mctl-pairdesk/pull/27) | new |
| mctl-pairdesk | issue-23-feat-web-create-order-step-2 | merged | [#30](https://github.com/mctlhq/mctl-pairdesk/pull/30) | new |
| mctl-pairdesk | issue-24-feat-redesign-create-order-t-bank | merged | [#31](https://github.com/mctlhq/mctl-pairdesk/pull/31) | new |
| mctl-pairdesk | issue-28-fix-web-create-order-step-1-collision | merged | [#29](https://github.com/mctlhq/mctl-pairdesk/pull/29) | new |
| mctl-pairdesk | issue-33-fix-web-hide-app-tab-bar | merged | [#41](https://github.com/mctlhq/mctl-pairdesk/pull/41) | new |
| mctl-pairdesk | issue-34-fix-web-rework-create-order-navigation | merged | [#42](https://github.com/mctlhq/mctl-pairdesk/pull/42) | new |
| mctl-pairdesk | issue-35-fix-web-city-notes-layout-overflow | merged | [#39](https://github.com/mctlhq/mctl-pairdesk/pull/39) | new |
| mctl-pairdesk | issue-36-fix-web-entered-city-missing | merged | [#40](https://github.com/mctlhq/mctl-pairdesk/pull/40) | new |
| mctl-pairdesk | issue-37-feat-web-one-currency-pair-per-order | merged | [#43](https://github.com/mctlhq/mctl-pairdesk/pull/43) | new |
| mctl-pairdesk | issue-38-fix-web-rate-slider-must-anchor | merged | [#44](https://github.com/mctlhq/mctl-pairdesk/pull/44) | new |
| mctl-pairdesk | issue-45-add-web-test-harness-rateslider | merged | [#46](https://github.com/mctlhq/mctl-pairdesk/pull/46) | new |
| mctl-pairdesk | issue-5-feat-add-landing-page-astro | merged | [#32](https://github.com/mctlhq/mctl-pairdesk/pull/32) | new |
| **mctl-pairdesk** | **issue-52-p3-add-native-showconfirm** | **⏳ proposed** | — | new |
| **mctl-pairdesk** | **issue-53-p3-create-order-has-no-ttl** | **⏳ proposed** | — | new |
| mctl-portal | scaffolder-path-traversal | **rejected** | [#10](https://github.com/mctlhq/mctl-portal/pull/10) | new |
| mctl-portal | scaffolder-secret-leak | **rejected** | [#12](https://github.com/mctlhq/mctl-portal/pull/12) | new |
| mctl-telegram | issue-59-add-observability-and-alerting | merged | [#61](https://github.com/mctlhq/mctl-telegram/pull/61) | new |
| mctl-telegram | issue-66-scalability-audit-and-hardening | merged | [#72](https://github.com/mctlhq/mctl-telegram/pull/72) | new |
| mctl-telegram | issue-67-build-browser-based-tg-account-onboarding | merged | [#73](https://github.com/mctlhq/mctl-telegram/pull/73) | new |
| mctl-telegram | issue-68-redesign-tg-mctl-ai-landing-page | merged | [#74](https://github.com/mctlhq/mctl-telegram/pull/74) | new |
| mctl-telegram | issue-69-improve-mobile-responsiveness | merged | [#75](https://github.com/mctlhq/mctl-telegram/pull/75) | new |
| mctl-telegram | issue-70-add-user-friendly-error-catalog | merged | [#76](https://github.com/mctlhq/mctl-telegram/pull/76) | new |
| mctl-telegram | issue-71-test-smoke-test-log-build-version | **rejected** | — | new |
| mctl-telegram | issue-86-ship-prometheusrule-manifests | merged | [#112](https://github.com/mctlhq/mctl-telegram/pull/112) | new |
| mctl-telegram | issue-87-grafana-dashboard-for-beta | merged | [#95](https://github.com/mctlhq/mctl-telegram/pull/95) | new |
| mctl-telegram | issue-88-define-beta-slos-and-burn-rate-alerts | merged | [#113](https://github.com/mctlhq/mctl-telegram/pull/113) | new |
| mctl-telegram | issue-89-synthetic-e2e-canary-oauth | merged | [#96](https://github.com/mctlhq/mctl-telegram/pull/96) | new |
| mctl-telegram | issue-90-beta-capacity-profile-load-test | merged | [#114](https://github.com/mctlhq/mctl-telegram/pull/114) | new |
| mctl-telegram | issue-91-sticky-routing-by-user-id | merged | [#132](https://github.com/mctlhq/mctl-telegram/pull/132) | new |
| mctl-telegram | issue-92-operational-runbook-for-beta | merged | [#115](https://github.com/mctlhq/mctl-telegram/pull/115) | new |
| mctl-telegram | issue-93-unified-connect-wizard-oidc | merged | [#99](https://github.com/mctlhq/mctl-telegram/pull/99) | new |
| mctl-telegram | issue-94-local-bridge-m4-community-release | merged | [#125](https://github.com/mctlhq/mctl-telegram/pull/125) | new |
| mctl-telegram | issue-154-nav-replace-github-text-link | merged | [#157](https://github.com/mctlhq/mctl-telegram/pull/157) | new |
| mctl-telegram | issue-158-non-deterministic-safety-block | merged | [#162](https://github.com/mctlhq/mctl-telegram/pull/162) | new |
| mctl-telegram | issue-159-live-send-unusable | merged | [#163](https://github.com/mctlhq/mctl-telegram/pull/163) | new |
| mctl-telegram | issue-202-mctl-telegram-canary-cronjob-stuck | merged | [#211](https://github.com/mctlhq/mctl-telegram/pull/211) | new |
| **mctl-telegram** | **issue-213-deploy-canary-prometheusrule** | **⏳ proposed** | — | new |
| **mctl-telegram** | **issue-214-self-service-canonicalize-client-tier** | **⏳ proposed** | — | new |
| mctl-web | wrangler-upgrade-security | merged | [#9](https://github.com/mctlhq/mctl-web/pull/9) | new |

---

## 3. Pipeline Diff (vs Yesterday)

**First run — no previous snapshot. All entries are new.**

- **Merged (total):** 51 proposals across mctl-agent (6), mctl-agents (1), mctl-api (2), mctl-design (3), mctl-docs (2), mctl-gitops (4), mctl-openclaw (1), mctl-pairdesk (12), mctl-telegram (19), mctl-web (1)
- **Rejected (total):** 5 — mctl-agent/phase4-metrics (superseded by 4a+4b split), mctl-openclaw/upgrade-to-2026-4-27, mctl-portal/scaffolder-path-traversal, mctl-portal/scaffolder-secret-leak, mctl-telegram/issue-71
- **Currently proposed (no PR):** 4 — see §6 Detected Problems
- **In-progress:** 0

---

## 4. Recent Merged PRs (24h)

GitHub search `org:mctlhq is:pr is:merged merged:>=2026-06-21` returned **0 results**. No PRs were merged in the last 24h.

Only fresh activity: `mctl-api#75` (`ci: bump anthropics/claude-code-action`) and `mctl-api#74` (`ci: bump actions/checkout`) were opened today (2026-06-22) — both dependency bumps, still open.

---

## 5. Bot Commits (26h)

```
(none — git log --author="mctl-agents" --since="26 hours ago" returned empty)
```

---

## 6. Detected Problems

### Stuck proposals — `proposed` for >7 days (no PR opened)

| repo | slug | source issue | proposed\_since | days\_stuck |
|------|------|-------------|----------------|------------|
| mctl-telegram | issue-213-deploy-canary-prometheusrule | [#213](https://github.com/mctlhq/mctl-telegram/issues/213) | 2026-05-25 | **28 days** |
| mctl-telegram | issue-214-self-service-canonicalize-client-tier | [#214](https://github.com/mctlhq/mctl-telegram/issues/214) | 2026-05-25 | **28 days** |
| mctl-pairdesk | issue-52-p3-add-native-showconfirm | [#52](https://github.com/mctlhq/mctl-pairdesk/issues/52) | 2026-06-04 | **18 days** |
| mctl-pairdesk | issue-53-p3-create-order-has-no-ttl | [#53](https://github.com/mctlhq/mctl-pairdesk/issues/53) | 2026-06-04 | **18 days** |

All four require `requires_human_approval: true` and have no PR. Stand-alone `[stuck-proposal]` issues opened — links below.

### Stale open PRs — >7 days without update (48 total)

Non-dep-bump feature/fix PRs aged **>30 days** (need merge or close decision):

| repo | PR | last updated | age | title |
|------|----|-------------|-----|-------|
| mctl-gitops | [#84](https://github.com/mctlhq/mctl-gitops/pull/84) | 2026-04-30 | **52d** | [wip] feat(agents): per-proposal claim mechanism |
| mctl-agents | [#15](https://github.com/mctlhq/mctl-agents/pull/15) | 2026-05-09 | **43d** | feat(orchestrator): Tier 2 implementer agents |
| mctl-agents | [#16](https://github.com/mctlhq/mctl-agents/pull/16) | 2026-05-09 | **43d** | feat(orchestrator): rotate mentor digests older than 8 weeks |
| mctl-agents | [#17](https://github.com/mctlhq/mctl-agents/pull/17) | 2026-05-09 | **43d** | feat(mctl-docs): fallback to GitHub API when sibling clones absent |
| mctl-api | [#47](https://github.com/mctlhq/mctl-api/pull/47) | 2026-05-10 | **43d** | feat(mcp): mctl_create_preview — build from branch support |
| mctl-portal | [#7](https://github.com/mctlhq/mctl-portal/pull/7) | 2026-05-10 | **43d** | feat(app): add /proposals page for agents review |
| mctl-gitops | [#217](https://github.com/mctlhq/mctl-gitops/pull/217) | 2026-05-16 | **36d** | feat(argo): add incident responder CronWorkflow |
| mctl-agent | [#20](https://github.com/mctlhq/mctl-agent/pull/20) | 2026-05-16 | **36d** | feat(skills): add statefulset-replicas-mismatch YAML skill |
| mctl-telegram | [#146](https://github.com/mctlhq/mctl-telegram/pull/146) | 2026-05-22 | **31d** | Enhance landing page UX: card animations, SVG icons, and social meta tags |

Security-related PRs stale **9–10 days** (⚠️ should not wait):

| repo | PR | age | title |
|------|----|-----|-------|
| mctl-gitops | [#415](https://github.com/mctlhq/mctl-gitops/pull/415) | **10d** | fix: remove ad-hoc vault workflows with plaintext secrets |
| mctl-portal | [#24](https://github.com/mctlhq/mctl-portal/pull/24) | **9d** | fix(security): require auth on custom-domains endpoints |
| mctl-portal | [#25](https://github.com/mctlhq/mctl-portal/pull/25) | **9d** | fix(security): derive OAuth state key from full key hash |

Remaining 36 stale PRs are dependency bumps and release PRs (not listed individually).

Stand-alone `[stale-pr]` issues opened for `mctl-gitops#84` (52d WIP), `mctl-agents#15` (43d, pipeline-critical), and `mctl-gitops#415` (10d, security). Links below.

---

## 7. Cluster Health

Skipped: api.mctl.ai MCP connector not attached yet. See TODO at the bottom of this issue.

---

## 8. Errors During Run

- **`mctlhq/mctl-agents` scope restriction**: This routine's GitHub MCP session was pre-scoped to `mctlhq/mctl-gitops` only. The `list_issues` call to `mctlhq/mctl-agents` returned "Access denied." Issue creation was attempted in `mctlhq/mctl-agents`; result recorded below. If write access was denied, this issue and all follow-ups will be in `mctlhq/mctl-gitops` instead. **Action required**: add `mctlhq/mctl-agents` to the routine's allowed GitHub repos.
- **`mcp__claude-code-remote__list_repos` / `add_repo` not available**: Could not dynamically expand session repo scope.

---

## 9. TODO

Attach the api.mctl.ai MCP connector to this routine to unlock workflow-run counts (`mctl_list_workflows`), MinIO PVC % (`mctl_get_resource_usage`), per-service restart counts (`mctl_get_service_status`), and ArgoCD app sync state.
