# P4.3 Fork promotion: observe, baseline eval, explicit owner promotion

## Context

Issue #1044 (epic #1002, P4; depends on P4.2 #1043) asks that a user-authored
private fork of a catalog assistant can never run `guarded` (autonomous
sends) on the owner's account without evidence. A fork may keep the base's
authority exactly and still change behaviour completely through its
instructions, so an authority diff alone is not enough. Promotion to
`guarded` therefore needs two gates, both bound to the exact fork digest: a
passing baseline automated eval (the C1 harness: classification, leaks,
binding, adversarial fixtures) and an explicit owner promotion that shows the
authority diff together with the eval result. A new fork version drops back
to `observe`.

The design is already accepted by the owner and recorded in
`docs/assistants/adr-forks.md` ("Promotion (P4.3)" and "P4.3 decisions",
2026-10-31). Slice S1 (`internal/agenteval`: suites, `suite_digest`,
`expected_decision`, fake API, guarded dry run, scorer, `RunBinding`) is
merged. This proposal covers the remaining slices: **S2** (server-side eval
runs) and **S3** (promotion and revocation, plus lifting the P4.2
"observe only" refusals when a promotion exists).

## User stories

- AS an account owner with a private fork I WANT to request a baseline eval of
  one fork version from the manage page SO THAT I get evidence of how it
  behaves before trusting it with autonomous replies.
- AS an account owner I WANT to promote a fork version only after seeing its
  authority diff against the base, its instructions and its eval result SO
  THAT I make an informed, explicit decision.
- AS an account owner I WANT any new fork version to start in observe again
  SO THAT an edited prompt never inherits a promotion it did not earn.
- AS an account owner I WANT to revoke a promotion at any time SO THAT I can
  take autonomy away immediately.
- AS the platform operator I WANT eval runs to be rate-limited, scored by the
  server and unable to cause real effects SO THAT the eval cannot be forged by
  a user, cannot spend unbounded model budget, and cannot touch Telegram.
- AS the platform operator I WANT a global switch
  (`ASSISTANT_FORK_GUARDED_ENABLED`, off by default) SO THAT I can degrade all
  forks to observe at once.

## Acceptance criteria (EARS)

Fork creation and versions

- WHEN a fork version is created by `fork_assistant` or `update_fork` THE
  SYSTEM SHALL store it with `promotion = observe`.
- WHILE a fork version's promotion is not `promoted` THE SYSTEM SHALL refuse
  to install it, or to update the install of it, in `guarded` mode
  (`checkForkInstall`), and SHALL refuse the claim for an install that pins it
  in `guarded`.
- WHEN the install pin moves to another fork digest while the mode is
  `guarded` THE SYSTEM SHALL refuse the change unless the new digest is
  promoted; it SHALL NOT lower the mode silently.
- THE SYSTEM SHALL NOT use any count of approved drafts as a promotion
  criterion.

Eval runs (S2)

- WHEN the owner requests an eval run from the manage page with the browser
  Telegram sign-in credential THE SYSTEM SHALL create a run bound to
  `(user_id, fork_digest, base_digest, suite_digest, harness_version)`, with
  the digest taken from the stored fork, never from the request.
