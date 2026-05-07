# Design: platform-temporal

## Source commits
- `mctl-gitops:c2066ae` — feat(infra): add Temporal as platform service
- `mctl-gitops:c878333` — feat: onboard labs/kuptsi-app (first Temporal tenant, context only)

## Current state of documentation
- **Page is missing** — no `docs/platform/temporal.md` exists.
- `docs/platform/components.md` lists platform components but Temporal is absent.
- `docs/platform/overview.md` ("What is MCTL?") describes the platform without
  mentioning Temporal.

## Proposed solution

**Action:** Create a new page `docs/platform/temporal.md`.

**Content outline:**
1. **Introduction** — what Temporal is (brief, with link to temporalio.io), why the
   platform provides it as a shared service.
2. **Web UI** — URL (`temporal.mctl.ai`), Backstage OIDC authentication requirement
   (same credentials as `app.mctl.ai`).
3. **Connecting a Temporal worker** — Temporal Frontend address, `<TODO: confirm
   exact gRPC endpoint with author of c2066ae>`, namespace parameter.
4. **Getting a namespace** — current manual process: open a request with the platform
   team; they extend the PostSync Job registration script in mctl-gitops. Note that
   self-serve is not yet available.
5. **Architecture note** — shared PostgreSQL cluster (advanced visibility mode),
   Vault-sourced credentials.
6. **Mermaid diagram** — auth flow for the Web UI (user → Backstage OIDC → Temporal
   Web UI → Temporal server).

**Also update:**
- `docs/platform/components.md` — add a one-line entry for Temporal (service name,
  URL, purpose) in the platform services table.
- `.vitepress/config.{js,ts}` — add `temporal` entry under the `platform/` sidebar
  group.

## Alternatives

1. **Add a Temporal section to `docs/platform/components.md`** — rejected: the
   component page already covers ArgoCD, Backstage, and mctl-agent. Adding Temporal
   inline would make it too long; the service has enough config detail (OIDC, worker
   config, namespace onboarding) to warrant a standalone page.

2. **Put Temporal under `docs/guides/`** (e.g. `docs/guides/temporal.md`) — rejected:
   Temporal is a platform service, not a how-to guide. The `docs/platform/` section is
   the correct home for infrastructure capabilities provided by the platform team.

## Impact
- **VitePress sidebar / nav config:** yes — must add `temporal` to the `platform/`
  group in `.vitepress/config.{js,ts}`.
- **Diagrams (mermaid):** one sequence diagram for the Web UI OIDC flow.
- **Documentation versioning:** applies to current production (deployed 2026-05-06).
  No version marker needed — feature is confirmed in production.
