> ⚠️ **Routing note:** This issue should be in `mctlhq/mctl-agents` but the GitHub MCP session is restricted to `mctlhq/mctl-gitops`. See §8 (Errors). Action required: add `mctlhq/mctl-agents` to the MCP allowed-repositories list.

---

## Summary

- **27 proposals** tracked across 9 repos (20 merged, 5 rejected, 2 `implemented`\*).
- **Busy 24h:** 4 agent-driven proposals went from inception to merged in a single day — `issue-67`, `issue-68`, `issue-69`, `issue-70` for `mctl-telegram`. A 5th (`issue-66`) moved from `implemented` → `merged`.
- **1 newly rejected:** `mctl-telegram/issue-71` — operator rejected at 08:54 UTC (no PR was ever opened).
- `issue-69` and `issue-70` show `implemented` in status files but **both PRs merged this morning** (08:43 and 08:51 UTC respectively, post-shepherd); status files will flip at next shepherd cycle (~10:30 UTC).
- **No stuck proposals.** No `in-progress` or `proposed` entries remain.
- **5 stale feature PRs** (>7 days, all pre-existing): follow-up comments posted to existing issues [#228](https://github.com/mctlhq/mctl-gitops/issues/228), [#229](https://github.com/mctlhq/mctl-gitops/issues/229), [#230](https://github.com/mctlhq/mctl-gitops/issues/230), [#231](https://github.com/mctlhq/mctl-gitops/issues/231), [#246](https://github.com/mctlhq/mctl-gitops/issues/246) + [#121](https://github.com/mctlhq/mctl-gitops/issues/121). 0 new stale-pr issues opened.
- **Diff baseline:** [mctlhq/mctl-gitops#245](https://github.com/mctlhq/mctl-gitops/issues/245) (2026-05-19 daily report).

---

## Proposal Pipeline State

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
| mctl-docs | fix-broken-mctl-ai-mcp-links | `merged` | [#6](https://github.com/mctlhq/mctl-docs/pull/6) | — |
| mctl-docs | mcp-agents-tools | `merged` | [#7](https://github.com/mctlhq/mctl-docs/pull/7) | — |
| mctl-gitops | argocd-informer-cache-patch | `merged` | [#90](https://github.com/mctlhq/mctl-gitops/pull/90) | — |
| mctl-gitops | argo-workflows-cve-patch-v2 | `merged` | [#85](https://github.com/mctlhq/mctl-gitops/pull/85) | — |
| mctl-gitops | eso-cve-patch | `merged` | [#87](https://github.com/mctlhq/mctl-gitops/pull/87) | — |
| mctl-gitops | grafana-sql-rce-patch | `merged` | [#89](https://github.com/mctlhq/mctl-gitops/pull/89) | — |
| mctl-openclaw | upgrade-to-2026-4-27 | `rejected` | [#15](https://github.com/mctlhq/mctl-openclaw/pull/15) | — |
| mctl-portal | scaffolder-path-traversal | `rejected` | [#10](https://github.com/mctlhq/mctl-portal/pull/10) | — |
| mctl-portal | scaffolder-secret-leak | `rejected` | [#12](https://github.com/mctlhq/mctl-portal/pull/12) | — |
| mctl-telegram | issue-59-add-observability-and-alerting-for-mctl | `merged` | [#61](https://github.com/mctlhq/mctl-telegram/pull/61) | — |
| mctl-telegram | issue-66-scalability-audit-and-hardening-for-100 | `merged` | [#72](https://github.com/mctlhq/mctl-telegram/pull/72) | ✓ implemented → merged |
| mctl-telegram | issue-67-build-browser-based-telegram-account-onb | `merged` | [#73](https://github.com/mctlhq/mctl-telegram/pull/73) | ✓ new → merged |
| mctl-telegram | issue-68-redesign-tg-mctl-ai-landing-page-for-cli | `merged` | [#74](https://github.com/mctlhq/mctl-telegram/pull/74) | ✓ new → merged |
| mctl-telegram | issue-69-improve-mobile-responsiveness-of-tg-mctl | `implemented`\* | [#75](https://github.com/mctlhq/mctl-telegram/pull/75) | ✓ new → implemented (PR merged 08:43) |
| mctl-telegram | issue-70-add-user-friendly-error-message-catalog | `implemented`\* | [#76](https://github.com/mctlhq/mctl-telegram/pull/76) | ✓ new → implemented (PR merged 08:51) |
| mctl-telegram | issue-71-test-smoke-test-log-build-version-git-sh | `rejected` | — | ✗ proposed → rejected |
| mctl-web | wrangler-upgrade-security | `merged` | [#9](https://github.com/mctlhq/mctl-web/pull/9) | — |

_\* Status file says `implemented`; GitHub confirms PRs merged this morning after the shepherd's last run at 08:31 UTC. Will flip to `merged` at next cycle._

---

## Pipeline Diff (vs [#245](https://github.com/mctlhq/mctl-gitops/issues/245) — 2026-05-19)

Yesterday: 23 proposals — merged(17), rejected(4), implemented(1), proposed(1)  
Today: 27 proposals — merged(20), rejected(5), implemented\*(2)

- **Newly merged** (3):
  - `mctl-telegram/issue-66` → [PR #72](https://github.com/mctlhq/mctl-telegram/pull/72) — was `implemented`, merged 22:31 UTC 2026-05-19
  - `mctl-telegram/issue-67` → [PR #73](https://github.com/mctlhq/mctl-telegram/pull/73) — new proposal, merged 08:18 UTC today (same-day turnaround)
  - `mctl-telegram/issue-68` → [PR #74](https://github.com/mctlhq/mctl-telegram/pull/74) — new proposal, merged 00:30 UTC today (same-day turnaround)
- **Newly rejected** (1):
  - `mctl-telegram/issue-71` — was `proposed` in #245, operator rejected at 08:54 UTC (tag: `requires_human_approval: true`, no PR was opened)
- **Newly implemented / same-day merges** (2):
  - `mctl-telegram/issue-69` → [PR #75](https://github.com/mctlhq/mctl-telegram/pull/75) — new, implemented 21:33 UTC yesterday, PR merged 08:43 today; status file shows `implemented` (shepherd lag)
  - `mctl-telegram/issue-70` → [PR #76](https://github.com/mctlhq/mctl-telegram/pull/76) — new, implemented 21:39 UTC yesterday, PR merged 08:51 today; status file shows `implemented` (shepherd lag)
- **Newly proposed**: none (all proposals this run moved immediately to implemented/merged/rejected)
- **Still in-progress**: none
- **Still proposed**: none

---

## Recent Merged PRs (24h)

27 PRs merged across the org since 2026-05-19 09:00 UTC:

| repo | PR | title | merged at |
|------|----|-------|-----------|
| mctlhq/mctl-telegram | [#85](https://github.com/mctlhq/mctl-telegram/pull/85) | chore(main): release 0.22.0 | 2026-05-20 08:53 |
| mctlhq/mctl-telegram | [#76](https://github.com/mctlhq/mctl-telegram/pull/76) | feat(agents): issue-70-add-user-friendly-error-message-catalog | 2026-05-20 08:51 |
| mctlhq/mctl-telegram | [#75](https://github.com/mctlhq/mctl-telegram/pull/75) | feat(agents): issue-69-improve-mobile-responsiveness-of-tg-mctl | 2026-05-20 08:43 |
| mctlhq/mctl-telegram | [#73](https://github.com/mctlhq/mctl-telegram/pull/73) | feat(agents): issue-67-build-browser-based-telegram-account-onb | 2026-05-20 08:18 |
| mctlhq/mctl-gitops | [#253](https://github.com/mctlhq/mctl-gitops/pull/253) | chore(labs): bump claude-remote to 0.1.6 | 2026-05-20 08:18 |
| mctlhq/mctl-telegram | [#84](https://github.com/mctlhq/mctl-telegram/pull/84) | chore(main): release 0.21.0 | 2026-05-19 23:27 |
| mctlhq/mctl-telegram | [#83](https://github.com/mctlhq/mctl-telegram/pull/83) | chore(oauth): diagnostic logging for DCR/authorize/token | 2026-05-19 23:26 |
| mctlhq/mctl-gitops | [#252](https://github.com/mctlhq/mctl-gitops/pull/252) | fix(labs): claude-remote 0.1.5 — seed settings.json | 2026-05-19 23:50 |
| mctlhq/mctl-gitops | [#251](https://github.com/mctlhq/mctl-gitops/pull/251) | fix(labs): claude-remote 0.1.4 — re-seed partial config | 2026-05-19 23:40 |
| mctlhq/mctl-gitops | [#250](https://github.com/mctlhq/mctl-gitops/pull/250) | fix(labs): claude-remote 0.1.3 — first-run config + device name | 2026-05-19 23:29 |
| mctlhq/mctl-telegram | [#74](https://github.com/mctlhq/mctl-telegram/pull/74) | feat(agents): issue-68-redesign-tg-mctl-ai-landing-page-for-cli | 2026-05-19 23:12 |
| mctlhq/mctl-gitops | [#249](https://github.com/mctlhq/mctl-gitops/pull/249) | fix(labs): claude-remote 0.1.2 — PTY for remote-control | 2026-05-19 23:08 |
| mctlhq/mctl-gitops | [#248](https://github.com/mctlhq/mctl-gitops/pull/248) | fix(labs): claude-remote 0.1.1 — remove --port flag | 2026-05-19 23:01 |
| mctlhq/mctl-gitops | [#247](https://github.com/mctlhq/mctl-gitops/pull/247) | feat(labs): add claude-remote service | 2026-05-19 22:54 |
| mctlhq/mctl-telegram | [#81](https://github.com/mctlhq/mctl-telegram/pull/81) | chore(main): release 0.20.1 | 2026-05-19 22:47 |
| mctlhq/mctl-telegram | [#80](https://github.com/mctlhq/mctl-telegram/pull/80) | fix(oauth): drop admin:users from public scopes_supported | 2026-05-19 22:44 |
| mctlhq/mctl-telegram | [#79](https://github.com/mctlhq/mctl-telegram/pull/79) | chore(main): release 0.20.0 | 2026-05-19 22:12 |
| mctlhq/mctl-telegram | [#72](https://github.com/mctlhq/mctl-telegram/pull/72) | feat(agents): issue-66-scalability-audit-and-hardening-for-100 | 2026-05-19 22:01 |
| mctlhq/mctl-telegram | [#78](https://github.com/mctlhq/mctl-telegram/pull/78) | chore(main): release 0.19.0 | 2026-05-19 21:55 |
| mctlhq/mctl-telegram | [#77](https://github.com/mctlhq/mctl-telegram/pull/77) | feat(oauth): allow chatgpt.com redirect_uri in implicit-host allowlist | 2026-05-19 21:54 |
| mctlhq/mctl-agents | [#25](https://github.com/mctlhq/mctl-agents/pull/25) | fix(shepherd): re-post @claude review after fix-up push | 2026-05-19 21:24 |
| mctlhq/mctl-gitops | [#244](https://github.com/mctlhq/mctl-gitops/pull/244) | chore(argo): bump mctl-agents cwfts to 1.12.1 | 2026-05-19 08:06 |
| mctlhq/mctl-agents | [#23](https://github.com/mctlhq/mctl-agents/pull/23) | feat(orchestrator): cap issues per poll cycle with --max-issues | 2026-05-19 08:00 |
| mctlhq/mctl-gitops | [#243](https://github.com/mctlhq/mctl-gitops/pull/243) | feat(argo): add issue-poll CronWorkflow, bump mctl-agents cwfts to 1.12.0 | 2026-05-19 05:22 |
| mctlhq/mctl-agents | [#22](https://github.com/mctlhq/mctl-agents/pull/22) | feat(orchestrator): add central issue-poller for agent:investigate | 2026-05-19 05:12 |
| mctlhq/mctl-agents | [#18](https://github.com/mctlhq/mctl-agents/pull/18) | feat: incident responder + migrate shepherd to @claude review | 2026-05-19 05:02 |
| mctlhq/mctl-telegram | [#64](https://github.com/mctlhq/mctl-telegram/pull/64) | chore(main): release 0.18.0 | 2026-05-19 04:48 |

---

## Bot Commits (26h window, author: mctl-agents)

```
16b7e3a  2026-05-20 08:31:32 +0000  chore(agents): shepherd run 2026-05-20
22acbd5  2026-05-20 00:31:26 +0000  chore(agents): shepherd run 2026-05-20
4a2aba7  2026-05-19 22:31:38 +0000  chore(agents): shepherd run 2026-05-19
1677016  2026-05-19 21:39:52 +0000  chore(agents): implement run 2026-05-19
0629718  2026-05-19 17:30:01 +0000  chore(agents): issue-poll 2026-05-19
28140ce  2026-05-19 08:43:38 +0000  chore(agents): investigate mctlhq/mctl-telegram/issues/71
30b6305  2026-05-19 08:26:59 +0000  chore(agents): implement issue-66-scalability-audit-and-hardening-for-100
```

7 commits: 3 shepherd status sweeps, 1 implement run, 1 issue-poll, 1 investigation, 1 implement. Pattern is healthy.

---

## Detected Problems

### Stale PRs (>7 days, no activity)

All 5 stale feature PRs are carry-overs from previous reports. **0 new issues opened.** Follow-up comments posted to existing issues.

| PR | title | days stale | dedup action |
|----|-------|------------|-------------|
| [mctl-agents#15](https://github.com/mctlhq/mctl-agents/pull/15) | feat(orchestrator): Tier 2 implementer agents | 11d | follow-up → [#228](https://github.com/mctlhq/mctl-gitops/issues/228#issuecomment-4496576206) |
| [mctl-agents#16](https://github.com/mctlhq/mctl-agents/pull/16) | feat(orchestrator): rotate mentor digests | 11d | follow-up → [#229](https://github.com/mctlhq/mctl-gitops/issues/229#issuecomment-4496576431) |
| [mctl-agents#17](https://github.com/mctlhq/mctl-agents/pull/17) | feat(mctl-docs): fallback to GitHub API | 11d | follow-up → [#230](https://github.com/mctlhq/mctl-gitops/issues/230#issuecomment-4496576594) |
| [mctl-api#47](https://github.com/mctlhq/mctl-api/pull/47) | feat(mcp): mctl_create_preview build-from-branch | 10d | follow-up → [#231](https://github.com/mctlhq/mctl-gitops/issues/231#issuecomment-4496576789) |
| [mctl-gitops#84](https://github.com/mctlhq/mctl-gitops/pull/84) | [wip] per-proposal claim mechanism | 20d | follow-up → [#246](https://github.com/mctlhq/mctl-gitops/issues/246#issuecomment-4496576924) |
| [mctl-portal#7](https://github.com/mctlhq/mctl-portal/pull/7) | feat(app): add /proposals page | 10d | follow-up → [#121](https://github.com/mctlhq/mctl-gitops/issues/121#issuecomment-4496577091) |

_Also visible but skipped (deps bump, conservative threshold): [mctl-api#51](https://github.com/mctlhq/mctl-api/pull/51) (9d, go-oidc bump)._

### Stuck proposals

None detected. Pipeline is in a healthy draining state.

---

## Cluster Health

Skipped: api.mctl.ai MCP connector not attached yet. See TODO at the bottom of this issue.

---

## Errors During Run

| step | error |
|------|-------|
| Write to `mctlhq/mctl-agents` | **Access denied** — MCP GitHub token is scoped to `mctlhq/mctl-gitops` only. This issue is filed in `mctlhq/mctl-gitops` as fallback. All stale-pr issues are also in `mctlhq/mctl-gitops`. |

**Fix required:** Add `mctlhq/mctl-agents` to the allowed-repositories list for the GitHub MCP token. Every daily-report run has been blocked from its intended home repo since at least 2026-05-05.

---

## TODO

Attach the `api.mctl.ai` MCP connector to this routine to unlock workflow-run counts (`mctl_list_workflows`), MinIO PVC % (`mctl_get_resource_usage`), per-service restart counts (`mctl_get_service_status`), and ArgoCD app sync state.

Also: **grant `mctlhq/mctl-agents` write access** to the GitHub MCP token used by this session.
