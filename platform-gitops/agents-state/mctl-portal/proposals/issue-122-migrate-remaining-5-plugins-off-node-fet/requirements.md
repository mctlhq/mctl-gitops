# Migrate the remaining five backend plugins off node-fetch@2 to the Node 22 global fetch

## Context

`mctl-portal` runs on Node 22 (`package.json` `engines.node: "22 || 24"`, runtime image
`node:22-bookworm-slim` in `Dockerfile`), where `fetch` is a stable global backed by undici.
`mctl-portal#121` already migrated `custom-domains-backend` to that global: its
`plugins/custom-domains-backend/src/mctlApiClient.ts` calls bare `fetch(...)` and uses the ambient
`RequestInit` / `AbortSignal` types, its `package.json` carries neither `node-fetch` nor
`@types/node-fetch`, and `plugins/custom-domains-backend/src/mctlApiClient.test.ts` mocks
`jest.spyOn(globalThis, 'fetch')` instead of `jest.mock('node-fetch', ...)`.

Five plugins still import `node-fetch@2`: `argo-workflows-backend`, `github-app-connect-backend`,
`proposals-backend`, `tenant-backend`, `vault-secrets-backend`. The repo is already inconsistent
*inside* those packages — `plugins/tenant-backend/src/router.ts:217` and
`plugins/github-app-connect-backend/src/githubDiscoveryProcessorModule.ts` (lines 66, 81, 101)
already call the global `fetch`, while sibling files in the same plugin go through node-fetch. So a
single plugin issues outbound HTTP through two different HTTP client stacks with different
connection pooling, timeout defaults, and error types, purely by historical accident. This proposal
finishes the job: one fetch driver across the whole backend, five fewer direct dependencies (plus
five `@types/node-fetch` dev dependencies), and no remaining `jest.mock('node-fetch')` test
scaffolding. It is a driver swap only — no endpoint, payload, retry, or auth behavior changes.

## User stories

- AS a mctl-portal maintainer I WANT every backend plugin to use one HTTP client (the Node 22
  global `fetch`) SO THAT outbound-HTTP behavior, error handling, and test mocking are uniform
  instead of split per file.
- AS a maintainer reviewing a dependency alert I WANT no first-party plugin to declare
  `node-fetch`/`@types/node-fetch` SO THAT a node-fetch@2 advisory does not require patching five
  packages that do not need the library at all.
- AS a developer writing a test for a backend plugin I WANT one mocking idiom
  (`jest.spyOn(globalThis, 'fetch')`) SO THAT I can copy any existing test in the repo without
  first checking which fetch driver that plugin happens to use.
- AS a platform operator I WANT the migration to leave request URLs, methods, headers, bodies, and
  status handling byte-identical SO THAT no portal feature changes behavior when the PR merges.

## Acceptance criteria (EARS)

- WHEN the migration is complete THE SYSTEM SHALL contain no `from 'node-fetch'` import in
  `plugins/argo-workflows-backend`, `plugins/github-app-connect-backend`,
  `plugins/proposals-backend`, `plugins/tenant-backend`, or `plugins/vault-secrets-backend`
  (currently: `argoClient.ts:1`, `github-app-connect-backend/src/router.ts:6`,
  `github-app-connect-backend/src/plugin.ts:8`, `proposals-backend/src/gitops-client.ts:1`,
  `tenant-backend/src/tenantSync.ts:1`, `tenant-backend/src/githubAppToken.ts:2`,
  `vault-secrets-backend/src/vaultAuth.ts:1`, `vault-secrets-backend/src/router.ts:2`, plus the
  three test files listed below).
- WHEN the migration is complete THE SYSTEM SHALL have removed `"node-fetch"` from `dependencies`
  and `"@types/node-fetch"` from `devDependencies` in each of those five `package.json` files, and
  `yarn.lock` SHALL be regenerated so `yarn install --immutable` (`.github/workflows/validate.yml`
  step "Install dependencies") succeeds.
- WHEN `plugins/argo-workflows-backend/src/argoClient.ts` no longer imports `node-fetch` THE SYSTEM
  SHALL type `ArgoWorkflowsClient.request`'s `options` parameter with the ambient global
  `RequestInit` type (the same type `custom-domains-backend/src/mctlApiClient.ts:159` already uses
  without an import), keeping the method signature source-compatible for its callers.
