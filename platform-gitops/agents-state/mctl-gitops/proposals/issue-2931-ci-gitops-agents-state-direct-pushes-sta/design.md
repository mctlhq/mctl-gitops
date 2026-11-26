# Design: agents-state separate repository, approval reconciliation and merge-queue monitoring (revision 3)

## Decision record / architecture

Owner-selected: **separate repository** plus **independent queue monitoring** (`mctl-gitops#2931` owner comment). The previous proposal's queue-aware push wait is **not** the target and is removed from the required implementation. No direct writes from mctl-agents to `mctl-gitops/main` after cutover. Existing bot pushes are retained only until explicit migration gates clear, without granting bypass or auto-merge.

### Why a repository and why separate trust domains

GitOps desired state (manifests, Argo configurations, scripts) and volatile agent operational state have different consistency and permission needs. Keeping them in one `main` branch invalidates every merge-group build and causes a hosted-runner job storm. A second branch in *the same GitOps repository* avoids the branch-tip coupling but does not eliminate the repository-wide overprivileged P6 deploy key (#2543).

**Target layout (to confirm in research):**

| Source of truth | Repository/ref | Writers | Readers / constraints |
|---|---|---|---|
| GitOps desired state | `mctlhq/mctl-gitops:main` | only normal governed PR/Merge Queue writers | Argo/CI; zero direct agent-state status writes |
| Reviewed proposal specs | `mctlhq/mctl-agents-state:specs` (candidate; protection must be demonstrated) | investigator publishes a candidate PR; authorized review/merge only | immutable reviewed commit, 4-file digest; runtime writer denied direct push |
| Mutable state (status, inbox, attempts, digest/pointer to specs) | `mctlhq/mctl-agents-state:runtime` (candidate; only mediated or constrained bot writes) | scoped state-writer identity | CAS + serialized status transitions; no executable manifests |
| Policy/authority grant | owner/MFA DevLoop control plane + audited grant store | authenticated human decide; bot cannot mint grant | binding to immutable `specs` SHA/digest and proposal id, consumed exactly once |

This is a *design hypothesis*, not a claim that the new repo, branch protection, CI permissions or storage exists. Research must verify GitHub plan/ruleset behavior and propose an equivalent separation if `specs`/`runtime` roles cannot be enforced. A repo-scoped deploy key alone cannot enforce path restrictions. A private state repository is the confidentiality default, not an assumption that private branch rulesets work on the current GitHub plan. A candidate proposal in a PR is not an approved executable proposal. No existing Temporal proposal may be automatically upgraded.

### Confidentiality and effective authority gate (P1-3)

`platform-gitops/agents-state/**` includes human-input requests and generated inbox/incident material. Treat the full subtree as **potentially sensitive** pending an evidence-based field-level classification; do not publish the new repository merely to obtain public-repository branch rulesets. The target repository `mctlhq/mctl-agents-state` returned 404 to the current GitHub client at revision-3 investigation (uncreated or inaccessible; neither possibility is evidence of a configured protection rule). The `mctlhq/mctl-gitops` repository was confirmed public. Operator issue #2931 reports an organization Free plan; **effective** private-repository branch/ruleset permissions must be checked against current GitHub capabilities, not inferred from template YAML.

Before GO_IMPLEMENT, decide and test one of these boundaries:

- **A — private repository + enforced protected specs ref** *only if* the org plan/rulesets truly block a runtime-write identity from pushing to reviewed specs and to GitOps main; require a real negative push test in an isolated canary, including force-push/bypass.
- **B — private repository + mediated writer service / separately governed authority store** if effective per-ref restrictions are unavailable: status-writer credentials cannot write specs, and the mediated service verifies the authorized path and immutable spec SHA before a conditional commit. The service's own privileged identity must remain outside LLM-executing pods. Its grant/operations authority lives in mctl-api, not a bot-owned YAML field.
- **C — distinct reviewed-spec repository with independently scoped credentials** if A/B cannot be proved. An extra repository is preferable to claiming GitHub permissions the current tier does not enforce.

Record a concrete threat model, data classification, approved visibility, audit actor matrix (read/write/bypass) and deny-test trace. No shared deploy key, unprotected `specs` path or public agent-state payload is acceptable by default. GitHub rule availability is a **research gate** until source-pinned verification, not a factual assumption in production.

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
| Human-input direct reader | `mctl-agents/orchestrator/temporal/activities/human_input.py` gets `human-input/request.json` via hard-coded GitOps repo/prefix; `mctl-api/internal/api/handlers_human_input.go` resolves records from `GitReader.ListHumanInputRequests` | Add epoch-aware state resolver and typed unknown/unavailable rather than silent empty; do not expose confidential requests in public repo |
| Incident responder / legacy authorization | `mctl-agents/orchestrator/run_incident_responder.py` 1–24 produces `incident-*` with `status: accepted`; `orchestrator/proposal_state.py` ~245–340 requires verified execution authority distinct from status | Preserve visible accepted state, but quarantine/deny execution without grant; no implicit autonomy by moving files |
| Independent review receipts (currently non-gating) | `mctl-agents/docs/adr/025-independent-review-receipts.md` 12–17 and 50–56 defines a proposed, currently unwired receipt contract with `gitops_commit` provenance | Version receipt source-provenance to explicit repository/ref/SHA/digest; preserve backward compatibility for existing sealed receipts; do not assert an enforced receipt gate |
| Other clients | `mctl-agents/config/settings`, `run_issue_investigator.py`, `run_implementer.py`, `run_shepherd.py`, CLI, human-input handlers, scheduler and dashboard (not exhaustively inspected) | Enumerate exact env/arg/config literals and owners with `git grep` and tests; UNKNOWN is blocking, not evidence of absence |

Evidence above is confirmed as repository references at review time, not an exhaustive deployed runtime inventory. `mctl-gitops#2931` includes observed stale queue groups, 22+ bot pushes and shared hosted-runner congestion. PR #2935 (stale `push` validation cancellation) was **MERGED 2026-11-23 01:22:19 UTC**, so it is a deployed-code mitigation dependency to verify in representative queue/runner telemetry; do not duplicate it or mistake it for eliminating direct state pushes.

## Proposed contracts

### 1. Versioned state locator

Resolve `StateLocator { schema_version, repo, runtime_ref, specs_repo, specs_ref, min_schema, migration_epoch }` from a single typed configuration per environment. All clients use the same resolver and log the resolved repository, ref and content SHA; no implicit `mctl-gitops` fallback when the new locator is selected. Explicit read-only legacy fallback is permitted *only* during shadow comparison and cannot authorize execution. A client encountering an unknown epoch/ref fails closed.

Stable proposal identity: `service/slug` plus immutable candidate-spec SHA; human-input artifacts and PR links map to this identity; migrate history without rewriting source audit events. State writes use GitHub ref compare-and-swap (create blob/tree/commit, conditional ref update) or equivalent ETag/CAS. On a conflict fetch latest state and re-run transition validation, bounded retries with jitter. Last-write-wins is forbidden for `.status.yaml` and approval fields. Transition keys include workflow run id / attempt id and transition id to make duplicate deliveries idempotent.

### 2. Reviewed specs vs runtime state

The new repo's protected `specs` branch holds proposal content and PR-based amendments. The runtime branch contains mutable status and references immutable `specs` SHA and content digest; a bot runtime token must not directly write protected specs. A new proposed candidate can be generated by investigator, but only **read-only** review and an owner-granted, exact-digest approval can change implementation authority. A proposal amendment advances source commit and invalidates pending approval; old approval grants cannot be reinterpreted against new content. Keep existing behavior of `control.requires_human_approval`, named approver and four-file digest framing from `mctl-agents/orchestrator/proposal_state.py`. Any change to canonical digest framing requires cross-language test vectors (Python, CWFT shell, mctl-api).

Cross-repo invariants: `approved.digest == digest(specs SHA)`, `approved.proposal_id == runtime.proposal_id`, `approved.source_sha == reviewed SHA` and `approved.grant_ref == fresh owner grant`. Implementer re-verifies all four immediately before work and after retries. A stale grant, unavailable refs or an ambiguous double-write returns explicit `blocked/pending_reconciliation`; never accept or run implementation.

### 2a. Cross-store grant and approval reconciliation (P1-1)

**The current implementation is not atomic.** `mctl-api/internal/api/handlers_write.go` around lines 626–635 consumes a grant **before** Argo submit; `cwft-mctl-agents-approve.yaml` separately makes the Git commit under a mutex (around 681–820). The Git commit and the grant ledger cannot participate in one ACID transaction. Therefore 'exactly once' means deduplicated *observable effect* under crash/retry, **not** an assumed single transaction.

**Required proposed command contract (not claimed to exist today):** `ApprovalTransition { proposal_id, reviewed_specs_repo, reviewed_specs_sha, content_digest, migration_epoch, approval_ref, decision_context_digest, command_id, argo_submission_id?, runtime_commit_sha?, outcome }`. The server derives and persists the binding; `command_id` is stable across retries and scoped to grant/proposal/revision/epoch. Operator/user input cannot choose a different approved ref. The durable mctl-api grant/transition ledger is authority, the runtime `.status.yaml` is an eventually consistent projection, and Temporal/Argo execution ids are correlated evidence.

**Explicit states and recovery:**

1. `issued`: authenticated owner/MFA grant exists for exact proposal/ref/digest. No runnable state.
2. `spent_pending_submission`: grant is consumed and a durable command/intent exists **before** attempting dispatch. Its nonce may not be spent again by another command. Implementer remains blocked.
3. `submitted`: verified Argo/Temporal submission id recorded; uncertain HTTP/dispatch responses reconcile by stable operation id against actual platform execution state, not a fresh grant or second run.
4. `state_committed`: a conditional runtime commit recorded exact approved grant, specs SHA/digest, transition id and immutable evidence; no automatic promotion from a lone `accepted` text field.
5. `reconciled`: a read-after-write check confirms command, status, issued grant, lease and (if applicable) Temporal submission agree. Only then may downstream authorization consider the record, and it must still reverify grant plus digest at execution boundary.
6. `unknown/quarantined`: grant spent but dispatch failed or unknown; dispatch succeeded but Git CAS failed; state committed but acknowledgment lost; conflicting approval actor/epoch; missing provenance. Retry reconciliation with bounded schedule, and alert/escalate if uncertain. **No auto-refund/reissue, no fabrication of approval, no implementation while unresolved.**

If the current mctl-api grant ledger cannot store a durable command prior to spending, that is a **separate explicit implementation dependency** to be designed and tested before write cutover. A compensating retry cannot recreate human authority. Owner-controlled recovery decides whether to reissue a grant only after proof of no conflicting implementation. Pending decide-page links bind their original revision and fail closed after amendment or epoch switch unless an audited migration record proves exact equivalence.

**Acceptance tests:** failure injection at *every* boundary (durable intent, consume, submit before response, submit after response, CAS conflict, state committed before ack, retry after worker crash), verify at-most-once implementer effect, and no approved runnable record without reconciled evidence; compare a live older-epoch DevLoop with a brand-new new-epoch proposal.

### 3. Permissions model

- Runtime writer identity installed **only** in the dedicated private state store; it may update `runtime` only after effective branch restrictions are proven (or via a mediated service under option B). It must have no permission in `mctl-gitops` or to protected specs and no admin. Use deny tests against both protected proposal ref and GitOps main. Document whether policy must be enforced by branch rulesets, a mediated writer API, or a dedicated second repo for reviewed content if current GitHub permissions cannot uphold the separation.
- Candidate-proposal author can open a PR against protected `specs` but cannot merge it. Independent reviewer credentials are separate. GitHub-hosted CI guards review and immutable grant/digest binding.
- GitOps credential used for approved configuration changes remains governed by existing PR / Merge Queue. Revoke the old P6 deploy key after cutover; link the permission inventory and rollback to #2543.
- Deny force-push, branch deletion and bypass outside explicitly reviewed exception; do not treat `git add` scoping as an authorization boundary. Require durable logs without leaking tokens.

### 4. Phased migration and rollback

**Legacy-state migration matrix (P1-2):** classify by *authority evidence*, not only by `.status.yaml.status`:

| Original record | New visible state | Execution authorization after migration | Recovery |
|---|---|---|---|
| `proposed` without grant | `proposed` | Denied until owner grant for immutable spec SHA/digest | Preserve proposal and allow fresh review |
| `accepted` with named approver + verifiable matching grant/content digest | `accepted`, with source mapping and grant reference | Only after epoch mapping and reconciled revalidation | If grant source/SHA cannot be proved, quarantine and require owner decision |
| `accepted` legacy incident with absent `control` / approval | `accepted` display plus explicit `unauthorized_legacy_auto_accepted` quarantine | **Denied**, even though `approval_requirement_met` may return true; no implicit autonomy policy | Human triage and new grant through approved flow; never auto-upgrade |
| `accepted` with anonymous/missing grant/ref/digest | Existing status plus `unauthorized_unverified_approval` | Denied | Audit and re-approval, no inferred attribution |
| `implementing` / leased / pending approval decision | Preserve exact activity, lease and original pinned revision | Hold or reconcile to known durable authorization before resume | Drain/epoch fence and compare Temporal/Argo ids, never replay a grant blindly |
| Terminal (`implemented`, `rejected`, `failed`, etc.) | Preserve terminal status and immutable audit | No new implementation from history | Archive/read-only; any reopening requires new authority |

Do not rewrite legacy status to make it look approved. Inventory counts by each row, classify falsey `requires_human_approval` as a gate waiver only, and retain rejected/anonymous/incident diagnostics. Test the actual `incident-*` shape from `run_incident_responder.py` and the separate `execution_authorization` predicate from `proposal_state.py`.

**Human-input fail-closed migration (P2-1):** `mctl-api/internal/gitops/reader.go` ~1879–1887 returns `nil,nil` if its old agents-state root vanishes; `internal/api/handlers_human_input.go` ~175–178 converts this to no loaded requests. Redirect the API to an epoch-versioned **state** reader before removing the old source. A reader with an obsolete epoch, missing root, absent auth, stale cache or unknown migration marker must return typed `unknown/unavailable`, not `[]` or 200 'none pending'. Parallel direct Temporal reader `orchestrator/temporal/activities/human_input.py` also needs ref switch, confidentiality checks and parity tests. Genuine emptiness is permitted only after listing successfully and proving complete, authorized, non-truncated state for that epoch. No silent skip of human-input requests during rollback.

**Receipt schema compatibility (P2-2):** the currently **proposed, not live-gating** ADR 025 `gitops_commit` is a legacy proposal source pointer. Version the artifact binding to `source_repo/source_ref/source_sha/content_digest` with explicit migration provenance; maintain byte-exact historical receipt verification, do not rewrite sealed legacy receipts, and make wrong-source receipts stale or unobservable (never PASS). Align future Tier B receipt adapter independently; migration itself must not activate an ungated approval mechanism.

**Phase A — evidence / compatibility (no writes):** verify grant-command feasibility, legacy record counts and data classification/branch security under the current org plan; source-pin all consumers. Then full anchored inventory, secret scopes (metadata only), GitHub permissions probes using isolated canary, measured queue/CI durations, choose branch/ruleset, define versioned locator and digest vectors. Capture baseline of proposals, statuses, active DevLoops, in-flight approvals, attempts, inbox/human-input, content/history counts. Include old-to-new mapping.

**Phase B — provision and shadow:** after separate GO, establish a private-compatible permission boundary and test forbidden writes; no public publication of human-input payloads. Then create state repo and protected review source under a *separate* explicit infrastructure approval; backfill at known Git SHA; build read-only shadow resolvers; compare digests/status/attempt metadata per proposal. Do not dual-write approvals blindly. Put modern state writer through repeatable conflict simulations; keep all existing production writers unchanged during this gate.

**Phase C — bounded writers cutover:** freeze only affected workloads after acknowledging any spent-but-unreconciled grants, migrate their command IDs and epoch fences; do not switch until old API human-input reads can no longer show false-empty. Then temporarily quiesce only affected state writers at approved boundary; drain/reconcile outstanding approvals and attempts; final immutable snapshot + compare; activate versioned locator and state writer identity; preserve audit/proposal SHAs and marker to reject late legacy writes. Existing read-only DevLoop remains safe or explicitly held. Verify fresh Investigator, Approve (synthetic approval only), Implementer gate (must not start on unapproved), Shepherd, Reconcile and Incident Responder in **test** environment. No production owner grants are fabricated.

**Phase D — remove old authority:** verify GitOps main has **zero** direct bot state commits during representative activity, CI volume declines, cache/decide consistency, and queue throughput improves; revoke legacy main-write deploy key / bypass through #2543; stop reliance on legacy tree and validators only when equivalent new policy checks have proved active; record owner post-cutover sign-off.

**Rollback:** before C, switch readers back to legacy without data loss. At/after C, pause writers/implementation, reconcile new status into a verified, explicitly authorized recovery store, restore client locator only after parity and approval revalidation. **Never** silently enable old direct GitOps-main bot pushes as a rollback strategy; if no safe audited path exists, fail closed and require new owner decision. Test recovery with pending grant, concurrent status transition and digest amendment. Document whether a rollback is one-way at each phase.

### 5. Merge queue monitoring and CI-load behavior

Build a read-only monitor whose implementation matches actual GitHub API fields and required permissions (research gate). Query merge queue state, merge_group workflow runs/check SHA history and main push audit. Correlate a head's rebuild sequence and direct commits, without asserting causality from timestamps alone. Recover prior progress timestamps from durable GitHub evidence (not process memory). Poll approximately every **5 min**; alert:
1. same queue entry rebuilt 3+ times without advancing;
2. queued entries with no meaningful completion/advance for **15 min**;
3. direct bot push to protected branch correlated with invalidated merge-group SHA/checks.
Include PR IDs (head and impacted), workflow/run identity, source SHA(s), merge-group SHA(s), timestamps, counts and correlation confidence. If unavailable mark `unknown`, and separately alert on monitor failure or missed schedule. Add a *delivered* on-call notification route (use an existing approved notifier or owner-specified destination; no unreviewed new secret). Deduplicate by queue-entry id + incident type, send recovery signal when progress resumes.

Don't conflate GitHub runner congestion with just queue rebuilding. The `push: main` full validation floods the shared hosted-runner pool; verify related PR #2935 cancellation scope, concurrent active jobs and stale workflow run count in testing. A healthy queue monitor may still report hosted-runner starvation elsewhere: add congestion telemetry/runbook and require an end-to-end pressure test. No new unconditional GitOps `push`-triggered validation work.

**Monitoring read-only evidence gates (P2-3):** before coding a watcher, record successful *actual* GitHub REST/GraphQL read-only responses (scrub tokens), permitted fields, pagination/cursor semantics, event timestamps, scope of `GITHUB_TOKEN` vs GitHub App token, and 403/404/429 retry behavior. A historical queue rebuild must be demonstrated with head PR, merge-group ref/SHA, original and replacement check runs; a bot push may be labeled `correlated` only if invalidation is backed by explicit predecessor/successor ref evidence, otherwise `suspected/unknown`. Preserve an observable last-progress source across monitor runs; healthy long-running checks should not be called stalled solely from enqueue age. Test deduplicated *delivered* notifications and silent-schedule failure using a synthetic fixture. Successful #2935 cancellation metrics are a parallel runner-saturation check, not proof of causal correctness.

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
6. #2935 merged on 2026-11-23 01:22:19 UTC; measure actual queue/CI/hosted-runner effect and guard against duplicate changes.
