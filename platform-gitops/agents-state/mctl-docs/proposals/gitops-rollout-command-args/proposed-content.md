# Proposed content: gitops-rollout-command-args

> **Apply to:** `mctl-docs/docs/guides/gitops-workflows.md` (UPDATE)
> **Source:** `mctl-gitops@1e3f42f`
> **Mode:** insert the section below before the existing `## CI/CD Integration` heading
> (or after `## Repository Structure` — either position works; keep it in the
> "service configuration" part of the page rather than the workflow-mechanics part).

---

## Before (excerpt — no service values section exists today)

```markdown
## Repository Structure

The `mctl-gitops` repository is organized by tenant:
...

## CI/CD Integration

When you push a tag to a service repository:
...
```

## After (insert new section between the two above)

```markdown
## Repository Structure

The `mctl-gitops` repository is organized by tenant:
...

## Service Configuration Values

Every service deployed through the base-service Helm chart can override these
container-level values in its `values.yaml`:

| Value | Type | Description |
|---|---|---|
| `command` | `list<string>` | Override the container entrypoint (maps to `command:` in the pod spec). Optional — omit to use the image default. |
| `args` | `list<string>` | Override the container arguments (maps to `args:` in the pod spec). Optional — omit to use the image default. |

**Example** — service that wraps a binary with a custom entrypoint:

```yaml
# platform-gitops/services/tenants/my-team/my-app/values.yaml
command:
  - /app/wrapper.sh
args:
  - --port=8080
  - --env=production
```

> **Deployment and Rollout parity**
> Both the `deployment.yaml` and `rollout.yaml` base templates honour `command` and
> `args`. Prior to `mctl-gitops` commit `1e3f42f` (2026-05-02), these values were
> silently ignored when using the Argo Rollout strategy — the container would start
> with the default image entrypoint. If you were relying on this oversight (custom
> command intentionally suppressed in rollout mode), review your configuration.

::: warning Silent regression risk
If you recently switched a service from Deployment to Rollout strategy, check your
`values.yaml`. Custom `command` / `args` that worked in Deployment mode now also
apply in Rollout mode. Verify the container starts as expected after the rollout
template parity fix.
:::

## CI/CD Integration

When you push a tag to a service repository:
...
```

---

> **Note for implementer:** the `::: warning` callout uses VitePress custom containers
> (supported in VitePress 1.6). No plugin needed. Verify it renders correctly with
> `npm run dev`.
