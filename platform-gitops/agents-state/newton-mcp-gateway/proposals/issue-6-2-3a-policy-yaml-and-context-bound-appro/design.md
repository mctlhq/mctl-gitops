# Design: issue-6-2-3a-policy-yaml-and-context-bound-appro

## Current state

### The policy engine is in-code, contract-only, and has no version

`src/newton_mcp/action/policy.py` is 69 lines. `Decision` is a `StrEnum`
(`auto`/`confirm`/`deny`), `PolicyRule` carries exactly `goal_prefix`, `max_risk`,
`decision`, `min_confidence`, and `Policy` carries `rules` plus `default`
(`Decision.DENY`). `_RISK_ORDER` lists `Risk` from `READ_ONLY` to `CRITICAL` and
risk comparison is an `index()` on that list.

`Policy.evaluate(contract)` takes only a `PhysicalActionContract`. Its order is:

1. `contract.risk is Risk.CRITICAL` -> `DENY` ("critical risk is never automated").
2. `contract.requires_confirmation` truthy -> `CONFIRM` ("contract requests
   confirmation"). Note this returns *immediately*, so a `high`-risk contract with
   `requires_confirmation=True` currently yields `CONFIRM`, i.e. the flag can
   **raise** authority above what the rules would have granted.
3. First matching rule by `goal_prefix` / `max_risk` / `min_confidence`.
4. `self.default`.

The `min_confidence` check is `if contract.confidence is not None and
contract.confidence < rule.min_confidence: continue` — a `None` confidence
satisfies any `min_confidence`.

There is no `policy_version`, no YAML loader, and neither `Policy` nor `PolicyRule`
sets `extra="forbid"` (unlike every model in `runtime/config.py`).

`Policy.conservative()` builds two rules (`max_risk=LOW, decision=AUTO,
min_confidence=0.8` then `max_risk=MEDIUM, decision=CONFIRM`) with
`default=DENY`. `tests/test_action_contract.py::test_conservative_policy_matrix`
and `::test_explicit_confirmation_overrides_auto` are the only policy tests, and
both call `p.evaluate(_contract(...))` positionally with a contract only.

### The resolver already produces the concrete action, but identity is a label

`src/newton_mcp/runtime/resolver.py` defines `CandidateAction` (frozen, via
`ConfigDict(frozen=True)`) with `server_identity`, `tool_name`, `args`,
`read_tool`, `idempotent`, `score`, `why`. `Resolver._evaluate()` sets
`server_identity=server_config.resolved_identity`, and
`ServerConfig.resolved_identity` in `src/newton_mcp/runtime/config.py` is just
`self.identity if self.identity is not None else self.name`. `args` is the output
of `render_arguments()`, already schema-validated against the discovered tool's
`input_schema`, so it is plain JSON-compatible data.

`Transport` is a discriminated union of `StdioTransport` (`kind`, `command`,
`args: tuple[str, ...]`, `env: dict[str, str]`) and `HttpTransport` (`kind`,
`url`). Every model in that file sets `extra="forbid"` deliberately — the module
docstring says a misspelt key "must fail loudly at load time, never silently widen
what a physical action can reach". `load_runtime_config()` is the loader pattern to
copy: it raises `ValueError` for an unset/blank env var, a missing file, an
unreadable file and unparseable YAML, then lets `model_validate` raise
`ValidationError` for schema problems, and explicitly never falls back to a default.

`src/newton_mcp/runtime/catalog.py` records `ObservedServerInfo(server, name,
version)` from the initialize handshake, with a docstring stating it is
"metadata only. Never used for filtering, ranking or identity".

`docs/action-runtime.md` lines 85-91 state the open question this issue closes
verbatim: "What a server's canonical identity is (config label, transport
fingerprint, observed `serverInfo`, or some combination) and what an approval binds
to is a question for a later, security-relevant proposal". `docs/architecture.md`
lists `approval (tied to the exact normalized action)` as a pipeline box and
already asserts "Approval is invalidated if parameters change after it was granted"
— an assertion no code backs today.

### There is no approval code at all

`grep -rn "approval" src/` finds nothing outside docs. `src/newton_mcp/action/`
contains `contract.py`, `examples.py`, `policy.py`, `prompts.py`, `propose.py`, and
`__init__.py` exporting `Decision`, `Policy`, `PolicyRule` among others. Stack:
Python 3.12, Pydantic v2, `pyyaml`, `jsonschema`, `pytest` with
`asyncio_mode = "auto"`.

## Proposed solution

Four code changes plus one example file and docs. Everything stays synchronous and
executes nothing.

