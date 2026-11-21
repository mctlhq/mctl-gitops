# Design: issue-1379-spike-ai-product-discovery-grok-bot-benc

## Current state

The clone is pinned at `568da0156513bb2b3bf63e53df608af759fcac30` (2026-11-21, merge of #1377). It is a shallow clone, so the history of `internal/pa` is not available.

### Personal Assistant (ADR 0011, epic #1312)

- `docs/adr/0011-personal-assistant.md` is `Status: Proposed`. It says "Accepting this record authorizes nothing to run." It defines:
  - a dedicated Bot API bot, private chats only;
  - Phase 1 is read-only on `tg` and `alice`;
  - consent `pa-data-flow/v1`;
  - a connector executor in which the worker never holds downstream tokens;
  - cookie-free linking (PKCE S256, RFC 8707 `resource`, RFC 9207 `iss`, two `initData` checks, a `get_my_identity` owner check for `tg`);
  - the tiers `auto`, `approve`, `disclosure` and `never`;
  - taint;
  - egress allowlists;
  - limits (8 tool calls per run, 64 KiB per tool output);
  - audit before dispatch;
  - the switches `PA_ENABLED`, `PA_EXTERNAL_TOOLS_ENABLED`, `PA_WRITES_ENABLED` and `PA_SERVER_<NAME>_ENABLED`.

  Its Consequences section names "the Town-style experience" as the goal.
- `docs/agent-runtime/personal-assistant-threat-model.md` covers T1-T14 (linking, state, credentials, ingress, taint, Alice disclosure, approvals, scopes, egress, cost, kill switches, audit, consent, output). The threat model is authoritative over the ADR.
- Code is merged under `internal/pa/`:
  - `ingress.go`, `webhook.go`, `runloop.go`, `conversation.go` and `memory.go`;
  - `catalog/`, `connector/` (`dispatch.go`, `mcpclient.go`), `linking/` (`linking.go`, `http.go` with `/pa/oauth/callback/{server}` and `/pa/oauth/handoff`, `flags.go` naming `ServerTG` and `ServerAlice`), `egress/`, `output/`, `gate/` and `jobs/`.
  - `conversation.go` handles `/new`, `/forget` and `/consent`. `DefaultConversationTTL` and `MaxConversationTTL` are both `24 * time.Hour`.
  - `phase2_inert_test.go` keeps the Phase 2 write primitives out of the running service.
- Gate manifests:
  - `docs/agent-runtime/pa-s1-manifest.yaml`: its header says the S1 gate "is NOT closed while any gap is listed", and the file still carries `gaps:` entries.
  - `docs/agent-runtime/pa-s2-manifest.yaml`: 26 `pending` and 4 `green` entries. Its header says "PA_WRITES_ENABLED stays off on every environment" until no id is pending.
- Flags: `internal/config/config.go:642` reads `envBool("PA_ENABLED", false)`.

### MCP provider surface used by external clients

- Discovery:
  - `cmd/server/main.go:522-523` serves `/.well-known/oauth-protected-resource` and its `cfg.MCPPath` alias;
  - `internal/oauth/server.go:1432` serves `/.well-known/oauth-authorization-server`;
  - `server.go:1440-1441` serves `/oauth/revoke` and `/oauth/register` (DCR);
  - `internal/oauth/cimd_client.go` handles CIMD.
  - `cmd/canary/main.go:105` defaults the MCP path to `/mcp`.
- Scopes:
  - `internal/oauth/scopes.go`: `narrowGrant`, `applyScopeCeiling` and `withinScopeCeiling` (the per-client ceiling, #1326);
  - `internal/toolprofile/toolprofile.go`: client bindings keyed by `client_id`, `redirect_uri`, `profile` and `scope_ceiling`.
- Profiles: `docs/design/core-profiles.md` defines `core-readonly` (`list_dialogs`, a bounded `get_messages`, peer-required search and unread, `get_my_identity`, and others) and `core-reply` (adds `draft_reply` and a `send_reply(confirmation_id)` that requires confirmation). The doc names Town as the motivating client.
- `internal/digest/digest.go` is an operator digest of new client sign-ins. It is not a user-facing daily digest, which is relevant to the "daily digest" hypothesis.
- `docs/spikes/assistant-builder-ui-reference.md` (#1280) sets the house style for a spike: a pinned SHA, an "Evidence limitations" section, and the labels `VERIFIED`, `VENDOR-DOCUMENTED`, `UNTESTED` and `UNKNOWN`. This spike follows it.
- `git grep -i -E "grok|x\.ai"` matches nothing in the repo, so the repo holds no Grok Bot material.

### Deployed state checked

- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml` (production `tg`):
  - image `0.140.1`;
  - `OAUTH_ISSUER_URL: https://tg.mctl.ai`;
  - `OAUTH_ALLOWED_IMPLICIT_HOSTS` includes `www.town.com` and `town.com`, but no xAI or Grok host;
  - `OAUTH_CIMD_ACCEPT` and `OAUTH_CIMD_ADVERTISE` are `"true"`;
  - `OAUTH_CIMD_ALLOWED_HOSTS: chatgpt.com,claude.ai,vscode.dev,www.town.com`;
  - `MCP_CLIENT_PROFILES` binds `https://www.town.com/.well-known/oauth-client-id` to `core-reply` (owner, 2026-10-22);
  - `OAUTH_ACCESS_TOKEN_TTL: 1h` and `OAUTH_CODE_TTL: 30m`;
  - no `PA_*` variable is set.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/values.yaml`:
  - image `main-568da01`, the same commit as the clone;
  - host `tg-preview.mctl.ai`, issuer `https://tg-preview.mctl.ai`;
  - the implicit hosts have no Town and no Grok entry;
  - `MANAGED_RUNTIME_ENABLED: "true"`;
  - no `PA_*` variable is set.

  So the PA is merged but deployed nowhere.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-alice/values.yaml`: image `2.15.1`, ingress `alice.mctl.ai`, one replica, a Yandex OAuth token from Vault. Its own OAuth server configuration (discovery, scopes, narrowing) is not visible here. Gap: `UNKNOWN`, recorded under Open questions.
- mctl MCP tools: not called. The gitops checkout answered the deployment questions. Live discovery documents were not fetched, so the discovery cells for the deployed hosts stay "read from config", not "observed".
- Vendor docs (town.com, docs.x.ai): not fetched by this investigation. Every vendor fact is unclassified until the report task fetches and dates it.

## Proposed solution

Write one docs-only research report, `docs/spikes/pa-grok-town-benchmark.md`. Its structure mirrors `docs/spikes/assistant-builder-ui-reference.md`:

0. **Header and evidence limitations.** Status PROPOSED, `Refs #1379` (not `Closes`), the pinned mctl-telegram SHA and gitops state, vendor access dates, and the label legend: `VERIFIED`, `VENDOR-DOCUMENTED`, `UNTESTED`, `NOT-IMPLEMENTED`, `UNKNOWN`, plus `NOT-EXECUTED` for tests.
1. **MCTL baseline.** A table with one row per item from work package 1. The columns are merged, deployed, flagged, tested, planned and the source path. The values come from the facts in Current state. For example, PA ingress is merged and tested but not deployed, and `PA_ENABLED` defaults to false. Internal identities are omitted: no Telegram ids, Vault paths or account ids. Consequence: the canary `MCP_K8S_SA_TELEGRAM_ID` and the Cloudflare account path in `OAUTH_DCR_REDIRECT_URIS` must not be copied.
2. **Vendor benchmark.** A matrix of Townie and Grok Bot across the 15 dimensions in work package 2, each cell labelled and sourced only from the six URLs in the issue. The cells for custom MCP authentication quote the vendor text verbatim, or say `UNKNOWN`.
3. **Interop matrix.** Four rows: Grok Bot and Townie, each against `tg` and `alice`. The `tg`-side columns come from code and config. For Townie x `tg`, admission is `VERIFIED` by config (CIMD plus implicit host, `core-reply` profile). For Grok Bot x `tg`, admission is `NOT-IMPLEMENTED`: no host is allowlisted. Admitting Grok Bot is an owner decision with a proposed `core-readonly` binding, and it is not made here. The `alice` columns are `UNKNOWN` until the mctl-alice repo is read.
4. **Reproducible test plan** (all `NOT-EXECUTED`). The target is `tg-preview.mctl.ai` with a synthetic or approved isolated account, driven by a scripted MCP client such as the existing `cmd/canary` probe pattern, not by the vendor.
   - Positive steps: discovery, CIMD or DCR, PKCE S256 with `resource`, `initialize`, `tools/list` (compared with the `core-readonly` descriptor), and `get_my_identity`.
   - Negative steps: a scope outside the ceiling, a revoked token after `/oauth/revoke`, a wrong `resource`, a redirect not on the allowlist, a profile-excluded tool such as `send_message`, and expired code reuse.
   - Each step states its expected result and the audit entry it should leave.
   - A vendor-driven step is listed separately and requires owner approval.
5. **Meetup pack:**
   - the pitch;
   - a storyboard on synthetic personas (Alice, Bob, Carol, Dana), using recorded screens or local synthetic data, never a live private chat;
   - an interop demo that shows only the discovery JSON and a `tools/list` against preview;
   - an interview script with a consent line and questions on recurring workflows, onboarding friction, confidence, and willingness to pilot or pay;
   - an anonymized findings template with no identity or chat fields.
6. **Hypotheses (3-5).** Candidates:
   - H1, daily digest of the user's own chats, routed to #1325 (routines);
   - H2, voice input, a new candidate gated by consent, T13 provider disclosure and a cost analysis;
   - H3, reusable skills and routines, routed to #1325;
   - H4, contextual memory, routed to #1325, using the no-op `memory.go` interface;
   - H5, external-client distribution (a client profile recipe for third-party agents), routed to #1048 for custom MCP and to the existing `toolprofile` mechanism.

   Each hypothesis carries ICE scores, metrics, the smallest experiment and its security implications. Metric definitions: activation, D7, task success, cost per successful task (from the #1092 ledger), approval and denial rates, and retention and privacy limits, with no message bodies stored and aggregates only.
7. **Decision and PDLC handoff.** The report recommends one of the four options, and the owner makes the decision. The provisional working hypothesis is DUAL_TRACK_BOUNDED, because the Town binding already exists, which is MCP distribution in production, while the PA stays gated by S1 and S2. The report confirms or rejects this from evidence. The handoff chain is AI Research -> Hypothesis -> OpenSpec -> DevLoop -> Governed Release -> Metrics -> Feedback.

The report is a Markdown file. If a docs test is added later (as for runbook and troubleshooting docs), that is separate work. This spike adds no test.

## Alternatives

- **Live end-to-end test with Grok Bot or Townie now.** Rejected. The issue forbids external live tests without separate owner approval. Grok Bot is not admitted by `tg`'s redirect and CIMD allowlists, so testing it would itself require an OAuth policy change.
- **Put the findings in ADR 0011 or the threat model.** Rejected. Research must not change governance documents or phase gates. A separate spike document keeps the authority boundary clear, as the #1280 precedent does.
- **Open feature issues for each gap (voice, digest, memory).** Rejected. The issue asks for hypotheses, not parity mandates. Scope belongs to #1325, #1048 and #1088, and parallel issues would fragment it.

## Platform impact

- Migrations: none. Backward compatibility: unaffected. No code, image, flag or gitops change. Resource impact: none.
- Risks and mitigations:
  - **Leaking internal identifiers into a public repo.** Do not copy numeric Telegram ids, Cloudflare account paths, Vault paths or principals from gitops. Use the synthetic personas only.
  - **Overstating vendor capability.** Use the strict labels and verbatim quotes, and keep `UNKNOWN` as a first-class value.
  - **Fabricated meetup results.** The findings section is a template only.
  - **The report being read as authorization.** The status line states that it grants nothing, uses `Refs` (not `Closes`), and needs an independent review before approval.
  - **A stale baseline.** Pin the SHA and the gitops state, and date everything.
