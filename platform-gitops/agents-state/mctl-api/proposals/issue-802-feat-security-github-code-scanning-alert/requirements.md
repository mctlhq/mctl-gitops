# GitHub code_scanning_alert webhook receiver for SecurityFinding v1 (#2103 P3)

## Context

mctlhq/mctl-gitops#2103 needs one real authenticated provider path into the SecurityFinding v1 store shipped by mctlhq/mctl-api#774. mctlhq/mctl-api#802 owns the in-process receiver for GitHub repository webhook `code_scanning_alert` deliveries. mctlhq/mctl-api#801 separately publishes Trivy SARIF to GitHub Code Scanning.

The receiver is public at the HTTP edge, so its trust boundary is strict: a dedicated HMAC secret authenticates the delivery; provider identity and tenant are server-derived; payload prose is untrusted; an allowlisted delivery is never acknowledged 2xx unless the #774 store durably accepted it as created or duplicate.

## User stories

- AS a platform security operator I WANT allowlisted GitHub Code Scanning alerts to become #774 observations automatically SO THAT scanner findings enter the governed lifecycle without a manual import.
- AS an operator I WANT failed deliveries to remain visibly failed in GitHub and metrics SO THAT they can be redelivered without silent loss.
- AS a security reviewer I WANT provider identity, principal provenance and tenant to come only from server configuration SO THAT payload text cannot impersonate another provider, principal or tenant.

## Acceptance criteria

### Route and channel authentication

- THE SYSTEM SHALL expose `POST /api/v1/security/webhooks/github-code-scanning` outside bearer-token middleware, next to the existing GitHub webhook receiver.
- IF `GITHUB_CODE_SCANNING_WEBHOOK_SECRET` is unset, shorter than the platform secret minimum, or equal to `GITHUB_WEBHOOK_SECRET`, THE SYSTEM SHALL disable only this receiver and answer 503.
- THE SYSTEM SHALL read at most 1 MiB and answer 413 above that limit.
- IF `X-Hub-Signature-256` is absent, malformed or not a valid HMAC-SHA256 of the raw body under the dedicated secret, compared in constant time, THE SYSTEM SHALL answer 401, count `signature_invalid`, and record nothing.
- A body signed only with `GITHUB_WEBHOOK_SECRET` SHALL be rejected with 401.

### Server-derived provider authority

- `provider_ref` SHALL be the route-bound constant `github-code-scanning`; payload fields SHALL NOT select it.
- The receiver SHALL require a valid `SECURITY_PROVIDERS` entry for `github-code-scanning` and a valid `SECURITY_GITHUB_CODE_SCANNING` config whose repository-to-tenant mappings are a subset of that provider's configured tenants.
- The in-process `securityfindings.ProviderContext` SHALL set:
  - `Ref = "github-code-scanning"`;
  - `PrincipalID = "service:security-provider:github-code-scanning"` (server-derived, non-empty);
  - `MaxStrength` and tenant allowlist from server configuration only.
- The same stable principal id SHALL be used for audit provenance. A payload `provider`, tool name, actor or user field SHALL NOT alter provider identity, principal identity, tenant, authority or verification strength.
- The dedicated webhook HMAC is the channel credential. No `MCTL_SECURITY_PROVIDER_TOKENS` token is required for this in-process call.

### Configuration and allowlists

- `SECURITY_GITHUB_CODE_SCANNING` SHALL be validated at startup. Invalid JSON, foreign provider ref, unknown configured action, empty repository map/tool list, empty tenant, or a tenant outside the provider config SHALL disable only this receiver and produce a 503 on the route.
- Only `X-GitHub-Event: code_scanning_alert` is processed. Other signed events, including `ping`, SHALL return 2xx ignored and write nothing.
- Only configured actions, repositories and tools are processed. Disallowed values SHALL return 2xx ignored and write nothing.
- The implementation SHALL pin its supported action/payload vocabulary to current authoritative GitHub webhook documentation in tests/fixtures or a documented mapping test; it SHALL NOT invent fields/actions from article prose.

### Stable alert identity and mapping

For an allowlisted delivery:

- `delivery_id` SHALL be `X-GitHub-Delivery`.
- `identity` SHALL be `alert.rule.id`.
- `source_finding_id` SHALL be the stable alert identity:
  `github:<repository.full_name>/code-scanning/<alert.number>`.
  It SHALL NOT contain branch/ref, commit, action or `most_recent_instance.ref`, because those change across observations of the same GitHub alert.
- Branch/ref is observation context only and MAY be retained as bounded evidence/untrusted metadata; it SHALL NOT participate in `source_finding_id`.
- Subject SHALL contain repository + path + `start_line:end_line` + rule id, preserving #774 occurrence identity semantics.
- Action mapping SHALL be limited to live GitHub-supported actions selected by config. Initial mapping:
  - `created`, `appeared_in_branch`, `reopened`, `reopened_by_user` -> `present`;
  - `fixed` -> `fixed`;
  - `closed_by_user` -> `withdrawn`.
- `observed_revision` SHALL use the event commit field when present, otherwise the most recent instance commit SHA when valid; user-only actions that carry no revision SHALL leave it empty rather than fabricate one.
- Rule description, message, severity, tool name/version, refs and other provider prose SHALL be stored only as bounded evidence/untrusted data and SHALL never drive identity, authorization, strength or lifecycle policy.
- Missing delivery GUID, alert number, rule id or location path in an otherwise allowlisted delivery SHALL be a rejected 4xx, not ignored and not accepted.

### Durable handling

- The receiver SHALL synchronously call the #774 store with a 5 s bound; that store write is the durability point.
- `created` -> 202 `accepted`.
- `duplicate` -> 202 `duplicate`.
- Nil/unavailable store, timeout, returned store error, or `internal_error` item result -> 503 `store_unavailable`.
- Other item rejection -> 4xx `rejected` with the canonical code.
- An allowlisted delivery SHALL NEVER receive 2xx unless its item result is `created` or `duplicate`.
- Redelivery of the same GitHub delivery/body SHALL be idempotent under #774 observation hashing.

### Metrics, logs and audit

- THE SYSTEM SHALL expose `mctl_security_webhook_deliveries_total{provider,result}` for provider `github-code-scanning`, with closed results `accepted|duplicate|ignored|signature_invalid|store_unavailable|rejected`, pre-initialized to zero.
- The secret, signature header and raw request body SHALL never be logged.
- Accepted/duplicate deliveries SHALL create a `security.observations.webhook` audit event carrying the stable principal id, delivery GUID, repository and result.
- Tests SHALL prove the `ProviderContext.PrincipalID` delivered to the store is exactly `service:security-provider:github-code-scanning` and cannot be altered by payload fields.

## Out of scope

- GitOps/Vault/ESO wiring, webhook registration and alerting: mctlhq/mctl-gitops#2103.
- Trivy SARIF publishing: mctlhq/mctl-api#801.
- A durable outbox/asynchronous relay.
- Organization/GitHub App webhook support or generic SARIF ingestion.
- Automatic redelivery.
- Verification strength changes; initial GitOps provider ceiling remains `provider_claim` unless separately reviewed.
- Automatic remediation, merge or deploy.

## Rollout / release gate

The implementation PR owns code, tests, docs and release notes. It SHALL NOT manually cut or mutate an mctl-api release tag as part of the implementer task. After merge, the normal mctl-api release automation/process produces a tag containing the receiver. mctlhq/mctl-gitops#2103 remains blocked until that released/deployed tag is verified and the final env/metric names are recorded on #2103.