- WHILE the fetch driver is being swapped THE SYSTEM SHALL preserve every request URL, HTTP method,
  header set, body, status check, and thrown error message exactly as written today — no timeouts,
  retries, abort signals, or response-shape changes are introduced.
- WHEN a test previously used `jest.mock('node-fetch', () => jest.fn())` THE SYSTEM SHALL instead
  install `jest.spyOn(globalThis, 'fetch')` and restore it afterwards, following
  `plugins/custom-domains-backend/src/mctlApiClient.test.ts:6-14`; this applies to
  `vault-secrets-backend/src/vaultAuth.test.ts`, `vault-secrets-backend/src/router.test.ts`, and
  `github-app-connect-backend/src/router.auth.test.ts`.
- IF a test file both stubs an upstream call AND drives a real local HTTP server through
  `globalThis.fetch` — which `plugins/vault-secrets-backend/src/router.test.ts` does (it stubs
  Vault at `https://vault.example` while calling `globalThis.fetch` against
  `http://127.0.0.1:<port>` at lines 404, 414, 423, 433, 444, 453, 468, 480, 491, 502) — THEN THE
  SYSTEM SHALL keep the two apart by capturing the real `fetch` reference at module load and using
  it for the server-driving calls, so that the spy still observes Vault traffic only.
- WHILE `vault-secrets-backend/src/router.test.ts` asserts `expect(fetchMock).not.toHaveBeenCalled()`
  (lines 474, 484, 496) THE SYSTEM SHALL keep those assertions meaning "no Vault request was made",
  not "no HTTP request of any kind was made".
- WHEN the change is complete THE SYSTEM SHALL pass `yarn tsc --noEmit`, `yarn build:backend`, and
  `yarn test` with no new failures, and every previously passing test in the three migrated test
  files SHALL still pass with unchanged assertions apart from the mock-installation lines.
- IF `Response.json()` resolves to `unknown` rather than `any` under the repo's ambient typings
  THEN THE SYSTEM SHALL add an explicit cast at the two currently uncast call sites
  (`github-app-connect-backend/src/plugin.ts:73` `const items = await resp.json();` and
  `plugins/github-app-connect-backend/src/plugin.ts:101` `return resp.json();`) rather than widen
  any consumer's type.

## Out of scope

- `custom-domains-backend` — already migrated in `#121`.
- Any behavioral change beyond the fetch-driver swap: no added timeouts/`AbortSignal.timeout`, no
  retry logic, no new error mapping, no endpoint or payload changes.
- Removing `node-fetch` from `yarn.lock` entirely. It stays as a transitive dependency of upstream
  packages (see `yarn.lock` entries at lines 154, 1821, 3238, 7780, 10270, 15777, 19178); the goal
  is only that no first-party plugin declares it.
- Adding an ESLint guard (e.g. `no-restricted-imports` for `node-fetch`) to prevent regressions.
- Adding new test coverage for code that has none today (`tenant-backend/src/tenantSync.ts`,
  `tenant-backend/src/githubAppToken.ts`, `proposals-backend/src/gitops-client.ts`'s HTTP paths —
  `gitops-client.test.ts` only exercises `parseStatusYaml`).
- The frontend (`packages/app`) and non-plugin packages.

## Open questions

- Should a lint guard be added so a future PR cannot reintroduce `import ... from 'node-fetch'`?
  The issue does not ask for one. Recorded as deferred; this proposal keeps the diff mechanical and
  leaves the guard to a follow-up issue.
- The clone has no `node_modules`, so it is not possible to confirm offline whether the ambient
  `Response.json()` in this toolchain resolves to `Promise<any>` (DOM lib) or `Promise<unknown>`
  (`undici-types` via `@types/node`). Both are handled: every other call site already casts
  (`as { token: string }`, `as ContentItem[]`, etc.), and the two uncast sites in
  `github-app-connect-backend/src/plugin.ts` flow into `RouterOptions` fields typed
  `(request: any) => Promise<any>` (`router.ts:38-39`), so a cast there is safe and local.
  `yarn tsc --noEmit` is the arbiter.
- Undici applies default `headersTimeout`/`bodyTimeout` (~300s) where node-fetch@2 had none. A
  request that previously hung forever against an unresponsive upstream will now reject after ~5
  minutes. This is judged an improvement and is not compensated for; flagged so a reviewer can
  disagree.
