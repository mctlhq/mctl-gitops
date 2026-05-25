> ⚠️ **Routing note:** Intended for `mctlhq/mctl-agents`; posted here because the GitHub MCP session is restricted to `mctlhq/mctl-gitops`. Fix: add `mctlhq/mctl-agents` to the MCP allowed-repositories list. Previous report: [mctlhq/mctl-gitops#298](https://github.com/mctlhq/mctl-gitops/issues/298) (2026-05-24).

---

## 1. Summary

45 proposals tracked across 10 repos (was 42 in [#298](https://github.com/mctlhq/mctl-gitops/issues/298)): **38 merged, 5 rejected, 2 newly proposed today, 0 in-progress**. Three new proposals since yesterday: `issue-202` appeared and merged in the same day (bot fixed canary CronWorkflow stuck on image pull); `issue-213` and `issue-214` are freshly proposed (both mctl-telegram, require human approval). **31 PRs merged org-wide in 24h** — all mctl-telegram, heavy demo/release sprint (6 releases: 0.31.0→0.38.0 plus /demo page, reviewer auth-mode, OAuth and CSP fixes). 5 bot commits (3 issue-poll, 1 shepherd, 1 implement). **4 new stale-pr issues opened** (mctl-api#55–58 crossed the 7-day threshold today, as predicted in #298). 11 dedup comments posted on existing stale-pr issues. **api.mctl.ai MCP connector online:** 20 active warning incidents (all recurring ≥3 days, none critical); 2 agent runs failed at 09:05 UTC (transient, prior 09:00 runs succeeded).

---

## 2. Proposal Pipeline State

| repo | slug | status | pr | Δ #298 |
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
| mctl-telegram | issue-154-nav-replace-github-text-link-with-a-gith | `merged` | [#157](https://github.com/mctlhq/mctl-telegram/pull/157) | — |
| mctl-telegram | issue-158-non-deterministic-safety-block-on-get-me | `merged` | [#162](https://github.com/mctlhq/mctl-telegram/pull/162) | — |
| mctl-telegram | issue-159-live-send-unusable-when-prepare-send-mes | `merged` | [#163](https://github.com/mctlhq/mctl-telegram/pull/163) | — |
| mctl-telegram | issue-202-mctl-telegram-canary-cronjob-stuck-on-im | `merged` | [#211](https://github.com/mctlhq/mctl-telegram/pull/211) | **✓ new→merged** |
| mctl-telegram | issue-213-deploy-canary-prometheusrule-to-cluster | `proposed` | — | **new** |
| mctl-telegram | issue-214-self-service-canonicalize-client-tier-in | `proposed` | — | **new** |
| mctl-web | wrangler-upgrade-security | `merged` | [#9](https://github.com/mctlhq/mctl-web/pull/9) | — |

---

## 3. Pipeline Diff (vs [#298](https://github.com/mctlhq/mctl-gitops/issues/298) — 2026-05-24)

Yesterday ([#298](https://github.com/mctlhq/mctl-gitops/issues/298)): 42 proposals — merged(36), rejected(6) — all terminal  
Today: **45 proposals — merged(38), rejected(5), proposed(2)**

- **Newly merged (1):** `mctl-telegram/issue-202-mctl-telegram-canary-cronjob-stuck-on-im` → PR [mctl-telegram#211](https://github.com/mctlhq/mctl-telegram/pull/211) (merged 2026-05-25T07:00:55Z — bot fixed canary CronWorkflow stuck on image pull)
- **Newly proposed (2):**
  - `mctl-telegram/issue-213-deploy-canary-prometheusrule-to-cluster` (proposed 2026-05-25T06:45Z, requires human approval)
  - `mctl-telegram/issue-214-self-service-canonicalize-client-tier-in` (proposed 2026-05-25T08:08Z, requires human approval)
- **Newly rejected:** none
- **Still in-progress:** none
- **Still proposed (carry-over):** none — both proposed entries are new today

---

## 4. Recent Merged PRs (24h)

> PRs merged across the org since 2026-05-24T09:00Z. Source: `org:mctlhq is:pr is:merged merged:>=2026-05-24`.

**31 PRs merged in 24h** — mctl-telegram dominated with a /demo page buildout and six release cuts. Notable: reviewer auth-mode, OAuth CSP fix, dry-run for demo accounts, and mctl-telegram 0.38.0 shipping the agent-merged canary CronWorkflow fix.

| merged\_at (UTC) | repo | PR | title |
|-----------------|------|----|-------|
| 2026-05-25 06:22 | mctl-telegram | [#212](https://github.com/mctlhq/mctl-telegram/pull/212) | chore(main): release 0.38.0 |
| 2026-05-25 06:18 | mctl-telegram | [#211](https://github.com/mctlhq/mctl-telegram/pull/211) | feat(agents): issue-202-mctl-telegram-canary-cronjob-stuck-on-im |
| 2026-05-25 05:24 | mctl-gitops | [#303](https://github.com/mctlhq/mctl-gitops/pull/303) | chore(labs): bump mctl-telegram DEMO_VIDEO_URL cache-buster to v=2 |
| 2026-05-25 05:24 | mctl-telegram | [#209](https://github.com/mctlhq/mctl-telegram/pull/209) | chore(main): release 0.37.2 |
| 2026-05-25 05:23 | mctl-telegram | [#210](https://github.com/mctlhq/mctl-telegram/pull/210) | chore: force release 0.37.2 (refreshed /demo video) |
| 2026-05-25 05:23 | mctl-telegram | [#208](https://github.com/mctlhq/mctl-telegram/pull/208) | feat(web): refresh /demo walkthrough video (full 8-step run) |
| 2026-05-25 04:51 | mctl-telegram | [#207](https://github.com/mctlhq/mctl-telegram/pull/207) | chore(main): release 0.37.1 |
| 2026-05-25 04:50 | mctl-telegram | [#206](https://github.com/mctlhq/mctl-telegram/pull/206) | chore: force release 0.37.1 (ship /demo heading) |
| 2026-05-25 01:08 | mctl-telegram | [#205](https://github.com/mctlhq/mctl-telegram/pull/205) | docs(web): reframe /demo list as capabilities |
| 2026-05-25 00:54 | mctl-gitops | [#302](https://github.com/mctlhq/mctl-gitops/pull/302) | feat(telegram): point demo video at self-hosted walkthrough mp4 |
| 2026-05-25 00:46 | mctl-telegram | [#204](https://github.com/mctlhq/mctl-telegram/pull/204) | chore(main): release 0.37.0 |
| 2026-05-25 00:45 | mctl-telegram | [#203](https://github.com/mctlhq/mctl-telegram/pull/203) | feat(web): serve demo walkthrough video on /demo |
| 2026-05-25 00:13 | mctl-telegram | [#201](https://github.com/mctlhq/mctl-telegram/pull/201) | chore(main): release 0.36.0 |
| 2026-05-25 00:12 | mctl-telegram | [#200](https://github.com/mctlhq/mctl-telegram/pull/200) | feat(mcp): force dry-run for reviewer/demo account sends |
| 2026-05-24 23:30 | mctl-telegram | [#199](https://github.com/mctlhq/mctl-telegram/pull/199) | chore(main): release 0.35.1 |
| 2026-05-24 23:29 | mctl-telegram | [#198](https://github.com/mctlhq/mctl-telegram/pull/198) | fix(oauth): allow cross-origin redirect after sign-in (CSP form-action) |
| 2026-05-24 23:06 | mctl-gitops | [#301](https://github.com/mctlhq/mctl-gitops/pull/301) | fix(telegram): raise OAUTH_CODE_TTL to 30m |
| 2026-05-24 22:59 | mctl-gitops | [#300](https://github.com/mctlhq/mctl-gitops/pull/300) | feat(telegram): enable demo reviewer login mode |
| 2026-05-24 22:48 | mctl-telegram | [#197](https://github.com/mctlhq/mctl-telegram/pull/197) | chore(main): release 0.35.0 |
| 2026-05-24 22:39 | mctl-telegram | [#196](https://github.com/mctlhq/mctl-telegram/pull/196) | feat(oauth): password-gated reviewer/demo auth-mode |
| 2026-05-24 20:15 | mctl-gitops | [#299](https://github.com/mctlhq/mctl-gitops/pull/299) | feat(telegram): set DEMO_VIDEO_URL for /demo walkthrough |
| 2026-05-24 09:04 | mctl-telegram | [#195](https://github.com/mctlhq/mctl-telegram/pull/195) | chore(main): release 0.34.1 |
| 2026-05-24 09:03 | mctl-telegram | [#194](https://github.com/mctlhq/mctl-telegram/pull/194) | fix(ui): tidy footer layout on mobile |
| 2026-05-24 08:50 | mctl-telegram | [#193](https://github.com/mctlhq/mctl-telegram/pull/193) | chore(main): release 0.34.0 |
| 2026-05-24 08:49 | mctl-telegram | [#192](https://github.com/mctlhq/mctl-telegram/pull/192) | feat(ui): add demo link to topbar nav |
| 2026-05-24 08:30 | mctl-telegram | [#191](https://github.com/mctlhq/mctl-telegram/pull/191) | chore(main): release 0.33.0 |
| 2026-05-24 08:29 | mctl-telegram | [#190](https://github.com/mctlhq/mctl-telegram/pull/190) | feat(web): add /demo page for ChatGPT App review recording |
| 2026-05-24 00:49 | mctl-telegram | [#189](https://github.com/mctlhq/mctl-telegram/pull/189) | chore(main): release 0.32.0 |
| 2026-05-24 00:48 | mctl-telegram | [#188](https://github.com/mctlhq/mctl-telegram/pull/188) | feat(mcp): add outputSchema to all MCP tool descriptors |
| 2026-05-24 00:24 | mctl-telegram | [#187](https://github.com/mctlhq/mctl-telegram/pull/187) | chore(main): release 0.31.0 |
| 2026-05-24 00:23 | mctl-telegram | [#186](https://github.com/mctlhq/mctl-telegram/pull/186) | OpenAI Apps submission readiness: state cap + domain verification + /terms |

_(31 PRs total — mctl-telegram: 26, mctl-gitops: 5)_

---

## 5. Bot Commits (26h)

> `git log --author="mctl-agents" --since="26 hours ago"` in `mctlhq/mctl-gitops`

| hash | timestamp (UTC) | message |
|------|-----------------|---------|
| `fead412` | 2026-05-25 08:08 | chore(agents): issue-poll 2026-05-25 |
| `ba22131` | 2026-05-25 07:02 | chore(agents): shepherd run 2026-05-25 |
| `3298d0e` | 2026-05-25 06:47 | chore(agents): issue-poll 2026-05-25 |
| `56b754f` | 2026-05-25 05:48 | chore(agents): implement run 2026-05-25 |
| `81c9c58` | 2026-05-25 00:30 | chore(agents): issue-poll 2026-05-25 |

5 bot commits — 3 issue-poll, 1 shepherd, 1 implement. The implement run at 05:48 correlates with `issue-202` being merged at 07:01 (bot opened PR, shepherd merged it within ~1h).

---

## 6. Detected Problems

### New stale-pr issues opened (4)

These 4 mctl-api dep-bump PRs crossed the 7-day dormancy threshold today, as predicted in [#298](https://github.com/mctlhq/mctl-gitops/issues/298) watch list.

| PR | title | days dormant | new issue |
|----|-------|-------------|-----------|
| [mctl-api#55](https://github.com/mctlhq/mctl-api/pull/55) | deps: bump mcp-go 0.46.0→0.54.0 | **7 d** | _see below_ |
| [mctl-api#56](https://github.com/mctlhq/mctl-api/pull/56) | deps: bump k8s.io/apimachinery 0.32.3→0.36.1 | **7 d** | _see below_ |
| [mctl-api#57](https://github.com/mctlhq/mctl-api/pull/57) | deps: bump k8s.io/api 0.32.3→0.36.1 | **7 d** | _see below_ |
| [mctl-api#58](https://github.com/mctlhq/mctl-api/pull/58) | deps: bump k8s.io/client-go 0.32.3→0.36.1 | **7 d** | _see below_ |

### Existing stale-pr issues — dedup follow-up comments posted (11)

| PR | days dormant | existing issue | action |
|----|-------------|----------------|--------|
| [mctl-gitops#84](https://github.com/mctlhq/mctl-gitops/pull/84) | **26 d** | [#246](https://github.com/mctlhq/mctl-gitops/issues/246) | comment |
| [mctl-agents#15](https://github.com/mctlhq/mctl-agents/pull/15) | 17 d | [#228](https://github.com/mctlhq/mctl-gitops/issues/228) | comment |
| [mctl-agents#16](https://github.com/mctlhq/mctl-agents/pull/16) | 17 d | [#229](https://github.com/mctlhq/mctl-gitops/issues/229) | comment |
| [mctl-agents#17](https://github.com/mctlhq/mctl-agents/pull/17) | 17 d | [#230](https://github.com/mctlhq/mctl-gitops/issues/230) | comment |
| [mctl-api#47](https://github.com/mctlhq/mctl-api/pull/47) | 16 d | [#231](https://github.com/mctlhq/mctl-gitops/issues/231) | comment |
| [mctl-api#51](https://github.com/mctlhq/mctl-api/pull/51) | 15 d | [#263](https://github.com/mctlhq/mctl-gitops/issues/263) | comment |
| [mctl-portal#7](https://github.com/mctlhq/mctl-portal/pull/7) | 16 d | [#121](https://github.com/mctlhq/mctl-gitops/issues/121) | comment |
| [mctl-docs#17](https://github.com/mctlhq/mctl-docs/pull/17) | 10 d | [#294](https://github.com/mctlhq/mctl-gitops/issues/294) | comment |
| [mctl-gitops#217](https://github.com/mctlhq/mctl-gitops/pull/217) | 10 d | [#295](https://github.com/mctlhq/mctl-gitops/issues/295) | comment |
| [mctl-agent#20](https://github.com/mctlhq/mctl-agent/pull/20) | 10 d | [#296](https://github.com/mctlhq/mctl-gitops/issues/296) | comment |
| [mctl-web#12](https://github.com/mctlhq/mctl-web/pull/12) | 10 d | [#297](https://github.com/mctlhq/mctl-gitops/issues/297) | comment |

### Watch list — PRs approaching 7-day threshold

| PR | title | days dormant | threshold date |
|----|-------|-------------|----------------|
| [mctl-telegram#146](https://github.com/mctlhq/mctl-telegram/pull/146) | Enhance landing page UX: card animations, SVG icons | 3 d | 2026-05-29 |
| [mctl-api/pull/61](https://github.com/mctlhq/mctl-api/pull/61) | ci: bump claude-code-action | <1 d | 2026-06-01 |

### Cluster incidents (active, recurring)

20 active warning-severity incidents, all stuck in `analyzing` (no fix proposed). Three patterns recurring ≥3 days — not escalating yet (all warnings, no critical, and today is only day 2 of incident tracking since MCP connector came online):

| pattern | tenant / service | oldest firing |
|---------|----------------|--------------|
| Vmagent scrape_pool 0 targets | monitoring | 2026-05-21T08:09Z (4 d) |
| CPU throttling | argo-workflows-workflow-controller | 2026-05-21T12:17Z (4 d) |
| CPU throttling | labs-claude-remote-base-service | 2026-05-20T12:39Z (5 d) |
| CPU throttling | argocd-repo-server | 2026-05-20T14:16Z (5 d) |
| Job failed (kube-state-metrics) | labs / monitoring | 2026-05-21T08:12Z (4 d) |

### Agent workflow failures at 09:05 UTC

- `mctl-agents-implement-1779699900` — child `…-1127520951` failed  
- `mctl-agents-issue-poll-1779699900` — child `…-1374372431` failed  

Transient — immediately prior runs at 09:00 UTC succeeded. No action needed unless next run also fails.

---

## 7. Cluster Health

**api.mctl.ai MCP connector available** (connected mid-run; was listed as unavailable in prior routine's TODO). Data sourced from `mctl_list_incidents`, `mctl_list_recent_agent_runs`, `mctl_list_workflows`.

- **0 critical incidents.** 20 active warnings (details in section 6).
- **Agent crons:** 2 failed at 09:05 UTC (`implement` + `issue-poll`), prior 09:00 succeeded; shepherd submitted at 09:00.
- **Labs deploys (24h):** 2 operator (`mashkovd`) deploys at 2026-05-24T22:35 and T22:45.
- **Manual runs (24h):** mashkovd ran `mctl-agents-shepherd` at 06:14 and `mctl-agents-implement` at 05:45.
- **Resource usage / per-service restart counts / ArgoCD sync state:** not queried this run (would require per-team calls); recurring CPU throttling incidents suggest `argo-workflows-workflow-controller` and `labs-claude-remote-base-service` are undersized.

---

## 8. Errors During Run

| step | error | impact |
|------|-------|--------|
| Report destination | GitHub MCP restricted to `mctlhq/mctl-gitops`; write to `mctlhq/mctl-agents` denied | Issue posted to `mctl-gitops` — consistent with all prior daily reports since 2026-05-05 |
| Previous daily-report lookup | `list_issues --repo mctlhq/mctl-agents` denied (same scope restriction) | Diffed against `mctlhq/mctl-gitops` daily-report issues (#298); no data loss |
| Telegram notification | `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` not set | Silently skipped (expected) |
| GitHub MCP PR search | Two `search_pull_requests` responses exceeded token limit; saved to disk | Recovered via Python; all 31 merged + 26 open PRs processed; no data loss |

---

## 9. TODO

- **Fix write scope:** Add `mctlhq/mctl-agents` to the GitHub MCP session's allowed-repositories list. Every daily-report run since 2026-05-05 has been misrouted to `mctlhq/mctl-gitops`.
- **Act on 15 open stale-pr issues** — oldest: mctl-gitops#84 (26 days), mctl-agents#15/16/17 (17 days), mctl-api#47/51 (15–16 days), mctl-portal#7 (16 days).
- **Resolve 2 new proposals:** issue-213 and issue-214 both require human approval (ArgoCD canary PrometheusRule + client-tier canonicalization).
- **Investigate recurring CPU throttling** on `argo-workflows-workflow-controller` and `labs-claude-remote-base-service` — both firing for 5+ days with no fix proposed. Raise resource limits via gitops.
- **Investigate Vmagent scrape_pool zero-target** alert in `monitoring` — firing for 4+ days.
- **Expand cluster health section** next run: query `mctl_get_resource_usage` per team, `mctl_get_service_status` for services with open incidents, `mctl_list_workflows` counts.
