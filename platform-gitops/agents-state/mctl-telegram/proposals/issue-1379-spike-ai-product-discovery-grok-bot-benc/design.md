# Design: issue-1379-spike-ai-product-discovery-grok-bot-benc

Revision 3 (2026-11-23), including revision 2 and its finding-to-change matrix. Status remains `proposed`; dated historic baselines below are superseded only where explicitly corrected in the new evidence section.

## Current state

Pinned baseline:

- mctl-telegram `b318e97a027bdae661344d4a324ddf47dc1426c6` (2026-11-21 23:15 +0100), a shallow clone;
- mctl-gitops `a967430042424562a696cac216e428e00631c252` (2026-11-21 22:48 UTC).

Revision 1 cited mctl-telegram `568da01`. Every statement below was re-read at `b318e97`.

### Personal Assistant (ADR 0011, epic #1312)

- `docs/adr/0011-personal-assistant.md`, `Status: Proposed`, says:
  - Phase 1 is read-only on `tg` and `alice`;
  - Phase 1 is gated on S1 green, then the preview deployment (owner GO), then evals, then owner GO;
  - for Alice, "If `alice` cannot narrow its scopes, Alice linking needs an owner decision."
- `docs/agent-runtime/personal-assistant-threat-model.md`:
  - invariant I6 (external content never removes a gate);
  - T5 taint;
  - T6 Alice disclosure classes;
  - the Phase 1 pinned tools: `tg` gets `list_dialogs`, `get_messages`, `search_messages`, `list_folders`, `list_topics` and `get_my_identity`, and `alice` gets four read tools;
  - line 680 records: mctl-alice has `iot:view`, `iot:control` and `quasar`, and its `TOOL_SCOPES` per-tool check lets only the read tools accept `iot:view`. The PA requests exactly `iot:view` (`internal/pa/connection/scope.go`, `ErrScopeMismatch`, tested in `internal/pa/connection/acceptance_test.go`).
  - In Phase 1 every dispatched call is recorded with `taint=external`.
- Code under `internal/pa/`:
  - `ingress.go`, `webhook.go`, `runloop.go`, `conversation.go` (`DefaultConversationTTL` and `MaxConversationTTL` are both `24 * time.Hour`), `memory.go`, `outbox.go`;
  - `connection/`, `connector/`, `linking/`, `egress/`, `output/`, `gate/`, `jobs/`, `catalog/`;
  - `phase2_inert_test.go`.
- Gates:
  - In the current manifest body, no gap entries were found; #1317 is OPEN and the actual S1 gate-closing run and R1-R6 exit evals are not attested. Do not infer gate closure from grep alone.
  - `pa-s2-manifest.yaml` has 27 `status: pending` and 5 `status: green` entries.
- Flags: `PA_ENABLED` defaults to false. Production has no PA variables. Preview config explicitly includes PA variables but PA_ENABLED=false, PA_EXTERNAL_TOOLS_ENABLED=false, PA_SERVER_TG_ENABLED=false and PA_WRITES_ENABLED=false. Dedicated PA preview worker has replicaCount 0. GitOps desired state != real runtime evidence.

### MCP provider surface used by external clients

- Discovery and endpoints:
  - `cmd/server/main.go` serves `/.well-known/oauth-protected-resource`;
  - `internal/oauth/server.go` serves `/.well-known/oauth-authorization-server`, `/oauth/register`, `/oauth/token` and `/oauth/revoke`;
  - `internal/oauth/cimd_client.go` handles CIMD;
  - Streamable HTTP is served at `/mcp`.
- Scopes, from `internal/oauth/scopes.go`:
  - `DCRNegotiableScopes` contains `telegram:dialogs:read`, `telegram:messages:read`, `telegram:messages:send`, `telegram:messages:pin` and `account:manage`;
  - `membershipScopes` contains `admin:users`, `admin:users:read` and `admin:broadcast`, granted by membership whatever the client asked for;
  - `applyScopeCeiling` strips everything outside the ceiling, membership scopes and groups included;
  - `withinScopeCeiling` is the mint-time backstop.
