# Design: openclaw-gateway-handshake-timeout

## Source commits

- `mctl-openclaw:bcc6a24` — fix(gateway): make handshake timeout configurable

## Current state of documentation

- **Existing page:** `docs/platform/openclaw.md` — "OpenClaw Integration"
  - No configuration reference section exists.
  - An admin hitting WebSocket handshake timeouts has no entry point in docs.mctl.ai;
    they must find and read the full openclaw gateway config reference.
  - **Gap:** the option is new and not documented anywhere in docs.mctl.ai.

## Proposed solution

Add a **"Configuration reference (operations)"** subsection to `docs/platform/openclaw.md`
that surfaces the small set of config options most relevant to mctl platform operators.
Start with `gateway.handshakeTimeoutMs` as the first entry; the section can grow.

Format: a small table (option, type, default, description) + a JSON5 code block showing
how to set the value, matching the pattern in openclaw's own configuration how-to.

Also add a "When to use" guidance note (verbatim from upstream: prefer fixing startup
stalls first; this knob is for hosts that are healthy but slow during warmup).

A cross-link to openclaw's full configuration reference (`docs.openclaw.ai/gateway/configuration-reference`)
should be present so readers can find other options.

No changes to `.vitepress/config` are needed.

## Alternatives

1. **Troubleshooting page only (`docs/reference/troubleshooting.md`)** — add a short
   callout to the existing troubleshooting page. Dropped: the option is a configuration
   choice, not a diagnostic step; it belongs in a config section alongside deployment vars.

2. **Separate `docs/platform/openclaw-config.md` page** — a dedicated config reference
   for openclaw on mctl; dropped as premature at one option. A single section in
   `openclaw.md` is sufficient.

## Impact

- **Sidebar / nav config:** no change (content added inside existing page).
- **Mermaid diagrams:** none needed.
- **Documentation versioning:** applies to mctl-openclaw as of commit `bcc6a24`.
  Version unverified (no mcp__mctl__* check possible).
