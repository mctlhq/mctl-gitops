# Stop mctl-agents state writes starving GitOps Merge Queue — revision 2

## Decision and problem statement

**Owner decision (2026-11-23, mctl-gitops#2931): GO_RESEARCH / DESIGN for options 2 + 4.** The target is a separately permissioned repository, provisionally `mctlhq/mctl-agents-state`, for agent-generated proposal and operational state; merge-queue starvation monitoring is required. This is **not** approval to implement, merge or deploy. The separate-repository migration is **in scope**, not a follow-up. Batch commits, increased queue parallelism and queue-aware push deferral are not substitutes.

Observed 2026-11-22: many `chore(agents)` direct commits to `mctl-gitops/main` invalidated merge-group heads (#2923), blocked #2924/#2927, and triggered numerous heavyweight `validate-manifests.yml` push jobs across the organization's shared GitHub-hosted runner quota. See #2931 evidence and follow-up comment on hosted runners, plus in-flight mitigation PR #2935. A red workflow alone is not a reliable page to the operator. We must eliminate direct agent-state pushes to `mctl-gitops/main` and provide actionable alerts, while preserving content-bound human approval.

## Scope and invariants

1. **Canonical target:** migrate agent runtime state and generated proposal artifacts currently under `platform-gitops/agents-state/**` into a **separate** repository. Keep `mctl-gitops/main` only for GitOps desired-state declarations, workflows and migration configuration. No automated agent status write may advance `mctl-gitops/main` after cutover.
2. **Trust separation:** proposal content (`requirements.md`, `design.md`, `tasks.md` and optional `proposed-content.md`) is reviewable and immutable for a given approved revision; operational `.status.yaml`, attempts, review status and inbox are mutable. The design SHALL explicitly isolate bots that publish runtime status from the protected review/approval source and define its branch/ruleset design. A repository-scoped key alone is not path-scoped.
3. **Approval invariants:** no agent write is an owner approval; no missing, anonymous, mismatched or stale `approval.approved_by` / `approval.content_digest` may enable implementation. `control.requires_human_approval` stays fail-closed. Review grants bind to exact content digest, proposal identity and immutable Git revision, and are invalidated by amendment or migration drift.
4. **No automatic authority expansion:** no admin bypass, no Merge Queue bypass, no automatic owner approval, no implementer start from this design authorization. Existing writers remain functioning until explicit phased rollout / evidence / rollback approval.
5. **No duplicate work:** linked #2543 deploy-key hardening and PR #2935 push-run concurrency cancellation are dependencies or adjacent mitigations, not new implementation issues; `mctl-gitops#2931` owns the migration proposal.

## User stories

- AS an operator I WANT workflows to record status during a DevLoop burst without writing to `mctl-gitops/main` SO THAT valid queued pull requests can complete checks.
- AS an approver I WANT review grants bound to exactly the immutable proposal I saw SO THAT migrations, retries, races and amendments cannot cause unreviewed implementation.
- AS a security maintainer I WANT the runtime writer's credential limited to an isolated repository and branch SO THAT a stolen agent deploy credential cannot advance GitOps desired state.
- AS an on-call operator I WANT 3-rebuild, 15-minute no-progress and causal push alerts SO THAT I can act before the 120-minute queue eviction.
- AS a workflow maintainer I WANT measured cutover, idempotent writes, reconciliation and a tested rollback SO THAT operational status is never silently lost or duplicated.

## Acceptance criteria (EARS)

### Repository and migration

- R1. WHEN migration is activated THE SYSTEM SHALL use a separately provisioned `mctlhq/mctl-agents-state` repository (or an explicitly owner-approved equivalent); `mctl-gitops/main` SHALL no longer receive writes of `platform-gitops/agents-state/**` by agent workflows. A branch *within mctl-gitops* does **not** satisfy this criterion.
- R2. BEFORE cutover THE SYSTEM SHALL inventory **every** reader, writer, poller, validator, CLI, API and workflow referring to `agents-state` or its GitHub source/ref, with repository/path/evidence, owner, transition mode and validation test; an unknown consumer blocks GO_CUTOVER.
- R3. WHEN proposal artifacts are generated or amended THE SYSTEM SHALL publish the immutable review candidate through a protected, independently reviewed path (e.g. a protected `specs` branch in the new repository, with bot-authored PRs) distinct from the runtime-status writer target (e.g. `runtime` branch). No bot credential used for runtime status SHALL be able to directly update protected reviewed proposal content.
- R4. WHEN a proposal is accepted THE SYSTEM SHALL require the exact audited human authorization referencing the reviewed proposal digest and source commit; missing, changed, anonymous, cross-repo-stale or unbound approvals SHALL fail closed. Retried approvals SHALL be idempotent and SHALL NOT start implementation twice.
- R5. WHEN any agent workflow writes status THE SYSTEM SHALL use optimistic commit/ref updates (or equivalent CAS), bounded retry/backoff, deterministic idempotency keys and explicit failure outcomes; concurrent investigator, implementer, approve, shepherd and reconcile updates SHALL neither overwrite newer status nor lose unrelated state. The durable commit identity SHALL be logged.
- R6. WHEN the target repository or credentials are unavailable THE SYSTEM SHALL expose a retriable/unavailable state and never falsely report a persisted approval, status transition or successful implementation. No implicit fallback to direct writes to `mctl-gitops/main` after cutover.
- R7. BEFORE switching writers THE SYSTEM SHALL complete a checksum/inventory backfill, prove source-to-target parity, run shadow reads and conflict/replay tests, and verify an owner-defined maximum freshness lag. The cutover SHALL be gated by an explicit independent review plus separate owner GO_CUTOVER.
- R8. DURING migration THE SYSTEM SHALL provide an auditable mapping of old path/commit/SHA to new proposal identity/review ref/status ref; older active DevLoops SHALL continue safely or fail closed rather than approve an unbound record.
- R9. WHEN rollback is declared THE SYSTEM SHALL support a tested reader/writer rollback or pause with reconciliation and without re-enabling unsafe direct pushes. Rollback SHALL preserve approved digest and attempt/approval history; non-reversible states must cause a fail-closed operator hold.

### Permissions and security

- R10. THE SYSTEM SHALL use separate least-privilege credentials for repo runtime writes, protected proposal publishing, and GitOps configuration reads. A negative authorization test SHALL prove the runtime credential cannot push to `mctl-gitops/main` **or** the new repository's protected reviewed-proposal ref; revoke the old P6 direct-write deploy key after cutover with #2543 evidence.
- R11. THE SYSTEM SHALL protect force-pushes, branch deletion and unreviewed approval-material edits; map GitHub App / deploy-key repository-level capabilities, ruleset bypass actors, and CI enforcement with tests of effective permissions, not merely template `git add` path guards.
- R12. THE SYSTEM SHALL maintain audit chain `proposal_id → reviewed content SHA/digest → owner grant → consumed transition → implementer attempt/PR` across all repository boundaries; stale or unresolvable references block execution.

### Queue and CI observability

- R13. WHEN a queue entry is rebuilt at least **3 times** without progressing THE SYSTEM SHALL emit a deduplicated actionable alert naming head PR, affected queued PRs, original and rebuilt merge-group SHA(s), offending push SHA, bot identity and workflow correlation (or explicitly `unknown` when attribution is unavailable).
- R14. WHEN entries wait but **no meaningful queue progress occurs for 15 minutes** THE SYSTEM SHALL alert; age alone is not equivalent to progress. Monitoring SHALL distinguish healthy long-running checks from repeated invalidation and shall have an explicit false-positive policy.
- R15. WHEN a bot push to a protected branch invalidates merge-group checks THE SYSTEM SHALL correlate the push with invalidated runs where evidence supports causality and alert, including after the migration; non-causal temporal coincidence must be qualified.
- R16. WHEN monitoring cannot read API evidence or misses its schedule THE SYSTEM SHALL emit an `unknown/monitoring-degraded` signal, not green; alert routing SHALL notify a named on-call channel rather than rely solely on an unobserved red workflow. Detection target: 5-minute evaluation cadence with a 15-minute no-progress threshold; document API quota and delay assumptions.
- R17. THE SYSTEM SHALL verify GitHub GraphQL/REST query shapes, API permissions and pagination against live read-only fixtures before implementation; unit tests SHALL pin empty queue, rebuild counting, stale/deleted head, rate limiting, missing permissions, monitoring outages and SHAs/correlation.
- R18. BEFORE declaring success THE SYSTEM SHALL verify the bot-generated `push` workload drops from GitOps `main`, stale CI runs are canceled or bounded (respect #2935), merge-group jobs finish in at least one representative synthetic DevLoop burst, and unrelated repositories do not suffer the same hosted-runner starvation.

## Exclusions

- No implementation in this revision; these are design and acceptance documents only.
- No wholesale changes to release image bumps, GitOps desired state or queue-policy bypass.
- Queue-aware deferral is an optional short-lived mitigation only if separately justified with expiry, risk, proof of no approval latency regression, and its own GO. It cannot satisfy R1 or R10, and is not part of the required end state.
- Do not change `max_entries_to_build` or queue timeout as the primary repair; settings may be evaluated separately after evidence.

## Evidence and unresolved design gates

- **Verified repo anchors:** `mctl-api/internal/gitops/reader.go` maintains a GitOps mono-repo clone; `mctl-api/internal/api/handlers_devloop_decide.go` binds decisions to approval/context/content digests; `mctl-agents/orchestrator/temporal/activities/gitops_state.py` reads the GitHub tree under the GitOps repo; `mctl-agents/orchestrator/proposal_state.py` defines the 4-file digest; `mctl-gitops/scripts/validate-agents-state-approval.py` directly validates the old tree; the CWFTs commit status into GitOps (`design.md` inventory).
- **To verify before GO_IMPLEMENT:** exhaustive repository-wide usages beyond those anchors, exact REST/GraphQL scopes, whether GitHub native rulesets can enforce both branch roles with current GitHub plan, real approval/decide workflow compatibility, recovery when an approval is pending across cutover, rollback after a protected proposal revision changes.
- **Related:** mctl-gitops#2931, #2543, #2935, mctlhq/.github#351, and `docs/runbooks/proposal-approval-content-digest.md`.
