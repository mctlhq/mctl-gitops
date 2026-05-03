# Design — wrangler-node22-ci-upgrade

## Current state

The mctl-web Cloudflare Worker is deployed by a `deploy.yml` GitHub
Actions workflow that lives in this repository — the only service on the
platform that does not use the centralized mctl-gitops build pipeline (see
`context/architecture.md`, "Cloudflare Worker" and "Known limitations").

The workflow runs `npm ci` and then `wrangler deploy`. If the workflow
currently pins `node-version: '18'` or `node-version: '20'`, the
combination with wrangler @4.87.0 is immediately fatal: wrangler's startup
code validates the Node.js major version and calls `process.exit(1)` with
a human-readable error before any deploy logic runs. This blocks 100% of
Worker deploys until remediated.

The Nuxt SSG build step (which may share the same workflow or run in a
parallel job) is not directly affected by the wrangler version gate, but
it will benefit from Node 22's performance improvements.

## Proposed solution

Three coordinated changes, all in the same pull request:

### 1. Update Node.js version in `deploy.yml`

In every job that invokes wrangler, change the `actions/setup-node` step:

```yaml
- uses: actions/setup-node@v4
  with:
    node-version: '22'
```

If the Nuxt build job is in the same workflow file, update it to `'22'`
as well to keep the environment consistent. Node 22 is the current LTS
line; pinning the major version (rather than `latest`) avoids unexpected
breakage from a future major bump.

### 2. Bump wrangler in `package.json`

```json
"wrangler": "^4.87.0"
```

Using a caret range (`^4.x.x`) ensures patch and minor updates within the
v4 major are picked up automatically on future `npm ci` runs while
protecting against a v5 major-version break. After editing `package.json`,
run `npm install` locally to regenerate `package-lock.json` and commit
both files.

### 3. Verify end-to-end in CI

After merging, the first CI run acts as the integration test:
`npm ci` installs the bumped wrangler, `node --version` confirms 22.x, and
`wrangler deploy --dry-run` (or the real deploy to the staging environment)
confirms a zero exit code.

## Alternatives considered

### A. Pin wrangler below 4.87.0 (e.g., `4.86.x`)

This avoids the Node version bump but leaves the project on an older
workers-sdk version indefinitely. Every subsequent wrangler release will
carry the same gate, making this a temporary workaround that increases
future upgrade debt. Security patches and Cloudflare runtime improvements
would be missed. Rejected.

### B. Override the Node version check via an environment variable or
   patch

Cloudflare has explicitly stated the gate is intentional and will not be
bypassable. Even if a workaround existed, it would be fragile and outside
supported usage. Rejected.

### C. Enforce Node 22 via `.nvmrc` or Volta in addition to the CI change

This is a complementary developer-experience improvement (ensures local
`wrangler dev` also uses Node 22) but does not replace the CI change and
is not required for the Worker deploy pipeline to function. It may be
added in the same PR as a bonus task but is not the primary fix.

## Platform impact

- **Tenant**: `admins`. The Worker is deployed under the `admins` tenant.
- **`labs` tenant**: no impact. This change touches only the Worker
  deploy CI job; no Kubernetes workloads, Helm charts, or shared
  infrastructure are modified.
- **Memory / CPU**: no runtime resource change. The Node.js version bump
  in CI affects ephemeral GitHub-hosted runner environments only.
- **Backward compatibility**: Node 22 is fully backward-compatible with
  the Worker source code (plain TypeScript / JS targeting Cloudflare's
  workerd runtime). The wrangler CLI itself does not run inside the Worker;
  it is a local/CI build tool only.
- **Nuxt build**: Node 22 is supported by all Nuxt 4.x, Vue 3.x, and Vite
  versions currently used in mctl-web. No build regressions are expected.
- **Rollback risk**: low. Both changes (YAML + package.json) are trivially
  reverted by a single revert commit. The Cloudflare Worker itself is not
  modified.
- **Migration**: none required. There are no database schema changes,
  environment variable changes, or Cloudflare secret rotations.
