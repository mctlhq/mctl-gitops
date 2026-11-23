# Spike (revision 4): AI product discovery, comparing Grok Bot and Townie, plus MCP conformance and vendor interoperability test plans

## Context

Issue #1379 (P2, parent #1312 Personal Assistant) asks for a research-only spike. It compares Townie (Town, the closest Telegram UX reference), Grok Bot (xAI's autonomous-agent benchmark) and the MCTL Personal Assistant (PA) as it really exists. It must answer four questions. Which daily jobs drive repeat use? Should MCTL be a PA, a trusted MCP provider for external agents, or both? Can Grok Bot and Townie use the existing MCTL MCP endpoints (`tg.mctl.ai`, `alice.mctl.ai`) through supported OAuth and transport, without any change to authority? Which gaps are evidence-backed product hypotheses? It also prepares a pack for the Grok Bot Meetup Belgrade, listed for 2026-11-28. That date is unconfirmed, because the banner and the date card differ.

This is revision 4 (2026-11-23), incorporating the owner-observed 2026-11-22 Grok connection. The independent review of revision 1 (gitops `bb69c72`) returned REQUEST_CHANGES with 0 P1, 7 P2 and 4 P3 findings, and its amendments supersede the original instructions where they conflict. design.md, section "Finding-to-change matrix", maps each finding to the sections that address it. The baseline is pinned again:

- HISTORICAL (2026-11-21) mctl-telegram `b318e97a027bdae661344d4a324ddf47dc1426c6`;
- HISTORICAL (2026-11-21) mctl-gitops `a967430042424562a696cac216e428e00631c252`; the current 2026-11-23 pinned source ledger is below.

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
- WHEN a claim is stated THE SYSTEM SHALL label its evidence with exactly one of `VERIFIED_CODE`, `VERIFIED_GITOPS_DESIRED`, `LIVE_ARGO_OBSERVED`, `OWNER_OBSERVED_WORKS`, `OBSERVED_AUDIT`, `VENDOR_DOCUMENTED`, `PROJECT_DOCUMENTED`, `DESIGNED_ONLY`, `NOT_IMPLEMENTED`, `UNKNOWN`. A proposed test has a **separate execution field** `NOT_EXECUTED`, `BLOCKED` or `EXECUTED` with run/date evidence; no contradiction between a historical owner-observed success and unexecuted negative tests.
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
- WHEN Alice is covered THE SYSTEM SHALL cite pinned `mctl-alice/src/tools/handlers.ts:4–26` for read `iot:view`, control `iot:control` and Quasar `quasar` tool scope enforcement; flag issuer/refresh/live OAuth as UNKNOWN if no direct proof and forbid real device/control calls.
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
- Town: `OWNER_OBSERVED_WORKS` on 2026-11-22 via merged #1393 (sign-in, token and tool call; owner report without repeatable transcript). **Only CIMD-versus-DCR choice remains UNKNOWN**. Existing `core-reply` profile is not a scope ceiling; future minimum ceiling requires separate owner decision.
- Alice: source is now verified at mctl-alice commit `cb276d6510ce01524b0ca90de46e10832aaee743`, `src/tools/handlers.ts:4–26`: four read tools accept `iot:view`, control tools require `iot:control`, Quasar tools `quasar`. Issuer, refresh and live end-to-end authentication are separately UNKNOWN until pinned/observed; no real-device action.
- Telegram licensing: per-chat consent of other participants, and whether an own-messages-only mode is needed. These need a legal opinion and a product decision.
- Test account: which isolated approved account, if any, the owner allows for a later run. The plan assumes `tg-preview.mctl.ai`. Preview admits none of the vendor hosts, so a vendor row on preview is BLOCKED without an owner decision.

## Revision 4: P2 reconciliation and current evidence (2026-11-23)

**Pinned repositories:** mctl-telegram ecbce7732fc2915a2a72dc21f1d1d2e9f8713d73; gitops 869582d33b66f5eb36de29ff9b52c487f2631ed4; mctl-alice cb276d6510ce01524b0ca90de46e10832aaee743; mctl-api 3233f6c0a00437f73021570d8a16253d2bcd524b; .github 60e9db522f18299e73dac23fffedfe5b4ce81930. The original 2026-11-21 SHAs above are HISTORICAL.

**Deployment evidence:** GitOps desired 2026-11-23: production mctl-telegram 0.145.0, no PA flags; preview main-6623542, PA_ENABLED=true, PA_EXTERNAL_TOOLS_ENABLED=true, PA_SERVER_TG_ENABLED=true, PA_WRITES_ENABLED=false, PA_SERVER_ALICE_ENABLED=false; PA worker replicaCount=1. Read-only live Argo status at 18:01–18:03Z: production, preview and PA worker Healthy/Synced, but this is NOT R1–R6 user evidence. S1 manifest has zero gap rows; #1317/#1319 open.

**Grok/Town:** [PR #1393](https://github.com/mctlhq/mctl-telegram/pull/1393) and [Grok #1381](https://github.com/mctlhq/mctl-telegram/issues/1381) record `OWNER_OBSERVED_WORKS` for **Grok (grok.com)** and Town on 2026-11-22, not scripted reproducibility. Grok Bot product/client/build attribution is UNKNOWN; do not label Grok definitively as Grok Web/Bot. The initial Grok OAuth mint for an admin inherited membership admin scopes; read-only least privilege, refresh/revoke negative cases remain **NOT_EXECUTED** and must be separately approved. The external-client PA policy does not automatically carry to Grok.

**Alice:** pinned source `mctl-alice/src/tools/handlers.ts:4–26` confirms four `iot:view` read methods (also accept `iot:control`), mutations `iot:control`, Quasar `quasar`; still UNKNOWN: issuer discovery/refresh/live test. No device action is authorized.

**Vendor source-to-claim evidence (checked 2026-11-23):** [Grok Bot skills/routines](https://docs.x.ai/grok-bot/skills-routines-and-automations), short excerpt “Set up a routine to” (VENDOR_DOCUMENTED); [custom MCP](https://docs.x.ai/grok-bot/computer-and-apps), excerpts “Remote HTTPS” and “OAuth Client ID” (VENDOR_DOCUMENTED, callback/client ID UNKNOWN); [Hermes skills](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/skills.md), “Agent-Managed Skills” (PROJECT_DOCUMENTED); [dots](https://openai.com/index/introducing-dots/), “Introducing dots” (VENDOR_DOCUMENTED); [Gemini schedules](https://support.google.com/gemini/answer/17094710), “A schedule acts as the automated trigger for a task” (VENDOR_DOCUMENTED); [Town MCP docs](https://www.town.com/docs/integrations/mcp-servers), “Town talks to MCP servers over Streamable HTTP only” (VENDOR_DOCUMENTED). Vendor features are NOT implemented PA features.

**Telegram licensing:** [official Content Licensing Terms](https://telegram.org/tos/content-licensing) mention “all relevant users individually provide explicit, informed, affirmative and continued consent”; the account owner's PA consent alone does not resolve other-participant consent. Keep the legal/policy gate open and synthetic demos only.

**11 historic findings:** P2-01 re-pinned current vs historic; P2-02 profile vs exact-client ceiling; P2-03 revocation TTL semantics; P2-04 conformance vs vendor plans; P2-05 external-client boundary plus Alice pinned; P2-06 legal gate OPEN; P2-07 Nov 26 docs / Nov 27 rehearsal / Nov 28 event with offline A fallback; P3 primary sources dated, product job hypotheses, voice owner pending triage, docs CI verified. All accepted only as research/plan, not runtime verified. Keep `proposed`, no merge/GO/implementer or external live test.