- Profile vs ceiling (`internal/toolprofile/toolprofile.go`):
  - `Binding` has `client_id`, `redirect_uri`, `profile` and `scope_ceiling`;
  - `Bindings.ScopeCeiling` "deliberately has no redirect_uri fallback: the ceiling is keyed by client_id alone";
  - `Bindings.Resolve` lets a `client_id` win over a `redirect_uri`;
  - a profile narrows tools only, and the ceiling narrows the token's scopes.
- Dynamic client identity: an implicit-host DCR registration receives a random `tgmcp_` `client_id` (`internal/oauth/dcr_allowlist_test.go`, "want a random tgmcp_ id"). Only a CIMD URL, a preregistered client or the `OAUTH_DCR_REDIRECT_URIS` pinned prefix gives a stable id. Consequence: a `grok.com` or `cursor.com` DCR client can be bound to a profile by exact `redirect_uri`, but cannot get a scope ceiling.
- `get_my_identity` is `scopeExempt` (`internal/mcp/hidden.go`). The minimum read scopes for `core-readonly` are expected to be `telegram:dialogs:read` and `telegram:messages:read`. Task 3 confirms this against `internal/mcp/hidden.go`.
- Revocation (`internal/oauth/server.go` `handleRevoke`, `SECURITY.md` "Refresh tokens"):
  - `/oauth/revoke` requires `token` and `client_id`;
  - it revokes the whole refresh family (`explicit_revoke`);
  - an unknown or foreign token gets 200 with an empty body;
  - access tokens "are not revocable by this endpoint or by any other means short of rotating OAUTH_JWT_SIGNING_KEY";
  - refresh tokens rotate on use, and replay revokes the family;
  - the absolute refresh lifetime is `OAUTH_REFRESH_TOKEN_TTL` (default 720h, `internal/config/config.go`);
  - account deletion revokes the families;
  - "Disconnect does not revoke ... it ends the Telegram session but keeps the client's OAuth grant."
