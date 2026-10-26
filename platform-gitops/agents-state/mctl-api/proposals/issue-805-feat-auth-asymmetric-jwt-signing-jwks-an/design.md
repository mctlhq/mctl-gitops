# Design: issue-805-feat-auth-asymmetric-jwt-signing-jwks-an

## Current state

Code read in the clone (HEAD `a94a4db`):

- `internal/auth/oauth_server.go`
  - `OAuthServer.JWTSecret []byte`: "the HMAC-SHA256 signing key for issued access tokens". It is set by `NewOAuthServer(... jwtSecret ...)` from `cmd/api/main.go:189` (`[]byte(cfg.OAuthJWTSecret)`, env `OAUTH_JWT_SECRET`, required by `validate()` around lines 2068/2094).
  - `IssueJWT(login, principalID, groups)` builds `jwtPayload{Issuer: s.BaseURL, Subject, PID, Groups, IssuedAt, ExpiresAt}` and calls `signJWT(payload, s.JWTSecret)`. The TTL is `AccessTokenTTL`, default 1h. It is called from `ExchangeCodeWithClientAuth` (around line 1527) and from the two refresh paths (around 1706 and 1739).
  - The minimal JWT section (around lines 1880-1935) has a constant header `jwtHeader = {"alg":"HS256","typ":"JWT"}`. There is no `kid` and no `aud` field in `jwtPayload`. `verifyJWT(token, secret, expectedIssuer)` splits the token and compares the HMAC over `parts[0].parts[1]`. It never parses the header, so `alg` is implicitly pinned to HS256: an `alg:none` token fails the HMAC, but nothing records why. It then checks `iss` and `exp` only. `aud` is ignored (T10).
  - `ValidateJWT` wraps `verifyJWT(token, s.JWTSecret, s.BaseURL)` and then applies the principal-mode logic.
  - `RefreshAccessTokenWithClientAuth` uses `deriveSuccessorRefreshToken(s.JWTSecret, refreshToken)`, so the HMAC secret is also refresh-token key material and cannot be removed.
- `internal/auth/provider_localoauth.go`: `localOAuthProvider.Verify` calls `oauth.ValidateJWT(raw)`. It claims tokens by an exact (normalized) match of the unverified `iss` against `BaseURL` (`Claims`).
- `internal/auth/oidc.go` (around line 1018): the legacy middleware path also routes JWTs whose `iss == oauth.BaseURL` to `oauth.ValidateJWT`. Both verification entry points therefore pass through `ValidateJWT`/`verifyJWT`, and a check there covers both.
- `internal/auth/federation.go`: the federation registry has Prometheus counters (`federation_audience_rejected_total` and others, built with `prometheus.NewCounterVec`), and OIDC providers already have audience audit/enforce modes. The local provider has none.
- `internal/api/oauth_handlers.go`: `OAuthMeta` (RFC 8414) has no `jwks_uri`. `handleOAuthMeta` builds it from `OAuthServer.BaseURL`. `handleProtectedResourceMeta` advertises `resource` = base, or base + `/mcp` for the MCP alias.
- `internal/api/router.go:405-409`: the well-known routes (`oauth-authorization-server`, `oauth-protected-resource`, `/mcp` alias).
- `go.mod` already depends on `github.com/go-jose/go-jose/v4 v4.1.4`, used by `internal/auth/cimd/assertion.go` to verify `private_key_jwt` client assertions against a fetched JWKS with an explicit algorithm allow-list.
- `helm/templates/deployment.yaml` injects env from `envFromSecret`, `envFromExtraSecret` and `envFromOptionalSecrets`. `helm/values.yaml` has `replicaCount: 1`.

Deployed state checked:
- `mctl_get_service_config(team=admins, service=mctl-api)`: error "service not found: admins/mctl-api". mctl-api is not a catalogue tenant service, so its deployed config was not observed through this tool.
- `$MCTL_GITOPS_ROOT/services/*`: tenants `admins`, `karabu`, `labs`, `namax66`. None has an `mctl-api` directory, so mctl-api's deployed `values.yaml` (replicas, `SELF_URL`, `OAUTH_TOKEN_TTL`, secret wiring) is not in this checkout.
- `services/labs/mctl-telegram/values.yaml` (around line 359) records that mctl-telegram previously sourced `OAUTH_JWT_SECRET` from mctl-api's Vault path `secret/data/platform/mctl-api/oauth`, and that an mctl-api rotation then silently invalidated mctl-telegram tokens. It now uses its own key. This is concrete evidence of the shared-secret coupling the issue describes, and it shows the Vault path where mctl-api's OAuth secret lives.
- Gaps (see Open questions): the replica count, the access-token TTL in production and the exact secret projection were not observed. The design does not depend on them, except that keys must reach every replica identically, which is true of any env-from-secret projection.

