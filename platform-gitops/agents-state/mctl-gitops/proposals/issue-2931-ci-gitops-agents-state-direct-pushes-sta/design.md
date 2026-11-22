# Design: agents-state separate repository, atomic approval migration and merge-queue monitoring (revision 2)

## Decision record / architecture

Owner-selected: **separate repository** plus **independent queue monitoring** (`mctl-gitops#2931` owner comment). The previous proposal's queue-aware push wait is **not** the target and is removed from the required implementation. No direct writes from mctl-agents to `mctl-gitops/main` after cutover. Existing bot pushes are retained only until explicit migration gates clear, without granting bypass or auto-merge.

### Why a repository and why separate trust domains

GitOps desired state (manifests, Argo configurations, scripts) and volatile agent operational state have different consistency and permission needs. Keeping them in one `main` branch invalidates every merge-group build and causes a hosted-runner job storm. A second branch in *the same GitOps repository* avoids the branch-tip coupling but does not eliminate the repository-wide overprivileged P6 deploy key (#2543).

**Target layout (to confirm in research):**

| Source of truth | Repository/ref | Writers | Readers / constraints |
|---|---|---|---|
| GitOps desired state | `mctlhq/mctl-gitops:main` | only normal governed PR/Merge Queue writers | Argo/CI; zero direct agent-state status writes |
| Reviewed proposal specs | `mctlhq/mctl-agents-state:specs`, PR-protected | investigator publishes a candidate PR; authorized review/merge only | immutable reviewed commit, 4-file digest; runtime writer denied direct push |
| Mutable state (status, inbox, attempts, digest/pointer to specs) | `mctlhq/mctl-agents-state:runtime` | scoped state-writer identity | CAS + serialized status transitions; no executable manifests |
| Policy/authority grant | owner/MFA DevLoop control plane + audited grant store | authenticated human decide; bot cannot mint grant | binding to immutable `specs` SHA/digest and proposal id, consumed exactly once |

This is a *design hypothesis*, not a claim that the new repo, branch protection, CI permissions or storage exists. Research must verify GitHub plan/ruleset behavior and propose an equivalent separation if `specs`/`runtime` roles cannot be enforced. A repo-scoped deploy key alone cannot enforce path restrictions. A candidate proposal in a PR is not an approved executable proposal. No existing Temporal proposal may be automatically upgraded.

## Current evidence / cross-repository inventory (starting, non-exhaustive)

| Component | Existing evidence | Required change |
|---|---|---|
| CWFT writers | `mctl-gitops/platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-{investigate,implement,approve,shepherd,reconcile,run}.yaml` have `commit-and-push` to GitOps `main`, serialized by `mctl-gitops-main-writes` | Identify all producer paths (including incident-responder cron), route operational commits to isolated repo with CAS and branch-specific credential; keep GitOps templates controlled by PR |
| Approve / implement | `mctl-agents/orchestrator/proposal_state.py` `PROPOSAL_DIGEST_FILES` and `approval_digest_verdict`; `mctl-gitops/docs/runbooks/proposal-approval-content-digest.md` and CWFT approve | Make digest source immutable `specs` commit; enforce digest/proposal/grant match on accept and implement; reject missing/unresolved digest |
| Temporal reconcile | `mctl-agents/orchestrator/temporal/activities/gitops_state.py` `TREE_URL` currently points to `GITOPS_REPO/main:AGENTS_STATE_PREFIX`; refs to `proposals.py` and `pr_state.py` | Introduce versioned state locator and authenticated new-repo tree/blob reader; preserve cache correctness and pagination/truncation error semantics |
| API GitOps reader | `mctl-api/internal/gitops/reader.go` `Reader` clones a configured GitOps repository | Inventory downstream `ListHumanInputRequests`, proposals, decision UI, cache/freshness and add a separate state reader; never repoint global GitOps reader used for tenant state |
| DevLoop decide | `mctl-api/internal/api/handlers_devloop_decide.go` checks approval ref, context digest and content digest with fresh second-factor identity | Add source ref/commit binding and invalidation on amendments; pin grant revision until consumed or expired |
| Approval operation | `mctl-api/internal/operations/registry.go` and `internal/api/handlers_write.go` require `expected_content_digest`; existing tool instructions refer to old GitOps path | Version external contract with migration-safe resolver and backward-compat rejection, update MCP descriptions and runbooks |
| GitOps CI | `mctl-gitops/scripts/validate-agents-state-approval.py` hardcodes `platform-gitops/agents-state`; `.github/workflows/validate-manifests.yml` runs full 4-shard validation on `push: main` | After migration, validate rules in state repo on protected change and periodic audit; GitOps CI validates **absence** of unauthorized state writes, not an empty legacy status snapshot |
| Argo discovery / workflows | `platform-gitops/bootstrap/templates/bootstrap/applicationset-apps.yaml` excludes frequent bot churn via `manifest-generate-paths`; CWFT scripts clone GitOps main | Keep Argo code source GitOps only; agents-state repo is data, not watched for deploy manifests; verify every `git clone` and credential mount |
| Other clients | `mctl-agents/config/settings`, `run_issue_investigator.py`, `run_implementer.py`, `run_shepherd.py`, CLI, human-input handlers, scheduler and dashboard (not exhaustively inspected) | Enumerate exact env/arg/config literals and owners with `git grep` and tests; UNKNOWN is blocking, not evidence of absence |

Evidence above is confirmed as repository references at review time, not an exhaustive deployed runtime inventory. `mctl-gitops#2931` includes observed stale queue groups, 22+ bot pushes and shared hosted-runner congestion. PR #2935 independently aims to supersede stale `push` jobs and must be reviewed as adjacent mitigation, not merged blindly or duplicated here.

## Proposed contracts

### 1. Versioned state locator

Resolve `StateLocator { schema_version, repo, runtime_ref, specs_repo, specs_ref, min_schema, migration_epoch }` from a single typed configuration per environment. All clients use the same resolver and log the resolved repository, ref and content SHA; no implicit `mctl-gitops` fallback when the new locator is selected. Explicit read-only legacy fallback is permitted *only* during shadow comparison and cannot authorize execution. A client encountering an unknown epoch/ref fails closed.

Stable proposal identity: `service/slug` plus immutable candidate-spec SHA; human-input artifacts and PR links map to this identity; migrate history without rewriting source audit events. State writes use GitHub ref compare-and-swap (create blob/tree/commit, conditional ref update) or equivalent ETag/CAS. On a conflict fetch latest state and re-run transition validation, bounded retries with jitter. Last-write-wins is forbidden for `.status.yaml` and approval fields. Transition keys include workflow run id / attempt id and transition id to make duplicate deliveries idempotent.

### 2. Reviewed specs vs runtime state

The new repo's protected `specs` branch holds proposal content and PR-based amendments. The runtime branch contains mutable status and references immutable `specs` SHA and content digest; a bot runtime token must not directly write protected specs. A new proposed candidate can be generated by investigator, but only **read-only** review and an owner-granted, exact-digest approval can change implementation authority. A proposal amendment advances source commit and invalidates pending approval; old approval grants cannot be reinterpreted against new content. Keep existing behavior of `control.requires_human_approval`, named approver and four-file digest framing from `mctl-agents/orchestrator/proposal_state.py`. Any change to canonical digest framing requires cross-language test vectors (Python, CWFT shell, mctl-api).

Cross-repo invariants: `approved.digest == digest(specs SHA)`, `approved.proposal_id == runtime.proposal_id`, `approved.source_sha == reviewed SHA` and `approved.grant_ref == fresh owner grant`. Implementer re-verifies all four immediately before work and after retries. A stale grant, unavailable refs or an ambiguous double-write returns explicit `blocked/pending_reconciliation`; never accept or run implementation.

### 3. Permissions model

- State writer GitHub App or deploy key installed **only** in `mctl-agents-state`; can update `runtime`, no privilege in `mctl-gitops`, no admin. Use deny tests against both protected proposal ref and GitOps main. Document whether policy must be enforced by branch rulesets, a mediated writer API, or a dedicated second repo for reviewed content if current GitHub permissions cannot uphold the separation.
- Candidate-proposal author can open a PR against protected `specs` but cannot merge it. Independent reviewer credentials are separate. GitHub-hosted CI guards review and immutable grant/digest binding.
- GitOps credential used for approved configuration changes remains governed by existing PR / Merge Queue. Revoke the old P6 deploy key after cutover; link the permission inventory and rollback to #2543.
- Deny force-push, branch deletion and bypass outside explicitly reviewed exception; do not treat `git add` scoping as an authorization boundary. Require durable logs without leaking tokens.

### 4. Phased migration and rollback

**Phase A — evidence / compatibility (no writes):** full anchored inventory, secret scopes (metadata only), GitHub permissions probes using isolated canary, measured queue/CI durations, choose branch/ruleset, define versioned locator and digest vectors. Capture baseline of proposals, statuses, active DevLoops, in-flight approvals, attempts, inbox/human-input, content/history counts. Include old-to-new mapping.

**Phase B — provision and shadow:** create state repo and protected review source under a *separate* explicit infrastructure approval; backfill at known Git SHA; build read-only shadow resolvers; compare digests/status/attempt metadata per proposal. Do not dual-write approvals blindly. Put modern state writer through repeatable conflict simulations; keep all existing production writers unchanged during this gate.

**Phase C — bounded writers cutover:** temporarily quiesce only affected state writers at approved boundary; drain/reconcile outstanding approvals and attempts; final immutable snapshot + compare; activate versioned locator and state writer identity; preserve audit/proposal SHAs and marker to reject late legacy writes. Existing read-only DevLoop remains safe or explicitly held. Verify fresh Investigator, Approve (synthetic approval only), Implementer gate (must not start on unapproved), Shepherd, Reconcile and Incident Responder in **test** environment. No production owner grants are fabricated.

**Phase D — remove old authority:** verify GitOps main has **zero** direct bot state commits during representative activity, CI volume declines, cache/decide consistency, and queue throughput improves; revoke legacy main-write deploy key / bypass through #2543; stop reliance on legacy tree and validators only when equivalent new policy checks have proved active; record owner post-cutover sign-off.

**Rollback:** before C, switch readers back to legacy without data loss. At/after C, pause writers/implementation, reconcile new status into a verified, explicitly authorized recovery store, restore client locator only after parity and approval revalidation. **Never** silently enable old direct GitOps-main bot pushes as a rollback strategy; if no safe audited path exists, fail closed and require new owner decision. Test recovery with pending grant, concurrent status transition and digest amendment. Document whether a rollback is one-way at each phase.

### 5. Merge queue monitoring and CI-load behavior

Build a read-only monitor whose implementation matches actual GitHub API fields and required permissions (research gate). Query merge queue state, merge_group workflow runs/check SHA history and main push audit. Correlate a head's rebuild sequence and direct commits, without asserting causality from timestamps alone. Recover prior progress timestamps from durable GitHub evidence (not process memory). Poll approximately every **5 min**; alert:
1. same queue entry rebuilt 3+ times without advancing;
2. queued entries with no meaningful completion/advance for **15 min**;
3. direct bot push to protected branch correlated with invalidated merge-group SHA/checks.
Include PR IDs (head and impacted), workflow/run identity, source SHA(s), merge-group SHA(s), timestamps, counts and correlation confidence. If unavailable mark `unknown`, and separately alert on monitor failure or missed schedule. Add a *delivered* on-call notification route (use an existing approved notifier or owner-specified destination; no unreviewed new secret). Deduplicate by queue-entry id + incident type, send recovery signal when progress resumes.

Don't conflate GitHub runner congestion with just queue rebuilding. The `push: main` full validation floods the shared hosted-runner pool; verify related PR #2935 cancellation scope, concurrent active jobs and stale workflow run count in testing. A healthy queue monitor may still report hosted-runner starvation elsewhere: add congestion telemetry/runbook and require an end-to-end pressure test. No new unconditional GitOps `push`-triggered validation work.

### 6. Acceptance evidence and release governance

All three docs amended on a branch and merged docs-only through normal PR/Merge Queue only after independent source-pinned review. That merger does **not** approve the proposal. On the accepted docs revision recompute `scripts/proposal-content-digest.py --rev <merged-sha> ...` while in legacy location; after migration use new versioned resolver. A future owner decision must bind to one digest and explicitly define slice/scope; no automatic Temporal approval signal now.

**Required tests:** inventory completeness; read shadow parity; digest cross-language vectors and amendment invalidation; stale approved grant after cutover; concurrent conflicting `.status.yaml` writes; duplicate/replayed transitions; GitHub API 403/404/429/timeouts; repo/ref access revocation; branch protections (negative tests); cache staleness; queue 3x rebuild / 15-minute no-progress / attribution / API unknown; stale-run cancellation and backlog relief; no pre-cutover prod mutation; controlled rollback of partial cutover.

## Alternatives and explicitly rejected shortcuts

- Branch only inside `mctl-gitops`: repo credential authority remains overbroad; rejected as end state.
- Queue-aware 15-minute deferral (prior revision): timeouts, API fail-open, approval exemption and burst races still push to GitOps main; optional separately approved emergency mitigation, **not** a fix.
- Route high-frequency status writes through GitOps Merge Queue: creates heavy PR/CI load and delays status; rejected.
- Increase `max_entries_to_build`: throughput tuning, not root-cause repair; optional P3 after evidence.
- Single unprotected new-state branch with all reviewable specs and bot-controlled approvals: insufficient authority separation; rejected until owner explicitly accepts security consequences.

## Open research questions (block implementation if unresolved)

1. Are GitHub rulesets, branch protections, GitHub App permission scopes and Actions tokens sufficient on the current plan to separate protected `specs` from bot-writable `runtime`? If not, design a mediated writer or separate reviewed-specs repository; no guess or permissions-by-convention.
2. What are *all* state consumers in `mctl-gitops`, `mctl-api`, `mctl-agents`, Telegram decide notifications, CLI and future Personal Assistant? Provide pinned file-line inventory and runtime config.
3. Where should an approval grant live durably, how is second-factor binding preserved, and how are previously issued/consumed grants reconciled? Which paths are non-reversible?
4. What is safe agent-status freshness lag, failure budget, transition concurrency and max backfill size? Provide measurements and bounded limits.
5. Can the native merge-queue GraphQL/API fields proposed in revision 1 actually be read with the intended token, with pagination/rate limits? Prove with sandbox/read-only query before coding.
6. Confirm #2935 status and queue/CI telemetry; ensure no duplicate, and explicitly record dependency for hosted-runner recovery.
