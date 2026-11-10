# Design: issue-1274-feat-glovo-g3-link-only-handoff-provider

## Current state

In this repository (`main` at `641ce02`):

- **Facade.** `cmd/glovo-mcp/main.go` with `internal/glovo/{authn,config,contract,facade,mctlapi,tools}`.
  - `internal/glovo/tools/tools.go` registers exactly the contract tools through one handler
    template: strict arguments (`jsonstrict.RejectDuplicateKeys`, `ValidateInput`), a scope
    check, a per-call `API.Resolve`, one `API.Do(op)` and `ValidateOutput`. Every failure is a
    typed refusal.
  - The `impls` map binds seven tool names to `mctlapi.Op` values. `NewMCPServer` fails if the
    contract and the map differ.
- **Contract.** `docs/contracts/glovo-mcp-tools.json` (`$id .../glovo-mcp-tools/v1alpha1`,
  resource `https://glovo.mctl.ai/mcp`, scopes `glovo:read` and `glovo:basket:prepare`) is
  embedded byte-equal as `internal/glovo/contract/glovo-mcp-tools.json`
  (`TestEmbeddedCopyEqualsDocsContract`).
  - `glovo_order_status` outputs `{state (free string), outcome (OUTCOME_UNKNOWN|observed_placed), handoff_url?}`.
  - `glovo_connect_account` returns `pending_handoff` and a `handoff_url`, which is an account
    binding.
  - `glovo_prepare_order` takes a `preview_id` from order history.
- **Contract test.** `docs/glovo_contract_test.go` pins the tool allowlist. It forbids the
  tool-name regex `place|pay|checkout|purchase|submit_order` and the input properties `url`,
  `endpoint`, `cookie`, `session`, `token` and others. It requires every object to be closed.
- **Wire to mctl-api.** `internal/glovo/mctlapi/mctlapi.go` holds the candidate harness wire
  `glovo-facade-mctl-api/v1alpha1` with a closed refusal set. It is served only by
  `internal/glovo/mctlapi/fakeapi/fakeapi.go`, whose order status always answers
  `OUTCOME_UNKNOWN`. `docs/glovo-mcp.md` says the facade is `BLOCKED_FOR_REAL_API` until
  mctl-api#957 lands.
- **Import boundary.** `internal/glovo/imports_test.go` uses `go list -deps` to keep Telegram,
  Temporal and gotd packages out of `cmd/glovo-mcp`, and the facade out of `cmd/server`.
