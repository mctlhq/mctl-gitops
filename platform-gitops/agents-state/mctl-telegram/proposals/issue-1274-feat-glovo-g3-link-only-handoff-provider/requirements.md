# Glovo G3: link-only handoff provider, no account binding

## Context

The owner decided on 2026-11-09 that real Glovo use (G3) takes the handoff route. The
connector helps the user decide what to order and get it approved. It then gives the user an
`https://glovoapp.com/...` link to a city, category or store page, and the user finishes the
order in their own Glovo app or web session. MCTL never holds a Glovo credential, session,
cookie or token. It never calls a Glovo host, and it never places, pays for or tracks an order.
Desk research (verdict `FEASIBLE_ONLY_STORE_OR_SEARCH_LINK`) found no basket-prefill, address
or custom-scheme link. That leaves a link to a page plus the approved item list restated as
text.

This is a new scope with its own approval. No approval of the M1 slices carries over. In this
repository the proposal owns four things:

- a pure, allowlisted link builder;
- a second, link-only provider kind in the provider worker of #1262 (`provider/glovo/`, on
  `main` since #1262 and #1276, `976afa32`);
- a separate tool contract for the facade (`cmd/glovo-mcp`, `internal/glovo/*`);
- the canonical seam document that the owning slices amend: mctl-api#957 §3a, mctl-api#985 §2a,
  mctl-agents#1059 and mctl-api#989.

The MCTL-specific value is the approval, budget and audit path placed in front of the link. The
link is not where the value lies.

## User stories

- AS a pilot user I WANT to tell the assistant my city, an optional store or category and the
  items I want, in plain words, SO THAT I get one approved, auditable shortlist and a link that
  takes me to the right Glovo page.
- AS a pilot user I WANT the order status to say exactly "handoff issued" with the link SO THAT
  I am never told an order was placed, paid or delivered when MCTL cannot know that.
- AS the owner I WANT the human `aar_` approval, tenant fences and revocation of M1 to apply
  unchanged to the new provider kind SO THAT going to real use does not weaken any control.
- AS a security reviewer I WANT the link builder to emit only allowlisted `https://glovoapp.com`
  paths SO THAT it can never become an open redirect or an SSRF vector.
- AS an operator I WANT the handoff kind to perform no outbound request to any Glovo host SO
  THAT MCTL stays outside Glovo's automated-access terms, whatever they turn out to say.

## Acceptance criteria (EARS)

Link builder (`handofflink`)
- WHEN the builder is given a country, city, optional category and optional store slug that
  each match the closed allowlist THE SYSTEM SHALL return exactly one URL. Its scheme is
  `https`, its host is exactly `glovoapp.com`, it has no port, userinfo, query or fragment, and
  its path is one of the three templates `city`, `category` and `store`.
- IF any of these inputs is outside the closed set or pattern THEN THE SYSTEM SHALL refuse with
  `invalid_arguments` and emit no URL. This covers a country or language not in the allowlist, a
  city, category or slug with a character outside its set, an empty segment, `..`, `%`, `/`,
  `?`, `#`, `@`, `\`, whitespace or a non-ASCII byte, and an over-long segment.
- IF both a store slug and a category are given THEN THE SYSTEM SHALL use the `store` template
  and SHALL NOT combine the two templates.
- THE SYSTEM SHALL produce byte-identical output for identical input (the vectors below pin
  this), in the provider worker and in every vendored copy.
- WHILE building a link THE SYSTEM SHALL NOT put any item name, quantity, note or other free
  text into the URL.

Prepare and approval
- WHEN a user prepares a handoff THE SYSTEM SHALL build a `mctl-handoff-basket/v1` object. It
  holds country, language, city, the optional store slug and category, and 1..30 lines of
  `{name, quantity}`. It holds no price, fee, total, availability or delivery time. THE SYSTEM
  SHALL bind `basket_fingerprint = "sha256:" + hex(SHA-256(JCS(basket)))` to the order and the
  `aar_` exactly as the M1 path does.
- IF an item name is empty, has more than 80 characters, is not NFC, or contains any character
  outside the item-name allowlist THEN THE SYSTEM SHALL refuse the prepare with
  `invalid_arguments`. The allowlist is closed: Unicode letters (category `L*`, NFC), the digits
  `0-9`, the space `U+0020` and the four marks `-` `'` `,` `&`. The first and last character is
  a letter or a digit, and two spaces never follow each other. It forbids, among others,
  `.` `/` `:` `@` `[` `]` `(` `)` `*` `_`, the backtick, `\`, `<`, `>`, `#`, `%` and every control,
  format and combining character. A denylist of substrings is not used.