- IF the request comes from any other credential (for example an MCP
  client's `account:manage` token) THEN THE SYSTEM SHALL refuse it and change
  nothing.
- IF the fork's base has no suite THEN THE SYSTEM SHALL refuse the run
  (`no_suite`); IF the fork has no `propose_reply` THEN THE SYSTEM SHALL refuse
  it (`nothing_to_promote`).
- IF a request would exceed 1 queued-or-running run per account, 3 runs per
  account per 24 h, 20 runs per day globally, or 2 scored runs per digest
  (the second only after a failed first, none after a pass) THEN THE SYSTEM
  SHALL refuse it and change nothing.
- WHEN the agent worker claims an eval task THE SYSTEM SHALL do so only while
  the real-job queue is empty, render the fork itself from `assistant_forks` by
  `(user_id, digest)` with the suite's install values and no `ownerNotes`,
  and issue a token with audience `agent-eval` bound to that task and
  attempt.
- WHILE serving an eval task THE SYSTEM SHALL route it only to
  `internal/agenteval` handlers, which have no path to the executor or to
  Telegram, and SHALL refuse `agent-eval` tokens on real agent routes and
  `agent`/`agent-job` tokens on eval routes.
- WHEN all fixtures of a run finish THE SYSTEM SHALL compute the verdict with
  `agenteval.Score` from effects observed on its own eval routes, never from a
  value the worker reports, and store `passed` or `failed`.
- IF a run is unfinished after 24 h, cancelled (fork version deleted, account
  purged), or incomplete THEN THE SYSTEM SHALL mark it `expired`,
  `cancelled` or `incomplete`, which never pass and do not count as scored.
- THE SYSTEM SHALL store per fixture only id, category, action, flags,
  leak-marker ids and cost, never model output text, and SHALL delete runs
  with the account.

Promotion (S3)

- WHEN the owner submits the promote form with the browser sign-in
  credential, `account:manage`, an `auth_time` no older than 15 minutes, the
  ticked acknowledgement, the typed slug, the digest, the eval run id and
  `expected_revision` THE SYSTEM SHALL, in one transaction under the
  account's fork lock, re-check that the run is the latest scored run for that
  digest and passed, that its binding matches the fork's
  `(user_id, digest, base_digest, suite_digest, harness_version)`, that the
  base lifecycle is `published`, and that `ASSISTANT_FORKS_ENABLED` and
  `ASSISTANT_FORK_GUARDED_ENABLED` are both on, and only then set
  `promotion = promoted`.
- IF there is no passing scored run for that digest THEN THE SYSTEM SHALL
  refuse the promotion and change nothing.
- IF the submitted run is bound to a different digest (or base, suite,
  harness or account) THEN THE SYSTEM SHALL refuse the promotion and change
  nothing.
- IF the access token has no `auth_time` claim, or `auth_time` is more than
  15 minutes old THEN THE SYSTEM SHALL refuse and send the owner through the
  Telegram sign-in again.
- WHEN the "switch my install to guarded now" checkbox is ticked THE SYSTEM
  SHALL change the install mode in the same transaction and under the same
  `expected_revision`; any mismatch SHALL refuse both.
- THE SYSTEM SHALL show on the promote page the fork reference, the writing
  client and time, the base and its lifecycle, the authority diff against the
  base, the full instructions (collapsed) with a diff against the last promoted
  version, the eval result gate by gate, and the statement that `ownerNotes`
  and install values are not covered; the page and its API SHALL send
  `Cache-Control: no-store`.
- WHEN a fork version is promoted or revoked THE SYSTEM SHALL append a row to
  `assistant_fork_promotion_events` (eval run id, client id, token jti), audit
  the fork reference and run id (never the text), and alert the owner in the
  bot chat.
- THE SYSTEM SHALL NOT offer promotion through any MCP tool or `/mctl`
  command.

Runtime

- WHILE an install pins a promoted fork digest in `guarded` mode, and
  `ASSISTANT_FORK_GUARDED_ENABLED` is on, THE SYSTEM SHALL run it guarded: the
  claim accepts it and every `policy.Evaluate` caller sets
  `ForkPromoted = true`.
- IF the promotion lookup errors THEN THE SYSTEM SHALL treat the fork as not
  promoted.
- WHILE `ASSISTANT_FORK_GUARDED_ENABLED` is off THE SYSTEM SHALL treat every
  fork's effective mode as `observe` everywhere, including the executor's
  send-time check, and SHALL refuse promotion.
- WHEN the owner revokes a promotion (needs only `account:manage`) THE SYSTEM
  SHALL set `promotion = revoked` and, if the install pins that digest in
  `guarded`, set the mode to `observe` in the same transaction; an auto-send
  queued before the revocation SHALL be held by the send-time check.
- WHILE the base is `deprecated` THE SYSTEM SHALL keep an existing promotion
  effective and refuse new ones; WHILE it is `disabled` THE SYSTEM SHALL stop
  new jobs as for every fork.

## Out of scope

- Slice S1 (`internal/agenteval`), already merged.
- Suites for bases other than those already shipped under
  `assistants/<name>/eval/`; authoring new suites.
- A per-fork admin kill switch (ADR decision 5: none for now).
- Any change in mctl-api or the registry (ADR: "mctl-api: nothing in P4").
- A promotion "epoch" for changing a suite under a running base.
- Certifying `ownerNotes` or install values.
- Enabling `ASSISTANT_FORKS_ENABLED`, `ASSISTANT_FORK_EVAL_ENABLED` or
  `ASSISTANT_FORK_GUARDED_ENABLED` in production gitops values (a separate
  operator change).

## Open questions

- The ADR fixes the S2 limits but not where the global "20 per day" counter
  lives with more than one server replica. Assumption: a DB count over
  `assistant_fork_eval_runs.created_at` inside the insert transaction, no
  in-memory counter.
- How the agent worker learns of eval tasks: the ADR says "claims eval tasks
  only when its real-job queue is empty" but not whether that is a new claim
  route or a flag on the existing claim. Assumption: a separate
  `POST /api/agent/v1/eval/claim` route that the server answers with
  `204` while real jobs are pending, so the real claim path is unchanged.
- Which "client wrote this version" the promote page shows: `assistant_forks`
  has no writer column today. Assumption: add a nullable `written_by_client`
  column in S3, filled from the MCP identity's client id for new writes;
  older versions show "unknown".
- `assistants/hr-recruiter/eval/` holds suites for 0.1.0 and 0.1.1, pinned
  by `activeSuiteDigests` in `internal/agenteval/agenteval_test.go`. Whether
  the registry's published `hr-recruiter` version is one of these needs a
  check before the preview run. A base without a suite stays unpromotable
  (ADR decision 11).
