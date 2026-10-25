# Tasks: issue-195-spike-mcp-gateway-validate-identity-per

All work is in `mctlhq/.github` only. Commits and the PR use `Refs #195`.

- [ ] 1. Re-pin evidence: record 40-hex SHAs and read date for mctlhq/.github,
  mctl-api (baseline `98bbf8c61006f1d70762c1ae2a9d3747c67ef241`), mctl-gitops,
  mctl-agents; re-read the hooks listed in design.md "Current state" and note
  any delta if mctl-api has moved; record the pinned mcp-go version from
  mctl-api `go.mod` (`v1.0.0`) and a pinned `modelcontextprotocol/go-sdk`
  release/commit. — DoD: evidence-pin table drafted in
  `docs/spikes/mcp-gateway-g0.md` with every `[CODE]` hook as `repo@sha:path:symbol`.
- [ ] 2. Scaffold `docs/spikes/mcp-gateway-g0/` (`go.mod` with no `require`,
  `README.md` with non-normative banner and run command, `fixtures/`). — DoD:
  `go vet ./...` and `go test ./...` pass on an empty test; no `go.sum`.
- [ ] 3. Fixtures (depends on 2): `principals.json` (prn_fixture_a owner
  tenant-red + viewer tenant-blue; prn_fixture_b developer tenant-blue;
  gateway service principal), `ceiling.json`, `grants.json` (with policy
  version), downstream catalogues for `api` and `tg` plus one malformed
  catalogue, `keys.json` with deterministic fixture-only ed25519 seeds for two
  `kid`s. — DoD: fixtures load in a test; all identifiers are synthetic.
- [ ] 4. `model/token.go` (depends on 3): EdDSA JWS sign/verify, JWKS document,
  `kid` lookup, rotation (add/remove key), checks for alg, iss, aud, exp/iat
  skew, sub/pid consistency. — DoD: unit tests for each refusal reason.
- [ ] 5. `model/exchange.go` (depends on 4): RFC 8693-shaped exchange with
  actor restriction, allowed-resource list, `act` claim, `exp = min(subject.exp,
  now + max)`, no authority widening, unavailable/invalid-response modes. —
  DoD: E1 exchange tests pass.
- [ ] 6. `model/policy.go` (depends on 3): `effective(P,T,S)` = ceiling ∩
  grants union; inert grants; versioned snapshot with soft/hard TTL, refresh
  timeout, newer-version replace, fake clock; fail-closed when undecidable. —
  DoD: E2 and E4 tests pass.
- [ ] 7. `model/downstream.go` + `model/gateway.go` + `model/audit.go`
  (depends on 4, 5, 6): reference API resource with own aud check and
  independent tenant check; gateway `tools/list` aggregation with `_meta`
  failed servers; `tools/call` re-check + exchange + forward using a distinct
  exchanged-token type; correlation record and redacting sink. — DoD: E3, E5
  and G0.7 tests pass via `httptest` servers.
- [ ] 8. `bench_test.go` (depends on 7): benchmarks for verify, exchange,
  policy lookup (cache hit/miss) and one full in-process `tools/call` round
  trip. — DoD: numbers recorded in the report labelled "reference estimate,
  local, not production".
- [ ] 9. E6 SDK comparison (depends on 1): compare mcp-go (pinned) vs official
  go-sdk (pinned) on the six G0.8 dimensions with cited sources; default keep
  mcp-go. — DoD: comparison table in report; any recommendation to change D1
  only through a `REVISE` verdict.
