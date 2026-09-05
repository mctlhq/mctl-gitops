# Tasks: dev-loop-describe-endpoint

- [ ] 1. Update `docs/api/index.md` with the content from `proposed-content.md`.
        — DoD: entry present, `vitepress build docs` is green.
- [ ] 2. Confirm the exact HTTP method, path, and response field names for the
        `describe` endpoint against `mctl-api` source (commit `d6aca27`) and replace
        the `<TODO: confirm with author of d6aca27>` markers in `proposed-content.md`.
        — DoD: no TODO markers remain in the published entry.
- [ ] 3. Run `npm run dev` locally and open the page. — DoD: it renders, the new entry
        is visible, links work.
- [ ] 4. Cross-link: add a pointer from the "Approving agent proposals" section
        (proposed in `platform-operations-approval-flow/proposed-content.md`) to this
        endpoint, since checking workflow liveness informs which approval path to use.
        — DoD: cross-reference in place (coordinate with that proposal if implemented
        separately).
- [ ] 5. Open a PR against `mctlhq/mctl-docs`, request a `@claude review`, merge.
        — DoD: deployed to docs.mctl.ai.

## Tests

- [ ] T1. `vitepress build docs` with no errors and no warnings.
- [ ] T2. Every link in the changed page resolves (no 404s).
- [ ] T3. The `curl` example has been hand-checked against a live call (or flagged as
        unverified if the exact path/method cannot be confirmed before merge) —
        response should parse cleanly with `jq .`.

## Rollback

- Delete the added entry via a revert PR. Low risk — markdown only.
