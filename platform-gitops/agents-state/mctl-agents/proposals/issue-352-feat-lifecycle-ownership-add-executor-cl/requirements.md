# Execution claims, epoch fencing and explicit owner handoff

## Context

ADR-010 (`docs/adr/010-lifecycle-ownership-contract.md`) splits the lifecycle of a
DevLoop entity into two independent facts: **durable ownership** (actor X is
responsible for reaching a terminal state on `(entity, phase)`) and an
**`ExecutionClaim`** (this one concrete worker attempt holds the temporary right
to perform a mutating step right now). Phase 1 (`mctlhq/mctl-agents#351`) shipped
the ownership half only — `orchestrator/lifecycle/{contract,client,policy,rollout,shadow}.py`,
the `lifecycle_ownership` activity in `orchestrator/temporal/activities/lifecycle.py`,
and the `_owner_epoch` bookkeeping in `orchestrator/temporal/workflows/dev_loop.py`.
The ADR's implementation map puts `ExecutionClaim`, the database-clock lease,
epoch fencing and handoff in phase 2, which is this issue.

Without claims the repository still has no fence. `EntityRef.version` exists but
is documented as "becomes a precondition on an execution claim (phase 2, #352)"
and is never used as one. The only lease in the tree is the 130-minute
`.status.yaml` `attempt` block written in `run_implementer.py` around line 1778,
whose holder is written but never compared: `run_shepherd._attempt_is_fresh`
(line 2669) reads `expires_at` and nothing else. Its attempt id is
`os.getenv("WORKFLOW_UID") or str(uuid.uuid4())` — non-deterministic in exactly
the retried-pod case where determinism matters. And the authoritative CAS layer
is half-built: `run_shepherd.merge_pr` already passes `--match-head-commit`
(line 2221), while `run_implementer._push_followup` (line 923) and
`_push_and_open_pr` (line 1662) push with no `--force-with-lease` anywhere in the
repository. So a worker that stalls between "am I still the owner?" and "push"
still lands its write on top of whoever replaced it. This proposal closes that
gap.

## User stories

- AS the DevLoop control plane I WANT at most one worker to hold a mutating
  execution right per `(entity, phase, owner_epoch, entity_version)` SO THAT
  overlapping cron ticks, Temporal retries and pod restarts cannot double-drive
  one pull request.
- AS a shepherd or pr-steward executor I WANT a mutating attempt to abort with an
  explicit fenced outcome when ownership has moved or the PR head has changed SO
  THAT I never push a fix computed against a world that no longer exists.
- AS an operator handing a PR from a dead `DevLoopWorkflow` to the fallback
  shepherd I WANT the handoff to bump a fencing epoch SO THAT the pre-handoff
  executor is invalidated the moment it wakes up, rather than racing the new one.
- AS an operator I WANT claim acquire/reject/release/expire/handoff events that
  name the entity, phase, owner epoch, executor and attempt SO THAT a race is
  explainable after the fact instead of inferred from two interleaved logs.
- AS a reviewer of `mctlhq/mctl-agents#344` I WANT holding a claim to grant
  nothing about merge authority SO THAT a delegated executor cannot merge a PR
  its owner was never permitted to merge.
- AS the Temporal worker I WANT every claim call to happen in an activity SO THAT
  workflow replay stays deterministic.

## Acceptance criteria (EARS)

### Acquisition and mutual exclusion

- WHEN two executors attempt to acquire a claim on the same
  `(entity_kind, entity_id, phase, owner_epoch, entity_version)` concurrently
  THE SYSTEM SHALL grant the claim to exactly one of them and SHALL answer the
  loser with a verdict whose `may_execute` is false and which names the winning
  executor.
- WHEN an executor is refused a claim THE SYSTEM SHALL perform no mutating call
  to GitHub, git or `.status.yaml` for that attempt.
- WHILE a claim is `active` THE SYSTEM SHALL refuse every other acquire for the
  same `(entity, phase)` except a renew by the holding executor.
- IF the claim store answers with anything other than a granted claim — a 5xx, a
  timeout, an unreachable host, an unrecognised payload, an unrecognised claim
  state — THEN THE SYSTEM SHALL classify the answer as `unknown` and SHALL NOT
  treat it as an unclaimed entity.
