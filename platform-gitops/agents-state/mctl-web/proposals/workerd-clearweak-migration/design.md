# Design: workerd-clearweak-migration

## Current state
As documented in `context/architecture.md`, the Cloudflare Worker lives in `cloudflare-worker/` and is deployed via Wrangler through `deploy.yml`. It handles all `/api/*` routes for mctl-web:
- `/api/github/login` and `/api/github/callback` — GitHub OAuth
- `/api/submit` — tenant provisioning via Backstage
- `/api/contact` — contact form submissions

The Worker integrates with external services (GitHub OAuth App, Backstage API, Telegram Bot, Resend) via secrets stored in the Cloudflare Dashboard. Its npm dependencies are defined in `cloudflare-worker/package.json`.

workerd v1.20260426.1 deprecates the ClearWeak V8 API (used internally by some JavaScript runtimes and native Node.js addons to register weak reference callbacks). While pure JavaScript Worker code written against the standard Cloudflare Workers API does not use ClearWeak directly, it could be introduced transitively by an npm dependency that includes native bindings or that polyfills certain WeakRef-adjacent behaviour.

The deprecation is currently a warning; Cloudflare has not announced a hard removal date, but based on workerd's versioning cadence (frequent point releases) removal is expected within several months.

## Proposed solution
The migration follows an audit-first, fix-second approach:

**Phase 1 — Audit**
1. Search `cloudflare-worker/` source files for any explicit ClearWeak references (unlikely in pure JS, but confirms direct usage).
2. Enumerate all npm dependencies in `cloudflare-worker/package.json` (direct and transitive via `npm list --all`).
3. For each dependency, check if it ships native `.node` addons or references WeakRef/FinalizationRegistry APIs in a way that might delegate to ClearWeak internally. Flag candidates.
4. Deploy the Worker to a staging environment running against the latest workerd-compatible Cloudflare runtime and observe `wrangler tail` for ClearWeak deprecation warnings.

**Phase 2 — Remediation (conditional)**
- If no ClearWeak usage is found: document the audit result as a clean bill of health; no code changes are needed beyond updating `wrangler.toml` compatibility date to a value that acknowledges the new workerd baseline.
- If ClearWeak usage is found in Worker source: rewrite the affected section to use the updated API or a pure-JS equivalent.
- If ClearWeak usage is found in a transitive dependency: upgrade or replace the dependency with a version that has addressed the deprecation, or switch to an alternative that does not use the deprecated path.

**Compatibility date**: Update `wrangler.toml`'s `compatibility_date` to `2026-04-26` or later to opt in to the new workerd baseline and surface any remaining issues in `wrangler dev` before production.

## Alternatives

### Option A: Do nothing until Cloudflare removes the API
Wait until a runtime error forces action. Rejected because the Worker handles all `/api/*` traffic including OAuth and tenant provisioning; an unplanned outage at removal time has direct user impact and no advance notice window.

### Option B: Disable or mock the ClearWeak code path via a Wrangler compatibility flag
Cloudflare may expose a compatibility flag to temporarily retain the old behaviour. Rejected as a long-term strategy because compatibility flags are themselves time-limited and using them defers rather than resolves the problem.

### Option C: Rewrite the Worker in a runtime that does not expose the V8 ClearWeak concern (e.g., migrate to Cloudflare's module Workers with explicit lifecycle management)
A full Worker rewrite would certainly eliminate the issue but is far beyond the scope of a single deprecation. Rejected due to disproportionate effort for the risk level.

## Platform impact

### Migrations
- `wrangler.toml` `compatibility_date` is updated; this is a non-breaking Cloudflare-side configuration change.
- If any npm dependencies need updating, `package.json` and `package-lock.json` inside `cloudflare-worker/` are updated.

### Backward compatibility
The Cloudflare Workers JavaScript API surface used by the Worker (Fetch, KV, environment bindings, etc.) is unaffected by the ClearWeak deprecation. The Worker's HTTP behaviour—request handling, response codes, rate limiting—remains identical.

### Resource impact
The Worker runs in the `admins` Cloudflare account, not in Kubernetes. There is no CPU or memory impact on the `admins` or `labs` Kubernetes tenants. Cloudflare's own resource accounting for the Worker is unaffected by this change.

### Risks and mitigations
- **Risk:** The audit finds no ClearWeak usage, and a future workerd release introduces a new removal that this proposal did not catch.
  **Mitigation:** The updated `compatibility_date` in `wrangler.toml` ensures the Worker is regularly tested against the current runtime in `wrangler dev`; a standing practice of running `wrangler tail` after each deploy provides ongoing observability.
- **Risk:** A transitive dependency update (phase 2) introduces a regression in Worker behaviour.
  **Mitigation:** End-to-end smoke tests against the staging Worker (task 5) cover all four `/api/*` endpoints before production promotion.
- **Risk:** Cloudflare removes ClearWeak before this proposal is implemented.
  **Mitigation:** Impact is low if no direct usage exists (most likely); if removal causes a Worker startup error, rollback is immediate by reverting to the previous `compatibility_date` value.
