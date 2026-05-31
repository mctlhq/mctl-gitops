> **⚠️ Routing note:** `mctlhq/mctl-agents` is not accessible in this session (GitHub MCP token scoped to `mctlhq/mctl-gitops` only). This report is posted to `mctlhq/mctl-gitops` as a fallback. Previous report: [#338](https://github.com/mctlhq/mctl-gitops/issues/338) (2026-05-30).

---

## 1. Summary

- **46 proposals** across 9 repos (+1 vs #338): **39 merged**, **5 rejected**, **2 proposed** — **mctl-openclaw/issue-25 newly merged** (first pipeline movement in 7 days).
- **50 PRs merged** in 24 h — record day: mctl-loyalty MVP launched (new repo, 11 PRs), fleet-wide claude-review model rollback `opus-4-8 → sonnet-4-6` (10 repos simultaneously), mctl-telegram 0.41.1 release + 3 production fixes.
- **Bot silence BROKEN: 2 commits today** after 5 consecutive idle days — bot investigated and implemented [mctl-openclaw/issues/25](https://github.com/mctlhq/mctl-openclaw/issues/25).
- **2 proposals** still `proposed` (issue-213, issue-214 in mctl-telegram) — now **6 days old; threshold is tomorrow (2026-06-01)**. Approve or expect stuck-proposal issues tomorrow.
- 14 stale PRs (>7 days no activity) — all prior tracking issues were closed; fresh stale-pr issues opened below.

---

## 2. Proposal pipeline state

| repo | slug | status | pr | Δ #338 |
|------|------|--------|----|--------|
| mctl-agent | incident-auto-cleanup-phase1 | `merged` | [#11](https://github.com/mctlhq/mctl-agent/pull/11) | — |
| mctl-agent | incident-auto-cleanup-phase2 | `merged` | [#13](https://github.com/mctlhq/mctl-agent/pull/13) | — |
| mctl-agent | incident-auto-cleanup-phase3 | `merged` | [#12](https://github.com/mctlhq/mctl-agent/pull/12) | — |
| mctl-agent | incident-auto-cleanup-phase4-metrics | `rejected` | — | — |
| mctl-agent | incident-auto-cleanup-phase4a-metrics-wiring | `merged` | [#16](https://github.com/mctlhq/mctl-agent/pull/16) | — |
| mctl-agent | incident-auto-cleanup-phase4b-metrics-full | `merged` | [#17](https://github.com/mctlhq/mctl-agent/pull/17) | — |
| mctl-agent | sqlite-cve-patch | `merged` | [#9](https://github.com/mctlhq/mctl-agent/pull/9) | — |
| mctl-agents | tier3-pr-shepherd | `merged` | [#12](https://github.com/mctlhq/mctl-agents/pull/12) | — |
| mctl-api | chi-security-patch | `merged` | [#39](https://github.com/mctlhq/mctl-api/pull/39) | — |
| mctl-api | pgx-sqli-cve-2025-54236 | `merged` | [#40](https://github.com/mctlhq/mctl-api/pull/40) | — |
| mctl-design | issue-3-change-the-storybook-overview-brand-icon | `merged` | [#8](https://github.com/mctlhq/mctl-design/pull/8) | — |
| mctl-design | issue-4-rename-storybook-brand-title-to-mctl-ui | `merged` | [#5](https://github.com/mctlhq/mctl-design/pull/5) | — |
| mctl-design | issue-6-align-storybook-page-title-og-title-with | `merged` | [#7](https://github.com/mctlhq/mctl-design/pull/7) | — |
| mctl-docs | fix-broken-mctl-ai-mcp-links | `merged` | [#6](https://github.com/mctlhq/mctl-docs/pull/6) | — |
| mctl-docs | mcp-agents-tools | `merged` | [#7](https://github.com/mctlhq/mctl-docs/pull/7) | — |
| mctl-gitops | argo-workflows-cve-patch-v2 | `merged` | [#85](https://github.com/mctlhq/mctl-gitops/pull/85) | — |
| mctl-gitops | argocd-informer-cache-patch | `merged` | [#90](https://github.com/mctlhq/mctl-gitops/pull/90) | — |
| mctl-gitops | eso-cve-patch | `merged` | [#87](https://github.com/mctlhq/mctl-gitops/pull/87) | — |
| mctl-gitops | grafana-sql-rce-patch | `merged` | [#89](https://github.com/mctlhq/mctl-gitops/pull/89) | — |
| mctl-openclaw | **issue-25-ci-add-claude-review-yml-automated-pr-re** | **`merged`** ✅ | [#26](https://github.com/mctlhq/mctl-openclaw/pull/26) | **new** |
| mctl-openclaw | upgrade-to-2026-4-27 | `rejected` | [#15](https://github.com/mctlhq/mctl-openclaw/pull/15) | — |
| mctl-portal | scaffolder-path-traversal | `rejected` | [#10](https://github.com/mctlhq/mctl-portal/pull/10) | — |
| mctl-portal | scaffolder-secret-leak | `rejected` | [#12](https://github.com/mctlhq/mctl-portal/pull/12) | — |
| mctl-telegram | issue-154-nav-replace-github-text-link-with-a-gith | `merged` | [#157](https://github.com/mctlhq/mctl-telegram/pull/157) | — |
| mctl-telegram | issue-158-non-deterministic-safety-block-on-get-me | `merged` | [#162](https://github.com/mctlhq/mctl-telegram/pull/162) | — |
| mctl-telegram | issue-159-live-send-unusable-when-prepare-send-mes | `merged` | [#163](https://github.com/mctlhq/mctl-telegram/pull/163) | — |
| mctl-telegram | issue-202-mctl-telegram-canary-cronjob-stuck-on-im | `merged` | [#211](https://github.com/mctlhq/mctl-telegram/pull/211) | — |
| mctl-telegram | **issue-213-deploy-canary-prometheusrule-to-cluster** | **`proposed`** ⚠️ | — | still (6 d) |
| mctl-telegram | **issue-214-self-service-canonicalize-client-tier-in** | **`proposed`** ⚠️ | — | still (6 d) |
| mctl-telegram | issue-59-add-observability-and-alerting-for-mctl | `merged` | [#61](https://github.com/mctlhq/mctl-telegram/pull/61) | — |
| mctl-telegram | issue-66-scalability-audit-and-hardening-for-100 | `merged` | [#72](https://github.com/mctlhq/mctl-telegram/pull/72) | — |
| mctl-telegram | issue-67-build-browser-based-telegram-account-onb | `merged` | [#73](https://github.com/mctlhq/mctl-telegram/pull/73) | — |
| mctl-telegram | issue-68-redesign-tg-mctl-ai-landing-page-for-cli | `merged` | [#74](https://github.com/mctlhq/mctl-telegram/pull/74) | — |
| mctl-telegram | issue-69-improve-mobile-responsiveness-of-tg-mctl | `merged` | [#75](https://github.com/mctlhq/mctl-telegram/pull/75) | — |
| mctl-telegram | issue-70-add-user-friendly-error-message-catalog | `merged` | [#76](https://github.com/mctlhq/mctl-telegram/pull/76) | — |
| mctl-telegram | issue-71-test-smoke-test-log-build-version-git-sh | `rejected` | — | — |
| mctl-telegram | issue-86-ship-prometheusrule-manifests-for-produc | `merged` | [#112](https://github.com/mctlhq/mctl-telegram/pull/112) | — |
| mctl-telegram | issue-87-grafana-dashboard-for-beta-operations | `merged` | [#95](https://github.com/mctlhq/mctl-telegram/pull/95) | — |
| mctl-telegram | issue-88-define-beta-slos-and-burn-rate-alerts | `merged` | [#113](https://github.com/mctlhq/mctl-telegram/pull/113) | — |
| mctl-telegram | issue-89-synthetic-end-to-end-canary-oauth-list-d | `merged` | [#96](https://github.com/mctlhq/mctl-telegram/pull/96) | — |
| mctl-telegram | issue-90-beta-capacity-profile-load-test-tuned-co | `merged` | [#114](https://github.com/mctlhq/mctl-telegram/pull/114) | — |
| mctl-telegram | issue-91-sticky-routing-by-user-id-for-multi-repl | `merged` | [#132](https://github.com/mctlhq/mctl-telegram/pull/132) | — |
| mctl-telegram | issue-92-operational-runbook-for-beta-top-n-incid | `merged` | [#115](https://github.com/mctlhq/mctl-telegram/pull/115) | — |
| mctl-telegram | issue-93-unified-connect-wizard-oidc-enable-acces | `merged` | [#99](https://github.com/mctlhq/mctl-telegram/pull/99) | — |
| mctl-telegram | issue-94-local-bridge-m4-finish-community-release | `merged` | [#125](https://github.com/mctlhq/mctl-telegram/pull/125) | — |
| mctl-web | wrangler-upgrade-security | `merged` | [#9](https://github.com/mctlhq/mctl-web/pull/9) | — |

---

## 3. Pipeline diff (vs [#338](https://github.com/mctlhq/mctl-gitops/issues/338) — 2026-05-30)

- **Newly merged**: `mctl-openclaw / issue-25-ci-add-claude-review-yml` → [mctl-openclaw#26](https://github.com/mctlhq/mctl-openclaw/pull/26) (merged 2026-05-30T13:53Z, bot-implemented)
- **Newly rejected**: none
- **Newly proposed**: none
- **Still in-progress**: none
- **Still proposed (6 days — threshold 2026-06-01)**:
  - `mctl-telegram / issue-213-deploy-canary-prometheusrule-to-cluster` — proposed 2026-05-25T06:45Z
  - `mctl-telegram / issue-214-self-service-canonicalize-client-tier-in` — proposed 2026-05-25T08:08Z

---

## 4. Recent merged PRs (24 h — since 2026-05-30T09:00Z)

50 PRs merged. Notable groups:

**mctl-loyalty MVP (new repo)** — 11 PRs, complete greenfield launch:
- [#1](https://github.com/mctlhq/mctl-loyalty/pull/1) feat: Telegram loyalty MVP
- [#2](https://github.com/mctlhq/mctl-loyalty/pull/2) fix: enable SSL for CNPG Postgres connection
- [#3](https://github.com/mctlhq/mctl-loyalty/pull/3)–[#13](https://github.com/mctlhq/mctl-loyalty/pull/13) feat: merchant deep-link, QR redemption, staff onboarding, Astro landing, redesign iterating to Direction C

**mctl-telegram 0.41.0/0.41.1 production** — 10 PRs:
- [#249](https://github.com/mctlhq/mctl-telegram/pull/249) fix(telegram): seed peer cache from dialogs (PEER_ID fix)
- [#250](https://github.com/mctlhq/mctl-telegram/pull/250) fix(metrics): WriteHeader only once
- [#254](https://github.com/mctlhq/mctl-telegram/pull/254) fix(telegram): skip min peers when seeding
- [#256](https://github.com/mctlhq/mctl-telegram/pull/256) chore(main): release 0.41.1
- [#257](https://github.com/mctlhq/mctl-telegram/pull/257)–[#259](https://github.com/mctlhq/mctl-telegram/pull/259) docs(submission): reviewer flow for App Store review

**Fleet-wide model rollback** — 10 repos in one sweep:
- `claude-review opus-4-8 → sonnet-4-6` applied to mctl-agent, mctl-api, mctl-gitops, mctl-design, mctl-docs, mctl-web, mctl-portal, mctl-openclaw, mctl-telegram, mctl-claude-remote

**mctl-gitops** — 6 PRs:
- [#349](https://github.com/mctlhq/mctl-gitops/pull/349) chore(agents): bump CWFT image 1.14.0→1.14.1
- [#351](https://github.com/mctlhq/mctl-gitops/pull/351) feat(mctl-telegram): ALLOWED_ORIGINS for OriginGuard
- [#352](https://github.com/mctlhq/mctl-gitops/pull/352) fix(labs/mctl-loyalty): inject bot-token secret into env
- [#353](https://github.com/mctlhq/mctl-gitops/pull/353) feat(mctl-telegram): grant reviewer admin for App review
- [#355](https://github.com/mctlhq/mctl-gitops/pull/355) feat(loyalty): add rewards.mctl.ai brand domain
- [#356](https://github.com/mctlhq/mctl-gitops/pull/356) revert(mctl-telegram): reviewer back to non-admin

---

## 5. Bot commits (26 h — author = mctl-agents)

**Bot is active after 5-day silence.**

| hash | timestamp | message |
|------|-----------|---------|
| a99aa5f | 2026-05-30 12:57 UTC | chore(agents): implement run 2026-05-30 |
| 46fe3c9 | 2026-05-30 12:44 UTC | chore(agents): investigate https://github.com/mctlhq/mctl-openclaw/issues/25 2026-05-30 |

_(Both commits tied to mctl-openclaw/issue-25 → mctl-openclaw#26. Bot resumed normal operation.)_

---

## 6. Detected problems

### New stale-pr issues opened today

All prior tracking issues for the 14 stale PRs were closed; fresh issues reopened:

| issue | repo / PR | days stale | note |
|-------|-----------|-----------|------|
| see below | mctl-gitops#84 | **32 d** | [wip] per-proposal claim mechanism |
| see below | mctl-agents#15 | **22 d** | Tier 2 implementer agents |
| see below | mctl-agents#16 | **22 d** | rotate mentor digests |
| see below | mctl-agents#17 | **22 d** | fallback to GitHub API |
| see below | mctl-api#47 | **21 d** | mctl_create_preview branch support |
| see below | mctl-portal#7 | **21 d** | /proposals page |
| see below | mctl-api#51 | **20 d** | go-oidc/v3 dep bump |
| see below | mctl-agent#20 | **15 d** | statefulset-replicas-mismatch skill |
| see below | mctl-gitops#217 | **15 d** | incident responder CronWorkflow |
| see below | mctl-api#55–58 | **13 d** | k8s.io + mcp-go dep bumps (4 PRs grouped) |
| see below | mctl-telegram#146 | **9 d** | landing page UX enhancements |

_(Issue links will be filled in once created.)_

### Proposed proposals at threshold — act tomorrow

| slug | proposed_at | days | threshold |
|------|------------|------|-----------|
| mctl-telegram/issue-213-deploy-canary-prometheusrule-to-cluster | 2026-05-25 | **6 d** | **2026-06-01** |
| mctl-telegram/issue-214-self-service-canonicalize-client-tier-in | 2026-05-25 | **6 d** | **2026-06-01** |

Both proposals have `control.requires_human_approval: true`. If neither has a PR by tomorrow's run, `[stuck-proposal]` issues will be opened.

### Bot agent status

Bot resumed after 5 consecutive idle days: 2 commits recorded at 12:44–12:57 UTC on 2026-05-30. Root cause of the 5-day idle period not yet confirmed — worth verifying cron logs.

### Watch list — approaching 7-day threshold

| PR | last activity | days stale | threshold |
|----|-------------|-----------|-----------|
| [mctl-gitops#306](https://github.com/mctlhq/mctl-gitops/pull/306) | 2026-05-25 | 6 d | **2026-06-01** |
| [mctl-telegram#221](https://github.com/mctlhq/mctl-telegram/pull/221) | 2026-05-26 | 5 d | 2026-06-02 |
| [mctl-telegram#170](https://github.com/mctlhq/mctl-telegram/pull/170) | 2026-05-27 | 4 d | 2026-06-03 |
| [mctl-telegram#167](https://github.com/mctlhq/mctl-telegram/pull/167) | 2026-05-27 | 4 d | 2026-06-03 |

---

## 7. Cluster health

Skipped: api.mctl.ai MCP connector not attached to this session run. See TODO.

---

## 8. Errors during run

| step | error | impact |
|------|-------|--------|
| Report destination | GitHub MCP restricted to `mctlhq/mctl-gitops`; write to `mctlhq/mctl-agents` denied | Report posted to `mctlhq/mctl-gitops` (established fallback) |
| `gh` CLI | Not installed in this environment | All GitHub ops via MCP tools |
| Telegram notification | `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` not set | Silently skipped |

---

## 9. TODO

- Attach the api.mctl.ai MCP connector to this routine to unlock workflow-run counts (`mctl_list_workflows`), MinIO PVC % (`mctl_get_resource_usage`), per-service restart counts (`mctl_get_service_status`), and ArgoCD app sync state.
- Fix write scope: add `mctlhq/mctl-agents` to the GitHub MCP session's allowed-repositories list.
- **2026-06-01:** open `[stuck-proposal]` issues for mctl-telegram/issue-213 and issue-214 if still no PR. Also open `[stale-pr]` for mctl-gitops#306 if no activity.
- Investigate 5-day bot idle period (2026-05-25→2026-05-30): verify what stopped and restarted the cron.
- Resolve 2 open proposals (issue-213 + issue-214) — both require human approval in mctl-telegram.
