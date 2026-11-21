# Spike: AI product discovery, comparing Grok Bot and Townie, plus an MCP interoperability test plan

## Context

Issue #1379 (P2, parent #1312 Personal Assistant) asks for a research-only spike. It compares three things: Townie (Town, the closest Telegram UX reference), Grok Bot (xAI's autonomous-agent benchmark) and MCTL's actual Personal Assistant (PA) as it exists today. The spike should answer four questions. Which daily jobs drive repeat use? Should MCTL be a PA, a trusted MCP provider for external agents, or both? Can Grok Bot and Townie use the existing MCTL MCP endpoints (`tg.mctl.ai`, `alice.mctl.ai`) through supported OAuth and transport, with no change to authority? Which gaps are evidence-backed product hypotheses?

The spike also prepares material for the Grok Bot Meetup Belgrade, listed for 2026-11-28. The date is unconfirmed because the banner and the date card differ.

This matters because MCTL already serves one of the compared vendors. Production `tg` admits Town as a CIMD client and pins it to the `core-reply` tool profile (gitops `services/labs/mctl-telegram/values.yaml`, `OAUTH_CIMD_ALLOWED_HOSTS`, `MCP_CLIENT_PROFILES`). ADR 0011 cites "the Town-style experience" as the reason the PA exists. Meanwhile the PA itself is not deployed: no `PA_*` flag is set on production or preview, and `PA_ENABLED` defaults to false. The output is one docs-only research report, `docs/spikes/pa-grok-town-benchmark.md`, plus a decision recommendation. It changes no code, configuration, OAuth policy or phase HOLD.

## User stories

