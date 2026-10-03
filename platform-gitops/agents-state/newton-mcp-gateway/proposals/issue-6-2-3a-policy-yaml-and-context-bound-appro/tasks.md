# Tasks: issue-6-2-3a-policy-yaml-and-context-bound-appro

- [ ] 1. Add `src/newton_mcp/canonical.py` with `canonical_json_bytes(value)`,
      `sha256_hex(value)` and `canonical_timestamp(moment)` — DoD: UTF-8 JSON with
      `sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`,
      `allow_nan=False`; a pre-walk raises `ValueError` on any non-string mapping
      key; `canonical_timestamp` raises on a naive `datetime` and otherwise renders
      UTC as `YYYY-MM-DDTHH:MM:SS.ffffffZ`. Stdlib only, no new dependency, module
      docstring states that no numeric or string normalisation is performed and why.

- [ ] 2. Add `ServerConfig.transport_fingerprint` and
      `ServerConfig.binding_identity` to `src/newton_mcp/runtime/config.py`
      (depends on 1) — DoD: `transport_fingerprint` is `sha256_hex` of
      `{"kind": "streamable-http", "url": _canonical_url(url)}` for `HttpTransport`
      and `{"kind": "stdio", "command": ..., "args": [...], "env": dict(env)}`
      (names and values) for `StdioTransport`; `_canonical_url` lowercases the
      scheme and only the host-name part of the netloc, elides a port equal to the
      scheme default, and keeps userinfo, IPv6 brackets and path/query/fragment
      byte-exact (the netloc is not rebuilt from `hostname`/`port`); `binding_identity` is
      `f"{resolved_identity}@sha256:{transport_fingerprint}"`. No field added to
      any model, `runtime.yaml` schema unchanged, env values enter only the sha256
      input and never `binding_identity`, an `Approval`, a reason or a log.

- [ ] 3. Add `server_binding_identity: str` to `CandidateAction` and populate it in
      `Resolver._evaluate()` in `src/newton_mcp/runtime/resolver.py` (depends on 2)
      — DoD: taken from the same `server_config` that already supplies
      `resolved_identity`; `server_identity` keeps its #5 meaning; `Rejection`,
      scoring constants, ordering and the filter chain unchanged; existing
      `tests/runtime/` pass after `CandidateAction` literals are updated.

- [ ] 4. Extend `src/newton_mcp/action/policy.py` with the YAML schema (depends on 1)
      — DoD: `ValueRange` (`min`/`max`, `extra="forbid"`, validator requiring at
      least one bound and `min <= max`); `PolicyRule` gains `name`, `tool_name`,
      `arg_ranges` and `extra="forbid"`; `Policy` gains
      `policy_version: str = Field(min_length=1)` and `extra="forbid"`;
      `Policy.conservative()` keeps its zero-argument signature and supplies
      `CONSERVATIVE_POLICY_VERSION = "builtin.conservative.v1"` with its two rules
      unchanged.

- [ ] 5. Add `load_policy(path=None)` and `POLICY_PATH_ENV_VAR =
      "NEWTON_MCP_POLICY_PATH"` to `policy.py` (depends on 4) — DoD: mirrors
      `load_runtime_config()` exactly — `ValueError` naming the variable when
      unset/blank, `ValueError` naming the path for a missing/unreadable file and
      for `yaml.YAMLError`, then `Policy.model_validate(data or {})` so schema
      problems surface as `pydantic.ValidationError`; never falls back to
      `Policy.conservative()` or any other default.

- [ ] 6. Rework `Policy.evaluate` to take the resolved candidate (depends on 3, 4)
      — DoD: signature `evaluate(self, contract, candidate: ResolvedCandidate |
      None = None)`; order is (a) `risk is CRITICAL` -> `DENY`, (b) first matching
      rule checking `goal_prefix`, `tool_name`, `max_risk`, `min_confidence` then
      `arg_ranges` last, (c) `self.default`, (d) confirmation ceiling; a rule
      declaring `tool_name` or `arg_ranges` does not match when `candidate is
      None`; `min_confidence > 0` with `contract.confidence is None` does not
      match; every `PolicyResult` still carries a `reason`.

