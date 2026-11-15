# Finance Assistant L2 owner-private fake-transport security gates (test-only spike)

## Context

Issue mctlhq/mctl-telegram#1244 asks for a test-only research specification. The specification is
a matrix of application-level (L2) Go tests that run the real `mctl-telegram` components with fake
MTProto transport, in-memory SQLite and synthetic personas. The tests answer one question: can
MCTL's existing Saved Messages owner-control path and agent action/policy mechanisms meet a strict
owner-private delivery contract? The components are the listener extraction, the Saved Messages
history poller, the `/mctl` router, the owner Notifier, `policy.Evaluate` and the agent API
owner-facing handlers. No runtime code may change, and no live account may be touched. The
follow-up comes from the docs-only discovery report
`docs/reports/finance-assistant-owner-private-discovery.md` (#1240, PR #1242). Its section 8 lists
T1-T10 as "NOT EXECUTED", and its section 9 verdict `BOUNDED_EXTENSION_REQUIRED` lists unresolved
checks, among them account-revocation enforcement (T8) and the revision-0 fence skip.

This matters because a finance digest would be the first owner-private feature that carries
third-party financial data. The L1 synthetic arithmetic model from #1240 says nothing about whether
the actual Go code fails closed. This proposal authorizes only the intake artifacts. It defines
exactly which tests a later, separately approved test-only PR would add, how their outcomes are
graded (`PASS | FAIL/GAP | NOT-IMPLEMENTED | CANNOT-OBSERVE`), and how a gap is kept from turning
into a passing test. Parent #325 stays `RESEARCH_ONLY_DEFER`. Nothing here approves a pilot or a
product.

## User stories

- AS the platform owner I WANT reproducible L2 evidence of which owner-private safety invariants
  current code enforces SO THAT a later Finance Assistant decision rests on observed behaviour,
  not on an abstract model.
- AS a security reviewer I WANT every missing control to appear as `FAIL/GAP` or
  `NOT-IMPLEMENTED`, and never as a green test, SO THAT a missing guard is never waived by renaming.
- AS a security reviewer I WANT a negative (mutation) control in the harness SO THAT I can trust
  the assertions to detect a real leak and not pass tautologically.
- AS a Tier 2 implementer I WANT an exact list of test files, fixtures, commands and the outcome
  rubric SO THAT I can build the harness without touching production code.

## Acceptance criteria (EARS)

General
- THE SYSTEM SHALL add only `_test.go` files carrying the build constraint `//go:build l2finance`,
  plus one optional `workflow_dispatch` CI workflow and one results report under `docs/reports/`.
  It SHALL NOT modify any non-test Go file, migration, config, Helm value or deployment.
- WHILE the L2 suite runs THE SYSTEM SHALL use only fake `control.SelfSender` and
  `savedHistoryAPI` implementations, synthetic `*tg.Message` values, an `httptest` agent API and
  in-memory SQLite (`db.Open(ctx, "file:...?mode=memory&cache=shared")` + `db.MigrateCached`), with
  no network, credentials, `TG_API_ID`/`TG_API_HASH` or live account.
- THE SYSTEM SHALL use only the personas Alice (owner), Bob (same-tenant non-owner peer), Carol
  (other tenant owner) and Dana (spare/forward origin). It SHALL use numeric ids that `git grep`
  showed unused, or the package's existing constants (for example `selfTG`, `ownerUID`, `recruit`
  in `internal/agent/listener/extract_test.go`), and it SHALL record the `git grep` check in the
  report.
- WHEN a test case finishes THE SYSTEM SHALL emit exactly one structured result line
  `L2RESULT id=<T#.n> outcome=<PASS|FAIL/GAP|NOT-IMPLEMENTED|CANNOT-OBSERVE> rev=<git sha> evidence=<log-safe summary>`.
- IF a case observes a missing or bypassable guard THEN THE SYSTEM SHALL record `FAIL/GAP`. The Go
  test SHALL pass only while that observation reproduces, and SHALL fail with a "rubric must be
  updated" message once the gap is no longer observed. No case may move from `FAIL/GAP` to `PASS`
  without a reviewed rubric change.
