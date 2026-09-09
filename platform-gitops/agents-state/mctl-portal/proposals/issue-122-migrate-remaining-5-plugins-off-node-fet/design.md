# Design: issue-122-migrate-remaining-5-plugins-off-node-fet

## Current state

### Runtime and toolchain

- `package.json` pins `engines.node: "22 || 24"`; `Dockerfile:2` builds on `node:22-bookworm-slim`.
  Global `fetch` (undici) is stable and always present.
- `.github/workflows/validate.yml` runs exactly three checks: `yarn install --immutable` (line 26),
  `yarn tsc --noEmit` (line 29), `yarn build:backend` (line 32). **CI does not run `yarn test`** —
  unit tests must be run locally by whoever implements this, and by review.
- `tsconfig.json` extends `@backstage/cli/config/tsconfig.json`. The ambient global
  `RequestInit` type already resolves in this repo: `plugins/custom-domains-backend/src/mctlApiClient.ts:159`
  declares `private async request<T>(path: string, options?: RequestInit)` with no import, and that
  file compiles on `main` today. Same for `AbortSignal.timeout` (line 169).

### The reference migration (`#121`)

`plugins/custom-domains-backend`:

- `src/mctlApiClient.ts` calls bare `fetch(url, {...})` (line 163) and uses ambient `RequestInit`.
- `package.json` has no `node-fetch` and no `@types/node-fetch`.
- `src/mctlApiClient.test.ts:6-14` is the mocking pattern to copy:

  ```ts
  let fetchMock: jest.SpyInstance;
  beforeEach(() => { fetchMock = jest.spyOn(globalThis, 'fetch'); });
  afterEach(() => { fetchMock.mockRestore(); });
  ```

  Note the deliberately loose `jest.SpyInstance` type: it lets the existing plain-object stubs
  (`fetchMock.mockResolvedValue({ ok: true, status: 200, text: async () => '...' })`, lines 100-104)
  keep working without wrapping every stub in `as unknown as Response`. Nested describes still do
  `beforeEach(() => fetchMock.mockReset())` (line 97) — outer `beforeEach` installs the spy, inner
  one resets its behavior, which is the ordering Jest guarantees.
- `src/router.test.ts` drives a real local Express server with the global `fetch` (lines 236+) and
  never installs a fetch spy in that file — the two concerns live in separate files there.

### What still uses node-fetch

Source files (8), all `import fetch from 'node-fetch'` unless noted:

| Plugin | File | fetch call sites |
| --- | --- | --- |
| argo-workflows-backend | `src/argoClient.ts:1` — `import fetch, { RequestInit } from 'node-fetch'` | `argoClient.ts:53` (single private `request<T>` helper, used by `submitWorkflow`, `getWorkflow`, `getWorkflowNodes`) |
| github-app-connect-backend | `src/router.ts:6` | lines 203, 228, 274, 595, 737, 849, 857, 875, 932 (GitHub App installation tokens, installation lookup, repo/tag/content reads) |
| github-app-connect-backend | `src/plugin.ts:8` | lines 69, 86 (catalog + scaffolder clients built on `discovery`/`auth`) |
| proposals-backend | `src/gitops-client.ts:1` | lines 130, 146, 315 (GitHub contents API read/write) |
| tenant-backend | `src/tenantSync.ts:1` | lines 80, 137 |
| tenant-backend | `src/githubAppToken.ts:2` (doc comment line 6 also names node-fetch) | line 24 |
| vault-secrets-backend | `src/vaultAuth.ts:1` | line 92 (Kubernetes auth login) |
| vault-secrets-backend | `src/router.ts:2` | line 413, inside `vaultFetch` |

Test files (3) mocking the module:

- `plugins/vault-secrets-backend/src/vaultAuth.test.ts:1,4,6` — `jest.mock('node-fetch', () => jest.fn())`,
  `const fetchMock = fetch as unknown as jest.Mock`, ~25 `fetchMock` assertions.
