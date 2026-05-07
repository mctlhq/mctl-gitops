# Design: nuxt-minor-upgrade-v3

## Current state
As documented in `context/architecture.md`, `mctl-web` uses Nuxt 4.3.1 with SSR enabled
and prerendering configured for `/`, `/privacy`, and `/docs`. The build command is
`nuxt build`, which emits static files to `dist/` that are then deployed to Cloudflare Pages
by the `deploy.yml` GitHub Actions workflow via Wrangler. The full frontend dependency set
relevant to this upgrade is:

| Package        | Current version |
|----------------|----------------|
| nuxt           | 4.3.1          |
| vue (transitive) | 3.5.30       |
| @vueuse/core   | 14.2.1         |
| sass           | 1.98.0         |

vee-validate 4.15.1 and yup 1.7.1 are in scope for build regression testing but are not
bumped by this proposal (ADR 0001 constraint). vue-router 4.6.4 is also excluded (separate
proposal for v5 migration).

## Proposed solution
Update three explicit entries in the root `package.json`, regenerate the lockfile, and
validate the build. The changes are:

```
nuxt            4.3.1  →  ^4.4.3
@vueuse/core    14.2.1 →  ^14.3.0
sass            1.98.0 →  ^1.99.0
```

Vue 3.5.34 is not declared directly in `package.json` — it is pulled in transitively by
Nuxt 4.4.3, which updates its Vue peer-dependency range to cover 3.5.34.

The upgrade is applied in one pull request to keep the lockfile diff reviewable and to
ensure compatibility between all three packages is verified together. The implementation
steps are:

1. Edit `package.json` with the three version bumps above.
2. Run `npm install` to regenerate the lockfile.
3. Run `nuxt build` locally; inspect `dist/` for the three prerendered routes.
4. Run `npm audit --audit-level=high`; no new High or Critical CVEs are acceptable.
5. Deploy to a Cloudflare Pages preview branch; verify all routes return HTTP 200.
6. Open a pull request. CI must pass lint, type-check, and build before merge.

No changes to `nuxt.config.ts`, page components, composables, or the Cloudflare Worker
are anticipated, because all three bumps are within their respective minor lines and declare
backward compatibility.

## Alternatives

### Keep Nuxt at 4.3.1 and defer all companion bumps
The service is functional today and there is no known CVE in Nuxt 4.3.1 that demands an
immediate upgrade. Deferring is low-cost in the short term. Rejected because version debt
compounds: a two-minor gap now becomes a four- or five-minor gap in six months, at which
point the upgrade diff is much larger, harder to review, and more likely to contain hidden
breaking changes.

### Upgrade Nuxt but omit the @vueuse/core and sass bumps
Performing a Nuxt-only upgrade leaves `@vueuse/core` and `sass` one minor version behind
when they already have non-breaking updates available. Keeping them in sync with the Nuxt
ecosystem in the same PR avoids a second round of review and a second lockfile churn.
Rejected in favour of the bundled approach.

### Upgrade Nuxt together with vue-router to v5
Vue Router 5.x was released in April 2026 as a major version bump from 4.6.4. Bundling a
major router upgrade with this minor bump multiplies risk and effort, and makes regression
isolation much harder. Rejected; the router migration is tracked as a separate,
higher-effort proposal.

## Platform impact

### Migrations
- Root `package.json`: three version bumps (`nuxt`, `@vueuse/core`, `sass`).
- Regenerate root lockfile (`package-lock.json`).
- No database migrations, no Kubernetes manifest changes, no ArgoCD changes.
- No changes to `wrangler.toml` or Cloudflare Worker source.

### Backward compatibility
All three bumps are within their major lines (Nuxt 4.x, @vueuse/core 14.x, sass 1.x).
Nuxt and @vueuse/core minor releases are backward-compatible by policy. The sass 1.99.0
changelog contains no removals of sass features used in this project. If any deprecated
API surfaces as a build warning, it must be addressed in the same PR.

### Resource impact
The upgrade runs entirely in GitHub Actions during build time. The produced `dist/` is
served as static files via Cloudflare Pages; there is no runtime footprint on the
Kubernetes cluster. The `labs` tenant is not affected. Bundle size is expected to be
comparable to or smaller than the current 4.3.1 build.

### Risks and mitigations
- **Risk:** An undocumented breaking change in Nuxt 4.4.x silently corrupts one prerendered
  route. **Mitigation:** Run `nuxt build` locally and inspect the HTML of all three routes
  before opening the PR. CI enforces a build step on every commit.
- **Risk:** `vite-svg-loader 5.1.1` is incompatible with the Vite version bundled in
  Nuxt 4.4.3. **Mitigation:** Check the Nuxt 4.4.x release notes for the bundled Vite
  version; test an SVG-bearing page during local build verification.
- **Risk:** sass 1.99.0 emits new deprecation warnings for existing SCSS syntax.
  **Mitigation:** Run the build and treat any new sass warning as a blocking issue; update
  the SCSS syntax in the same PR.
- **Risk:** A transitive dependency introduced by Nuxt 4.4.3 carries a new CVE.
  **Mitigation:** Run `npm audit --audit-level=high` against the updated lockfile; no new
  High or Critical findings are acceptable before merge.
