> ⚠️ **Routing note:** Intended for `mctlhq/mctl-agents`; posted here because the GitHub MCP session is restricted to `mctlhq/mctl-gitops`. Fix: add `mctlhq/mctl-agents` to the MCP allowed-repositories list. Baseline: [mctlhq/mctl-gitops#269](https://github.com/mctlhq/mctl-gitops/issues/269) (2026-05-22).

---

## 1. Summary

42 proposals tracked across 10 repos — **all 42 in terminal state** (36 merged, 6 rejected). Pipeline fully clear for the second consecutive day. 6 new proposals appeared and immediately merged within the 24h window (3 mctl-design, 3 mctl-telegram). Standout: **mctl-telegram is in an intensive ChatGPT App Store submission sprint** — 35+ PRs merged in 24h covering MCP annotations, outputSchema, submission readiness, /demo page, and domain verification. 8 bot commits (3 shepherd, 3 implement, 1 reconcile, 1 issue-poll). 4 new stale-pr issues opened (mctl-docs#17, mctl-gitops#217, mctl-agent#20, mctl-web#12 all crossed the 7-day threshold today, as predicted in yesterday's watch list). 7 dedup follow-up comments posted on existing stale-pr issues.

---

## 2. Proposal Pipeline State

| repo | slug | status | pr | Δ yesterday |
|------|------|--------|----|-------------|
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
| mctl-design | issue-3-change-the-storybook-overview-brand-icon | `merged` | [#8](https://github.com/mctlhq/mctl-design/pull/8) | ✓ new→merged |
| mctl-design | issue-4-rename-storybook-brand-title-to-mctl-ui | `merged` | [#5](https://github.com/mctlhq/mctl-design/pull/5) | ✓ new→merged |
| mctl-design | issue-6-align-storybook-page-title-og-title-with | `merged` | [#7](https://github.com/mctlhq/mctl-design/pull/7) | ✓ new→merged |
| mctl-docs | fix-broken-mctl-ai-mcp-links | `merged` | [#6](https://github.com/mctlhq/mctl-docs/pull/6) | — |
| mctl-docs | mcp-agents-tools | `merged` | [#7](https://github.com/mctlhq/mctl-docs/pull/7) | — |
| mctl-gitops | argo-workflows-cve-patch-v2 | `merged` | [#85](https://github.com/mctlhq/mctl-gitops/pull/85) | — |
| mctl-gitops | argocd-informer-cache-patch | `merged` | [#90](https://github.com/mctlhq/mctl-gitops/pull/90) | — |
| mctl-gitops | eso-cve-patch | `merged` | [#87](https://github.com/mctlhq/mctl-gitops/pull/87) | — |
| mctl-gitops | grafana-sql-rce-patch | `merged` | [#89](https://github.com/mctlhq/mctl-gitops/pull/89) | — |
| mctl-openclaw | upgrade-to-2026-4-27 | `rejected` | [#15](https://github.com/mctlhq/mctl-openclaw/pull/15) | — |
| mctl-portal | scaffolder-path-traversal | `rejected` | [#10](https://github.com/mctlhq/mctl-portal/pull/10) | — |
| mctl-portal | scaffolder-secret-leak | `rejected` | [#12](https://github.com/mctlhq/mctl-portal/pull/12) | — |
| mctl-telegram | issue-154-nav-replace-github-text-link-with-a-gith | `merged` | [#157](https://github.com/mctlhq/mctl-telegram/pull/157) | ✓ new→merged |
| mctl-telegram | issue-158-non-deterministic-safety-block-on-get-me | `merged` | [#162](https://github.com/mctlhq/mctl-telegram/pull/162) | ✓ new→merged |
| mctl-telegram | issue-159-live-send-unusable-when-prepare-send-mes | `merged` | [#163](https://github.com/mctlhq/mctl-telegram/pull/163) | ✓ new→merged |
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

## 3. Pipeline Diff (vs [#269](https://github.com/mctlhq/mctl-gitops/issues/269) — 2026-05-22)

Yesterday: 36 proposals — merged(31), rejected(5) — all terminal  
Today: **42 proposals — merged(36), rejected(6)** — all terminal

- **Newly merged (6):** _(all appeared as new proposals already in merged state)_
  - `mctl-design/issue-3` → PR [mctl-design#8](https://github.com/mctlhq/mctl-design/pull/8) merged 2026-05-23T12:46Z
  - `mctl-design/issue-4` → PR [mctl-design#5](https://github.com/mctlhq/mctl-design/pull/5) merged 2026-05-22T19:08Z
  - `mctl-design/issue-6` → PR [mctl-design#7](https://github.com/mctlhq/mctl-design/pull/7) merged 2026-05-23T00:46Z
  - `mctl-telegram/issue-154` → PR [mctl-telegram#157](https://github.com/mctlhq/mctl-telegram/pull/157) merged 2026-05-23T10:31Z
  - `mctl-telegram/issue-158` → PR [mctl-telegram#162](https://github.com/mctlhq/mctl-telegram/pull/162) merged 2026-05-23T13:57Z
  - `mctl-telegram/issue-159` → PR [mctl-telegram#163](https://github.com/mctlhq/mctl-telegram/pull/163) merged 2026-05-23T12:51Z
- **Newly rejected:** none
- **Newly proposed:** none (all new proposals first observed in merged state)
- **Still proposed:** none
- **Still in-progress:** none

---

## 4. Recent Merged PRs (24h)

> PRs merged across the org since 2026-05-23T09:00Z. Source: `org:mctlhq is:pr is:merged merged:>=2026-05-23`.

**45 PRs merged in 24h** — mctl-telegram dominates with a ChatGPT App Store submission sprint (versions 0.30.0 → 0.34.1 in a single day).

| repo | PR | title | merged at (UTC) |
|------|----|-------|----------------|
| mctl-telegram | [#195](https://github.com/mctlhq/mctl-telegram/pull/195) | chore(main): release 0.34.1 | 2026-05-24 09:04 |
| mctl-telegram | [#194](https://github.com/mctlhq/mctl-telegram/pull/194) | fix(ui): tidy footer layout on mobile | 2026-05-24 09:03 |
| mctl-telegram | [#193](https://github.com/mctlhq/mctl-telegram/pull/193) | chore(main): release 0.34.0 | 2026-05-24 08:50 |
| mctl-telegram | [#192](https://github.com/mctlhq/mctl-telegram/pull/192) | feat(ui): add demo link to topbar nav | 2026-05-24 08:49 |
| mctl-telegram | [#191](https://github.com/mctlhq/mctl-telegram/pull/191) | chore(main): release 0.33.0 | 2026-05-24 08:30 |
| mctl-telegram | [#190](https://github.com/mctlhq/mctl-telegram/pull/190) | feat(web): add /demo page for ChatGPT App review recording | 2026-05-24 08:29 |
| mctl-telegram | [#189](https://github.com/mctlhq/mctl-telegram/pull/189) | chore(main): release 0.32.0 | 2026-05-24 00:49 |
| mctl-telegram | [#188](https://github.com/mctlhq/mctl-telegram/pull/188) | feat(mcp): add outputSchema to all MCP tool descriptors | 2026-05-24 00:48 |
| mctl-telegram | [#187](https://github.com/mctlhq/mctl-telegram/pull/187) | chore(main): release 0.31.0 | 2026-05-24 00:24 |
| mctl-telegram | [#186](https://github.com/mctlhq/mctl-telegram/pull/186) | OpenAI Apps submission readiness: state cap + domain verification + /terms | 2026-05-24 00:23 |
| mctl-telegram | [#185](https://github.com/mctlhq/mctl-telegram/pull/185) | chore(main): release 0.30.6 | 2026-05-23 23:17 |
| mctl-telegram | [#184](https://github.com/mctlhq/mctl-telegram/pull/184) | fix(mcp): annotate send_message as destructive/open-world for submission | 2026-05-23 23:17 |
| mctl-telegram | [#183](https://github.com/mctlhq/mctl-telegram/pull/183) | chore(main): release 0.30.5 | 2026-05-23 23:07 |
| mctl-telegram | [#182](https://github.com/mctlhq/mctl-telegram/pull/182) | chore(main): release 0.30.4 | 2026-05-23 22:57 |
| mctl-telegram | [#181](https://github.com/mctlhq/mctl-telegram/pull/181) | fix(send): preserve draft-preview contract, fix bridge propagation | 2026-05-23 22:55 |
| mctl-telegram | [#180](https://github.com/mctlhq/mctl-telegram/pull/180) | chore(main): release 0.30.3 | 2026-05-23 22:28 |
| mctl-telegram | [#179](https://github.com/mctlhq/mctl-telegram/pull/179) | fix(mcp): correct tool annotation hints for ChatGPT App submission | 2026-05-23 22:23 |
| mctl-telegram | [#178](https://github.com/mctlhq/mctl-telegram/pull/178) | docs(web): prepare public pages for ChatGPT App Directory | 2026-05-23 21:49 |
| mctl-telegram | [#177](https://github.com/mctlhq/mctl-telegram/pull/177) | docs: add ChatGPT Apps SDK readiness guidance | 2026-05-23 21:24 |
| mctl-telegram | [#176](https://github.com/mctlhq/mctl-telegram/pull/176) | chore(main): release 0.30.2 | 2026-05-23 20:59 |
| mctl-telegram | [#175](https://github.com/mctlhq/mctl-telegram/pull/175) | fix: remove prepare_send_message to fix mobile ChatGPT send stall | 2026-05-23 20:58 |
| mctl-telegram | [#174](https://github.com/mctlhq/mctl-telegram/pull/174) | ci: revert auto-merge step that broke release-please | 2026-05-23 20:17 |
| mctl-telegram | [#173](https://github.com/mctlhq/mctl-telegram/pull/173) | ci: auto-merge release PR from within release-please workflow | 2026-05-23 20:13 |
| mctl-telegram | [#172](https://github.com/mctlhq/mctl-telegram/pull/172) | chore(main): release 0.30.1 | 2026-05-23 19:56 |
| mctl-telegram | [#171](https://github.com/mctlhq/mctl-telegram/pull/171) | fix: send-by-default connect + ChatGPT prepare/send flow | 2026-05-23 19:54 |
| mctl-gitops | [#292](https://github.com/mctlhq/mctl-gitops/pull/292) | feat(openclaw): add mctl-token-refresh sidecar for proactive token renewal | 2026-05-23 16:24 |
| mctl-telegram | [#166](https://github.com/mctlhq/mctl-telegram/pull/166) | ci: auto-merge release-please PRs on open | 2026-05-23 15:11 |
| mctl-openclaw | [#24](https://github.com/mctlhq/mctl-openclaw/pull/24) | feat(agents): add agents-intake workflow for issue-poller auto-labelling | 2026-05-23 15:05 |
| mctl-telegram | [#160](https://github.com/mctlhq/mctl-telegram/pull/160) | chore(main): release 0.30.0 | 2026-05-23 14:57 |
| mctl-telegram | [#162](https://github.com/mctlhq/mctl-telegram/pull/162) | feat(agents): issue-158-non-deterministic-safety-block-on-get-me | 2026-05-23 13:57 |
| mctl-telegram | [#165](https://github.com/mctlhq/mctl-telegram/pull/165) | ci: add issue_comment trigger to claude-review workflow | 2026-05-23 13:34 |
| mctl-gitops | [#293](https://github.com/mctlhq/mctl-gitops/pull/293) | chore(agents): bump mctl-agents image to 1.14.0 | 2026-05-23 13:16 |
| mctl-agents | [#32](https://github.com/mctlhq/mctl-agents/pull/32) | fix(shepherd): detect claude review severity format | 2026-05-23 13:13 |
| mctl-telegram | [#163](https://github.com/mctlhq/mctl-telegram/pull/163) | feat(agents): issue-159-live-send-unusable-when-prepare-send-mes | 2026-05-23 12:51 |
| mctl-telegram | [#164](https://github.com/mctlhq/mctl-telegram/pull/164) | fix(docs): audit-log retention sweeper ships, not planned | 2026-05-23 11:10 |
| mctl-gitops | [#291](https://github.com/mctlhq/mctl-gitops/pull/291) | docs(claude-remote): update recovery runbook for 0.8.0 watchdog | 2026-05-23 10:54 |
| mctl-claude-remote | [#20](https://github.com/mctlhq/mctl-claude-remote/pull/20) | fix(pr-steward): don't let review Action's own flaky check block auto-merge | 2026-05-23 10:41 |
| mctl-telegram | [#157](https://github.com/mctlhq/mctl-telegram/pull/157) | feat(agents): issue-154-nav-replace-github-text-link-with-a-gith | 2026-05-23 10:30 |
| mctl-design | [#8](https://github.com/mctlhq/mctl-design/pull/8) | feat(agents): issue-3-change-the-storybook-overview-brand-icon | 2026-05-23 10:05 |
| mctl-claude-remote | [#19](https://github.com/mctlhq/mctl-claude-remote/pull/19) | feat: in-pod wedge watchdog + supervisor relaunch (B4) | 2026-05-23 09:47 |
| mctl-gitops | [#290](https://github.com/mctlhq/mctl-gitops/pull/290) | docs(claude-remote): add wedge/disconnect recovery runbook | 2026-05-23 09:25 |
| mctl-claude-remote | [#18](https://github.com/mctlhq/mctl-claude-remote/pull/18) | feat(pr-steward): auto-advance BEHIND + bot-thread-BLOCKED PRs | 2026-05-23 09:11 |

_(45 PRs total — mctl-telegram: 37 (ChatGPT App Store submission sprint, 0.30.0→0.34.1), mctl-gitops: 4, mctl-claude-remote: 3, mctl-agents: 1, mctl-openclaw: 1, mctl-design: 1. mctl-claude-remote B4 watchdog + pr-steward improvements also notable.)_

---

## 5. Bot Commits (26h)

> `git log --author="mctl-agents" --since="26 hours ago"` in `mctlhq/mctl-gitops`

| hash | timestamp (UTC) | message |
|------|-----------------|---------|
| `db3e119` | 2026-05-23 13:22 | chore(agents): shepherd run 2026-05-23 |
| `ae6d796` | 2026-05-23 12:52 | chore(agents): shepherd run 2026-05-23 |
| `d226c4c` | 2026-05-23 12:47 | chore(agents): reconcile status 2026-05-23 |
| `38e492a` | 2026-05-23 10:32 | chore(agents): shepherd run 2026-05-23 |
| `6d64615` | 2026-05-23 09:57 | chore(agents): implement run 2026-05-23 |
| `664ce5c` | 2026-05-23 09:49 | chore(agents): implement run 2026-05-23 |
| `4fcf987` | 2026-05-23 09:44 | chore(agents): implement run 2026-05-23 |
| `e49fd0e` | 2026-05-23 08:55 | chore(agents): issue-poll 2026-05-23 |

8 bot commits — 3 shepherd, 3 implement, 1 reconcile, 1 issue-poll. The 3 implement runs in ~15 min (09:44–09:57) are consistent with parallel processing of the 3 new mctl-design and mctl-telegram proposals.

---

## 6. Detected Problems

### New stale-pr issues opened (4)

These PRs crossed the 7-day dormancy threshold today. All were flagged in yesterday's watch list ([#269](https://github.com/mctlhq/mctl-gitops/issues/269)), confirming stable problems.

| PR | title | days dormant | new issue |
|----|-------|-------------|-----------|
| [mctl-docs#17](https://github.com/mctlhq/mctl-docs/pull/17) | chore(main): release 0.1.20 | **8 d** | [#294](https://github.com/mctlhq/mctl-gitops/issues/294) |
| [mctl-gitops#217](https://github.com/mctlhq/mctl-gitops/pull/217) | feat(argo): add incident responder CronWorkflow | **8 d** | [#295](https://github.com/mctlhq/mctl-gitops/issues/295) |
| [mctl-agent#20](https://github.com/mctlhq/mctl-agent/pull/20) | feat(skills): add statefulset-replicas-mismatch YAML skill | **8 d** | [#296](https://github.com/mctlhq/mctl-gitops/issues/296) |
| [mctl-web#12](https://github.com/mctlhq/mctl-web/pull/12) | feat: redesign v3 — pain section, trust strip, mid-CTA | **8 d** | [#297](https://github.com/mctlhq/mctl-gitops/issues/297) |

### Existing stale-pr issues — dedup follow-up comments posted (7)

| PR | days dormant | existing issue | follow-up |
|----|-------------|----------------|-----------|
| [mctl-gitops#84](https://github.com/mctlhq/mctl-gitops/pull/84) | **24 d** | [#246](https://github.com/mctlhq/mctl-gitops/issues/246) | [comment](https://github.com/mctlhq/mctl-gitops/issues/246#issuecomment-4527947041) |
| [mctl-agents#15](https://github.com/mctlhq/mctl-agents/pull/15) | 15 d | [#228](https://github.com/mctlhq/mctl-gitops/issues/228) | [comment](https://github.com/mctlhq/mctl-gitops/issues/228#issuecomment-4527947179) |
| [mctl-agents#16](https://github.com/mctlhq/mctl-agents/pull/16) | 15 d | [#229](https://github.com/mctlhq/mctl-gitops/issues/229) | [comment](https://github.com/mctlhq/mctl-gitops/issues/229#issuecomment-4527947271) |
| [mctl-agents#17](https://github.com/mctlhq/mctl-agents/pull/17) | 15 d | [#230](https://github.com/mctlhq/mctl-gitops/issues/230) | [comment](https://github.com/mctlhq/mctl-gitops/issues/230#issuecomment-4527947476) |
| [mctl-api#47](https://github.com/mctlhq/mctl-api/pull/47) | 14 d | [#231](https://github.com/mctlhq/mctl-gitops/issues/231) | [comment](https://github.com/mctlhq/mctl-gitops/issues/231#issuecomment-4527947567) |
| [mctl-api#51](https://github.com/mctlhq/mctl-api/pull/51) | 13 d | [#263](https://github.com/mctlhq/mctl-gitops/issues/263) | [comment](https://github.com/mctlhq/mctl-gitops/issues/263#issuecomment-4527947691) |
| [mctl-portal#7](https://github.com/mctlhq/mctl-portal/pull/7) | 14 d | [#121](https://github.com/mctlhq/mctl-gitops/issues/121) | [comment](https://github.com/mctlhq/mctl-gitops/issues/121#issuecomment-4527947790) |

### Watch list — PRs approaching 7-day threshold

| PR | title | days dormant | threshold date |
|----|-------|-------------|----------------|
| [mctl-api#55](https://github.com/mctlhq/mctl-api/pull/55) | deps: bump mcp-go 0.46.0→0.54.0 | 6 d | **2026-05-25** |
| [mctl-api#56](https://github.com/mctlhq/mctl-api/pull/56) | deps: bump k8s.io/apimachinery 0.32.3→0.36.1 | 6 d | **2026-05-25** |
| [mctl-api#57](https://github.com/mctlhq/mctl-api/pull/57) | deps: bump k8s.io/api 0.32.3→0.36.1 | 6 d | **2026-05-25** |
| [mctl-api#58](https://github.com/mctlhq/mctl-api/pull/58) | deps: bump k8s.io/client-go 0.32.3→0.36.1 | 6 d | **2026-05-25** |
| [mctl-telegram#146](https://github.com/mctlhq/mctl-telegram/pull/146) | Enhance landing page UX: card animations, SVG icons | 2 d | 2026-05-29 |

### Stuck proposals

None — all proposals in terminal state.

---

## 7. Cluster Health

> **Skipped:** api.mctl.ai MCP connector not attached yet. See TODO at the bottom of this issue.

---

## 8. Errors During Run

| step | error | impact |
|------|-------|--------|
| Report destination | GitHub MCP restricted to `mctlhq/mctl-gitops`; write to `mctlhq/mctl-agents` denied | This issue posted to `mctl-gitops` — consistent with all prior daily reports since 2026-05-05 |
| Previous daily-report lookup | `list_issues --repo mctlhq/mctl-agents` denied (same scope restriction) | Diffed against mctlhq/mctl-gitops daily-report issues instead; no data loss |
| Telegram notification | Env vars `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` not set | Silently skipped (expected) |

---

## 9. TODO

- **Fix write scope:** Add `mctlhq/mctl-agents` (read + issue-write) to the GitHub MCP session's allowed-repositories list. Every daily-report run since 2026-05-05 has been misrouted to `mctlhq/mctl-gitops`.
- **Act on watch-list PRs** (mctl-api#55–58) — 4 dep-bump PRs will cross the 7-day stale threshold on 2026-05-25.
- **Resolve mctl-docs#17** (release 0.1.20 stuck 8 days) — confirm whether release-please auto-merge is configured for mctl-docs or if the PR requires manual merge.
- **Resolve mctl-gitops#217** (incident responder CronWorkflow, 8 days) — rebase or close if design has changed.
- **Resolve mctl-agent#20** (statefulset-replicas-mismatch skill, 8 days) — merge or close if superseded by newer skill work.
- **Resolve mctl-web#12** (redesign v3, 8 days) — confirm whether active or superseded by a different branch.
- **Attach the api.mctl.ai MCP connector** to this routine to unlock workflow-run counts (`mctl_list_workflows`), MinIO PVC % (`mctl_get_resource_usage`), per-service restart counts (`mctl_get_service_status`), and ArgoCD app sync state.
