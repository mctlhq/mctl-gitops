> **Routing note:** This issue was intended for `mctlhq/mctl-agents` but was posted here because the GitHub MCP session is scoped to `mctlhq/mctl-gitops` only. To fix: expand the MCP allowed-repositories list to include `mctlhq/mctl-agents`.

---

## Summary

20 proposals tracked across 7 repos: **16 merged**, **4 rejected**, **0 in-progress**, **0 proposed**. Pipeline fully drained — no change from yesterday (#223). Zero `mctl-agents` bot commits in the last 26 h. **Active human day** (2026-05-17/18): 10 merged PRs spanning a mctl-telegram sprint — OAuth refresh-token grant, dedicated JWT signing key, landing redesign (0.14.0 + 0.15.0 releases), Telegram OIDC scaffold (0.16.0 release PR open), and an ArgoCD server-side-diff bug fix that was blocking the JWT-key rollout. **6 open PRs are stale (>7 days no activity)** — 2 already have stand-alone issues (follow-up comments posted); 4 new issues opened this run.

---

## Proposal pipeline state

| repo | slug | status | pr | changed_since_yesterday |
|------|------|--------|----|--------------------------|
| mctl-agents | tier3-pr-shepherd | merged | [mctl-agents#12](https://github.com/mctlhq/mctl-agents/pull/12) | — |
| mctl-agent | sqlite-cve-patch | merged | [mctl-agent#9](https://github.com/mctlhq/mctl-agent/pull/9) | — |
| mctl-agent | incident-auto-cleanup-phase1 | merged | [mctl-agent#11](https://github.com/mctlhq/mctl-agent/pull/11) | — |
| mctl-agent | incident-auto-cleanup-phase2 | merged | [mctl-agent#13](https://github.com/mctlhq/mctl-agent/pull/13) | — |
| mctl-agent | incident-auto-cleanup-phase3 | merged | [mctl-agent#12](https://github.com/mctlhq/mctl-agent/pull/12) | — |
| mctl-agent | incident-auto-cleanup-phase4-metrics | rejected | (no PR — budget exhausted before push) | — |
| mctl-agent | incident-auto-cleanup-phase4a-metrics-wiring | merged | [mctl-agent#16](https://github.com/mctlhq/mctl-agent/pull/16) | — |
| mctl-agent | incident-auto-cleanup-phase4b-metrics-full | merged | [mctl-agent#17](https://github.com/mctlhq/mctl-agent/pull/17) | — |
| mctl-api | chi-security-patch | merged | [mctl-api#39](https://github.com/mctlhq/mctl-api/pull/39) | — |
| mctl-api | pgx-sqli-cve-2025-54236 | merged | [mctl-api#40](https://github.com/mctlhq/mctl-api/pull/40) | — |
| mctl-docs | fix-broken-mctl-ai-mcp-links | merged | [mctl-docs#6](https://github.com/mctlhq/mctl-docs/pull/6) | — |
| mctl-docs | mcp-agents-tools | merged | [mctl-docs#7](https://github.com/mctlhq/mctl-docs/pull/7) | — |
| mctl-portal | scaffolder-path-traversal | rejected | [mctl-portal#10](https://github.com/mctlhq/mctl-portal/pull/10) | — |
| mctl-portal | scaffolder-secret-leak | rejected | [mctl-portal#12](https://github.com/mctlhq/mctl-portal/pull/12) | — |
| mctl-openclaw | upgrade-to-2026-4-27 | rejected | [mctl-openclaw#15](https://github.com/mctlhq/mctl-openclaw/pull/15) | — |
| mctl-web | wrangler-upgrade-security | merged | [mctl-web#9](https://github.com/mctlhq/mctl-web/pull/9) | — |
| mctl-gitops | argo-workflows-cve-patch-v2 | merged | [mctl-gitops#85](https://github.com/mctlhq/mctl-gitops/pull/85) | — |
| mctl-gitops | argocd-informer-cache-patch | merged | [mctl-gitops#90](https://github.com/mctlhq/mctl-gitops/pull/90) | — |
| mctl-gitops | grafana-sql-rce-patch | merged | [mctl-gitops#89](https://github.com/mctlhq/mctl-gitops/pull/89) | — |
| mctl-gitops | eso-cve-patch | merged | [mctl-gitops#87](https://github.com/mctlhq/mctl-gitops/pull/87) | — |

---

## Pipeline diff (vs yesterday — issue #223, 2026-05-17)

- **Newly merged:** none
- **Newly rejected:** none
- **Newly proposed:** none
- **Still in-progress:** none
- **Still proposed:** none

Pipeline is fully terminal. No delta from yesterday.

---

## Recent merged PRs (24h — 2026-05-17/18)

10 PRs merged across 3 repos:

**mctlhq/mctl-telegram (7):**
- [#54](https://github.com/mctlhq/mctl-telegram/pull/54) feat(auth): scaffold Telegram OIDC relying party (dormant) — 2026-05-18T08:33
- [#53](https://github.com/mctlhq/mctl-telegram/pull/53) chore(main): release 0.15.0 — 2026-05-17T22:39
- [#52](https://github.com/mctlhq/mctl-telegram/pull/52) chore: align release-please pre-1.0 versioning with org policy — 2026-05-17T20:05
- [#51](https://github.com/mctlhq/mctl-telegram/pull/51) feat(oauth): add refresh-token grant and dedicate the JWT signing key — 2026-05-17T20:10
- [#50](https://github.com/mctlhq/mctl-telegram/pull/50) chore: correct release-please manifest to 0.13.0 — 2026-05-17T15:17
- [#49](https://github.com/mctlhq/mctl-telegram/pull/49) feat(web): redesign landing page on the mctl design system — 2026-05-17T15:10
- [#18](https://github.com/mctlhq/mctl-telegram/pull/18) chore(main): release 0.14.0 — 2026-05-17T20:05

**mctlhq/mctl-gitops (3):**
- [#227](https://github.com/mctlhq/mctl-gitops/pull/227) fix(argocd): disable server-side diff to fix ExternalSecret apply — 2026-05-17T23:22
- [#226](https://github.com/mctlhq/mctl-gitops/pull/226) fix(mctl-telegram): force client-side apply for oauth ExternalSecret — 2026-05-17T23:04
- [#224](https://github.com/mctlhq/mctl-gitops/pull/224) fix(mctl-telegram): source JWT signing key from a dedicated Vault path — 2026-05-17T22:49

---

## Bot commits (26h — mctl-agents author)

None. No `mctl-agents`-authored commits in the last 26 hours.

---

## Detected problems

Stale PRs (>7 days without activity — cutoff 2026-05-11):

| PR | title | days stale | action taken |
|----|-------|-----------|--------------|
| [mctl-gitops#84](https://github.com/mctlhq/mctl-gitops/pull/84) | [wip] per-proposal claim mechanism (DRAFT) | 18d | follow-up comment → [#188](https://github.com/mctlhq/mctl-gitops/issues/188) |
| [mctl-portal#7](https://github.com/mctlhq/mctl-portal/pull/7) | feat(app): add /proposals page (DRAFT) | 8d | follow-up comment → [#121](https://github.com/mctlhq/mctl-gitops/issues/121) |
| [mctl-agents#15](https://github.com/mctlhq/mctl-agents/pull/15) | feat(orchestrator): Tier 2 implementer agents | 9d | new issue → _see below_ |
| [mctl-agents#16](https://github.com/mctlhq/mctl-agents/pull/16) | feat(orchestrator): rotate mentor digests older than 8 weeks | 9d | new issue → _see below_ |
| [mctl-agents#17](https://github.com/mctlhq/mctl-agents/pull/17) | feat(mctl-docs): fallback to GitHub API when sibling clones absent | 9d | new issue → _see below_ |
| [mctl-api#47](https://github.com/mctlhq/mctl-api/pull/47) | feat(mcp): mctl_create_preview — build from branch support | 8d | new issue → _see below_ |

All four new stand-alone issues are filed in `mctlhq/mctl-gitops` due to MCP session scope restriction (see Errors section). Issue links will be updated once created.

---

## Cluster health

Skipped: api.mctl.ai MCP connector not attached yet. See TODO at the bottom of this issue.

---

## Errors during run

1. **`mctlhq/mctl-agents` inaccessible via GitHub MCP** — The MCP session is restricted to `mctlhq/mctl-gitops`. As a result:
   - All stand-alone stale-pr issues are filed in `mctlhq/mctl-gitops` instead of `mctlhq/mctl-agents`.
   - Deduplication for existing `mctl-agents` issues could not be verified.
   - **Fix:** Add `mctlhq/mctl-agents` to the MCP session's allowed-repositories list.

---

## TODO

Attach the api.mctl.ai MCP connector to this routine to unlock workflow-run counts (`mctl_list_workflows`), MinIO PVC % (`mctl_get_resource_usage`), per-service restart counts (`mctl_get_service_status`), and ArgoCD app sync state.
