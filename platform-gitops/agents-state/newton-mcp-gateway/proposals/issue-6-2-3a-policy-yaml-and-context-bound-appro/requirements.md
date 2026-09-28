# Policy YAML and context-bound approvals

## Context

`src/newton_mcp/action/policy.py` today is a 69-line in-code policy engine: a
`Policy` holds `PolicyRule`s that can only match on `goal_prefix`, `max_risk` and
`min_confidence`, and `Policy.evaluate()` sees only a `PhysicalActionContract`. It
never sees the concrete tool call that would actually run. Meanwhile
`src/newton_mcp/runtime/resolver.py` (issue #5) already produces exactly that
concrete thing: a `CandidateAction` carrying `server_identity`, `tool_name` and the
rendered `args`. Nothing joins the two, there is no policy file an operator can
review, and there is no approval object at all — `docs/architecture.md` lists
"approval (tied to the exact normalized action)" as a future box, and
`docs/action-runtime.md` explicitly defers "what an approval binds to" to "a later,
security-relevant proposal". This is that proposal.

Two things must land together. First, the policy becomes a reviewable YAML file
(`NEWTON_MCP_POLICY_PATH`) with a required `policy_version`, evaluated against the
*resolved candidate* rather than the contract alone, so an operator can bound an
HVAC tool to 20-25 C rather than trusting the contract's own self-reported risk.
Second, an `Approval` becomes cryptographically bound to one exact action: a
sha256 over the canonical JSON of `{server_identity, tool_name, args, action_id,
policy_version, expires_at}`. Without that binding, an approval granted for
"set kitchen light on" is a bearer token that a later, different tool call could
replay. `docs/action-runtime.md` also flags the sharpest variant of that threat:
issue #5 left `server_identity` as the configured label from `runtime.yaml`, so an
operator re-pointing `home-bridge` from `https://home-bridge.local/mcp` to another
URL under the same `name` would leave every outstanding approval still valid
against a substituted server. This proposal closes that by making `server_identity`
in the binding the configured label plus a canonical transport fingerprint.

## User stories

- AS a platform operator I WANT the physical-action policy in a reviewable YAML file
  with an explicit `policy_version` SO THAT I can diff, review and pin what the
  runtime is allowed to do without editing Python.
- AS a safety reviewer I WANT policy rules that match on tool name and on numeric
  value ranges of the resolved arguments SO THAT an HVAC tool can be auto-approved
  only inside a comfort band instead of on the contract's self-declared risk.
- AS a safety reviewer I WANT an approval that is bound to one exact action SO THAT
  an approval cannot be replayed against a different tool, different arguments, a
  different action, a different policy version or a different server.
- AS a platform operator I WANT approvals issued before I re-pointed a server's
  `url`/`command`/`args` to become invalid SO THAT changing where a server lives is
  never a silent authorisation carry-over.
- AS a developer I WANT `Policy.conservative()` and `examples/policy.example.yaml`
  to keep working SO THAT the repo has a safe built-in default and a copyable,
  test-validated starting point.

## Acceptance criteria (EARS)

### Policy loading

- WHEN `load_policy()` is called with no argument THE SYSTEM SHALL read the policy
  file path from the `NEWTON_MCP_POLICY_PATH` environment variable.
- IF `NEWTON_MCP_POLICY_PATH` is unset or blank AND no explicit path was passed
  THEN THE SYSTEM SHALL raise `ValueError` naming the variable, and SHALL NOT fall
  back to `Policy.conservative()` or any other default.
- IF the named file does not exist, cannot be read, or is not parseable YAML THEN
  THE SYSTEM SHALL raise `ValueError` naming the path and the underlying error.
- IF the parsed document fails the policy schema THEN THE SYSTEM SHALL raise a
  `pydantic.ValidationError`, mirroring `load_runtime_config()` in
  `src/newton_mcp/runtime/config.py`.
- IF the document has no `policy_version`, or an empty `policy_version` THEN THE
  SYSTEM SHALL reject it as a schema error.
- IF the document, or any rule in it, carries an unknown key THEN THE SYSTEM SHALL
  reject it as a schema error (`extra="forbid"`, matching the runtime config
  convention that a misspelt key must never silently widen an allow-list).
- WHEN `Policy.conservative()` is called with no argument THE SYSTEM SHALL return a
  valid `Policy` carrying a built-in `policy_version` string, with the same
  decision matrix as today for the cases `tests/test_action_contract.py` asserts.
- WHEN `examples/policy.example.yaml` is loaded in a test THE SYSTEM SHALL validate
  it successfully.

### Policy evaluation

- WHEN a policy is evaluated THE SYSTEM SHALL evaluate against a resolved candidate
  (`PhysicalActionContract` plus the `CandidateAction` from
  `src/newton_mcp/runtime/resolver.py`), not the contract alone.
- WHEN more than one rule could match THE SYSTEM SHALL apply the first matching
  rule in file order and ignore the rest.
- IF no rule matches THEN THE SYSTEM SHALL return the policy's `default`, which
  SHALL default to `deny`.
- WHILE `contract.risk` is `critical` THE SYSTEM SHALL return `deny` regardless of
  any rule, and SHALL evaluate that check before any rule.
- WHILE `contract.requires_confirmation` is `true` THE SYSTEM SHALL never return
  `auto`: an otherwise-`auto` outcome SHALL be raised to `confirm`, and an
  otherwise-`deny` outcome SHALL stay `deny`.
- WHEN a rule declares `goal_prefix` THE SYSTEM SHALL match it only if
  `contract.goal` starts with that prefix.
- WHEN a rule declares `tool_name` THE SYSTEM SHALL match it only if it equals
  `candidate.tool_name` exactly (case-sensitive).
- WHEN a rule declares `max_risk` THE SYSTEM SHALL match it only if
  `contract.risk` is at or below that ceiling in the order
  `read_only < low < medium < high < critical`.
- WHEN a rule declares `min_confidence` greater than 0 THE SYSTEM SHALL match it
  only if `contract.confidence` is present and greater than or equal to it; a
  `None` confidence SHALL NOT satisfy a non-zero `min_confidence`.
- WHEN a rule declares `arg_ranges` THE SYSTEM SHALL evaluate the range check last
  among that rule's predicates, and only once every other predicate of that rule
  has matched.
- IF every other predicate of a rule matched AND a named argument's value falls
  outside its declared inclusive `[min, max]` range THEN THE SYSTEM SHALL return
  `deny` with a reason naming the argument, and SHALL NOT continue to later rules.
- IF every other predicate of a rule matched AND a named argument is absent from
  `candidate.args`, or is not an int/float (a `bool` is not a number here) THEN THE
  SYSTEM SHALL return `deny` with a reason naming the argument.
- IF a rule declares `tool_name` or `arg_ranges` AND no candidate was supplied
  THEN THE SYSTEM SHALL treat that rule as not matching, so evaluation falls
  through toward the `deny` default rather than matching on fewer predicates.
- WHEN any decision is returned THE SYSTEM SHALL carry a human-readable `reason`,
  as `PolicyResult` already does.

### Canonicalisation

- WHEN the system canonicalises a value for digesting THE SYSTEM SHALL emit UTF-8
  JSON with keys sorted, no whitespace between tokens, and non-ASCII characters
  emitted literally rather than escaped.
- IF a value to be canonicalised contains a non-string mapping key, `NaN`,
  `Infinity`, or any type JSON cannot represent THEN THE SYSTEM SHALL raise rather
  than coerce or drop it.
- WHEN a `datetime` enters the binding payload THE SYSTEM SHALL require it to be
  timezone-aware, convert it to UTC, and render it as
  `YYYY-MM-DDTHH:MM:SS.ffffffZ`.
- WHEN the same argument mapping is presented with a different key insertion order
  THE SYSTEM SHALL produce the identical binding digest.
- WHILE canonicalising THE SYSTEM SHALL keep `20` and `20.0` distinct, and SHALL
  NOT normalise numeric type, string case or percent-encoding inside argument
  values.

### Server identity in the binding

- WHEN the system computes the `server_identity` that enters an approval binding
  THE SYSTEM SHALL use the configured label (`ServerConfig.resolved_identity`)
  combined with a canonical fingerprint of that server's declared transport, and
  SHALL NOT use the observed MCP `serverInfo`, which stays metadata only because a
  remote server states its own `name`/`version`.
- WHEN the transport is `streamable-http` THE SYSTEM SHALL fingerprint
  `{"kind": "streamable-http", "url": <canonical url>}`, where canonicalisation
  lowercases only the scheme and the host, elides an explicit port equal to the
  scheme default (443 for https, 80 for http), and leaves path, query and fragment
  byte-exact.
- WHEN the transport is `stdio` THE SYSTEM SHALL fingerprint
  `{"kind": "stdio", "command": <command>, "args": [<args in order>], "env_names":
  [<sorted env variable names>]}`, with `command` and `args` byte-exact and no
  `PATH` lookup or filesystem resolution; environment variable *values* SHALL NOT
  enter the fingerprint.
- IF an operator changes a server's `url`, `command`, `args`, or the set of `env`
  variable names under an unchanged `name`/`identity` THEN THE SYSTEM SHALL make
  every approval issued before the change invalid.
- IF an operator only rotates an environment variable's *value* THEN THE SYSTEM
  SHALL leave an outstanding approval valid.

### Approval and verification

- WHEN an `Approval` is created THE SYSTEM SHALL populate `approval_id`,
  `action_id`, `server_identity`, `tool_name`, `args_digest`, `policy_version`,
  `approved_by`, `approved_at`, `expires_at` and `binding`.
- WHEN `binding` is computed THE SYSTEM SHALL take sha256 over the canonical JSON
  of exactly `{server_identity, tool_name, args, action_id, policy_version,
  expires_at}` — the full `args` mapping, not its digest — and no other field.
- WHEN `args_digest` is computed THE SYSTEM SHALL take sha256 over the canonical
  JSON of `candidate.args`.
- WHEN `verify_approval(approval, candidate, action_id, policy_version, now)` is
  called THE SYSTEM SHALL return valid only if the binding recomputed from the
  candidate, the supplied `action_id`, the supplied `policy_version` and the
  approval's own `expires_at` equals the stored `binding`, and `now <
  expires_at`.
- IF exactly one of `server_identity`, `tool_name`, any single entry of `args`,
  `action_id` or `policy_version` differs from what was approved THEN THE SYSTEM
  SHALL return invalid.
- IF `now >= approval.expires_at` THEN THE SYSTEM SHALL return invalid.
- IF `expires_at` on a stored approval is mutated THEN THE SYSTEM SHALL return
  invalid even when the new timestamp is still in the future, because `expires_at`
  is part of the canonical binding payload.
- IF `now` is not timezone-aware THEN THE SYSTEM SHALL raise rather than compare.
- WHEN comparing the recomputed binding to the stored one THE SYSTEM SHALL use a
  constant-time comparison.
- WHEN verification fails THE SYSTEM SHALL return a result carrying a `reason` that
  names the first failing check, and SHALL NOT include the `args` themselves in
  that reason.

## Out of scope

- The lifecycle state machine (`PROPOSED -> AUTHORIZED -> ...`) and correlation ids
  beyond `action_id` — issue #7.
- The audit log — issue #7.
- Execution: no `call_tool`, no retry, no verifier. The runtime still executes
  nothing.
- Any UI or MCP tool for approving. An `Approval` is constructed programmatically
  or by a demo script; no new MCP tool is registered in
  `src/newton_mcp/server.py`.
- Persisting approvals or policies anywhere (no DB, no file store beyond reading
  the YAML).
- Approval revocation, single-use/nonce semantics, or an approver identity/signature
  scheme — `approved_by` stays a plain string, not an authenticated principal.
- Nested or dotted argument paths in `arg_ranges`; only top-level argument names.
- Any change to `PhysicalActionContract`, so
  `schemas/physical-action-contract.schema.json` stays byte-identical.

## Open questions

- **`env` values in the stdio fingerprint.** This proposal fingerprints env
  variable *names* only, so credential rotation does not invalidate outstanding
  approvals while adding, removing or renaming a variable does. An owner who
  considers a changed env *value* a re-pointing-class event should say so and the
  fingerprint input becomes the full mapping. Recorded, proceeding with names-only.
- **`confidence is None` against a non-zero `min_confidence`.** Today's code lets a
  `None` confidence pass such a rule. This proposal tightens it to "does not
  match" as a fail-closed change. It is a behaviour change not listed in the
  issue's "unchanged invariants", so it is flagged for veto.
- **`requires_confirmation: true` on a `high`-risk contract.** Today's code returns
  `confirm`, i.e. it *upgrades* what the rules would have denied. This proposal
  reads the issue's invariant as a ceiling ("never downgrades to `auto`") and keeps
  `deny` as `deny`. Flagged because it changes an existing outcome.
- **Where the policy-version pin is enforced.** `verify_approval` compares the
  `policy_version` it is handed, but nothing yet forces a caller to hand it the
  version of the policy currently loaded. That coupling belongs to the executor in
  a later issue; this proposal only makes the mismatch detectable.
- **URL canonicalisation depth.** Only scheme/host case and default ports are
  normalised. Percent-encoding, IDNA and trailing-slash differences therefore
  produce *different* fingerprints, which fails safe (spurious invalidation, never
  spurious validity). Proceeding on that basis.
