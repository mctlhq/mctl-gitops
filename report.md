## Summary

- **42 proposals** tracked across 9 repos — 35 merged, 5 rejected, 3 accepted (awaiting implementation), 1 implemented (PR open for review).
- **50 PRs merged in the last 24 h** across the org — driven by a major pr-steward rollout into mctl-telegram/mctl-gitops and a rapid mctl-telegram release series (v0.29.0 → v0.29.4 in a single day).
- **2 proposals newly merged today**: `mctl-design/issue-4` and `mctl-design/issue-6`.
- **1 implementer failure noted**: `mctl-design/issue-3` implementer run produced no commits; proposal reverted to `accepted`.
- **7 open PRs stale >7 d** (no activity since before 2026-05-15); flagged below. No stuck-proposal thresholds triggered (no `in-progress` or `proposed` proposals exist).
- **First run** — no diff against a prior daily-report issue; all proposals shown as-is.

---

## Proposal pipeline state

| repo | slug | status | pr | changed (24 h) |
|---|---|---|---|---|
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
| mctl-design | issue-3-change-the-storybook-overview-brand-icon | **accepted** | — | ✓ implementer failed→reverted |
| mctl-design | issue-4-rename-storybook-brand-title-to-mctl-ui | merged | [#5](https://github.com/mctlhq/mctl-design/pull/5) | ✓ newly merged |
| mctl-design | issue-6-align-storybook-page-title-og-title-with | merged | [#7](https://github.com/mctlhq/mctl-design/pull/7) | ✓ newly merged |
| mctl-docs | fix-broken-mctl-ai-mcp-links | merged | [#6](https://github.com/mctlhq/mctl-docs/pull/6) | — |
| mctl-docs | mcp-agents-tools | merged | [#7](https://github.com/mctlhq/mctl-docs/pull/7) | — |
| mctl-gitops | argo-workflows-cve-patch-v2 | merged | [#85](https://github.com/mctlhq/mctl-gitops/pull/85) | — |
| mctl-gitops | argocd-informer-cache-patch | merged | [#90](https://github.com/mctlhq/mctl-gitops/pull/90) | — |
| mctl-gitops | eso-cve-patch | merged | [#87](https://github.com/mctlhq/mctl-gitops/pull/87) | — |
| mctl-gitops | grafana-sql-rce-patch | merged | [#89](https://github.com/mctlhq/mctl-gitops/pull/89) | — |
| mctl-openclaw | upgrade-to-2026-4-27 | rejected | [#15](https://github.com/mctlhq/mctl-openclaw/pull/15) | — |
| mctl-portal | scaffolder-path-traversal | rejected | [#10](https://github.com/mctlhq/mctl-portal/pull/10) | — |
| mctl-portal | scaffolder-secret-leak | rejected | [#12](https://github.com/mctlhq/mctl-portal/pull/12) | — |
| mctl-telegram | issue-154-nav-replace-github-text-link-with-a-gith | **implemented** | [#157](https://github.com/mctlhq/mctl-telegram/pull/157) _(open)_ | ✓ newly implemented |
| mctl-telegram | issue-158-non-deterministic-safety-block-on-get-me | **accepted** | — | ✓ new today |
| mctl-telegram | issue-159-live-send-unusable-when-prepare-send-mes | **accepted** | — | ✓ new today |
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
| mctl-web | wrangler-upgrade-security | merged | [#9](https://github.com/mctlhq/mctl-web/pull/9) | — |

---

## Pipeline diff (vs yesterday)

**First run — no previous daily-report baseline exists.** Changes observed within the last 24 h by `updated_at`:

- **Newly merged**: `mctl-design/issue-4` (PR [mctl-design#5](https://github.com/mctlhq/mctl-design/pull/5) merged 2026-05-22T19:08Z), `mctl-design/issue-6` (PR [mctl-design#7](https://github.com/mctlhq/mctl-design/pull/7) merged 2026-05-22T22:35Z)
- **Newly implemented (PR open)**: `mctl-telegram/issue-154` → PR [mctl-telegram#157](https://github.com/mctlhq/mctl-telegram/pull/157) pushed 2026-05-22T23:34Z, awaiting human review (`requires_human_approval: true`)
- **Newly accepted**: `mctl-telegram/issue-158` and `mctl-telegram/issue-159` (both accepted 2026-05-23T09:15Z by mashkovd)
- **Implementer failure → reverted**: `mctl-design/issue-3` — implementer ran at 2026-05-22T16:03Z but produced no commits; status reverted from in-progress to `accepted`
- **Still accepted (awaiting implementer)**: `mctl-design/issue-3`, `mctl-telegram/issue-158`, `mctl-telegram/issue-159`
- **Still implemented (awaiting human review)**: `mctl-telegram/issue-154` (open PR [#157](https://github.com/mctlhq/mctl-telegram/pull/157))

---

## Recent merged PRs (24 h)

50 PRs merged across the org between 2026-05-22T14:29Z and 2026-05-23T08:35Z:

| repo | PR | title | merged at |
|---|---|---|---|
| mctl-claude-remote | [#17](https://github.com/mctlhq/mctl-claude-remote/pull/17) | feat: detect wedged event loop in healthz + anti-poll-loop guidance | 2026-05-23T08:35Z |
| mctl-telegram | [#161](https://github.com/mctlhq/mctl-telegram/pull/161) | ci: auto-apply agents:intake label on new issues | 2026-05-23T08:33Z |
| mctl-gitops | [#289](https://github.com/mctlhq/mctl-gitops/pull/289) | chore(labs): bump claude-remote to 0.6.0 | 2026-05-23T08:28Z |
| mctl-gitops | [#288](https://github.com/mctlhq/mctl-gitops/pull/288) | chore(claude-remote): bump image to 0.5.0 | 2026-05-23T07:40Z |
| mctl-claude-remote | [#14](https://github.com/mctlhq/mctl-claude-remote/pull/14) | feat: resume prior session on restart | 2026-05-23T07:36Z |
| mctl-telegram | [#151](https://github.com/mctlhq/mctl-telegram/pull/151) | fix(docs): mark Local Bridge mode as beta-available in ROADMAP | 2026-05-23T07:23Z |
| mctl-telegram | [#156](https://github.com/mctlhq/mctl-telegram/pull/156) | chore(main): release 0.29.4 | 2026-05-22T23:31Z |
| mctl-telegram | [#155](https://github.com/mctlhq/mctl-telegram/pull/155) | fix: change send_message default mode from draft to send | 2026-05-22T23:30Z |
| mctl-agents | [#31](https://github.com/mctlhq/mctl-agents/pull/31) | chore: stop referencing codex for the PR review gate | 2026-05-22T23:21Z |
| mctl-trading-data | [#1](https://github.com/mctlhq/mctl-trading-data/pull/1) | docs: PR review trigger @codex -> @claude review | 2026-05-22T23:19Z |
| mctl-gitops | [#287](https://github.com/mctlhq/mctl-gitops/pull/287) | chore(agents-state): codex-review references -> @claude review | 2026-05-22T23:18Z |
| mctl-telegram | [#153](https://github.com/mctlhq/mctl-telegram/pull/153) | chore(main): release 0.29.3 | 2026-05-22T23:07Z |
| mctl-telegram | [#152](https://github.com/mctlhq/mctl-telegram/pull/152) | fix: remove destructiveHint from send_message for ChatGPT compatibility | 2026-05-22T23:06Z |
| mctl-gitops | [#286](https://github.com/mctlhq/mctl-gitops/pull/286) | fix(claude-remote): cap steward tick timeout below schedule interval | 2026-05-22T22:55Z |
| mctl-telegram | [#149](https://github.com/mctlhq/mctl-telegram/pull/149) | fix(mcp): remove prepare_send_message tool, raise confirmation TTL | 2026-05-22T22:44Z |
| mctl-telegram | [#150](https://github.com/mctlhq/mctl-telegram/pull/150) | chore(main): release 0.29.2 | 2026-05-22T22:48Z |
| mctl-design | [#7](https://github.com/mctlhq/mctl-design/pull/7) | feat(agents): issue-6-align-storybook-page-title-og-title-with | 2026-05-22T22:35Z |
| mctl-gitops | [#284](https://github.com/mctlhq/mctl-gitops/pull/284) | feat(claude-remote): enable built-in pr-steward scheduler | 2026-05-22T22:27Z |
| mctl-claude-remote | [#12](https://github.com/mctlhq/mctl-claude-remote/pull/12) | feat(pr-steward): in-pod scheduler with precheck-gated headless ticks | 2026-05-22T22:14Z |
| mctl-gitops | [#283](https://github.com/mctlhq/mctl-gitops/pull/283) | feat: onboard mctl-docs to pr-steward when-green | 2026-05-22T22:09Z |
| mctl-telegram | [#148](https://github.com/mctlhq/mctl-telegram/pull/148) | chore(main): release 0.29.1 | 2026-05-22T22:05Z |
| mctl-telegram | [#147](https://github.com/mctlhq/mctl-telegram/pull/147) | fix(mcp): make confirmation_id optional in send_message | 2026-05-22T22:03Z |
| mctl-gitops | [#282](https://github.com/mctlhq/mctl-gitops/pull/282) | feat: deploy steward 0.3.0 with per-repo merge_mode | 2026-05-22T21:52Z |
| mctl-gitops | [#281](https://github.com/mctlhq/mctl-gitops/pull/281) | feat(labs): steward owns mctl-telegram claude/* PRs (squash auto-merge) | 2026-05-22T21:43Z |
| mctl-claude-remote | [#11](https://github.com/mctlhq/mctl-claude-remote/pull/11) | feat(pr-steward): per-repo merge_mode/merge_method override | 2026-05-22T21:36Z |
| mctl-gitops | [#280](https://github.com/mctlhq/mctl-gitops/pull/280) | feat: activate Stage-2 unattended merge for mctl-design | 2026-05-22T21:25Z |
| mctl-gitops | [#279](https://github.com/mctlhq/mctl-gitops/pull/279) | fix: raise CPU limits on throttling services + widen flap cooldown | 2026-05-22T20:55Z |
| mctl-agent | [#23](https://github.com/mctlhq/mctl-agent/pull/23) | refactor(agent): pass resolution reason through to mctl-api | 2026-05-22T20:32Z |
| mctl-gitops | [#278](https://github.com/mctlhq/mctl-gitops/pull/278) | chore(mctl-agent): make AM_RECONCILE_ENABLED explicit | 2026-05-22T20:32Z |
| mctl-claude-remote | [#10](https://github.com/mctlhq/mctl-claude-remote/pull/10) | fix: health probe tolerance + faster restart | 2026-05-22T20:25Z |
| mctl-gitops | [#277](https://github.com/mctlhq/mctl-gitops/pull/277) | fix(labs): widen claude-remote liveness probe window | 2026-05-22T19:22Z |
| mctl-agent | [#21](https://github.com/mctlhq/mctl-agent/pull/21) | fix(poller): propagate self-cleanup resolves to mctl-api | 2026-05-22T19:19Z |
| mctl-agent | [#22](https://github.com/mctlhq/mctl-agent/pull/22) | ci: add Claude PR review workflow | 2026-05-22T19:11Z |
| mctl-design | [#5](https://github.com/mctlhq/mctl-design/pull/5) | feat(agents): issue-4-rename-storybook-brand-title-to-mctl-ui | 2026-05-22T19:08Z |
| mctl-gitops | [#275](https://github.com/mctlhq/mctl-gitops/pull/275) | chore(labs): bump claude-remote image 0.2.2 -> 0.2.3 | 2026-05-22T16:02Z |
| mctl-claude-remote | [#8](https://github.com/mctlhq/mctl-claude-remote/pull/8) | fix(pr-steward): App-token-safe check status, never hang | 2026-05-22T15:58Z |
| mctl-telegram | [#142](https://github.com/mctlhq/mctl-telegram/pull/142) | chore(main): release 0.29.0 | 2026-05-22T15:52Z |
| mctl-gitops | [#274](https://github.com/mctlhq/mctl-gitops/pull/274) | chore(agents): bump mctl-agents CWFTs to 1.13.0 | 2026-05-22T15:50Z |
| mctl-claude-remote | [#9](https://github.com/mctlhq/mctl-claude-remote/pull/9) | ci: add Claude PR review workflow | 2026-05-22T15:50Z |
| mctl-telegram | [#141](https://github.com/mctlhq/mctl-telegram/pull/141) | feat(ingress): Layer-1 sticky routing manifests + acceptance gate | 2026-05-22T15:42Z |
| mctl-design | [#2](https://github.com/mctlhq/mctl-design/pull/2) | feat(ci): main-merge deploy to ui.mctl.ai + approve-when-clean review | 2026-05-22T15:33Z |
| mctl-gitops | [#273](https://github.com/mctlhq/mctl-gitops/pull/273) | fix(claude-remote): clean steward log via tail sidecar | 2026-05-22T15:29Z |
| mctl-gitops | [#272](https://github.com/mctlhq/mctl-gitops/pull/272) | feat(labs): add mctl-design to pr-steward repos (Stage-0 dry pilot) | 2026-05-22T15:25Z |
| mctl-gitops | [#271](https://github.com/mctlhq/mctl-gitops/pull/271) | feat(agents): read-only reconcile CWFT + suspended CronWorkflow | 2026-05-22T15:25Z |
| mctl-gitops | [#270](https://github.com/mctlhq/mctl-gitops/pull/270) | chore(agents): skip mctl-design in shepherd CWFT + refresh intake docs | 2026-05-22T15:24Z |
| mctl-telegram | [#140](https://github.com/mctlhq/mctl-telegram/pull/140) | chore(main): release 0.28.1 | 2026-05-22T14:41Z |
| mctl-agents | [#30](https://github.com/mctlhq/mctl-agents/pull/30) | feat(shepherd): read-only --reconcile mode for skip-listed repos | 2026-05-22T14:40Z |
| mctl-agents | [#29](https://github.com/mctlhq/mctl-agents/pull/29) | feat(poller): retarget intake label to agents:intake | 2026-05-22T14:40Z |
| mctl-telegram | [#139](https://github.com/mctlhq/mctl-telegram/pull/139) | chore: release 0.28.1 | 2026-05-22T14:39Z |
| mctl-telegram | [#137](https://github.com/mctlhq/mctl-telegram/pull/137) | docs(web): mark audit log + 90-day sweeper as shipped | 2026-05-22T14:29Z |

---

## Bot commits (24 h)

`git log --author="mctl-agents" --since="26 hours ago"`:

| hash | timestamp | subject |
|---|---|---|
| `e49fd0e` | 2026-05-23T08:55Z | chore(agents): issue-poll 2026-05-23 |
| `9ce2877` | 2026-05-23T00:46Z | chore(agents): reconcile status 2026-05-23 |
| `d16f4f2` | 2026-05-22T23:34Z | chore(agents): implement issue-154-nav-replace-github-text-link-with-a-gith |
| `14b3f5d` | 2026-05-22T23:12Z | chore(agents): investigate mctlhq/mctl-telegram#154 |
| `60140c2` | 2026-05-22T19:24Z | chore(agents): implement issue-6-align-storybook-page-title-og-title-with |
| `10a1667` | 2026-05-22T19:21Z | chore(agents): investigate mctlhq/mctl-design#6 |
| `c46beaa` | 2026-05-22T16:13Z | chore(agents): implement issue-4-rename-storybook-brand-title-to-mctl-ui |
| `ace7e77` | 2026-05-22T16:10Z | chore(agents): investigate mctlhq/mctl-design#4 |
| `7aa4931` | 2026-05-22T16:03Z | chore(agents): implement issue-3-change-the-storybook-overview-brand-icon |
| `86d89fa` | 2026-05-22T15:57Z | chore(agents): investigate mctlhq/mctl-design#3 |

---

## Detected problems

### Open PRs stale >7 d (no activity since before 2026-05-16)

The following open PRs have not been updated in more than 7 days. No existing `stale-pr` issues found in `mctlhq/mctl-agents`. **This is the first run — standalone stale-pr issues could not be created due to a tool access constraint** (see Errors section); listed here for manual triage.

| repo | PR | title | last updated | days stale |
|---|---|---|---|---|
| mctl-api | [#51](https://github.com/mctlhq/mctl-api/pull/51) | deps: bump go-oidc/v3 from 3.17.0 to 3.18.0 | 2026-05-11 | 12 d |
| mctl-portal | [#7](https://github.com/mctlhq/mctl-portal/pull/7) | feat(app): add /proposals page for agents review | 2026-05-10 | 13 d |
| mctl-api | [#47](https://github.com/mctlhq/mctl-api/pull/47) | feat(mcp): mctl_create_preview — build from branch support | 2026-05-10 | 13 d |
| mctl-agents | [#15](https://github.com/mctlhq/mctl-agents/pull/15) | feat(orchestrator): Tier 2 implementer agents | 2026-05-09 | 14 d |
| mctl-agents | [#17](https://github.com/mctlhq/mctl-agents/pull/17) | feat(mctl-docs): fallback to GitHub API when sibling clones absent | 2026-05-09 | 14 d |
| mctl-agents | [#16](https://github.com/mctlhq/mctl-agents/pull/16) | feat(orchestrator): rotate mentor digests older than 8 weeks | 2026-05-09 | 14 d |
| mctl-gitops | [#84](https://github.com/mctlhq/mctl-gitops/pull/84) | [wip] feat(agents): per-proposal claim mechanism for parallel implementers | 2026-04-30 | 23 d |

### Implementer failure (notable, not yet threshold-crossing)

- `mctl-design/issue-3-change-the-storybook-overview-brand-icon` — implementer ran at 2026-05-22T16:03Z, pushed no commits, status reverted to `accepted`. First observed failure for this proposal; a stuck-proposal issue will be opened if it fails again on the next report.

---

## Cluster health

Skipped: api.mctl.ai MCP connector not attached yet. See TODO at the bottom of this issue.

---

## Errors during run

- **`gh` CLI not available** (`command not found`). This session has no `gh` binary; GitHub interactions were routed through the `mcp__github__*` tools instead.
- **MCP write scope restricted to `mctlhq/mctl-gitops`**: attempts to create standalone `stale-pr` issues in `mctlhq/mctl-agents` are blocked. The 7 stale PRs identified above require manual triage or a session reconfigured with write access to `mctlhq/mctl-agents`. To fix: add `mctlhq/mctl-agents` to the allowed-repositories list for this Claude Code web session.
- **Previous daily-report lookup via `mcp__github__list_issues` for `mctlhq/mctl-agents` was denied** for the same reason; `mcp__github__search_issues` was used as a fallback and confirmed 0 prior daily-report issues exist (this is the first run).

---

## TODO

Attach the api.mctl.ai MCP connector to this routine to unlock workflow-run counts (`mctl_list_workflows`), MinIO PVC % (`mctl_get_resource_usage`), per-service restart counts (`mctl_get_service_status`), and ArgoCD app sync state.
