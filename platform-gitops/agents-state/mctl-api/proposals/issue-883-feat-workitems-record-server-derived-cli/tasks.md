# Tasks: issue-883-feat-workitems-record-server-derived-cli

- [ ] 1. Mint the claim: add `ClientID` (`json:"client_id,omitempty"`) to
  `jwtPayload` in `internal/auth/oauth_server.go`. Thread a `clientID`
  argument through `issueJWTFor`, from the code exchange (`entry.ClientID`)
  and both refresh paths (the client id already matched against the stored
  session). `IssueJWT` and the support mint pass `""`. Bound the value
  (<= 512 bytes, no control characters) and omit it when out of bounds. —
  DoD: tokens from the code and refresh grants decode with `client_id` equal
  to the authenticated client, and existing auth tests pass.
- [ ] 2. Verify the claim (depends on 1): add the unexported
  `oauthClientID` field and an `OAuthClientID()` accessor to `auth.User`
  (`internal/auth/oidc.go`). Set the field only in `ValidateJWT` from the
  verified payload, applying the same bound check. — DoD: no other
  constructor sets the field; grep shows no authz code reading it.
- [ ] 3. Mutation (depends on 2): add `ActorClientID` to
  `workitems.Mutation` (`internal/workitems/inputs.go`), and set it in
  `mutationFor` (`internal/api/handlers_work_items.go`) from
  `user.OAuthClientID()`. Keep it out of `RequestHash`. — DoD: it compiles,
  and existing idempotency tests are unchanged.
- [ ] 4. Schema and store (depends on 3): add the
  `work_item_intents.actor_client_id`, `work_items.origin_client_id` and
  `work_item_events.actor_client_id` columns (`ADD COLUMN IF NOT EXISTS ...
  NOT NULL DEFAULT ''`) in `internal/workitems/store.go`. Write them in
  `AppendIntent`, `Create` and `appendEvent`. Read them in `getIntent`,
  `Intents`, `Intent`, `itemColumns`/`scanItem` and the events read. — DoD:
  store tests round-trip the values, and legacy rows read `""`.
- [ ] 5. Types (depends on 4): add `Intent.ActorClientID`
  (`actor_client_id`), `WorkItem.OriginClientID` (`origin_client_id`) and
  `Event.ActorClientID` (`actor_client_id`) to
  `internal/workitems/types.go`, without `omitempty`. — DoD: the JSON
  responses of create, append, list intents, get intent, get item and events
  include the keys.
- [ ] 6. Refuse input (depends on 3): add `actor_client_id`,
  `origin_client_id` and `client_id` to `forbiddenIdentityFields`. — DoD: a
  body with any of them gets 400 `actor_not_accepted`, and nothing is stored.
- [ ] 7. MCP descriptions: in `internal/mcp/workitems.go`, state in the
  `mctl_create_work_item` and `mctl_append_work_item_intent` descriptions
  that the server records the OAuth client and never takes it from an
  argument. — DoD: the tool count in `server_test.go` is unchanged, and the
  description tests pass.
- [ ] 8. Docs (depends on 1-6): update `docs/work-context-contract.md`
  (WorkItem, WorkItemIntent, Event fields; the "Identity and authorization"
  bullet; the MCP surface note, including the shared-portal limit). Document
  the `client_id` access-token claim in `docs/principals.md` or
  `docs/access-token-signing.md`. — DoD: the docs name the fields, their
  source, that `""` means not recorded, and that they are never accepted
  from input or used for authorization.
- [ ] 9. Run `go fmt`, `go vet`, `golangci-lint` and `go test ./...`. — DoD:
  all green.

## Tests

- [ ] T1. `internal/auth`: an authorization-code exchange for client A, and
  a refresh for client A, each produce a token whose `ValidateJWT` user
  reports `OAuthClientID() == A`. `IssueJWT` yields `""`. A token signed
  with a `client_id` over the bound reads `""`.
- [ ] T2. `internal/auth`: a token minted by the pre-change payload shape
  (no `client_id`) still validates and reports `""` (rollout compatibility).
- [ ] T3. `internal/api` handler test: the same principal appends one intent
  with a token for client A and one with a token for client B. The stored
  and returned intents carry `actor_client_id` A and B respectively, with the
  same `actor_principal` and `surface`. This is the #909 scenario.
  Mutation-verified: the test must fail when `mutationFor` sets
  `ActorClientID` to a constant, to `""`, or from the body. Record each
  mutant's failure in the PR description.
- [ ] T4. `internal/api` handler test: a body with `actor_client_id`,
  `origin_client_id` or `client_id` (on create and on append) gets 400
  `actor_not_accepted`, with no row and no event written. Mutation-verified:
  removing the entries from `forbiddenIdentityFields` must make the
  assertion on the error code fail.
- [ ] T5. `internal/mcp/workitems_test.go`: calling
  `mctl_append_work_item_intent` and `mctl_create_work_item` with extra
  arguments `client_id` / `actor_client_id` sends a REST body without those
  keys (assert on the captured request).
- [ ] T6. `internal/workitems` store test: `Create` stores `origin_client_id`
  and `AppendIntent` stores `actor_client_id`. Events carry
  `actor_client_id`. An idempotent replay with a different `ActorClientID`
  returns the originally stored value. A retention sweep keeps
  `actor_client_id` while redacting text.
- [ ] T7. Relay and service paths: a surface-relayed append and a
  service-token create record `""`.

## Rollback

Revert the release, or roll the image back to the prior tag in
`bootstrap/templates/mctl-platform/mctl-api.yaml`. The added columns are
additive with defaults, and older code ignores them, so they can stay in
place. Tokens minted with the `client_id` claim stay valid on older builds,
because `json.Unmarshal` ignores the unknown claim. No data migration needs
undoing. Readers that started depending on `actor_client_id` /
`origin_client_id` must treat a missing key as "not recorded".
