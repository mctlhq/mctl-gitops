# Dedicated per-client-address rate limit on POST /glovo/access/start

## Context
`POST /glovo/access/start` (the self-service Glovo access page from #1201) needs no
authentication. Every call writes one `glovo-access-self-start` row to the shared OAuth flow
store (`internal/auth/flowstore`, Postgres table `oauth_flow_entries`). The row has a TTL of
`releaseChallengeTTL` (10 minutes). The OAuth authorize, code, consent and JTI flows and every
approval page use the same table. A caller who sends start requests in bulk can make that table
grow and slow down the other sign-in flows.

The issue says the route has no rate limit. The code does not fully bear that out. The route is
mounted inside the public OAuth group in `internal/api/router.go`, and that group's middleware is
`httprate.Limit(60, 1*time.Minute, httprate.WithKeyFuncs(keyByTrustedIP))`. That is one per-IP
bucket shared by all the group's routes: `/oauth/*`, the identity link, the DevLoop decide page
and every approval page. The real gap is narrower. The most public start route has no budget of
its own sized for a human pressing "Sign in with Google", and so one address can write up to 60
flow rows a minute through it. This proposal adds a dedicated, tighter per-client-address limit
on that one route. The limit runs before the handler, so a refused request writes nothing.

## User stories
- AS a platform operator I WANT the public start route to be bounded per client address SO THAT nobody can flood the shared flow store that other sign-in flows depend on.
- AS a new Glovo customer I WANT my own sign-in to keep working while some other address is being throttled SO THAT another client's abuse does not lock me out.
- AS a maintainer I WANT a test that fails when the limiter is removed SO THAT the protection cannot silently regress.

## Acceptance criteria (EARS)
- WHEN one client address sends more than `glovoAccessSelfStartsPerMinute` (10) `POST /glovo/access/start` requests within one minute THE SYSTEM SHALL answer the excess requests with HTTP 429 and a `Retry-After` header.
- IF a start request is refused by the limiter THEN THE SYSTEM SHALL write no entry to the flow store, set no `__Host-mctl_glovo_access_self` cookie and not redirect to ZITADEL.
- WHEN a start request is refused THE SYSTEM SHALL render the page's own HTML refusal page (same CSP shell as `glovoAccessSelf.failed`) saying the person should wait a minute and try again, without echoing any request data.
- WHILE one client address is over the limit THE SYSTEM SHALL keep serving start requests from every other client address normally.
- WHEN the request arrives from a peer inside `TrustedProxyCIDRs` THE SYSTEM SHALL key the limit on the client address resolved by `clientMetaMiddleware` / `keyByTrustedIP` (the rightmost untrusted X-Forwarded-For hop), so that clients behind the ingress do not share one bucket.
- IF the peer is not a trusted proxy THEN THE SYSTEM SHALL key on the transport peer and ignore X-Forwarded-For, so rotating that header does not create fresh buckets.
- WHILE the page is not configured (`h.glovoAccessSelf == nil`) THE SYSTEM SHALL mount neither the route nor its limiter, as today.
- THE SYSTEM SHALL keep the existing group limit of 60 per minute in front of the new limit. The new limit only tightens it.

## Out of scope
- A limit shared across replicas (for example Redis- or Postgres-backed). Like every other limiter in mctl-api, this one is per process, so with N replicas the effective limit is N x 10 per minute. This is documented, not solved.
- Dedicated limits on the other page start routes (`/glovo/access-approvals/start`, `/glovo/basket/approvals/start`, `/release/approvals/start`, `/release/window-approvals/start`, `/deploy/approvals/start`, `/devloop/decide/start`, `/identity/link/zitadel`). They keep the shared 60-per-minute group bucket (see Open questions).
- A size cap or quota on `oauth_flow_entries` itself.
- Limits on `GET /glovo/access`, which writes nothing, or on `/glovo/access/callback` and `/glovo/access/confirm`, which only consume entries an earlier start wrote.

## Open questions
- The other start routes. They follow the same pattern but are reached by owners and admins from links they were sent, and those people are few. This proposal leaves them on the shared group bucket. A reviewer may want the same dedicated limiter on them. The helper in the design is written so that adding them is one line each.
- The limit value. 10 per minute per address is a judgement: a real person presses the button about once per 10-minute flow, and several people behind one NAT should still get through. The deployed replica count of mctl-api could not be observed from this run (see design.md), so the effective cluster-wide ceiling is 10 x replicas.
- The issue's premise. The issue says the route has no rate limit, but it already shares the 60-per-minute group bucket. The acceptance criteria still apply. The 429 test pins the dedicated limit, which is reached before the group limit.
