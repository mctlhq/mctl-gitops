## Summary (2026-06-10 09:00 UTC)

**60 proposals** across 11 repos (51 merged · 4 proposed · 5 rejected · 0 in-progress) — no state changes since #410 (2026-06-08). June 9 daily-report skipped. 0 PRs merged in 24 h. No bot commits (mctl-agents). 5 rapid-fire pelican-proxy deploys (0.12.0→0.16.0) in labs. mctl-telegram stuck proposals (#390/#391) now **16 days** old; follow-up comments added. mctl-pairdesk #52/#53 at 6 days (cross 7-day threshold tomorrow). All 10 stale-PR issues (#392/#393/#400–#407) updated with +2 d comments. No new standalone issues. api.mctl.ai MCP connector now attached. Daily-report issue: mctl-gitops#411.

---

## Proposal pipeline state

_Previous snapshot: 2026-06-08 / issue #410 (60 proposals — identical today, no changes. June 9 skipped)._

| repo | slug | status | pr | changed_since_yesterday |
|------|------|--------|----|------------------------|
| mctl-agent | incident-auto-cleanup-phase1 | merged | [#11](https://github.com/mctlhq/mctl-agent/pull/11) | — |
| mctl-agent | incident-auto-cleanup-phase2 | merged | [#13](https://github.com/mctlhq/mctl-agent/pull/13) | — |
| mctl-agent | incident-auto-cleanup-phase3 | merged | [#12](https://github.com/mctlhq/mctl-agent/pull/12) | — |
| mctl-agent | incident-auto-cleanup-phase4-metrics | rejected | — | — |
| mctl-agent | incident-auto-cleanup-phase4a-metrics-wiring | merged | [#16](https://github.com/mctlhq/mctl-agent/pull/16) | — |
| mctl-agent | incident-auto-cleanup-phase4b-metrics-full | merged | [#17](https://github.com/mctlhq/mctl-agent/pull/17) | — |
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
| mctl-openclaw | upgrade-to-2026-4-27 | rejected | [#15](https://github.com/mctlhq/mctl-openclaw/pull/15) | — |
| mctl-pairdesk | issue-5-feat-add-landing-page-astro-like-mctl-lo | merged | [#32](https://github.com/mctlhq/mctl-pairdesk/pull/32) | — |
| mctl-pairdesk | issue-22-feat-web-create-order-step-1-currency-pa | merged | [#27](https://github.com/mctlhq/mctl-pairdesk/pull/27) | — |
| mctl-pairdesk | issue-23-feat-web-create-order-step-2-coupled-dua | merged | [#30](https://github.com/mctlhq/mctl-pairdesk/pull/30) | — |
| mctl-pairdesk | issue-24-feat-redesign-create-order-into-a-t-bank | merged | [#31](https://github.com/mctlhq/mctl-pairdesk/pull/31) | — |
| mctl-pairdesk | issue-28-fix-web-create-order-step-1-collision-au | merged | [#29](https://github.com/mctlhq/mctl-pairdesk/pull/29) | — |
| mctl-pairdesk | issue-33-fix-web-hide-app-tab-bar-during-create-o | merged | [#41](https://github.com/mctlhq/mctl-pairdesk/pull/41) | — |
| mctl-pairdesk | issue-34-fix-web-rework-create-order-step-navigat | merged | [#42](https://github.com/mctlhq/mctl-pairdesk/pull/42) | — |
| mctl-pairdesk | issue-35-fix-web-city-notes-section-layout-overfl | merged | [#39](https://github.com/mctlhq/mctl-pairdesk/pull/39) | — |
| mctl-pairdesk | issue-36-fix-web-entered-city-missing-from-live-p | merged | [#40](https://github.com/mctlhq/mctl-pairdesk/pull/40) | — |
| mctl-pairdesk | issue-37-feat-web-one-currency-pair-per-order-rem | merged | [#43](https://github.com/mctlhq/mctl-pairdesk/pull/43) | — |
| mctl-pairdesk | issue-38-fix-web-rate-slider-must-anchor-the-last | merged | [#44](https://github.com/mctlhq/mctl-pairdesk/pull/44) | — |
| mctl-pairdesk | issue-45-add-web-test-harness-rateslider-anchorin | merged | [#46](https://github.com/mctlhq/mctl-pairdesk/pull/46) | — |
| mctl-pairdesk | **issue-52-p3-add-native-showconfirm-for-destructiv** | **proposed** | — | still (6 d ⚠ crosses 7 d tomorrow) |
| mctl-pairdesk | **issue-53-p3-create-order-has-no-ttl-expiry-picker** | **proposed** | — | still (6 d ⚠ crosses 7 d tomorrow) |
| mctl-portal | scaffolder-path-traversal | rejected | [#10](https://github.com/mctlhq/mctl-portal/pull/10) | — |
| mctl-portal | scaffolder-secret-leak | rejected | [#12](https://github.com/mctlhq/mctl-portal/pull/12) | — |
| mctl-telegram | issue-59-add-observability-and-alerting-for-mctl | merged | [#61](https://github.com/mctlhq/mctl-telegram/pull/61) | — |
| mctl-telegram | issue-66-scalability-audit-and-hardening-for-100 | merged | [#72](https://github.com/mctlhq/mctl-telegram/pull/72) | — |
| mctl-telegram | issue-67-build-browser-based-telegram-account-onb | merged | [#73](https://github.com/mctlhq/mctl-telegram/pull/73) | — |
| mctl-telegram | issue-68-redesign-tg-mctl-ai-landing-page-for-cli | merged | [#74](https://github.com/mctlhq/mctl-telegram/pull/74) | — |
| mctl-telegram | issue-69-improve-mobile-responsiveness-of-tg-mctl | merged | [#75](https://github.com/mctlhq/mctl-telegram/pull/75) | — |
| mctl-telegram | issue-70-add-user-friendly-error-message-catalog | merged | [#76](https://github.com/mctlhq/mctl-telegram/pull/76) | — |
| mctl-telegram | issue-71-test-smoke-test-log-build-version-git-sh | rejected | — | — |
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
| mctl-telegram | **issue-213-deploy-canary-prometheusrule-to-cluster** | **proposed** | — | still (16 d ⚠⚠) |
| mctl-telegram | **issue-214-self-service-canonicalize-client-tier-in** | **proposed** | — | still (16 d ⚠⚠) |
| mctl-web | wrangler-upgrade-security | merged | [#9](https://github.com/mctlhq/mctl-web/pull/9) | — |

**Totals:** 60 proposals — 51 merged · 4 proposed · 5 rejected · 0 in-progress
_(Previous 2026-06-08 / #410: identical — no state changes. June 9 skipped.)_

---

## Pipeline diff (vs 2026-06-08 / #410)

> Note: June 9 report was skipped — no daily-report issue found for 2026-06-09.

- **Newly merged:** none
- **Newly rejected:** none
- **Newly proposed:** none
- **Still in-progress:** none
- **Still proposed (unchanged):**
  - `mctl-telegram/issue-213` — **16 days** ⚠⚠ (follow-up comment → [#390](https://github.com/mctlhq/mctl-gitops/issues/390))
  - `mctl-telegram/issue-214` — **16 days** ⚠⚠ (follow-up comment → [#391](https://github.com/mctlhq/mctl-gitops/issues/391))
  - `mctl-pairdesk/issue-52` — **6 days** (crosses 7-day threshold tomorrow — standalone issue will open next run)
  - `mctl-pairdesk/issue-53` — **6 days** (same)

---

## Recent merged PRs (24 h)

Window: 2026-06-09T09:00Z → 2026-06-10T09:00Z

_No PRs merged in the last 24 h across `mctlhq/*`._

---

## Bot commits (last 26 h)

No results — no automated commits from the agent pipeline (`mctl-agents`).

Other commits in `mctl-gitops` last 26 h: 5 deploy commits for `labs/pelican-proxy` (0.12.0→0.16.0, 2026-06-09 12:37–19:15 UTC).

---

## Detected problems

### Stuck proposals (follow-up comments on existing issues)

| proposal | days | existing issue | action |
|----------|------|---------------|--------|
| mctl-telegram/issue-213 | **16 d** | [#390](https://github.com/mctlhq/mctl-gitops/issues/390) | comment added ✓ |
| mctl-telegram/issue-214 | **16 d** | [#391](https://github.com/mctlhq/mctl-gitops/issues/391) | comment added ✓ |

Watching (will open standalone issues next run if still proposed):
- mctl-pairdesk/52 (6 d, threshold 7 d tomorrow)
- mctl-pairdesk/53 (6 d, threshold 7 d tomorrow)

### Stale PRs (all tracked, no new issues)

| follow-up issue | tracked PR | days stale |
|-----------------|-----------|------------|
| [#392](https://github.com/mctlhq/mctl-gitops/issues/392) | [mctl-gitops#84](https://github.com/mctlhq/mctl-gitops/pull/84) [wip] per-proposal claim | **41 d** |
| [#393](https://github.com/mctlhq/mctl-gitops/issues/393) | [mctl-agents#15](https://github.com/mctlhq/mctl-agents/pull/15) / [#16](https://github.com/mctlhq/mctl-agents/pull/16) / [#17](https://github.com/mctlhq/mctl-agents/pull/17) | **32 d** |
| [#400](https://github.com/mctlhq/mctl-gitops/issues/400) | [mctl-portal#7](https://github.com/mctlhq/mctl-portal/pull/7) | **31 d** |
| [#401](https://github.com/mctlhq/mctl-gitops/issues/401) | [mctl-api#47](https://github.com/mctlhq/mctl-api/pull/47) | **31 d** |
| [#402](https://github.com/mctlhq/mctl-gitops/issues/402) | [mctl-gitops#217](https://github.com/mctlhq/mctl-gitops/pull/217) | **25 d** |
| [#403](https://github.com/mctlhq/mctl-gitops/issues/403) | [mctl-agent#20](https://github.com/mctlhq/mctl-agent/pull/20) | **25 d** |
| [#404](https://github.com/mctlhq/mctl-gitops/issues/404) | [mctl-telegram#146](https://github.com/mctlhq/mctl-telegram/pull/146) | **19 d** |
| [#405](https://github.com/mctlhq/mctl-gitops/issues/405) | [mctl-gitops#306](https://github.com/mctlhq/mctl-gitops/pull/306) | **16 d** |
| [#406](https://github.com/mctlhq/mctl-gitops/issues/406) | [mctl-telegram#221](https://github.com/mctlhq/mctl-telegram/pull/221) | **15 d** |
| [#407](https://github.com/mctlhq/mctl-gitops/issues/407) | [mctl-telegram#248](https://github.com/mctlhq/mctl-telegram/pull/248) | **11 d** |

Watching for next run (not yet stable enough for issue):
- mctl-pairdesk#57 (5 d), mctl-portal#23 (5 d) — cross 7 d on June 12
- mctl-api#70 / #71 CI dep-bumps (9 d — skipped per dep-bump convention)
- mctl-telegram#263 (4 d) — release-please PR
- mctl-api#72 (2 d)

---

## Cluster health

**api.mctl.ai MCP connector is now attached** — cluster health sections enabled from next run.

---

## TODO

1. Enable cluster health sections in next run: `mctl_list_workflows`, `mctl_get_resource_usage`, `mctl_get_service_status`, ArgoCD sync state.
2. Add `mctlhq/mctl-agents` to GitHub MCP write scope (currently using mctl-gitops as fallback).
