# Spike #2262: Cloudflare AI Gateway in front of mctl-support model calls

STATUS: GO, conditional (see section 7). Nothing in production values changes until the
conditions are met and this report is accepted on mctlhq/mctl-gitops#2262.

Question: can Cloudflare AI Gateway sit in front of the mctl-support agent's model calls
(Nebius GLM-5.1 today) and give per-key spend, token and rate-limit analytics that answer the
S2e pilot's "spend in caps" question (mctlhq/.github#270), without storing tenant prompts in
Cloudflare?

Comparison window: 2026-10-29T20:38:41Z to 2026-10-29T20:39:31Z (UTC), 20 synthetic requests.

## 1. What was built (Phase A, mctlhq/mctl-gitops#2265, merged 714210db8)

Declared in `infrastructure/cloudflare` and applied with `cloudflare-apply.yml`
(run 40948572540, `Plan: 1 to add`):

- `cloudflare_ai_gateway.mctl_support` (`infrastructure/cloudflare/account/ai-gateway.tf`):
  id `mctl-support`, `authentication = true`, `collect_logs = false`, `cache_ttl = 0`,
  `cache_invalidate_on_update = true`, rate limiting 0/0/fixed (off). Output
  `mctl_support_ai_gateway_url`.
- Token manifest (`infrastructure/cloudflare/tokens/manifest.tf`): AI Gateway Read on the plan
  token, AI Gateway Write on the apply token, and a new run-only token
  `mctl-support-ai-gateway-run (Vault platform/mctl-support/ai-gateway)`. The token value lives
  only in Vault at `secret/platform/mctl-support/ai-gateway`, key `token` (53 chars, `cfat_`
  prefix, verified active through `/accounts/<id>/tokens/verify`). It is not in Git, Terraform
  state or GitHub secrets.
- mctl-support 0.4.0 (mctlhq/mctl-support#34, not deployed): optional `MODEL_GATEWAY_TOKEN`
  env var sends `cf-aig-authorization: Bearer <token>` on every provider request. The provider
  base URL is already configurable (`NEBIUS_BASE_URL`, default
  `https://api.tokenfactory.nebius.com/v1`), so the gateway switch is a values change plus the
  token secret.

Read-back of the live gateway (GET `/accounts/<acc>/ai-gateway/gateways/mctl-support`, created
2026-10-29T20:28:29Z) matches the declaration. Attributes the API returns that the Terraform
resource does not declare: `log_management 100000 / DELETE_OLDEST`, `wholesale true`,
`workers_ai_billing_mode postpaid`, `logpush false`, `zdr false`, `byok_only false`. Watch the
next plan for drift on these.

## 2. Routing to Nebius: provider-specific path works, compat path does not

Nebius is not a native AI Gateway provider. It is reachable only through a **Custom Provider**
(OpenAI-compatible passthrough), which is where the main blocker sits (section 7).

| path | request | result |
|---|---|---|
| `<gw>/custom-nebius/v1/chat/completions`, `Authorization: Bearer <nebius key>`, `cf-aig-authorization` | model `zai-org/GLM-5.1` | 200, 12 tokens, `cf-aig-request-id` issued, `cf-aig-cache-status: MISS` |
| `<gw>/compat/chat/completions`, model `custom-nebius/zai-org/GLM-5.1` | same | 404: compat appends only `/chat/completions` to the provider host, dropping `/v1` |
| any path without `cf-aig-authorization` | any | 401 (authenticated gateway works) |
| `compat/chat/completions` without a provider key | any | 402, error 2021 "insufficient credits": Unified Billing fallback |
| `<gw>/anthropic/v1/messages`, labs Anthropic key from Vault `secret/platform/mctl-support/model` | claude-haiku-5-5 | 401 both direct and via gateway: the Anthropic org is disabled since 2026-10-29, so the Anthropic comparison from the spike boundary could not run |

Production-shaped configuration therefore is
`NEBIUS_BASE_URL=https://gateway.ai.cloudflare.com/v1/<acc>/mctl-support/custom-nebius/v1`
plus `MODEL_GATEWAY_TOKEN` from Vault. No code change beyond mctl-support#34.

The Custom Provider was created in the dashboard on 2026-10-29 after the owner's go-ahead:
name `Nebius (spike gitops#2262)`, slug `nebius`, base URL
`https://api.tokenfactory.nebius.com`, id `8bfd77c3-9335-44ee-b154-d6d1e51519f4`. This is
out-of-Terraform state and is deleted once this report is accepted (section 8).

## 3. Logging: off, verified by fact

- `collect_logs = false` in the declaration and in the read-back.
- After the discovery requests and the 20-request harness, GET
  `/accounts/<acc>/ai-gateway/gateways/mctl-support/logs` returns `total_count: 0`.
- Prompts and completions therefore never reach Cloudflare storage. Analytics (section 4) still
  work with logging off, since they are built from request metadata, not bodies.
- `cf-aig-metadata` (`{"tenant": "spike", "task": "h<i>"}`) was sent on every harness request.
  With logging off it is not queryable: the GraphQL dataset `aiGatewayRequestsAdaptiveGroups`
  has no metadata dimension (`metadataValue1` is "unknown field"), and the logs API that would
  carry it is empty by design. Per-tenant attribution must stay in mctl's own counters; the
  gateway gives per-gateway and per-model totals only.

## 4. Analytics compared with the agent's own counters

Harness: `harness.py` (20 chat completions, `max_tokens 48`, `temperature 0`, 0.5 s apart,
synthetic SRE questions, user agent `mctl-support-spike/0.1`), all 200. The agent-side counters
are the `usage` objects returned by Nebius, summed by the harness.

| source | requests (200) | tokens in | tokens out | cost |
|---|---|---|---|---|
| harness `usage` sums (window above) | 20 | 4952 | 960 | n/a |
| one discovery request before the window (section 2, row 1) | 1 | 7 | 5 | n/a |
| GraphQL `aiGatewayRequestsAdaptiveGroups`, gateway `mctl-support`, `datetime_geq 2026-10-29T20:00:00Z`, provider `custom-nebius`, status 200 | 21 | 4959 | 965 | 0 |

The gateway numbers equal the agent's counters exactly (20 + 1 requests, 4952 + 7 in,
960 + 5 out). The same query also shows the discovery failures separately: one 404
(compat path), one 502 (model `x`), one Anthropic 401. Non-200 rows carry zero tokens.