- AS the product owner I WANT a dated, source-classified comparison of Townie, Grok Bot and the MCTL PA SO THAT I can choose between PA_FIRST, MCP_DISTRIBUTION_FIRST, DUAL_TRACK_BOUNDED and DEFER using evidence, not feature parity.
- AS the security owner I WANT an interoperability matrix and a test plan that are read-only, use synthetic data and include negative cases SO THAT any later external-client test cannot widen scopes, bypass consent or touch real chats.
- AS the person presenting at the meetup I WANT a short pitch, a synthetic demo storyboard and a consented interview script SO THAT I collect real future evidence without collecting PII.
- AS a later DevLoop investigator I WANT 3-5 hypotheses, each routed to its existing owner issue (#1325, #1048, #1088, #1280) SO THAT no parallel infrastructure is proposed.

## Acceptance criteria (EARS)

- WHEN the report is written THE SYSTEM SHALL record, at the top, the inspected mctl-telegram SHA, the mctl-gitops state used, and the access date of every vendor source.
- WHEN a claim is stated THE SYSTEM SHALL label it with exactly one class:
  - `VERIFIED`: read in this repo or gitops at the pinned SHA;
  - `VENDOR-DOCUMENTED`: stated on a cited primary vendor page, with URL and access date;
  - `UNTESTED`: plausible, not observed;
  - `NOT-IMPLEMENTED`: absent at the pinned SHA, or explicitly planned only;
  - `UNKNOWN`: the source is unavailable.
- WHEN the MCTL baseline is described THE SYSTEM SHALL classify each item as merged, deployed, feature-flagged, tested or planned. It shall cover at least these items: consent (`pa-data-flow/v1`), private-chat-only ingress, the conversation TTL (24 h max), `/new`, `/forget`, `/consent`, linking OAuth, server-side tool execution, audit, egress, taint, budgets, allowlist and kill switches. Each item shall cite a file path.
- WHEN the vendor benchmark covers custom MCP authentication for Grok Bot or Townie THE SYSTEM SHALL state support only as `VENDOR-DOCUMENTED` with a quoted primary source, or as `UNKNOWN`. It shall never infer support.
- WHEN the interop matrix is produced THE SYSTEM SHALL give one row per client and server pair (Grok Bot and Townie, each against `tg.mctl.ai` and `alice.mctl.ai`). Each row shall cover:
  - endpoint and transport;
  - discovery (RFC 9728 and RFC 8414);
  - registration (CIMD or DCR);
  - `resource`/audience;
  - PKCE;
  - redirect allowlist status;
  - scope ceiling or tool profile;
  - tool discovery;
  - revocation;
  - errors and timeouts;
  - taint and prompt-injection exposure;
  - audit and cost.
- WHILE no separate owner approval for a live external test exists THE SYSTEM SHALL mark every test in the plan `NOT-EXECUTED`. It shall not link accounts, call vendor services or change any OAuth allowlist, profile or ceiling.
- WHEN the test plan is written THE SYSTEM SHALL list positive steps: `initialize`, `tools/list` and one harmless read (`get_my_identity`), run with a synthetic or isolated approved test account. It shall also list negative steps: insufficient scope, a revoked token, a wrong audience, a redirect not on the allowlist, and a tool outside the profile. Each step shall state its expected HTTP or JSON-RPC outcome.
- IF a vendor client would need a new redirect host, a CIMD host, a profile binding or a scope change on `tg` or `alice` THEN THE SYSTEM SHALL record that as an owner decision in the open questions. It shall not propose the change as part of this spike.
- WHEN the meetup pack is written THE SYSTEM SHALL include:
  - a 60-90 second English pitch;
  - a demo storyboard that uses only synthetic personas (Alice, Bob, Carol, Dana);
  - an interop demo plan;
  - a voluntary script of 5-10 interviews;
  - an anonymized findings template with no field for names, handles, phone numbers or chat content.
- WHEN hypotheses are proposed THE SYSTEM SHALL give 3-5 of them. Each shall state the user job, evidence (with its class), impact, confidence, effort, a measurable success and failure, dependencies, the smallest experiment, cost and security implications, and its owning issue.
- WHEN metrics are defined THE SYSTEM SHALL define activation, D7 repeat usage, task success, cost per successful task, and approval and denial rates, each with its retention and privacy constraint.
- WHEN the report concludes THE SYSTEM SHALL give exactly one decision (PA_FIRST, MCP_DISTRIBUTION_FIRST, DUAL_TRACK_BOUNDED or DEFER) and name the next owner decision.
- IF any meetup finding is reported before the meetup has happened THEN THE SYSTEM SHALL treat it as a defect. The findings section stays an empty template until real observations exist.
- WHILE the spike is in progress THE SYSTEM SHALL leave all of these unchanged: phase HOLDs, the #1327 scope ceiling, ADR 0011 gates, consent, provider disclosure, audit, taint, budget and release gates.

## Out of scope

- Any code, configuration, gitops, flag, OAuth allowlist, CIMD host, client profile or scope-ceiling change.
- Enabling or deploying the PA (`PA_ENABLED`, `PA_SERVER_*_ENABLED`, `PA_WRITES_ENABLED`).
- Live account linking, vendor sign-up or spend, outreach, payment, and live tool writes.
- An assistant builder UI (#1280), connector security or custom MCP by URL (#1048), the managed runtime (#1088), and Phase 4 memory, routines and Glovo (#1325).
- Running the meetup interviews or reporting their results. Only the instruments are produced.

## Open questions

- Meetup date: 2026-11-28 is from the issue. The organizer must confirm it, because the banner and the date card differ. If the report cannot be reviewed before then, the meetup pack is still useful afterwards, but the deadline goes.
- Was this run allowed to fetch vendor pages? This investigation fetched none, so every vendor claim in the proposal is unclassified until the report author fetches the cited docs with a date. If fetching is not allowed, every vendor cell becomes `UNKNOWN`.
- Grok Bot custom MCP authentication: it is unknown whether Grok Bot supports remote MCP with OAuth 2.1 (CIMD, DCR or static client). If it does, its redirect host is not on `tg`'s `OAUTH_ALLOWED_IMPLICIT_HOSTS` or `OAUTH_CIMD_ALLOWED_HOSTS` today. Any test would first need an owner decision on admission and on a `core-readonly` profile binding.
- Townie on CIMD: the gitops comment says Town's hosts stay on the implicit list "until Town is confirmed on CIMD". Is Town on CIMD now? Did its connections re-authorize? This is unverified.
- `alice.mctl.ai` OAuth surface: the gitops values of mctl-alice do not show its OAuth discovery, scopes or narrowing. ADR 0011 records "If `alice` cannot narrow its scopes, Alice linking needs an owner decision." Every Alice row stays `UNKNOWN` until its repo is read.
- Test account: which isolated, approved, synthetic test account (if any) the owner will allow for a later live run. The plan assumes `tg-preview.mctl.ai`, never production.
- Whether the report should also cover mctl-api as a future single authorization server (ADR 0011 alternatives). Assumed out of scope; mentioned only as a dependency.
