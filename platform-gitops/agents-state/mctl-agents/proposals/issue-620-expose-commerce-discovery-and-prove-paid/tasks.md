# Tasks: issue-620-expose-commerce-discovery-and-prove-paid

- [ ] 1. Discovery exposure: add `_commerce_view()` and an ISO 4217 `MINOR_UNIT_EXPONENTS` display helper (in `orchestrator/commerce.py`), include the compact `commerce` block in `CapabilityGateway.search()` rows and the full block in `describe()`, only when `descriptor.commerce` is set, and update the `sdk_tools()` descriptions. — DoD: legacy rows are byte-identical (snapshot test), paid rows carry price, currency, unit, mode, `quote_required` and `billable_on`, and the ADR 017 forbidden-field-name test passes.
- [ ] 2. Advisory approval hint: add a pure `policy_checkpoint.expected_verdict()` and return `approval_expected` from `describe()` (`unknown` for non-`PolicyDecidePolicyCheckpoint` checkpoints). (depends on 1) — DoD: unit tests cover required, not_required and unknown, and `invoke()` behaviour is unchanged.
- [ ] 3. Cross-repo prerequisite: open or link mctl-api issues for the budget, receipt and invocation-list reads, the MCP tools `mctl_get_commerce_budget`, `mctl_get_commerce_receipt` and `mctl_list_commerce_invocations`, the accept kill switch, and a proof-tenant-only fault hook on the simulated authorizer. Record the confirmed routes in #620. — DoD: the route shapes and reason codes are confirmed in writing before task 4 merges.
- [ ] 4. `CommerceClient.get_budget` / `get_receipt` / `list_invocations` plus `BudgetView` / `ReceiptView` parsers (integer money only, `schema_version` checked). (depends on 3) — DoD: unreachable answers `UNKNOWN`, a float amount is rejected, and no argument, result or `external_ref` field is surfaced.
- [ ] 5. `CommerceRuntime.from_env()` with `MCTL_COMMERCE_ENABLED`, `MCTL_COMMERCE_ADMITTED_PROVIDERS` and `MCTL_COMMERCE_FUNDS_MODE`, wired at the `CapabilityGateway.build(` call in `orchestrator/run_issue_investigator.py`. — DoD: unset means `None` and today's path, enabled with an empty admission list or a non-simulated mode raises at startup, and `tests/test_worker_isolation.py` stays green.
- [ ] 6. `orchestrator/commerce_metrics.py`: lazy OTel counters and a histogram with a closed attribute set, emitted from `PaidInvocation._note()` and the terminal answer. (depends on 5) — DoD: an attribute-key allowlist test passes, it is a no-op without OTel, and no amounts or non-provider ids appear as attributes.
- [ ] 7. Move `FakeLedger`, `FakeApprovals` and `Clock` from `tests/test_commerce_gateway.py` into `tests/commerce_fakes.py` and re-import them. — DoD: the existing commerce tests pass unchanged.
- [ ] 8. `tools/commerce_proof.py` with pure scenario and report functions S1-S14 and `--backend offline|live`, writing the pinned evidence JSON. (depends on 1, 4, 5, 6, 7) — DoD: the offline backend passes all scenarios in CI, the live backend runs with operator tokens, and the bundle pins SHAs, image tags, encoding versions and terms version.
- [ ] 9. Docs: `docs/benchmarks/paid-capabilities-proof.md` (scenario table, which backend proved each scenario, evidence link), `docs/runbooks/commerce-enable-disable.md`, a "Paid capabilities" section in `docs/capability-pilot-status.md`, and the metric names in `docs/observability/execution-traces.md`. Append C5 implementation notes to ADR 020 without changing the contract. (depends on 8) — DoD: the docs are reviewed and the runbook names the enable and disable order and the liability check.
- [ ] 10. Operator step (not the implementer): run `--backend live` against the designated proof tenant, attach the evidence to #620, and confirm zero unexplained liability. (depends on 3, 8, 9) — DoD: the evidence is attached and S14 is clean.

## Tests

- [ ] T1. `search()` and `describe()` on a set with one legacy and one paid descriptor: the legacy output is unchanged, and the paid output shows `price_display == "EUR 0.12"`, `amount_minor == 12` (int) and `quote_required is True`.
- [ ] T2. `describe()` of an id outside the sealed set returns `{"reason_code": "not-found"}` with no commerce or approval key.
- [ ] T3. `expected_verdict()` returns `required` for a `REQUIRE_APPROVAL` rule, `not_required` for `ALLOW`, and `unknown` for no rule or a missing grant.
- [ ] T4. Client reads: 404 for a foreign tenant and 404 for a missing id give identical answers, a transport error gives `UNKNOWN`, and a float amount is rejected.
- [ ] T5. `CommerceRuntime.from_env`: off gives `None`, `live` funds mode raises, an empty admission list raises.
- [ ] T6. Metrics attribute keys are a subset of `{phase, reason_code, price_mode, funds_mode, provider_id}`, and a provider outside the admission list is recorded as `other`.
- [ ] T7. Budget 100 minor, 12 concurrent calls at 12 minor: captures <= 8, committed <= 96, the others `budget-exhausted`, and a sequential 9th is `budget-exhausted` (ADR 020 invariant 11).
- [ ] T8. Idempotency: same key and args give one execution and one capture, and same key with changed args gives `idempotency-conflict`.
- [ ] T9. The S1-S14 offline proof run with OTel forced off equals the run with OTel on (invariant 16).
- [ ] T10. Settlement `unknown` after success keeps `settlement_status: pending`, a retry settles it, and the provider execution count stays at 1.
- [ ] T11. Disable with one `outcome_unknown` invocation: a new paid call is refused, and the existing one reaches a terminal phase through reconcile.
- [ ] T12. A direct `ProviderIngress` call without, or with a forged, `DispatchAuthorization` is refused and leaves the execution count at 0.

## Rollback

All changes are additive and gated. To roll back:

1. Unset `MCTL_COMMERCE_ENABLED` on the worker values (gitops). No new paid acceptances come from mctl-agents.
2. Turn off mctl-api's accept switch. Keep its reconciler running until `list_invocations` shows no non-terminal invocations. Never delete ledger rows.
3. If the discovery change itself misbehaves, revert the mctl-agents PR. The descriptors and sealed-set hashes are unchanged, so a revert needs no data migration.
