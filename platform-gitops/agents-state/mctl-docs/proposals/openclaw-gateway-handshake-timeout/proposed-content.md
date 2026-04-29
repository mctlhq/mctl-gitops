# Proposed content: openclaw-gateway-handshake-timeout

> **Apply to:** `mctl-docs/docs/platform/openclaw.md` (UPDATE)
> **Source:** mctl-openclaw@bcc6a24
> **Version-status:** unverified — confirm against production mctl-openclaw before merging.

---

## Before (no "Configuration reference" section currently exists)

```md
<!-- No configuration reference section exists in docs/platform/openclaw.md today. -->
```

## After — insert the following section (can be combined with the Deployment configuration
## section from proposal openclaw-docker-skip-onboarding if both land in the same PR)

---

```md
## Configuration reference (operations)

The following `gateway.*` configuration options are commonly tuned in mctl platform
deployments. Set them in your OpenClaw `config.json5` file or equivalent mounted config.

| Option | Type | Default | Description |
|---|---|---|---|
| `gateway.handshakeTimeoutMs` | number (ms) | `15000` | Pre-authentication WebSocket handshake timeout. Increase on loaded or low-powered Kubernetes nodes where clients connect successfully but timing out during startup warmup. `OPENCLAW_HANDSHAKE_TIMEOUT_MS` env var takes precedence when set. |

**Example — increase handshake timeout to 30 seconds:**

```json5
{
  gateway: {
    handshakeTimeoutMs: 30000,
  },
}
```

> **Guidance:** prefer investigating startup or event-loop stalls first. This knob is
> appropriate for nodes that are healthy but temporarily slow during warmup (e.g. after
> a rolling restart). If clients cannot connect even on a fully warmed node, investigate
> gateway CPU/memory or network policy issues instead.

For the full list of gateway configuration options see the
[OpenClaw gateway configuration reference](https://docs.openclaw.ai/gateway/configuration-reference).

> **Source:** commit `bcc6a24` (mctl-openclaw, 2026-04-28).
```

---