- [ ] 7. Implement the `arg_ranges` terminal-deny rule in `evaluate` (depends on 6)
      — DoD: reached only after every other predicate of that rule matched; a
      missing argument, a non-numeric value, or a `bool` (explicitly excluded even
      though `bool` subclasses `int`), or a value outside the inclusive
      `[min, max]` returns `DENY` immediately with a reason naming the argument and
      stops the rule walk — it never falls through to a later, broader rule.

- [ ] 8. Implement the confirmation ceiling in `evaluate` (depends on 6) — DoD:
      today's early `return CONFIRM` on `contract.requires_confirmation` is
      replaced by a post-decision clamp: `AUTO` becomes `CONFIRM` when
      `requires_confirmation is True`; `CONFIRM` and `DENY` pass through unchanged;
      the reason records that the ceiling was applied.

- [ ] 9. Add `src/newton_mcp/action/approval.py` (depends on 1, 3) — DoD: a
      `ResolvedCandidate` `typing.Protocol` (`server_identity`,
      `server_binding_identity`, `tool_name`, `args`) following
      `SupportsListTools` in `runtime/catalog.py` so `action/` imports nothing from
      `runtime/`; frozen `Approval` (`extra="forbid"`) with `approval_id`,
      `action_id`, `server_identity`, `tool_name`, `args_digest`, `policy_version`,
      `approved_by`, `approved_at`, `expires_at`, `binding`; frozen
      `ApprovalCheck(valid, reason)`.

- [ ] 10. Implement `compute_binding` and `create_approval` in `approval.py`
      (depends on 9) — DoD: `compute_binding` is the only place the payload is
      assembled and hashes exactly `{server_identity, tool_name, args, action_id,
      policy_version, expires_at}` with the full `args` mapping and
      `canonical_timestamp(expires_at)`, and nothing else; `create_approval` fills
      `server_identity` from `candidate.server_binding_identity` and `args_digest`
      from `sha256_hex(candidate.args)`.

- [ ] 11. Implement `verify_approval(approval, candidate, action_id,
      policy_version, now)` (depends on 10) — DoD: raises `ValueError` if `now` is
      naive; otherwise returns `ApprovalCheck`, checking in order expiry
      (`now < approval.expires_at`), `server_identity` vs
      `candidate.server_binding_identity`, `tool_name`, `args_digest`,
      `action_id`, `policy_version`, then the binding recomputed from the candidate
      and `approval.expires_at`, compared with `hmac.compare_digest`; the first
      failure's `reason` names the field and never echoes `args` values.

- [ ] 12. Add `examples/policy.example.yaml` (depends on 4) — DoD: header comment
      repeating the epic's safe-demo rule; `policy_version: "example.v1"`,
      `default: deny`, and safe rules only (HVAC `target_temperature_c` in
      `[20, 25]`, `set_light_state`, `announce`); tool names match
      `examples/runtime.example.yaml`; no lock, oven, alarm, industrial or
      safety-system tool appears.

- [ ] 13. Export the new symbols from `src/newton_mcp/action/__init__.py`
      (depends on 5, 9) — DoD: `Approval`, `ApprovalCheck`, `PolicyResult`,
      `ValueRange`, `compute_binding`, `create_approval`, `load_policy`,
      `verify_approval` added to the imports and to `__all__`, keeping `__all__`
      alphabetically sorted as it is today; importing `newton_mcp.action` and
      `newton_mcp.runtime` in either order raises no circular-import error.

- [ ] 14. Update docs (depends on 11) — DoD: `docs/action-runtime.md` replaces the
      deferred-identity paragraph (currently lines 85-91) with the decision taken
      here, the re-pointing rationale, an explicit statement that `binding` is
      context-binding and not authentication (a keyless sha256 does not prove who
      approved), why observed `serverInfo` is excluded, and a
      note that a transport edit invalidates outstanding approvals, and removes
      "policy evaluation" / "bind an approval" from "What this package does not do"
      while keeping execute/lifecycle/audit; `docs/architecture.md` marks the
      approval box implemented and points its "Approval is invalidated if
      parameters change" line at `compute_binding`; `README.md` line 160 narrows
      "no policy, no approval" to "no execution, no lifecycle, no audit";
      `.env.example` documents `NEWTON_MCP_POLICY_PATH`; wording stays "this
      project's experimental proposal" and nothing claims a live integration.