### 1. `src/newton_mcp/canonical.py` (new, ~40 lines)

One neutral, dependency-free module so both `action/` and `runtime/` can digest
without an import cycle (see "Import direction" below).

```python
def canonical_json_bytes(value: Any) -> bytes    # UTF-8, sort_keys, separators=(",", ":"),
                                                 # ensure_ascii=False, allow_nan=False
def sha256_hex(value: Any) -> str                # hexdigest of canonical_json_bytes(value)
def canonical_timestamp(moment: datetime) -> str # aware-only -> UTC -> "...%H:%M:%S.%fZ"
```

`canonical_json_bytes` pre-walks the value and raises `ValueError` on a non-string
mapping key, because `json.dumps` would otherwise coerce `{1: "a"}` and `{"1":
"a"}` to the same bytes. `allow_nan=False` makes `NaN`/`Infinity` raise instead of
emitting non-JSON tokens. No numeric normalisation: `20` and `20.0` serialise
differently and therefore bind differently, which is the fail-safe direction.
`canonical_timestamp` rejects a naive `datetime` outright — a naive `expires_at`
would silently mean "whatever the verifier's local zone is".

### 2. `src/newton_mcp/runtime/config.py` — transport fingerprint

Two properties on `ServerConfig`, no new fields, no schema change to
`runtime.yaml`:

```python
@property
def transport_fingerprint(self) -> str:
    """sha256 of the canonical transport form. Changing url/command/args/env names changes it."""

@property
def binding_identity(self) -> str:
    return f"{self.resolved_identity}@sha256:{self.transport_fingerprint}"
```

The canonical transport form is a plain dict handed to `sha256_hex`:

- `HttpTransport` -> `{"kind": "streamable-http", "url": _canonical_url(self.url)}`.
  `_canonical_url` uses `urllib.parse.urlsplit`. It lowercases the scheme and
  lowercases only the host-name part of the netloc. It drops a port equal to the
  scheme default. Any userinfo (`user:pass@`) and IPv6 brackets are kept byte-exact.
  Path, query and fragment are re-joined byte-exact. The netloc is **not** rebuilt
  from `hostname` + `port`, because that would silently drop userinfo and the IPv6
  brackets, and two URLs that differ only in credentials would then fingerprint the
  same (owner amendment). Nothing else is normalised, so two URLs that differ only in
  percent-encoding fingerprint differently — spurious invalidation, never spurious
  validity.
- `StdioTransport` -> `{"kind": "stdio", "command": self.command, "args":
  list(self.args), "env": dict(self.env)}`. `command` and `args` are byte-exact: no
  `shutil.which`, no `realpath` (both are I/O and non-deterministic, and `resolve()`
  in this package is structurally I/O-free). The full `env` mapping, names and
  values, is fingerprinted (owner amendment). A stdio server's target is often set
  through env (`HA_URL=…`), and the fingerprint cannot tell a credential rotation
  from an endpoint change, so a value change invalidates outstanding approvals. That
  fails safe because approvals are short-lived. Values are only ever sha256 input:
  `binding_identity` carries the digest, never a value, and no reason string or log
  line includes one.

**Why the fingerprint is required at all.** Issue #5 left `server_identity` as the
configured label. The threat that forces the change here is the re-pointing case
the issue names: an operator edits `examples/runtime.example.yaml`'s `home-bridge`
`url` from `https://home-bridge.local/mcp` to some other host, leaving `name:
home-bridge`. With a label-only binding, every outstanding approval for
`set_light_state` stays valid and now authorises a call against a different
server — the approval has become a bearer token for a tool *name*, not a tool.
Binding the transport makes the re-point invalidate those approvals. This does not
add a binding field: `server_identity` remains the single binding key the issue
specifies, its *value* is now the composite string.

**Why the observed `serverInfo` is excluded.** It is asserted by the remote server
during the handshake, so an attacker-controlled substitute can echo whatever
`name`/`version` the approval expects — including it adds no security. It would
also invalidate approvals on a benign version bump. `ObservedServerInfo` stays
metadata, and its existing docstring stays true.

### 3. `src/newton_mcp/runtime/resolver.py` — carry it on the candidate

`CandidateAction` gains one field:

```python
server_identity: str            # unchanged: the configured label, for display/logs
server_binding_identity: str    # new: server_config.binding_identity
```

`Resolver._evaluate()` takes the extra value from the same `server_config` it
already reads `resolved_identity` from. `Rejection` is untouched — a rejection is
never approved. This is additive; scoring, ordering and the filter chain are
unchanged, so `tests/runtime/test_resolver.py` keeps passing except where it
constructs a `CandidateAction` literal.

