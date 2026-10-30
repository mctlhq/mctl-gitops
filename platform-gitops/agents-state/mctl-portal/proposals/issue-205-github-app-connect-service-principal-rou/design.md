# Design: issue-205-github-app-connect-service-principal-rou

## Current state

All code is in `plugins/github-app-connect-backend/src/router.ts` (`createRouter`).

- Validators at the top of the file: `REPO_FULL_NAME_RE`, `TEAM_OR_SERVICE_RE = /^[a-zA-Z0-9_-]+$/` and `GITHUB_LOGIN_RE`.
- `RouterOptions.bindingCheckSubject?: string` is documented as "Unset: the route refuses everyone". `plugin.ts` reads it from `githubAppConnect.bindingCheckSubject`.
- `resolveCallerUserId` calls `httpAuth.credentials(req, { allow: ['user'] })` and returns the `user:default/<id>` name, or `undefined` on any error. `requireTeamAccess` builds on it and adds `checkTeamAccess`, which applies the admin bypass and then tenant membership.
- `GET /install-url` (line ~452) requires `team`, `service` and `repo`, and validates `repo` with `REPO_FULL_NAME_RE` only. It calls `requireTeamAccess`, then `encryptState({ team, service, repo, user: auth.userId, nonce }, stateSecret)`, and answers `{ url, state }`.
- `GET /repo-binding` (line ~482) is the only service route. It calls `httpAuth.credentials(req, { allow: ['service'] })` and answers 401 on failure. The subject must equal `bindingCheckSubject` or `external:${bindingCheckSubject}`, otherwise 403 `Not allowed`, and an unset subject is always refused. It then validates `team` and `repo` (400) and calls `isRepoBoundToTeam`.
- `GET /repos` (line ~819) is user-only, through `resolveCallerUserId`. With a `team` it calls `checkTeamAccess` and then `store.findVerifiedByTeam(team)`. Without a team it is admin-only and uses `store.findAllVerified()`. It answers sorted, de-duplicated `repo_full_name` values, and 500 `{repos: []}` on error.
- `POST /repos/sync` (line ~863) validates `team` for presence only, plus `user` presence and `GITHUB_LOGIN_RE`. It calls `requireTeamAccess`, and `user` must equal the caller unless the caller is an admin. The body then:
  - for `team === 'admins'`, adds every Organization installation;
  - adds `findInstallation(user, ...)`;
  - does an early `findVerifiedByTeam` exit when there are no installations;
  - fetches the repos of each installation;
  - calls `store.replaceTeam(..., created_by: sync:${auth.userId.toLowerCase()})`;
  - answers `{repos}`, or 500 `{repos: []}` on error.
