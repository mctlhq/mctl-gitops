# Chef review amendments for issue #1033

These amendments are normative for proposal approval. Where they conflict with `requirements.md`, `design.md`, or `tasks.md`, these amendments win until the proposal documents are folded together.

## A1. Centralization architecture

Do **not** implement a reusable workflow that mints an App token and returns it to the caller as a workflow output. The target architecture is **central privileged execution**:

- the central reusable workflow owns `AGENTS_APP_PRIVATE_KEY`;
- it mints the App token inside the privileged job;
- it performs the privileged action itself (release-please, dispatch, gitops bump, etc.);
- it never returns the App token to the caller;
- caller inputs are non-secret and narrowly typed;
- the target repository is derived from trusted execution context where possible, not accepted as an arbitrary caller-controlled repository string;
- cross-repo cases such as `release-drift` must be explicitly designed and allowlisted, not generalized into a caller-supplied arbitrary repository/permission broker.

The current design text describing “caller-supplied repositories/permissions and token as output” is rejected.

## A2. Known consumer inventory

The proposal must not treat the consumer set as only the four repos listed in the original issue. A prior org-wide code search already found 16 references total (1 runbook + 15 workflow files) and 11 repositories with direct workflow consumers:

- `mctl-gitops`
- `mctl-design`
- `mctl-api`
- `mctl-web`
- `mctl-agents`
- `mctl-telegram`
- `mctl-docs`
- `mctl-portal`
- `mctl-academy`
- `mctl-agent`
- `pfeifenpatenschaft-backend`

The implementation/runbook must use this as the current known baseline and re-verify it before any `selected repositories` change. Unknown/new consumers may be added only by explicit review.

## A3. Ratchet

Add a repository/org-level ratchet so a new direct reference to `AGENTS_APP_PRIVATE_KEY` outside the approved allowlist fails CI or an equivalent policy check. The goal is to make the current consumer reduction durable rather than convention-only.

The ratchet must be fail-closed for search/API failure: inability to complete the inventory check must not be interpreted as zero consumers.

## A4. Closure gate for #1033

The implementation PR produced from this proposal may harden the in-repo token scopes and add documentation, but **must not close #1033 by itself**.

#1033 may be closed only after all of the following are true:

1. `AGENTS_APP_ID` / `AGENTS_APP_PRIVATE_KEY` visibility is no longer `ALL` and is restricted to the verified selected repository set as the immediate mitigation;
2. the known consumer inventory has been re-verified after the visibility change and smoke-tested;
3. the central privileged execution migration is either completed so edge repositories no longer read the raw key, or an explicit security exception is accepted and tracked with owner + expiry/review date;
4. the direct-reference ratchet is active.

Per-call-site permission scoping in `mctl-gitops` is a useful partial mitigation, not the closure condition for the security issue.

## A5. Existing useful implementation scope remains

The following parts of the existing proposal remain valid and should proceed:

- add `permission-contents: write` to the `mctl-gitops` `gitops-bump` and `release-deploy` App-token call sites;
- keep `release-drift` as a deliberately cross-repo, read-only special case;
- add the durable runbook and cross-links;
- retain the proposed post-merge smoke tests;
- keep App installation `repository_selection` as a separate lever unless the implementation discovers it is required for the closure gate above.