- WHILE `LIFECYCLE_ROLLOUT_MODE` is at or past `enforce` and
  `LIFECYCLE_OWNERSHIP_REQUIRED` is not disabled, IF a claim verdict is `unknown`
  THEN THE SYSTEM SHALL block the git push and the merge and SHALL leave reads,
  the `.status.yaml` projection and human escalation permitted.

### Fencing

- WHEN a mutating lifecycle action is attempted THE SYSTEM SHALL carry
  `(entity_kind, entity_id, phase, owner_epoch, claim_id, entity_version)` with it.
- IF the ownership row's current epoch differs from the claim's `owner_epoch`
  THEN THE SYSTEM SHALL answer `fenced`, and the executor SHALL abort before
  invoking git.
- IF the claim's `entity_version` differs from the entity's current version — a
  new PR head SHA, or a changed `.status.yaml` content hash — THEN THE SYSTEM
  SHALL answer `fenced` and SHALL require an explicit new claim before any
  further mutation.
- WHEN a follow-up commit is pushed to a PR branch THE SYSTEM SHALL pass
  `--force-with-lease=<branch>:<claimed head sha>` so the push itself fails if
  the remote moved, independently of what the epoch check said.
- WHEN a PR is merged THE SYSTEM SHALL continue to pass `--match-head-commit`
  with the claimed head SHA.
- WHILE an attempt is fenced THE SYSTEM SHALL classify the outcome as a
  non-charging failure that does not consume a `review_attempts` slot, using the
  existing non-charging shape of `FollowupSubprocessError`.
- IF a claim is fenced THEN THE SYSTEM SHALL NOT silently re-acquire against the
  new owner or the new version within the same attempt; it SHALL end the attempt
  and leave the next tick to decide.

### Lease and recovery

- WHEN a claim is acquired or renewed THE SYSTEM SHALL take `lease_until` from
  the store's own clock and SHALL NOT compute it from the worker's local clock.
- WHILE a claim's lease is unexpired THE SYSTEM SHALL treat the claim as held
  even if the holding process has died.
- WHEN a claim's lease expires THE SYSTEM SHALL permit another executor to
  acquire only if the durable ownership row still names an owner whose epoch the
  new acquire matches; an expired lease alone SHALL NOT transfer ownership.
- IF a process restarts and re-derives the same attempt identity THEN THE SYSTEM
  SHALL let it renew its own existing claim rather than be refused by it.

### Idempotency

- WHEN an executor performs a mutating action THE SYSTEM SHALL derive
  `idempotency_key = sha256("{kind}|{id}|{phase}|{owner_epoch}|{attempt}|{version}|{action}")`
  using no wall clock and no random source.
- WHEN a Temporal activity retry, a Temporal replay or an Argo pod restart
  re-derives the same `idempotency_key` THE SYSTEM SHALL return the previously
  recorded outcome and SHALL NOT repeat the effective mutation.
- IF a deterministic attempt identity cannot be derived — no `WORKFLOW_UID` and
  no deterministic fallback — THEN THE SYSTEM SHALL refuse to acquire the claim
  rather than mint a random one.

### Handoff

- WHEN ownership is handed off THE SYSTEM SHALL increment the owner epoch on
  completion, and every claim carrying the pre-handoff epoch SHALL thereafter be
  fenced.
- WHEN a `DevLoopWorkflow` reaches a terminal or dead state and the fallback
  shepherd or reconciler takes the entity THE SYSTEM SHALL invalidate the
  workflow's outstanding claims through the epoch bump.
- WHEN a steward-owned repository needs a review fix THE SYSTEM SHALL let the
  shepherd take a delegated claim under the steward's current epoch, SHALL leave
  the ownership row with the steward, and SHALL re-evaluate merge authority at
  the merge boundary through `orchestrator/lifecycle/policy.merge_authority_for`,
  `run_shepherd._service_mode` and `NEVER_MERGE_SERVICES`.
- WHEN an adoption reconciler adopts a proposal-less PR and hands it to the
  shepherd THE SYSTEM SHALL use the same claim shape with `proposal_ref = ""` and
  SHALL synthesize no proposal and no `.status.yaml`.
- WHEN a review-fix push changes the PR head THE SYSTEM SHALL require the next
  review cycle to take a new claim pinned to the new head.

