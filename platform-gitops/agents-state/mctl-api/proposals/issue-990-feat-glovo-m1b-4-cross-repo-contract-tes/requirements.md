# Glovo M1b/4: cross-repo contract tests, negative matrix and race/recovery evidence

## Context
Issue mctlhq/mctl-api#990 is the last M1b slice of the #954 decomposition before P1
acceptance. Earlier slices (#988 M1b/1, #989 M1b/2, #985 M1b/3, the read extension
#986) and the peers mctlhq/mctl-agents#1044, mctlhq/mctl-telegram#1262 and the facade
mctlhq/mctl-telegram#1264 each ship their own unit tests. Nothing yet proves the whole
fake-only P1 flow end to end:
`history -> preview -> basket -> prepare -> aar_ approval -> dispatch -> fake-provider effect -> order status`.
Nothing yet proves its negative matrix either, meaning the races, crashes and lost
messages that would cause a second write, an untracked write or a cross-tenant leak.

This slice adds evidence only. It adds no new runtime behavior and enables nothing. It
adds PostgreSQL-backed contract and integration tests in mctl-api, driven by an
in-process fake provider. It also adds a set of golden wire fixtures pinned by sha256,
which the peer repositories pin with the same digests. A CI step fails closed when any
required test is skipped or missing. The whole flow runs on synthetic data, and no real
Glovo or provider endpoint is ever contacted.

## User stories
- AS the P1 owner I WANT deterministic, CI-enforced evidence of every exactly-once and isolation property SO THAT the P1 acceptance decision rests on reproducible proof rather than on reasoning about the code.
- AS a maintainer of mctl-agents, mctl-telegram or the facade I WANT golden fixtures pinned by sha256 SO THAT any change to the wire contract on one side fails CI on every other side.
- AS a security reviewer I WANT audit and metrics assertions on every path SO THAT I can see that effect ids are redacted, intents are hashed and no other tenant's order is ever exposed.

## Acceptance criteria (EARS)
- WHEN the contract suite runs with `TEST_DATABASE_URL` set THE SYSTEM SHALL execute the full flow `history -> preview -> basket -> prepare -> aar_ approval -> dispatch -> fake-provider effect -> order status` against a fake provider and SHALL assert exactly one provider effect and a terminal order status of `succeeded`.
- WHEN a golden fixture under `internal/glovo/contract/testdata/` is loaded THE SYSTEM SHALL verify its sha256 against `internal/glovo/contract/testdata/PROVENANCE` and SHALL fail the test if any digest differs.
- WHEN the "revoke wins" order of the race is forced (the revoke commits while the permit transaction waits on the `aar_` row lock) THE SYSTEM SHALL refuse the write permit with `write_fence_refused`, SHALL record zero fake-provider writes and SHALL leave `effect_state` at `none`.
- WHEN the "write wins" order of the race is forced (the permit commits before the revoke) THE SYSTEM SHALL record exactly one audited fake-provider write, and every later permit or retry for that command SHALL be denied (`permit_already_issued` or `write_fence_refused`) without a second write.
- IF the fake provider reports an ambiguous effect, or the worker restarts after a permit and before a result, or the result post is lost THEN THE SYSTEM SHALL end the command with `effect_state=unknown`, SHALL NOT issue a second permit, and SHALL record no second fake-provider write.
- WHILE a valid approved intent exists THE SYSTEM SHALL produce exactly one fake-provider effect for it, no matter how many claims, retries, reclaims or duplicate result posts are injected.
- IF a caller of another tenant or another principal reads or writes any command, order status, receipt or read-extension (#986) result THEN THE SYSTEM SHALL answer as if the object does not exist (`command_not_found` or the equivalent 404) and SHALL leak no field of it.
- IF a #986 read-extension result is expired, revoked or bound to a different digest THEN THE SYSTEM SHALL refuse it.
- WHEN any path in the suite completes THE SYSTEM SHALL emit audit records carrying a redacted effect id, the principal and tenant, the hashed intent, the receipt id and the outcome. Neither the audit records nor the metrics labels SHALL contain a raw effect id, a lease token or another tenant's identifiers.
- WHEN CI runs the contract step THE SYSTEM SHALL fail if any `TestPGGlovoContract*` test is skipped or any required test name is missing a `--- PASS` line.
- WHILE the suite runs THE SYSTEM SHALL use only synthetic data and the in-process fake provider. Any attempt to dial a non-loopback address SHALL fail the test.

## Out of scope
- Any production enablement: `MCTL_BRIDGE_ENABLED`, `glovo.Default`, provider credentials and the deployment gates in `docs/bridge.md` all stay unchanged.
- The behavior of the fence, basket, prepare, approval and read extension themselves. Those belong to #988, #989, #985 and #986. This slice only tests them.
- Running the peer repositories' code inside mctl-api CI. Each peer runs its own side against the same pinned fixtures.
- Real Glovo API calls, real orders, checkout or payment.
- The independent review and the owner approval bound to the proposal digest, which happen outside the code.

## Open questions
- Canonical fixture home: this proposal makes mctl-api the source of truth for the P1 golden fixtures, and the peers vendor them byte for byte. This mirrors the existing `internal/bridge/schema/PROVENANCE` pattern in reverse. If the owner wants mctl-agents to own the fixtures instead (it already owns the v1alpha1 schemas), only the direction of the PROVENANCE file changes.
- #988, #989, #985 and #986 are not merged in the clone (the only `WriteFence` is the refusing default in `internal/bridge/permit.go`). The exact constructor names of the real fence, the order-status reader and the read extension are therefore unknown. Tasks 3-6 bind to whatever those slices export. Implementation must wait for them to merge.
- The issue does not say how a "worker restart" should be modeled. This proposal models it as the lease expiring and the command being reclaimed under `lease_epoch+1` (the path already in `internal/bridge/store.go`), plus a fake provider whose in-memory state is discarded. A real process kill is not attempted.
- Deployed state of mctl-api could not be observed (see design.md). This does not affect a test-only change.
