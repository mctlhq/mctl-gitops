# Tasks: issue-1274-feat-glovo-g3-link-only-handoff-provider

Gate: no implementation PR is opened before task 0 is done. Until then the slice is "proposal
only", per owner decision 1 in the issue.

- [ ] 0. Owner gate. Record in the issue the Glovo consumer-terms clauses on automated access,
  deep linking and brand use, read in a browser. Also record decision 2 (connector name) and
  decision 3 (ship or not), and confirm that the amendment branches `docs/amend-glovo-r7-regressions`
  and `docs/amend-glovo-1044-990` have landed. — DoD: an owner comment on #1274 states all of
  these. If the terms forbid linking or the brand use, the slice stops here.

mctl-telegram (this repo)

- [ ] 1. `provider/glovo/internal/handofflink`: `Build`, `ItemsText` and the vendored
  `testdata/handoff-link.json` with a sha256 pin (depends on 0, 10, and the #1262 module
  skeleton). — DoD: stdlib only. A `go list -deps` test forbids `net/http`, `net` and `os`. Every
  accept vector produces the exact output and every `must_reject` vector is refused. The
  parse-back self-check is in place. The literal `glovoapp.com` occurs only in this package.
- [ ] 2. The facade contract `docs/contracts/glovo-handoff-mcp-tools.json` and its embedded copy
  (depends on 0). — DoD: four tools as in design section 5. The `state` enum has no
  `placed`/`paid`/`delivered`. `outcome` is the const `OUTCOME_UNKNOWN`. The `handoff_url`
  pattern is anchored to the three templates. Every description carries the not-affiliated
  notice. `TestEmbeddedCopyEqualsDocsContract` covers both files.
- [ ] 3. `docs/glovo_contract_test.go`: allowlists per contract, the extra forbidden input
  properties (`link`, `href`, `redirect`, `host`, `cc_url`), the state, outcome and pattern
  checks (depends on 2). — DoD: the existing fake-contract assertions are unchanged, and each new
  assertion goes red on a planted violation.
- [ ] 4. Facade kind selection. `internal/glovo/config` gets `GLOVO_MCP_PROVIDER_KIND`
  (`fake` default). `internal/glovo/tools` gets an `impls` map per kind. `internal/glovo/mctlapi`
  gets `OpConsent` and `OpPrepareHandoff`, and `fakeapi` serves them plus a `handoff_issued`
  order (depends on 2). — DoD: with the variable unset, `tools/list`, the wire golden fixtures and
  every existing test are byte-identical. With `link_handoff`, exactly the four handoff tools are
  listed. An unknown value fails startup.
