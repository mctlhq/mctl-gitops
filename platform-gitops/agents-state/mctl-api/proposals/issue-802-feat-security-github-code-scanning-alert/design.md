# Design: issue-802-feat-security-github-code-scanning-alert

## Current state

mctl-api already has two useful primitives:

1. `internal/api/handlers_github_webhook.go` exposes a public GitHub webhook receiver with a 1 MiB body cap, `validGitHubSignature` using constant-time `hmac.Equal`, ignored-event acknowledgements, and bounded durable handling.
2. `internal/securityfindings` from #774 owns normalization, occurrence identity, append-only observations and lifecycle. `Store.IngestBatch(ctx, ProviderContext, Batch)` returns per-item `created|duplicate|rejected`; database failures may surface as rejected `internal_error`, so the receiver must translate that to 5xx rather than acknowledge it.

The new receiver is intentionally a thin authenticated adapter between GitHub Code Scanning and #774. It is not a second finding store, scanner, policy engine or remediation engine.

## Proposed solution

### 1. Public route and configuration

Add `internal/api/handlers_security_code_scanning.go` with:

```text
POST /api/v1/security/webhooks/github-code-scanning
```

The route sits next to `/api/v1/webhooks/github`, outside bearer middleware. Add:

- `GITHUB_CODE_SCANNING_WEBHOOK_SECRET` — dedicated HMAC secret, distinct from `GITHUB_WEBHOOK_SECRET`;
- `SECURITY_GITHUB_CODE_SCANNING` — non-secret JSON config containing the fixed provider ref, repository->tenant mapping, tool allowlist and action allowlist.

`SECURITY_PROVIDERS` remains the authority source for `github-code-scanning` tenant scope and maximum verification strength. Invalid or inconsistent configuration disables only this receiver and makes it answer 503.

### 2. Channel trust and provider provenance

The HMAC secret is the channel credential. Because the receiver calls the store in-process, it does not authenticate back into mctl-api with a second bearer token.

After signature/config validation construct the provider context entirely server-side:

```go
pc := securityfindings.ProviderContext{
    Ref:         "github-code-scanning",
    PrincipalID: "service:security-provider:github-code-scanning",
    MaxStrength: providerConfig.MaxStrength,
    Tenants:     providerConfig.Tenants,
}
```

`PrincipalID` is deliberately non-empty. This ensures `security_observations.ingested_by_principal_id` and occurrence provenance identify the same route-bound security provider that the audit event uses. Payload fields never choose or override any field of this context.

The audit call uses the same canonical service principal, e.g. `auth.NewSecurityProviderUser("github-code-scanning")`.

### 3. Request processing order

For every request:

1. Refuse 503 when receiver configuration is disabled/unusable.
2. Read raw body with the existing 1 MiB + 1 byte limit; oversize -> 413 `rejected`.
3. Verify `X-Hub-Signature-256` over the raw body with the dedicated secret; invalid -> 401 `signature_invalid`.
4. Check `X-GitHub-Event`; non-`code_scanning_alert` -> 202 `ignored`.
5. Decode only the GitHub Code Scanning fields needed for mapping.
6. Apply configured action/repository/tool allowlists; disallowed -> 202 `ignored`.
7. Validate/map the alert to one `securityfindings.ObservationInput`.
8. Call `IngestBatch` under a 5 s context with exactly one observation.
9. Translate the item result to HTTP status/metric and write audit only for accepted/duplicate.

Every exit after configuration validation increments exactly one result label. The secret, signature and body are never logged.

### 4. Stable GitHub alert identity

The GitHub alert number is the stable source object. Therefore:

```text
source_finding_id = github:<repository.full_name>/code-scanning/<alert.number>
```

Do **not** append `ref`, commit, action or `most_recent_instance.ref`. Those are properties of an observation/instance and can change when the same alert appears, reopens, is fixed or is closed by a user. Keeping them in `source_finding_id` would fragment one GitHub alert into multiple source identities across its lifecycle.

