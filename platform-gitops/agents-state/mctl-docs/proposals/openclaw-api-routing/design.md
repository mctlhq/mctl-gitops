# Design: openclaw-api-routing

## Source commits

- `mctl-api:e4f104d` — fix(openclaw): route identity workflows to argo-workflows + skill quota filter
- `mctl-api:92fbf9e` — fix(openclaw): block openclaw ops from generic /execute path
- `mctl-api:edba139` — fix(openclaw): restrict identity listing to the fixed allowlist

## Current state of documentation

- **Existing page:** `docs/platform/openclaw.md` — "OpenClaw Integration"
  - Covers OpenClaw's role, channels (Telegram/Slack/Discord), and tenant configuration
    at a high level.
  - Does **not** mention which API endpoints accept skill/identity operations.
  - Does **not** describe namespace routing for identity workflow pods.
  - Does **not** mention the identity listing allowlist or the consequence of calling the
    generic `/execute` path for OpenClaw ops.
  - **Stale** relative to shipped behaviour: the routing and allowlist restrictions are
    already live but undocumented.

## Proposed solution

Add a **"API paths and namespace routing"** subsection to `docs/platform/openclaw.md`
(after the existing channels/config section, before the Security section that will be
added by `openclaw-outbound-security`).

The subsection should cover:

1. **Dedicated endpoints** — Skill and identity operations must be called via their
   dedicated API paths; the generic `POST /api/v1/operations/:name/execute` endpoint
   returns `400` for these operation names. A short table of operation names → path category
   is sufficient (exact paths are in `docs/api/index.md`).

2. **Namespace routing** — Identity workflow pods (`openclaw-identity-save`,
   `openclaw-identity-delete`) run in the `argo-workflows` Kubernetes namespace regardless
   of which tenant initiates the call. This is intentional: identity operations are
   platform-scoped, not tenant-scoped.

3. **Identity listing allowlist** — Only callers in the configured allowlist may enumerate
   identities via the listing endpoint. Callers outside the allowlist receive an error.
   Admins who need listing access should contact the platform team.
   (`<TODO: confirm the exact allowlist mechanism / env var name with author of edba139>`)

No changes to `.vitepress/config` sidebar/nav are needed — new content goes inside the
existing `openclaw.md` page.

## Alternatives

1. **Add the routing info to `docs/api/index.md` only** — that page is the right place for
   full endpoint reference, but operators reading the OpenClaw integration page will miss
   the routing restriction. Dropped: both pages should mention it (integration page: prose;
   API reference: table).

2. **New standalone page `docs/platform/openclaw-api.md`** — premature; the content is short
   (one subsection). Dropped.

## Impact

- **Sidebar / nav config:** no change required.
- **Mermaid diagrams:** a simple flow diagram (caller → mctl-api → route decision →
  `argo-workflows` ns or tenant ns) would add clarity. Included in `proposed-content.md`.
- **Documentation versioning:** applies to mctl-api commits `e4f104d`, `92fbf9e`, `edba139`
  (shipped in 4.15.0+). version-status: unverified.