- `GET /callback` decodes the state, checks the installation against `user` from the state with `resolveBindableRepos`, and records `callback:<user>` / `popup:<user>`.
- `store.ts` `VERIFIED_CREATED_BY_PREFIXES = ['popup:', 'callback:', 'sync:', 'legacy:']`. Only rows with these prefixes are returned by `findVerifiedByTeam` and `isRepoBoundToTeam` (`bindingLookup.ts`).
- Tests: `router.auth.test.ts` has `fakeHttpAuth()`, which maps the `x-test-service` header to a service principal and `x-test-user` to a user principal, and honors `allow`. It also has `buildRouter(members, storeOverrides, optionOverrides)`, `dispatch()`, and a `describe('GET /repo-binding')` block whose cases are the model for the new tests.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/bootstrap/templates/mctl-platform/mctl-portal.yaml`: production app-config is rendered here; the repo's `app-config.production.yaml` is not used in production. When `repoBinding.enabled`, it adds an externalAccess static entry with token `${MCTL_API_REPO_BINDING_TOKEN}`, `subject: mctl-api-repo-binding` and `accessRestrictions: - plugin: github-app-connect`, and sets `githubAppConnect.bindingCheckSubject: mctl-api-repo-binding`.
- `$MCTL_GITOPS_ROOT/bootstrap/values.yaml`: `repoBinding.enabled: true`. So the principal and subject the new routes need are already deployed, and no gitops change is required.
- `$MCTL_GITOPS_ROOT/bootstrap/templates/mctl-platform/mctl-api-repo-binding.yaml` and `mctl-api.yaml`: mctl-api gets the same token, from Vault `platform/mctl-portal/repo-binding-token`, as `repoBindingTokenSecret`.
- `$MCTL_GITOPS_ROOT/agents-state/mctl-api/proposals/issue-584-.../design.md` (status `proposed`, not yet accepted in gitops; the issue calls the design accepted): part B calls `/service/repos?team=`, `/service/install-url?team&service&repo&user` and `POST /service/repos/sync?team&user`, with `user` being the caller's validated GitHub login.
- `$MCTL_GITOPS_ROOT/services/`: no mctl-portal service values there. The portal is a platform component under `bootstrap/`, not a tenant service. mctl MCP tools were not used: the gitops reads above answered the questions about deployed config.

## Proposed solution

All changes are in `plugins/github-app-connect-backend/src/router.ts` plus tests. No config, schema or frontend change.

### 1. Shared service-principal guard

Add this inside `createRouter`, so it closes over `httpAuth`, `bindingCheckSubject` and `logger`:

```ts
type BindingPrincipal = { ok: true; subject: string } | { ok: false; status: 401 | 403; error: string };