## Proposed solution

The change ships in one PR with every new behaviour off or in grace by default. Operators then advance through three switches.

### 1. Claims and header (`internal/auth/oauth_server.go`)

- Extend `jwtPayload` with `Audience audience \`json:"aud,omitempty"\``. `audience` is a small type with a custom `UnmarshalJSON` that accepts a JSON string or an array of strings (RFC 7519 §4.1.3) and a `contains(string) bool` method. Minting always emits a single string.
- Add `jwtHeader{Alg, Typ, Kid string}`. `signJWT` and `verifyJWT` now marshal and parse it instead of using the constant `jwtHeader` string.
- Add `OAuthServer.AccessTokenAudience string`. It is set from the new env `OAUTH_ACCESS_TOKEN_AUDIENCE`, defaults to `SELF_URL`, and is compared via the existing `normalizeIssuer` (trailing-slash tolerant). `IssueJWT` sets `Audience` to it.
- `act`/`scope` are not added (out of scope). Unknown claims are already ignored by `json.Unmarshal`, so adding them later is backward compatible.

### 2. Signer abstraction (new file `internal/auth/jwt_keys.go`)

```go
type accessTokenKey struct {
    kid       string
    alg       string            // "EdDSA" | "ES256"
    private   crypto.Signer     // nil for a retained (retired) key
    public    crypto.PublicKey  // ed25519.PublicKey | *ecdsa.PublicKey (P-256)
    retiredAt time.Time         // zero for the active key
}
type accessTokenKeySet struct {
    active    *accessTokenKey
    keys      map[string]*accessTokenKey
    retention time.Duration
    now       func() time.Time
}
func (ks *accessTokenKeySet) lookup(kid, alg string) (*accessTokenKey, error) // refuses unknown kid, alg/key-type mismatch, and retiredAt+retention <= now
func (ks *accessTokenKeySet) PublicJWKS() jose.JSONWebKeySet                 // active + retained, public parts only, use=sig
```

- The key set is parsed at startup from `OAUTH_JWT_SIGNING_KEYS`, a JSON document delivered from the existing Vault-backed secret:
  `{"active":"2026-11a","keys":[{"kid":"2026-11a","alg":"EdDSA","private_key_pem":"..."},{"kid":"2026-10a","alg":"EdDSA","public_key_pem":"...","retired_at":"2026-11-02T10:00:00Z"}]}`.
  A retired key may also carry only its public PEM, so the private half can be destroyed at rotation time. Parsing validates the key type against `alg` (Ed25519 for EdDSA, P-256 for ES256), checks that `active` names a key with a private part, that `kid`s are unique, and that the document has at most 8 keys. Errors are wrapped with `fmt.Errorf("oauth signing keys: entry %q: %w", kid, err)` and never contain key material.
- `OAUTH_JWT_KEY_RETENTION` (duration, default `2h`, must be at least `AccessTokenTTL`, validated in `cmd/api/main.go` `validate()`). A retained key stays verifiable and published until `retired_at + retention`. After that it is treated as removed: it is absent from JWKS and its `kid` is refused. The check uses the clock rather than startup filtering, so a long-running pod drops the key on time.
- `OAUTH_JWT_SIGNING_ALG` = `HS256` (default) | `EdDSA` | `ES256`. A non-HS256 value requires `OAUTH_JWT_SIGNING_KEYS` with an active key of that algorithm, otherwise startup fails.
- Signing: Ed25519 uses `ed25519.Sign`. ES256 uses `ecdsa.Sign` with SHA-256 and the fixed 64-byte R||S encoding (RFC 7518 §3.4). Signing stays hand-rolled in stdlib, like today, because one header/payload layout is easy to keep byte-exact. Verification of asymmetric tokens uses go-jose (`jose.ParseSigned(token, []jose.SignatureAlgorithm{pinned})` and then `Verify(publicKey)`), the same library and allow-list pattern as `cimd/assertion.go`. That keeps the ES256 signature-format and EdDSA corner cases out of our own code. Round-trip tests pin interoperability between the two.

