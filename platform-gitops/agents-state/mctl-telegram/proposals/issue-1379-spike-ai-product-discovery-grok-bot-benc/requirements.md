# Spike (revision 3): AI product discovery, comparing Grok Bot and Townie, plus MCP conformance and vendor interoperability test plans

## Context

Issue #1379 (P2, parent #1312 Personal Assistant) asks for a research-only spike. It compares Townie (Town, the closest Telegram UX reference), Grok Bot (xAI's autonomous-agent benchmark) and the MCTL Personal Assistant (PA) as it really exists. It must answer four questions. Which daily jobs drive repeat use? Should MCTL be a PA, a trusted MCP provider for external agents, or both? Can Grok Bot and Townie use the existing MCTL MCP endpoints (`tg.mctl.ai`, `alice.mctl.ai`) through supported OAuth and transport, without any change to authority? Which gaps are evidence-backed product hypotheses? It also prepares a pack for the Grok Bot Meetup Belgrade, listed for 2026-11-28. That date is unconfirmed, because the banner and the date card differ.

This is revision 3 (2026-11-23), incorporating the owner-observed 2026-11-22 Grok connection. The independent review of revision 1 (gitops `bb69c72`) returned REQUEST_CHANGES with 0 P1, 7 P2 and 4 P3 findings, and its amendments supersede the original instructions where they conflict. design.md, section "Finding-to-change matrix", maps each finding to the sections that address it. The baseline is pinned again:

- mctl-telegram `b318e97a027bdae661344d4a324ddf47dc1426c6`;
- mctl-gitops `a967430042424562a696cac216e428e00631c252`.

Three corrections to revision 1 follow from the re-pin:

- Production `tg` now lists `grok.com`, `www.cursor.com` and `cursor.com` as implicit DCR hosts.
- Preview lists none of those hosts, and no Town host either.
- `docs/platforms/compatibility.md` now records Grok (grok.com) and Town as works, owner-observed on 2026-11-22 (PR #1393); #1381 was closed. Cursor (#1385) remains not tested.

The only output is a docs-only report, `docs/spikes/pa-grok-town-benchmark.md`, plus a decision recommendation. The report changes no code, configuration, OAuth policy or phase HOLD.

## User stories

- AS the product owner I WANT a dated, source-classified comparison of jobs, differentiation and measurable outcomes across Townie, Grok Bot and the MCTL PA, rather than a feature-parity list, SO THAT I can choose PA_FIRST, MCP_DISTRIBUTION_FIRST, DUAL_TRACK_BOUNDED or DEFER from evidence.
- AS the security owner I WANT these kept separate: implicit admission, exact DCR redirects, CIMD, tool profile, scope ceiling, desired configuration and live observation. I also WANT a conformance test plan and a vendor interoperability plan that stay separate, SO THAT nobody infers Grok Bot support from Grok Chat or Cursor admission, and no later live test widens authority.
- AS the security owner I WANT an external-client threat model SO THAT the PA's consent, taint, budget, audit and kill switches are not assumed to protect direct MCP clients.
- AS the policy owner I WANT the Telegram consent and licensing questions recorded as open policy and legal questions SO THAT digest, memory and external distribution hypotheses do not rest on the account owner's consent alone.
- AS the meetup presenter I WANT a mandatory offline synthetic pack (A) and optional live tracks (B, C), each with an explicit gate and fallback, SO THAT I never claim live readiness without evidence.
- AS a later DevLoop investigator I WANT 3-5 hypotheses routed to the issues that already own the scope (#1325, #1048, #1088, #1280, #1381) SO THAT no parallel infrastructure is proposed.

## Acceptance criteria (EARS)

### Provenance and labels
- WHEN the report is written THE SYSTEM SHALL record at its top:
  - the pinned mctl-telegram SHA and mctl-gitops SHA;
  - the production image tag and the preview image tag read at that gitops SHA;
  - the access date of every vendor or Telegram source.
- WHEN a claim is stated THE SYSTEM SHALL label it with exactly one class:
  - `VERIFIED`: read in code or gitops at the pinned SHAs;
  - `VENDOR-DOCUMENTED`: a minimal verbatim quote from a dated primary vendor page, with its URL;
  - `UNTESTED`;
  - `NOT-IMPLEMENTED`;
  - `UNKNOWN`: the source is unavailable or silent.

  Every test step carries `NOT-EXECUTED` until it has been run.
- IF a vendor page cannot be fetched or does not address a question THEN THE SYSTEM SHALL record `UNKNOWN` and never infer support. Leads from the prior review are leads to verify, not evidence.

### MCTL baseline (P2-01, P2-02, P2-03)
- WHEN `tg` admission is described THE SYSTEM SHALL keep these as separate columns, for production and preview alike:
  - implicit DCR host (`OAUTH_ALLOWED_IMPLICIT_HOSTS`);
  - exact DCR redirect URIs (`OAUTH_DCR_REDIRECT_URIS`, counted only, never reproduced);
  - CIMD host (`OAUTH_CIMD_ALLOWED_HOSTS`, plus `OAUTH_CIMD_ACCEPT` and `OAUTH_CIMD_ADVERTISE`);
  - tool profile (`MCP_CLIENT_PROFILES` profile);
  - scope ceiling (`MCP_CLIENT_PROFILES` `scope_ceiling`);
  - live observation (`docs/platforms/compatibility.md` status).
- WHEN classifying Grok clients THE SYSTEM SHALL preserve the owner-observed 2026-11-22 Grok (grok.com) sign-in, token and tool-call success, while separately marking the exact Grok Bot client/build attribution UNKNOWN. An implicit host alone is not proof, but PR #1393 records a later actual observation.
- WHEN the profile and the ceiling are described THE SYSTEM SHALL state the following, citing `internal/toolprofile/toolprofile.go` (`Bindings.ScopeCeiling`, `Bindings.Resolve`) and `internal/oauth/scopes.go` (`applyScopeCeiling`, `withinScopeCeiling`):
  - a scope ceiling is keyed by exact `client_id` only;
  - a profile may be bound by `client_id` or by exact `redirect_uri`;
  - an implicit-host DCR registration receives a random `tgmcp_` `client_id` (`internal/oauth/dcr_allowlist_test.go`), so no ceiling can bind it.
- WHEN revocation is described THE SYSTEM SHALL state the pinned semantics, citing `internal/oauth/server.go` `handleRevoke` and `SECURITY.md`:
  - `/oauth/revoke` revokes the refresh-token family and answers 200 with an empty body for unknown or foreign tokens;
  - replay of a rotated refresh token revokes the family;
  - issued access tokens stay valid until `OAUTH_ACCESS_TOKEN_TTL` (1h on production and preview);
  - the refresh absolute lifetime defaults to 720h;
  - account deletion revokes the families;
  - disconnect ends the Telegram session but keeps the OAuth grant.

  No test shall expect an immediate 401 on `/mcp` after a revoke.

### Test plans (P2-04)
- WHEN test plans are written THE SYSTEM SHALL produce two separate plans:
  - **Conformance:** a scripted client against `tg-preview.mctl.ai`, synthetic or isolated approved account, which proves server behaviour only.
  - **Vendor interoperability:** one row per client category (Grok Bot, Townie, and optionally Grok Chat and Cursor IDE, labelled as distinct categories). Each row records the registration strategy, the exact callback host and URI, `resource`, PKCE, the requested and the granted scopes, `initialize`, `tools/list`, `get_my_identity`, one harmless read of a synthetic chat, negative cases and audit.
- WHEN any step is listed THE SYSTEM SHALL state its exact expected HTTP or JSON-RPC outcome and its timing, grounded in code, and mark it `NOT-EXECUTED`.
- IF a later external live test is proposed THEN THE SYSTEM SHALL list these preconditions:
  - a verified stable client identity;
  - a `core-readonly` profile AND a scope ceiling of exactly the minimum read scopes;
  - no `admin:*`, groups, `telegram:messages:send`, `telegram:messages:pin` or `account:manage`;
  - verification of the minted and refreshed tokens' scopes without logging token values;
  - separate owner approval.
- IF a client has only a dynamic or rotating `client_id` THEN THE SYSTEM SHALL mark that live test BLOCKED pending a separate owner decision. It shall never propose widening policy or relying on prompt instructions.

### Threat model and consent (P2-05, P2-06)
- WHEN the external-client threat model is written THE SYSTEM SHALL list, control by control, which PA protections from `docs/agent-runtime/personal-assistant-threat-model.md` do NOT apply to a direct MCP client: consent `pa-data-flow/v1`, taint, kill switches, PA budgets, PA audit-before-dispatch and pin. It shall then state which `tg` server-side controls do apply.
- WHEN Grok Bot boundaries are described THE SYSTEM SHALL quote the vendor's own statements on shared connections, the shared cloud computer and session boundaries, and mark everything else `UNKNOWN`.
- WHEN Alice is covered THE SYSTEM SHALL state:
  - `iot:view` against `iot:control` and `quasar`, from the PA threat model and `internal/pa/connection/scope.go`;
  - that the mctl-alice code itself was not read in this run, so its server-side `TOOL_SCOPES` claim stays secondary evidence;
  - that no real device and no control call is in any plan.
- WHEN a hypothesis touches digest, memory or external distribution THE SYSTEM SHALL cite `docs/design/core-profiles.md` "Telegram terms: what a profile does and does not solve" and the official Telegram terms. It shall state that the account owner's consent is not the consent of other chat participants, and list the policy and legal questions apart from the engineering questions.

### Meetup (P2-07)
- WHEN the meetup pack is written THE SYSTEM SHALL target:
  - Nov 26 for the docs and demo pack;
  - Nov 27 for a rehearsal;
  - Nov 28 for the event.

  It shall define:
  - **A (mandatory):** an offline synthetic pitch (60-90 s), architecture, public discovery evidence, and a storyboard using Alice, Bob, Carol and Dana only;
  - **B (optional):** a PA read-only preview, gated on #1318, #1319 and owner GO;
  - **C (optional):** Grok Bot OAuth with a synthetic read, gated on a separate owner GO and verified confinement.

  It shall also give an explicit fallback to A if OAuth, the PA, vendor access or the event date is unavailable.
- IF a meetup finding is reported before real observations exist THEN THE SYSTEM SHALL treat it as a defect. The findings section stays an empty, anonymized template with no field for names, handles, phones or chat content.

### Hypotheses, metrics, decision
- WHEN hypotheses are proposed THE SYSTEM SHALL give 3-5 of them. Each shall give:
  - the user job and a differentiation statement;
  - evidence with its class;
  - impact, confidence and effort;
  - measurable success and failure;
  - dependencies, the smallest experiment, and cost and security implications;
  - its owner.

  Voice input is labelled "candidate, owner pending triage, no new epic".
- WHEN metrics are defined THE SYSTEM SHALL define activation, D7 repeat usage, task success, cost per successful task, and approval and denial rates, each with its retention and privacy constraint.
- WHEN the report concludes THE SYSTEM SHALL state exactly one decision and the next owner decision. DUAL_TRACK_BOUNDED is treated as a hypothesis to test, not a predetermined outcome.
- WHILE the spike is in progress THE SYSTEM SHALL leave all of these unchanged:
  - runtime, OAuth configuration, production, live data, paid plans and accounts;
  - every phase HOLD, the #1327 scope ceiling and the ADR 0011 gates;
  - consent, provider disclosure, audit, taint, budget and release gates.

## Out of scope

- Any code, configuration, gitops, flag, allowlist, CIMD host, profile or ceiling change, including the admission work tracked in #1381, #1385 and #784.
- Enabling or deploying the PA.
- Live account linking, vendor sign-up or spend, outreach, event registration, date confirmation with the organizer (an owner action), payment, and live tool writes.
- Builder UI (#1280), connector security and custom MCP (#1048), the managed runtime (#1088), and Phase 4 memory, routines and Glovo (#1325).
- Running interviews, and any external live test.
- Approval, the implementer and a report PR at intake.

## Open questions

- Meetup date: the owner must confirm 2026-11-28 with the organizer. If the date moves, pack A still ships and tracks B and C are re-gated.
- Grok Bot custom MCP: the vendor docs fetched on 2026-11-21 give a "Server URL", optional "HTTP headers" and an OAuth "Client ID" and "Client Secret". They state no callback URL, DCR or CIMD. The relation of `grok.com` admission (Grok Chat) to Grok Bot is `UNKNOWN`. The docs also say "App sign-ins stay on Cursor's servers", and whether Grok Bot's OAuth callback is on `cursor.com` is `UNKNOWN`. It must not be inferred.
- Grok Bot "Client ID" field: could a static preregistered client give a stable `client_id` that a ceiling can bind? Production sets no `OAUTH_PREREGISTERED_CLIENTS`. This is a separate owner decision and is not proposed here.
- Town: it is unconfirmed whether Town uses CIMD or DCR, and no token or tool call is proven (compatibility matrix). The Town binding is a `core-reply` profile with no scope ceiling. Whether a ceiling should be added is an owner decision outside this spike.
- Alice: the mctl-alice repo was not available in this run. Its OAuth discovery, its `TOOL_SCOPES` and its revocation are secondary evidence, taken from the PA threat model only.
- Telegram licensing: per-chat consent of other participants, and whether an own-messages-only mode is needed. These need a legal opinion and a product decision.
- Test account: which isolated approved account, if any, the owner allows for a later run. The plan assumes `tg-preview.mctl.ai`. Preview admits none of the vendor hosts, so a vendor row on preview is BLOCKED without an owner decision.

## Revision 3: observed Grok and bounded Grok Bot interoperability (2026-11-23)

- THE SYSTEM SHALL distinguish (a) Grok on grok.com: OWNER_OBSERVED_WORKS against https://tg.mctl.ai/mcp on 2026-11-22; (b) Grok Bot as a separately named product: exact initiating client/build UNKNOWN; and (c) least-privilege / negative interoperability checks: NOT_PROVEN. Cite https://github.com/mctlhq/mctl-telegram/pull/1393 , https://github.com/mctlhq/mctl-telegram/issues/1381 and docs/platforms/compatibility.md. Do not repeat already successful Grok OAuth simply to fill a research matrix.
- THE SYSTEM SHALL record the 2026-11-21 #1381 audit nuance: the signing-in platform-admin account was granted implicit admin membership scopes beyond the five requested scopes. Functioning OAuth is **not** evidence of effective read-only scope confinement, safe sends, token refresh or revocation. A restricted, isolated test requires separate owner GO, exact stable client identity, scope ceiling, appropriate profile and synthetic data.
- THE SYSTEM SHALL include a date-labelled source-to-claim ledger for Grok Bot Remote HTTPS custom MCP, skills and routines, Hermes skills, dots and Gemini proactive tasks. Each vendor claim is VENDOR_DOCUMENTED, distinct from an MCTL tested integration; document missing exact callback/PKCE/resource/client evidence as UNKNOWN. Sources: https://docs.x.ai/grok-bot/computer-and-apps , https://docs.x.ai/grok-bot/skills-routines-and-automations , https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/skills.md .
- THE SYSTEM SHALL update the PA baseline: production has no PA variables; preview has explicit PA_ENABLED=false, PA_EXTERNAL_TOOLS_ENABLED=false, PA_SERVER_TG_ENABLED=false, PA_WRITES_ENABLED=false; the dedicated agent-worker-pa-preview is at replicaCount 0 in GitOps. This is desired state, not proof of a live run.
- The comparative experiment SHALL separate a skill (non-authoritative procedure) from a routine (versioned, approved schedule/event occurrence) and user memory. External Grok observations do not imply PA runtime or Phase 4 activation. Existing #1398/#1325 own those designs.
- The report SHALL distinguish OWNER_OBSERVED_WORKS, OBSERVED_AUDIT, VERIFIED_CODE, VERIFIED_GITOPS, VENDOR_DOCUMENTED, UNKNOWN and NOT_EXECUTED. Explicitly state the limits of #1393: owner report without replayable commands or screenshots. Preserve all HOLDs and status proposed.
