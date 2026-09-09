# Close the 12 deferred P3s from the custom-domains gateway (#118)

## Context

`mctl-portal#118` repointed the `custom-domains` plugin from its own local
table at mctl-api's domains registry, closing `#117`. It went through seven
review rounds; every P1/P2 was fixed and pinned with a regression test, and the
remaining twelve non-blocking P3 findings were deliberately deferred rather
than extend the PR further. Issue #120 files them so they are not lost.

The twelve findings cluster into four areas: the frontend card
(`packages/app/src/components/catalog/EntityDomainsCard.tsx`) silently swallows
mctl-api's "not verified yet, here is why" answer and gates its Verify button on
two `omitempty` fields; the backend client
(`plugins/custom-domains-backend/src/mctlApiClient.ts`) has an `undefined as T`
type lie, no logger for upstream 5xx diagnosis, one un-sanitised error branch,
two documented-but-unverified upstream assumptions, and an avoidable
`node-fetch@2` dependency on a Node 22 stack; the router
(`plugins/custom-domains-backend/src/router.ts`) logs routine 4xx at `error`
level, carries one inaccurate comment, and leaves one request value cast rather
than checked; and `router.test.ts`'s `express-promise-router` regression table
covers only two of the four affected routes. None is urgent, but together they
are the difference between an operator being able to debug a routine mctl-api
500 and not, and between a user seeing "no TXT record found at
_mctl-challenge.example.com" and seeing nothing at all.

## User stories

- AS a tenant developer verifying a custom domain I WANT the Verify action to
  tell me why verification did not pass SO THAT I can fix my DNS record instead
  of clicking Verify repeatedly with no feedback.
- AS a tenant developer whose domain check failed I WANT the Verify button to
  stay available for any pending or failed row SO THAT a lighter list-response
  shape upstream never strands my domain with no retry path.
- AS a platform operator debugging an mctl-api outage I WANT the upstream 5xx
  body recorded in the portal backend logs SO THAT I can diagnose the failure
  without reproducing it by hand.
- AS a platform operator watching log-based alerts I WANT routine user-caused
  4xx logged at `warn` SO THAT a user's typo does not raise a false-positive
  error alert.
- AS a security reviewer I WANT no upstream URL or internal detail forwarded to
  the browser on any error branch SO THAT the leak class closed in #118 stays
  closed on the one branch that was missed.
- AS a maintainer of this plugin I WANT the client's success-path types to match
  what it can actually return, and the upstream assumptions in its comments to
  be verified against mctl-api's source SO THAT a later reader can trust them.

## Acceptance criteria (EARS)

Frontend — `EntityDomainsCard.tsx`

- WHEN the verify request returns HTTP 200 with a body whose `verified` is
  `false` THE SYSTEM SHALL display that body's `reason` to the user, and
  SHALL NOT report the attempt as a silent success.
- WHEN the verify request returns HTTP 200 with `verified` true THE SYSTEM
  SHALL clear any previous verify error and refresh the domain list.
- IF the verify response body is absent or unparseable on a 2xx THEN THE SYSTEM
  SHALL refresh the list and SHALL NOT display a spurious error.
- WHILE a domain row has `status` of `pending` or `failed` THE SYSTEM SHALL
  offer the Verify action for that row, whether or not the row carries
  `challenge_record_name`/`challenge_record_value`.
- WHILE a domain row carries both challenge fields THE SYSTEM SHALL offer the
  Verify action regardless of its `status`, preserving today's behaviour for a
  status this card has never seen.
- WHILE a domain row carries no challenge fields THE SYSTEM SHALL render the
  Verification column as an em dash rather than a partial TXT hint.

Backend client — `mctlApiClient.ts`

- WHEN an mctl-api response has an empty body on a successful status THE SYSTEM
  SHALL represent that as `undefined` through a `Promise<T | undefined>`-typed
  internal helper, and SHALL NOT assert it as `T`.
- IF `verify()` receives an empty or non-object body on a successful status THEN
  THE SYSTEM SHALL throw `MctlApiError(502, ...)`, because mctl-api's
  `verifyAndRespond` always answers `200` with a JSON `Result`.
