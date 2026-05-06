# [daily-report] 2026-05-06 pipeline summary

## 1. Summary

13 proposals tracked across 8 repos. All proposals are in terminal state: **10 merged**, **3 rejected**, **0 in-progress**, **0 proposed**. No stuck proposals requiring escalation. One bot commit recorded today (full-run housekeeping). This is the **first run** of the daily-report agent — no previous report exists for diffing (GitHub API was also unavailable; see §8 Errors).

## 2. Proposal pipeline state

| repo | slug | status | pr | changed_since_yesterday |
|------|------|--------|----|------------------------|
| mctl-agents | tier3-pr-shepherd | merged | [#12](https://github.com/mctlhq/mctl-agents/pull/12) | — |
| mctl-openclaw | upgrade-to-2026-4-27 | rejected | [#15](https://github.com/mctlhq/mctl-openclaw/pull/15) | — |
| mctl-agent | sqlite-cve-patch | merged | [#9](https://github.com/mctlhq/mctl-agent/pull/9) | — |
| mctl-api | pgx-sqli-cve-2025-54236 | merged | [#40](https://github.com/mctlhq/mctl-api/pull/40) | — |
| mctl-api | chi-security-patch | merged | [#39](https://github.com/mctlhq/mctl-api/pull/39) | — |
| mctl-docs | fix-broken-mctl-ai-mcp-links | merged | [#6](https://github.com/mctlhq/mctl-docs/pull/6) | — |
| mctl-portal | scaffolder-path-traversal | rejected | [#10](https://github.com/mctlhq/mctl-portal/pull/10) | — |
| mctl-portal | scaffolder-secret-leak | rejected | [#12](https://github.com/mctlhq/mctl-portal/pull/12) | — |
| mctl-web | wrangler-upgrade-security | merged | [#9](https://github.com/mctlhq/mctl-web/pull/9) | — |
| mctl-gitops | argo-workflows-cve-patch-v2 | merged | [#85](https://github.com/mctlhq/mctl-gitops/pull/85) | — |
| mctl-gitops | eso-cve-patch | merged | [#87](https://github.com/mctlhq/mctl-gitops/pull/87) | — |
| mctl-gitops | argocd-informer-cache-patch | merged | [#90](https://github.com/mctlhq/mctl-gitops/pull/90) | — |
| mctl-gitops | grafana-sql-rce-patch | merged | [#89](https://github.com/mctlhq/mctl-gitops/pull/89) | — |

## 3. Pipeline diff (vs yesterday)

**First run — no previous daily-report found to diff against** (GitHub API unavailable; see §8).

Best-effort status from `.status.yaml` timestamps: all 13 proposals reached their terminal state on 2026-05-01 or 2026-05-02. None changed in the last 24 hours.

- **Newly merged (24h):** none (all merges occurred on 2026-05-01)
- **Newly rejected (24h):** none (all rejections occurred on 2026-05-01 / 2026-05-02)
- **Newly proposed (24h):** none
- **Still in-progress:** none
- **Still proposed:** none

## 4. Recent merged PRs (24h)

_Skipped: GitHub API unavailable (GITHUB_PAT token returned 401 Bad credentials). See §8._

From `git log --all --since="26 hours ago"` on the gitops repo, the following human-authored PRs were merged into `mctlhq/mctl-gitops` in the last 24h:

- `eb585ae` — Merge PR #126: `docs(labs): operator USER-GUIDE for eth-trading-intel Telegram bot`
- `d40ce5f` — Merge PR #125: `fix(labs): translate cron alert + onExit notification to Russian`
- `659787d` — Merge PR #124: `fix(labs): broadcast cron alerts to every allowFrom operator chat`
- `d237316` — Merge PR #123: `feat(labs): trading-intel 1.5` (fix(labs): unique JSON-RPC ids + SSE parser; URLError; 24h lookback; etc.)

## 5. Bot commits (24h)

From `git log --author="mctl-agents" --since="26 hours ago"` in `mctlhq/mctl-gitops`:

| hash | timestamp | message |
|------|-----------|---------|
| `0e58f80` | 2026-05-06 06:23:22 UTC | `chore(agents): full run 2026-05-06` |

1 commit. Normal housekeeping; no proposal state changes.

## 6. Detected problems

**None.** All proposals are in terminal state (merged or rejected). No proposals are stuck `in-progress` or lingering in `proposed`. Stale-PR check and stuck-proposal follow-up issue logic was skipped due to GitHub API unavailability — re-run with working credentials to enable deduplication checks.

No stand-alone issues opened this run.

## 7. Cluster health

Skipped: api.mctl.ai MCP connector not attached yet. See TODO at the bottom of this issue.

## 8. Errors during run

| step | error |
|------|-------|
| `gh auth status` | `gh` CLI not installed (not found in `$PATH`) |
| GitHub API (issues, PRs, search) | `GITHUB_PAT` present but returns HTTP 401 "Bad credentials" — token is expired or revoked |
| GitHub MCP tools (`mcp__github__*`) | Not registered in this session (ToolSearch returned no matches) |
| Previous daily-report lookup | Skipped — GitHub API unavailable |
| `gh issue create` (report posting) | Skipped — GitHub API unavailable; report written to `report.md` only |
| Stale-PR / stuck-proposal deduplication | Skipped — GitHub API unavailable |
| Telegram notification | Skipped — `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` not set |

**Impact:** Pipeline ran in read-only local mode. The report is complete from local git data but could not be posted as a GitHub issue. All GitHub-sourced sections (merged PRs org-wide, open PRs, previous report diff, follow-up issue creation) are unavailable until authentication is restored.

**Recommended fix:** Rotate the `GITHUB_PAT` secret in the agent runner environment. The token `ghp_GV5S6Z…` (40 chars) is present but rejected by the GitHub API.

## 9. TODO

Attach the api.mctl.ai MCP connector to this routine to unlock workflow-run counts (`mctl_list_workflows`), MinIO PVC % (`mctl_get_resource_usage`), per-service restart counts (`mctl_get_service_status`), and ArgoCD app sync state.
