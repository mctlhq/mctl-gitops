> **⚠️ Routing note:** `mctlhq/mctl-agents` is not accessible in this session (GitHub MCP token scoped to `mctlhq/mctl-gitops` only). This report is posted to `mctlhq/mctl-gitops` as a fallback. Previous report: [#331](https://github.com/mctlhq/mctl-gitops/issues/331) (2026-05-29).

---

## 1. Summary

- **45 proposals** across 9 repos: **38 merged** (84%), **5 rejected**, **2 proposed** — **no pipeline changes vs [#331](https://github.com/mctlhq/mctl-gitops/issues/331)**.
- **18 PRs merged today**: coordinated `claude-opus-4-8` review-model rollout (10 repos simultaneously), a **mctl.ai production outage fix** (mctl-web#20: port 80/8080 mismatch in v3 nginx caused 503), and the **v3 redesign** (mctl-web#12, stale for 13d — now resolved ✅).
- **0 mctl-agents bot commits — 5th consecutive day** of bot silence (last activity: 2026-05-25T08:08Z). Shepherd + implementer crons appear idle.
- **[stale-pr] mctl-telegram#146** opened today ([#337](https://github.com/mctlhq/mctl-gitops/issues/337)) — crossed 7d threshold as predicted in [#331](https://github.com/mctlhq/mctl-gitops/issues/331). **[stale-pr] mctl-web#12** ([#297](https://github.com/mctlhq/mctl-gitops/issues/297)) **closed** — PR merged.
- 11 dedup comments posted on continuing stale-pr tracking issues.

---

## 2. Proposal pipeline state

| repo | slug | status | pr | Δ #331 |
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
| mctl-openclaw | upgrade-to-2026-4-27 | `rejected` | [#15](https://github.com/mctlhq/mctl-openclaw/pull/15) | — |
| mctl-portal | scaffolder-path-traversal | `rejected` | [#10](https://github.com/mctlhq/mctl-portal/pull/10) | — |
| mctl-portal | scaffolder-secret-leak | `rejected` | [#12](https://github.com/mctlhq/mctl-portal/pull/12) | — |
| mctl-telegram | issue-154-nav-replace-github-text-link-with-a-gith | `merged` | [#157](https://github.com/mctlhq/mctl-telegram/pull/157) | — |
| mctl-telegram | issue-158-non-deterministic-safety-block-on-get-me | `merged` | [#162](https://github.com/mctlhq/mctl-telegram/pull/162) | — |
| mctl-telegram | issue-159-live-send-unusable-when-prepare-send-mes | `merged` | [#163](https://github.com/mctlhq/mctl-telegram/pull/163) | — |
| mctl-telegram | issue-202-mctl-telegram-canary-cronjob-stuck-on-im | `merged` | [#211](https://github.com/mctlhq/mctl-telegram/pull/211) | — |
| mctl-telegram | **issue-213-deploy-canary-prometheusrule-to-cluster** | **`proposed`** | — | — |
| mctl-telegram | **issue-214-self-service-canonicalize-client-tier-in** | **`proposed`** | — | — |
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

## 3. Pipeline diff (vs [#331](https://github.com/mctlhq/mctl-gitops/issues/331) — 2026-05-29)

- **Newly merged**: none (proposal states unchanged)
- **Newly rejected**: none
- **Newly proposed**: none
- **Still in-progress**: none
- **Still proposed (5 days old — threshold 2026-06-01)**:
  - `mctl-telegram / issue-213-deploy-canary-prometheusrule-to-cluster` — proposed 2026-05-25T06:45Z
  - `mctl-telegram / issue-214-self-service-canonicalize-client-tier-in` — proposed 2026-05-25T08:08Z

---

## 4. Recent merged PRs (24 h — since 2026-05-29T09:00Z)

| merged_at (UTC) | repo | PR | title |
|-----------------|------|----|-------|
| 08:38 | mctl-web | [#20](https://github.com/mctlhq/mctl-web/pull/20) | fix: serve mctl-web on port 80 (v3 deploy outage fix) ⚠️ production fix |
| 08:31 | mctl-gitops | [#336](https://github.com/mctlhq/mctl-gitops/pull/336) | feat(base-service): optional renderIf gate for extraObjects |
| 08:20 | mctl-web | [#19](https://github.com/mctlhq/mctl-web/pull/19) | ci: bump claude review model to opus-4-8 |
| 08:18 | mctl-gitops | [#334](https://github.com/mctlhq/mctl-gitops/pull/334) | feat(telegram): add demo session refresh CronJob |
| 08:12 | mctl-web | [#12](https://github.com/mctlhq/mctl-web/pull/12) | feat: redesign v3 — pain section, trust strip, mid-CTA, updated hero ✅ (was stale 13d) |
| 07:28 | mctl-portal | [#17](https://github.com/mctlhq/mctl-portal/pull/17) | ci: bump claude review model to opus-4-8 |
| 07:28 | mctl-gitops | [#333](https://github.com/mctlhq/mctl-gitops/pull/333) | ci: bump claude review model to opus-4-8 |
| 07:28 | mctl-api | [#66](https://github.com/mctlhq/mctl-api/pull/66) | ci: bump claude review model to opus-4-8 |
| 07:28 | mctl-agents | [#33](https://github.com/mctlhq/mctl-agents/pull/33) | ci: bump claude review model to opus-4-8 |
| 07:28 | mctl-docs | [#19](https://github.com/mctlhq/mctl-docs/pull/19) | ci: bump claude review model to opus-4-8 |
| 07:28 | mctl-claude-remote | [#21](https://github.com/mctlhq/mctl-claude-remote/pull/21) | ci: bump claude review model to opus-4-8 |
| 07:28 | mctl-agent | [#24](https://github.com/mctlhq/mctl-agent/pull/24) | ci: bump claude review model to opus-4-8 |
| 07:21 | mctl-api | [#65](https://github.com/mctlhq/mctl-api/pull/65) | ci(release): harden release-please (issues:write, failure alert, concurrency) |
| 07:08 | mctl-portal | [#16](https://github.com/mctlhq/mctl-portal/pull/16) | ci(release): harden release-please (issues:write, failure alert, concurrency) |
| 06:53 | mctl-design | [#11](https://github.com/mctlhq/mctl-design/pull/11) | docs: list the @mctlhq/ui components in the README |
| 06:50 | mctl-portal | [#14](https://github.com/mctlhq/mctl-portal/pull/14) | feat(ci): migrate to centralized build via release-please and mctl-gitops release-deploy |
| 06:50 | mctl-api | [#63](https://github.com/mctlhq/mctl-api/pull/63) | feat(ci): migrate to centralized build via release-please and mctl-gitops release-deploy |
| 06:48 | mctl-design | [#10](https://github.com/mctlhq/mctl-design/pull/10) | chore(ci): use claude-opus-4-8 for the PR reviewer |

_(18 PRs total. Notable: mctl-web v3 outage fix merged ~26min after the redesign that caused it. mctl-docs PR #19 merged cleanly — separate from the stale release PR #17 which remains open.)_

---

## 5. Bot commits (26 h — author = mctl-agents)

**None** for the **5th consecutive day**. Last `mctl-agents` bot activity was 2026-05-25T08:08Z (`chore(agents): issue-poll 2026-05-25`).

---

## 6. Detected problems

### New stand-alone issue opened today

| issue | PR | reason |
|-------|----|--------|
| [#337](https://github.com/mctlhq/mctl-gitops/issues/337) | [mctl-telegram#146](https://github.com/mctlhq/mctl-telegram/pull/146) | Crossed 7d threshold (last activity 2026-05-22, 8d ago); predicted in #331 |

### Stand-alone issue closed today

| issue | PR | reason |
|-------|----|--------|
| [#297](https://github.com/mctlhq/mctl-gitops/issues/297) ✅ | [mctl-web#12](https://github.com/mctlhq/mctl-web/pull/12) | PR merged 2026-05-30T08:12Z |

### Continuing stale-pr issues (dedup comments posted)

| issue | PR | days stale | today's action |
|-------|----|-----------|----------------|
| [#121](https://github.com/mctlhq/mctl-gitops/issues/121) | [mctl-portal#7](https://github.com/mctlhq/mctl-portal/pull/7) | **32 d** | comment posted |
| [#228](https://github.com/mctlhq/mctl-gitops/issues/228) | [mctl-agents#15](https://github.com/mctlhq/mctl-agents/pull/15) | **21 d** | comment posted |
| [#229](https://github.com/mctlhq/mctl-gitops/issues/229) | [mctl-agents#16](https://github.com/mctlhq/mctl-agents/pull/16) | **21 d** | comment posted |
| [#230](https://github.com/mctlhq/mctl-gitops/issues/230) | [mctl-agents#17](https://github.com/mctlhq/mctl-agents/pull/17) | **21 d** | comment posted |
| [#231](https://github.com/mctlhq/mctl-gitops/issues/231) | [mctl-api#47](https://github.com/mctlhq/mctl-api/pull/47) | **20 d** | comment posted |
| [#246](https://github.com/mctlhq/mctl-gitops/issues/246) | [mctl-gitops#84](https://github.com/mctlhq/mctl-gitops/pull/84) | **30 d** | comment posted |
| [#263](https://github.com/mctlhq/mctl-gitops/issues/263) | [mctl-api#51](https://github.com/mctlhq/mctl-api/pull/51) | **19 d** | comment posted |
| [#294](https://github.com/mctlhq/mctl-gitops/issues/294) | [mctl-docs#17](https://github.com/mctlhq/mctl-docs/pull/17) | ~14 d (updated today by automation) | comment posted |
| [#295](https://github.com/mctlhq/mctl-gitops/issues/295) | [mctl-gitops#217](https://github.com/mctlhq/mctl-gitops/pull/217) | **14 d** | comment posted |
| [#296](https://github.com/mctlhq/mctl-gitops/issues/296) | [mctl-agent#20](https://github.com/mctlhq/mctl-agent/pull/20) | **14 d** | comment posted |
| [#305](https://github.com/mctlhq/mctl-gitops/issues/305) | [mctl-api#55–58](https://github.com/mctlhq/mctl-api/pull/55) | **12 d** | comment posted |

### Watch list — approaching 7-day threshold

| PR | title | last activity | days stale | threshold |
|----|-------|--------------|-----------|-----------|
| [mctl-gitops#306](https://github.com/mctlhq/mctl-gitops/pull/306) | fix(observability): prometheus-pushgateway into gitops | 2026-05-25 | 5 d | **2026-06-01** |
| [mctl-api#61](https://github.com/mctlhq/mctl-api/pull/61) | ci: bump claude-code-action | 2026-05-25 | 5 d | **2026-06-01** |
| [mctl-telegram#221](https://github.com/mctlhq/mctl-telegram/pull/221) | fix(oauth): auto-persist tier=client on sign-in | 2026-05-26 | 4 d | 2026-06-02 |
| [mctl-telegram#170](https://github.com/mctlhq/mctl-telegram/pull/170) | chore(deps): bump golang.org/x/crypto | 2026-05-27 | 3 d | 2026-06-03 |
| [mctl-telegram#167](https://github.com/mctlhq/mctl-telegram/pull/167) | chore(deps): bump chi/v5 5.2.5→5.3.0 | 2026-05-27 | 3 d | 2026-06-03 |

### Bot agent idle — 5 consecutive days

`mctl-agents` bot has produced no commits since 2026-05-25T08:08Z. Both `mctl-agents-shepherd` and `mctl-agents-implement` crons appear inactive. The two open `proposed` proposals (issue-213, issue-214) require human approval per their `control.requires_human_approval: true` flag, so they are not blocking the bot — but the bot is also not advancing any other new work. Verify the cron schedule is still live.

### Stuck proposals

None. issue-213 and issue-214 are 5 days old (threshold: 7 days, date: **2026-06-01**).

---

## 7. Cluster health

Skipped: api.mctl.ai MCP connector not attached to this session run. See TODO.

---

## 8. Errors during run

| step | error | impact |
|------|-------|--------|
| Report destination | GitHub MCP restricted to `mctlhq/mctl-gitops`; write to `mctlhq/mctl-agents` denied | Report posted to `mctlhq/mctl-gitops` (established fallback since 2026-05-05) |
| Previous daily-report lookup | Diffed against #331 found in `mctlhq/mctl-gitops` | Diffed correctly |
| `gh` CLI | Not installed in this environment | All GitHub ops via MCP tools |
| Telegram notification | `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` not set | Silently skipped |

---

## 9. TODO

- Attach the api.mctl.ai MCP connector to this routine to unlock workflow-run counts (`mctl_list_workflows`), MinIO PVC % (`mctl_get_resource_usage`), per-service restart counts (`mctl_get_service_status`), and ArgoCD app sync state.
- Fix write scope: add `mctlhq/mctl-agents` to the GitHub MCP session's allowed-repositories list.
- **2026-06-01:** open `[stale-pr]` issues for mctl-gitops#306 and mctl-api#61 if still no activity.
- Investigate `mctl-agents` bot idle for 5d: verify cron schedule for `mctl-agents-shepherd` and `mctl-agents-implement`.
- Resolve 2 open proposals (issue-213 + issue-214) — both require human approval in mctl-telegram.
