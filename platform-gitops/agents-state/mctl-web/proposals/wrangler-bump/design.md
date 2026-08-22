# Design: wrangler-bump

## Current state
Per `context/architecture.md`, the Cloudflare Worker is deployed via Wrangler through
GitHub Actions (`deploy.yml` in this repo — an explicit exception from centralized
`mctl-gitops` builds). The Worker handles `/api/github/login`, `/api/github/callback`,
`/api/submit` (tenant provisioning via Backstage), and `/api/contact`, with rate
limits on submit/contact/login endpoints, and uses several secrets (Telegram, GitHub
OAuth, Backstage HMAC token, Resend) managed via Cloudflare Dashboard / `wrangler
secret`. wrangler itself is a build-time devDependency of this pipeline — it is not
part of the Worker's runtime bundle.

## Proposed solution
Bump the `wrangler` devDependency (part of `cloudflare/workers-sdk`) used by
`deploy.yml` to 4.125.0, or the latest patch release at execution time. Concretely:

1. Update the wrangler version pin in the deploy pipeline's dependency manifest
   (`package.json` devDependencies or equivalent used by `deploy.yml`).
2. Run the pipeline against a non-production target (or a dry-run/`--dry-run` deploy
   if supported) to confirm compatibility with the current `wrangler.toml`
   configuration before deploying to production.
3. Deploy to production via the normal `deploy.yml` flow and confirm the Worker
   remains reachable and functioning (OAuth login/callback, submit, contact, and
   domain redirects).

Since wrangler operates only at build/deploy time and does not run inside the deployed
Worker, this bump carries no runtime dependency risk to the live service between
deploys — the risk surface is limited to the deploy pipeline itself.

## Alternatives
- **Skip the bump since it's "just" a devDependency**: rejected — the KV value
  corruption bug is a correctness issue that could silently corrupt data written
  through the deploy tooling (e.g., any KV-backed state managed via wrangler), and the
  auth-handling fix reduces CI deploy flakiness/security risk around Cloudflare
  authentication; both are concrete, fixed bugs worth picking up given the low
  effort.
- **Wait and bundle this with the next larger pipeline change**: rejected — the fix is
  low-effort and low-risk on its own; bundling it with unrelated pipeline work only
  delays the fix without reducing risk.
- **Adopt wrangler's new features (TCP `connect`, preview containers, workflow
  instance deletion) as part of this same change**: rejected — those are unrelated to
  the driving rationale (KV corruption + auth fixes) and would broaden the scope and
  review surface of what should be a narrow, low-risk bump.

## Platform impact
- **Migrations:** None. No data migration; wrangler is a CLI tool used at deploy time,
  not a stored dependency in the Worker's runtime bundle.
- **Backward compatibility:** Review `wrangler.toml` and any CLI flags used in
  `deploy.yml` for compatibility with 4.125.0 before merging; the deploy pipeline
  itself should continue to function identically from the perspective of routes,
  secrets, and rate limits.
- **Resource impact (labs):** None. mctl-web and its Worker are deployed in the
  `admins` tenant only; this change does not touch the `labs` tenant or any
  Kubernetes-scheduled workload memory footprint (Wrangler here is a GitHub
  Actions build tool, not a cluster workload).
- **Risks and mitigations:**
  - Risk: a breaking CLI/config change in wrangler 4.125.0 causes `deploy.yml` to
    fail. Mitigation: dry-run/non-production validation (step 2 above) before the
    production deploy.
  - Risk: KV corruption fix behavior differs from what the pipeline currently
    (accidentally) relies on. Mitigation: verify any KV-backed state used by the
    Worker post-deploy, since `hasDatabase=false` suggests limited persistent state,
    but KV namespaces used for secrets/rate-limit counters should be checked.
  - Risk: low — this is the lowest-impact/lowest-effort item of the Top-3, and any
    issue is confined to the deploy pipeline, not the running Worker between deploys.