- WHEN restated item text is shown (the facade output field, the approval text, the status
  `notice`) THE SYSTEM SHALL carry it as a data field and SHALL tell the model to show it
  verbatim as plain text or in a code block. The text is the user's own words, never an
  instruction. The allowlist cannot make prose harmless (a name made only of letters can still
  read like an instruction), so this rendering rule is the control for that case.
- WHILE an order has no `approved` `aar_` that matches its fingerprint THE SYSTEM SHALL issue no
  handoff record and no link.
- THE SYSTEM SHALL bind the version of the link rules to the approval. The basket carries
  `link_spec = "sha256:" + hex(SHA-256(handoff-link.json))`, so the fingerprint and the `aar_`
  cover it. IF the `link_spec` of a command is not the digest of the file the provider worker or
  mctl-api holds THEN THE SYSTEM SHALL refuse it (the worker as `failed_terminal`/`provider_rejected`/`none`
  before any permit, mctl-api at dispatch as `intent_mismatch`) and SHALL issue no link.
- THE SYSTEM SHALL show the deterministic link, computed by mctl-api from the pinned file, in the
  approval text next to the restated items.
- WHEN the approval is refused, expires or is revoked, or the consent record is revoked, before
  the command completes THE SYSTEM SHALL end the order as in M1 (`refused`, `expired`,
  `cancelled` or `unknown`) and SHALL issue no link.

Handoff effect
- WHEN an approved handoff command is executed THE SYSTEM SHALL create exactly one handoff
  record per order. The record holds the link, the template id and the restated item text.