- IF the capability under test does not exist in code (finance job kind, finance command, source
  consent store) THEN THE SYSTEM SHALL record `NOT-IMPLEMENTED` and SHALL write the future
  contract test as a specification in the report. It SHALL NOT stub the missing authorization
  layer.
- IF an assertion cannot be made at the stated layer (for example observing `tg.InputPeerSelf`
  under `internal/telegram.SendToSelfWithRandomID` without a real `*telegram.Client`) THEN THE
  SYSTEM SHALL record `CANNOT-OBSERVE` with the reason and SHALL NOT report the case as `PASS`.

Cases
- T1. WHEN Alice's own unforwarded `/mctl status` arrives in her primary Saved Messages dialog
  (push via `Listener.onMessage` and history via `pollSavedHistory`) THE SYSTEM SHALL produce
  exactly one `EventKindSavedCommand` and one `Router.HandleSavedText` call, and the only send
  SHALL be one `SelfSender.SendToSelf`, with zero peer sends. WHEN `/mctl finance` (or any finance
  verb) arrives THE SYSTEM SHALL answer with `unknownCommandReply`, and the finance-command case
  SHALL be recorded `NOT-IMPLEMENTED`.
- T2. WHEN Bob sends finance-looking text, including `/mctl status` and `/mctl approve <code>`, in
  a DM to Alice THE SYSTEM SHALL record no saved command and make no router call and no SelfSender
  call. The harness SHALL record, as observed behaviour, whether a job bound to Bob's conversation
  can queue `send_owner_summary` (expected: allowed by the `ActionTypeOwnerSummary` short-circuit
  in `policy.Evaluate`). That is a `FAIL/GAP` against the finance owner-invocation contract, not a
  PASS.
- T3. WHILE Carol's account has profile, conversation and notification rows THE SYSTEM SHALL deny
  an Alice-identity request for Carol's conversation (`GetConversation(ctx, aliceUID, carolConv)`
  -> 404), and `DeliverPending` SHALL deliver each notification only with its own `UserID`. The
  finance-source isolation case SHALL be recorded `NOT-IMPLEMENTED`, because no source or consent
  store exists.
- T4. IF a Saved Messages message has `FwdFrom` set, a `SavedPeerID` other than self, or a
  `FromID` other than self, or the message is in a group or chat peer, THEN THE SYSTEM SHALL return
  `ok=false` (or a non-command event) from `ExtractMessage` / `ExtractSavedHistoryMessage` and SHALL
  NOT call the router.
- T5. WHEN the same update is delivered twice, or arrives through both push and history, or
  arrives out of order, THE SYSTEM SHALL produce one router effect. WHEN `DeliverPending` runs
  twice THE SYSTEM SHALL send once, and the persisted `random_id` SHALL be reused on retry. Source
  dedupe (`eventIDForMessage`), random-id reuse (`ClaimOwnerNotification`) and history cursor
  behaviour SHALL be separate sub-cases.
- T6. WHEN a self-authored command has `Out=false` on push and on history after a simulated
  restart (fresh `Listener` on the same store) THE SYSTEM SHALL classify it as an owner command
  exactly once.
- T7. WHEN an owner-facing or reply action carries an `InstallRevision` different from
  `Profile.InstallRevision` THE SYSTEM SHALL deny with `DenyInstallChanged`. WHEN `InstallRevision`
  is 0, set directly or through a job-bound call that omits `job_id` to `handleOwnerFacing`, THE
  SYSTEM SHALL have that observation recorded as `FAIL/GAP` if no denial occurs, with no policy
  change.
- T8. WHILE `GlobalKill` returns true THE SYSTEM SHALL send nothing from `DeliverPending` and SHALL
  leave rows pending. WHEN the profile mode is `off` before queueing THE SYSTEM SHALL deny with
  `DenyModeOff` and SHALL queue no notification. WHEN mode is set to `off` after queueing, or
  `telegram_accounts.revoked_at` is set after queueing and before `DeliverPending`, THE SYSTEM
  SHALL have any resulting send recorded as `FAIL/GAP`.
- T9. WHEN a job attempts to send finance-digest text to a peer via `propose_reply` THE SYSTEM
  SHALL send nothing to the peer immediately in observe mode. Any `DenyCode` returned SHALL be
  recorded. Absence of a finance job kind and of a `never` tier for finance intent SHALL be
  recorded `NOT-IMPLEMENTED`, with the future contract test specified.
