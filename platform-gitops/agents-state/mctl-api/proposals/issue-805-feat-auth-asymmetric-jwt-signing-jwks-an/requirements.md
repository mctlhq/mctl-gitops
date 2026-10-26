# Asymmetric JWT signing, JWKS publication and audience enforcement for mctl-api access tokens

## Context

This is the P1 follow-up of the mctlhq/.github#195 verdict (REVISE, report `docs/spikes/mcp-gateway-g0.md`, sections D2 and D6). The access tokens that `mctl-api`'s own OAuth server mints (`OAuthServer.IssueJWT` in `internal/auth/oauth_server.go`) are HS256 JWTs signed with the shared `OAUTH_JWT_SECRET`. `verifyJWT` checks the HMAC, `iss` and `exp` only. Tokens carry no `aud` and no `kid`. Two consequences follow. First, any token from the same issuer and key is a valid API bearer whatever audience it was meant for: threat T10 `LegacyIgnoreAudience`. Second, no other service can verify an mctl-api token without holding the signing secret, so the secret has to be shared, which is the coupling mctl-telegram already had to undo.

The proposal adds an `aud` claim and enforces it, with a bounded and observable grace rule for aud-less tokens minted before rollout. It also adds asymmetric signing (EdDSA, with ES256 as a fallback) behind a flag, with a `kid` header and a key set that keeps retired keys for a bounded window. HS256 is still accepted during the drain. Public keys are published at a JWKS route advertised through `jwks_uri` in the RFC 8414 metadata, and the `alg` is pinned before any key lookup. Audience enforcement at `api.mctl.ai` must be deployed before anything mints a token with another audience, such as `aud=https://mcp.mctl.ai`.

## User stories

- AS a platform security owner I WANT the API to refuse a token minted for a different audience SO THAT a token for a future MCP gateway (or any other resource) cannot be replayed against the REST/MCP API (T10).
- AS a downstream service owner (for example a future MCP gateway) I WANT to verify mctl-api access tokens with public keys from a JWKS endpoint SO THAT I do not need the API's signing secret.
- AS an operator I WANT to rotate the signing key by `kid`, while previously issued tokens stay valid for a bounded window, SO THAT rotation does not log everyone out and a removed key is really dead.
- AS an operator I WANT metrics for aud-less and HS256 tokens still being accepted SO THAT I know when the drain is complete and the grace switches can be turned off safely.

## Acceptance criteria (EARS)

Minting
- WHEN `IssueJWT` mints an access token THE SYSTEM SHALL include `aud` equal to the configured access-token audience, which defaults to `SELF_URL` (`OAuthServer.BaseURL`, `https://api.mctl.ai` in production).
- WHILE `OAUTH_JWT_SIGNING_ALG` is `EdDSA` or `ES256` THE SYSTEM SHALL sign access tokens with the active private key of that algorithm and put its `kid` and `alg` in the JOSE header.
- WHILE `OAUTH_JWT_SIGNING_ALG` is unset or `HS256` THE SYSTEM SHALL sign exactly as today with `OAUTH_JWT_SECRET`, adding only the `aud` claim.

Verification (`verifyJWT` / `OAuthServer.ValidateJWT`, which serves both the federation registry path, `localOAuthProvider.Verify`, and the legacy middleware path in `internal/auth/oidc.go`)
- WHEN a token's header `alg` is `none`, missing, or not in the accepted set THE SYSTEM SHALL refuse it before it looks up any key or computes any signature.
- IF `OAUTH_JWT_ACCEPT_HS256` is false THEN THE SYSTEM SHALL refuse every HS256 token before it computes any HMAC.
- WHEN an asymmetric token's `kid` is missing or names no key in the verification set THE SYSTEM SHALL refuse it.
- WHEN an asymmetric token's `kid` names a retained (retired but still inside its retention window) key THE SYSTEM SHALL accept it if the signature and claims are valid.
- WHEN a token's `aud` claim is present (a string or an array) and does not contain the configured audience THE SYSTEM SHALL refuse it, whatever its algorithm and whatever the grace setting.
- IF a token has no `aud` claim, is HS256, and `OAUTH_JWT_REQUIRE_AUD` is false THEN THE SYSTEM SHALL accept it, subject to the existing checks, and increment `oauth_jwt_audless_accepted_total`.
- IF a token has no `aud` claim and either `OAUTH_JWT_REQUIRE_AUD` is true or the token is asymmetrically signed THEN THE SYSTEM SHALL refuse it.
- WHEN any token is verified THE SYSTEM SHALL increment `oauth_jwt_verifications_total{alg,result}`, so that the drain of HS256 tokens is observable.

JWKS and metadata
- WHILE at least one asymmetric key is configured THE SYSTEM SHALL serve `GET /.well-known/jwks.json` as an RFC 7517 JWK Set. Every active and retained key appears with `kid`, `kty`, `alg` and `use=sig`, and only public key material is included.
- WHILE at least one asymmetric key is configured THE SYSTEM SHALL advertise `jwks_uri` = `<BaseURL>/.well-known/jwks.json` in `/.well-known/oauth-authorization-server`.
- WHILE no asymmetric key is configured THE SYSTEM SHALL omit `jwks_uri` and answer 404 on the JWKS route.
- WHEN a retained key's retention window has elapsed THE SYSTEM SHALL drop it from both the JWKS document and the verification set.
- IF the configured key set is malformed, holds an HMAC or private key where a public key is required, names an unknown active `kid`, or mixes an algorithm with the wrong key type THEN THE SYSTEM SHALL fail startup with a configuration error naming the offending entry and never the key material.

## Out of scope

- The `act` and `scope` claims mentioned as "(later)" in the issue. `jwtPayload` stays forward-compatible, but neither is minted nor enforced here.
- Minting tokens for any audience other than the API. RFC 8707 `resource` parameter handling at `/oauth/token` and any `aud=https://mcp.mctl.ai` token are out of scope; the ordering constraint requires this change to ship first.
- Building the MCP gateway itself.
- Changing refresh tokens. `deriveSuccessorRefreshToken` keeps using `OAUTH_JWT_SECRET`, so that secret stays required.
- Automatic key generation or rotation. Keys are provisioned through Vault and gitops, and rotation is an operator procedure that this change enables.
- Audience handling for third-party OIDC providers. The federation registry already has its own audit/enforce audience modes.

## Open questions

- Audience value for tokens used at `/mcp`. The protected-resource document advertises `resource: <base>/mcp` for the MCP endpoint, while the issue pins `aud=https://api.mctl.ai`. The proposal mints and accepts only `https://api.mctl.ai` (the base URL) for both, because the token endpoint ignores `resource` today. Whether `<base>/mcp` should become an additional accepted audience is left open.
- Array `aud`. Per RFC 7519 the proposal accepts an `aud` array that contains the API audience. A stricter "exactly one audience" rule would also block a multi-audience token that names the API. Reviewers should confirm containment is wanted.
- Retention window default. The proposal uses `OAUTH_JWT_KEY_RETENTION` = 2h, which is at least the access-token TTL plus margin. The report may prescribe a different bound.
- Deployed state. mctl-api's own values file is not in the gitops checkout available to this run, and `mctl_get_service_config admins/mctl-api` returned "service not found". The actual replica count, `OAUTH_TOKEN_TTL` and how the Vault secret `secret/data/platform/mctl-api/oauth` is projected were therefore not observed. The rollout assumes keys arrive through the same Vault-backed secret as `OAUTH_JWT_SECRET`.
