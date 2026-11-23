# Design: issue-1274-feat-glovo-g3-link-only-handoff-provider

## Current state

In this repository (`main` at `976afa32`, which contains #1262 and #1276):

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
- **Provider module (on `main`).** `provider/glovo/` is merged (#1262, #1276), so this slice no
  longer waits for it. It holds `internal/protocol/v1alpha1`, `internal/bridgeclient` (an
  origin-pinned RoundTripper, no proxy, no redirects), `internal/executor` (a single outcome
  table), `internal/fakestore` (effects keyed by `command_id`), `internal/fakeonly` (a
  `GLOVO_*TOKEN*`/`SESSION`/`COOKIE`/`PASSWORD`, `GLOVO_API_*`, `GLOVO_BASE_URL` deny list), a
  `BRIDGE_WORKER_IDENTITY` such as `provider:glovo` and `internal/poller`. Facts this design depends
  on, read from `origin/main`:
  - `wire.go:27-30`: `Version` v1alpha1, `VersionV2` v1alpha2, `ClaimVersion` v1alpha1, `ClaimV2`
    `bridge.mctl.ai/claim/v1alpha2`; `wire.go:201,212` embed only the v1alpha2 command schema
    `command-place-order-fake` (`urlCommandV2`); `ParseCommand` (`wire.go:315`) switches on
    `Version` and `VersionV2`, and v1alpha2 accepts `place_order_fake` only; `ParseClaimResponse`
    (`wire.go:389`) accepts the two claim envelopes above and nothing else.
  - `wire.go:124`: `Mutating(kind)` is `kind == KindPlaceOrder || kind == KindCancelOrder`. It
    decides, in `poller.go:285`, whether the permit path runs (`!cmd.Mutating()` goes to
    `RunRead` and returns), and in `bridgefake.go:427`.
  - `poller.go:252`: a command whose `Audience` differs from `Cfg.WorkerIdentity` is dropped as
    `schema_invalid`/`audience_mismatch`.

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
  - #1262 is merged (mctl-telegram `976afa32`, with #1276).
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
The input has already been validated against the item-name allowlist, which is a closed set and
not a denylist: 1..80 runes, NFC, and every rune one of
- a Unicode letter (`unicode.L`);
- an ASCII digit;
- `U+0020` space;
- one of `-` `'` `,` `&`.

The first and last rune is a letter or a digit, and two spaces never follow each other. The set
forbids `.` `/` `:` `@` `[` `]` `(` `)` `*` `_`, the backtick and `\`, so a name cannot carry a
bare domain, a `t.me/` address, an `@handle`, a Markdown link, emphasis or code, and the old
substring checks (`://`, `www.`, `<`, `>`) are subsumed. Combining marks and format
characters are outside the set, which is why the name must be NFC (precomposed letters pass). The
rule lives in `handoff-link.json` beside the vectors, with accept and `must_reject` name
vectors, so mctl-api, the worker and the facade apply the same rule. Free text never reaches
`Build`.

What the allowlist does not do: a name made only of letters, such as an instruction sentence,
passes. The control for that case is rendering. Restated text travels only in the data field
`handoff_items_text` (and in the approval text), the facade output schema constrains each line to
`<quantity> x <name>` with the same character set, the tool description tells the model to show
the field verbatim as plain text or in a code block, and the `notice` says the text is the user's
own words. The text is never placed in the URL, in the `notice`, or in an error.

### 2. Handoff basket and command (contract text for mctl-agents, follow-up task 10)

`mctl-handoff-basket/v1` (`handoff-basket.schema.json`) is closed and has every field required
except the two optionals:

- `v`;
- `lang`;
- `cc`;
- `city`;
- `category?`;
- `store?`;
- `link_spec`: `"sha256:" + hex(SHA-256(bytes of handoff-link.json))`, set by mctl-api at prepare
  from its vendored copy (see "Pinning the link rules" below);
- `lines[1..30]`, each `{name, quantity 1..100}`; `name` follows the item-name allowlist of
  section 1.

It has no price, fee, total, store ref or availability field. The patterns equal
`handoff-link.json`. The fingerprint is `"sha256:" + hex(SHA-256(JCS(basket)))`, using the #1059
JCS implementation and its vectors.

Deliberate difference from #1059. The #1059 approval basket is normalised: lines sorted
ascending by a unique `item_code`, duplicates refused (the merged `checkBasketRules`
in `wire.go` refuses unsorted and duplicate input and never re-sorts). The handoff basket has no
item code and no normalisation. Lines keep the user's order, and both the order and duplicates
are part of what the user approves: restated text is read by a person, and "2 x Agua" is not
"1 x Agua, 1 x Agua". The vectors below use the method of #1059 (JCS, SHA-256), computed here with
a placeholder `link_spec` of `sha256:` followed by 64 zeros; task 10 regenerates them with the real
file digest and a JCS implementation, and they are the contract once vendored:

| id | lines, in order | fingerprint (placeholder `link_spec`) |
|---|---|---|
| A | `Tortilla` x1, `Agua` x2 | `sha256:7f1166755743217ad2cdc829ad53878eee693d947227f92416bc6468daedac7d` |
| B | `Agua` x2, `Tortilla` x1 | `sha256:6b49099540660f44ca79218d46f801fafe1b94c6e4b693bb45612a8e5ec222f2` |
| C | `Agua` x1, `Agua` x1 | `sha256:99159b3ade30b0544510f69039bbc7a53de865dcf6d43f270ec3812ac59b02c2` |
| D | `Agua` x2 | `sha256:78749403e394450a98908eef04e640dbf9d25badafe465d5a10ac1b9e195c706` |

A and B differ, so order is bound. C and D differ, so duplicates are not merged. Common fields:
`v` `mctl-handoff-basket/v1`, `lang` `en`, `cc` `es`, `city` `madrid`, no `category` or `store`.

Pinning the link rules. The link is a function of the basket and of `handoff-link.json`. Without a
pin, an approval could be given for one version of the allowlist and dispatched under another.
So the basket carries `link_spec`, the fingerprint and the `aar_` cover it, and both consumers
check it: the provider worker compares it with the digest of its vendored file and answers
`failed_terminal`/`provider_rejected`/`none` before any permit on a mismatch; mctl-api keeps the
vendored files of every version it has issued, recomputes the link with the file whose digest
equals `link_spec`, and refuses the dispatch as `intent_mismatch` (#985 §2b) when it holds no such
file. The approval text shows the same deterministic link, computed by mctl-api from that file,
next to the restated items, so the owner of the approval sees where the user will be sent
(owner decision 4).

The command schema is `command-issue-handoff-link.schema.json` with `schema_version`
`bridge.mctl.ai/v1alpha3` and `kind` const `issue_handoff_link`. The envelope is the #1059
v1alpha2 write envelope field by field: `approval_ref` required, no `install_revision_ref`, and
`payload` is the handoff basket exactly. It is a new version, not an edit of v1alpha2, because
of the #1059 rule "any byte change is a new `schema_version`". mctl-api leases it only to a
provider whose `BridgeProviderConfig` declares v1alpha3 (#986 `supported_versions`, `Caller.Versions`).
How the command reaches the worker is not verified end to end: the merged worker accepts the claim
envelopes `bridge.mctl.ai/v1alpha1` and `bridge.mctl.ai/claim/v1alpha2` only (`wire.go:29-30,389`) and
embeds no v1alpha3 schema, so the worker needs a `VersionV3` constant, the embedded schema, one new
`ParseCommand` case and, if mctl-api uses a new `claim/v1alpha3` envelope instead of carrying the
command inside `claim/v1alpha2`, one more accepted claim value. Which of the two mctl-api does is
OPEN (requirements, open questions). In M1 that is only
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

`unknown` for this kind (a reclaim after a permit, a revocation between permit and result, a
rejected result) is never shown as success or failure: no link, no items text, `OUTCOME_UNKNOWN`,
and the description of section 5 tells the user what happened. A revocation after `handoff_issued`
cannot recall a link that was already issued, and `handoff_url` has no TTL: it is a public page
address, and the status keeps returning the stored link (retention follows the order record).

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

  Each state value of the `state` enum is a wire state of mctl-api#957 §3a, checked against its
  tables: `open`, `awaiting_approval`, `approved`, `refused`, `expired`, `cancelled`, `dispatched`,
  `failed`, `unknown` all appear there; `handoff_issued` is the new value of section 3 and `placed`
  is deliberately absent. `handoff_items_text` is constrained line by line (`<quantity> x <name>`,
  the item-name character set). Every description ends with the not-affiliated notice. The
  `unknown` description says that MCTL cannot confirm whether a link was issued, that MCTL placed no
  order, and that a new request and a new approval is the way to get a link. There are no order-history, preview or
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
- **`Mutating(kind)` (fail-open if forgotten).** `provider/glovo/internal/protocol/v1alpha1/wire.go:124`
  today returns true for `place_order_fake` and `cancel_order_fake` only. `poller.go:285` sends every
  other kind to `RunRead` and returns before the permit path, so an `issue_handoff_link` command
  would be answered without a write permit, the single-use `aar_` would never be consumed and the
  link could be re-issued on every approval replay. The change adds `KindIssueHandoffLink` to
  `Mutating`, and also makes the function exhaustive: a test walks the closed list of kinds and
  requires each to be mutating or in an explicit read set, so a future kind cannot default to a
  read. The `bridgefake` check at `bridgefake.go:427` uses the same function. A mutation test
  removes the kind from `Mutating` and must go red twice: the unit table, and an end-to-end run
  through `poller` and `bridgefake` that expects exactly one permit request and a consumed `aar_`
  (tasks 7a and T13).
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
  - Forgotten `Mutating` entry: the permit is skipped and the `aar_` is never consumed. A new kind
    in the exhaustive table and an end-to-end permit assertion, both mutation-verified.
  - Allowlist drift between approval and dispatch: `link_spec` in the basket, checked by the worker
    and by mctl-api.
  - v1alpha3 claim envelope: not verified in mctl-api (OPEN); the worker side is one constant, one
    schema and one `ParseCommand` case.
  - The provider tasks no longer wait for #1262 (merged). They do wait for task 10 (the contract
    files) and for the mctl-api lease of v1alpha3.