### 4. `src/newton_mcp/action/policy.py` — YAML, candidate-aware, versioned

```python
POLICY_PATH_ENV_VAR = "NEWTON_MCP_POLICY_PATH"
CONSERVATIVE_POLICY_VERSION = "builtin.conservative.v1"

class ValueRange(BaseModel):     # extra="forbid"
    min: float | None = None
    max: float | None = None     # model_validator: at least one bound, and min <= max

class PolicyRule(BaseModel):     # extra="forbid"
    name: str | None = None
    goal_prefix: str | None = None
    tool_name: str | None = None
    max_risk: Risk = Risk.LOW
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    arg_ranges: dict[str, ValueRange] = Field(default_factory=dict)
    decision: Decision = Decision.AUTO

class Policy(BaseModel):         # extra="forbid"
    policy_version: str = Field(min_length=1)
    rules: list[PolicyRule] = Field(default_factory=list)
    default: Decision = Decision.DENY

def load_policy(path: str | Path | None = None) -> Policy: ...
```

`load_policy` is a near-copy of `load_runtime_config`: `ValueError` naming
`NEWTON_MCP_POLICY_PATH` when unset/blank, `ValueError` for a missing/unreadable
file and for `yaml.YAMLError`, then `Policy.model_validate(data or {})` so a
missing `policy_version` surfaces as a `ValidationError`. No fallback to
`conservative()` — a broken policy file must not silently become a permissive one.

`Policy.conservative()` keeps its zero-argument signature and gains
`policy_version=CONSERVATIVE_POLICY_VERSION`; its rules are unchanged.

`evaluate` becomes:

```python
def evaluate(
    self,
    contract: PhysicalActionContract,
    candidate: ResolvedCandidate | None = None,
) -> PolicyResult:
```

so the two existing positional call sites in `tests/test_action_contract.py` stay
valid. Order:

1. `risk is CRITICAL` -> `DENY`. Unchanged, still first.
2. Walk rules in file order. Per rule, check in this order: `goal_prefix`,
   `tool_name`, `max_risk`, `min_confidence`, then `arg_ranges`.
   - `tool_name` or `arg_ranges` declared while `candidate is None` -> the rule does
     not match (fail closed; it must not match on fewer predicates than it
     declares).
   - `min_confidence > 0` and `contract.confidence is None` -> does not match
     (tightened; see Platform impact).
   - `arg_ranges`: reached only when every other predicate matched. A missing
     argument, a non-numeric value (`bool` excluded explicitly, since `bool` is an
     `int` subclass in Python), or a value outside the inclusive bound returns
     `DENY` immediately and stops the walk. This implements the issue's invariant
     "out-of-range values deny", which is strictly stronger than "the rule does not
     match" — falling through could otherwise let a broader later rule auto-approve
     the very value a narrower rule forbade.
3. No rule matched -> `self.default`.
4. **Confirmation ceiling, applied to the outcome of 2 or 3:** if
   `contract.requires_confirmation is True` and the decision is `AUTO`, raise it to
   `CONFIRM`; `CONFIRM` and `DENY` pass through unchanged.

Step 4 replaces today's early `return CONFIRM`. The issue words the invariant as
"`requires_confirmation: true` never downgrades to `auto`", i.e. a ceiling on
authority, not a fixed outcome. A flag inside a contract — which for the
`propose_action` path is model-authored — must never be able to *grant* more than
the operator's rules do.

### 5. `src/newton_mcp/action/approval.py` (new, ~120 lines)

```python
class ResolvedCandidate(Protocol):
    server_identity: str
    server_binding_identity: str
    tool_name: str
    args: dict[str, Any]

class Approval(BaseModel):       # frozen=True, extra="forbid"
    approval_id: str
    action_id: str
    server_identity: str         # the composite binding identity
    tool_name: str
    args_digest: str
    policy_version: str
    approved_by: str
    approved_at: datetime
    expires_at: datetime
    binding: str

class ApprovalCheck(BaseModel):  # frozen=True
    valid: bool
    reason: str

def compute_binding(*, server_identity, tool_name, args, action_id,
                    policy_version, expires_at) -> str
def create_approval(candidate, *, action_id, policy_version, approved_by,
                    approved_at, expires_at, approval_id) -> Approval
def verify_approval(approval, candidate, action_id, policy_version, now) -> ApprovalCheck
```

`compute_binding` is the single place the payload is assembled:

```python
sha256_hex({
    "server_identity": server_identity,
    "tool_name": tool_name,
    "args": args,
    "action_id": action_id,
    "policy_version": policy_version,
    "expires_at": canonical_timestamp(expires_at),
})
```