- `plugins/vault-secrets-backend/src/router.test.ts:5,21,23` — same idiom, **plus** it starts a real
  Express server (`app.listen(0)`, line 376) and drives it with `globalThis.fetch(...)` (lines 404,
  414, 423, 433, 444, 453, 468, 480, 491, 502). The comment at lines 319-323 spells this out: routes
  are driven "with the platform's own fetch (no supertest ...)" while "Vault responses come from the
  module-level node-fetch mock". Today the two drivers are physically distinct objects; after the
  migration they are the same function.
- `plugins/github-app-connect-backend/src/router.auth.test.ts:4,7,9,187-188` — same idiom, with
  `fetchMock.mockImplementation(async (url: string) => githubFetchStub(url))`. This file dispatches
  the Express `Router` in-process (`dispatch()`, lines 132-136 — "without spinning up a real HTTP
  server or pulling in supertest"), so it makes **no** real HTTP calls and has no spy collision.

Package manifests: each of the five declares `"node-fetch": "^2.7.0"` in `dependencies` and
`"@types/node-fetch": "^2.6.9"` in `devDependencies`. Corresponding workspace entries in
`yarn.lock` are around lines 5402, 5435, 5483, 5517, 5535.

### Already inconsistent today

- `plugins/tenant-backend/src/router.ts:217` calls global `fetch('https://api.github.com/users/...')`
  while `tenantSync.ts` and `githubAppToken.ts` in the same package use node-fetch.
- `plugins/github-app-connect-backend/src/githubDiscoveryProcessorModule.ts:66,81,101` calls global
  `fetch` against the GitHub API while `router.ts`/`plugin.ts` use node-fetch.

So this is not "introduce a new HTTP client"; it is "stop running two".

### What is NOT used from node-fetch

A repo-wide grep for node-fetch-only surface — `agent:`, `redirect:`, `compress`, `follow:`,
`size:`, `.buffer()`, `FetchError`, `new Request`, `Headers(` — returns no hits in these plugins.
Every call uses `{ method, headers, body }` only, and every response use is `ok`, `status`, `text()`,
`json()`. That is the exact intersection of node-fetch@2 and the WHATWG global, which is why this
migration is a pure import swap.

## Proposed solution

Five self-contained per-plugin changes, mechanically identical, plus one lockfile refresh. Nothing
is abstracted, wrapped, or centralized — introducing a shared HTTP helper would be a behavioral and
architectural change the issue explicitly excludes.

### 1. Source edits

For each of the 8 source files: delete the `import ... from 'node-fetch'` line. Every `fetch(...)`
call then resolves to the ambient global with zero call-site edits, because none of the call sites
use node-fetch-only options.

Two files need one extra touch:

- `plugins/argo-workflows-backend/src/argoClient.ts` imports the *type* `RequestInit` from
  node-fetch (line 1) and uses it at line 51. Drop the whole import; the ambient global
  `RequestInit` takes over, matching what `custom-domains-backend/src/mctlApiClient.ts:159` already
  does. `request<T>`'s existing body — `...options`, `headers: { ...this.headers(), ...(options?.headers as Record<string, string> || {}) }`,
  `resp.json() as Promise<T>` — is valid against the global types unchanged (`Promise<unknown>`
  asserts to `Promise<T>` fine, since `Promise<T>` is assignable to `Promise<unknown>`).
- `plugins/tenant-backend/src/githubAppToken.ts:6` has a doc comment saying "Uses only Node.js
  built-in crypto and node-fetch (no extra deps)". Update it to name the global `fetch`, so the
  comment does not outlive the dependency.

`plugins/vault-secrets-backend/src/router.ts`'s `vaultFetch` (lines 406-431) declares its return
type structurally — `Promise<{ status: number; ok: boolean; json: () => Promise<any> }>` — not as
node-fetch's `Response`. A global `Response` satisfies that shape, and so do the test's plain-object
stubs. No signature change needed.

Only two response reads in the whole set are uncast: `github-app-connect-backend/src/plugin.ts:73`
(`const items = await resp.json();`) and `:101` (`return resp.json();`). If the ambient
`Response.json()` types as `unknown` here, add a local cast (`as unknown[]` / `as any`) at those two
lines. Both values flow into `RouterOptions.catalogClient` / `.scaffolderClient`, declared as
`(request: any) => Promise<any>` at `github-app-connect-backend/src/router.ts:38-39`, so a cast is
contained and changes no consumer type.

### 2. Test edits

`vaultAuth.test.ts` and `router.auth.test.ts` — replace the three-line module-mock header with the
`#121` pattern:

```ts
// before
import fetch from 'node-fetch';
jest.mock('node-fetch', () => jest.fn());
const fetchMock = fetch as unknown as jest.Mock;

// after
let fetchMock: jest.SpyInstance;
beforeEach(() => { fetchMock = jest.spyOn(globalThis, 'fetch'); });
afterEach(() => { fetchMock.mockRestore(); });
```

Every existing `fetchMock.mockResolvedValue(...)` / `.mockImplementation(...)` / assertion stays
byte-identical: `jest.SpyInstance` is loosely typed, so the plain-object response stubs
(`vaultAuth.test.ts`'s `loginOk`, `router.auth.test.ts`'s `githubFetchStub`) need no `as unknown as
Response` wrapping. Existing `fetchMock.mockReset()` calls in `beforeEach` hooks stay — they must
run *after* the spy is installed, which they do (outer `beforeEach` first). `router.auth.test.ts`'s
existing `beforeEach` at lines 186-189 already resets and re-installs `mockImplementation`, so it
just needs to run after the spy exists — put the spy installation in a `beforeEach` declared above
it in the same file scope.

`vault-secrets-backend/src/router.test.ts` — the one file with a real collision. It must keep
stubbing Vault while genuinely talking HTTP to `127.0.0.1`. Fix by capturing the real global at
module load, before any spy exists:

```ts
// Captured before any jest.spyOn replaces globalThis.fetch: the route tests
// below drive a real local server over HTTP, and must not be intercepted by
// the spy that stubs Vault. Keeping them separate also preserves the meaning
// of `expect(fetchMock).not.toHaveBeenCalled()` — "Vault was never called".
const realFetch: typeof globalThis.fetch = globalThis.fetch.bind(globalThis);
```

Then rewrite the ~10 server-driving `globalThis.fetch(...)` calls (lines 404, 414, 423, 433, 444,
453, 468, 480, 491, 502) to `realFetch(...)`, and install the Vault spy exactly as above. The Vault
stubs (`mockVaultKV`, lines 382-388; the `ok`/`denied` helpers used from line 519 on) and every
assertion — including the three `expect(fetchMock).not.toHaveBeenCalled()` checks at lines 474, 484,
496, which are the security-relevant "no secret was ever fetched" assertions — remain unchanged and
keep their exact original meaning. Update the block comment at lines 319-323 to say the Vault
responses come from a `globalThis.fetch` spy and that the route calls use the captured real fetch.

### 3. Manifests and lockfile

Remove `"node-fetch": "^2.7.0"` from `dependencies` and `"@types/node-fetch": "^2.6.9"` from
`devDependencies` in all five plugin `package.json` files (each keeps `@backstage/cli` in
`devDependencies`, so no manifest ends up with an empty block). Then run `yarn install` to
regenerate `yarn.lock`, because CI's first step is `yarn install --immutable` and would otherwise
fail on a manifest/lock mismatch. `node-fetch` remains in the lock as a transitive dependency of
upstream packages — that is expected and not a regression.

### Why this shape

- **Per-plugin, no shared abstraction.** The issue scopes this to a driver swap. A shared
  `httpClient` package would change error surfaces, add a workspace dependency edge, and make the
  diff un-reviewable against "behavior identical".
- **Delete the import, touch nothing else.** Since no call site uses node-fetch-only options, the
  minimal diff is also the correct one, and review can be a mechanical check that only import lines
  and mock headers changed.
- **Capture-the-real-fetch instead of a passthrough spy** in `vault router.test.ts`: a spy that
  forwards `127.0.0.1` traffic to the real implementation would silently break the
  `not.toHaveBeenCalled()` assertions (the driving call itself would register on the spy), turning
  three security assertions into no-ops. Capturing keeps the counts honest.

## Alternatives

1. **One shared `fetch` wrapper package for all backend plugins** (e.g. `@internal/http`, with
   timeouts and error mapping like `custom-domains-backend`'s `MctlApiError`/`AbortSignal.timeout`).
   Rejected: it is a behavior change (new timeouts, new error types) across five plugins in a PR
   whose stated contract is "no behavioral change", and it would need per-caller error-handling
   review at ~19 call sites. Worth a separate issue if the platform ever wants uniform timeouts.

2. **Keep `import fetch from 'node-fetch'` and alias the global**
   (`const fetch = globalThis.fetch;` at the top of each file). Rejected: it keeps a shadowing local
   binding and gains nothing over deleting the import — the whole point is fewer moving parts. It
   also leaves the "why is there a local named fetch?" question for every future reader.

3. **Migrate only the plugins whose tests already mock node-fetch** (vault-secrets,
   github-app-connect) and defer the rest. Rejected: `argo-workflows-backend`, `proposals-backend`,
   and `tenant-backend` are the *cheapest* three (no test rewiring at all — delete an import line
   and two manifest entries), so deferring them keeps the dependency and the split-driver problem
   alive for no saving.

4. **Add `undici` as an explicit dependency and import `fetch` from it.** Rejected: Node 22 already
   ships it as a global; an explicit dependency would re-create exactly the redundant-dependency
   problem this issue exists to remove, and risks a second undici version in the tree.

## Platform impact

- **Migrations / data:** none. No schema, config, or GitOps change. No `app-config*.yaml` change.
- **Backward compatibility:** no public API of any plugin changes.
  `ArgoWorkflowsClient.request`'s `options` parameter changes nominal type from node-fetch's
  `RequestInit` to the global `RequestInit`; it is private and its only callers are in the same
  file. `vaultFetch`'s exported signature is structural and unchanged.
- **Runtime behavior:** requests move from node-fetch@2's `http.request` stack to undici. Same URLs,
  methods, headers, bodies, and status handling. Differences worth naming:
  - undici applies default `headersTimeout`/`bodyTimeout` (~300s); node-fetch@2 had none. A request
    that previously hung indefinitely against a dead upstream now rejects. Net improvement; recorded
    as an open question in `requirements.md` in case a reviewer wants it compensated for.
  - Network errors reject with `TypeError` (cause-wrapped) rather than node-fetch's `FetchError`.
    Nothing in these plugins branches on the error class — every handler uses `err.message` or a
    generic `catch` — so no code path changes.
  - Connection pooling is undici's global agent, shared with the code that already uses global
    `fetch` (`tenant-backend/src/router.ts`, `githubDiscoveryProcessorModule.ts`,
    `custom-domains-backend`). Two pools become one; expect marginally fewer sockets, not more.
  - No proxy env vars are configured in `Dockerfile` or `app-config.production.yaml`, so no
    proxy-behavior difference between the two drivers applies here.
- **Resource impact:** slightly smaller `node_modules` and image; no runtime CPU/memory change of
  note.
- **Risks and mitigations:**
  - *Risk:* the `vault-secrets-backend/src/router.test.ts` spy swallows the route-driving HTTP calls,
    making route tests fail confusingly or — worse — pass vacuously.
    *Mitigation:* the captured-`realFetch` design above; verify by running that file and confirming
    all cases still pass and the `not.toHaveBeenCalled()` cases still fail if the assertion is
    deliberately inverted during review.
  - *Risk:* `Response.json()` typing as `unknown` breaks `yarn tsc --noEmit` at the two uncast sites.
    *Mitigation:* known, localized, and covered by a task; CI's type-check gate catches it before
    merge regardless.
  - *Risk:* forgetting to regenerate `yarn.lock` fails CI at `yarn install --immutable`.
    *Mitigation:* explicit task and DoD.
  - *Risk:* an untested HTTP path regresses silently (`tenantSync.ts`, `githubAppToken.ts`,
    `gitops-client.ts` have no HTTP-level tests, and CI does not run tests at all).
    *Mitigation:* diffs in those files are import-line-only; reviewer should confirm the diff for
    those three files contains no other change. `yarn build:backend` still validates plugin wiring.
  - *Rollback:* trivially revertible single PR (see `tasks.md`).
