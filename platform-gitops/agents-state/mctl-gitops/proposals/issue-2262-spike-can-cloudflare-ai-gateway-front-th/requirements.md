# Spike: Cloudflare AI Gateway in front of mctl-support model calls (spend analytics without storing tenant prompts)

## Context

The mctl-support agent (`platform-gitops/services/admins/mctl-support/values.yaml`,
image `0.3.6`) runs a model loop against Nebius Token Factory (`MODEL_PROVIDER: nebius`,
`NEBIUS_MODEL: zai-org/GLM-5.1`). This is an interim choice. The reference model is
Anthropic `claude-sonnet-5-5`, and the Anthropic organization currently answers 401
"organization has been disabled". The spend caps (0.50 USD per task, 10 per tenant,
50 per workspace, per UTC month) are enforced only from the agent's own Postgres spend
ledger. Someone checks them against the provider console by hand. The S2e pilot review
(mctlhq/.github#270) needs an independent answer to the question "did spend stay
inside the caps?".

The issue asks for a time-boxed, observe-first spike with one question: can Cloudflare
AI Gateway sit in the request path of mctl-support and give per-key token, cost, error
and rate-limit analytics without storing tenant prompts in Cloudflare? The required
output is a go/no-go report. A "go" also needs a gitops PR that declares the gateway
in OpenTofu (`infrastructure/cloudflare`) and switches the `*_BASE_URL` of this one
service. A "no-go" records the concrete blocker on the issue. Reading the mctl-support
source already surfaced one likely blocker. The OpenAI-compatible adapter sends only
`Authorization: Bearer <provider key>`, so an authenticated gateway, which requires
`cf-aig-authorization`, cannot be reached by changing the base URL alone.

## User stories

- AS the platform owner I WANT an independent, gateway-side count of mctl-support tokens, cost and errors SO THAT the S2e "spend in caps" answer does not rest only on the agent's own counters.
- AS the platform owner I WANT the gateway to keep no prompt or response bodies SO THAT tenant data from support conversations never lands in Cloudflare.
- AS an operator I WANT the gateway, its settings and its API tokens declared in `infrastructure/cloudflare` and applied through `cloudflare-apply.yml` SO THAT the change is reviewable, drift-checked and reversible like the rest of the account.
- AS the S2e pilot reviewer I WANT a written go/no-go with the numbers from the three sources for one window SO THAT the decision to put a gateway in the production path is based on measured agreement, not on the product page.

## Acceptance criteria (EARS)

- WHEN the spike starts THE SYSTEM SHALL record in the report which env var sets the provider base URL for each provider in mctl-support at the deployed tag (`NEBIUS_BASE_URL`, `HETZNER_BASE_URL`; for Anthropic, the SDK's `ANTHROPIC_BASE_URL` fallback). It SHALL also record which headers each adapter sends, citing source file and line.
- WHEN the gateway is declared THE SYSTEM SHALL declare it as an OpenTofu resource in `infrastructure/cloudflare/account/`. Log collection SHALL be disabled (or set to metadata-only, if the provider exposes that), authentication SHALL be enabled, and the declaration SHALL contain no provider API key.
- WHEN a new or widened Cloudflare API token is needed (gateway plan/apply permission on the CI tokens, the gateway run token) THE SYSTEM SHALL declare it in `infrastructure/cloudflare/tokens/manifest.tf` in the same PR as the dashboard change, so the `tokens` root plan proves the two agree.
- WHEN the gateway run token is created THE SYSTEM SHALL store its value only in Vault at `secret/data/platform/mctl-support/ai-gateway` (property `token`), never in Git, OpenTofu state, a Worker, or a GitHub secret.
- WHEN the comparison window closes THE SYSTEM SHALL publish a report with, for the same UTC window: gateway analytics (requests, input/output tokens, cost, errors, rate-limited requests), the Nebius console usage for the key used, and the mctl-support spend ledger totals. The report SHALL also give the absolute and relative difference per metric.
- WHEN a request through the gateway returns 4xx/5xx THE SYSTEM SHALL record the response body before classifying the cause. A status code alone SHALL NOT be recorded as "provider unsupported".
- IF Nebius cannot be routed through AI Gateway (no native, compat or custom-provider route works) THEN THE SYSTEM SHALL record the attempted routes with their response bodies. It SHALL then run the comparison against Anthropic with a labs key, stating this substitution in the report. IF no working Anthropic key exists either, THEN it SHALL record that as the blocker.
- IF logging cannot be verified as off (or metadata-only) by reading the gateway configuration back AND by confirming that the gateway's log view contains no request/response bodies after test traffic THEN THE SYSTEM SHALL conclude no-go with blocker "logging cannot be disabled".
- IF the authenticated gateway requires a header that mctl-support at the deployed tag cannot send THEN THE SYSTEM SHALL record this as a blocker for the base-URL-only switch and link a follow-up issue in mctlhq/mctl-support. It SHALL NOT fall back to an unauthenticated gateway in production.
- WHILE the spike runs THE SYSTEM SHALL send only synthetic harness traffic through the gateway; no production mctl-support request SHALL pass through it before the go PR is merged.
- WHEN the comparison window closes THE SYSTEM SHALL compare gateway analytics against the Nebius console and the harness-side ledger computation for the harness key, and SHALL separately compare the production spend ledger (`spend_turns`) against the Nebius console for the production key over the same window.
- WHILE the report is not accepted THE SYSTEM SHALL leave `platform-gitops/services/admins/mctl-support/values.yaml` unchanged.
- WHEN the report is accepted with outcome "go" THE SYSTEM SHALL open one PR that adds the gateway-token ExternalSecret and sets `NEBIUS_BASE_URL` (or the provider in use) to the gateway URL for mctl-support only. The PR SHALL keep the Vault-backed provider key path unchanged.
- WHEN the go PR has been live for its first full UTC day THE SYSTEM SHALL post the direct gateway-versus-ledger comparison for production traffic on mctlhq/mctl-gitops#2262.
- WHEN the outcome is "no-go" THE SYSTEM SHALL post the concrete blocker (provider unsupported, logging cannot be disabled, latency, auth) as a comment on mctlhq/mctl-gitops#2262. It SHALL also open a PR that removes the spike gateway resource, unless the report says to keep it.

## Out of scope

- Any change to mctl-support source code. If a gateway-auth header is needed, it is filed as a follow-up in mctlhq/mctl-support.
- Routing any service other than mctl-support, any production values change before the report is accepted, and any production traffic through the gateway during the spike (author decision: off-production harness only).
- Response caching. It stays off for the spike, because a cached tool-calling reply would also skew the comparison.
- Enforcing caps at the gateway (gateway rate limits or spend limits replacing the ledger). The ledger stays the enforcement point.
- BYOK / storing provider keys in Cloudflare Secrets Store.
- Deciding the fate of the pre-existing, unused gateway `test` beyond recording it (see Open questions).
- Logpush, Workers, or any DNS change. A gateway needs none of them.

## Open questions

- Resolved (author answer, request hir-5e1b638e9eca1efa): the comparison window is off-production only. A bounded harness sends traffic through the gateway, and the production ledger is calibrated against the Nebius console separately for the same window. The direct gateway-versus-ledger comparison on production traffic happens after the go PR. This is not an open question any more and is kept here only for the record.
- Whether the Anthropic fallback is possible at all. The values comment says every Anthropic key, including the dedicated one, answers 401 "organization has been disabled". Whether a separate labs Anthropic key exists that is not in that organization is unknown.
- Whether Nebius Token Factory is reachable through a native provider route, the OpenAI-compatible `compat` endpoint, or only a custom provider. This is determined in task 3, not assumed.
- Whether provider `cloudflare/cloudflare ~> 5` (pinned in `account/versions.tf`) exposes a `cloudflare_ai_gateway` resource with the fields needed: log collection off, authentication on, rate limit settings. If it does not, declaring the gateway in IaC is a blocker, and the dashboard is not an acceptable fallback.
- Whether "per-key" in the issue means per provider key (one gateway or one key per service) or per tenant. Per-tenant attribution would need `cf-aig-metadata` headers, which is a code change. The spike reports per-gateway and per-model numbers only.
- Whether the existing gateway `test` (0 requests, per mctl-gitops#2259) should be imported and renamed, or deleted. Deleting it outside Git is against the repo's rule, and importing it would make an unused object look deliberate.
- The deploy tooling has been seen stripping colon-bearing env values (values.yaml comment on `NEBIUS_BASE_URL`). Whether a URL set by a values.yaml PR survives a later `mctl_deploy_service` update-config is unverified. Other URL-valued env vars (`SUPPORT_PUBLIC_URL`, `MCTL_API_URL`) are present in the file today.