- [ ] 15. Run `uv sync --locked --group dev && uv run pytest -q` (depends on all)
      — DoD: green, `uv.lock` unchanged (no new dependency), and
      `schemas/physical-action-contract.schema.json` untouched.

## Tests

New files `tests/test_policy_yaml.py`, `tests/test_approval.py` and
`tests/test_canonical.py`; existing `tests/test_action_contract.py` keeps its two
policy tests. Follow `tests/runtime/test_config.py`: a module-level `MINIMAL_POLICY`
dict, `tmp_path` for files, `pytest.raises`.

### Canonicalisation

- [ ] T1. `canonical_json_bytes` sorts keys, emits no whitespace, and round-trips a
      non-ASCII string literally (`ensure_ascii=False`).
- [ ] T2. `canonical_json_bytes` raises on a non-string mapping key, on `NaN` and
      on `Infinity`.
- [ ] T3. `20` and `20.0` produce different canonical bytes (documented fail-safe,
      not a bug).
- [ ] T4. `canonical_timestamp` raises on a naive `datetime`; two aware datetimes
      denoting the same instant in different offsets render identically.

### Server identity and re-pointing

- [ ] T5. `binding_identity` starts with `resolved_identity` and differs from it.
- [ ] T6. Changing `HttpTransport.url` under an unchanged `name` changes
      `transport_fingerprint`; changing `StdioTransport.command`, and separately
      `args`, does too.
- [ ] T7. `_canonical_url` treats `https://Host.local/mcp`,
      `https://host.local:443/mcp` and `https://host.local/mcp` as one fingerprint,
      while `https://host.local/mcp/` (trailing slash) stays distinct. Owner
      amendment: `https://alice:x@host.local/mcp` and `https://bob:x@host.local/mcp`
      fingerprint differently, and `https://alice:x@host.local/mcp` differs from
      `https://host.local/mcp`. `http://[::1]:8080/mcp` keeps its brackets and port,
      and `http://[::1]:80/mcp` equals `http://[::1]/mcp`.
- [ ] T8. (owner amendment) Changing an `env` *value* changes
      `transport_fingerprint`, and so does adding, removing or renaming an `env`
      variable. The same mapping in a different insertion order gives the same
      fingerprint. `binding_identity` never contains an env value. An approval issued before an env value change
      verifies invalid.