- [ ] 5. Provider worker kind: `GLOVO_PROVIDER_KIND` in `provider/glovo/cmd/glovo-provider-worker/config.go`,
  with the identity rule `provider:glovo-handoff` (depends on 1, #1262 merged). — DoD: the
  default `fake` is unchanged. `link_handoff` with the fake identity, or the fake kind with the
  handoff identity, refuses to start. `fakeonly.Check` still runs.
- [ ] 6. Protocol: vendor the v1alpha3 command and result schemas, with sha256 pins and
  `PROVENANCE`, and dispatch in `ParseCommand` by (`schema_version`, `kind`, provider kind)
  (depends on 5, 10). — DoD: each kind refuses the other's commands locally. The golden fixtures
  pass, and `EncodeResult` validates against `result-handoff.schema.json`.
- [ ] 7. Executor: `handoffstore` with `EffectOf(command_id)` dedupe, a `Build` pre-flight before
  the permit, and the new rows in the single outcome table and the runbook (depends on 6). — DoD:
  the reused #1262 state machine steps 4.1-4.3 are covered for the new kind. The runbook table is
  generated from, or tested against, the code table.
- [ ] 8. Docs: `docs/contracts/glovo-link-handoff.md` (the canonical seam text), threat model
  TM17-TM20 with tests named, the ADR 0010 G3 note and a `docs/glovo-mcp.md` config row (depends
  on 2). — DoD: `TestGlovoThreatModelCrossReferences` and `TestGlovoDocsHaveNoCredentialShapes`
  pass.

Follow-ups in other repos (each with its own issue and approval; listed so the seams are owned)

- [ ] 10. mctl-agents (owner #1059): `docs/contracts/bridge/handoff/v1alpha1/` holds
  `handoff-link.json`, `handoff-basket.schema.json`, `command-issue-handoff-link.schema.json` and
  `result-handoff.schema.json`, all listed in `SHA256SUMS`, plus fingerprint vectors. — DoD: the
  drift and fixture tests pass, and the vendoring table names mctl-telegram and mctl-api.
- [ ] 11. mctl-api: #988 `provider_kind`, `glovo_handoff_record`; #985 §2a and #957 §3a gain the
  kind key and the `handoff_issued` rows, and the body restores `handoff_url` for that state only;
  #986 adds v1alpha3 leasing for declared providers only and the `SubmitResult` recompute-compare;
  #989 adds the fence basket dispatch; #959/#961 add the `link_handoff` consent connection. — DoD:
  the totality and guard test shows no `placed`/`observed_placed` for `issue_handoff_link`, and
  the M1 tenant tests T1-T7 and T16 run for both kinds.
- [ ] 12. mctl-api#957: freeze the routes `POST /handoff-consents` and `POST /handoffs:prepare`, and
  replace the candidate harness rows in `internal/glovo/mctlapi`.
- [ ] 13. mctl-gitops: a NetworkPolicy for the handoff worker (default-deny egress except the
  mctl-api origin and DNS), and values only after G6. — DoD: a policy test shows a denied
  connection to an external host.

## Tests

- [ ] T1. `handofflink` accepts: every accept vector gives the exact URL for each template, and
  `store` wins over `category`.
- [ ] T2. `handofflink` refuses each of these, and each test goes red when its specific check is
  removed:
  - a `cc` or `lang` outside its set;
  - uppercase;
  - `..`, `/`, `%`, `?`, `#`, `@`, `\` or whitespace;
  - a homoglyph;
  - an empty segment;
  - an over-long segment;
  - `evil.com` as a city.
- [ ] T3. Self-check: a planted builder bug that emits `https://glovoapp.com.evil.test/...` or adds
  a query is refused by the parse-back check (a mutation test).
- [ ] T4. `ItemsText` and prepare validation: control or format characters, `://`, `www.`, `<`,
  more than 80 runes, non-NFC input, 0 or more than 30 lines and a quantity of 0 or 101 are each
  refused. No item text ever appears in the URL (a property test over random names).
- [ ] T5. Exactly one record. A redelivered command with a local effect follows the #1262
  `applied_prior_lease` path and issues no second permit and no second link. A replayed result
  against `bridgefake` gives `replayed:true` and the same record.
- [ ] T6. Recompute-compare (in the `bridgefake` model, and as an mctl-api follow-up test): a
  result whose link differs by one byte gives `result_inconsistent` and the effect becomes
  `unknown`.
- [ ] T7. Egress: the recording `DialContext` over the full link-handoff path sees only the
  mctl-api origin, and a second `httptest` server standing in for any other host receives zero
  requests. A static test checks that `glovoapp.com` appears only in `handofflink`.
- [ ] T8. Status truth (facade with `fakeapi`): `handoff_issued` carries `handoff_url`,
  `handoff_items_text` and `notice`. Other states carry no `handoff_url`. An upstream body with
  `state=placed`, `outcome=observed_placed` or a non-template `handoff_url` becomes
  `upstream_invalid`.
- [ ] T9. Kind isolation: the fake kind refuses a v1alpha3 command and the handoff kind refuses
  `place_order_fake`, `cancel_order_fake`, `quote` and `read_status`. The mismatched identity
  refuses to start.
- [ ] T10. Default unchanged: with `GLOVO_MCP_PROVIDER_KIND` unset, `tools/list` and the wire golden
  fixtures are byte-equal to `main`, and every existing `internal/glovo` and `provider/glovo`
  test passes.
- [ ] T11. Fences in `fakeapi` for the handoff tools: two tenants, two principals, a foreign
  `order_id` (`not_found`), approval replay, and revoke, expiry and cancel giving
  `cancelled`/`expired` with no link. These mirror ADR 0010 T1-T7 and T16.
- [ ] T12. Leak scan: canary strings in item names and the credential file never appear in logs,
  metrics or errors (`leakcheck`), except as restated item text in the status body.

## Rollback

Nothing here is deployed or published, and both binaries default to the `fake` kind.

- To stop serving: set `GLOVO_MCP_PROVIDER_KIND=fake`, or unset it, in the facade, and scale the
  `provider:glovo-handoff` worker to zero. mctl-api then leases no v1alpha3 command, because no
  provider declares it, and open commands expire to `cancelled` per the M1 sweep.
- To remove the code: revert the merge commits. The new packages, contract files and the config
  switch are additive, so a revert leaves the fake path and `tg.mctl.ai` untouched.
- The cross-repo follow-ups are additive in mctl-api (a nullable column defaulting to `fake`, and
  a new table). Each rolls back by its own revert.
