# Tasks: issue-73-request-media-refused-through-the-cloudf

- [ ] 1. Declare the documented default in `src/auth/config.ts`, immediately
      after `SUPPORTED_SCOPES` (`:17`): `export const DEFAULT_SCOPES = [SCOPE_READ, SCOPE_REQUEST] as const;`
      with a comment naming RFC 6749 §3.3 and stating why `offline_access` is
      excluded (a refresh token is issued regardless, and returning an
      unrequested scope makes clients warn the user).
      — DoD: constant exported, `npm run typecheck` clean, no behaviour change
      yet.
- [ ] 2. Apply the default in `src/auth/routes.ts:330` (depends on 1): replace
      `const requested = (params.scope ?? SCOPE_READ).split(/\s+/).filter(Boolean);`
      with a split of the named scopes followed by a fallback to
      `[...DEFAULT_SCOPES]` when nothing was named, so that an absent `scope`
      and a present-but-empty `scope` take the same branch. Update the import
      at `:6` to bring in `DEFAULT_SCOPES` and drop `SCOPE_OFFLINE` (imported
      and unused today) plus `SCOPE_READ` if it becomes unreferenced.
      — DoD: a no-scope authorize persists `"seerr:read seerr:request"` on the
      pending authorization; the `invalid_scope` check at `:331` still runs
      against explicitly named scopes; `npm run typecheck` clean.
- [ ] 3. Extend the test helpers in `tests/oauth.test.ts` (depends on 2) so
      `getAuthorizationCode` and `runFlow` can send an authorize request with
      no `scope` query parameter at all — today `:126` always sets one, so the
      failing request cannot be expressed. Suggested shape: `scope: null` means
      "omit the parameter"; `undefined` keeps the current default.
      — DoD: helper omits `scope` when asked, every existing test in the file
      still passes unchanged.
- [ ] 4. Add the regression tests T1-T5 below (depends on 3).
      — DoD: T1 fails on the current `main` (it reports
      `this token is not granted the seerr:request scope`) and passes with
      tasks 1-2 applied; the whole suite is green.
- [ ] 5. Document the default in `README.md` Security Model (depends on 2),
      in the scopes bullet at `:405-408`: an authorize request naming no scope
      is granted `seerr:read seerr:request` as the RFC 6749 §3.3 documented
      default, a client that names scopes gets exactly those, `offline_access`
      is never added implicitly, and a grant issued before this change keeps
      its old scope across refreshes until the client re-authorizes.
      — DoD: bullet reads correctly in context, no other README claim
      contradicted (check the MCP section at `:184-192`).
- [ ] 6. Open the PR with the four files touched (`src/auth/config.ts`,
      `src/auth/routes.ts`, `tests/oauth.test.ts`, `README.md`) and reference
      issue #73 and the draft reference implementation in #72 (depends on 1-5).
      — DoD: CI green — `npm run check:tokens`, `npm run typecheck`, `npm test`
      (against the Postgres service container) and the Docker build all pass.
- [ ] 7. After deploy, re-authorize the portal's `seerrsense` upstream once —
      sign the upstream out and back in so a fresh authorization mints a token
      with the new default — then run the repro from the issue: ask for
      Ratatouille (2007, TMDB 2062) through the portal and confirm
      `request_media` files the request (depends on 6).
      — DoD: `seerrsense_whoami` still reports the session as connected
      (`source: household`), and the request succeeds instead of answering
      `this token is not granted the seerr:request scope`. Record the result on
      issue #73.

## Tests

- [ ] T1. No-scope authorize yields a request-capable token: drive the flow
      with the `scope` parameter omitted, assert the token response's `scope`
      is exactly `"seerr:read seerr:request"`, then call `request_media`
      (`mediaType: "movie"`) over `/mcp` with that access token and assert the
      payload does not contain `not granted`. This is the case that must fail
      on the current `main`.
- [ ] T2. Named scopes are honoured exactly: an authorize with
      `scope=seerr:read` still produces a read-only token — `/api/v1/search`
      succeeds and `request_media` answers `seerr:request` — i.e. the existing
      case at `tests/oauth.test.ts:1125` keeps passing unchanged. Add the
      companion assertion that its token response `scope` is exactly
      `"seerr:read"`, so the default cannot leak into a named request.
- [ ] T3. Consent page for a no-scope authorize lists every granted scope:
      render `/oauth/google/callback` for an authorize that sent no `scope` and
      assert the HTML contains both "Search your media library" and "Request
      new films" (the `SCOPE_LABELS` strings at `src/auth/routes.ts:78-82`).
- [ ] T4. An explicitly empty or whitespace-only `scope=` is treated as naming
      nothing and gets the same default, rather than producing a zero-scope
      token that the `/mcp` read gate would refuse with 403 `insufficient_scope`.
- [ ] T5. Unchanged neighbours: an unknown scope still redirects with
      `error=invalid_scope`; `scope=seerr:read offline_access` still returns
      exactly that string (`tests/oauth.test.ts:923`); a refresh of a
      `seerr:read`-only grant still returns `seerr:read` and does not widen to
      the new default. Add a cheap assertion that every member of
      `DEFAULT_SCOPES` appears in `SUPPORTED_SCOPES`, so the default cannot
      drift into an `invalid_scope` redirect.

## Rollback

The change is two source lines plus documentation, with no schema or config
change, so rollback is a revert: `git revert` the merge commit and redeploy the
previous image tag. Tokens already minted under the new default keep working —
they are ordinary grants carrying `seerr:read seerr:request`, and the refresh
path reissues whatever scope the grant holds — so a revert narrows only
*future* authorizations back to `seerr:read`. Nothing needs to be re-issued or
migrated, and the portal's upstream would simply return to the behaviour
described in issue #73 until re-authorized after a subsequent fix. If instead
the wider default proves unwanted for one specific client, that client can pin
itself back to read-only by naming `scope=seerr:read` on its authorize request,
with no server change at all.
