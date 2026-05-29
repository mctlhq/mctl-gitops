> **⚠️ Routing note:** `mctlhq/mctl-agents` is not accessible in this session (GitHub MCP token scoped to `mctlhq/mctl-gitops` only). This report is posted to `mctlhq/mctl-gitops` as a fallback. Previous report: [#329](https://github.com/mctlhq/mctl-gitops/issues/329) (2026-05-28).

---

## 1. Summary

- **45 proposals** across 10 repos: **38 merged**, **5 rejected**, **2 proposed** — **no pipeline changes vs [#329](https://github.com/mctlhq/mctl-gitops/issues/329)**.
- **3 PRs merged today**: design system completed (mctl-design#9 + mctl-web#17 aligned to MCTL tokens); CI infra (mctl-gitops#330 adds `values_path` override for bootstrap service deploys).
- **0 mctl-agents bot commits — 4th consecutive day** of bot silence (last activity: 2026-05-25T08:08Z). Shepherd + implementer crons appear idle.
- **15 stale PRs** (>7 d) — all have tracking issues; 12 dedup comments posted. **mctl-telegram#146 crosses the >7d threshold at 22:37 UTC tonight** — issue will be opened in tomorrow's run if still open.
- New open PRs today: mctl-api#63, mctl-portal#13/#14, mctl-design#10 (all CI migration / housekeeping).

---

## 2. Proposal pipeline state

| repo | slug | status | pr | Δ #329 |
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

## 3. Pipeline diff (vs [#329](https://github.com/mctlhq/mctl-gitops/issues/329) — 2026-05-28)

- **Newly merged**: none
- **Newly rejected**: none
- **Newly proposed**: none
- **Still in-progress**: none
- **Still proposed (4 days old — threshold 2026-06-01)**:
  - `mctl-telegram / issue-213-deploy-canary-prometheusrule-to-cluster` — proposed 2026-05-25T06:45Z
  - `mctl-telegram / issue-214-self-service-canonicalize-client-tier-in` — proposed 2026-05-25T08:08Z

---

## 4. Recent merged PRs (24 h)

| merged_at (UTC) | repo | PR | title |
|-----------------|------|----|-------|
| 2026-05-29T07:36Z | mctl-web | [#17](https://github.com/mctlhq/mctl-web/pull/17) | feat: align mctl-web with the MCTL design system |
| 2026-05-29T07:35Z | mctl-design | [#9](https://github.com/mctlhq/mctl-design/pull/9) | feat: brand Storybook, load fonts, refine + extend the component library |
| 2026-05-29T07:12Z | mctl-gitops | [#330](https://github.com/mctlhq/mctl-gitops/pull/330) | feat(ci): add optional values_path to release-deploy for bootstrap services |

_(3 PRs total — design system completion sprint + CI infra. mctl-telegram#235/#236 were in yesterday's report.)_

---

## 5. Bot commits (26 h — author = mctl-agents)

**None** for the **4th consecutive day**. Last `mctl-agents` bot activity in mctl-gitops was 2026-05-25T08:08Z (`chore(agents): issue-poll 2026-05-25`).

Other notable automation commits in mctl-gitops (last 26 h):

| hash | author | message |
|------|--------|---------|
| `44970d7` | mctl-ci | chore: bump admins/mctl-design to c8e875d4986f |
| `6cdccd6` | mctl-deploy | feat(ci): support split registry/repository format in release-deploy bump |
| `f8e97ed` | mctl-deploy | feat(ci): add optional values_path to release-deploy for bootstrap services |
| `630a627` | mctl-deploy | ci: retrigger claude review |

---

## 6. Detected problems

### Stale PRs (>7 d) — all already tracked, follow-up comments posted

No new stale-pr issues opened today. mctl-telegram#146 crosses >7d at **22:37 UTC tonight** (6.5 d at run time) — issue queued for tomorrow's run. All 12 ongoing issues received a dedup comment.

| PR | days stale | tracking issue | today's action |
|----|-----------|----------------|----------------|
| [mctl-portal#7](https://github.com/mctlhq/mctl-portal/pull/7) | **29 d** | [#121](https://github.com/mctlhq/mctl-gitops/issues/121) | comment posted |
| [mctl-gitops#84](https://github.com/mctlhq/mctl-gitops/pull/84) | **29 d** | [#246](https://github.com/mctlhq/mctl-gitops/issues/246) | comment posted |
| [mctl-agents#15](https://github.com/mctlhq/mctl-agents/pull/15) | **20 d** | [#228](https://github.com/mctlhq/mctl-gitops/issues/228) | comment posted |
| [mctl-agents#16](https://github.com/mctlhq/mctl-agents/pull/16) | **20 d** | [#229](https://github.com/mctlhq/mctl-gitops/issues/229) | comment posted |
| [mctl-agents#17](https://github.com/mctlhq/mctl-agents/pull/17) | **20 d** | [#230](https://github.com/mctlhq/mctl-gitops/issues/230) | comment posted |
| [mctl-api#47](https://github.com/mctlhq/mctl-api/pull/47) | **19 d** | [#231](https://github.com/mctlhq/mctl-gitops/issues/231) | comment posted |
| [mctl-api#51](https://github.com/mctlhq/mctl-api/pull/51) | **18 d** | [#263](https://github.com/mctlhq/mctl-gitops/issues/263) | comment posted |
| [mctl-docs#17](https://github.com/mctlhq/mctl-docs/pull/17) | **13 d** | [#294](https://github.com/mctlhq/mctl-gitops/issues/294) | comment posted |
| [mctl-gitops#217](https://github.com/mctlhq/mctl-gitops/pull/217) | **13 d** | [#295](https://github.com/mctlhq/mctl-gitops/issues/295) | comment posted |
| [mctl-agent#20](https://github.com/mctlhq/mctl-agent/pull/20) | **13 d** | [#296](https://github.com/mctlhq/mctl-gitops/issues/296) | comment posted |
| [mctl-web#12](https://github.com/mctlhq/mctl-web/pull/12) | **13 d** | [#297](https://github.com/mctlhq/mctl-gitops/issues/297) | comment posted |
| [mctl-api#55–58](https://github.com/mctlhq/mctl-api/pull/55) | **11 d** | [#305](https://github.com/mctlhq/mctl-gitops/issues/305) | comment posted |

### Watch list — approaching 7-day threshold

| PR | title | last activity | days stale | threshold |
|----|-------|--------------|-----------|-----------|
| [mctl-telegram#146](https://github.com/mctlhq/mctl-telegram/pull/146) | Enhance landing page UX: card animations, SVG icons | 2026-05-22T22:37Z | **6.5 d** | **tonight 22:37 UTC** → open issue 2026-05-30 |
| [mctl-gitops#306](https://github.com/mctlhq/mctl-gitops/pull/306) | fix(observability): prometheus-pushgateway into gitops | 2026-05-25 | 4 d | 2026-06-01 |
| [mctl-api#61](https://github.com/mctlhq/mctl-api/pull/61) | ci: bump claude-code-action | 2026-05-25 | 4 d | 2026-06-01 |
| [mctl-telegram#221](https://github.com/mctlhq/mctl-telegram/pull/221) | fix(oauth): auto-persist tier=client on sign-in | 2026-05-26 | 3 d | 2026-06-02 |

### Stuck proposals

None. issue-213 and issue-214 are 4 days old (threshold: 7 days, date: 2026-06-01).

### Bot agent idle — 4 consecutive days

`mctl-agents` bot has produced no commits since 2026-05-25T08:08Z. Both `mctl-agents-shepherd` and `mctl-agents-implement` crons appear inactive. Verify schedule is still live.

---

## 7. Cluster health

Skipped: api.mctl.ai MCP connector not attached to this session run. See TODO.

---

## 8. Errors during run

| step | error | impact |
|------|-------|--------|
| Report destination | GitHub MCP restricted to `mctlhq/mctl-gitops`; write to `mctlhq/mctl-agents` denied | Report posted to `mctlhq/mctl-gitops` (established fallback since 2026-05-05) |
| Previous daily-report lookup | Used search in `mctlhq/mctl-gitops` as fallback | Diffed against #329 correctly |
| `gh` CLI | Not installed in this environment | All GitHub ops via MCP tools |
| `GITHUB_PAT` | Present in env but returns HTTP 401 (token expired) | Not used |
| Telegram notification | `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` not set | Silently skipped |

---

## 9. TODO

- Attach the api.mctl.ai MCP connector to this routine to unlock workflow-run counts (`mctl_list_workflows`), MinIO PVC % (`mctl_get_resource_usage`), per-service restart counts (`mctl_get_service_status`), and ArgoCD app sync state.
- Fix write scope: add `mctlhq/mctl-agents` to the GitHub MCP session's allowed-repositories list.
- **Tomorrow (2026-05-30):** open `[stale-pr] mctl-telegram#146` if still no activity (crosses >7d at 22:37 UTC tonight).
- Investigate `mctl-agents` bot idle for 4d: verify cron schedule for `mctl-agents-shepherd` and `mctl-agents-implement`.
- Resolve 2 open proposals (issue-213 + issue-214) — both require human approval in mctl-telegram.
