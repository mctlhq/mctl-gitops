# Design: issue-308-spike-agent-identity-cloudflare-web-bot

## Current state

`mctlhq/.github` (read at `5097e14d360b29322e9732b071268d7aa80b3cb4`) holds the
spike reports and roadmap manifests. No product code lives here.

- Spike reports live in `docs/spikes/<name>.md` and are indexed under
  `# Spikes` in `AGENTS.md`. The two most recent are
  `docs/spikes/journey-intent-correlation.md` (#306) and
  `docs/spikes/edge-config-kv-instant.md` (#272). Both use the same structure:
  a non-claims section, evidence tags (`[CODE]`, `[CONFIG]`/`[DEPLOYED]`,
  `[LIVE]`, `[DOC]`), an evidence-pin table with 40-hex commits, and
  `unknown (not observed)` instead of guesses. Both report a *proposed* verdict
  and leave the manifest without a decision.
- Spike manifests live in `roadmap/spikes/*.yaml` as `kind: SpikeDefinition`
  (`roadmap/schemas/spike-definition.schema.json`). Required fields are
  `spec.{title,question,lifecycle,github.issue,outcomes}`. Outcomes must match
  `^[A-Z][A-Z0-9_]*$` (`ADOPT`, `LIMITED`, `DEFER`, `REJECT` all match). A
  `decision` block is allowed only when `lifecycle: decided`. Validation:
  `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes`, with tests
  in `roadmap/tests/test_validate_spike.py`. The comment header in
  `roadmap/spikes/journey-intent-correlation.yaml` records the convention: "an
  agent does not record its own approval".
- Reference harness precedent: `docs/spikes/mcp-gateway-g0/` is a Go 1.22
  module (`module mctl.ai/spikes/mcpgatewayg0`) with `model/`,
  `harness_test.go`, `bench_test.go` and `fixtures/keys.json` holding
  fixture-only Ed25519 seeds that are documented as public test material. It
  runs with `go vet ./... && go test ./...`, offline.
- Related boundaries already documented: `docs/spikes/agent-governance-decision-assurance.md`
  (#181/#182 decision chain), `docs/plans/agent-commerce.md` (#173, payment
  never authorizes), `docs/spikes/journey-intent-correlation.md` (proposes
  reusing `work_item_id` as the journey key), `docs/plans/mcp-gateway.md`
  (inbound MCP policy). No document in this repository mentions Web Bot Auth,
  `Signature-Agent`, HTTP Message Signatures or an outbound egress gateway
  (`grep -rli "web-bot-auth|Signature-Agent|http-message-signatures"` found
  nothing). The only Cloudflare hits are inbound or edge config concerns.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/../infrastructure/cloudflare/` (mctl-gitops
  `3bc9c27a2109afe8f5d1f5dd684a871be30d3fcf`): `account/`, `portal/`, `tokens/`,
  `zones/`, `modules/{zone-baseline,spoofed-crawlers}`. Nothing related to Web
  Bot Auth, a key directory or outbound signing. `[CONFIG]`
- `infrastructure/cloudflare/modules/spoofed-crawlers/main.tf`: an *inbound*
  WAF expression `(not cf.client.bot and (<UA fragments>))` blocks crawler
  User-Agents that are not verified bots. It records that user-initiated agents
  (`Claude-User`, `ChatGPT-User`, `Perplexity-User`) are deliberately excluded
  because they are not in Cloudflare's verified-bot list, and that including them
  returned 403 `mcp_request_blocked` to claude.ai connectors on 2026-10-29. This
  is direct evidence that MCTL already *consumes* verified-bot status on
  inbound traffic and has been hurt by unverified agent traffic. The spike must
  keep inbound and outbound concerns separate. `[CONFIG]`
- `tenants/admins/values.yaml`: `networking.allowInternetEgress: true`,
  `allowClusterEgress: true`. Outbound egress from admins workloads is not
  network-constrained. `[CONFIG]`
- `services/admins/mctl-support/values.yaml`: comment states that egress is not
  limited by NetworkPolicy and that containment comes from a scoped run token and
  "no shell, fs, web or kubectl tools". So the support agent has no web-fetch
  surface. `[CONFIG]`
- `services/admins/` lists `mctl-agents-worker`, `mctl-agents-worker-exec`,
  `mctl-agents-worker-implement`, `mctl-design`, `mctl-docs`, `mctl-support`,
  `mctl-web`, `umami`. No dedicated egress proxy, browser-use or Playwright
  service was found. A grep for `browser|playwright|puppeteer` across
  `services/` matched only comments about in-browser login flows
  (mctl-telegram, claude-remote) and unrelated tenant apps. `[CONFIG]`
- mctl MCP tools: not called for this proposal. The question concerns egress
  code paths and external Cloudflare state, not a service's runtime config. The
  implementer should call `mctl_list_services` to confirm the egress-surface
  inventory. This is recorded under Open questions in requirements.md.
- Cloudflare primary docs and IETF drafts: **not fetched** in this
  investigation; unknown (not observed). They must be pinned in task 2.

## Proposed solution

Add one spike report, one manifest, one offline harness and one index line. No
service, IaC or runtime changes.

1. `docs/spikes/cloudflare-agent-identity-web-bot-auth.md` contains these
   sections:
   - Non-claims and evidence tags, using the same vocabulary as #306 and #272,
     plus `[TEST]` for harness output.
   - Evidence pins for repos (`.github`, mctl-gitops, mctl-api, mctl-agents,
     plus mctl-telegram / claude-remote where they make outbound calls) and
     external docs (URL, retrieval date, draft revision). Each pin separates
     *technical signature validity*, *BotBase Verified acceptance* and
     *per-site allow policy*.
   - Current-state and duplicate map: egress surfaces, owner, HTTP client,
     tenant/principal propagation, secret custody, audit correlation key
     (`work_item_id` / `we_` per #306), and existing gates (#181 decision chain,
     #173 commerce). Includes the inbound `spoofed-crawlers` rule as a related
     but separate consumer of verified-bot status. Also records #292 Private
     Origins as out of scope.
   - Surface matrix, one row per path, with columns: client under MCTL control?,
     signing point, signing viable?, verified result or syntax-only result,
     blockers, operator effort, cost, added latency. Rows: (a) server-side
     HTTP/MCP fetch from an MCTL-owned Go/Python process (controlled;
     `http.RoundTripper` or equivalent); (b) Claude/Codex built-in web-fetch
     tools (uninstrumentable, because the vendor runtime owns the client and
     egress may originate from vendor infrastructure), versus an MCTL-provided
     MCP fetch tool (controlled, reduces to (a)); (c) browser-use navigation
     (uninstrumentable for subresources and redirects without browser
     interception, which is a non-goal).
   - Identity separation. **Operator** = MCTL, public in the key directory and
     `Signature-Agent`. **Owner/tenant/principal/action/approval** stay internal,
     and are joined in MCTL audit by `work_item_id` and a request digest, never
     emitted in headers. Architecture sketch: principal/tenant -> policy and
     approval (mctl-api, #181) -> execution (`wi_`/`we_`) -> egress adapter (an
     allowlist check, then a re-check of exact-action authorization for
     mutations, then signing) -> Cloudflare -> site.
   - Harness evidence: positive and negative transcripts, plus key-directory
     validation.
   - Replay and idempotency, as Cloudflare documents them: `nonce` is
     recommended but not tracked, and `expires` is short-lived. The conclusion
     is that MCTL idempotency keys and exact-action binding remain mandatory for
     governed mutations.
   - Signing boundary and key lifecycle (proposal only). A single central
     signer holds the key in Vault or KMS. No client or tenant sees the private
     key. Rotation happens through overlapping `kid`s in the directory.
     Revocation removes the `kid`, and the report records how long a cached
     directory stays valid. Compromise response: remove the key, rotate,
     notify Cloudflare. Also covers redirects (re-sign per hop only on an
     allowlisted same-policy host, otherwise stop), cross-host requests,
     proxies/CDNs and header mutation (sign only components that survive
     intermediaries: `@authority`, `signature-agent`), retries (new
     `created`/`nonce`, same MCTL idempotency key), caching, and SSRF (a
     deny-private-range resolver plus a per-action destination allowlist).
   - Threat matrix with the rows required in requirements.md.
   - Options comparison (see Alternatives) and a BotBase path: what a
     submission requires, and how to validate `Agent`/`Transact` and
     `Intermediary` classification and site-side allow/block. This is gated on
     separate owner approval.
   - Experimental transitive-trust / `Forwarded` direction, explicitly
     separated.
   - Proposed verdict and GO surface. On current evidence the expected verdict
     is `DEFER`: no MCTL-controlled product surface makes governed third-party
     web requests today, and Intermediary eligibility is a Cloudflare decision.
     If the surface inventory finds a real controlled path, `LIMITED`
     (server-side controlled clients only, browser-use and vendor tools
     unsupported) becomes the candidate. The implementer must choose from the
     evidence, not from this expectation.
2. `docs/spikes/cloudflare-agent-identity-web-bot-auth/`: a Go 1.22 module
   (`module mctl.ai/spikes/webbotauth`), standard library only (`crypto/ed25519`,
   `net/http/httptest`, `encoding/json`). It contains:
   - `model/sign.go`: RFC 9421 signature-base construction for a fixed component
     set (`@authority`, `signature-agent`), with `created`, `expires`,
     `keyid` (JWK thumbprint, RFC 7638), `nonce` and `tag="web-bot-auth"`.
   - `model/directory.go`: JWKS directory served as
     `application/http-message-signatures-directory+json`, with the response
     itself signed.
   - `model/verify.go`: a local verifier.
   - `fixtures/keys.json`: fixture-only seeds, documented as public test
     material the same way as in mcp-gateway-g0.
   - `harness_test.go`: the positive case plus negative controls: unsigned,
     tampered `@authority`, expired, wrong key, rotated key (old `kid` removed),
     and replay. Replay is "accepted by signature alone" and is listed as an
     observed property, not a pass.
   - `probe/`: an opt-in program (build tag `probe`, not run by `go test`) that
     sends one synthetic signed request to the Cloudflare test endpoint and
     prints status and headers. Its output is pasted into the report only if
     it was run.
   - `README.md`.
3. `roadmap/spikes/cloudflare-agent-identity-web-bot-auth.yaml`: a
   `SpikeDefinition` with `owner: mctlhq/.github`, issue `mctlhq/.github#308`,
   `lifecycle: proposed`, outcomes `ADOPT, LIMITED, DEFER, REJECT`,
   `execution.devloop: true`, `evidence.report`, no `decision`, and the same
   header comment as the #306 manifest.
4. `AGENTS.md`: one entry under `# Spikes`.

Why this shape: it matches the existing spike convention exactly. That keeps
roadmap validation and review mechanics unchanged. An offline harness gives
reproducible red/green evidence without any provider-facing dependency, which
satisfies the "or precise external blocker and reproducible local validation"
acceptance path.

## Alternatives

- **Report only, no harness.** Dropped. The issue requires an isolated valid
  request plus negative controls. Prose about signature validity is not
  evidence.
- **Deploy a temporary key directory on a `*.mctl.ai` host (Worker or
  service) and register a test bot.** Dropped. It violates "no new worker, no
  production key publication, no registration" and needs owner approval. It is
  documented instead as the gated next step of a possible ADOPT follow-up.
- **Use a third-party Web Bot Auth library (for example Cloudflare's
  reference implementations) inside the harness.** Dropped for the harness
  because it adds dependencies and supply-chain surface to a docs repo. Instead,
  a standard-library implementation is cross-checked against the published
  test vectors in the draft or Cloudflare docs, if they are available. The
  report records the reference library versions in the pins for a later
  implementation.

## Platform impact

- Migrations: none. Backward compatibility: no runtime or API changes. The
  manifest adds one entry to roadmap validation and leaves epics unaffected.
  Spikes are not yet part of RoadmapPublication (`roadmap/README.md`).
- Resources and spend: none. The optional probe is one synthetic HTTPS request.
- Risks and mitigations:
  - A fixture key is mistaken for an operator key. Mitigation: keys are marked
    fixture-only, never served from a public host, and the README says so.
  - The report over-claims "Verified". Mitigation: a mandatory three-level
    distinction (syntax / BotBase Verified / site allow), and 401 is never
    success.
  - Stale external facts. Mitigation: URL and retrieval-date pins, and
    `unknown (not observed)` where unfetched.
  - Inbound and outbound conflation with the `spoofed-crawlers` WAF rule.
    Mitigation: a separate section, and no IaC edits.
  - CI: the Go module is not wired into any workflow, matching mcp-gateway-g0.
    The roadmap validation test suite must stay green.
