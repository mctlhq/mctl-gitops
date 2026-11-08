# Tasks: issue-1240-spike-finance-assistant-owner-private-de

All tasks are research and documentation. None modifies mctl-telegram runtime code,
gitops, flags or deployments.

- [ ] 1. Pin and resolve versions: record the mctl-telegram SHA (`8ab82c82...` or newer), map gitops image tag `0.135.0` (services/labs/mctl-telegram/values.yaml) to its commit, and note mctl-api's SHA. — DoD: the report header lists all SHAs and the tag-to-SHA mapping, or marks it "unknown".
- [ ] 2. Evidence matrix (depends on 1): `sendself.go` SendToSelf*, `notifier.go` Reply/DeliverPending, `extract.go` ExtractMessage/classifySavedCommand, `history.go` pollSavedHistory, `router.go` HandleSavedText command set, `agentapi/actions.go` handleOwnerFacing, `policy.go` Evaluate ordering, `executor.go` stale-install checks, `assistant.go` audience/onlySenders/TierNever, `assistantinstall/service.go` revisioned Patch. — DoD: each row is labelled implemented/configured/tested/unknown with file:symbol and test-file references, cross-checked against #325 D2.
- [ ] 3. Threat model and data-flow diagram (depends on 2). — DoD: a Mermaid diagram plus a table of every edge with its fence or "GAP". Includes the peer-triggered `send_owner_summary` leak counterexample and deny-by-default for non-InputPeerSelf destinations.
- [ ] 4. Option analysis: Saved Messages vs bot owner DM vs workspace launcher; CSV-only vs no-ingestion educational. Describe (do not implement) the smallest extension: owner-invoked job kind, ConversationID==0 policy rule, consent-grant revision fence, revoke-tombstones-pending-notifications. — DoD: a comparison table with fences, gaps and effort for each option.
- [ ] 5. CSV/privacy risk matrix: encryption at rest (`internal/crypto`), size caps (cf. `MediaUploadMaxBytes`), parser safety, merchant/memo prompt injection, redaction (`internal/audit/redact.go`), traces, retention/backup deletion; read mctl-api upload/retention code read-only. — DoD: a matrix where each cell is cited or "unknown".
- [ ] 6. Vendor/region benchmark from the three primary URLs in the issue, plus a separate search for Montenegro open-banking providers (no credential linking). — DoD: every claim has a URL and access date. Montenegro/EEA/UK matrix with "unknown" where unverified.
- [ ] 7. Governance/cost: #1048 connector trust, #1088 managed runtime/soak, #309 shared-memory limits; budget, retention and incident assumptions. — DoD: a section listing gates as unchanged and naming no production authorization.
- [ ] 8. L2 test plan (depends on 3, 4). — DoD: each test below specified with setup, stimulus, expected deny/allow and audit row, using fake SelfSender, fake MTProto updates, in-memory SQLite and personas Alice/Bob/Carol/Dana. Marked "not executed".
- [ ] 9. Final report and verdict (depends on 2-8): exactly one outcome (preliminary BOUNDED_EXTENSION_REQUIRED), the smallest next owner decision, repos, dependency gates, and stop reasons. Published as a PR to mctlhq/.github docs/spikes/. — DoD: the PR is open for independent review. #325 remains RESEARCH_ONLY_DEFER. No implementer started.
- [ ] 10. (Gated: only after separate human approval of a test-only PR) Execute L2 tests and append the results. — DoD: results attached with commit SHA. A test that did not run is reported as not run, never as PASS.

## Tests
L2 plan cases (specified in task 8, executed only under task 10):
- [ ] T1. Legitimate owner `/mctl` command in Saved Messages (Alice): only InputPeerSelf is called. The fake sender records zero peer sends.
- [ ] T2. Same-tenant non-owner (Bob) sends a finance-looking command in a DM: no job, no owner summary with finance content, no reply.
- [ ] T3. Other-tenant account (Carol) state is never read for Alice's digest: user-mismatch fence.
- [ ] T4. Group/peer message and forwarded `/mctl` text: rejected by classifySavedCommand (fwd_from, saved_peer_id, from_id).
- [ ] T5. Replay and out-of-order: duplicate event_id and edited command produce one action. Random-id duplicate yields no second send.
- [ ] T6. Reconnect with `msg.Out=false` on push and history: still classified as owner command exactly once.
- [ ] T7. Stale install revision: an owner summary with an old InstallRevision is denied DenyInstallChanged.
- [ ] T8. Revoke/kill during pending send: GlobalKill or mode=off before DeliverPending yields no send. Account revocation is documented as a gap if it is not enforced.
- [ ] T9. No auto-reply: no `propose_reply` reaches any peer for a finance job. Tier `never` is enforced.
- [ ] T10. Denial audit: every denial writes an audit/action row with its DenyCode and no transaction body in logs (redaction check).

## Rollback
No runtime changes. Rollback means closing or reverting the documentation PR in
mctlhq/.github. If an approved test-only PR misbehaves, revert it. It adds tests only
and touches no production flag or deployment.
