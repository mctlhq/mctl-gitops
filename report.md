## Summary (2026-06-06 09:00 UTC)

**60 proposals** tracked across 11 repos (51 merged · 4 proposed · 5 rejected · 0 in-progress). Since the 2026-06-02 snapshot, **13 new proposals were added and merged** — all in `mctl-pairdesk` (12) and `mctl-openclaw` (1), reflecting a burst of pairdesk feature work that closed 12 GitHub issues in under 4 days. Two new proposals are freshly in `proposed` (mctl-pairdesk). The two mctl-telegram proposals stuck since 2026-05-25 are now 12 days old; standalone issues filed (mctl-gitops#390, #391). 5 org PRs merged in the last 24 h (ChatGPT app submission prep + pairdesk UX). Standalone stale-PR issues filed for oldest 4 open PRs (mctl-gitops#392, #393).

---

## Proposal pipeline state

_Previous snapshot: 2026-06-02 (46 proposals). New proposals marked ✓ in `changed_since_yesterday`._

| repo | slug | status | pr | changed_since_yesterday |
|------|------|--------|----|------------------------|
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
| mctl-design | issue-3-change-the-storybook-overview-brand-icon | merged | [#8](https://github.com/mctlhq/mctl-design/pull/8) | — |
| mctl-design | issue-4-rename-storybook-brand-title-to-mctl-ui | merged | [#5](https://github.com/mctlhq/mctl-design/pull/5) | — |
| mctl-design | issue-6-align-storybook-page-title-og-title-with | merged | [#7](https://github.com/mctlhq/mctl-design/pull/7) | — |
| mctl-docs | fix-broken-mctl-ai-mcp-links | merged | [#6](https://github.com/mctlhq/mctl-docs/pull/6) | — |
| mctl-docs | mcp-agents-tools | merged | [#7](https://github.com/mctlhq/mctl-docs/pull/7) | — |
| mctl-gitops | argo-workflows-cve-patch-v2 | merged | [#85](https://github.com/mctlhq/mctl-gitops/pull/85) | — |
| mctl-gitops | argocd-informer-cache-patch | merged | [#90](https://github.com/mctlhq/mctl-gitops/pull/90) | — |
| mctl-gitops | eso-cve-patch | merged | [#87](https://github.com/mctlhq/mctl-gitops/pull/87) | — |
| mctl-gitops | grafana-sql-rce-patch | merged | [#89](https://github.com/mctlhq/mctl-gitops/pull/89) | — |
| mctl-openclaw | issue-25-ci-add-claude-review-yml-automated-pr-re | merged | [#26](https://github.com/mctlhq/mctl-openclaw/pull/26) | ✓ new |
| mctl-openclaw | upgrade-to-2026-4-27 | rejected | [#15](https://github.com/mctlhq/mctl-openclaw/pull/15) | — |
| mctl-pairdesk | issue-5-feat-add-landing-page-astro-like-mctl-lo | merged | [#32](https://github.com/mctlhq/mctl-pairdesk/pull/32) | ✓ new |
| mctl-pairdesk | issue-22-feat-web-create-order-step-1-currency-pa | merged | [#27](https://github.com/mctlhq/mctl-pairdesk/pull/27) | ✓ new |
| mctl-pairdesk | issue-23-feat-web-create-order-step-2-coupled-dua | merged | [#30](https://github.com/mctlhq/mctl-pairdesk/pull/30) | ✓ new |
| mctl-pairdesk | issue-24-feat-redesign-create-order-into-a-t-bank | merged | [#31](https://github.com/mctlhq/mctl-pairdesk/pull/31) | ✓ new |
| mctl-pairdesk | issue-28-fix-web-create-order-step-1-collision-au | merged | [#29](https://github.com/mctlhq/mctl-pairdesk/pull/29) | ✓ new |
| mctl-pairdesk | issue-33-fix-web-hide-app-tab-bar-during-create-o | merged | [#41](https://github.com/mctlhq/mctl-pairdesk/pull/41) | ✓ new |
| mctl-pairdesk | issue-34-fix-web-rework-create-order-step-navigat | merged | [#42](https://github.com/mctlhq/mctl-pairdesk/pull/42) | ✓ new |
| mctl-pairdesk | issue-35-fix-web-city-notes-section-layout-overfl | merged | [#39](https://github.com/mctlhq/mctl-pairdesk/pull/39) | ✓ new |
| mctl-pairdesk | issue-36-fix-web-entered-city-missing-from-live-p | merged | [#40](https://github.com/mctlhq/mctl-pairdesk/pull/40) | ✓ new |
| mctl-pairdesk | issue-37-feat-web-one-currency-pair-per-order-rem | merged | [#43](https://github.com/mctlhq/mctl-pairdesk/pull/43) | ✓ new |
| mctl-pairdesk | issue-38-fix-web-rate-slider-must-anchor-the-last | merged | [#44](https://github.com/mctlhq/mctl-pairdesk/pull/44) | ✓ new |
| mctl-pairdesk | issue-45-add-web-test-harness-rateslider-anchorin | merged | [#46](https://github.com/mctlhq/mctl-pairdesk/pull/46) | ✓ new |
| mctl-pairdesk | **issue-52-p3-add-native-showconfirm-for-destructiv** | **proposed** | — | ✓ new |
| mctl-pairdesk | **issue-53-p3-create-order-has-no-ttl-expiry-picker** | **proposed** | — | ✓ new |
| mctl-portal | scaffolder-path-traversal | rejected | [#10](https://github.com/mctlhq/mctl-portal/pull/10) | — |
| mctl-portal | scaffolder-secret-leak | rejected | [#12](https://github.com/mctlhq/mctl-portal/pull/12) | — |
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
| mctl-telegram | issue-154-nav-replace-github-text-link-with-a-gith | merged | [#157](https://github.com/mctlhq/mctl-telegram/pull/157) | — |
| mctl-telegram | issue-158-non-deterministic-safety-block-on-get-me | merged | [#162](https://github.com/mctlhq/mctl-telegram/pull/162) | — |
| mctl-telegram | issue-159-live-send-unusable-when-prepare-send-mes | merged | [#163](https://github.com/mctlhq/mctl-telegram/pull/163) | — |
| mctl-telegram | issue-202-mctl-telegram-canary-cronjob-stuck-on-im | merged | [#211](https://github.com/mctlhq/mctl-telegram/pull/211) | — |
| mctl-telegram | **issue-213-deploy-canary-prometheusrule-to-cluster** | **proposed** | — | still (12 d ⚠) |
| mctl-telegram | **issue-214-self-service-canonicalize-client-tier-in** | **proposed** | — | still (12 d ⚠) |
| mctl-web | wrangler-upgrade-security | merged | [#9](https://github.com/mctlhq/mctl-web/pull/9) | — |

**Totals:** 60 proposals — 51 merged · 4 proposed · 5 rejected · 0 in-progress  
_(Previous: 46 proposals — 39 merged · 5 rejected · 2 proposed)_

---

## Pipeline diff (vs 2026-06-02)

- **Newly merged (13):**
  - `mctl-pairdesk/issue-5` → [#32](https://github.com/mctlhq/mctl-pairdesk/pull/32) (landing page)
  - `mctl-pairdesk/issue-22` → [#27](https://github.com/mctlhq/mctl-pairdesk/pull/27) (create-order step 1 currency)
  - `mctl-pairdesk/issue-23` → [#30](https://github.com/mctlhq/mctl-pairdesk/pull/30) (create-order step 2 dual currency)
  - `mctl-pairdesk/issue-24` → [#31](https://github.com/mctlhq/mctl-pairdesk/pull/31) (T-Bank redesign)
  - `mctl-pairdesk/issue-28` → [#29](https://github.com/mctlhq/mctl-pairdesk/pull/29) (step 1 collision fix)
  - `mctl-pairdesk/issue-33` → [#41](https://github.com/mctlhq/mctl-pairdesk/pull/41) (hide tab bar)
  - `mctl-pairdesk/issue-34` → [#42](https://github.com/mctlhq/mctl-pairdesk/pull/42) (step navigation rework)
  - `mctl-pairdesk/issue-35` → [#39](https://github.com/mctlhq/mctl-pairdesk/pull/39) (city notes overflow fix)
  - `mctl-pairdesk/issue-36` → [#40](https://github.com/mctlhq/mctl-pairdesk/pull/40) (city missing from live preview)
  - `mctl-pairdesk/issue-37` → [#43](https://github.com/mctlhq/mctl-pairdesk/pull/43) (one currency pair per order)
  - `mctl-pairdesk/issue-38` → [#44](https://github.com/mctlhq/mctl-pairdesk/pull/44) (rate slider anchor)
  - `mctl-pairdesk/issue-45` → [#46](https://github.com/mctlhq/mctl-pairdesk/pull/46) (test harness for rate slider)
  - `mctl-openclaw/issue-25` → [#26](https://github.com/mctlhq/mctl-openclaw/pull/26) (CI: claude-review workflow)
- **Newly rejected (0):** None.
- **Newly proposed (2):**
  - `mctl-pairdesk/issue-52` (proposed 2026-06-04, 2 days, P3 — showConfirm for destructive actions)
  - `mctl-pairdesk/issue-53` (proposed 2026-06-04, 2 days, P3 — TTL expiry picker in create-order)
- **Still in-progress (0):** None.
- **Still proposed (2, now confirmed stable):**
  - `mctl-telegram/issue-213` — proposed 2026-05-25, now **12 days** old → standalone issue [mctl-gitops#390](https://github.com/mctlhq/mctl-gitops/issues/390)
  - `mctl-telegram/issue-214` — proposed 2026-05-25, now **12 days** old → standalone issue [mctl-gitops#391](https://github.com/mctlhq/mctl-gitops/issues/391)

---

## Recent merged PRs (last 24 h)

_Search: `org:mctlhq is:pr is:merged merged:>=2026-06-05`_

| merged at | repo | PR | title |
|-----------|------|----|-------|
| 2026-06-05T19:51Z | mctl-gitops | [#389](https://github.com/mctlhq/mctl-gitops/pull/389) | chore(mctl-telegram): bump demo video cache-buster to v=5 |
| 2026-06-05T19:38Z | mctl-telegram | [#265](https://github.com/mctlhq/mctl-telegram/pull/265) | chore(demo): refresh walkthrough video with real multi-step ChatGPT flow |
| 2026-06-05T13:15Z | mctl-telegram | [#264](https://github.com/mctlhq/mctl-telegram/pull/264) | feat(web): refresh demo walkthrough (superseded by #265) |
| 2026-06-05T07:12Z | mctl-telegram | [#262](https://github.com/mctlhq/mctl-telegram/pull/262) | fix(mcp): redact telegram login secrets |
| 2026-06-05T07:04Z | mctl-pairdesk | [#58](https://github.com/mctlhq/mctl-pairdesk/pull/58) | feat(web): add 7-day expiry option, rename 72h to 3 days |

_5 PRs merged. All human-authored. Active focus: ChatGPT app submission prep (demo video refresh ×2, login-secret redaction) and mctl-pairdesk TTL UX fix._

---

## Bot commits (last 24 h)

`git log --author="mctl-agents" --since="26 hours ago"` returned **no results**. No automated commits from the agent pipeline in the last 26 h.

---

## Detected problems

### Stuck proposals (stable — appeared in previous report, now >7 days)

| proposal | source issue | since | days | standalone issue |
|----------|-------------|-------|------|-----------------|
| mctl-telegram/issue-213-deploy-canary-prometheusrule | [#213](https://github.com/mctlhq/mctl-telegram/issues/213) | 2026-05-25 | 12 d | [mctl-gitops#390](https://github.com/mctlhq/mctl-gitops/issues/390) ⚠ see §8 |
| mctl-telegram/issue-214-self-service-canonicalize-client-tier | [#214](https://github.com/mctlhq/mctl-telegram/issues/214) | 2026-05-25 | 12 d | [mctl-gitops#391](https://github.com/mctlhq/mctl-gitops/issues/391) ⚠ see §8 |

_Below threshold — watching:_
- `mctl-pairdesk/issue-52` — 2 days in proposed (threshold 7 d)
- `mctl-pairdesk/issue-53` — 2 days in proposed (threshold 7 d)

### Stale open PRs (stable — appeared in previous report, now >7 days no activity)

Standalone issues filed for oldest 4:

| repo | PR | title | last updated | days | issue |
|------|----|-------|-------------|------|-------|
| mctl-gitops | [#84](https://github.com/mctlhq/mctl-gitops/pull/84) | [wip] feat(agents): per-proposal claim mechanism | 2026-04-30 | 37 d | [#392](https://github.com/mctlhq/mctl-gitops/issues/392) |
| mctl-agents | [#15](https://github.com/mctlhq/mctl-agents/pull/15) | feat(orchestrator): Tier 2 implementer agents | 2026-05-09 | 28 d | [#393](https://github.com/mctlhq/mctl-gitops/issues/393) |
| mctl-agents | [#16](https://github.com/mctlhq/mctl-agents/pull/16) | feat(orchestrator): rotate mentor digests | 2026-05-09 | 28 d | [#393](https://github.com/mctlhq/mctl-gitops/issues/393) |
| mctl-agents | [#17](https://github.com/mctlhq/mctl-agents/pull/17) | feat(mctl-docs): fallback to GitHub API | 2026-05-09 | 28 d | [#393](https://github.com/mctlhq/mctl-gitops/issues/393) |

Not actioned yet — confirmed stable on next run:

| repo | PR | title | last updated | days |
|------|----|-------|-------------|------|
| mctl-portal | [#7](https://github.com/mctlhq/mctl-portal/pull/7) | feat(app): add /proposals page for agents review | 2026-05-10 | 27 d |
| mctl-api | [#47](https://github.com/mctlhq/mctl-api/pull/47) | feat(mcp): mctl_create_preview — build from branch support | 2026-05-10 | 27 d |
| mctl-api | [#51](https://github.com/mctlhq/mctl-api/pull/51) | deps: bump go-oidc/v3 3.17→3.18 | 2026-05-11 | 26 d |
| mctl-gitops | [#217](https://github.com/mctlhq/mctl-gitops/pull/217) | feat(argo): add incident responder CronWorkflow | 2026-05-16 | 21 d |
| mctl-agent | [#20](https://github.com/mctlhq/mctl-agent/pull/20) | feat(skills): add statefulset-replicas-mismatch YAML skill | 2026-05-16 | 21 d |
| mctl-telegram | [#146](https://github.com/mctlhq/mctl-telegram/pull/146) | Enhance landing page UX: card animations, SVG icons | 2026-05-22 | 15 d |
| mctl-gitops | [#306](https://github.com/mctlhq/mctl-gitops/pull/306) | fix(observability): bring prometheus-pushgateway into gitops | 2026-05-25 | 12 d |
| mctl-telegram | [#221](https://github.com/mctlhq/mctl-telegram/pull/221) | fix(oauth): auto-persist tier=client to DB on sign-in | 2026-05-26 | 11 d |

<details>
<summary>Deps/release PRs with >7 days no activity (not flagged as stale-pr)</summary>

| repo | PR | title | last updated |
|------|----|-------|-------------|
| mctl-api | [#55](https://github.com/mctlhq/mctl-api/pull/55) | deps: bump mcp-go 0.46→0.54 | 2026-05-18 |
| mctl-api | [#56](https://github.com/mctlhq/mctl-api/pull/56) | deps: bump k8s.io/apimachinery 0.32→0.36 | 2026-05-18 |
| mctl-api | [#57](https://github.com/mctlhq/mctl-api/pull/57) | deps: bump k8s.io/api 0.32→0.36 | 2026-05-18 |
| mctl-api | [#58](https://github.com/mctlhq/mctl-api/pull/58) | deps: bump k8s.io/client-go 0.32→0.36 | 2026-05-18 |
| mctl-api | [#64](https://github.com/mctlhq/mctl-api/pull/64) | chore(main): release 4.20.0 (release-please) | 2026-05-30 |
| mctl-docs | [#17](https://github.com/mctlhq/mctl-docs/pull/17) | chore(main): release 0.1.20 (release-please) | 2026-05-30 |
| mctl-telegram | [#167](https://github.com/mctlhq/mctl-telegram/pull/167) | chore(deps): bump go-chi/chi 5.2→5.3 | 2026-05-27 |
| mctl-telegram | [#170](https://github.com/mctlhq/mctl-telegram/pull/170) | chore(deps): bump golang.org/x/crypto 0.51→0.52 | 2026-05-27 |

</details>

---

## Cluster health

Skipped: api.mctl.ai MCP connector not attached yet. See TODO at the bottom of this issue.

---

## Errors during run

**Write scope mismatch — `mctlhq/mctl-agents` not in session scope.**

The GitHub MCP tool in this session is scoped to `mctlhq/mctl-gitops` only. All 4 standalone issues (#390–#393) and this daily-report were created in `mctlhq/mctl-gitops` instead of `mctlhq/mctl-agents`.

**Fix:** Add `mctlhq/mctl-agents` to the session's repository scope before the next run. The `add_repo` tool from the `claude-code-remote` MCP server was not available in this session.

Previous run (2026-06-02) had the same error; standalone issues were not filed then. Filed today retroactively for the stable stale items.

---

## TODO

- Attach the `api.mctl.ai` MCP connector to this routine to unlock workflow-run counts (`mctl_list_workflows`), MinIO PVC % (`mctl_get_resource_usage`), per-service restart counts (`mctl_get_service_status`), and ArgoCD app sync state.
- Add `mctlhq/mctl-agents` to the GitHub MCP session scope so the report and follow-up issues land in the correct repo.
- Next run: confirm or clear the 8 "not actioned yet" stale PRs listed in §6 — they will be stable by then.
