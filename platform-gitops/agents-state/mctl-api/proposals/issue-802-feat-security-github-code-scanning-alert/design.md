# Design: issue-802-feat-security-github-code-scanning-alert

## Current state

Existing GitHub webhook receiver
- `internal/api/handlers_github_webhook.go` `HandleGitHubWebhook` serves
  `POST /api/v1/webhooks/github`. It is mounted in `internal/api/router.go` under
  "Webhook callbacks (unauthenticated/token-validated)", outside the auth group and
  outside the timeout middleware. It:
  - reads at most `maxGitHubWebhookBytes` (1 MiB) and answers 413 above that;
  - verifies with `validGitHubSignature(secret, body, header)`, which uses `hmac.Equal`
    and is therefore constant time;
  - acknowledges unhandled events and owners with 202 `{"status":"ignored"}`;
  - bounds its durable write with `githubEnqueueTimeout` (5 s) and answers 503 if that
    write fails;
  - answers 202 only after the outbox commit.
  Its secret is `Options.GitHubWebhookSecret` from `GITHUB_WEBHOOK_SECRET`
  (`cmd/api/main.go` ~L1618). The new receiver copies this shape.

SecurityFinding v1 store (#774)
- `internal/securityfindings/ingest.go` `(*Store).IngestBatch(ctx, ProviderContext, Batch)`
  returns one `ItemResult` per item.
  - Each item gets its own transaction.
  - A database failure inside an item is not returned as an error. It becomes
    `ItemResult{Status:"rejected", Code: CodeInternal /* "internal_error" */}`.
  - `IngestBatch` itself errors only on batch-level `ErrInvalid`.
  - So the receiver must map `CodeInternal` to 5xx itself.
- Redelivery: `ingestTx` looks up `observation_hash`, which covers identity, subject
  fingerprint, `source_finding_id`, `claimed_action`, revision, artifact, `delivery_id`
  and evidence digest, per `provider_ref`. On a match it returns `ItemDuplicate`. A GitHub
  redelivery reuses the `X-GitHub-Delivery` GUID and body, so it is a duplicate.
- `internal/securityfindings/types.go`:
  - `ObservationInput` has `Tenant, Identity, Aliases, Subject, SourceFindingID,
    ClaimedAction, ObservedRevision, ObservedArtifactDigest, EvidenceRefs, ObservedAt,
    Untrusted`.
  - `Untrusted{Title(256), Description(4096), Severity(32), ClaimedProvider(128)}`. There
    is no tool-version field, so tool name/version must go into `Description` and
    `ClaimedProvider`.
  - Claim constants are `ClaimPresent/ClaimFixed/ClaimAbsent/ClaimWithdrawn`.
  - `ProviderContext{Ref, MaxStrength, Tenants, AnyTenant, PrincipalID}`.
  - `allowsTenant` rejects tenants outside `Tenants` with `CodeTenantDenied`.
- `internal/securityfindings/identity.go`:
  - `classify` turns `CVE-…`/`GHSA-…` rule ids into `cve:`/`ghsa:` keys and anything
    else into `rule:<providerRef>:<id>`.
  - `checkSubjectStrength` requires repository|resource plus purl|path|location|artifact.
  - `fixed` only verifies through `verifyFromObservation`, at `StrengthProviderClaim`,
    capped by `pc.MaxStrength`.
- `internal/api/handlers_security_findings.go`:
  - `IngestSecurityObservations` (bearer-authenticated `POST /api/v1/security/observations`)
    builds the provider context in `providerContext(user)` from `h.opts.SecurityProviders`,
    keyed by `user.SecurityProviderRef()`.
  - Payload provider text goes into `Untrusted.ClaimedProvider` via `truncate`.
  - `auditSecurity(r, user, op, params)` writes `security.<op>` audit entries.
  - `securityProviderGate` confines provider principals to the ingest route.
- `internal/auth/security_provider.go`:
  - `SECURITY_PROVIDERS` is parsed by `ParseSecurityProviders` and `LoadSecurityProviders`
    into `map[ref]SecurityProviderConfig{Ref, MaxStrength, Tenants}`.
  - `MCTL_SECURITY_PROVIDER_TOKENS` mints `NewSecurityProviderUser(ref)` with the id
    `service:security-provider:<ref>`.
  - `Options.SecurityFindings` is the concrete `*securityfindings.Store`, and
    `Options.SecurityProviders` is set in `cmd/api/main.go` ~L1127.
- Metrics are `prometheus.NewCounterVec` package vars, registered in `init()` (for example
  `internal/api/handlers_identity_link.go:145`).
- Tests: `handlers_security_findings_test.go` needs `TEST_DATABASE_URL` for the real store.
  There is no seam for simulating a store outage.
- Helm: `helm/templates/deployment.yaml` renders `SECURITY_PROVIDERS` from
  `.Values.securityProviders`. `envFromOptionalSecrets` already exists in `helm/values.yaml`.

Deployed state checked:
- `mctl_get_service_status(team=admins, service=mctl-api)`: Argo CD app `admins-mctl-api`
  is Healthy and Synced (updatedAt 2026-10-26T12:43:00Z). `service: null`, because it is a
  bootstrap app, not a catalogue service.
- `$MCTL_GITOPS_ROOT/bootstrap/templates/mctl-platform/mctl-api.yaml`:
  - image tag `"4.124.0"`;
  - `envFromOptionalSecrets: [mctl-api-zitadel-hook]`;
  - no `securityProviders`, `securityCodeScanning` or `SECURITY_GITHUB_CODE_SCANNING` yet,
    as expected, since #2103 adds them after this lands.
- `$MCTL_GITOPS_ROOT/services/admins/` does not contain mctl-api, which confirms it is not
  a tenant service.
- `agents-state/mctl-gitops/proposals/issue-2103-…/design.md` was read for the mapping
  table, the planned env, the provider entry
  `{"ref":"github-code-scanning","max_strength":"provider_claim","tenants":["admins"]}`
  and the planned alert on this metric.
- Not observed: the clone has no git tags, so whether `4.124.0` contains #774 was not
  verified. The issue asserts it does.

## Proposed solution

### New file `internal/api/handlers_security_code_scanning.go`

Constants:
- `securityCodeScanningRoute = "/api/v1/security/webhooks/github-code-scanning"`
- `codeScanningProviderRef = "github-code-scanning"`
- `codeScanningStoreTimeout = 5 * time.Second`

Config type, parsed in the same package and used by `cmd/api/main.go`:
```go
type CodeScanningConfig struct {
    ProviderRef  string            `json:"provider_ref,omitempty"` // must be "" or "github-code-scanning"
    Repositories map[string]string `json:"repositories"`           // full_name (case-insensitive) -> tenant
    Tools        []string          `json:"tools"`                  // exact alert.tool.name
    Actions      []string          `json:"actions"`                // subset of the six mappable actions
}
func ParseCodeScanningConfig(raw string) (*CodeScanningConfig, error)
```
Validation rules:
- Empty input means "not configured" and returns nil.
- Malformed JSON, a foreign `provider_ref`, an unknown action, an empty map or tool
  list, or an empty tenant is an error.

New `Options` fields in `internal/api/router.go`:
- `CodeScanningWebhookSecret string`
- `CodeScanningConfig *CodeScanningConfig`
- `SecurityIngester securityIngester`, an optional test seam:
  `interface{ IngestBatch(context.Context, securityfindings.ProviderContext, securityfindings.Batch) ([]securityfindings.ItemResult, error) }`.
  When it is nil the handler uses `h.opts.SecurityFindings`. The guard checks for a nil
  `*Store` explicitly, so a typed nil never becomes a non-nil interface.

Route: `r.Post(securityCodeScanningRoute, h.HandleGitHubCodeScanningWebhook)`, placed next
to `/api/v1/webhooks/github`. It is public, HMAC-authenticated, and not reachable by the
bearer middleware, the security-provider gate or the CSRF/consent logic.

Handler order, with every exit counted exactly once in
`mctl_security_webhook_deliveries_total{provider="github-code-scanning",result}`:
1. If the secret is empty, the config is nil, or `SecurityProviders["github-code-scanning"]`
   is missing or has an invalid `max_strength`, answer 503
   `{"error":"code scanning webhook not configured"}`. This is not counted (see Open
   questions).
2. Read the body through `io.LimitReader(maxGitHubWebhookBytes+1)`. Above the limit,
   answer 413 and count `rejected`.
3. Check `validGitHubSignature(secret, body, r.Header.Get("X-Hub-Signature-256"))`,
   reusing the existing helper. On failure answer 401 and count `signature_invalid`.
   Nothing is parsed or logged beyond the delivery GUID.
4. If `X-GitHub-Event` is not `code_scanning_alert`, answer 202 `ignored` and count
   `ignored`. This covers `ping`.
5. Decode a minimal struct:
   - `action`, `ref`, `commit_oid`;
   - `repository.full_name`;
   - `alert.number`, `alert.html_url`;
   - `alert.rule.{id,severity,security_severity_level,description}`;
   - `alert.tool.{name,version}`;
   - `alert.most_recent_instance.{ref,commit_sha,location.{path,start_line,end_line},message.text}`.
   Invalid JSON answers 400 and counts `rejected`.
6. Check the allowlists: action in `Actions`, repository in `Repositories` (compared
   lowercase), and `alert.tool.name` in `Tools`. Otherwise answer 202 `ignored` with a
   reason and count `ignored`.
7. Map with the pure function
   `mapCodeScanningAlert(delivery, tenant string, p payload) (securityfindings.ObservationInput, error)`:
   - `Tenant` = `Repositories[full_name]`.
   - `Identity` = `alert.rule.id`.
   - `Subject{Repository: full_name, Path: location.path, Location: fmt.Sprintf("%d:%d", start, end), RuleID: rule.id}`.
   - `SourceFindingID` = `github:<full_name>/code-scanning/<number>@<instRef>`, where
     `instRef` = `most_recent_instance.ref`, else top-level `ref`. If both are empty the
     `@…` suffix is omitted.
   - `ClaimedAction`:
     - `created`, `appeared_in_branch`, `reopened`, `reopened_by_user` -> `present`
     - `fixed` -> `fixed`
     - `closed_by_user` -> `withdrawn`
   - `ObservedRevision` = `commit_oid`, else `most_recent_instance.commit_sha`. It is
     forced to `""` for actions ending in `_by_user`.
   - `EvidenceRefs` = `[{kind:"github_code_scanning_alert", ref: html_url}]` when
     `html_url` is non-empty. The delivery GUID is already `delivery_id`.
   - `Untrusted`:
     - `Title` = `rule.description`;
     - `Severity` = `security_severity_level`, else `rule.severity`;
     - `Description` = `message.text` plus `"\ntool: <name> <version>"`;
     - `ClaimedProvider` = `tool.name`.
     Each is passed through the existing `truncate` to the `securityfindings.MaxUntrusted*`
     caps.
   A missing GUID, a zero `alert.number`, an empty rule id or an empty path is an error.
   The handler answers 400 and counts `rejected`.
8. Call `IngestBatch(ctx /* WithTimeout codeScanningStoreTimeout */, pc, Batch{DeliveryID: guid, Observations: [obs]})`.
   `pc` is built server-side as
   `ProviderContext{Ref: "github-code-scanning", MaxStrength: parsed cfg.MaxStrength, Tenants: cfg.Tenants, PrincipalID: ""}`.
   Nothing in it comes from the payload. Result handling:
   - A nil store, a returned error, or a deadline answers 503 and counts
     `store_unavailable`. The error is logged without the body.
   - `ItemCreated` answers 202 `{"status":"accepted", finding_id, occurrence_id, observation_id}`
     and counts `accepted`.
   - `ItemDuplicate` answers 202 `{"status":"duplicate", …}` and counts `duplicate`.
   - `ItemRejected` with `Code == CodeInternal` answers 503 and counts `store_unavailable`.
   - Any other `ItemRejected` (`subject_too_weak`, `invalid_request`, `tenant_not_allowed`,
     `finding_alias_conflict`) answers 422 with the code and counts `rejected`.
9. On accepted or duplicate, call `auditSecurity` with
   `auth.NewSecurityProviderUser(codeScanningProviderRef)` and operation
   `observations.webhook`. The params are the delivery GUID, repository, action and result.
   A structured `slog.Info` records the same fields. The secret, the signature and the
   body are never logged.

Metric: a package-level `securityWebhookDeliveriesTotal` CounterVec with the name
`mctl_security_webhook_deliveries_total`, labels `provider` and `result`, registered in
`init()`. All six results are pre-initialized with `WithLabelValues(...).Add(0)` for
`github-code-scanning`, so `increase()` alerts work from the first scrape.

### Wiring in `cmd/api/main.go`
- Read `GITHUB_CODE_SCANNING_WEBHOOK_SECRET` with `strings.TrimSpace`. If it equals the
  trimmed `GITHUB_WEBHOOK_SECRET`, log
  `slog.Error("code scanning webhook secret equals GITHUB_WEBHOOK_SECRET; receiver disabled")`
  and use `""`. Do the same when it is shorter than `minSurfaceTokenLen`, either by reusing
  the auth package constant or by applying the same 32-byte floor locally.
- Parse `SECURITY_GITHUB_CODE_SCANNING` through `api.ParseCodeScanningConfig`. On error,
  log and use nil.
- Cross-check: if the config is set, every mapped tenant must appear in
  `LoadSecurityProviders()["github-code-scanning"].Tenants`. Otherwise log and set the
  config to nil, so the route answers 503 instead of a 422 store rejection on every
  delivery.
- Pass both values into `api.Options`. Startup is never fatal, because the route is
  optional.

### Helm (`helm/values.yaml`, `helm/templates/deployment.yaml`)
- Add an optional `securityCodeScanning` value (a map) that renders
  `SECURITY_GITHUB_CODE_SCANNING` as `toJson | quote`, guarded by `if`, mirroring
  `securityProviders`.
- The secret arrives through `envFromOptionalSecrets`, which already exists. No new
  template is needed for it.
- Add a `helm/render_test.go` case.

### Provider authentication decision
"Webhook secret configured" is the channel credential. The receiver runs in-process and
calls the store directly, so a bearer token would authenticate the process to itself and
add a second secret without narrowing anything. The route still needs a
`SECURITY_PROVIDERS` entry for `github-code-scanning`, which supplies the tenant ceiling
and the `max_strength` ceiling. Authority is therefore the AND of four things:
1. a valid HMAC under the dedicated secret;
2. the route-bound constant ref;
3. the `SECURITY_PROVIDERS` entry;
4. the repository map.
This decision is stated in the PR description and recorded on mctl-gitops#2103 with the
final env and metric names.

## Alternatives
1. Extend `HandleGitHubWebhook` with a `code_scanning_alert` branch and the org secret.
   Dropped:
   - the issue requires a distinct secret, and a body signed with the org secret must
     get 401;
   - sharing the handler would couple rotation and blast radius with pull-request events,
     which the gitops design also rejects.
2. Have the receiver call `POST /api/v1/security/observations` over loopback with a
   `MCTL_SECURITY_PROVIDER_TOKENS` token. Dropped:
   - it adds a credential and a network hop inside one process;
   - loopback skips the global rate limit but not the auth plumbing;
   - the bearer route's 200-with-per-item-results contract would have to be re-parsed to
     recover `internal_error`, which is the case that must become a 5xx.
3. Accept with 202 into an outbox (like the PR event path) and ingest asynchronously.
   Dropped for v1:
   - it needs a new table, a relay and dead-letter handling;
   - the store is in-process, and one delivery is one small transaction, so a synchronous
     write with 503 on failure meets "never 2xx unless durably accepted" more simply;
   - it can be revisited if delivery volume grows.

## Platform impact
- Migrations: none. The receiver writes through the existing #774 tables.
- Backward compatibility: purely additive. With the new env unset, the new route answers
  503 and nothing else changes. Existing routes, tokens and `SECURITY_PROVIDERS`
  semantics are untouched.
- Resource impact: one delivery per alert event and one short transaction each. The
  body is capped at 1 MiB and the store call at 5 s.
- Risks and mitigations:
  - A public, unauthenticated route invites forged traffic. HMAC is checked before
    parsing and with a constant-time compare. Unsigned traffic costs one HMAC over at most
    1 MiB. An IP rate limit is not added, matching `/api/v1/webhooks/github`. A flood would
    show as `signature_invalid`.
  - Payload-driven attribution. The tenant comes from the config map and the provider is
    a constant. Tool and provider text goes only into `untrusted`. The tool allowlist
    reads `tool.name` only to narrow scope, never to grant it.
  - Silent loss. Every non-recorded allowlisted delivery is a 4xx or 5xx, and
    `CodeInternal` is mapped explicitly to 503.
  - Overstated resolution. `fixed` is capped at `provider_claim` by the store and by
    gitops' `max_strength`, so a webhook cannot verify a fix by itself.
  - Secret reuse. A startup check disables the receiver if its secret equals the org
    secret.
- Rollout: release an mctl-api tag. Then gitops #2103 sets the secret, config and provider
  entry and registers the hook.