Observation mapping:

```text
delivery_id        = X-GitHub-Delivery
identity           = alert.rule.id
subject.repository = repository.full_name
subject.path       = alert.most_recent_instance.location.path
subject.location   = <start_line>:<end_line>
subject.rule_id    = alert.rule.id
```

Action mapping is a closed table validated against current GitHub webhook documentation and pinned in tests:

```text
created | appeared_in_branch | reopened | reopened_by_user -> present
fixed                                                    -> fixed
closed_by_user                                           -> withdrawn
```

Revision uses the event commit field when supplied, otherwise the most recent instance commit SHA when valid. For user-only actions whose webhook contract carries no revision, keep it empty. Never manufacture a SHA.

Branch/ref, rule text, message, severity and tool name/version are evidence/untrusted context only. They do not participate in provider identity, tenant, authorization, verification strength or stable source finding identity.

### 5. Store result semantics

Introduce a narrow `securityIngester` interface as a handler test seam while production uses the concrete #774 store.

- nil/unconfigured ingester -> 503;
- returned error/deadline -> 503;
- `ItemCreated` -> 202 accepted;
- `ItemDuplicate` -> 202 duplicate;
- `ItemRejected` + `internal_error` -> 503;
- other item rejection -> 422 (or 400 for pre-store malformed input).

An allowlisted delivery is never answered 2xx unless the store durably reports created or duplicate.

### 6. Metrics and audit

Add a CounterVec:

```text
mctl_security_webhook_deliveries_total{provider,result}
```

Provider is fixed to `github-code-scanning`; results are `accepted`, `duplicate`, `ignored`, `signature_invalid`, `store_unavailable`, `rejected`. Pre-initialize all six series.

Accepted/duplicate writes call `auditSecurity` with operation `observations.webhook`, canonical provider user/principal id, delivery GUID, repository and result.

### 7. Wiring and Helm

`cmd/api/main.go`:

- trim/read dedicated secret;
- disable it if too short or equal to the existing org webhook secret;
- parse `SECURITY_GITHUB_CODE_SCANNING`;
- cross-check every mapped tenant against the `github-code-scanning` `SECURITY_PROVIDERS` entry;
- pass secret/config into `api.Options`.

Helm:

- add optional `securityCodeScanning` value rendered as `SECURITY_GITHUB_CODE_SCANNING` JSON;
- dedicated secret is supplied through existing secret/env wiring owned by #2103, not committed in values.

### 8. Tests / authoritative GitHub contract

Tests must include fixture payloads or mapping tables derived from current authoritative GitHub `code_scanning_alert` webhook documentation for the supported actions/fields. The test fixture is the contract for this adapter; provider prose or an article is not.

Required tests cover valid delivery, duplicate delivery, all action mappings, wrong/absent signature, body signed with the org secret, ignored event/action/repository/tool, store unavailable/internal error, body limit, malformed fields, payload provider spoofing, and `ProviderContext.PrincipalID` provenance.

### 9. Release boundary

The implementation DevLoop owns code + tests + docs + PR only. It does not create a release tag. After merge, normal mctl-api release automation/process cuts the tag. #2103 remains blocked until a released/deployed tag containing the receiver is observed and the final configuration/metric names are recorded there.

## Alternatives rejected

- Reuse the org GitHub webhook secret: rejected; it couples blast radius and violates the dedicated-channel requirement.
- Loop back through bearer-authenticated `/security/observations`: rejected; a second credential and HTTP hop add no authority inside the same process.
- Generic SARIF/native-Trivy receiver: rejected; GitHub Code Scanning is the bounded provider adapter chosen for this slice.
- Async outbox in v1: rejected; one bounded store transaction is sufficient and 5xx preserves explicit redelivery semantics.

## Rollback

Unset the dedicated secret/config to make only this route return 503, or roll back the mctl-api image tag. No schema migration is added. Existing observations remain ordinary append-only #774 evidence.