### 3. Verification order in `verifyJWT` (renamed to an `OAuthServer` method so it can see config)

1. Split into 3 parts, decode and unmarshal the header. A malformed header is refused.
2. **Pin `alg` before any key work.** The accepted set is `{OAUTH_JWT_SIGNING_ALG if asymmetric}` plus `{HS256 if OAUTH_JWT_ACCEPT_HS256}`. `none` and any other value are refused with `errUnacceptedAlg`. The counter records `result="alg_refused"`.
3. Asymmetric: require a `kid` and call `keys.lookup(kid, alg)`. An unknown or expired `kid` gives `result="unknown_kid"`. Otherwise verify with go-jose. HS256: run the existing HMAC comparison (`hmac.Equal`).
4. Unmarshal the payload. Check `iss` and `exp` as today.
5. Audience: if `aud` is present and does not contain `AccessTokenAudience`, refuse (`result="aud_mismatch"`). This is the T10 fix and has no grace. If `aud` is absent: refuse for any asymmetric token, because this build always mints `aud`, and refuse when `OAUTH_JWT_REQUIRE_AUD=true`. Otherwise accept and increment `oauth_jwt_audless_accepted_total`.
6. Increment `oauth_jwt_verifications_total{alg,result="ok"}`.

The check lives in `verifyJWT`/`ValidateJWT` rather than in `localOAuthProvider.Verify`, because `internal/auth/oidc.go` calls `ValidateJWT` directly. Enforcing it in only one of the two callers would leave the legacy path open.

New metrics are registered next to the federation ones in `internal/auth/federation.go`'s registration block, or in a sibling `jwt_metrics.go`:
- `oauth_jwt_verifications_total{alg, result}`, where result is one of ok, alg_refused, unknown_kid, bad_signature, iss_mismatch, expired, aud_mismatch, aud_missing, malformed.
- `oauth_jwt_audless_accepted_total`: the grace-rule drain counter required by the issue.
- `oauth_jwt_signing_keys{state="active|retained"}` gauge.

### 4. JWKS route and metadata (`internal/api`)

- New `OAuthServer.PublicJWKS() (jose.JSONWebKeySet, bool)`. It returns false when no asymmetric key is configured. Each `jose.JSONWebKey` is built from `public` only, with `Use: "sig"`, `Algorithm`, `KeyID`. A unit test asserts that `IsPublic()` holds for every key and that the JSON contains no `d` member.
- New handler `handleJWKS` in `internal/api/oauth_handlers.go`, routed in `router.go` beside the other well-known routes as `r.Get("/.well-known/jwks.json", h.handleJWKS)`. It answers 404 when the OAuth server is nil or no keys are configured. Otherwise it serves `Content-Type: application/jwk-set+json` and `Cache-Control: public, max-age=300` (consistent with `handleProtectedResourceMeta`).
- `OAuthMeta` gains `JWKSURI string \`json:"jwks_uri,omitempty"\``, set to `base + "/.well-known/jwks.json"` only when keys exist. Optionally add `id_token_signing_alg_values_supported`. That is not needed: there are no ID tokens.

### 5. Configuration (`cmd/api/main.go`, `helm/`)

New `Config` fields and env vars: `OAUTH_ACCESS_TOKEN_AUDIENCE`, `OAUTH_JWT_SIGNING_ALG`, `OAUTH_JWT_SIGNING_KEYS`, `OAUTH_JWT_KEY_RETENTION`, `OAUTH_JWT_ACCEPT_HS256` (default true) and `OAUTH_JWT_REQUIRE_AUD` (default false). They are wired after `NewOAuthServer` in the same way `AccessTokenTTL` is. `validate()` refuses `ACCEPT_HS256=false` while `SIGNING_ALG=HS256`, which would refuse every token the server mints. The Helm chart needs no template change: `OAUTH_JWT_SIGNING_KEYS` comes in through the existing `envFromSecret` (the Vault-synced secret at `secret/data/platform/mctl-api/oauth`).

### 6. Rollout order (satisfies the issue's ordering constraint)