- [ ] T9. **Re-pointing test (the issue's explicit ask):** an approval created
      against a server, then verified against the candidate produced after the
      server's `url` was re-pointed under the same `name`, is invalid.

### Policy YAML

- [ ] T10. `examples/policy.example.yaml` loads via `load_policy()` and yields the
      expected `policy_version` and rule count.
- [ ] T11. A document without `policy_version`, and one with an empty
      `policy_version`, both raise `ValidationError`.
- [ ] T12. An unknown key at document level, and an unknown key inside a rule, both
      raise `ValidationError` (`extra="forbid"`).
- [ ] T13. `load_policy()` with `NEWTON_MCP_POLICY_PATH` unset, and with it blank,
      raises `ValueError` naming the variable (`monkeypatch.delenv`/`setenv`).
- [ ] T14. A missing path and a file containing invalid YAML each raise `ValueError`
      naming the path.
- [ ] T15. A `ValueRange` with neither bound, and one with `min > max`, raise
      `ValidationError`.

### Policy invariants

- [ ] T16. `critical` risk denies even when a rule with `max_risk: critical,
      decision: auto` matches first.
- [ ] T17. `requires_confirmation: true` turns an otherwise-`auto` outcome into
      `confirm` (low risk), and leaves an otherwise-`deny` outcome `deny`
      (high risk) — the ceiling, not an upgrade.
- [ ] T18. First match wins: with two rules that both match, the first one's
      decision is returned and the second is never consulted.
- [ ] T19. An empty-rules policy returns its `default`, and `default` is `deny`
      when omitted.
- [ ] T20. `tool_name` matches exactly and case-sensitively; a rule whose
      `tool_name` differs from `candidate.tool_name` does not match.
- [ ] T21. `min_confidence` with `contract.confidence is None` does not match the
      rule (fail closed).
- [ ] T22. `test_conservative_policy_matrix` and
      `test_explicit_confirmation_overrides_auto` in
      `tests/test_action_contract.py` still pass unmodified.

### Value ranges

- [ ] T23. An in-range `target_temperature_c` (23, band `[20, 25]`) yields the
      rule's decision; both inclusive bounds (20 and 25) also yield it.
- [ ] T24. An out-of-range value (26) yields `deny` with a reason naming
      `target_temperature_c`, **and is not rescued by a later broader
      `decision: auto` rule** — the walk stops.
- [ ] T25. An argument absent from `candidate.args`, a string value, and a `bool`
      value each yield `deny` on a rule declaring a range for it.
- [ ] T26. A rule declaring `tool_name` or `arg_ranges` does not match when
      `evaluate()` is called without a candidate, so the result is the `deny`
      default.

### Approval binding — one test per bound field

- [ ] T27. A freshly created approval verifies valid against its own candidate,
      `action_id`, `policy_version` and a `now` before `expires_at`.
- [ ] T28. `server_identity`: verifying against a candidate whose
      `server_binding_identity` differs is invalid.
- [ ] T29. `tool_name`: verifying against a candidate with a different
      `tool_name` is invalid.
- [ ] T30. `args`: changing exactly one argument value is invalid; separately,
      adding one extra argument key is invalid; separately, removing one is invalid.
- [ ] T31. `action_id`: verifying with a different `action_id` is invalid.
- [ ] T32. `policy_version`: verifying with a different `policy_version` is
      invalid.
- [ ] T33. `expires_at`: an approval whose `expires_at` was mutated via
      `model_copy(update=...)` **to a still-future timestamp** is invalid, because
      `expires_at` is in the canonical binding payload.
- [ ] T34. Expiry: `now == expires_at` is invalid and `now > expires_at` is
      invalid, while `now < expires_at` is valid.
- [ ] T35. A naive `now` raises `ValueError` rather than returning
      `valid=False`.
- [ ] T36. Canonicalisation: two candidates whose `args` mappings carry the same
      pairs in a different insertion order produce the same `binding` and the same
      `args_digest`, and each verifies against the other's approval.
- [ ] T37. Mutating `approved_by`, `approved_at` or `approval_id` via
      `model_copy(update=...)` leaves the approval valid — those are deliberately
      not bound (that is issue #7's audit concern).
- [ ] T38. Every failure `reason` from `verify_approval` contains no argument value
      from `candidate.args` (assert against a sentinel argument value).

## Rollback

Fully revertable with `git revert` of the single PR: nothing is persisted, no
migration runs, no deployment or external system is touched, and no dependency is
added so `uv.lock` does not move.

Partial rollback, if only the identity decision is contested: revert tasks 2, 3 and
T5-T9, and change `create_approval`/`verify_approval` to read
`candidate.server_identity` instead of `candidate.server_binding_identity`. That
restores issue #5's label-only identity while keeping the YAML policy and the
binding for the other five fields; the binding payload's key names do not change,
so only tests T5-T9 are affected. The re-pointing hole returns, so
`docs/action-runtime.md` must go back to naming it an open question rather than a
resolved one.

If instead the policy tightenings are contested, tasks 7 and 8 and the
`min_confidence`-with-`None` change in task 6 are independent of the approval work
and can be reverted on their own; `Policy.evaluate` then returns to today's
early-`CONFIRM` behaviour while approvals stay bound.

Downstream risk is zero today: no caller in `src/` invokes `Policy.evaluate`, and
`src/newton_mcp/server.py` registers no policy or approval MCP tool, so a revert
cannot leave a half-wired execution path behind.