- IF `remove()` receives an empty body (a 204) THEN THE SYSTEM SHALL resolve
  with a defined `RemoveResult`-shaped value rather than `undefined`, so the
  router's `res.json(result)` never answers `200` with an empty body.
- WHEN an mctl-api call fails with a 5xx THE SYSTEM SHALL log the upstream
  status, path, and response body at `error` level through an injected logger,
  and SHALL NOT include that body in the error message returned to the browser.
- WHEN a network-level failure occurs THE SYSTEM SHALL log the underlying
  message locally and SHALL throw an `MctlApiError(502, ...)` whose message
  names only the request path, never the resolved upstream URL or the
  underlying driver message.
- WHILE no logger is supplied to `MctlApiDomainsClient` THE SYSTEM SHALL
  continue to function, defaulting to a no-op logger.
- THE SYSTEM SHALL use the Node 22 global `fetch` in this plugin and SHALL NOT
  depend on `node-fetch` or `@types/node-fetch`.
- THE SYSTEM SHALL keep the 401/403-to-502 mapping, documented as verified
  against mctl-api `internal/api/handlers_domains.go` at HEAD: `AddDomain`
  rejects a platform domain with `http.StatusBadRequest`, not 403, and the only
  403 that handler emits for this caller (`access denied to team`) is
  unreachable for an admin-scoped service token and otherwise signals a
  misconfigured `customDomains.token`.
- WHEN a 400 platform-domain rejection is returned by mctl-api THE SYSTEM SHALL
  forward status 400 and mctl-api's own message to the caller.
- THE SYSTEM SHALL document, at `domainBelongsToTeam`, that
  `GET /api/v1/domains?team=` is complete and unpaginated, verified against
  mctl-api `internal/domains/store.go` `ListByTeam` (no `LIMIT`/`OFFSET`), and
  SHALL name the symbol to re-check if that changes.

Router — `router.ts`

- WHEN an `MctlApiError` with a status in the 400-499 range is handled THE
  SYSTEM SHALL log it at `warn` level.
- WHEN an `MctlApiError` with any other status, or any non-`MctlApiError`
  failure, is handled THE SYSTEM SHALL log it at `error` level.
- IF the `service` query parameter on `GET /domains` is present and not a string
  THEN THE SYSTEM SHALL respond 400 without making an upstream call.
- THE SYSTEM SHALL correct the POST `/domains` body-validation comment so it no
  longer claims Express 4's default `qs` query parser guarantees a string, and
  SHALL state that the query-param routes are safe because of their own
  `typeof` checks.

Tests

- WHEN the membership lookup rejects on `POST /domains` or on
  `POST /domains/:id/verify` THE SYSTEM SHALL answer 500 rather than hang, and
  the `rejectingDb` `it.each` table SHALL cover all four affected routes.

## Out of scope

- Migrating the other five plugins (`argo-workflows-backend`,
  `github-app-connect-backend`, `proposals-backend`, `tenant-backend`,
  `vault-secrets-backend`) off `node-fetch@2`. This proposal changes only
  `custom-domains-backend`.
- Dropping the retired local `custom_domains` table from the Backstage database
  (deliberately deferred by #118's own `plugin.ts` note).
- Any change to mctl-api itself, including adding a per-domain
  `GET /api/v1/domains/{id}` lookup or pagination to `ListDomains`.
- Removing the retired `POST /domains/:id/activate` 410 route.
- Reworking the frontend card's visual design, adding polling, or changing the
  Add Domain dialog flow.

## Open questions

- The issue asks for a `failed`-status test fixture "with the challenge fields
  populated". mctl-api's `domainResponseFor` is the authority on whether a
  `failed` row still carries them; this proposal treats the fixture as a
  contract fixture for the card's own logic and does not assert upstream
  behaviour. Proceeding on the reading that the card must tolerate both shapes.
- Finding 4 asks for a logger on the client. Backstage's `LoggerService` is a
  backend-plugin type; injecting it makes `MctlApiDomainsClient` non-trivially
  constructible in a frontend or script context. Proceeding with an optional
  minimal structural logger interface (`{ warn, error }`) defaulting to no-op,
  which `coreServices.logger` satisfies without importing it into the client.
- Whether the deferred `service` `typeof` guard should answer 400 or silently
  drop a non-string `service`. Proceeding with 400, matching every other
  validation branch in `router.ts`.
