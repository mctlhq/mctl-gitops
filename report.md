> **⚠️ Routing note:** `mctlhq/mctl-agents` is not accessible in this session (GitHub MCP token scoped to `mctlhq/mctl-gitops` only). This report is posted to `mctlhq/mctl-gitops` as a fallback. Previous report: [#338](https://github.com/mctlhq/mctl-gitops/issues/338) (2026-05-30).

---

## 1. Summary

- **46 proposals** across 11 repos: **41 merged**, **5 rejected**, **2 proposed** — no pipeline movement since yesterday.
- **No bot commits** from `mctl-agents` in the last 26 hours (bot was active 2026-05-30, silent today).
- **15 PRs merged** org-wide in the last 24h, driven by `mctl-loyalty` (11 PRs) and `mctl-pairdesk` (3 PRs); two gitops housekeeping fixes.
- **2 proposals** (`issue-213`, `issue-214` in mctl-telegram) crossed the **7-day `proposed` threshold today** — stuck-proposal issues opened.
- **8 open stale-pr tracking issues** from yesterday (#358–365) all still open; follow-up comments added with updated staleness counts. One new entrant approaches threshold tomorrow (mctl-gitops#306 at 6.7d).

---

## 2. Proposal pipeline state

| repo | slug | status | pr | Δ vs #338 |
|------|------|--------|----|-----------|
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
| mctl-openclaw | issue-25-ci-add-claude-review-yml-automated-pr-re | `merged` | [#26](https://github.com/mctlhq/mctl-openclaw/pull/26) | — |
| mctl-openclaw | upgrade-to-2026-4-27 | `rejected` | [#15](https://github.com/mctlhq/mctl-openclaw/pull/15) | — |
| mctl-portal | scaffolder-path-traversal | `rejected` | [#10](https://github.com/mctlhq/mctl-portal/pull/10) | — |
| mctl-portal | scaffolder-secret-leak | `rejected` | [#12](https://github.com/mctlhq/mctl-portal/pull/12) | — |
| mctl-telegram | issue-154-nav-replace-github-text-link-with-a-gith | `merged` | [#157](https://github.com/mctlhq/mctl-telegram/pull/157) | — |
| mctl-telegram | issue-158-non-deterministic-safety-block-on-get-me | `merged` | [#162](https://github.com/mctlhq/mctl-telegram/pull/162) | — |
| mctl-telegram | issue-159-live-send-unusable-when-prepare-send-mes | `merged` | [#163](https://github.com/mctlhq/mctl-telegram/pull/163) | — |
| mctl-telegram | issue-202-mctl-telegram-canary-cronjob-stuck-on-im | `merged` | [#211](https://github.com/mctlhq/mctl-telegram/pull/211) | — |
| mctl-telegram | **issue-213-deploy-canary-prometheusrule-to-cluster** | **`proposed` ⚠️** | — | **7d threshold hit** |
| mctl-telegram | **issue-214-self-service-canonicalize-client-tier-in** | **`proposed` ⚠️** | — | **7d threshold hit** |
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

- **Newly merged**: none
- **Newly rejected**: none
- **Newly proposed**: none
- **Still in-progress**: 0
- **Still proposed — threshold crossed today**:
  - `mctl-telegram / issue-213-deploy-canary-prometheusrule-to-cluster` — proposed 2026-05-25T06:45Z, now **7d 2h** with no PR
  - `mctl-telegram / issue-214-self-service-canonicalize-client-tier-in` — proposed 2026-05-25T08:08Z, now **7d 1h** with no PR
  - Both have `control.requires_human_approval: true` — no implementer can start without an approval gate being lifted.

---

## 4. Recent merged PRs (24h — since 2026-05-31T09:00 UTC)

15 PRs merged across 4 repos:

| repo | # | title | merged\_at |
|------|---|-------|-----------|
| mctl-gitops | [#367](https://github.com/mctlhq/mctl-gitops/pull/367) | fix(pairdesk): inject SERVICE\_VERSION env var | 2026-06-01T06:09Z |
| mctl-gitops | [#366](https://github.com/mctlhq/mctl-gitops/pull/366) | fix(labs/mctl-pairdesk): wire bot-secret envFrom | 2026-05-31T22:09Z |
| mctl-loyalty | [#19](https://github.com/mctlhq/mctl-loyalty/pull/19) | feat(landing): real device screenshots in place of CSS mockups | 2026-06-01T07:19Z |
| mctl-loyalty | [#18](https://github.com/mctlhq/mctl-loyalty/pull/18) | feat(landing): refresh admin mockups + copy for tabbed role-based admin | 2026-06-01T06:51Z |
| mctl-loyalty | [#17](https://github.com/mctlhq/mctl-loyalty/pull/17) | feat(web): redesign admin Mini App to Direction C, role-based tabs | 2026-06-01T06:18Z |
| mctl-loyalty | [#16](https://github.com/mctlhq/mctl-loyalty/pull/16) | feat(api): per-merchant accrual rule management | 2026-05-31T21:10Z |
| mctl-loyalty | [#15](https://github.com/mctlhq/mctl-loyalty/pull/15) | docs: refresh CLAUDE.md to 0.8.0 | 2026-05-31T18:34Z |
| mctl-loyalty | [#14](https://github.com/mctlhq/mctl-loyalty/pull/14) | fix(server): 301 redirect /help to /docs | 2026-05-31T18:36Z |
| mctl-loyalty | [#13](https://github.com/mctlhq/mctl-loyalty/pull/13) | feat(landing): redesign to Direction C (Minimal Editorial) | 2026-05-31T08:37Z |
| mctl-loyalty | [#12](https://github.com/mctlhq/mctl-loyalty/pull/12) | feat(app): Telegram hand-off for /app+/admin; collapse /help into /docs | 2026-05-31T08:08Z |
| mctl-loyalty | [#11](https://github.com/mctlhq/mctl-loyalty/pull/11) | feat(landing): real app screenshot in a device frame | 2026-05-31T07:44Z |
| mctl-design | [#13](https://github.com/mctlhq/mctl-design/pull/13) | feat: MCTL Mini App Kit — Telegram section in ui.mctl.ai | 2026-06-01T07:18Z |
| mctl-pairdesk | [#3](https://github.com/mctlhq/mctl-pairdesk/pull/3) | feat: Stage 4-5 — subscription matching, pagination, rate limit, bot hardening | 2026-06-01T05:53Z |
| mctl-pairdesk | [#2](https://github.com/mctlhq/mctl-pairdesk/pull/2) | feat: Stage 2 Telegram bot | 2026-05-31T21:42Z |
| mctl-pairdesk | [#1](https://github.com/mctlhq/mctl-pairdesk/pull/1) | feat: Stage 3 React + Vite Mini App | 2026-05-31T21:12Z |

Notable: `mctl-pairdesk` appears as a new repo (3 PRs in 24h). `mctl-loyalty` is in heavy iteration (11 PRs in 24h).

---

## 5. Bot commits (26h — `--author="mctl-agents"`)

_No commits authored by `mctl-agents` in the last 26 hours._

The bot was active on 2026-05-30 (2 commits for mctl-openclaw/issue-25). Today: silent. The shepherd cron filters on `implemented`/`review-fixing` status only — with 0 proposals in those states there is nothing to process.

---

## 6. Detected problems

### New: stuck proposals at 7-day threshold

| slug | repo | proposed\_at | days | issue |
|------|------|-------------|------|-------|
| issue-213-deploy-canary-prometheusrule-to-cluster | mctl-telegram | 2026-05-25T06:45Z | **7d** | _see §6.3_ |
| issue-214-self-service-canonicalize-client-tier-in | mctl-telegram | 2026-05-25T08:08Z | **7d** | _see §6.3_ |

Both proposals require `control.requires_human_approval: true`. The 7-day clock started on 2026-05-25 when they were filed by the agent. No approval has been registered in their `.status.yaml` files.

### Continuing: open stale-pr tracking issues (all from 2026-05-31)

Follow-up comments posted to each existing issue. None of the stale PRs have been updated since yesterday.

| existing issue | PR | days stale today |
|----------------|-----|-----------------|
| [#358](https://github.com/mctlhq/mctl-gitops/issues/358) | [mctl-gitops#84](https://github.com/mctlhq/mctl-gitops/pull/84) \[wip\] per-proposal claim | **33d** |
| [#359](https://github.com/mctlhq/mctl-gitops/issues/359) | [mctl-agents#15/#16/#17](https://github.com/mctlhq/mctl-agents) orchestrator PRs | **23d** |
| [#360](https://github.com/mctlhq/mctl-gitops/issues/360) | [mctl-api#47](https://github.com/mctlhq/mctl-api/pull/47) mctl\_create\_preview | **22d** |
| [#361](https://github.com/mctlhq/mctl-gitops/issues/361) | [mctl-portal#7](https://github.com/mctlhq/mctl-portal/pull/7) /proposals page | **22d** |
| [#362](https://github.com/mctlhq/mctl-gitops/issues/362) | [mctl-api#51](https://github.com/mctlhq/mctl-api/pull/51) go-oidc/v3 dep bump | **21d** |
| [#363](https://github.com/mctlhq/mctl-gitops/issues/363) | [mctl-agent#20](https://github.com/mctlhq/mctl-agent/pull/20) + [mctl-gitops#217](https://github.com/mctlhq/mctl-gitops/pull/217) | **16d** |
| [#364](https://github.com/mctlhq/mctl-gitops/issues/364) | [mctl-api#55–58](https://github.com/mctlhq/mctl-api) k8s.io + mcp-go dep bumps | **14d** |
| [#365](https://github.com/mctlhq/mctl-gitops/issues/365) | [mctl-telegram#146](https://github.com/mctlhq/mctl-telegram/pull/146) landing page UX | **10d** |

### Watch list — approaching 7-day threshold

| PR | last activity | days stale | threshold |
|----|-------------|-----------|-----------|
| [mctl-gitops#306](https://github.com/mctlhq/mctl-gitops/pull/306) | 2026-05-25T17:38Z | **6.7d** | **2026-06-02** |
| [mctl-telegram#221](https://github.com/mctlhq/mctl-telegram/pull/221) | 2026-05-26T14:44Z | **5.8d** | 2026-06-02 |
| [mctl-telegram#170](https://github.com/mctlhq/mctl-telegram/pull/170) | 2026-05-27T20:40Z | **4.5d** | 2026-06-03 |
| [mctl-telegram#167](https://github.com/mctlhq/mctl-telegram/pull/167) | 2026-05-27T20:40Z | **4.5d** | 2026-06-03 |

### §6.3 Stand-alone issues opened today

| issue | type | subject |
|-------|------|---------|
| _TBD (see below)_ | stuck-proposal | mctl-telegram / issue-213 |
| _TBD (see below)_ | stuck-proposal | mctl-telegram / issue-214 |

---

## 7. Cluster health

Skipped: api.mctl.ai MCP connector not attached yet. See TODO at the bottom of this issue.

---

## 8. Errors during run

| step | error | impact |
|------|-------|--------|
| Report destination | GitHub MCP restricted to `mctlhq/mctl-gitops`; write to `mctlhq/mctl-agents` denied | Report + follow-up issues posted to `mctlhq/mctl-gitops` (established fallback) |
| `gh` CLI | Not installed in this environment | All GitHub ops via MCP tools |
| `mcp__claude-code-remote__list_repos` / `add_repo` | Tools not available in this session to expand repo scope | Cannot unlock `mctlhq/mctl-agents` write access |
| Telegram | `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` not set | Silently skipped |

---

## 9. TODO

- Attach the api.mctl.ai MCP connector to this routine to unlock workflow-run counts (`mctl_list_workflows`), MinIO PVC % (`mctl_get_resource_usage`), per-service restart counts (`mctl_get_service_status`), and ArgoCD app sync state.
- Fix write scope: add `mctlhq/mctl-agents` to the GitHub MCP session's allowed-repositories list so daily-report, stuck-proposal, and stale-pr issues land in the correct repo.
- **Action required:** approve or reject `mctl-telegram/issue-213` and `mctl-telegram/issue-214` — both proposals have been `proposed` for 7 days with `requires_human_approval: true`.
- **2026-06-02:** open `[stale-pr]` for mctl-gitops#306 and mctl-telegram#221 if no activity.
- Investigate bot silence today (2026-06-01): shepherd cron healthy but no eligible proposals to process.