Caveats:

- **Analytics lag.** Queried about one minute after the harness, GraphQL showed 3 requests and
  536/101 tokens; queried four minutes later it showed the full 21. Treat the dataset as
  eventually consistent, not real time.
- **GraphQL budget.** The first query of the evening was refused with "budget depleted,
  5 minutes". A spend-cap check must tolerate that and must not read a refused query as zero
  usage ("could not observe" is not "observed absent").
- **Cost is 0 for a custom provider.** Cloudflare has no price table for Nebius models, so
  `sum.cost` is always 0 on `custom-nebius`. The gateway answers "how many tokens" but not
  "how many dollars"; USD stays a multiplication done in mctl. At Nebius' list price (USD 1.40
  per million input, 4.40 per million output, 0.26 per million cached input; official
  machine-readable catalog https://tokenfactory.nebius.com/model-catalog.md, checked 2026-10-29)
  the harness cost about USD 0.011, far under the USD 0.50 task cap. mctl-support already owns
  that price: `MODEL_INPUT_USD_PER_MTOK` / `MODEL_OUTPUT_USD_PER_MTOK` in its gitops values are
  1.40 / 4.40, so condition 2 below holds for the Nebius route as deployed.
- **Hetzner Inference is free while experimental, and limited by requests, not dollars.** Its
  terms (https://docs.hetzner.com/general/company-and-policy/experiments/inference/, checked
  2026-10-29): free of charge as long as the API is experimental, advance notice by email if that
  changes, "as is" with no availability guarantee, and explicitly not for production. Per API key:
  4M input tokens, 100k output tokens and 10 requests per 60 seconds, 429 beyond. All four model
  ids on `/v1/models` (`Qwen/Qwen3.6-35B-A3B`, `Qwen/Qwen3.6-35B-A3B-FP8`, `Qwen/Qwen3.8-27B`,
  `Qwen3.8-27B`, 262k context each) answered 200 through `custom-hetzner` on 2026-10-29. A USD
  price of 0 would make every mctl-support spend cap vacuous, so a Hetzner deployment needs a
  request-rate guard rather than a price table, and stays a non-production fallback under
  Hetzner's own terms.
- **Nebius console**: not compared. No read-only usage API for the Nebius console was found
  during the spike, and the console itself was not opened. The owner can compare the window
  above against the console by hand; the agent-side `usage` values come from Nebius' own
  responses, so a mismatch would point at the console, not the gateway.

## 5. Latency

| path | samples | values |
|---|---|---|
| via gateway, harness | 20 | p50 1829 ms, max 3140 ms |
| direct to `api.tokenfactory.nebius.com`, curl, same model and shape | 5 | 1.80, 4.43, 2.55, 2.27, 2.60 s |

Within this small sample the gateway adds no measurable overhead; the spread of the direct
calls is wider than any difference between the two paths. Five direct samples are too few to
claim more than "no evidence of a penalty".

## 6. Auth and secret handling

- The gateway rejects requests without `cf-aig-authorization` (401), so a leaked base URL alone
  cannot spend on the account.
- The run token has AI Gateway Run only. Listing custom providers with it fails with auth error
  10000, as intended.