async function requireBindingPrincipal(req: Request): Promise<BindingPrincipal> {
  let subject: string | undefined;
  try {
    const credentials = await httpAuth.credentials(req, { allow: ['service'] });
    subject = (credentials.principal as { subject?: string }).subject;
  } catch {
    return { ok: false, status: 401, error: 'Authentication required' };
  }
  if (!bindingCheckSubject || !subject ||
      (subject !== bindingCheckSubject && subject !== `external:${bindingCheckSubject}`)) {
    return { ok: false, status: 403, error: 'Not allowed' };
  }
  return { ok: true, subject };
}
```

Refactor `/repo-binding` onto this helper. Its behavior does not change, and its existing tests are the regression guard. The guard runs before any parameter validation, as `/repo-binding` does today.

Add a small `auditServiceCall(route, subject, fields)` that logs `logger.info('github-app-connect service call', { audit: 'service_principal', route, subject, ...fields })`. It is called on every accepted `/service/*` request, after validation and before any work.

### 2. Extract the sync body

Move the body of `/repos/sync`, from `installMap` construction to the response, into a closure `syncTeamRepos(team: string, user: string, res: Response)` inside `createRouter`. It writes `created_by: sync:${user.toLowerCase()}`. In the user route, `auth.userId` and `user` are equal case-insensitively after the identity check, except under admin bypass. Under admin bypass today `created_by` uses the admin's id, so `/repos/sync` keeps passing `auth.userId` through a `createdByLogin` parameter: `syncTeamRepos(team, user, createdByLogin, res)`. The user route's behavior is byte-for-byte the same. The service route passes the asserted `user` for both.

The `sync:` prefix is kept on purpose, because `VERIFIED_CREATED_BY_PREFIXES` only treats those rows as verified bindings.

### 3. New routes

They are registered in `createRouter` next to `/repo-binding`. Each starts with `requireBindingPrincipal`.

- `GET /service/repos`: require `team` as a string matching `TEAM_OR_SERVICE_RE`, else 400 `Missing or invalid param: team`. Audit `{route, subject, team}`. Read `store.findVerifiedByTeam(team)` and answer `{ repos: [...new Set(rows.map(r => r.repo_full_name))].sort() }`. On error, answer 500 `{ repos: [] }`. There is no `findAllVerified` branch.
- `GET /service/install-url`: validate `team` and `service` with `TEAM_OR_SERVICE_RE`, `repo` with `REPO_FULL_NAME_RE` and `user` with `GITHUB_LOGIN_RE`, all as strings; any failure is 400. Audit `{route, subject, team, service, repo, user}`. Then `encryptState({ team, service, repo, user, nonce }, stateSecret)` and answer `{ url, state }`, built exactly like `/install-url`. `/callback` needs no change. It already trusts only the decrypted state and checks the installation against `user` with `resolveBindableRepos`, so asserting a login that does not own or cannot read the installation still records nothing.
- `POST /service/repos/sync`: validate `team` (`TEAM_OR_SERVICE_RE`) and `user` (`GITHUB_LOGIN_RE`), else 400. Audit `{route, subject, team, user}`. Call `syncTeamRepos(team, user, user, res)`.

Routes are mounted under the plugin base path, giving `/api/github-app-connect/service/...`, which is what part B calls. The plugin has no `addAuthPolicy` for these paths (`plugin.ts` only opens `/callback`, `/popup-done` and `/webhook`). The default policy therefore still requires a valid credential at the framework layer, and the guard narrows it to the single subject.

Path note: the existing user route `GET /service-config` is a different literal path (`/service-config`, not `/service/...`), so there is no Express route collision.

### Why this way

- It reuses the exact trust model already reviewed for `/repo-binding`: the same principal, the same subject check, and the same "mctl-api is the authority" stance. The externalAccess entry is already restricted to `github-app-connect`.
- The separate `/service/*` paths keep the UI routes' semantics unchanged, and make the trusted, asserted-identity surface explicit and greppable.
- Extracting the sync body avoids two copies of the transaction-sensitive replace logic.

## Alternatives

1. **Widen the existing routes to `allow: ['user', 'service']`.** `/install-url` and `/repos/sync` derive the user from the credential, so they would still need an "asserted user" branch keyed on the principal type. That mixes two trust models in one handler, and makes a regression that lets a service credential skip membership checks for UI callers easier to introduce. Dropped. The issue asks that user routes reject service credentials.
2. **Forward a Backstage user identity from mctl-api (token exchange or impersonation).** mctl-api users are not Backstage sessions, and this would need a new Backstage auth provider or impersonation capability, which is a much larger trust change. Dropped, as also concluded in the mctl-api#584 design.
3. **Duplicate the sync body into the new route instead of extracting it.** Simpler diff, but two copies of the `replaceTeam` / carried-row logic would drift. That logic has had several review rounds (see the CHANGELOG entry "atomic repo sync, bounded permission checks"). Dropped.

## Platform impact

- **Migrations:** none. There is no schema change. Rows keep existing `created_by` prefixes.
- **Config / gitops:** none. `bindingCheckSubject: mctl-api-repo-binding` and the externalAccess entry restricted to `github-app-connect` are already rendered with `repoBinding.enabled: true`.
- **Backward compatibility:** additive routes only. User routes and `/repo-binding` are unchanged in behavior. Until mctl-api part B ships, nothing calls the new routes. Part B must not ship before this is deployed, or its calls answer 404, which mctl-api surfaces as 502.
- **Resources:** negligible. The new routes do the same work, for the same callers, that the user routes already do.
- **Security risks and mitigations:**
  - The asserted `user` and `team` are trusted from mctl-api. Mitigations:
    - only one subject is accepted;
    - the token is plugin-restricted;
    - inputs are validated by regex;
    - `/callback` still checks the installation against `user` on GitHub before recording;
    - `/service/repos/sync` only lists the asserted login's personal installation, which GitHub owns.
  - Residual risk: a leaked `mctl-api-repo-binding` token now allows listing any team's repos and triggering syncs, not just binding lookups. Mitigations: a per-call audit log line with the subject; the token is stored only in Vault and the two pods. Rotating it is the existing Vault procedure.
  - No admin-bypass audit is emitted on these routes (`auditAdminBypass` is user-only). The `service_principal` audit line replaces it, and mctl-api audits the end user.
