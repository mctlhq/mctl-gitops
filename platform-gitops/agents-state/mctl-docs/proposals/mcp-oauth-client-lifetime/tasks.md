# Tasks: mcp-oauth-client-lifetime

- [ ] 1. Update `docs/mcp/connecting.md` with the "Token Lifetime & Client
        Registration" subsection from `proposed-content.md`. — DoD: file
        updated, `vitepress build docs` is green.
- [ ] 2. Update `docs/reference/troubleshooting.md` with the new
        "429 Too Many Requests on `/oauth/register`" entry and the
        expired-token note from `proposed-content.md`. — DoD: file
        updated, builds clean.
- [ ] 3. No `.vitepress/config.{js,ts}` change needed — both pages already
        exist and are in the nav. — DoD: n/a, skip.
- [ ] 4. Run `npm run dev` locally and open `/mcp/connecting` and
        `/reference/troubleshooting`. — DoD: both sections render, the
        cross-links between them resolve.
- [ ] 5. Cross-link: `docs/mcp/tools-reference.md`'s `mctl_whoami` /
        connection-related rows — check whether a short pointer to the
        new subsection is warranted. — DoD: added only if it reads
        naturally.
- [ ] 6. Open a PR against `mctlhq/mctl-docs`, request a `@claude review`,
        merge. — DoD: deployed to docs.mctl.ai.

## Tests
- [ ] T1. `vitepress build docs` with no errors and no warnings.
- [ ] T2. Every link in both changed pages resolves (no 404s), including
        the new cross-link from troubleshooting.md back to connecting.md.
- [ ] T3. The rate-limit number (30/min/IP) and TTL (24h) match the
        current source (`internal/api/router.go`, `cmd/api/main.go` in
        `mctl-api`) at merge time — re-verify against the repo before
        merging in case the values changed again between proposal and
        implementation.

## Rollback
- Revert the two file changes via a revert PR. Low risk — markdown only.
