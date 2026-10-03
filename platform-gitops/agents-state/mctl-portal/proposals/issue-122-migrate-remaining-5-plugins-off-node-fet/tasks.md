# Tasks: issue-122-migrate-remaining-5-plugins-off-node-fet

Tasks 1-3 are independent of each other and of 4-5. Task 4 (vault-secrets) is the only one with a
non-mechanical test change. Do them in one PR so `yarn.lock` is regenerated once.

- [ ] 1. `argo-workflows-backend`: delete `import fetch, { RequestInit } from 'node-fetch';`
      (`plugins/argo-workflows-backend/src/argoClient.ts:1`) so the `fetch` call at line 53 and the
      `RequestInit` annotation on `request<T>` (line 51) bind to the ambient globals — the same way
      `plugins/custom-domains-backend/src/mctlApiClient.ts:159,163` already does. Remove
      `"node-fetch"` from `dependencies` and `"@types/node-fetch"` from `devDependencies` in
      `plugins/argo-workflows-backend/package.json`.
      — DoD: no `node-fetch` string remains anywhere in the plugin; `submitWorkflow`, `getWorkflow`,
      `getWorkflowNodes` are otherwise byte-identical; `yarn tsc --noEmit` clean for this package.

- [ ] 2. `proposals-backend`: delete `import fetch from 'node-fetch';`
      (`plugins/proposals-backend/src/gitops-client.ts:1`); the three call sites (lines 130, 146,
      315) are unchanged. Remove both manifest entries from
      `plugins/proposals-backend/package.json`.
      — DoD: diff for this plugin is exactly one deleted import line plus two manifest lines;
      `gitops-client.test.ts` (which only tests `parseStatusYaml`) still passes untouched.

- [ ] 3. `tenant-backend`: delete `import fetch from 'node-fetch';` from
      `plugins/tenant-backend/src/tenantSync.ts:1` (calls at 80, 137) and
      `plugins/tenant-backend/src/githubAppToken.ts:2` (call at 24), and update the stale doc
      comment at `githubAppToken.ts:6` ("Uses only Node.js built-in crypto and node-fetch") to name
      the Node 22 global `fetch`. Remove both manifest entries from
      `plugins/tenant-backend/package.json`. This aligns these two files with
      `plugins/tenant-backend/src/router.ts:217`, which already uses global `fetch`.
      — DoD: no `node-fetch` string in the plugin; `plugins/tenant-backend/src/router.test.ts` (which
      drives a real server with global `fetch`, lines 88-215) passes unchanged — it installs no fetch
      spy, so it must not need one.

- [ ] 4. `vault-secrets-backend` source: delete `import fetch from 'node-fetch';` from
      `src/vaultAuth.ts:1` (login call at line 92) and `src/router.ts:2` (call at line 413 inside
      `vaultFetch`). Leave `vaultFetch`'s structural return type
      (`Promise<{ status: number; ok: boolean; json: () => Promise<any> }>`, router.ts:411) as is —
      a global `Response` satisfies it. Remove both manifest entries from
      `plugins/vault-secrets-backend/package.json`.
      — DoD: no `node-fetch` string in `src/*.ts` (non-test); no signature changes.

- [ ] 5. `vault-secrets-backend` tests (depends on 4) — the only file where the spy would collide
      with real HTTP:
      - `src/vaultAuth.test.ts`: replace lines 1/4/6 (`import fetch from 'node-fetch'`,
        `jest.mock('node-fetch', () => jest.fn())`, `const fetchMock = fetch as unknown as jest.Mock`)
        with the `#121` pattern from `plugins/custom-domains-backend/src/mctlApiClient.test.ts:6-14`:
        `let fetchMock: jest.SpyInstance;` + `beforeEach(() => { fetchMock = jest.spyOn(globalThis, 'fetch'); })`
        + `afterEach(() => fetchMock.mockRestore())`. Keep the existing
        `beforeEach(() => fetchMock.mockReset())` (line 19) and all ~25 assertions unchanged.
      - `src/router.test.ts`: same header replacement (lines 5/21/23), **plus** add at module scope,
        above any spy, `const realFetch: typeof globalThis.fetch = globalThis.fetch.bind(globalThis);`
        with a comment explaining why, and rewrite the route-driving calls at lines 404, 414, 423,
        433, 444, 453, 468, 480, 491, 502 from `globalThis.fetch(...)` to `realFetch(...)`. Update
        the block comment at lines 319-323 to describe the new arrangement.
      — DoD: `yarn test plugins/vault-secrets-backend` fully green; `mockVaultKV` and the
      `ok`/`denied` helpers and every assertion (especially
      `expect(fetchMock).not.toHaveBeenCalled()` at 474, 484, 496) are unchanged in text and still
      mean "no Vault request was issued".