- T10. WHEN any of the denials above occurs THE SYSTEM SHALL have its `agent_actions` row
  (`PolicyDecision`, `PolicyReasons`, `Status`) and DenyCode metric checked. A JSON slog capture
  through the production redaction handler (`internal/audit`) SHALL contain no synthetic
  transaction marker string. A missing audit field SHALL be recorded `FAIL/GAP`, not `PASS`.

Negative controls
- WHEN the harness-only mutation variants run (unguarded extraction that feeds a forwarded command
  straight to the router; a `GlobalKill` hook left nil; a leaking SelfSender wrapper that also
  writes to a peer sink; a slog handler without redaction) THE SYSTEM SHALL detect each leak
  through the same assertions the real cases use, and SHALL report `MUTATION-DETECTED`. If a
  mutation goes undetected the suite SHALL fail.

## AMEND: hermetic test execution and independent security gate

These EARS criteria are **required**; they override any ambiguous "no network"
language above without changing the strictly test-only scope.

- WHILE any L2 Go test runs THE SYSTEM SHALL permit only in-process calls,
  loopback TCP for `httptest`, and local Unix sockets; all non-loopback
  outbound network connections, external DNS and real MTProto/Telegram
  clients SHALL be blocked. A test SHALL fail closed if such an attempt
  occurs. Fake `SelfSender`, fake history API, synthetic identities and
  in-memory SQLite remain mandatory. Installing Go dependencies *before*
  test execution does not authorize test-time egress.
- WHEN any L2 run finishes THE SYSTEM SHALL report `harness_status`
  separately from `security_gate_status`, with a machine-validated
  per-case manifest, counts and IDs for `PASS`, `FAIL/GAP`,
  `NOT-IMPLEMENTED` and `CANNOT-OBSERVE`. Missing, duplicate or
  unclassified mandatory results SHALL be errors.
- IF any mandatory case is `FAIL/GAP`, `NOT-IMPLEMENTED` or
  `CANNOT-OBSERVE` THEN THE SYSTEM SHALL explicitly output
  `FINANCE_SECURITY_GATE=BLOCKED` in the Markdown report and any
  manual CI job summary/artifacts **even when `go test` exits zero**.
  The suite's successful exit means only that assertions and negative
  controls executed correctly, not that finance security or a pilot
  is approved. No green check may be labelled a security clearance.
- WHEN an optional manual `workflow_dispatch` test job is added, it
  SHALL have no deployment or product-promotion steps and SHALL visibly
  distinguish harness integrity from the security gate outcome.

## Out of scope

- Any production Go change: no new `/mctl` command, finance job kind, policy or permission rule,
  consent or CSV store, revocation check, or change to the revision-0 fence.
- Real Telegram sends, the real MTProto network, bank/Plaid/OAuth, real statements or merchant
  data, real persons' ids or names, production flags, deployments and customer records.
- Running the suite, opening the test PR, approving or merging as part of intake.
- Changing the #325 verdict or the #1240 verdict, or allowing a Finance Assistant pilot.
- Fixing any GAP found. Fixes need a separate bounded-extension proposal.

## Open questions

- Whether `internal/telegram.SendToSelfWithRandomID` can be driven without a network. Its
  `*telegram.Client` is a concrete gotd type. A no-network `telegram.Options.Middlewares`
  interceptor might work but is unverified. If it does not work, T1's wire-level `InputPeerSelf`
  assertion is `CANNOT-OBSERVE` and only the `SelfSender` seam plus the source pin of
  `SendToSelf` (`&tg.InputPeerSelf{}`, `internal/telegram/sendself.go`) remain.
- Whether the owner wants the optional `workflow_dispatch` CI workflow, or only the documented
  local command. The proposal includes the workflow as a separately reviewable task.
- Whether a job-bound token that omits `job_id` on `/notify/summary` (so the job's revision is
  never loaded) counts as part of T7 or as a separate binding finding. The proposal records it
  under T7 (T7.3).
- Duplicate check: no other L2 or finance proposal appears under
  `agents-state/mctl-telegram/proposals/` besides `issue-1240-spike-finance-assistant-owner-private-de`.
  GitHub issue search was not available in this run, so an issue-level duplicate cannot be
  excluded.
