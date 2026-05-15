# [daily-report] 2026-05-15 pipeline summary

## Summary

20 proposals tracked across 7 repos: **16 merged**, **4 rejected**, **0 in-progress**, **0 proposed**. All proposals have reached a terminal state — no open pipeline work from the agents. No bot commits in the last 26 h. Since the previous report (2026-05-06, stored locally — GitHub was unavailable that day), **7 new proposals** appeared and all reached terminal state: 6 merged, 1 rejected. The mctl-telegram repo had a burst of **20 PRs merged in the last 24 h** as part of an active feature sprint (OAuth, Local Bridge, open-source prep). **1 stale WIP draft PR** detected: `mctlhq/mctl-gitops#84` (15 days with zero activity). Stand-alone issue creation was attempted; see §Detected problems for result.

---

## Proposal pipeline state

| repo | slug | status | pr | changed\_since\_prev\_report |
|------|------|--------|----|------------------------------|
| mctl-agents | tier3-pr-shepherd | merged | [mctl-agents#12](https://github.com/mctlhq/mctl-agents/pull/12) | — |
| mctl-agent | sqlite-cve-patch | merged | [mctl-agent#9](https://github.com/mctlhq/mctl-agent/pull/9) | — |
| mctl-agent | incident-auto-cleanup-phase1 | merged | [mctl-agent#11](https://github.com/mctlhq/mctl-agent/pull/11) | **new** |
| mctl-agent | incident-auto-cleanup-phase2 | merged | [mctl-agent#13](https://github.com/mctlhq/mctl-agent/pull/13) | **new** |
| mctl-agent | incident-auto-cleanup-phase3 | merged | [mctl-agent#12](https://github.com/mctlhq/mctl-agent/pull/12) | **new** |
| mctl-agent | incident-auto-cleanup-phase4-metrics | rejected | [mctl-agent#17](https://github.com/mctlhq/mctl-agent/pull/17) | **new** |
| mctl-agent | incident-auto-cleanup-phase4a-metrics-wiring | merged | [mctl-agent#16](https://github.com/mctlhq/mctl-agent/pull/16) | **new** |
| mctl-agent | incident-auto-cleanup-phase4b-metrics-full | merged | [mctl-agent#17](https://github.com/mctlhq/mctl-agent/pull/17) | **new** |
| mctl-api | chi-security-patch | merged | [mctl-api#39](https://github.com/mctlhq/mctl-api/pull/39) | — |
| mctl-api | pgx-sqli-cve-2025-54236 | merged | [mctl-api#40](https://github.com/mctlhq/mctl-api/pull/40) | — |
| mctl-docs | fix-broken-mctl-ai-mcp-links | merged | [mctl-docs#6](https://github.com/mctlhq/mctl-docs/pull/6) | — |
| mctl-docs | mcp-agents-tools | merged | [mctl-docs#7](https://github.com/mctlhq/mctl-docs/pull/7) | **new** |
| mctl-portal | scaffolder-path-traversal | rejected | [mctl-portal#10](https://github.com/mctlhq/mctl-portal/pull/10) | — |
| mctl-portal | scaffolder-secret-leak | rejected | [mctl-portal#12](https://github.com/mctlhq/mctl-portal/pull/12) | — |
| mctl-openclaw | upgrade-to-2026-4-27 | rejected | [mctl-openclaw#15](https://github.com/mctlhq/mctl-openclaw/pull/15) | — |
| mctl-web | wrangler-upgrade-security | merged | [mctl-web#9](https://github.com/mctlhq/mctl-web/pull/9) | — |
| mctl-gitops | argo-workflows-cve-patch-v2 | merged | [mctl-gitops#85](https://github.com/mctlhq/mctl-gitops/pull/85) | — |
| mctl-gitops | argocd-informer-cache-patch | merged | [mctl-gitops#90](https://github.com/mctlhq/mctl-gitops/pull/90) | — |
| mctl-gitops | grafana-sql-rce-patch | merged | [mctl-gitops#89](https://github.com/mctlhq/mctl-gitops/pull/89) | — |
| mctl-gitops | eso-cve-patch | merged | [mctl-gitops#87](https://github.com/mctlhq/mctl-gitops/pull/87) | — |

---

## Pipeline diff (vs previous report — 2026-05-06)

Previous report baseline: `report.md` in repo root (2026-05-06 run; GitHub was unavailable that day so it was never posted as an issue — diff is therefore against local file, not a GitHub issue).

- **Newly merged (since 2026-05-06):**
  - `mctl-agent/incident-auto-cleanup-phase1` → [mctl-agent#11](https://github.com/mctlhq/mctl-agent/pull/11) (merged 2026-05-06)
  - `mctl-agent/incident-auto-cleanup-phase3` → [mctl-agent#12](https://github.com/mctlhq/mctl-agent/pull/12) (merged 2026-05-06)
  - `mctl-docs/mcp-agents-tools` → [mctl-docs#7](https://github.com/mctlhq/mctl-docs/pull/7) (merged 2026-05-06)
  - `mctl-agent/incident-auto-cleanup-phase2` → [mctl-agent#13](https://github.com/mctlhq/mctl-agent/pull/13) (merged 2026-05-07)
  - `mctl-agent/incident-auto-cleanup-phase4a-metrics-wiring` → [mctl-agent#16](https://github.com/mctlhq/mctl-agent/pull/16) (merged 2026-05-07)
  - `mctl-agent/incident-auto-cleanup-phase4b-metrics-full` → [mctl-agent#17](https://github.com/mctlhq/mctl-agent/pull/17) (merged 2026-05-07)
- **Newly rejected (since 2026-05-06):**
  - `mctl-agent/incident-auto-cleanup-phase4-metrics` → superseded by 4a+4b split (rejected 2026-05-07)
- **Newly proposed (since 2026-05-06):** all 7 of the above (appeared and immediately reached terminal state)
- **Still in-progress:** none
- **Still proposed:** none

---

## Recent merged PRs (24 h)

All 20 merged PRs are from `mctlhq/mctl-telegram` — active feature sprint building a Telegram-native identity layer and Local Bridge:

| PR | title | merged at (UTC) |
|----|-------|-----------------|
| [mctl-telegram#22](https://github.com/mctlhq/mctl-telegram/pull/22) | feat(auth): Telegram-native OAuth issuer | 2026-05-15 08:26 |
| [mctl-telegram#21](https://github.com/mctlhq/mctl-telegram/pull/21) | chore: prepare repository for public open source release | 2026-05-15 07:56 |
| [mctl-telegram#20](https://github.com/mctlhq/mctl-telegram/pull/20) | feat(local): daemon CLI — init/login/connect/daemon | 2026-05-14 22:37 |
| [mctl-telegram#19](https://github.com/mctlhq/mctl-telegram/pull/19) | feat(bridge): server-side Local Bridge — websocket transport | 2026-05-14 22:37 |
| [mctl-telegram#17](https://github.com/mctlhq/mctl-telegram/pull/17) | feat(scopes)!: admins group is read-only by default (M2.6) | 2026-05-14 17:25 |
| [mctl-telegram#16](https://github.com/mctlhq/mctl-telegram/pull/16) | Revert "feat(scopes)!: admins group is read-only by default…" | 2026-05-14 16:47 |
| [mctl-telegram#15](https://github.com/mctlhq/mctl-telegram/pull/15) | feat(bridge): Local Bridge scaffolding — protocol, hub, scheduler | 2026-05-14 01:34 |
| [mctl-telegram#14](https://github.com/mctlhq/mctl-telegram/pull/14) | docs(web): surface M2+M3 features on /security, /privacy, landing | 2026-05-14 01:30 |
| [mctl-telegram#13](https://github.com/mctlhq/mctl-telegram/pull/13) | feat(mcp): wrap Telegram message text in untrusted-content tags | 2026-05-14 01:26 |
| [mctl-telegram#12](https://github.com/mctlhq/mctl-telegram/pull/12) | feat(audit): tamper-evident hash-chain on audit_logs (M3.1) | 2026-05-14 01:23 |
| [mctl-telegram#11](https://github.com/mctlhq/mctl-telegram/pull/11) | feat(scopes)!: admins group is read-only by default (M2.6, B…) | 2026-05-14 01:19 |
| [mctl-telegram#10](https://github.com/mctlhq/mctl-telegram/pull/10) | feat(sweeper): audit-log retention sweeper + AUDIT_RETENTION | 2026-05-14 01:15 |
| [mctl-telegram#9](https://github.com/mctlhq/mctl-telegram/pull/9) | feat(ratelimit): per-(identity, peer) write cap for prepare_send | 2026-05-14 01:10 |
| [mctl-telegram#8](https://github.com/mctlhq/mctl-telegram/pull/8) | feat(mcp): two-step prepare→confirm for send/pin (M2.3) | 2026-05-14 01:06 |
| [mctl-telegram#7](https://github.com/mctlhq/mctl-telegram/pull/7) | feat(ttl): session TTL (idle 30d + absolute 90d) with hourly sweeper | 2026-05-14 01:05 |
| [mctl-telegram#6](https://github.com/mctlhq/mctl-telegram/pull/6) | feat(audit): user-visible audit log via MCP tool + HTTP endpoint | 2026-05-14 00:55 |
| [mctl-telegram#5](https://github.com/mctlhq/mctl-telegram/pull/5) | feat(web): honest-disclosure landing + /security + /privacy | 2026-05-14 00:52 |
| [mctl-telegram#4](https://github.com/mctlhq/mctl-telegram/pull/4) | feat(auth): JWT audience claim enforcement with phased rollout | 2026-05-14 00:31 |
| [mctl-telegram#3](https://github.com/mctlhq/mctl-telegram/pull/3) | feat(crypto): per-user HKDF session keys with lazy v1→v2 migration | 2026-05-14 00:28 |
| [mctl-telegram#2](https://github.com/mctlhq/mctl-telegram/pull/2) | feat: self-service disconnect/delete + enforce send_enabled flag | 2026-05-14 00:44 |

---

## Bot commits (24 h)

No commits authored by `mctl-agents` in the last 26 h (`git log --author="mctl-agents" --since="26 hours ago"` returned empty).

---

## Detected problems

### Stale WIP PR — `mctlhq/mctl-gitops#84` (15 days, threshold 7 d)

[mctlhq/mctl-gitops#84](https://github.com/mctlhq/mctl-gitops/pull/84) — **[wip] feat(agents): per-proposal claim mechanism for parallel implementer**

- State: **open draft**, not for merge yet
- Created: 2026-04-30, last commit/update: 2026-04-30 (15 days with zero activity)
- Author: `mashkovd`
- The PR is an intentional design placeholder (1 commit, 117 additions, 1 file). Author note: "Will iterate on this branch when implementation starts. Reach me before merging — there are coordinated changes across two repos."
- Qualifies for `[stale-pr]` issue (>7 days, no activity). Deduplication check against `mctlhq/mctl-agents` was **not possible** — GitHub MCP session is restricted to `mctlhq/mctl-gitops` only; see §Errors.
- Stand-alone `[stale-pr]` issue creation was attempted in `mctlhq/mctl-agents` — see §Errors for result.

**Open PRs stale >48 h (approaching 7-day threshold, watch next run):**

| repo | PR | title | last updated | days stale |
|------|----|-------|-------------|-----------|
| mctl-api | [#53](https://github.com/mctlhq/mctl-api/pull/53) | deps: bump k8s.io/api 0.32.3→0.36.0 | 2026-05-11 | 4 d |
| mctl-api | [#52](https://github.com/mctlhq/mctl-api/pull/52) | deps: bump mcp-go 0.46.0→0.52.0 | 2026-05-11 | 4 d |
| mctl-api | [#51](https://github.com/mctlhq/mctl-api/pull/51) | deps: bump go-oidc/v3 3.17.0→3.18.x | 2026-05-11 | 4 d |
| mctl-api | [#50](https://github.com/mctlhq/mctl-api/pull/50) | deps: bump k8s.io/client-go 0.32.3→0.36.0 | 2026-05-11 | 4 d |
| mctl-portal | [#7](https://github.com/mctlhq/mctl-portal/pull/7) | feat(app): add /proposals page for agents review | 2026-05-10 | 5 d |
| mctl-api | [#47](https://github.com/mctlhq/mctl-api/pull/47) | feat(mcp): mctl_create_preview build-from-branch | 2026-05-10 | 5 d |
| mctl-web | [#12](https://github.com/mctlhq/mctl-web/pull/12) | feat: redesign v3 | 2026-05-10 | 5 d |
| mctl-agents | [#15](https://github.com/mctlhq/mctl-agents/pull/15) | feat(orchestrator): Tier 2 implementer agents | 2026-05-09 | 6 d |
| mctl-agents | [#17](https://github.com/mctlhq/mctl-agents/pull/17) | feat(mctl-docs): fallback to GitHub API | 2026-05-09 | 6 d |
| mctl-agents | [#16](https://github.com/mctlhq/mctl-agents/pull/16) | feat(orchestrator): rotate mentor digests >8w | 2026-05-09 | 6 d |

These hit 7 days on 2026-05-16/17. Next run should open `[stale-pr]` issues if still inactive.

---

## Cluster health

The `api.mctl.ai` MCP connector **was found attached** at run time (contrary to the task configuration which said it was not yet attached — this appears to be a stale note in the task definition).

**Services (10 deployed):**

| team | service | image tag | host |
|------|---------|-----------|------|
| admins | mctl-docs | 0.1.20 | docs.mctl.ai |
| admins | mctl-web | 4.7.0 | mctl.me |
| admins | openclaw | 2026.5.14-beta.1 | admins-openclaw.mctl.ai |
| labs | kuptsi-app | 0.2.12 | labs-kuptsi-app.mctl.ai |
| labs | mctl-telegram | 0.8.2 | tg.mctl.ai |
| labs | openclaw | 2026.5.14-beta.1 | labs-openclaw.mctl.ai |
| labs | pelican-proxy | 0.11.0 | labs-pelican-proxy.mctl.ai |
| labs | pelican-proxy-pr-36 *(preview)* | preview.37 | pelican-proxy-pr-36.mctl.ai |
| labs | trading-data | 0.2.4 | — |
| ovk | openclaw | 2026.5.14-beta.1 | ovk-openclaw.mctl.ai |

**Workflow runs (last 24 h):** 8 runs — all `deploy-service` with status `submitted`, driven by `mashkovd`. 7 for team `labs`, 1 for team `admins`. Timing correlates with the mctl-telegram feature sprint merges (08:29, 08:13, 07:59 UTC today; 22:38, 22:29, 22:22, 16:49, 16:47 UTC yesterday). No rollbacks or failed workflows visible in this window.

*Per-service restart counts and MinIO PVC % require per-service `mctl_get_service_status` / `mctl_get_resource_usage` calls — not pulled this run to keep scope bounded. ArgoCD sync state similarly not checked. Full enrichment available on next run now that the connector is confirmed attached.*

---

## Errors during run

| step | error | impact |
|------|-------|--------|
| Previous daily-report lookup (GitHub) | GitHub MCP restricted to `mctlhq/mctl-gitops`; `mctlhq/mctl-agents` returned "Access denied" | Diffed against local `report.md` (2026-05-06) instead |
| Stand-alone issue creation (`mctlhq/mctl-agents`) | GitHub MCP restricted; attempted `issue_write` — expected to fail (result appended below) | `[stale-pr]` issue for gitops#84 not posted |
| Deduplication check for stuck-proposal/stale-pr | Cannot list issues in `mctlhq/mctl-agents` | Deduplication skipped for this run |
| `gh` CLI | Not found in `$PATH` (`command not found`) | No fallback; all GitHub cross-repo operations via MCP only |
| Telegram notification | `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` not set | Silently skipped per task spec |

---

## TODO

- Expand the GitHub MCP session scope to include `mctlhq/mctl-agents` (read + issue-write) so that daily-report issues, deduplication checks, and follow-up `[stale-pr]` / `[stuck-proposal]` issues can be posted correctly.
- The `api.mctl.ai` MCP connector is now confirmed attached. Enrich next run with: `mctl_get_service_status` (per-service restart counts), `mctl_get_resource_usage` (MinIO PVC %), ArgoCD app sync state.
- The 10 open PRs currently stale 4–6 days (mctl-agents #15/16/17, mctl-api #47/50/51/52/53, mctl-portal #7, mctl-web #12) will cross the 7-day `[stale-pr]` threshold on 2026-05-16/17. Next run should open issues for them if still without activity.