### Observability and placement

- WHEN a claim is acquired, rejected, renewed, released, expired or fenced THE
  SYSTEM SHALL emit one structured event carrying entity kind, entity id, phase,
  owner epoch, entity version, executor type, executor id, attempt id and claim
  id.
- WHILE running inside a Temporal worker THE SYSTEM SHALL issue every claim call
  from an activity in `orchestrator/temporal/activities/lifecycle.py` and SHALL
  make no HTTP call from `@workflow.defn` code.
- IF a claim call fails for any reason THEN THE SYSTEM SHALL NOT fail the
  workflow; it SHALL decline the claim and let the existing fallback owner keep
  the entity.
- WHILE `LIFECYCLE_ROLLOUT_MODE` is `off` THE SYSTEM SHALL make no claim HTTP
  call, and WHILE it is `observe` THE SYSTEM SHALL record and log claim decisions
  without letting them block any mutation.

## Out of scope

- The mctl-api server side: the `execution_claims` table, its partial unique
  index, the `pg_advisory_xact_lock` transition and the HTTP routes. Those are a
  sibling-repository change; this proposal ships the Python contract, clients,
  call sites and the rollout gate that degrades safely until those routes exist.
- A generic distributed lock service for arbitrary application code.
- Making a short lease the source of truth for durable ownership.
- Making claim holding sufficient for GitHub merge or approval authorization.
- The reconciler over ownership rows (`mctlhq/mctl-agents#353`) and the discovery
  of adoptable proposal-less PRs (`mctlhq/mctl-agents#334`). This proposal ships
  the claim shape those paths use, not their discovery loops.
- Operator recovery tooling (`mctl-api#294`).
- Fixing the `.status.yaml` lost-update race (`mctlhq/mctl-agents#354`).
- Extending claims beyond the `devloop-proposal`/`implement` and
  `pull-request`/`review-remediation` pairs. `deploy-watch`, `investigate` and
  `await-approval` stay reserved and unimplemented, as in ADR-010 section 3.

## Open questions

- **Wire status for a fence.** ADR-010 section 6 says the server returns
  "409 FENCED", but a 409 is also the natural status for "someone else holds an
  active claim", and the two have different consequences: fenced ends the attempt
  without charging it, held-by-other means stand down and retry next tick. This
  proposal reads a `code` field on mctl-api's existing `{"error": ...}` envelope
  (`fenced` vs `claim-held`) and classifies a 409 with no recognised code as
  held-by-other — the fail-closed direction, since it neither licenses execution
  nor charges an attempt. If mctl-api prefers 412 for the precondition failure,
  only `claim_answer_from` changes.
- **Proposal `entity_version`.** ADR-010 section 2 defines it as the
  `.status.yaml` content hash. The exact hash input is unspecified, and
  `proposal_state.py` writes no `ownership:` projection block today — ADR-010
  section 7 describes one, but nothing implements it. This proposal hashes the
  canonicalised mapping with `updated_at`, `updated_by` and any future derived
  `ownership:` block excluded, so that a bookkeeping write cannot fence its own
  writer. If the projection lands later with a different shape, only the hash
  input changes.
- **Deterministic attempt fallback.** ADR-010 section 8 forbids a UUID and
  permits "a deterministic fallback" without naming one. This proposal uses
  `sha256("{service}|{slug}|{owner_epoch}|{attempt_ordinal}")`, where the ordinal
  is the count of recorded attempts for that epoch, and refuses to acquire when
  even that cannot be computed.
- **Lease durations.** ADR-010 section 3 gives liveness and progress bounds for
  ownership (130 min / 130 min, 10 h / 48 h) but no claim lease length. This
  proposal proposes a claim lease of 130 minutes for `implement` (matching the
  lease it replaces) and 30 minutes for `review-remediation` (one
  `MERGE_POLL_INTERVAL`), both overridable by env, and treats these as tunables
  rather than contract.
- **Delegated-claim executor identity for the pr-steward.** The steward is a
  headless `claude -p` process in the claude-remote pod; whether it can present a
  stable executor id across restarts is not established in this repository. If it
  cannot, its claims are effectively single-attempt and expire rather than renew,
  which is safe but wasteful.