- **Earlier handoff design.** `docs/contracts/glovo-checkout-handoff.md` (#1184 spike) already
  has a `handoff_issued` state, `HandoffTarget -> {app_open|web_url|unverified}`, and "MCTL
  never pays". `docs/adr/0010-glovo-multitenant-connections.md` defines G3 as "legally and
  technically reviewed real account access". `docs/agent-runtime/glovo-threat-model.md` lists
  TM1-TM16. None of them has a link-only provider.
- **Redaction.** `internal/audit/redact.go` (line 138) already redacts the facade's forwarded
  token and scope handle. `internal/netsafe/netsafe.go` exists for outbound safety.
- **No provider module.** There is no `provider/` directory on `main` (`ls provider` fails). The
  provider worker is designed in #1262 and exists only as a draft (#1258 branch). #1262 places it
  at `provider/glovo/` with `internal/protocol/v1alpha1`, `internal/bridgeclient` (an
  origin-pinned RoundTripper, no proxy, no redirects), `internal/executor` (a single outcome
  table), `internal/fakestore` (effects keyed by `command_id`), `internal/fakeonly` (a
  `GLOVO_*TOKEN*`/`SESSION`/`COOKIE`/`PASSWORD`, `GLOVO_API_*`, `GLOVO_BASE_URL` deny list) and a
  `BRIDGE_WORKER_IDENTITY` such as `provider:glovo`.

Seam texts read (mctl-gitops `agents-state`, as mounted 2026-11-10):

- **mctl-api#957 §3a** (proposed). `GET /orders/{order_id}` is `{state, outcome}`, and
  "`handoff_url` is never part of this body". The row (`completed`, `succeeded`) maps to
  `placed` / `observed_placed`. That row must never apply to a handoff.
- **mctl-api#985 §2a "Result to order"** (proposed). `reconcileOrder` keys one table by
  (`status`, `effect_state`) alone. (`completed`, `succeeded`) leads to `MarkClosed` and wire
  `placed`. The table has no notion of command kind.
- **mctl-agents#1059** (merged).
  - The only v1alpha2 write is `place_order_fake`, whose payload is the approval basket
    `mctl-approval-basket/v1`. That basket has priced `FAKE-` item codes and a `pst_` store ref.
    Its fingerprint is SHA-256 over JCS.
  - The result is the unchanged v1alpha1 `result.schema.json`, which has no data payload, only
    `result_ref`.
  - "Any byte change to a schema is a new `schema_version` and a new `$id`."
  - mctl-api leases a version only to a provider whose `BridgeProviderConfig` declares it.
- **mctl-telegram#1262** (proposed). It covers the provider state machine and outcome map.
  `permit_already_issued` and a reclaim give `failed_terminal`/`unknown`.

Deployed state checked:

- `mctl_list_services(team=labs)`: `complete=true`, 21 services. No `glovo-mcp` and no Glovo
  provider worker is deployed. The only related services are `mctl-telegram` (`tg.mctl.ai`,
  0.137.1) and `mctl-telegram-preview`.
- `$MCTL_GITOPS_ROOT/services/labs/`: no `glovo*` directory. `grep -rli glovo` over `services/`
  and `tenants/` matched nothing.
- `agents-state/*/proposals/*glovo*` and `.status.yaml`:
  - #957, #985, #989, #990, #954, #961 and #1044 are `proposed`;
  - #960 is `accepted`;
  - #988 and #1236 are `implemented`;
  - #959, #1059, #1184, #1227, #1235 and mctl-gitops#2470 are `merged`;
  - #1262 is `proposed`.
- Not observed: whether the amendment branches `docs/amend-glovo-r7-regressions` and
  `docs/amend-glovo-1044-990` have merged (no branch view in this checkout), and the mctl-api
  deployed values. Both are recorded under Open questions in requirements.md. Neither is assumed
  absent.

## Proposed solution

### 0. Shape

```
user/model --(city, store?, category?, items as text)--> facade glovo_prepare_handoff
  -> mctl-api: build mctl-handoff-basket/v1, fingerprint, order (#988, provider_kind=link_handoff), aar_ (#989)
  -> human approves the aar_ (unchanged M1 path)
  -> #985 dispatch: command kind issue_handoff_link, schema bridge.mctl.ai/v1alpha3,
     leased only to provider:glovo-handoff
  -> provider worker (link_handoff kind): write-permit (consumes aar_) -> handofflink.Build -> result{handoff}
  -> mctl-api recomputes the link from the stored basket, byte-compares, stores ONE handoff record
  -> glovo_order_status: state=handoff_issued, outcome=OUTCOME_UNKNOWN, handoff_url, items_text, notice
```

The handoff is still a bridge *mutation*. It requires `approval_ref` and a write permit, so the
#989 fence consumes the single-use receipt exactly once. The M1 approval, fencing and
revocation are reused rather than re-argued. The "effect" is the creation of a record in MCTL;
nothing is written to Glovo.

### 1. Link builder (new, pure): `provider/glovo/internal/handofflink`

The package has no `net/http`, `net` or `os` imports; a `go list -deps` boundary test enforces
this. It imports `net/url` only to parse its own output in the final self-check.

Templates (closed; the template id is part of the result):

| id | path |
|---|---|
| `city` | `/{lang}/{cc}/{city}` |
| `category` | `/{lang}/{cc}/{city}/categories/{category}` |
| `store` | `/{lang}/{cc}/{city}/stores/{store}` |

The host is the constant `glovoapp.com` and the scheme is the constant `https`. The query and
fragment are always empty.

Character sets (ASCII only, checked before assembly):

| field | rule |
|---|---|
| `lang` | closed set, initially `{en}` |
| `cc` | closed set, initially `{es}` (the only country observed) |
| `city` | `^[a-z](?:[a-z0-9]\|-(?=[a-z0-9])){1,47}$` (no leading or trailing `-`, no `--`) |
| `category` | `^[a-z][a-z0-9_]{0,47}$` (as `food_1`) |
| `store` | `^[a-z0-9](?:[a-z0-9]\|-(?=[a-z0-9])){1,95}$` |

The `cc` and `lang` sets and the patterns live in one data file,
`handoff-link.json`, together with `vectors`. The vectors are accept cases with the exact
expected output and `must_reject` cases:

- `../x`;
- `madrid%2F`;
- `madrid/`;
- `ma drid`;
- `MADRID`;
- `madrid?x=1`;
- `madrid#x`;
- `user@evil`;
- `evil.com`;
- the Cyrillic `а` homoglyph;
- an empty segment;
- an over-long segment;
- a `cc` outside the set;
- `lang=es` while only `en` is listed.

The canonical copy of this file is owned by mctl-agents (task 10, next to the #1059 contracts,
under `docs/contracts/bridge/handoff/v1alpha1/`). It is vendored byte for byte, with sha256 pins,
into `provider/glovo/internal/handofflink/testdata/` and into mctl-api, where the link is
recomputed.

`Build(in Input) (Link{URL, TemplateID}, error)`:

1. Validate every field against its rule. A store slug takes precedence over a category, and the
   two templates are never combined.
2. Assemble the path with string concatenation of the already-validated segments.
3. Self-check: `url.Parse(out)` must give `Scheme=="https"`, `Host=="glovoapp.com"`,
   `User==nil`, `Port()==""`, `RawQuery==""`, `Fragment==""`, `Opaque==""`, and a path that
   matches the full template regex. Any failure returns `ErrRefused`.

Test matrix T2/T3: there is one negative test per rule. With the rule's check removed, that
test must go red.

`ItemsText(lines) string` renders the approved lines as `"<quantity> x <name>"`, one per line.
The input has already been validated: NFC, no control or format characters (`unicode.Cc`/`Cf`),
1..80 runes, and no `://`, `www.`, `<` or `>`. Free text never reaches `Build`.

### 2. Handoff basket and command (contract text for mctl-agents, follow-up task 10)

`mctl-handoff-basket/v1` (`handoff-basket.schema.json`) is closed and has every field required
except the two optionals:

- `v`;
- `lang`;
- `cc`;
- `city`;
- `category?`;
- `store?`;
- `lines[1..30]`, each `{name, quantity 1..100}`.

It has no price, fee, total, store ref or availability field. The patterns equal
`handoff-link.json`. The fingerprint is `"sha256:" + hex(SHA-256(JCS(basket)))`, using the #1059
JCS implementation and its vectors. Lines keep the user's order, and both the order and
duplicates are part of what the user approves.

The command schema is `command-issue-handoff-link.schema.json` with `schema_version`
`bridge.mctl.ai/v1alpha3` and `kind` const `issue_handoff_link`. The envelope is the #1059
v1alpha2 write envelope field by field: `approval_ref` required, no `install_revision_ref`, and
`payload` is the handoff basket exactly. It is a new version, not an edit of v1alpha2, because
of the #1059 rule "any byte change is a new `schema_version`". mctl-api leases it only to a
provider whose `BridgeProviderConfig` declares v1alpha3. In M1 that is only
`provider:glovo-handoff`. The fake provider is never handed it, and the handoff provider is
never handed `place_order_fake`.

The result schema is `result-handoff.schema.json` (`bridge.mctl.ai/v1alpha3`). It is the
v1alpha1 result properties plus a required `handoff` object
`{template_id: enum[city,category,store], url: string(pattern = the three templates), basket_fingerprint}`.
`handoff` is allowed only together with `outcome=succeeded` and `provider_effect=applied`, and is
forbidden otherwise. `effect_state` keeps its existing six values, so the issue's "new kind or
new effect_state" is answered with a **new kind**.

mctl-api's `SubmitResult` for this kind does three things:

1. It recomputes `handofflink.Build` from the stored basket using the vendored data file.
2. It compares `url`, `template_id` and `basket_fingerprint` byte for byte. A mismatch is 422
   `result_inconsistent` and the effect becomes `unknown`.
3. It inserts one `glovo_handoff_record` row (unique on `order_id`, and on `command_id`) in the
   result transaction. A replay finds the row and answers `replayed:true`.

A provider-supplied link is therefore only ever compared, the same rule #1059 applies to the
fingerprint.

The #989 write fence recomputes the fingerprint from the payload. For this kind it parses the
handoff basket instead of the approval basket; that is a one-line dispatch on `schema_version`
in #989.

### 3. Status and transition rows (seam text for mctl-api#957 §3a and #985 §2a)

#988 `Order` gains `provider_kind` (`fake` default, `link_handoff`), set at prepare and
immutable. `CommandEffect` returns (`kind`, `status`, `effect_state`). Both tables gain a leading
`kind` key. Every existing row is scoped to `place_order_fake`. For `issue_handoff_link` the
rows are identical except one:

| kind | status | effect_state | #988 call | #989 call | wire `state` | wire `outcome` |
|---|---|---|---|---|---|---|
| `issue_handoff_link` | `completed` | `succeeded` and a handoff record exists | `MarkClosed` | none (the permit consumed it) | `handoff_issued` | `OUTCOME_UNKNOWN` |
| `issue_handoff_link` | `completed` | `succeeded`, no handoff record | none | none | 503 `unavailable` (invariant) | none |

A totality test covers every (kind, status, effect_state). Its guard asserts that no
`issue_handoff_link` row yields `placed` or `observed_placed`. The pre-dispatch rows (`open`,
`awaiting_approval`, `approved`, `refused`, `expired`, `cancelled`, `unknown`) are unchanged for
both kinds.

The §3a body gains, **only** for `state=handoff_issued`:

- `handoff_url` (from the record);
- `handoff_items_text`;
- `notice` (the const "Not affiliated with Glovo. Finish the order in your Glovo app or on
  glovoapp.com; prices, availability and delivery are shown there.").

This reverses the §3a line "`handoff_url` is never part of this body" for this kind only.

### 4. Consent record, not account binding (seam text for #959/#961)

The `link_handoff` connection kind has states `active`, `revoked` and `expired`. It stores
`{consent_at, cc, city}` and has no sealed secret, DEK or provider identity. Creating it is
immediately `active`. Revoke and expiry reuse #959 `LiveConnection` and the #985
`CancelOpenForConnections`, so an open handoff command is cancelled exactly as in M1.

### 5. Facade (this repo): a second contract, chosen at startup

- New file `docs/contracts/glovo-handoff-mcp-tools.json` (`$id .../glovo-handoff-mcp-tools/v1alpha1`),
  with an embedded copy under `internal/glovo/contract/`. Same resource and scopes. The tools are:
  - `glovo_auth_status`: output `{connection_state: none|active|revoked|expired, connection_id?, cc?, city?}`.
  - `glovo_record_handoff_consent`: input `{cc, city, idempotency_key}`; output
    `{connection_id, state: const active, cc, city}`. There is no `handoff_url`, because there is
    nothing to log in to.
  - `glovo_prepare_handoff`: input `{city?, category?, store?, lines[1..30]{name, quantity}, idempotency_key}`.
    `city` defaults to the consent city and `cc` always comes from the consent. The output is
    `{order_id, fingerprint, consent_request_id, expires_at}`, the same as `glovo_prepare_order`.
  - `glovo_order_status`: output
    `{state: enum[open,awaiting_approval,approved,refused,expired,cancelled,dispatched,handoff_issued,failed,unknown], outcome: const OUTCOME_UNKNOWN, handoff_url?(pattern = templates), handoff_items_text?, notice?}`.

  Every description ends with the not-affiliated notice. There are no order-history, preview or
  basket tools, because there is no catalogue.
- `internal/glovo/config`: new `GLOVO_MCP_PROVIDER_KIND` = `fake` (default) | `link_handoff`.
  It selects the contract and the `impls` map. One process serves exactly one contract, and the
  default behaviour is byte-identical to today.
- `internal/glovo/tools`: an `impls` map per kind, so `NewMCPServer` keeps its "exact match"
  check for each. `internal/glovo/mctlapi`: new ops `OpConsent` (`POST /handoff-consents`) and
  `OpPrepareHandoff` (`POST /handoffs:prepare`), as candidate harness routes for #957 to freeze.
  `fakeapi` serves them, including a `handoff_issued` order that uses the vendored vectors.
- `docs/glovo_contract_test.go` checks both contracts:
  - the allowlist is per contract;
  - the forbidden-input set gains `link`, `href`, `redirect`, `host`, `cc_url`;
  - the handoff `state` enum must not contain `placed`, `paid` or `delivered`;
  - `outcome` must be the const `OUTCOME_UNKNOWN`;
  - the `handoff_url` pattern must anchor `^https://glovoapp\.com/`.

  The output-schema pattern is a third, independent fence. A link that slipped past both
  builders is refused as `upstream_invalid` at the facade.

### 6. Provider worker (this repo, on top of #1262)

- `provider/glovo/cmd/glovo-provider-worker/config.go`: `GLOVO_PROVIDER_KIND` = `fake`
  (default) | `link_handoff`. `link_handoff` requires
  `BRIDGE_WORKER_IDENTITY=provider:glovo-handoff`, so it is a separate deployment and a separate
  `ProviderRef`, and it refuses the fake identity. `fakeonly.Check` and its deny list stay on for
  both kinds; the handoff kind has no Glovo credential to hold.
- `provider/glovo/internal/protocol`: vendor the v1alpha3 command and result schemas, pinned by
  sha256. `ParseCommand` accepts v1alpha3 only with `kind == issue_handoff_link` and only in the
  `link_handoff` kind. The fake kind refuses it locally as `ErrInvalid`, and the handoff kind
  refuses every fake kind.
- `provider/glovo/internal/executor`: a new `handoffstore` replaces `fakestore` for this kind.
  It keeps an in-memory `EffectOf(command_id)` with the same dedupe, so state machine step 4 of
  #1262 is reused unchanged:
  1. read back;
  2. permit;
  3. `handofflink.Build`;
  4. `succeeded`/`applied` with `handoff{...}`.

  Errors from `Build` give `failed_terminal`/`provider_rejected`/`none` with no permit
  requested. The builder runs before the permit, as a pre-flight check. The outcome table gains
  these rows in the single `executor` table.
- Egress: the #1262 origin-pinned RoundTripper is the only HTTP client in the module. A test
  installs a recording `DialContext` and runs the full link-handoff path against `bridgefake`. It
  asserts that every dial goes to the mctl-api origin, and no dial goes to any other host, `glovoapp.com`
  included. A static test asserts that the literal `glovoapp.com` appears only in `handofflink`
  and its testdata. NetworkPolicy (default-deny egress except mctl-api and DNS) is mctl-gitops
  follow-up task 13. The runbook documents it.

### 7. Docs

- `docs/contracts/glovo-link-handoff.md`: the canonical seam text for sections 1-6, and the
  owner gate.
- `docs/agent-runtime/glovo-threat-model.md` gains:
  - TM17: open redirect / SSRF through the link (closed templates, recompute-compare, output
    pattern);
  - TM18: a false order claim (no `placed` row for the kind);
  - TM19: prompt injection through item names (text-only, validated, never in the URL);
  - TM20: brand and terms (owner gate, notice, no logo).
- `docs/adr/0010-glovo-multitenant-connections.md`: a note that the G3 handoff route needs owner
  decision 1 instead of account-access review.
- `docs/glovo-mcp.md`: the `GLOVO_MCP_PROVIDER_KIND` row.

## Alternatives

1. **Build the link in mctl-api and skip the provider worker.** The link is a pure function of
   the approved basket, so this is the smallest design. It was dropped because the issue places
   the effect in the #1262 worker, behind the same command bridge and permit. Without the
   worker, the approval would need a second, non-bridge consume path in #989. The recompute-compare
   rule keeps most of the alternative's safety: mctl-api never trusts a provider link.
2. **A new `effect_state` (`handoff_issued`) instead of a new kind.** This was dropped.
   `effect_state` drives the write-fence and reclaim machine in mctl-api (`permitted -> unknown`
   and others). A seventh value touches every transition and every #1044 pair guard, while a
   new kind only adds a key to two tables.
3. **Extend v1alpha2 `place_order_fake` with optional text lines.** This was dropped. #1059
   forbids in-version changes, the basket would mix priced fake items with unpriced free text,
   and the fake's `placed` row would apply.
4. **Use Glovo's own discovery connector for item search.** This was dropped as out of scope.
   It is an outbound call to a Glovo host, and it carries live prices that MCTL must not claim.

## Platform impact

- **Migrations.** This repo has none; the stores are in memory and the facade has no database.
  In mctl-api (follow-up): `orders.provider_kind` (default `fake`), a new table
  `glovo_handoff_record (order_id unique, command_id unique, url, template_id, fingerprint, items_text, created_at)`,
  and connection kind `link_handoff`. All are additive.
- **Backward compatibility.** The default kind is `fake` in both binaries, and the existing
  contract, `impls`, golden wire fixtures and every fake test are unchanged. A
  `GLOVO_MCP_PROVIDER_KIND` that is unset behaves as today. The v1alpha1 and v1alpha2 schemas are
  unchanged, and v1alpha3 is leased only to a provider that declares it.
- **Resources.** One more worker deployment at deploy time, which is not part of this slice. CI
  gains a few unit tests. There is no new dependency: `handofflink` is stdlib only.
- **Risks and mitigations.**
  - Open redirect: closed templates, ASCII-only patterns, a parse-back self-check, mctl-api
    recompute-compare and the facade output pattern. That is three independent fences, each
    with a red test.
  - A false claim of placement: no `placed` row exists for the kind, enforced by a totality and
    guard test, and `outcome` is a const in the handoff contract.
  - Glovo terms or brand: implementation is gated on owner decision 1 (task 0), a notice goes in
    every description and status, there is no logo, and the name is a config value.
  - Prompt injection through item names: validated text, never in the URL, and restated only as
    approved.
  - Seam drift across four repos: the canonical data file and schemas live in mctl-agents and are
    vendored with sha256 pins, the same mechanism as #1059.
  - #1262 not merged: the provider tasks (1, 5-7) need its `provider/glovo` module and wait for
    it. The facade, contract and docs tasks (2-4, 8) do not depend on it and can be reviewed first,
    behind the default `fake` kind.
