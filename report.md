## Summary

This is the **first run** of the daily-report routine (no previous snapshot exists). The proposal pipeline across all `mctlhq/*` repos shows **57 total proposals**: 51 merged (89%), 4 stuck in `proposed` (no PR), 5 rejected, 0 currently in-progress. No bot commits or merged PRs were detected in the last 24 h — the pipeline has been quiet since at least 2026-06-15. Four proposals have been in `proposed` state for >7 days without a PR, and 34 open PRs have not been updated in >7 days (13 for >30 days), indicating a significant backlog of unreviewed work.

---

## Proposal Pipeline State

> First run — `changed_since_yesterday` is **new** for all entries.

| repo | slug | status | pr | changed_since_yesterday |
|------|------|--------|----|------------------------|
| mctl-agent | incident-auto-cleanup-phase1 | merged | [#11](https://github.com/mctlhq/mctl-agent/pull/11) | new |
| mctl-agent | incident-auto-cleanup-phase2 | merged | [#13](https://github.com/mctlhq/mctl-agent/pull/13) | new |
| mctl-agent | incident-auto-cleanup-phase3 | merged | [#12](https://github.com/mctlhq/mctl-agent/pull/12) | new |
| mctl-agent | incident-auto-cleanup-phase4-metrics | **rejected** | — | new |
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
| mctl-pairdesk | **issue-52-p3-add-native-showconfirm** | **proposed** | — | new |
| mctl-pairdesk | **issue-53-p3-create-order-has-no-ttl** | **proposed** | — | new |
| mctl-portal | scaffolder-path-traversal | **rejected** | [#10](https://github.com/mctlhq/mctl-portal/pull/10) | new |
| mctl-portal | scaffolder-secret-leak | **rejected** | [#12](https://github.com/mctlhq/mctl-portal/pull/12) | new |
| mctl-telegram | issue-154-nav-replace-github-text-link | merged | [#157](https://github.com/mctlhq/mctl-telegram/pull/157) | new |
| mctl-telegram | issue-158-non-deterministic-safety-block | merged | [#162](https://github.com/mctlhq/mctl-telegram/pull/162) | new |
| mctl-telegram | issue-159-live-send-unusable | merged | [#163](https://github.com/mctlhq/mctl-telegram/pull/163) | new |
| mctl-telegram | issue-202-mctl-telegram-canary-cronjob-stuck | merged | [#211](https://github.com/mctlhq/mctl-telegram/pull/211) | new |
| mctl-telegram | **issue-213-deploy-canary-prometheusrule** | **proposed** | — | new |
| mctl-telegram | **issue-214-self-service-canonicalize-client-tier** | **proposed** | — | new |
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
| mctl-web | wrangler-upgrade-security | merged | [#9](https://github.com/mctlhq/mctl-web/pull/9) | new |

---

## Pipeline Diff (vs yesterday)

**First run — no previous snapshot. All entries are new.**

- **Merged (total):** 51 proposals across mctl-agent (6), mctl-agents (1), mctl-api (2), mctl-design (3), mctl-docs (2), mctl-gitops (4), mctl-openclaw (1), mctl-pairdesk (12), mctl-telegram (19), mctl-web (1)
- **Rejected (total):** 5 — mctl-agent/phase4-metrics (superseded by 4a+4b split), mctl-openclaw/upgrade-to-2026-4-27, mctl-portal/scaffolder-path-traversal, mctl-portal/scaffolder-secret-leak, mctl-telegram/issue-71
- **Currently proposed (no PR):** 4 — see Detected Problems
- **In-progress:** 0

---

## Recent Merged PRs (24 h)

GitHub PR search returned **0 results** for `org:mctlhq merged:>=2026-06-18`. The most recently updated open PR was last touched on 2026-06-15 (`mctl-api#73`), suggesting the pipeline has been idle for ~4 days.

---

## Bot Commits (24 h)

```
(none — git log --author="mctl-agents" --since="26 hours ago" returned empty)
```

---

## Detected Problems

### Stuck proposals — in `proposed` for >7 days (no PR opened)

| repo | slug | source issue | proposed_since | days_stuck |
|------|------|-------------|----------------|-----------|
| mctl-telegram | issue-213-deploy-canary-prometheusrule | [#213](https://github.com/mctlhq/mctl-telegram/issues/213) | 2026-05-25 | **25 days** |
| mctl-telegram | issue-214-self-service-canonicalize-client-tier | [#214](https://github.com/mctlhq/mctl-telegram/issues/214) | 2026-05-25 | **25 days** |
| mctl-pairdesk | issue-52-p3-add-native-showconfirm | [#52](https://github.com/mctlhq/mctl-pairdesk/issues/52) | 2026-06-04 | **15 days** |
| mctl-pairdesk | issue-53-p3-create-order-has-no-ttl | [#53](https://github.com/mctlhq/mctl-pairdesk/issues/53) | 2026-06-04 | **15 days** |

Stand-alone `[stuck-proposal]` issues were opened for each of the above — see links in the **Detected Problems** section below.

### Stale open PRs — >7 days without update: 34 total

PRs older than **30 days** (non-dep-bump, need explicit action or close):

| repo | PR | last updated | title |
|------|----|-------------|-------|
| mctl-gitops | [#84](https://github.com/mctlhq/mctl-gitops/pull/84) | 2026-04-30 | [wip] feat(agents): per-proposal claim mechanism |
| mctl-agents | [#15](https://github.com/mctlhq/mctl-agents/pull/15) | 2026-05-09 | feat(orchestrator): Tier 2 implementer agents |
| mctl-agents | [#16](https://github.com/mctlhq/mctl-agents/pull/16) | 2026-05-09 | feat(orchestrator): rotate mentor digests older than 8 weeks |
| mctl-agents | [#17](https://github.com/mctlhq/mctl-agents/pull/17) | 2026-05-09 | feat(mctl-docs): fallback to GitHub API when sibling clones absent |
| mctl-api | [#47](https://github.com/mctlhq/mctl-api/pull/47) | 2026-05-10 | feat(mcp): mctl_create_preview — build from branch support |
| mctl-portal | [#7](https://github.com/mctlhq/mctl-portal/pull/7) | 2026-05-10 | feat(app): add /proposals page for agents review |
| mctl-gitops | [#217](https://github.com/mctlhq/mctl-gitops/pull/217) | 2026-05-16 | feat(argo): add incident responder CronWorkflow |
| mctl-agent | [#20](https://github.com/mctlhq/mctl-agent/pull/20) | 2026-05-16 | feat(skills): add statefulset-replicas-mismatch YAML skill |

An additional 5 dep-bump PRs in mctl-api and 21 other PRs aged 7–30 days are listed in the open PRs search (not broken out here to keep noise low).

`[stale-pr]` issues were opened for the 8 non-dep-bump feature PRs >30 days above — see links below.

---

## Cluster Health

Skipped: api.mctl.ai MCP connector not attached yet. See TODO at the bottom of this issue.

---

## Errors During Run

- **`mctlhq/mctl-agents` write access**: This routine's GitHub session scope is restricted to `mctlhq/mctl-gitops`. The `list_issues` call to `mctlhq/mctl-agents` returned "Access denied." This daily-report issue and all follow-up issues were posted to `mctlhq/mctl-gitops` as a fallback. **Action required**: add `mctlhq/mctl-agents` to the routine's allowed GitHub repos so future runs post to the intended repo.
- **Merged PR search**: Both `org:mctlhq is:pr is:merged merged:>=2026-06-18` and `merged:>=2026-06-18T00:00:00Z` returned 0 via the GitHub MCP search tool. This appears accurate given no bot commits either.

---

## TODO

Attach the api.mctl.ai MCP connector to this routine to unlock workflow-run counts (`mctl_list_workflows`), MinIO PVC % (`mctl_get_resource_usage`), per-service restart counts (`mctl_get_service_status`), and ArgoCD app sync state.