- `docs/platforms/compatibility.md` (#784 D1, rows dated 2026-11-21 against gitops `8d082583b`):
  - Grok (grok.com): host admitted in #2870; now OWNER_OBSERVED_WORKS against tg.mctl.ai on 2026-11-22 (sign-in, token grant and tool calls, mctl-telegram PR #1393; issue #1381 closed). Grok Bot-specific client attribution remains UNKNOWN.
  - Cursor: allowlisted, not tested, #1385;
  - Town: OWNER_OBSERVED_WORKS on 2026-11-22 via #1393; CIMD-versus-DCR remains unknown.
  - The matrix legend says "An allowlist entry alone means `not tested`."
- `docs/runbooks/admitting-an-agent-platform.md` defines the intake, settings, verification and rollback order for admission. This spike reuses it and does not duplicate it.
- `docs/design/core-profiles.md`, section "Telegram terms: what a profile does and does not solve", quotes Telegram Content Licensing (read 2026-10-21): an exception requires that "all relevant users individually provide explicit, informed, affirmative and continued consent". It also cites API Terms §1.4 and §1.5. It states that profiles do not "obtain consent from the *other* people in a chat", and that this needs a legal opinion and a product decision.
- `docs/spikes/assistant-builder-ui-reference.md` sets the house spike style: pinned SHA, evidence limitations, labels.
- Docs CI: `docs/doc.go` declares `package docs`, consistency tests for documentation. CI runs `go test -race ./...` (`.github/workflows/build.yml`), which covers `./docs`. There is no markdown linter. The `product-updates` gate applies only to tool-surface changes, so a docs-only report does not trigger it. No docs test reads `docs/spikes/`.

### Vendor sources fetched (2026-11-21, read-only, no login)

These are summaries from one fetch each. Task 2 re-reads every page and records minimal verbatim quotes.

- `https://docs.x.ai/grok-bot/overview`:
  - "Grok Bot supports custom tooling, so it can interact with any MCP or API.";
  - "Bots remember you.";
  - routines are scheduled repeats;
  - "access to a real computer in the cloud";
  - OAuth, Telegram and pricing are not mentioned.
- `https://docs.x.ai/grok-bot/computer-and-apps`:
  - a Remote HTTPS connector takes a "Server URL", optional "HTTP headers" and an OAuth "Client ID", with a "Client Secret" field;
  - no callback URL is documented for custom MCP;
  - connected apps are "available to every Bot you run";
  - per-account screens "are separate work surfaces, not separate security boundaries";
  - between users, the computer is "dedicated and hardware-isolated";
  - Telegram is not mentioned.
- `https://docs.x.ai/grok-bot/how-grok-bot-works`:
  - "Auto Review is on by default, and most actions go ahead on their own";
  - "Ask first" rules exist;
  - per-Bot memory with remember, fix and forget;
  - "App sign-ins stay on Cursor's servers";
  - "Your Bots aren't separated from each other";
  - Telegram, WhatsApp and SMS are not mentioned.
- `https://www.town.com/docs/integrations/mcp-servers`:
  - "Town talks to MCP servers over Streamable HTTP only";
  - "Town runs the OAuth flow for you";
  - the callback is `https://www.town.com/api/mcp/oauth/callback`;
  - the CIMD client id is `https://www.town.com/.well-known/oauth-client-id`;
  - DCR is supported.
- `https://www.town.com/features/telegram`:
  - Telegram is a bot DM (@TownAIBot) linked with a 6-digit code;
  - voice notes are transcribed, and photos are processed;
  - access to the user's personal Telegram chats is not mentioned.
- Not fetched yet: `town.com/docs`, `town.com/product`, `docs.x.ai/grok-bot/skills-routines-and-automations`, and the Grok Bot security, pricing and FAQ pages. Task 2 fetches them, or records them as `UNKNOWN`.

### Deployed state checked (HISTORICAL 2026-11-21 baseline; superseded by Revision 3 for PA flags and current image tags)

- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml` (production `tg`, gitops `a967430`):
  - image `0.141.0`;
  - `OAUTH_ISSUER_URL: https://tg.mctl.ai`;
  - `OAUTH_ALLOWED_IMPLICIT_HOSTS` (line 130) includes `grok.com`, `www.cursor.com`, `cursor.com`, `www.town.com` and `town.com`, with the Google `user_bound_custom-mcp-` path-prefix entries;
  - `ALLOWED_ORIGINS` includes `https://grok.com`;
  - `OAUTH_CIMD_ACCEPT` and `OAUTH_CIMD_ADVERTISE` are `"true"`;
  - `OAUTH_CIMD_ALLOWED_HOSTS: chatgpt.com,claude.ai,vscode.dev,www.town.com`, which has no Grok or Cursor host;
  - `MCP_CLIENT_PROFILES` (line 160) has one record: the Town CIMD `client_id` bound to `core-reply`, with no `scope_ceiling` and no `redirect_uri` record;
  - `OAUTH_DCR_REDIRECT_URIS` holds two exact Cloudflare portal URIs, which are not reproduced;
  - `OAUTH_ACCESS_TOKEN_TTL: "1h"` and `OAUTH_CODE_TTL: "30m"`;
  - `OAUTH_REFRESH_TOKEN_TTL` is not set, so the default is 720h;
  - no `OAUTH_PREREGISTERED_CLIENTS` and no `PA_*` key.

  This corrects revision 1, which said production had no Grok host.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/values.yaml`:
  - image `main-b318e97`, the same commit as the clone;
  - issuer `https://tg-preview.mctl.ai`;
  - `OAUTH_ALLOWED_IMPLICIT_HOSTS` has no Grok, Cursor or Town host;
  - no `OAUTH_CIMD_*` key, so CIMD is off by default (`internal/config/config.go`, `OAUTH_CIMD_ACCEPT` default false);
  - no `MCP_CLIENT_PROFILES` key;
  - `OAUTH_ACCESS_TOKEN_TTL: "1h"`;
  - no `PA_*` key.

  Consequence: no vendor client can complete registration on preview without an owner decision.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-alice/values.yaml`: image `2.16.0`, ingress `alice.mctl.ai`. The OAuth configuration is not visible here.
- The gitops values hold internal identifiers: session-TTL exemption ids and a Cloudflare account path. They were read but are never copied into the report.
- mctl MCP tools: not called. The gitops checkout answered the configuration questions. Live discovery documents and service status were not fetched, so every "deployed" cell means desired configuration in gitops, not a live observation.
- The mctl-alice repo was not available. Gap recorded under Open questions in requirements.md.

## Proposed solution

Write one docs-only report, `docs/spikes/pa-grok-town-benchmark.md` (status PROPOSED, `Refs #1379`), in the house style of `docs/spikes/assistant-builder-ui-reference.md`. Its sections:

0. **Header and evidence limitations.**
   - The two pinned SHAs and both image tags.
   - Vendor access dates.
   - The label legend: `VERIFIED`, `VENDOR-DOCUMENTED`, `UNTESTED`, `NOT-IMPLEMENTED`, `UNKNOWN`, plus `NOT-EXECUTED` and `BLOCKED` for tests.
   - A statement that "deployed" means gitops desired state unless a dated live observation is cited.
1. **MCTL baseline.**
   - 1a: PA items (consent, private-chat ingress, 24h TTL, `/new`, `/forget`, `/consent`, linking, connector executor, audit, egress, taint, budgets, pin and allowlist, switches). Each is classified merged, deployed, flagged, tested or planned, with a path.
   - 1b: `tg` admission table, with production and preview columns. Rows are the client categories: Grok Bot, Grok Chat, Cursor IDE, Town, plus the other CIMD clients for contrast. The separate columns are implicit host, exact DCR URIs (count only), CIMD host, profile, ceiling, stable `client_id`?, and live observation (from `compatibility.md`).
   - 1c: profile vs ceiling, with exact code citations. This is the precondition matrix for any later live test.
   - 1d: revocation semantics table. The events are refresh-family revoke, replay, access-token TTL, refresh absolute expiry, account deletion, disconnect, `MCP_CLIENT_PROFILES` removal (next refresh) and CIMD host removal (refreshes stop). For each event, the table gives the expected outcome and its timing.
2. **Vendor benchmark.**
   - Townie and Grok Bot across the work package 2 dimensions, each cell labelled, with a minimal verbatim quote and the date.
   - Custom MCP authentication is quoted, or marked `UNKNOWN`.
   - Town appears in two roles: Telegram UX reference (bot DM, 6-digit linking, voice and photo) and MCP distribution channel (the custom MCP client of `tg`).
   - The comparison is framed as jobs, differentiation and measurable outcomes, not parity.
3. **Interop compatibility matrix.**
   - Rows: Grok Bot x `tg`, Townie x `tg`, Grok Bot x `alice`, Townie x `alice`, plus optional Grok Chat x `tg` and Cursor IDE x `tg` as distinct categories.
   - Columns: the work package 3 columns.
   - Grok (grok.com) x tg: OWNER_OBSERVED_WORKS (2026-11-22, #1393/#1381), with untested negative paths. Grok Bot specifically x tg: client/build ATTRIBUTION_UNKNOWN; do not downgrade the existing Grok observation or upgrade the Bot without new proof.
   - Alice rows: secondary evidence only.
4. **Conformance test plan** (scripted client, preview, synthetic or isolated approved account, all `NOT-EXECUTED`).
   - Positive steps:
     - RFC 9728 and RFC 8414 discovery;
     - DCR with a loopback redirect (accepted regardless of the list);
     - PKCE S256 with `resource`;
     - a token requesting only `telegram:dialogs:read telegram:messages:read`, with the granted `scope` read from the token response (never the token value);
     - `initialize`;
     - `tools/list`;
     - `get_my_identity`;
     - one `get_messages` on a synthetic chat.
   - Negative steps, with exact expected outcomes:
     - a redirect host off the list: 400 `invalid_redirect_uri`;
     - a wrong `resource`;
     - a scope outside the entitlement;
     - a tool absent from the scope or profile;
     - a revoked refresh token on `/oauth/token`: `invalid_grant`;
     - the access token after a revoke: it is still accepted until it expires (<=1h), and that is the expected result, not a failure;
     - replay of a rotated refresh token, which revokes the family;
     - code reuse;
     - disconnect, after which tools fail at the Telegram layer while OAuth persists.
   - Each step names its expected audit or metric entry. The plan states that it proves server behaviour only, never vendor E2E.
5. **Vendor interoperability test plan** (all `NOT-EXECUTED`, BLOCKED until a separate owner GO).
   - One row per category. Each row records the registration strategy, the exact callback host and URI (vendor-documented or `UNKNOWN`), `resource`, PKCE, the requested and granted scopes, `initialize`, `tools/list`, the identity read, one synthetic read, negative cases and audit.
   - Preconditions:
     - a stable `client_id`;
     - `core-readonly` AND a ceiling of exactly the minimum read scopes;
     - no admin, groups, write or account scopes;
     - minted and refreshed scopes verified without logging token values;
     - an isolated account with no real chats and no other credentials.
   - A dynamic-id client is BLOCKED and becomes a separate owner decision. The plan never proposes widening policy or relying on prompt instructions. No outbound vendor action is taken.
6. **External-client threat model.**
   - Controls that do not carry over to a direct MCP client: the PA consent `pa-data-flow/v1`, taint, kill switches `PA_*`, PA budgets, PA pin and audit-before-dispatch.
   - Controls that do: server-side scopes and ceiling, profiles, PKCE and `resource`, redirect allowlists, the `send_reply` confirmation binding, the `tg` audit chain, and token TTL.
   - Grok Bot boundaries as quoted: connections shared across all Bots, the shared computer, "Auto Review is on by default". Everything else is `UNKNOWN`.
   - Alice: `iot:view` only, no real devices, no control.
7. **Telegram consent and licensing gate.** It cites core-profiles and the official terms, re-read with a date. It separates policy and legal questions (other participants' consent, own-messages-only mode) from engineering questions. It applies the gate to the digest, memory and external-distribution hypotheses. The demo uses synthetic data only.
8. **Meetup pack.**
   - Timeline: Nov 26 pack, Nov 27 rehearsal, Nov 28 event. Date confirmation and registration are owner actions.
   - Track A (mandatory, offline): pitch, architecture diagram, public discovery JSON, synthetic storyboard.
   - Track B (optional): PA read-only preview, gated on #1318, #1319 and owner GO.
   - Track C (optional): Grok Bot OAuth and a synthetic read, gated on a separate GO and the section 5 preconditions.
   - Fallback: track A only.
   - Also: an interview script (5-10 voluntary interviews) and an anonymized findings template, left empty.
9. **Hypotheses (3-5), metrics, decision.**
   - Candidates:
     - daily digest of the user's own chats (#1325, consent gate);
     - voice input (a candidate, owner pending triage, no new epic);
     - reusable skills and routines (#1325);
     - contextual memory (#1325);
     - external-client distribution with a ceiling-bound read profile (#1048 and the existing `toolprofile`; admission verification stays in #1381, #1385 and #784).
   - Metric definitions: activation, D7, task success, cost per successful task, approval and denial rates, each with its retention and privacy limit.
   - One decision, with DUAL_TRACK_BOUNDED examined as a hypothesis and not assumed.
   - The next owner decision and the PDLC handoff.

### Finding-to-change matrix

| Finding | Change in revision 2 | Where |
|---|---|---|
| P2-01 SHAs, admission separation | Both SHAs re-pinned. `grok.com` and Cursor implicit hosts recorded, and production vs preview contrasted. Seven separate admission columns. No inference from Grok Chat or Cursor. | requirements "Provenance", "MCTL baseline"; design "Deployed state checked", report 1b, 3 |
| P2-02 profile vs ceiling | Ceiling is keyed by `client_id` only and a profile by `client_id` or `redirect_uri`. DCR gives a random `tgmcp_` id. Live-test preconditions set, and dynamic ids BLOCKED. | requirements "Test plans"; design "MCP provider surface", report 1c, 5 |
| P2-03 revocation | Semantics from `handleRevoke` and `SECURITY.md`: access token valid until TTL (1h), family revoke, replay, 720h absolute, deletion, disconnect. No immediate-401 expectation. | requirements "MCTL baseline"; report 1d, 4; T5 |
| P2-04 conformance vs vendor | Two plans. Vendor plan per client category, all `NOT-EXECUTED` or BLOCKED. | report 4, 5; tasks 4, 5 |
| P2-05 external threat model | Control-by-control carry-over table, Grok Bot quotes, Alice `iot:view`. | report 6; task 6 |
| P2-06 Telegram consent | core-profiles section and terms cited. Policy split from engineering. Gate applied to hypotheses. | report 7, 9; task 7 |
| P2-07 meetup | Nov 26, 27, 28 timeline. Tracks A, B and C with gates and a fallback. | report 8; task 8 |
| P3 sources | Additional primary sources allowed. Five fetched and dated, the rest are task 2 or `UNKNOWN`. | design "Vendor sources fetched"; task 2 |
| P3 jobs not parity | Framing changed. Town in two roles. DUAL_TRACK_BOUNDED is a hypothesis. | report 2, 9 |
| P3 voice owner | "Candidate, owner pending triage, no new epic". | report 9 |
| P3 docs CI | Verified: `package docs` exists, CI runs `go test -race ./...`, there is no markdown linter, and the product-updates gate does not apply. | design "Docs CI"; T2 |

## Alternatives

- **Run the vendor flow now against production `tg`.** Production already admits `grok.com`, so this would look possible. Rejected: the issue forbids it without a separate owner GO. A DCR client gets no scope ceiling, so a Grok-side sign-in could carry `telegram:messages:send` and `account:manage` unless the client restricts itself. And `grok.com` may not be Grok Bot at all.
- **Fold the work into `docs/platforms/compatibility.md` or #1381.** Rejected as the primary vehicle. That matrix records verified admission per host, while this spike is product discovery. The report links to it and routes admission verification to #1381, #1385 and #784, so nothing is duplicated.
- **Propose a Grok ceiling or preregistered client now.** Rejected: that is a policy change. It is recorded as an owner decision.

## Platform impact

- No migrations, code, image, flag or gitops change. Backward compatible. No resource impact.
- Risks and mitigations:
  - **Leaking internal ids or account paths.** Never copy gitops identifiers. Use the personas Alice, Bob, Carol and Dana only. T3 greps for leaks.
  - **Overstating vendor support.** Strict labels, quotes and `UNKNOWN`. Admission alone is reported as `not tested`.
  - **A misread revocation expectation.** The access-token TTL is stated explicitly.
  - **A stale baseline.** Both SHAs are pinned and everything is dated. The PR re-checks gitops.
  - **The report read as authorization.** It says so explicitly and uses `Refs`, not `Closes`. Independent review is required before approval.

## Revision 3 evidence reconciliation (2026-11-23)

| Question | Source | Classification | Limitation |
| --- | --- | --- | --- |
| Grok (grok.com) -> tg.mctl.ai/mcp | mctl-telegram#1381 and merged PR #1393 (2026-11-22) | OWNER_OBSERVED_WORKS | Sign-in, token issuance and tool calls recorded as owner's statement; no replayable run ID or transcript |
| Grok DCR before success | #1381 comment 7069894566, 2026-11-21 | OBSERVED_AUDIT | Redirect admitted and token issued, but admin principal inherited extra admin scopes; initial read-call/refresh/revoke rows were unfilled |
| Grok Bot distinct executable | No client name/build evidence in #1393 | ATTRIBUTION_UNKNOWN | Grok web success is not by itself Grok Bot's OAuth E2E |
| Grok Bot skill -> routine | docs.x.ai/grok-bot/skills-routines-and-automations | VENDOR_DOCUMENTED | Not implemented in MCTL PA |
| Grok Bot custom Remote HTTPS MCP | docs.x.ai/grok-bot/computer-and-apps | VENDOR_DOCUMENTED | UI supports Server URL and OAuth Client ID; exact MCTL callback identity not known |
| Hermes skill management | NousResearch/hermes-agent website/docs/user-guide/features/skills.md | PROJECT_DOCUMENTED | Different authority model; no MCTL parity inferred |

**Security finding:** #1381 shows implicit platform-admin scopes in the historical Grok OAuth grant. A profile is not a per-client scope ceiling; a random DCR client_id cannot be safely confined through a redirect-host-only ceiling. Future isolated read-only tests need fixed auditable client identity, minimum scopes, both AS and MCP enforcement and owner GO. PA's consent/taint/budget gates do not automatically apply to third-party clients.

**Updated deployment baseline:** current GitOps production tag 0.143.0; preview main-3aab3cb with explicit disabled PA flags; separate agent-worker-pa-preview has replicaCount 0. These are desired-state observations on 2026-11-23. The old 2026-11-21 no-PA-variables-in-preview text in the historic deployment section must not be used as current evidence.

**Research decision:** keep dual-track hypothesis: working Grok web MCP distribution is independently valuable; distinct Grok Bot identity and least-privilege guarantees need evidence. Run no new live test, change no OAuth settings, do not approve or implement Phase 2-4.