- The provider key still travels in `Authorization` on every request (BYOK). It is never stored
  in Cloudflare, a Worker or Terraform state. The gateway was not configured with stored
  provider keys.
- Unified Billing fallback: with no provider key the compat endpoint tried to bill Cloudflare
  credits (402). For a BYOK deployment the gateway must be set to require provider credentials,
  otherwise a missing or rotated key turns into Cloudflare charges instead of a visible error.
  This setting was not found in the `cloudflare_ai_gateway` Terraform schema and is part of the
  conditions below.

## 7. Verdict and conditions

Technically the path works end to end: authenticated gateway, Nebius reachable through a
custom provider, logging off and verified empty, token analytics equal to the agent's own
counters, no visible latency penalty. The go is conditional on four items; until they are met,
production values stay as they are.

1. **The custom provider cannot be declared in Terraform.** The Cloudflare Terraform provider
   (latest checked v5.28.1, 2026-10-20) has `cloudflare_ai_gateway` and
   `cloudflare_ai_gateway_dynamic_routing` and nothing for custom providers. The REST endpoint
   `/accounts/<acc>/ai-gateway/custom-providers` exists (it is what rejected the run token), so
   the options are: a `terraform_data` or REST-provider resource calling that endpoint from
   `cloudflare-apply.yml`; waiting for a native resource; or routing through a native provider
   (Anthropic) once that org is restored. A dashboard-managed provider violates the
   "Cloudflare changes only through gitops" rule and is not acceptable for production.
2. **USD spend needs a price table in mctl.** Gateway cost is 0 for custom providers (section 4).
   The spend-cap check in mctl-support must multiply gateway tokens by a model price it owns,
   or keep using its own counters and use the gateway only as an independent token check.
3. **Require provider credentials** must be on before any production traffic (section 6), through
   gitops. If the Terraform resource cannot express it, that is a second instance of item 1.
   Resolved 2026-10-29: the setting is `byok_only` on the gateway (Cloudflare changelog
   2026-09-14, "Require provider credentials"), present in provider 5.28.1, which the account
   root pins since #2268; declared `true` in `ai-gateway.tf`. A request without a provider key
   then gets a 400 instead of a Unified Billing charge. mctl-support can add the per-request
   `cf-aig-no-wholesale` header as a second lock; it cannot loosen the gateway setting.
4. **Per-tenant attribution stays in mctl.** With logging off, request metadata is not
   queryable (section 3). The gateway gives per-gateway/per-model totals, which is enough for
   the workspace cap (USD 50 per month) but not for the tenant cap (USD 10) on its own.
   This holds by construction as long as the Postgres ledger in mctl-support (`budget/ledger.py`)
   stays the enforcement point of every cap, which Phase B does not change: the gateway is
   observational, a monthly cross-check of its per-model totals against the workspace ledger.

Fair prices for the Hetzner models (owner decision 2026-10-29: price them as a paid host would,
so a free provider never makes the caps vacuous). Nebius lists one of them; the other is not on
Nebius and takes its OpenRouter list price. Both go into `MODEL_INPUT_USD_PER_MTOK` /
`MODEL_OUTPUT_USD_PER_MTOK` next to the model id whenever Hetzner is the configured provider:

| Hetzner model id | priced as | USD / 1M in | USD / 1M out | source |
|---|---|---|---|---|
| `Qwen/Qwen3.8-27B`, `Qwen3.8-27B` | Nebius `Qwen/Qwen3.8-27B` | 0.45 | 3.00 | tokenfactory.nebius.com/model-catalog.md |
| `Qwen/Qwen3.6-35B-A3B`, `-FP8` | OpenRouter Qwen3.6-35B-A3B | 0.15 | 1.00 | openrouter.ai model listing (aggregator) |

What the gateway does give today, at zero cost on Workers Paid: an independent, eventually
consistent token count per gateway and model, error-code breakdown, optional rate limiting and
caching, all without a code change beyond a base URL and one header.

## 8. Cleanup and follow-ups

- Delete the dashboard-created custom provider `nebius`
  (id `8bfd77c3-9335-44ee-b154-d6d1e51519f4`) once this report is accepted. Until then it is
  recorded here as unmanaged state.
- The unmanaged gateway `test` (0 requests, found by mctlhq/mctl-gitops#2259) is still in the
  account; owner's decision to delete it is separate from this spike.
- Keep `cloudflare_ai_gateway.mctl_support` and the three token changes: they are declared,
  applied and harmless at zero traffic.
- The run token in Vault stays until the gateway is either adopted or the resource is removed;
  removing the resource must be paired with deleting the token (manifest and Vault).
- Not observed, therefore unknown: Nebius console figures for the window; gateway behaviour
  under streaming responses (the harness used non-streaming calls); behaviour at the
  per-model rate limits the gateway can enforce (left at 0/off).