Exactly the six fields the issue lists, nothing else. `approved_at`,
`approved_by`, `approval_id` and `args_digest` are deliberately *not* bound: the
binding answers "which action is this approval for", not "who granted it" (that is
audit, issue #7). `args_digest` is a derived convenience/audit field —
`compute_binding` hashes the full `args`, so a digest-only binding never happens.

`verify_approval` checks, in order, returning the first failure with a reason that
names the field but never echoes `args`: `now` aware (raises `ValueError` — a
naive `now` is a programming error, not an invalid approval), `expires_at`
freshness, `server_identity` vs `candidate.server_binding_identity`, `tool_name`,
`args_digest`, `action_id`, `policy_version`, then the recomputed binding compared
with `hmac.compare_digest`. The field-by-field checks exist only for actionable
reasons; the binding recompute is authoritative and is what catches the
`expires_at`-mutation case (the payload uses `approval.expires_at`, so editing it
changes the recomputed digest while the stored `binding` does not follow).

`ResolvedCandidate` is a `typing.Protocol`, following the `SupportsListTools`
protocol already used in `runtime/catalog.py`, so `action/` never imports
`runtime/`.

**Import direction.** Today `runtime/resolver.py` imports `action/contract.py`;
`action/` imports nothing from `runtime/`. If `policy.py` imported
`CandidateAction`, then importing `newton_mcp.action` would run
`action/__init__` -> `policy` -> `runtime.resolver` -> `action.contract` while
`action/__init__` is still initialising: a real circular import. The Protocol keeps
the existing one-way edge, and `canonical.py` sits at `src/newton_mcp/` so
`runtime/config.py` can use it without touching `newton_mcp.action` at all.

### 6. `examples/policy.example.yaml` (new) and docs

Modelled on `examples/runtime.example.yaml`: a header comment repeating the epic's
safe-demo rule, then safe capabilities only — the HVAC comfort band
(`target_temperature_c` in `[20, 25]`, matching the example contract's
`minimum_temperature_c: 20` / `maximum_temperature_c: 25`), lights, a speaker
announcement — and an explicit `default: deny`.

```yaml
policy_version: "example.v1"
default: deny
rules:
  - name: hvac-within-comfort-band
    goal_prefix: reduce_room_temperature
    tool_name: set_target_temperature
    max_risk: low
    min_confidence: 0.8
    arg_ranges:
      target_temperature_c: { min: 20, max: 25 }
    decision: auto
  - name: lighting
    tool_name: set_light_state
    max_risk: low
    min_confidence: 0.8
    decision: auto
  - name: announcements
    goal_prefix: announce
    tool_name: announce
    max_risk: low
    decision: confirm
```

Docs: `docs/action-runtime.md` replaces the deferred-identity paragraph (lines
85-91) with the decision taken here plus the re-pointing rationale. It states
explicitly that `binding` is **context-binding, not authentication**: a keyless
sha256 shows which exact action an approval covers, but anyone able to write an
`Approval` can compute a valid binding, so it does not prove who approved
(owner amendment; signed approvals are out of scope). and drops
"policy evaluation" / "bind an approval" from the "what this package does not do"
list while keeping execute/lifecycle/audit there. `docs/architecture.md` marks the
approval box implemented and points its "Approval is invalidated if parameters
change" sentence at `compute_binding`. `README.md` line 160's "no policy, no
approval" is narrowed to "no execution, no lifecycle, no audit". Wording stays
"this project's experimental proposal" and "mock-validated" throughout — nothing
here has run against a live MCP actuator.

## Alternatives

1. **Bind the configured label only, as #5 left it.** Smallest diff and no change
   to `runtime/` at all. Dropped: it leaves exactly the re-pointing hole the issue
   asks this proposal to resolve, and `docs/action-runtime.md` already promised a
   decision. An approval that survives its server being swapped is not
   context-bound in any useful sense.

2. **Add a separate `transport_fingerprint` field to the binding payload.**
   Arguably clearer to read in an audit record. Dropped: the issue says "The
   binding fields listed above stay as specified, and anything added must be
   justified by the re-pointing threat" — folding the fingerprint into the
   `server_identity` value keeps the payload at exactly six keys and keeps the
   field list reviewable against the issue.

3. **Include the observed `serverInfo` in the fingerprint.** Dropped: it is
   self-asserted by the remote peer, so it adds no resistance to server
   substitution, and a benign version bump would invalidate live approvals. Keeping
   it as metadata also preserves `ObservedServerInfo`'s existing docstring.

4. **Pass the `RuntimeConfig` into `verify_approval` and compute the fingerprint
   there.** Avoids touching `CandidateAction`. Dropped: it contradicts the
   signature the issue specifies (`approval, candidate, action_id, policy_version,
   now`) and would make the verifier depend on the config being the same one the
   resolver used — a second thing to get wrong.

5. **A JSON Schema file for the policy, validated with the existing `jsonschema`
   dependency.** Dropped: `runtime.yaml` is validated by Pydantic with
   `extra="forbid"`, and following that precedent means one schema source of truth
   (the model) rather than two that can drift. `jsonschema` stays where it is used
   today — validating *discovered tool* input schemas in `resolver.py`.

6. **A new `evaluate_candidate()` method, leaving `evaluate()` contract-only.**
   Dropped: two entry points into a security decision invite the wrong one being
   called. An optional `candidate` parameter that makes candidate-dependent rules
   fail closed gives the same backward compatibility with one code path.

## Platform impact

**Migrations.** None in the platform sense — no DB, no deployment, no Kubernetes,
nothing persisted. `runtime.yaml` files are unchanged (the fingerprint is derived
from fields that already exist). A policy file is new and opt-in:
`NEWTON_MCP_POLICY_PATH` unset only means `load_policy()` raises; `Policy(...)`
constructed in code and `Policy.conservative()` keep working. Add
`NEWTON_MCP_POLICY_PATH` to `.env.example`.

**Backward compatibility.** Four intentional breaks, all in the fail-closed
direction, none silent:

- `Policy(...)` without `policy_version` now raises `ValidationError`. Required by
  the issue. Only `Policy.conservative()` constructs a `Policy` in `src/`, and it
  supplies the built-in version.
- `PolicyRule`/`Policy` gain `extra="forbid"`, so a previously-ignored unknown key
  now raises. Matches `runtime/config.py`'s stated philosophy for allow-lists.
- `requires_confirmation: true` on a contract the rules would `deny` now yields
  `deny` instead of `confirm`. `tests/test_action_contract.py::
  test_explicit_confirmation_overrides_auto` uses `risk="low"` and stays green; the
  changed case is untested today. Flagged as an open question.
- A `None` `confidence` no longer satisfies a non-zero `min_confidence`. Flagged as
  an open question.

`CandidateAction` gains a field rather than changing one, so
`candidate.server_identity` keeps its #5 meaning for logs and `why` strings. Any
test that builds a `CandidateAction` literal must add
`server_binding_identity`. `PhysicalActionContract` is untouched, so
`schemas/physical-action-contract.schema.json` needs no regeneration and
`test_schema_file_is_in_sync_with_model` stays green.

**Resource impact.** Negligible: one `yaml.safe_load` of a small file at load time,
a handful of sha256 digests over small dicts per approval. No new dependency —
`hashlib`, `hmac`, `json`, `urllib.parse`, `datetime` are stdlib and `pyyaml` is
already a dependency, so `uv.lock` is unchanged.

**Risks and mitigations.**

- *A canonicalisation bug collapses two different actions to one digest.* Mitigated
  by refusing every ambiguity-creating input (non-string keys, `NaN`, naive
  datetimes) rather than coercing, by normalising nothing inside argument values,
  and by the per-bound-field test matrix (one test per field, plus the key-order
  test).
- *Over-normalised URLs make two servers fingerprint alike.* Only scheme/host case
  and default ports are elided, both RFC 3986 equivalences. Every other difference
  produces a different fingerprint, so the failure mode is a spuriously invalid
  approval, not a spuriously valid one.
- *Approvals invalidated by benign config edits become an operator annoyance and
  get worked around.* Mitigated by scoping the fingerprint to transport
  re-pointing (observed `serverInfo` excluded; env values included by owner decision,
  accepting that a credential rotation invalidates short-lived approvals) and by documenting
  in `docs/action-runtime.md` that a transport edit invalidates outstanding
  approvals.
- *`verify_approval` returning `ApprovalCheck(valid=False, ...)` rather than
  raising invites a caller ignoring the return value.* Mitigated by mirroring the
  existing `PolicyResult` shape (a reason is needed, not just a boolean) and by
  there being no executor yet to misuse it; the executor issue must treat a falsy
  `valid` as terminal.
- *A reason string leaks argument values into a log.* `verify_approval` reasons name
  fields and digests only, never `args` contents; asserted in a test.
- *Scope creep into #7.* No lifecycle enum, no audit record, no correlation id
  beyond `action_id`, no `call_tool`. `approved_by` stays a plain string.