- [ ] 6. `github-app-connect-backend` source: delete `import fetch from 'node-fetch';` from
      `src/router.ts:6` (calls at 203, 228, 274, 595, 737, 849, 857, 875, 932) and `src/plugin.ts:8`
      (calls at 69, 86). If `yarn tsc --noEmit` reports `unknown` at the two uncast reads —
      `plugin.ts:73` `const items = await resp.json();` and `plugin.ts:101` `return resp.json();` —
      add a local cast there only; do not change `RouterOptions.catalogClient`/`.scaffolderClient`
      (`router.ts:38-39`, already `(request: any) => Promise<any>`). Remove both manifest entries
      from `plugins/github-app-connect-backend/package.json`. This also aligns the package with
      `src/githubDiscoveryProcessorModule.ts:66,81,101`, which already uses global `fetch`.
      — DoD: no `node-fetch` string in the plugin's non-test sources; every other call site
      unchanged.

- [ ] 7. `github-app-connect-backend` tests (depends on 6): in `src/router.auth.test.ts`, replace
      lines 4/7/9 with the same `jest.spyOn(globalThis, 'fetch')` pattern, declaring the spy in a
      `beforeEach` that runs before the existing one at lines 186-189 (which does
      `fetchMock.mockReset()` then `fetchMock.mockImplementation(async (url: string) => githubFetchStub(url))`).
      No real HTTP is involved here — `dispatch()` (lines 132-136) drives the Express `Router`
      in-process — so no `realFetch` capture is needed.
      — DoD: `githubFetchStub` and every auth/authz assertion unchanged; the whole file passes.

- [ ] 8. Regenerate the lockfile (depends on 1-7): run `yarn install` at the repo root and commit
      the resulting `yarn.lock`. Expect the five workspace entries (around `yarn.lock:5402, 5435,
      5483, 5517, 5535`) to lose their `node-fetch`/`@types/node-fetch` lines; expect `node-fetch`
      itself to remain in the lock as a transitive dependency of upstream packages — that is correct,
      not a missed step.
      — DoD: `yarn install --immutable` succeeds from a clean checkout (this is CI's first step,
      `.github/workflows/validate.yml:26`).

- [ ] 9. Full verification sweep (depends on 8): `yarn tsc --noEmit`, `yarn build:backend --config
      ../../app-config.yaml`, `yarn test`, and a final
      `grep -rn "node-fetch" plugins/ packages/` returning nothing outside `yarn.lock`.
      — DoD: all four clean. Note CI runs only install + tsc + build, so `yarn test` here is the
      only test gate this change gets.

## Tests

- [ ] T1. `plugins/vault-secrets-backend/src/vaultAuth.test.ts` passes unchanged apart from the mock
      header: login, custom auth mount path, token caching, JWT re-read on rotation, renewal-failure
      fallback, and the invalidate/re-login cases all still exercise the same stubbed responses via
      the global-fetch spy.
- [ ] T2. `plugins/vault-secrets-backend/src/router.test.ts` route tests (masked vs. reveal, viewer
      vs. developer 403s) still reach a real Express server over `realFetch`, and the Vault spy still
      returns the `mockVaultKV` stub — i.e. no test starts hitting a real network and none is
      silently short-circuited by the spy.
- [ ] T3. In that same file, the three `expect(fetchMock).not.toHaveBeenCalled()` assertions (lines
      474, 484, 496) still fail if the guard they protect is removed. Verify manually once during
      implementation by temporarily inverting one assertion — a spy that also captured the
      route-driving calls would make these vacuously wrong.
- [ ] T4. `plugins/github-app-connect-backend/src/router.auth.test.ts` passes unchanged: anonymous
      requests still 401/403, member/admin requests still reach `githubFetchStub`-backed 200s, and
      `fetchMock.mock.calls` still records the GitHub URLs those routes request.
- [ ] T5. `plugins/tenant-backend/src/router.test.ts` and
      `plugins/custom-domains-backend/src/router.test.ts` — both drive real local servers with global
      `fetch` and must remain untouched and green, proving no cross-file spy leakage was introduced.
- [ ] T6. `yarn tsc --noEmit` is the regression gate for the ambient-typing question
      (`RequestInit` in `argoClient.ts`, `Response.json()` in `plugin.ts`). No new `@ts-expect-error`
      or `any` widening beyond the two localized casts allowed in task 6.
- [ ] T7. No new tests are added for `tenantSync.ts`, `githubAppToken.ts`, or `gitops-client.ts`'s
      HTTP paths (out of scope); instead the reviewer confirms their diffs are import-line-only.

## Rollback

Single self-contained PR touching only `plugins/*/src/*.ts`, five `plugins/*/package.json`, and
`yarn.lock` — no config, schema, GitOps, or infrastructure change, so `git revert <merge-commit>`
followed by `yarn install` fully restores the previous state; the reverted image redeploys through
the normal release-please/ArgoCD path with no manual cleanup.

If a single plugin misbehaves in production after merge (most plausible symptom: a request that
used to hang now rejects on undici's ~300s default timeout, or an upstream call fails in an
environment-specific way), revert just that plugin by restoring its `import fetch from 'node-fetch'`
line and its two `package.json` entries and re-running `yarn install` — each plugin's change is
independent, and node-fetch@2 will still be resolvable from `yarn.lock` as a transitive dependency.
Test-only regressions need no production action since CI does not gate on tests; fix forward in the
affected test file.