| Step | Change | Effect |
|---|---|---|
| A | Deploy this PR with the defaults | `aud` is minted and enforced. Foreign `aud` is refused immediately (T10 closed). Aud-less HS256 tokens are accepted and counted. |
| B | After at least 1 TTL, once `oauth_jwt_audless_accepted_total` stops increasing, set `OAUTH_JWT_REQUIRE_AUD=true` | Grace ends. |
| C | Provision an EdDSA key in Vault and set `OAUTH_JWT_SIGNING_ALG=EdDSA` | New tokens are EdDSA. JWKS and `jwks_uri` go live. HS256 is still accepted. |
| D | After at least 1 TTL, once the HS256 `ok` count in `oauth_jwt_verifications_total` is zero, set `OAUTH_JWT_ACCEPT_HS256=false` | HS256 is refused before any HMAC. |
| E | Only after A is everywhere | Any other issuer or path may mint tokens with `aud=https://mcp.mctl.ai` (a separate issue). |

Rotation: add the new key as `active`, and move the old one to retained with `retired_at=now`. It stays in JWKS and verifiable for `OAUTH_JWT_KEY_RETENTION`, then drops out. Deleting the entry earlier removes the `kid` immediately, which is the emergency-revocation path.

## Alternatives

1. **Enforce `aud` only in `localOAuthProvider.Verify`.** The issue names this hook as an option. It was dropped because `internal/auth/oidc.go` calls `ValidateJWT` directly on the legacy path, so the check would be bypassable there.
2. **Move the whole JWT path to go-jose/`jwt` (sign and verify) and delete the hand-rolled code.** This is cleaner long term, but it changes HS256 token bytes and the error strings existing tests assert on (`oauth_server_test.go`), and it widens the diff of a security-sensitive change. The hybrid approach was chosen: stdlib signing, go-jose verification for the asymmetric algorithms, and the HS256 path unchanged apart from header parsing. A follow-up can consolidate once HS256 has been drained.
3. **Grace rule by a fixed cutoff timestamp (accept aud-less only if `iat < cutoff`) instead of a flag.** This drains automatically, but it needs a deploy-time constant that is wrong if rollout slips, and it adds no security. Aud-less tokens can only be minted by holders of `OAUTH_JWT_SECRET`, and the T10 substitution needs a foreign `aud`, which is refused unconditionally. A flag plus the drain counter is simpler and observable. Aud-less asymmetric tokens are refused outright because no build ever minted them.
4. **ES256 as primary.** It was kept as a fallback only, as the report recommends. EdDSA keys are smaller and deterministic, and Ed25519 has no nonce-reuse risk. Both are implemented so that a consumer unable to verify EdDSA can be served by flipping one env var.

## Platform impact

- **Backward compatibility:** default config changes one observable thing, the new `aud` claim. Old tokens without `aud` keep working under the grace rule. Clients that cache tokens see no difference. The only newly refused token is one with a foreign `aud`, which mctl-api has never minted.
- **Migrations:** none (no database). The new secret key `OAUTH_JWT_SIGNING_KEYS` must be added to the Vault path before step C. That is a gitops/Vault change outside this repo.
- **Refresh tokens:** unaffected. `OAUTH_JWT_SECRET` stays required for `deriveSuccessorRefreshToken`, and that has to be documented so nobody "retires" the secret after step D.
- **Multi-replica:** every replica must load the same key set. Env-from-secret guarantees that per rollout. During a rotation rollout, replicas briefly hold different active keys. Every replica keeps the other key in its set (new as active, old as retained), so tokens from either verify everywhere, provided the retained entry is added in the same secret update.
- **Resource impact:** negligible. Ed25519 verification costs microseconds per request. JWKS is a static response.
- **Risks and mitigations:**
  - Misconfigured key set takes down auth: fail at startup (pod never becomes ready, old ReplicaSet keeps serving) rather than at request time.
  - Private key leak through JWKS: JWKS is built only from the `public` field, and a test asserts no `d`, `p`, `q` or `k` members.
  - Algorithm confusion (HS256 signed with the public key as HMAC secret): the alg is pinned before lookup, and the HMAC path always uses `JWTSecret`, never a key-set entry.
  - Flipping `ACCEPT_HS256=false` too early logs users out: the per-alg counter tells the operator when it is safe. The impact is bounded to a re-login, because refresh tokens mint fresh EdDSA access tokens.
  - Clock skew around `retired_at`: retention defaults to 2h, which is greater than the 1h TTL.
