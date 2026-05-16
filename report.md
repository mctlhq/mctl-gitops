# [daily-report] 2026-05-16 pipeline summary

## 1. Summary

20 proposals tracked across 8 repos: **16 merged**, **4 rejected**, **0 in-progress**, **0 proposed** — pipeline remains fully flushed, no change from yesterday. mctl-telegram had an active 24 h sprint: **14 PRs merged** (hands-off onboarding + Dependabot + OAuth client tier) plus 1 mctl-gitops config follow-up; mctl-telegram is now live at `0.11.0`. 8 deploy-service workflow runs landed in the last 24 h (all labs, all `mashkovd`). Shepherd cron ran 5 times on its 2 h cadence — all succeeded. **mctl-gitops#84** ([wip] claim mechanism) remains idle for **16 days** — a stable stale-pr problem (second consecutive report); stand-alone issue creation blocked by MCP scope restriction (same as yesterday — see §8).

---

## 2. Proposal pipeline state

| repo | slug | status | pr | changed since yesterday |
|---|---|---|---|---|
| mctl-agents | tier3-pr-shepherd | merged | [#12](https://github.com/mctlhq/mctl-agents/pull/12) | — |
| mctl-agent | incident-auto-cleanup-phase1 | merged | [#11](https://github.com/mctlhq/mctl-agent/pull/11) | — |
| mctl-agent | incident-auto-cleanup-phase2 | merged | [#13](https://github.com/mctlhq/mctl-agent/pull/13) | — |
| mctl-agent | incident-auto-cleanup-phase3 | merged | [#12](https://github.com/mctlhq/mctl-agent/pull/12) | — |
| mctl-agent | incident-auto-cleanup-phase4-metrics | rejected | — | — |
| mctl-agent | incident-auto-cleanup-phase4a-metrics-wiring | merged | [#16](https://github.com/mctlhq/mctl-agent/pull/16) | — |
| mctl-agent | incident-auto-cleanup-phase4b-metrics-full | merged | [#17](https://github.com/mctlhq/mctl-agent/pull/17) | — |
| mctl-agent | sqlite-cve-patch | merged | [#9](https://github.com/mctlhq/mctl-agent/pull/9) | — |
| mctl-api | chi-security-patch | merged | [#39](https://github.com/mctlhq/mctl-api/pull/39) | — |
| mctl-api | pgx-sqli-cve-2025-54236 | merged | [#40](https://github.com/mctlhq/mctl-api/pull/40) | — |
| mctl-docs | fix-broken-mctl-ai-mcp-links | merged | [#6](https://github.com/mctlhq/mctl-docs/pull/6) | — |
| mctl-docs | mcp-agents-tools | merged | [#7](https://github.com/mctlhq/mctl-docs/pull/7) | — |
| mctl-gitops | argo-workflows-cve-patch-v2 | merged | [#85](https://github.com/mctlhq/mctl-gitops/pull/85) | — |
| mctl-gitops | argocd-informer-cache-patch | merged | [#90](https://github.com/mctlhq/mctl-gitops/pull/90) | — |
| mctl-gitops | eso-cve-patch | merged | [#87](https://github.com/mctlhq/mctl-gitops/pull/87) | — |
| mctl-gitops | grafana-sql-rce-patch | merged | [#89](https://github.com/mctlhq/mctl-gitops/pull/89) | — |
| mctl-openclaw | upgrade-to-2026-4-27 | rejected | [#15](https://github.com/mctlhq/mctl-openclaw/pull/15) | — |
| mctl-portal | scaffolder-path-traversal | rejected | [#10](https://github.com/mctlhq/mctl-portal/pull/10) | — |
| mctl-portal | scaffolder-secret-leak | rejected | [#12](https://github.com/mctlhq/mctl-portal/pull/12) | — |
| mctl-web | wrangler-upgrade-security | merged | [#9](https://github.com/mctlhq/mctl-web/pull/9) | — |

---

## 3. Pipeline diff (vs yesterday — 2026-05-15)

Previous report: local `report.md` (2026-05-15 run; never posted to GitHub — MCP scope blocked issue creation that day too).

- **Newly merged:** none (all proposals were already in terminal state)
- **Newly rejected:** none
- **Newly proposed:** none
- **Still in-progress:** none
- **Still proposed:** none

No proposal-level movement today. All flux is in the PR/deploy layer (mctl-telegram sprint, §4–5).

---

## 4. Recent merged PRs (last 24 h)

14 PRs merged since 2026-05-15T09:00Z (13 × mctl-telegram, 1 × mctl-gitops):

| # | repo | title | merged at |
|---|---|---|---|
| [#41](https://github.com/mctlhq/mctl-telegram/pull/41) | mctl-telegram | feat: hands-off client onboarding — open auto-approve + daily digest | 2026-05-16T08:39Z |
| [#33](https://github.com/mctlhq/mctl-telegram/pull/33) | mctl-telegram | fix: add Dependabot and CodeQL for Scorecard compliance | 2026-05-16T01:41Z |
| [#32](https://github.com/mctlhq/mctl-telegram/pull/32) | mctl-telegram | fix: pin GHA actions to SHA and restrict workflow permissions | 2026-05-16T01:30Z |
| [#31](https://github.com/mctlhq/mctl-telegram/pull/31) | mctl-telegram | feat(oauth): client scope tier + DB-backed client management | 2026-05-16T01:14Z |
| [#27](https://github.com/mctlhq/mctl-telegram/pull/27) | mctl-telegram | feat(oauth): in-browser enable_access flow for MTProto session onboarding | 2026-05-16T00:22Z |
| [#30](https://github.com/mctlhq/mctl-telegram/pull/30) | mctl-telegram | ci: fix claude-review to actually post review findings | 2026-05-15T23:46Z |
| [#29](https://github.com/mctlhq/mctl-telegram/pull/29) | mctl-telegram | chore: document squash-merge-only convention | 2026-05-15T23:41Z |
| [#28](https://github.com/mctlhq/mctl-telegram/pull/28) | mctl-telegram | ci: add Claude-powered automated PR review | 2026-05-15T23:10Z |
| [#26](https://github.com/mctlhq/mctl-telegram/pull/26) | mctl-telegram | fix: add unsafe-eval to CSP for Telegram widget | 2026-05-15T19:49Z |
| [#25](https://github.com/mctlhq/mctl-telegram/pull/25) | mctl-telegram | fix: authorize page dark mode and CSP for Telegram widget | 2026-05-15T19:39Z |
| [#24](https://github.com/mctlhq/mctl-telegram/pull/24) | mctl-telegram | fix: update connectors URL to claude.ai/customize/connectors | 2026-05-15T19:35Z |
| [#23](https://github.com/mctlhq/mctl-telegram/pull/23) | mctl-telegram | fix(web): landing dark mode contrast — lead text + inline code | 2026-05-15T18:54Z |
| [#214](https://github.com/mctlhq/mctl-gitops/pull/214) | mctl-gitops | feat(mctl-telegram): switch to local-jwt auth, wire TELEGRAM_LOGIN_BOT_TOKEN | 2026-05-15T18:43Z |

*(#21 and #22 were captured in yesterday's report.)*

---

## 5. Bot commits (last 24 h)

| hash | timestamp | message |
|---|---|---|
| `e66c53c` | 2026-05-16T00:27:19Z | chore(agents): full run 2026-05-16 |

---

## 6. Detected problems

### Stable stale PR — mctl-gitops#84 (now 16 days)

[mctlhq/mctl-gitops#84](https://github.com/mctlhq/mctl-gitops/pull/84) — **[wip] feat(agents): per-proposal claim mechanism for parallel implementer**

- Last updated: 2026-04-30 (16 days ago)
- Qualifies for `[stale-pr]` issue (>7 days, stable: present in 2026-05-15 report)
- **Stand-alone issue creation blocked** — MCP session restricted to `mctlhq/mctl-gitops`; cannot write issues to `mctlhq/mctl-agents`. See §8.
- **Recommended action:** rebase + push a commit if still active, or close with a note if superseded.

### Open PRs stale >48 h (watch list)

11 PRs with no update in >48 h. Those approaching or at the 7-day threshold:

| # | repo | title | last updated | days stale |
|---|---|---|---|---|
| [#15](https://github.com/mctlhq/mctl-agents/pull/15) | mctl-agents | feat(orchestrator): Tier 2 implementer agents | 2026-05-09 | 7 d |
| [#16](https://github.com/mctlhq/mctl-agents/pull/16) | mctl-agents | feat(orchestrator): rotate mentor digests >8 weeks | 2026-05-09 | 7 d |
| [#17](https://github.com/mctlhq/mctl-agents/pull/17) | mctl-agents | feat(mctl-docs): fallback to GitHub API when sibling clones absent | 2026-05-09 | 7 d |
| [#7](https://github.com/mctlhq/mctl-portal/pull/7) | mctl-portal | feat(app): add /proposals page for agents review | 2026-05-10 | 6 d |
| [#47](https://github.com/mctlhq/mctl-api/pull/47) | mctl-api | feat(mcp): mctl_create_preview — build from branch support | 2026-05-10 | 6 d |
| [#12](https://github.com/mctlhq/mctl-web/pull/12) | mctl-web | feat: redesign v3 | 2026-05-10 | 6 d |
| [#53](https://github.com/mctlhq/mctl-api/pull/53) | mctl-api | deps: bump k8s.io/api 0.32.3→0.36.0 | 2026-05-11 | 5 d |
| [#52](https://github.com/mctlhq/mctl-api/pull/52) | mctl-api | deps: bump mcp-go 0.46.0→0.52.0 | 2026-05-11 | 5 d |
| [#51](https://github.com/mctlhq/mctl-api/pull/51) | mctl-api | deps: bump go-oidc/v3 3.17.0→3.18.0 | 2026-05-11 | 5 d |
| [#50](https://github.com/mctlhq/mctl-api/pull/50) | mctl-api | deps: bump k8s.io/client-go 0.32.3→0.36.0 | 2026-05-11 | 5 d |

mctl-agents #15/16/17 are at exactly 7 days today; `[stale-pr]` issues will be opened on the next run if still inactive (threshold: >7 days). mctl-api Dependabot PRs reach threshold on 2026-05-18.

---

## 7. Cluster health

api.mctl.ai MCP connector is **attached and responding**.

### Services (10 deployed)

| team | service | image tag | host |
|---|---|---|---|
| admins | mctl-docs | 0.1.20 | docs.mctl.ai |
| admins | mctl-web | 4.7.0 | mctl.me |
| admins | openclaw | 2026.5.14-beta.1 | admins-openclaw.mctl.ai |
| labs | kuptsi-app | 0.2.12 | labs-kuptsi-app.mctl.ai |
| labs | **mctl-telegram** | **0.11.0** ↑ *(was 0.8.2 yesterday)* | tg.mctl.ai |
| labs | openclaw | 2026.5.14-beta.1 | labs-openclaw.mctl.ai |
| labs | pelican-proxy | 0.11.0 | labs-pelican-proxy.mctl.ai |
| labs | pelican-proxy-pr-36 *(preview)* | preview.37 | pelican-proxy-pr-36.mctl.ai |
| labs | trading-data | 0.2.4 | — |
| ovk | openclaw | 2026.5.14-beta.1 | ovk-openclaw.mctl.ai |

### Workflow runs (last 24 h)

8 `deploy-service` runs since 2026-05-15T09:00Z, all team `labs`, all by `mashkovd`. No rollbacks or failures in window. Timings correlate tightly with mctl-telegram PR merges.

| workflow | timestamp |
|---|---|
| deploy-service-b304fb3a | 2026-05-16T08:40Z |
| deploy-service-c03f3266 | 2026-05-16T01:15Z |
| deploy-service-712cb3bb | 2026-05-16T00:31Z |
| deploy-service-f912ec61 | 2026-05-15T21:10Z |
| deploy-service-7370d2d6 | 2026-05-15T20:40Z |
| deploy-service-8b81747c | 2026-05-15T19:49Z |
| deploy-service-1674df29 | 2026-05-15T19:40Z |
| deploy-service-8c551fcf | 2026-05-15T18:54Z |

### Agent cron runs (last 24 h)

| operation | timestamp | status |
|---|---|---|
| mctl-agents-shepherd | 2026-05-16T08:30Z | succeeded |
| mctl-agents-shepherd | 2026-05-16T06:30Z | succeeded |
| mctl-agents-shepherd | 2026-05-16T04:30Z | succeeded |
| mctl-agents-shepherd | 2026-05-16T02:30Z | succeeded |
| mctl-agents-shepherd | 2026-05-16T00:30Z | succeeded |
| mctl-agents-daily | 2026-05-16T00:00Z | succeeded |
| mctl-agents-shepherd | 2026-05-15T22:30Z | succeeded |
| mctl-agents-shepherd | 2026-05-15T20:30Z | succeeded |
| mctl-agents-shepherd | 2026-05-15T18:30Z | succeeded |
| mctl-agents-shepherd | 2026-05-15T16:30Z | succeeded |

Shepherd running on 2 h cadence — all 5 runs since midnight succeeded. `mctl-agents-daily` ran at 00:00 UTC (this is a second/manual 09:00 UTC invocation of the same routine).

*Per-service restart counts and MinIO PVC % not pulled this run (would require per-service `mctl_get_service_status` / `mctl_get_resource_usage` calls). ArgoCD sync state not checked. These are available for enrichment on a future run.*

---

## 8. Errors during run

| step | error | impact |
|---|---|---|
| Previous daily-report lookup | `mcp__github__list_issues` denied for `mctlhq/mctl-agents` (MCP scope = `mctlhq/mctl-gitops` only); used `search_issues` as fallback — confirmed 0 existing daily-report issues | No data lost; diff based on local `report.md` instead |
| Stand-alone issue creation (`[stale-pr]` for mctl-gitops#84) | `mcp__github__issue_write` denied for `mctlhq/mctl-agents` | Issue not posted — second consecutive failure |
| Daily-report issue creation | `mcp__github__issue_write` denied for `mctlhq/mctl-agents` | Report saved to local `report.md` only |
| `gh` CLI | Not available in `$PATH` | No gh fallback |
| Telegram | `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` not set | Silently skipped |

**Persistent blocker:** The GitHub MCP session must be expanded to include `mctlhq/mctl-agents` (issue write + comment write) before this routine can post daily-report issues or stand-alone follow-up issues. This has now failed on two consecutive runs (2026-05-15, 2026-05-16).

---

## 9. TODO

- **[P0 blocker]** Expand GitHub MCP session scope to include `mctlhq/mctl-agents` so daily-report issues, `[stale-pr]`, and `[stuck-proposal]` issues can be posted. Currently blocked on two consecutive runs.
- Enrich next run with `mctl_get_service_status` (per-service restart counts) and `mctl_get_resource_usage` (MinIO PVC %) — connector is confirmed attached.
- mctl-agents #15/16/17 cross the 7-day stale-pr threshold on **2026-05-17** — open `[stale-pr]` issues then if still inactive.
- mctl-api Dependabot PRs #50–53 + mctl-portal #7 + mctl-web #12 cross threshold on **2026-05-17/18**.
- Attach the `api.mctl.ai` MCP connector ArgoCD app sync state query to future runs.
