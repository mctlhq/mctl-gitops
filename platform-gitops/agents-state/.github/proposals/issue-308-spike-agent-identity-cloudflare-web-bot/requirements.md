# Spike: Cloudflare Web Bot Auth as operator identity for governed MCTL agent egress

## Context

Issue mctlhq/.github#308 asks whether MCTL can act as a Cloudflare Web Bot Auth
/ Verified Bots *Intermediary* operator for controlled outbound HTTP actions, so
that sites behind Cloudflare can recognise MCTL-originated agent traffic. The
spike must not create a second identity or authorization plane. A Web Bot Auth
signature (HTTP Message Signatures, RFC 9421, Ed25519, with a signed JWKS key
directory at `/.well-known/http-message-signatures-directory`) identifies only
the *operator* of a request. Tenant, principal, exact action, approval, budget,
audit and revocation remain MCTL decisions, owned by the governed decision chain
(.github#181 / mctl-api#701), Commerce authority (.github#173 / mctl-api#549) and
the existing execution and correlation identity (`work_item_id`, see
`docs/spikes/journey-intent-correlation.md`).

This is a discovery spike (P2, timebox 2 agent working days). The deliverable is
a report under `docs/spikes/`, a `SpikeDefinition` manifest under
`roadmap/spikes/`, and a self-contained, offline reference harness with
fixture-only keys, following the `docs/spikes/mcp-gateway-g0/` precedent. The
report proposes exactly one verdict from `ADOPT | LIMITED | DEFER | REJECT`.
Only the owner records the decision. Nothing is deployed, registered or paid for.

## User stories

- AS the platform owner I WANT a primary-source-pinned assessment of Web Bot
  Auth eligibility, Verified Bots classification and protocol limits SO THAT I
  can decide whether MCTL should invest in a signed egress path at all.
- AS a security reviewer I WANT a threat, tenant-isolation, key-lifecycle and
  replay analysis SO THAT a later signed egress cannot become a bypass of MCTL
  authorization or a PII leak.
- AS an mctl-agents / mctl-api maintainer I WANT a per-surface matrix of which
  outbound HTTP clients MCTL actually controls SO THAT any follow-up targets only
  instrumentable clients.
- AS a site operator receiving MCTL agent traffic I WANT the operator identity
  to be verifiable and free of end-user identifiers SO THAT I can apply my own
  allow/block policy without learning who the user is.

## Acceptance criteria (EARS)

- WHEN the spike report is written THE SYSTEM SHALL contain an evidence-pin
  table listing every repository read with a 40-hex commit, and every external
  document (Cloudflare docs pages, IETF draft names and revisions, SDK/tool
  versions) with its URL and retrieval date.
- WHEN the report records a claim THE SYSTEM SHALL tag it as `[CODE]`,
  `[CONFIG]`, `[LIVE]`, `[DOC]` or `[TEST]`, and SHALL write
  `unknown (not observed)` where no evidence exists, never `absent` or `PASS`.
- WHEN the current-state map is built THE SYSTEM SHALL inventory existing
  outbound HTTP, MCP and browser egress paths, their owners, tenant/principal
  propagation, secret custody, audit correlation, the Cloudflare IaC in
  mctl-gitops `infrastructure/cloudflare/` (including the
  `modules/spoofed-crawlers` verified-bot rule) and existing approval gates, and
  SHALL record any prior request-signing PoC or egress gateway, or that none was
  found in the repositories searched.
- WHEN egress surfaces are assessed THE SYSTEM SHALL assess at least three:
  (a) server-side HTTP/MCP fetch from an MCTL-owned process, (b) Claude/Codex
  tool-driven HTTP requests, (c) browser-use navigation; and SHALL mark each as
  `controlled`, `partially controlled` or `uninstrumentable`, with the exact
  point where signing could occur.
- IF a surface's HTTP client is not under MCTL control THEN THE SYSTEM SHALL
  classify it as unsupported, not as covered.
- WHEN the reference harness runs THE SYSTEM SHALL generate or load a
  fixture-only Ed25519 key, serve a JWKS key directory with its own signature,
  and produce one signed synthetic request carrying `Signature-Agent`,
  `Signature-Input` and `Signature` headers, using only the Go standard
  library, offline.
- WHEN the harness runs negative controls THE SYSTEM SHALL verify locally that
  unsigned, tampered-component, expired, wrong-key, rotated-key and replayed
  requests are rejected or flagged, each with expected vs observed result.
- IF the optional external probe against Cloudflare's documented test endpoint
  (`https://crawltest.com/cdn-cgi/web-bot-auth`) is run THEN THE SYSTEM SHALL
  record exact status codes and the request trace, SHALL send only synthetic
  requests signed with a non-production key, and SHALL NOT report a 401 or any
  unregistered-key response as Verified.
- IF the external probe is not permitted or not reachable THEN THE SYSTEM SHALL
  record the precise blocker and rely on the reproducible local validation.
- WHEN replay is analysed THE SYSTEM SHALL record Cloudflare's documented nonce
  and expiry behaviour, and SHALL state that short expiries are not an
  idempotency or anti-replay guarantee, so MCTL exact-action authorization,
  idempotency and audit apply independently of any web signature.
- WHILE any signing design is proposed THE SYSTEM SHALL keep the signing private
  key out of every client, tenant workload and agent runtime, and SHALL put no
  tenant, principal or user identifier in the key directory, `User-Agent`,
  `Signature-Agent` or any unsigned header.
- WHEN the threat matrix is written THE SYSTEM SHALL cover forged operator
  identity, cross-tenant bleed, leaked signing key, replay, expired or revoked
  authorization, bypass of site policy, redirect/cross-host signing, SSRF and
  allowlist, and PII in logs.
- WHEN options are compared THE SYSTEM SHALL compare sign-at-client, a central
  MCTL egress adapter, and not supporting browser-use initially, including
  failure modes, operational and financial cost, robots.txt and target-site
  policy compliance, and Cloudflare lock-in and fallback.
- WHEN the report discusses Cloudflare's transitive-trust / `Forwarded`
  direction THE SYSTEM SHALL label it experimental and separate from supported
  Web Bot Auth, and SHALL NOT use it to carry personal identifiers or claim
  user-authorization proof.
- WHEN the report concludes THE SYSTEM SHALL propose exactly one verdict from
  `ADOPT`, `LIMITED`, `DEFER`, `REJECT`, an explicit GO surface (possibly
  empty), a revisit trigger when the verdict is DEFER, and any follow-up issues
  only as proposals attached to existing owners (mctl-api, mctl-agents,
  mctl-gitops) subject to normal gates.
- WHILE the spike is in progress THE SYSTEM SHALL NOT perform a BotBase
  submission, publish a persistent production key, deploy a Worker, change WAF or
  bot settings, buy a plan, or make provider-facing requests beyond the single
  permitted synthetic probe.
- WHEN the manifest is added THE SYSTEM SHALL validate with
  `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes` and SHALL
  stay `lifecycle: proposed` with no `decision` block.

## Out of scope

- Production rollout, BotBase registration or submission, production key
  publication, new Workers, WAF or bot-management changes, or new spend.
- Federated user identity, a competing agent identity standard, or replacing
  OAuth / MCP auth.
- A universal browser proxy or browser traffic interception.
- Promising Cloudflare bypass, guaranteed allowlisting, or bypassing logins,
  paywalls or target-site restrictions.
- Cloudflare Private Origins (.github#292) and Commerce payment interoperability
  (.github#173), beyond citing their boundary.
- Changing Claude or Codex runtimes.

## Open questions

- Is the single synthetic probe to `crawltest.com/cdn-cgi/web-bot-auth`
  permitted from the investigation environment? The issue says "if permitted".
  Proceed: run it only if an operator has allowed outbound access, otherwise
  record the blocker and rely on local validation.
- Which existing controlled HTTPS test endpoint may host a temporary,
  non-production key directory? None was identified in this investigation, and
  serving one on a `*.mctl.ai` host would be a deployment. Proceed: serve the
  directory from the local harness (loopback, self-signed or plain HTTP) and
  record "no controlled public HTTPS test endpoint used" as a blocker for
  Verified-level evidence.
- The current Cloudflare docs, the IETF draft revisions
  (`draft-meunier-web-bot-auth-architecture`,
  `draft-meunier-http-message-signatures-directory`) and Intermediary
  eligibility were not fetched during this investigation. The implementer must
  pin them at execution time and must not rely on the issue text.
- Which surface (if any) makes MCTL-originated outbound HTTP to third-party
  sites today? The deployed config shows admins pods with open internet egress,
  but no dedicated egress gateway or browser-use service was found. This is the
  main input to the verdict. Recording "no current product need" is a valid
  outcome that points toward DEFER or REJECT.
