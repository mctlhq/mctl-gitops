# Glovo M1b/4: cross-repo contract tests, negative matrix and race/recovery evidence

## Amendment 2026-11-09 (round 7): aligned with the merged M1 seams

Resolves the findings F1-F7 of the round-6 cross-slice review. Where this section and
older text disagree, this section wins; the passages it contradicts have been edited.
This slice owns no wire contract and no behavior. Every value it asserts is owned by one
of the proposals named in the ownership table below, and the tests cite the owner's
section instead of restating the value.

| Finding | Change |
|---|---|
| F1 (happy path bypassed prepare, decision and dispatch) | Flow rewritten on the real seams: the #957 routes, the owner decision route, the #985 control routes and the #1059 `place_order_fake` command. `allowFence`, a direct `Store.Enqueue` and raw writes to `aar_` or order rows are forbidden in the package (a static test, proven red) |
| F2 (superuser store) | The harness provisions the `glovo_migrator` and `glovo_runtime` roles in a throwaway database, runs the `ApplySchema` chain as the migrator and runs everything as `glovo_runtime`; `control.ProveOneDatabase` and `receipt.Ready` must pass first; one negative proves `not_ready` on a wrong role |
| F3 (race waited on the wrong lock) | The race drives the real revokers and the real permit through the #957 §6b lock order and parks on the observed lock level; outcomes are the owners' (#985 §7.2, T12-T14, T24), timeout cases added |
| F4 (stale dependency set) | Dependencies and merge order follow #957 §6d.1; this slice lands last |
| F5 (stale wire vocabulary) | Each surface is asserted with its owner's code, status and body; order states are the #957 §3a names |
| F6 (second source of truth) | No canonical fixtures here. The slice pins the owners' file sets by digest and validates every message of its run against the owner's schema; `testdata/p1/` is a labelled transcript |
| F7 (matrix incomplete, no red proof) | A closed negative matrix with one named test per row (own or delegated by owner task), a CI check on every delegated name, and a mutation requirement per test |

## Context

