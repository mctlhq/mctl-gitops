# Tasks: auth-token-overhaul

## Implementation tasks

- [ ] 1. Read the current `docs/security/authentication.md` in `mctlhq/mctl-docs`
        and identify every occurrence of "1 hour", "1h", or similar TTL language.
        Apply the UPDATE diff from `proposed-content.md` (access token TTL section).
        — DoD: file saved, no reference to 1-hour TTL remains.

- [ ] 2. Add the refresh token persistence paragraph from `proposed-content.md`
        into the refresh token section of `docs/security/authentication.md`.
        — DoD: paragraph present, mentions Postgres backend and pod-restart
        resilience.

- [ ] 3. Add or rewrite the token revocation section in
        `docs/security/authentication.md` using the content from
        `proposed-content.md`. Include the curl example and the grace window note.
        — DoD: section present, curl example shows both `token` and `client_id`
        parameters.

- [ ] 4. Add the `invalid_grant` error shape reference block from
        `proposed-content.md` into `docs/security/authentication.md`.
        — DoD: block present, shows `error_description: "invalid or expired token"`.

- [ ] 5. Read the current `docs/mcp/connecting.md`. If it contains any reference
        to 1-hour token expiry or "re-connect every hour" troubleshooting advice,
        remove or correct it with a cross-link to `docs/security/authentication.md`.
        — DoD: no 1-hour TTL language in connecting.md.

- [ ] 6. (If needed) Update `.vitepress/config.{js,ts}` — sidebar / nav entry.
        No change is expected (page already in sidebar); verify and skip if not
        needed.
        — DoD: confirmed no sidebar change required.

- [ ] 7. Run `npm run dev` locally and open `docs/security/authentication.md`.
        — DoD: page renders, mermaid sequence diagram renders (if included),
        all internal links resolve.

- [ ] 8. Cross-link check: confirm `docs/mcp/connecting.md` links to
        `docs/security/authentication.md` for token lifetime details. Add link if
        absent.
        — DoD: cross-reference in place.

- [ ] 9. Open a PR against `mctlhq/mctl-docs`, run code review, merge.
        — DoD: changes deployed to docs.mctl.ai.

## Tests

- [ ] T1. `vitepress build docs` completes with no errors and no warnings.
- [ ] T2. Every internal link in `docs/security/authentication.md` and
          `docs/mcp/connecting.md` resolves (no 404s). Use `vitepress build`
          dead-link checker or a local `linkchecker` run.
- [ ] T3. The curl example in the revocation section is hand-tested against a
          staging instance of `mctl-api` (or confirmed by the commit author of
          `5b166aa` if staging is unavailable).
          — Confirm: `POST /oauth/revoke` with `token=<value>&client_id=<id>`
          returns HTTP 200 with empty body (RFC 7009 §2.2).
- [ ] T4. The mermaid sequence diagram (if included) renders without console
          errors in the local dev server.

## Rollback

Revert the PR. Changes are markdown only — no build artifacts. Low risk.
