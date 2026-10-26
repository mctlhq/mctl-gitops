# GitHub code_scanning_alert webhook receiver for SecurityFinding v1 (#2103 P3)

## Context
mctlhq/mctl-gitops#2103 (SecurityFinding v1 slice 3) feeds GitHub Code Scanning alerts
(initially Trivy SARIF uploads on `mctlhq/mctl-api`) into the SecurityFinding v1 store
that mctl-api#774 added (`internal/securityfindings`). Its prerequisite P3, this issue
(mctl-api#802), adds a signed, in-process receiver for GitHub `code_scanning_alert`
repository-webhook deliveries. The receiver turns each verified delivery into exactly one
#774 observation under the server-bound provider `github-code-scanning`. GitOps (#2103)
only wires the secret, the provider config and the alert. The mapping contract is the one
in the accepted gitops proposal
`agents-state/mctl-gitops/proposals/issue-2103-feat-gitops-code-scanning-webhook-endpoi/design.md`.

This matters because the route is public and unauthenticated by bearer token. Its trust
rests on three things: the HMAC signature with a dedicated secret, the server-side
allowlists, and the rule that provider identity and tenant never come from the payload.
It must also never answer 2xx for a delivery that was not durably recorded, because
GitHub does not redeliver failed deliveries by itself. A 5xx is the only signal an
operator gets to redeliver.

## User stories
- AS a platform security operator I WANT Code Scanning alerts on allowlisted repositories to become SecurityFinding observations automatically SO THAT findings are tracked through the #774 lifecycle without a manual import.
- AS a platform operator I WANT a failed or lost delivery to be visible as a non-2xx in the GitHub hook log and in a metric SO THAT I can redeliver it and no finding is silently dropped.
- AS a security reviewer I WANT the provider identity, tenant and allowed scope to come only from server configuration SO THAT a forged or attacker-shaped payload cannot attribute findings to another tenant or provider.

## Acceptance criteria (EARS)
- WHEN a `POST /api/v1/security/webhooks/github-code-scanning` request arrives THE SYSTEM SHALL serve it outside the bearer-token authenticated group, next to `POST /api/v1/webhooks/github`.
- IF `GITHUB_CODE_SCANNING_WEBHOOK_SECRET` is unset or empty THEN THE SYSTEM SHALL answer 503 on this route and leave every other route unaffected.
- IF `GITHUB_CODE_SCANNING_WEBHOOK_SECRET` equals `GITHUB_WEBHOOK_SECRET` THEN THE SYSTEM SHALL log an error at startup, without either value, and treat the receiver secret as unset (503).
- IF `SECURITY_GITHUB_CODE_SCANNING` is unset, is not valid JSON, names a `provider_ref` other than `github-code-scanning`, lists an action outside the six mappable actions, or maps a repository to a tenant outside the `github-code-scanning` entry of `SECURITY_PROVIDERS` THEN THE SYSTEM SHALL log an error at startup and answer 503 on this route.
- IF `SECURITY_PROVIDERS` has no `github-code-scanning` entry, or that entry's `max_strength` is invalid, THEN THE SYSTEM SHALL answer 503 on this route.
- WHEN a request body exceeds 1 MiB THE SYSTEM SHALL answer 413 and record nothing.
- IF `X-Hub-Signature-256` is absent, malformed, or not a valid HMAC-SHA256 of the raw body under `GITHUB_CODE_SCANNING_WEBHOOK_SECRET`, compared in constant time, THEN THE SYSTEM SHALL answer 401, count `result="signature_invalid"`, and record nothing. This includes a body correctly signed with the org `GITHUB_WEBHOOK_SECRET`.
- WHEN a validly signed delivery has `X-GitHub-Event` other than `code_scanning_alert` (including `ping`) THE SYSTEM SHALL answer 2xx, count `result="ignored"`, and record nothing.
- WHEN a validly signed `code_scanning_alert` delivery has an action outside the configured allowlist (including `updated_assignment`), a `repository.full_name` not in the configured repository map, or an `alert.tool.name` not in the configured tool list, THE SYSTEM SHALL answer 2xx, count `result="ignored"`, and record nothing.
- WHEN a validly signed, allowlisted delivery arrives THE SYSTEM SHALL submit exactly one observation to the #774 store with provider ref `github-code-scanning` (a server constant) and the tenant from the repository map, never from the payload.
- WHEN mapping a delivery THE SYSTEM SHALL use `delivery_id` = `X-GitHub-Delivery`; `identity` = `alert.rule.id`; `source_finding_id` = `github:<repository.full_name>/code-scanning/<alert.number>@<alert.most_recent_instance.ref>`; subject = `{repository: full_name, path: most_recent_instance.location.path, location: "<start_line>:<end_line>", rule_id: alert.rule.id}`; `claimed_action` = `present` for `created`, `appeared_in_branch`, `reopened` and `reopened_by_user`, `fixed` for `fixed`, and `withdrawn` for `closed_by_user`; `observed_revision` = top-level `commit_oid`, else `most_recent_instance.commit_sha`, and empty for `*_by_user` actions.
- WHEN mapping a delivery THE SYSTEM SHALL place rule description, message text, severity and tool name/version only into the observation's `untrusted` object, truncated to the #774 caps (title 256, severity 32, description 4096, claimed_provider 128 bytes). No such text reaches identity, tenant, provider, strength or authorization.
- WHEN the store records the observation as `created` THE SYSTEM SHALL answer 202 and count `result="accepted"`.
- WHEN the store reports the observation as `duplicate`, for example a GitHub redelivery with the same `X-GitHub-Delivery` GUID and content, THE SYSTEM SHALL answer 202 and count `result="duplicate"`.
- IF the store is not configured, the store call returns an error or exceeds the 5 s bound, or the item result is `rejected` with code `internal_error` THEN THE SYSTEM SHALL answer 503 and count `result="store_unavailable"`.
- IF a signed, allowlisted delivery is malformed (invalid JSON, missing `X-GitHub-Delivery`, missing alert number, rule id or location path) or the store rejects the item with any code other than `internal_error` THEN THE SYSTEM SHALL answer a 4xx (400 or 422) and count `result="rejected"`.
- WHILE the receiver runs THE SYSTEM SHALL never answer 2xx for an allowlisted delivery that the store did not report as `created` or `duplicate`.
- WHILE the receiver runs THE SYSTEM SHALL expose `mctl_security_webhook_deliveries_total{provider,result}`, with `result` in `accepted, duplicate, ignored, signature_invalid, store_unavailable, rejected`. Every combination is pre-initialized to 0 for `provider="github-code-scanning"`.
- WHILE the receiver runs THE SYSTEM SHALL never log the secret, the signature header, or the request body.
- WHEN an observation is accepted or duplicate THE SYSTEM SHALL write a `security.observations.webhook` audit entry with the principal id `service:security-provider:github-code-scanning`, the delivery GUID, the repository and the result.

## Out of scope
- GitOps wiring: the ExternalSecret, the `securityProviders` Helm value, the config env, `envFromOptionalSecrets`, the alert rule and the runbook. All of these belong to mctl-gitops#2103.
- Registering the repository webhook on GitHub, and P2 (SARIF upload in `.github/workflows/security.yml`).
- A durable outbox or asynchronous relay for this route. The synchronous store write is the durability point.
- Organization or GitHub App webhooks, and any event other than `code_scanning_alert`.
- Verification-strength changes. The provider ceiling stays whatever `SECURITY_PROVIDERS` says (gitops plans `provider_claim`).
- Automatic redelivery of failed deliveries.

## Open questions
- Provider authentication (the issue asks for a recorded decision). This proposal takes the "webhook secret configured" option. The in-process receiver builds its `securityfindings.ProviderContext` from the `github-code-scanning` entry of `SECURITY_PROVIDERS`, and the HMAC secret is the channel credential. No `MCTL_SECURITY_PROVIDER_TOKENS` entry is needed. The PR must state this decision and it must be recorded on #2103.
- `most_recent_instance.ref` empty or absent (possible on `*_by_user` actions). This proposal falls back to the top-level `ref`, and then omits the `@<ref>` suffix. This keeps the delivery recordable, but it could split one alert into two source ids across actions. Reviewers should confirm.
- Status code for ignored deliveries. The issue says "2xx". The gitops design mentions 204, and the existing `HandleGitHubWebhook` uses 202 with a JSON body. This proposal uses 202 with `{"status":"ignored","reason":...}` for consistency with the existing receiver.
- Configuration errors (secret, config or provider unset) answer 503 but are not counted in the six-result metric, because the issue fixed that label set. They appear in startup logs, and as 503s in GitHub's delivery log and `http_requests_total`. Gitops could alert on those if wanted.
- Deployed state: whether tag `4.124.0` contains the #774 store could not be confirmed from this clone, which has no tags. The issue states it does.