Issue mctlhq/mctl-api#990 is the last M1b slice before P1 of the decomposition of the parent issue mctl-api#954 into #988, #989, #985 and #986 (#954 itself owns no code here, and no "#954 fence" exists: the fence is #989 `receipt.Fence`)
acceptance. Each earlier slice ships its own unit tests: the facade join routes, prepare,
the workflow-start outbox and the status bodies (#957), the connection registry (#959,
#960, #961), the order index (#988), the `aar_` receipt and fence (#989), the read
extension (#986), control dispatch, cancel and the permit-time fence wiring (#985), the
v1alpha2 contract (mctl-agents#1059), the control workflow (mctl-agents#1044) and the
provider and facade peers (mctl-telegram#1262, #1264). Nothing yet proves that the real
stack, wired as production wires it, does exactly one fake-provider effect per approved
intent and leaks nothing across tenants:

`history -> preview -> basket -> prepare (pending aar_, control_starts row) -> owner decision -> control dispatch -> provider claim -> write permit -> fake effect -> result -> read_command_result -> order status`

Nothing proves its negative matrix either: the races, crashes, timeouts and lost
messages that would cause a second write, an untracked write or a cross-tenant leak.

This slice adds evidence only. It adds no runtime behavior and enables nothing in any
deployment. It adds PostgreSQL-backed integration tests in mctl-api, built on the #957
harness (`glovojoin_fixture` build tag) and driven by an in-process fake provider, plus a
CI step that fails closed when any required test is skipped or missing. The whole flow
runs on synthetic data, and no real Glovo or provider endpoint is ever contacted.

## Ownership table (what this slice consumes, and from whom)

| Surface | Owner (the only definition) |
|---|---|
| Facade routes, prepare, `glovo.control_starts` and its dispatcher, status bodies and wire states, closed refusal set | mctl-api#957 (§3, §3a, §4.1, §6c) |
| M1a connection, enders (`Revoke`, `RevokeInstall`, `Reconnect`), `glovo.Code` | #959, #960, #961 |
| Order index and the basket fingerprint | #988 |
| `aar_` receipt, owner decision, `receipt.Fence`, `receipt.Ready` | #989 |
| Control routes, refusal table, `bridge.Store.CommandEffect`, `ProveOneDatabase`, lock order wiring, `internal/glovo/control/contract/` | #985 |
| Read extension | #986 |
| `bridge.mctl.ai/v1alpha2` files, including the Glovo `place_order_fake` command (the write command; its result document stays v1alpha1) and `SHA256SUMS` | mctl-agents#1059; vendored by mctl-api#986 under `internal/bridge/schema/v1alpha2/` |
| Per-command wire version, claim gating (`supported_versions`, `Caller.Versions`, `Store.WireVersionsEnabled()`) | mctl-api#986 §2 |
| The total (command status, `effect_state`) to order table, `reconcileOrder`, `bridge.Store.CommandEffect` returning `(status, effectState, err)` | mctl-api#985 §2a (wire rendering #957 §3a) |
| The fixture seam (`glovojoin_fixture`: `gate_{release,fixture}.go`, `ttl_{release,fixture}.go`, `SetFixtureDispatchCommandTTL`; `internal/glovojoin/ttl_{release,fixture}.go`, `SetFixtureGlovoApprovalTTL`) | mctl-api#985 §7.4 and #957 §8 |
| Control workflow and `glovo-control-input.v1alpha1.json` | mctl-agents#1044 |
| Fake provider behavior of record | mctl-telegram#1262 |

## User stories

- AS the P1 owner I WANT deterministic, CI-enforced evidence of every exactly-once and isolation property, produced through the same seams production uses, SO THAT the P1 acceptance decision rests on reproducible proof rather than on reasoning about the code.
- AS a maintainer of any M1 slice I WANT the final gate to fail when a pinned contract file or a required sibling test changes or disappears SO THAT drift on one side is caught before P1.
- AS a security reviewer I WANT audit and metrics assertions on every path SO THAT I can see that effect ids are redacted, intents are hashed and no other tenant's order is ever exposed.

## Acceptance criteria (EARS)

Harness and roles (F2)
- WHEN the suite starts THE SYSTEM SHALL create a throwaway database on the `TEST_DATABASE_URL` server, provision `glovo_migrator`, `glovo_runtime` and a work-items role, run the `ApplySchema` chain as the migrator in the order of #957 design §6d.1, open one runtime pool as `glovo_runtime`, build the stores through `bridge.NewRuntimeStore` and the #959, #988 and #989 constructors, and assert that `control.ProveOneDatabase` and `receipt.Ready` return nil before any scenario runs. It SHALL drop the database at the end and touch no other package's rows.
- IF the runtime pool is pointed at a superuser or an owning role THEN THE SYSTEM SHALL report `not_ready`, leave the fence as `refusingFence` and record zero provider writes (the unprovable-boundary rule of #985 §4).
- THE SYSTEM SHALL open the const-closed gate (`controlGateOpen`, behind `glovo.ControlDefault`) and shorten the TTLs (`SetFixtureDispatchCommandTTL`, `SetFixtureGlovoApprovalTTL`) only under the `glovojoin_fixture` build tag, drive connection expiry with short real durations and no injected clock, and keep the other #985 §7.3 preconditions real (the `MCTL_GLOVO_CONTROL_ENABLED` flag, `ProveOneDatabase`, #959 `Ready()`, `MembershipRevocationWired()`, the revocation hook, `receipt.Ready`). It SHALL require `Store.WireVersionsEnabled()` and a provider entry declaring v1alpha2, and SHALL assert that the release build carries none of the seams (#985 T29, #957 T13, run by the CI step).

Happy path (F1)
- WHEN the suite runs the full flow THE SYSTEM SHALL exercise, in this order and only through the owners' entry points: the #957 routes `orders:list`, `previews`, `basket` and `orders:prepare` against the real #986 read client and the fake provider; the pending `aar_` and the `glovo.control_starts` row with zero `place_order_fake` commands and zero provider writes; the owner decision through `POST /api/v1/action-approvals/{id}/decision` as the owner principal; the #957 §6c dispatcher starting the workflow through a recording starter; a test control-worker client calling the #985 dispatch route with `approval_ref` and `fingerprint`; the fake provider claiming under `bridge.mctl.ai/v1alpha2`, taking the write permit and posting its result; the #985 `read_command_result` and `read_approval` routes; and the #957 `GET /orders/{order_id}` route.
- WHEN that flow completes THE SYSTEM SHALL assert exactly one provider effect, exactly one `bridge_write_permits` row, `effect_state=succeeded`, the `aar_` consumed, the #988 order closed, and the order status body equal to the #957 §3a row for a placed order. It SHALL assert that the command's `workflow_id` and `run_id` equal the started run (#957 A8), and that the `bridge-result` signal went to that workflow and run with a digest equal to the read-back one.
- THE SYSTEM SHALL contain no use of `allowFence`, no direct call of `Store.Enqueue`, and no raw write to an `aar_` or order row in this package, and SHALL prove that check red by adding one of each.

Races, timeouts and recovery (F3)
- WHEN the "revoke wins" order is forced THE SYSTEM SHALL drive each real revoker (#959 `Revoke`, `RevokeInstall`, `Reconnect` with the real `CancelOpenForConnections` hook) and the #985 cancel while the real permit is parked on the lock level it actually waits on, confirmed through `pg_locks` and not through a timer. The permit SHALL be refused with the code that #985 T13 and #989 T11 pin, the fake provider SHALL record zero writes and `effect_state` SHALL be `none`.
- WHEN the "write wins" order is forced THE SYSTEM SHALL let the permit commit first, make the revoker wait behind it, and then show the command as `unknown` once the revoker proceeds (#985 §7.2, T13). It SHALL record exactly one audited fake-provider write and no second permit, reclaim write or accepted duplicate result for that command.
- WHEN the connection or the `aar_` passes its expiry or freshness bound between dispatch and permit THE SYSTEM SHALL refuse the permit with the owner's refusal and record zero writes (#985 T24, #989 T7).
- IF the fake provider reports an ambiguous effect, or the worker restarts after a permit and before a result, or the result post is lost THEN THE SYSTEM SHALL end the command with `effect_state=unknown`, SHALL NOT issue a second permit, and SHALL record no second fake-provider write.
- WHEN the provider ends the command without a permit, or a command is cancelled or expires with no effect, THE SYSTEM SHALL move the order through `reconcileOrder` as #985 §2a states (a completed command with effect `none` or `not_performed` is `closed` with wire `failed` and its `aar_` `unknown`; a cancelled or expired one with no effect is `cancelled`; a cancel after the permit is `unknown`), SHALL never leave the order `dispatched` behind a terminal command, and SHALL answer 503 `unavailable` with no state body for a pair outside that table.
- WHILE a valid approved intent exists THE SYSTEM SHALL produce exactly one fake-provider effect for it, no matter how many dispatches, claims, retries, reclaims or duplicate result posts are injected.

Isolation, per surface (F5)
- THE SYSTEM SHALL assert each surface with its owner's code, status and body, and SHALL require byte-identical bodies only inside one surface, between the absent and the foreign case. The surfaces are: the bridge provider routes (`command_not_found`, bridge body, `docs/bridge.md`); the facade routes and the #985 control routes (`not_found`, the #957 §4 body); and the #986 read extension, asserted in process on its sentinel and its #957 §4.2 mapping.
- IF a caller of another tenant or another principal reads or writes any command, order status, `read_command_result`, `read_approval` or read-extension result THEN THE SYSTEM SHALL answer as the owner of that surface answers for an absent object and SHALL leak no field of it.
- IF a #986 read-extension result is expired, revoked or bound to a different digest THEN THE SYSTEM SHALL surface the owner's distinct sentinel and its #957 §4.2 mapping, never data.

Negative matrix (F7)
- THE SYSTEM SHALL run, for every row of the matrix below, one named test (this slice's own, or the owner's named by task and recorded in `docs/glovo-p1-contract.md`), and SHALL fail the CI step when any named test is missing, skipped or lacks a `--- PASS` line.

| Row | Test (own, or delegated to the owner's task) |
|---|---|
| two tenants | own `TestPGGlovoContractIsolation`; #957 T6 |
| two principals in one tenant | own `TestPGGlovoContractIsolation`; #957 T6 |
| wrong audience (control token, facade token, bridge-provider token) | #985 T16; #957 T2, T3 |
| missing human-selected team grant | #957 T4 |
| revoked connection (typed `connection_revoked`, and `connection_revoked` for a `gcn_` that differs from the order's) | own race tests; #959 T24; #985 T11, T12 |
| expired connection (typed `connection_expired`) and absent or failed connection (typed `no_connection`) | own `TestPGGlovoContractTimeouts`; #959 T24; #985 T11, T24 |
| `ActivateTx` refusal codes of the connect flow (`invalid_transition`, `connection_revoked`, `connection_expired`, `no_connection`, `not_found`; #961-compatible) | #959 T9, T20 |
| stale install | #985 T11; #957 A5 matrix |
| approval replay (second `aar_`, reserved or consumed `aar_`) | own `TestPGGlovoContractExactlyOnce`; #985 T1, T3, T5; #989 T8 |
| basket change after prepare (`basket_changed`, `intent_mismatch`) | #985 T10; #989 T6 |
| foreign order | own `TestPGGlovoContractIsolation`; #985 T9 |
| ambiguous provider write | own `TestPGGlovoContractUnknown*` |
| timeout (dispatch to permit, lost result, lease expiry) | own `TestPGGlovoContractUnknown*`; #985 T24; #989 T7 |
| worker not ready (wrong role, failed proof) | own `TestPGGlovoContractNotReady`; #985 T17 |
| result to order is total (every status x `effect_state` pair; nothing left `dispatched` behind a terminal command) | own `TestPGGlovoContractResultToOrder` (four pairs); #985 T27 `TestReconcileOrderTable`; #957 T6 |
| provider version gating (`[v1alpha1]` provider never receives the v1alpha2 command; real provider refuses what it does not support) | #986 T4f, T4h, T7c; mctl-telegram#1262 T26, T27 |
| fixture seam is absent from the release build | #985 T29; #957 T13 |
| actor sources of the mutating methods (`glovo.ActorFrom(ctx)` returns the `WithActor` actor, else derives `Actor{principal, worker}` from the authenticated worker principal in the context (`IsGlovoWorker()`); `ActivateTx` does the same when `ActivateInput.Actor` is zero; there is no system fallback, and a call with no `Actor` and no authenticated worker principal in its context is refused `invalid_request` with no write) | #959 T23 |
| join `GET /connection` after a revoke is 409 `connection_revoked` (the most recent revoked row), and 404 `no_connection` only for no row or a most recent `failed` row | #957 §4.1; #959 |
| unauthenticated call: 401 written by the auth layer through `glovo.WriteUnauthenticated`, body code `not_authorized`; `glovo.Status(not_authorized)` is 403 | #957 §4.1; #959 A15, T25 |

- WHEN a test of this slice is accepted THE SYSTEM SHALL have shown it red with the named mutation applied to the code under test and green with the mutation reverted, and `docs/glovo-p1-contract.md` SHALL record each pair. At least: `allowFence` swapped in turns `...RevokeWins` and `...Isolation` red; `WriteFence.PreLock` removed turns the race tests red; the tenant predicate removed turns `...Isolation` red; the `aar_` reservation removed turns `...HappyPath` red.
- THE SYSTEM SHALL assert, inside each race and isolation test, the precondition that makes it non-vacuous (the permit was observed waiting on a lock; the foreign row exists), so a vacuous run fails instead of passing.

Audit, metrics and contract pins (F6)
- WHEN any path in the suite completes THE SYSTEM SHALL emit audit records carrying a redacted effect id, the principal and tenant, the hashed intent, the receipt id and the outcome. Neither the audit records nor the metrics labels SHALL contain a raw effect id, a lease token or another tenant's identifiers.
- THE SYSTEM SHALL own no canonical wire file. It SHALL pin the owners' file sets by digest (#1059 `SHA256SUMS` as vendored, #985 `internal/glovo/control/contract/SHA256SUMS`, #957 `internal/glovojoin/contract/`), SHALL fail when a pinned digest differs from the checked-in file, and SHALL validate every message its end-to-end run puts on a hop against the owner's schema. `testdata/p1/` is a recorded transcript labelled as evidence, never as a contract.
- WHEN CI runs the contract step THE SYSTEM SHALL fail if any `TestPGGlovoContract*` or `TestGlovoContract*` test, or any delegated test name, is skipped or lacks a `--- PASS` line, and SHALL also run the fake provider's own tests and require its non-loopback dial guard test by name.
- WHILE the suite runs THE SYSTEM SHALL use only synthetic data and the in-process fake provider. Any attempt to dial a non-loopback address SHALL fail the test, on every transport the harness clients use.

## Out of scope

- Any production enablement: `MCTL_BRIDGE_ENABLED`, `glovo.Default`, `glovo.ControlDefault`, provider credentials and the deployment gates in `docs/bridge.md` all stay unchanged.
- The behavior of the fence, basket, prepare, approval, dispatch and read extension themselves. Those belong to #988, #989, #985, #986 and #957. This slice only tests them.
- Running the peer repositories' code inside mctl-api CI (the control workflow of mctl-agents#1044 is played by a test control-worker client; the fake provider of mctl-telegram#1262 by the in-process stand-in). Each peer runs its own side against the owners' pinned files.
- Real Glovo API calls, real orders, checkout, payment, logins, sessions or baskets.
- The independent review and the owner approval bound to the proposal digest, which happen outside the code.

## Dependencies and merge order (F4)

This slice implements nothing until the whole set it binds to has merged, in the order
stated once in mctl-api#957 design §6d.1: mctl-agents#1059, then #959, #988, #960, #961,
#989, #957 A13 and A14, #986, #985, #957's read routes. It also needs mctl-agents#1044
and mctl-telegram#1262 for their contract files. #990 lands last. Task 0 records, for
each symbol and route the suite uses, the owning issue and the merged commit.

## Open questions

- Fixture seams (settled by #985 §7.4 and #957 §8; owner confirmation is OPEN-985-14, recommendation accept). This slice defines none of them: the names are listed in design item 1. The remaining open items belong to the owners: OPEN-985-13 (`DispatchCommandTTL`, recommendation 900 s) and OPEN-986-6 (the real provider's `supported_versions` is an activation precondition owned by the gitops P1 activation issue, not a test precondition). If an owner removes the seam, the timeout rows revert to #985 T24 and #989 T7 and the gap is recorded in `docs/glovo-p1-contract.md`.
- The issue does not say how a "worker restart" should be modeled. This proposal models it as the lease expiring and the command being reclaimed under `lease_epoch+1`, plus a fake provider whose in-memory state is discarded. A real process kill is not attempted.
- Whether the `-count=20` stability run is a CI job or a one-off pre-merge run. Proposed: a manual-dispatch job, run once before merge and recorded in the PR; the CI step itself runs once.
- Deployed state of mctl-api could not be observed (see design.md). This does not affect a test-only change.
