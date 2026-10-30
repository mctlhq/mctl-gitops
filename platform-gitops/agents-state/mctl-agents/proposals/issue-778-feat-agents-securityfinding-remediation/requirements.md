# SecurityFinding remediation and exact-revision verification runner (.github#209 slice 2)

## Context

mctlhq/.github#209 decided `ADD_SECURITY_FINDING_CONTRACT`
(`tests/fixtures/spike_manifests/security-finding-lifecycle.yaml`, follow-ups
mctl-api#774, mctl-agents#778, mctl-gitops#2103). The normative
`SecurityFinding v1` contract (`SecurityFinding -> SecurityOccurrence ->
RemediationAttempt[]`) is owned by mctl-api#774. This issue is the
mctl-agents slice: start remediation for ONE affected `SecurityOccurrence`
through the existing WorkItem / execution-request / DevLoopWorkflow path, bind
the landed commit to the active attempt, and run a bounded verification against
that exact revision/artifact before the occurrence can become `resolved`.

It matters because "PR merged" is not evidence that a vulnerability is gone.
Without a verification step bound to the landed revision, MCTL would report
fixes it never observed, and stale or replayed scanner traffic could flap
occurrences between resolved and reopened. All state lives in mctl-api; this
slice is a client and a runner, never a second store or approval system.

## User stories

- AS a platform operator I WANT to start remediation for one affected
  occurrence SO THAT the fix goes through the same governed WorkItem/DevLoop
  approval path as any other change.
- AS a security owner I WANT an occurrence to stay `awaiting_verification`
  after merge until a verifier observes absence on the landed revision SO THAT
  "resolved" means "observed fixed".
- AS an auditor I WANT every remediation cycle and every verification result
  preserved as history SO THAT a regression never erases how an earlier fix was
  proven.
- AS a platform maintainer I WANT verification strength to come from the
  authenticated provider channel, never from payload text, SO THAT a hostile
  provider cannot resolve or reopen anything by wording.

## Acceptance criteria (EARS)

Start remediation
- WHEN an operator or dispatcher requests `start_remediation` for an
  occurrence THE SYSTEM SHALL call the #774 start-remediation route for that
  occurrence id with a deterministic idempotency key derived from
  (occurrence id, occurrence state version) and SHALL record the returned
  `RemediationAttempt` id together with the existing WorkItem id and
  execution-request id.
- IF the occurrence already has an active `RemediationAttempt` THEN THE SYSTEM
  SHALL return a deterministic refusal (or the replayed existing attempt, per
  #774's answer) and SHALL NOT create a WorkItem, execution request or DevLoop.
- WHEN two occurrences of the same finding are each requested THE SYSTEM SHALL
  produce two independent attempts with independent WorkItems/DevLoops.
- THE SYSTEM SHALL reference existing WorkItem (`wi_`), execution request
  (`xr_`) and execution (`we_`) identities and SHALL NOT introduce any new
  approval mechanism; every DevLoop it starts still waits for the existing
  human approval.

Merge is not resolution
- WHEN a DevLoop whose input carries a remediation attempt observes its PR as
  merged THE SYSTEM SHALL bind `PRState.merge_commit` (and, where #774 asks
  for it, the immutable artifact digest) to the active attempt through the
  #774 API and SHALL request the occurrence transition to
  `awaiting_verification`.
- THE SYSTEM SHALL NOT request `resolved` as a consequence of a merge, an
  implementer completion, or a DevLoop completion.
- IF the PR is closed unmerged THEN THE SYSTEM SHALL leave the attempt for
  #774's policy (no landed-revision binding).

Verification runner
- WHEN an occurrence is `awaiting_verification` THE SYSTEM SHALL select only
  strategies allowed for the occurrence's authenticated provider channel by
  #774 policy: scanner rerun, Runtime Assurance replay, deterministic
  regression test, provider fixed claim (weak), manual evidence (only where
  policy allows).
- WHEN a strategy reports `absent` at a strength meeting the policy threshold
  and bound to the attempt's landed revision/artifact THE SYSTEM SHALL submit
  the verification evidence and request `resolved`.
- WHEN a strategy reports `present` THE SYSTEM SHALL submit the evidence and
  request that the occurrence remain in / re-enter remediation.
- IF a strategy errors, times out, exceeds its budget or is unavailable THEN
  THE SYSTEM SHALL record `unverifiable` and SHALL NOT request `resolved`.
- IF verification evidence is bound to a revision/artifact other than the
  active attempt's landed binding THEN THE SYSTEM SHALL reject it locally and
  SHALL NOT submit it as resolving evidence.
- IF the only evidence is a provider `fixed` claim THEN THE SYSTEM SHALL NOT
  request `resolved` under default policy.
- WHILE running a strategy THE SYSTEM SHALL bound it by wall-clock timeout and
  attempt count and SHALL treat exhaustion as `unverifiable`.

Regression / reopen
- WHEN new evidence for a resolved occurrence is received THE SYSTEM SHALL
  submit it to the #774 API with its observation identity and revision
  binding and SHALL let #774 decide reopen; the runner never sets state
  directly.
- IF the evidence is bound to a revision that #774 / repository identity
  evidence shows is not a descendant of the resolving revision (including
  the pre-fix revision) THEN THE SYSTEM SHALL NOT request a reopen.
- IF ancestry cannot be established THEN THE SYSTEM SHALL treat the
  relationship as unknown and SHALL NOT assume descendant.
- WHEN the same observation is redelivered THE SYSTEM SHALL submit it with the
  same observation idempotency key so that it counts at most once toward any
  confirmation threshold.
- WHEN remediation starts again after a reopen THE SYSTEM SHALL create a new
  `RemediationAttempt`; earlier attempts and their verification evidence SHALL
  remain readable and unchanged.

Trust boundary
- THE SYSTEM SHALL derive verification strength only from the provider/adapter
  identity and allowed semantics returned by #774 for the authenticated
  channel, never from a provider-controlled payload string.
- THE SYSTEM SHALL treat provider title, description, severity and suggested
  fix text as untrusted data: redacted and bounded via
  `orchestrator.redaction`, never used to select a transition, a strategy, a
  tool permission or an approval.
- WHERE a Runtime Assurance replay is used THE SYSTEM SHALL count it only when
  the referenced `AssuranceFinding` / run / result validate through
  `orchestrator.runtime_assurance` and are bound to the landed target
  revision, at the strength #774 configures for that source.

Auditability and rollout
- THE SYSTEM SHALL perform every transition and evidence write through the
  #774 API, with the authenticated mctl-agent principal, and log the request
  id, attempt id and evidence id.
- IF the #774 API is unreachable or answers ambiguously THEN THE SYSTEM SHALL
  treat the answer as unknown, write nothing else, and never treat it as
  "no active attempt".
- WHILE `SECURITY_REMEDIATION_ROLLOUT_MODE` is `off` (the default) THE SYSTEM
  SHALL make no #774 call and behave exactly as today.

## Out of scope

- Provider webhook endpoint, configuration and secrets (mctl-gitops#2103).
- Any scanner implementation; the runner only invokes configured adapters.
- Security UI.
- Policy / approval redesign; no auto-merge or production auto-deploy.
- Changing Runtime Assurance contracts (#151, ADR 022/023) or its replay
  engine; this slice only consumes a confirmed replay.
- Defining the `SecurityFinding v1` schema, state machine, confirmation
  thresholds or ancestry policy; those are mctl-api#774's.

## Open questions

- Dependency gate: mctl-api#774 is not visible from this clone. Route names,
  field names, the state vocabulary (`awaiting_verification`, `unverifiable`,
  `resolved`), and whether a regression reuses or creates a WorkItem are
  assumed from the issue text. Implementation MUST NOT start until #774 is
  merged/released; all route strings are isolated in one `ROUTES` table so a
  rename is one line.
- Does #774 enforce "at most one active attempt" server-side (expected) with a
  named refusal code, or must the client pre-check? This design relies on the
  server and only adds a read-before-write for a friendlier message.
- Who resolves ancestry (descendant-of-resolving-revision): #774 server-side
  from repository identity evidence, or the runner via the GitHub compare API?
  Assumed #774 decides; the runner supplies revision identity only and never
  infers descendant from "SHA differs".
- Which scanner adapters exist for "scanner rerun on exact revision"? None
  exist in mctl-agents today; the runner defines an adapter protocol and ships
  only Runtime Assurance replay, deterministic regression test (CI check on
  the landed SHA) and provider-claim adapters. Real scanner adapters are
  follow-ups.
- Artifact identity: for container-image occurrences, where does the runner
  obtain the immutable digest of the landed build (deploy observation in
  `DevLoopWorkflow._observe_deploy`, or #774)? Assumed optional; commit SHA is
  always bound.
- Trigger for verification: a new Temporal schedule sweeping
  `awaiting_verification` occurrences vs. an inline step after the DevLoop
  merge. This design does both: inline best-effort after merge, plus a sweep
  that is authoritative.
