# Proposed content: openclaw-docker-skip-onboarding

> **Apply to:** `mctl-docs/docs/platform/openclaw.md` (UPDATE)
> **Source:** mctl-openclaw@490e6d6
> **Version-status:** unverified — confirm against production mctl-openclaw before merging.

---

## Before (no "Deployment configuration" section currently exists)

```md
<!-- No deployment/env-var section exists in docs/platform/openclaw.md today. -->
```

## After — insert the following section after the overview / integration section

---

```md
## Deployment configuration

The mctl platform provisions OpenClaw non-interactively via ArgoCD. The following
environment variables are relevant when configuring the OpenClaw container in a GitOps
manifest or CI environment:

| Variable | Description | Accepted truthy values |
|---|---|---|
| `OPENCLAW_SKIP_ONBOARDING` | Skip the interactive onboarding step during Docker setup while still applying gateway defaults. Required for automated (non-interactive) deployments. | `1`, `true`, `yes`, `on` |

Set this variable in your ArgoCD `Application` manifest or Helm values under `env`:

```yaml
env:
  - name: OPENCLAW_SKIP_ONBOARDING
    value: "1"
```

For the full list of Docker setup variables (sandbox, volumes, socket paths, OTEL
config, etc.) see the
[OpenClaw Docker install guide](https://docs.openclaw.ai/install/docker).

> **Source:** commit `490e6d6` (mctl-openclaw, 2026-04-28).
```

---