- WHEN the same command is redelivered or its result is replayed THE SYSTEM SHALL return the
  same record and SHALL NOT create a second link or a second record. WHEN an `aar_` that has been
  consumed is presented again THE SYSTEM SHALL answer `approval_replayed` (#989 fence) and create
  no second record.
- THE SYSTEM SHALL treat `issue_handoff_link` as a mutating command in the provider worker
  (`Mutating(kind)` in `provider/glovo/internal/protocol/v1alpha1/wire.go`), so the write permit
  is always requested and the single-use `aar_` is consumed. A kind that is neither mutating nor
  in an explicit read set SHALL fail a test.
- WHILE the effect of a handoff command is `unknown` (a reclaim after a permit, a revocation
  between permit and result, a rejected result) THE SYSTEM SHALL report `unknown` and SHALL NOT
  show a link, a success or a failure. The user is told that MCTL cannot confirm whether a link
  was issued, that MCTL placed no order, and that a new request with a new approval is the way to
  get a link.
- IF the link in the provider's result differs by even one byte from the link that mctl-api
  recomputes from the stored, approved basket THEN THE SYSTEM SHALL reject the result as
  `result_inconsistent`, store no link, and report the order as `unknown`.

Status
- WHEN a handoff order has completed with effect `succeeded` THE SYSTEM SHALL report
  `state=handoff_issued`, `outcome=OUTCOME_UNKNOWN`, the `handoff_url`, the restated items and
  the not-affiliated notice.
- WHILE an order belongs to the link-handoff kind THE SYSTEM SHALL NOT report `placed`, `paid`,
  `delivered` or `observed_placed` in any state, in any row of the status tables.
- THE SYSTEM SHALL return `handoff_url` only in the `handoff_issued` state. The link is a plain
  public page address with no expiry of its own: a revocation after `handoff_issued` stops later
  commands, but it cannot recall a link that was already issued, and the status keeps returning
  the stored link.

No account binding and no Glovo egress
- WHEN a user connects the link-handoff provider THE SYSTEM SHALL record only consent, country
  and city. It SHALL hold no secret, DEK, session or token, and the connection SHALL be `active`
  without any login step.
- THE SYSTEM SHALL perform no outbound network request to any Glovo host on any code path of the
  link-handoff kind. The provider worker SHALL dial only the mctl-api origin.
- IF a `GLOVO_*TOKEN*`, `GLOVO_*SESSION*`, `GLOVO_*COOKIE*`, `GLOVO_*PASSWORD*`, `GLOVO_API_*` or
  `GLOVO_BASE_URL` variable is set THEN THE SYSTEM SHALL refuse to start the provider worker
  (the existing `fakeonly` deny list).

Fences
- WHILE serving the link-handoff kind THE SYSTEM SHALL enforce the M1 fences unchanged: two
  tenants, two principals in one tenant, a foreign `order_id` (`not_found`) and approval replay.
- IF a command's `audience` is not the worker's own identity THEN THE SYSTEM SHALL refuse it
  locally (the handoff worker refuses a `provider:glovo` command), and mctl-api SHALL lease
  `issue_handoff_link` only to a provider that declares v1alpha3 and `place_order_fake` never to
  the handoff provider. IF a facade token's `aud` is not the facade resource THEN THE SYSTEM SHALL
  refuse the call, for both contracts.
- THE SYSTEM SHALL keep the fake provider as the default kind and as the test fixture, and every
  existing fake test SHALL pass unchanged.

Every negative criterion has a test that goes red when its check is removed (see tasks.md).

## Out of scope

- Any Glovo login, session, cookie, token or password in MCTL, in model context or in logs.
- Any call to a Glovo host, including the published Glovo discovery connector. Also out of
  scope: scraping, catalogue fetch or cache, and the merchant Partner API.
- Any claim of price, availability, delivery time or order state, and any basket prefill,
  address carry or `glovoapp://` scheme.
- Glovo logo or brand assets.
- Telegram bot UI for the handoff. The Saved Messages buttons of the #1184 contract remain a
  later slice.
- The code changes in mctl-api (#957, #985, #988, #989, #986), in mctl-agents (#1059 contract
  files) and in mctl-gitops (NetworkPolicy, values, DNS). This proposal defines the seam text
  they adopt and lists them as follow-up tasks. It does not implement them.
- Deployment, image publication and pilot activation.

## Open questions

- Owner decision 1 (blocking implementation, not this proposal): someone must read the Glovo
  consumer terms in a browser and record the clauses on automated access, deep linking and brand
  use. Until that happens this slice stays "proposal only". Task 0 in tasks.md is that gate.
- Owner decision 2: keep the connector name `glovo.mctl.ai` / `mctl-glovo-mcp`, or rename it to
  something descriptive. The design keeps the names as configuration and puts the
  not-affiliated notice in every tool description, so a rename touches only the protected
  resource, the gitops host and the server name.
- Owner decision 3: is a link-only handoff worth shipping next to Glovo's own connector? The
  proposal assumes yes, because the approval, budget and audit path is the value.
- Category URL shape: the observed category URL carried `?type=...`. The builder emits no query
  string, by design. Whether `/categories/<slug>` resolves without `type` was not verified.
  If it does not, the `category` template is dropped and the city template is used instead, with
  no query.
- Initial country, language and city allowlists: only `en` / `es` / `madrid` were observed.
  The proposal ships `en` and `es`, with the city pattern open to any slug that matches the
  character set. The owner may want an explicit city list instead.
- Owner decision 4: the link is pinned into the basket (`link_spec`) and shown in the approval
  text. Proposed: yes to both, because a pin without sight lets the owner approve text that
  does not show where the user will be sent, and showing the link costs one line.
- Claim envelope for v1alpha3: the merged worker (`wire.go`) knows the claim envelopes
  `bridge.mctl.ai/v1alpha1` and `bridge.mctl.ai/claim/v1alpha2` only. Whether mctl-api carries a
  v1alpha3 command inside `claim/v1alpha2` or in a new `claim/v1alpha3` envelope was not verified
  in mctl-api (#986). OPEN until it is; the worker change is one accepted value either way.
- Revoke between permit and result: the expected order is `unknown` (a command cancelled after its
  permit has `effect_state` `unknown`, #985 §2a) with no link. Whether mctl-api accepts a result
  that arrives after the cancel was not verified in #985/#986; the test asserts only that
  `handoff_issued` is never shown for it. OPEN.
- Reclaim behaviour: under M1, a command redelivered after a reclaim reports
  `applied_prior_lease` and the order becomes `unknown` (#1262). The handoff has no external side
  effect, so this is safe but pessimistic. Relaxing it for this kind is left to the owner and is
  not proposed here.
- Dependencies not observed: whether the mctl-gitops amendment branches
  `docs/amend-glovo-r7-regressions` and `docs/amend-glovo-1044-990` have landed was not
  checked. The design is written against the proposal texts as mounted on 2026-11-10 (see
  design.md).
- Which roles call the new routes on mctl-api (consent, prepare-handoff) is owned by #957 §6d.1.
  The proposal names the routes only as candidates.