- [ ] 10. Write report `docs/spikes/mcp-gateway-g0.md` (depends on 1, 7, 8, 9):
  header/non-claims, evidence pins, D1 duplicate map (.github#194, #184, #35,
  mctl-agents#242, mctl-api#377 as completed baseline, #488, #747), D2 token
  contract with production hook map and the audience-before-mint ordering
  constraint, D3 policy + derived `R_max`, D4 migration states, D5 E1-E6
  results with test names, E5 failure matrix, D6 ownership table with the
  mctl-api signing/JWKS/audience slice listed separately and its independent
  usefulness stated, D7 roadmap draft per verdict (G1-G5 order preserved; text
  only), GO-criteria table, D8 single verdict. Flag the plan's G0 row scope
  mismatch. — DoD: every claim tagged `[REF]`/`[CODE]`/`[DOC]`/`unknown (not
  observed)`; exactly one of `GO`/`REVISE`/`NO-GO` appears as the verdict.
- [ ] 11. Register the spike (depends on 10): add
  `roadmap/spikes/mcp-gateway-g0.yaml` (`lifecycle: active`, outcomes `GO`,
  `REVISE`, `NO_GO`, issue mctlhq/.github#195, `timebox.decisionBy` set to a
  date the owner accepts — default 2026-11-15, `execution.devloop: true`,
  `evidence.report: docs/spikes/mcp-gateway-g0.md`, no `decision`); add the
  report to `AGENTS.md` `# Spikes`. — DoD: `python roadmap/scripts/validate.py
  roadmap/epics roadmap/spikes` passes.
- [ ] 12. CI wiring (depends on 2): extend `.github/workflows/workflow-tests.yml`
  path filters with `docs/spikes/mcp-gateway-g0/**` and add a step that sets up
  Go via `actions/setup-go` pinned by commit SHA with
  `go-version-file: docs/spikes/mcp-gateway-g0/go.mod`, then runs
  `go test ./...` with `working-directory: docs/spikes/mcp-gateway-g0`. — DoD:
  workflow passes on the PR; `permissions: {}` unchanged.

## Tests

- [ ] T1. E1: gateway accepts aud=`https://mcp.mctl.ai` token for prn_fixture_a
  and prn_fixture_b; reference API refuses the same token (audience mismatch).
- [ ] T2. E1: wrong audience, expired, bad signature, unknown `kid`, `alg`
  mismatch (incl. `none` and `HS256`), and sub/pid mismatch are each refused at
  gateway and API.
- [ ] T3. E1: exchange yields aud=`https://api.mctl.ai`, same sub/pid,
  `act.sub` = gateway principal, `exp` <= subject exp and <= now+max; reference
  API accepts it.
- [ ] T4. E1: exchange refused for non-gateway actor, subject token not for the
  gateway, disallowed resource, expired subject, requested wider scope.
- [ ] T5. E1: JWKS rotation — token signed with retained key accepted; with
  removed key refused.
- [ ] T6. E2: A and B receive different effective catalogues for the same
  downstream fixtures (golden lists asserted).
- [ ] T7. E2: hidden tool invoked by direct name returns the same error as an
  unknown tool; grant for a tool outside ceiling or unpublished is inert.
- [ ] T8. E2: A's tenant-red owner authority cannot authorize a tenant-blue
  mutation at the gateway; with the gateway check bypassed in the test, the
  reference downstream independently refuses.
- [ ] T9. Every `tools/call` re-evaluates policy (counter on policy evaluation
  asserted; prior `tools/list` not consulted).
- [ ] T10. E3: gateway token sent directly to reference downstream refused;
  exchanged token accepted; the downstream never receives the caller bearer
  (asserted on received `Authorization` header).
- [ ] T11. E4: with fake clock, a grant removed at the source is refused no later
  than `R_max = hard_ttl + refresh_timeout`; a newer policy version observed
  revokes immediately; an older version is ignored.
- [ ] T12. E5: policy unavailable with no valid cache, cache past hard TTL,
  exchange unavailable, exchange returns invalid token, downstream unavailable
  on call, downstream failure and malformed catalogue on list (`_meta` lists
  failed server ids, not an empty/complete catalogue) — each asserts the
  documented fail-closed/explicit-error result.
- [ ] T13. G0.7: one call produces one audit record with all nine correlation
  fields; captured logs and audit contain none of the fixture tokens, seeds or
  signatures and no request/result body.
- [ ] T14. `roadmap/scripts/validate.py roadmap/epics roadmap/spikes` passes with
  the new manifest.
- [ ] T15. Report lint (manual review checklist in PR): one verdict, all GO
  criteria rows filled, all `[CODE]` rows pinned, every number labelled as
  reference estimate.

## Rollback

The change is additive documentation, a self-contained Go test module, one
roadmap spike manifest, one `AGENTS.md` line and one CI step. Roll back by
reverting the PR (or removing `docs/spikes/mcp-gateway-g0*`,
`roadmap/spikes/mcp-gateway-g0.yaml`, the `AGENTS.md` entry and the
`workflow-tests.yml` step). No runtime, gitops, or other repository is affected,
so no production rollback is required. If only the CI step misbehaves, drop the
Go step and path filter while keeping the report.
