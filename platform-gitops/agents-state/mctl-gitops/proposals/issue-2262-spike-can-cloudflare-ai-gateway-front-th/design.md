# Design: issue-2262-spike-can-cloudflare-ai-gateway-front-th

## Current state

### mctl-support model path (source: mctlhq/mctl-support `main`, read via `gh api`)

- `src/mctl_support/config.py`: `PROVIDERS = ("anthropic", "hetzner", "nebius")`.
  `DEFAULT_NEBIUS_BASE_URL = "https://api.tokenfactory.nebius.com/v1"`, read from
  `NEBIUS_BASE_URL` (line ~332, `.strip().rstrip("/")`). `HETZNER_BASE_URL` is read the
  same way. There is no `ANTHROPIC_BASE_URL` field in `Config`.
- `src/mctl_support/app.py` (lines 64-67): `AnthropicProvider(config.anthropic_model,
  key)` is built with no `base_url`, so the official `anthropic` SDK falls back to its own
  `ANTHROPIC_BASE_URL` env var. `OpenAICompatibleProvider(model, key, base_url)` is used
  for Nebius and Hetzner.
- `src/mctl_support/agent/providers/openai_compatible.py`: it POSTs to
  `base_url + "/chat/completions"` with exactly one header,
  `{"Authorization": f"Bearer {self._key}"}`. There is no hook for extra headers.
  **Consequence:** an authenticated AI Gateway requires `cf-aig-authorization: Bearer
  <gateway token>` next to the provider key, which mctl-support 0.3.6 cannot send. The
  issue's premise of "no code change beyond a base URL" holds only for an
  unauthenticated gateway, and the issue forbids that.
- `src/mctl_support/budget/ledger.py`: the Postgres spend ledger (`spend_periods`,
  `spend_turns`, `usage_outbox`). It reserves before each provider call and settles
  with actual cost. Cost is computed from `MODEL_INPUT_USD_PER_MTOK` /
  `MODEL_OUTPUT_USD_PER_MTOK`. This is "the agent's own spend counters".

### mctl-gitops

- `platform-gitops/services/admins/mctl-support/values.yaml`: `MODEL_PROVIDER: nebius`,
  `NEBIUS_MODEL: zai-org/GLM-5.1`, prices 1.40/4.40 USD per Mtok. The provider key
  comes from ExternalSecret `admins-mctl-support-model`, which reads Vault
  `secret/data/platform/mctl-support/model` property `nebius-api-key` through the
  `vault-backend` ClusterSecretStore. A comment states `NEBIUS_BASE_URL` is left unset
  because "the deploy tooling's yq rewrite has been seen stripping colon-bearing env
  values". Another comment states the Anthropic organization is disabled: every key
  answers 401.
- `infrastructure/cloudflare/README.md`: OpenTofu `>= 1.9`, `cloudflare/cloudflare ~> 5`,
  one root per directory with `versions.tf`, state in R2 `mctl-cloudflare-state`.
  Applies are manual through `.github/workflows/cloudflare-apply.yml` (plan job, then
  an apply job gated by the `cloudflare-apply` environment reviewer, with a digest
  check). Drift runs nightly in `cloudflare-drift.yml`.
- `infrastructure/cloudflare/account/`: account-scoped resources such as
  `workers-kv.tf` and `r2.tf`. The header comment of each file names the permission
  the apply token (`CF_APPLY_TOKEN_ACCOUNT`) and plan token (`CF_ACCOUNT_READ_TOKEN`)
  need. Neither file mentions AI Gateway today.
- `infrastructure/cloudflare/tokens/manifest.tf`: declares every account API token
  with its permission groups (`local.pg.*`). `mctl-gitops-plan-account
  (CF_ACCOUNT_READ_TOKEN)` and `mctl-gitops-apply-account (cloudflare-iac #1111)` hold
  no AI Gateway permission group, and no `local.pg` entry exists for AI Gateway.
  `tokens/README.md` rule: tokens are made in the dashboard and declared here in the
  same PR, and values never enter state.
- No `ai_gateway` or "AI Gateway" reference exists anywhere under `infrastructure/`.
  The gateway `test` found by mctl-gitops#2259 is unmanaged.

Deployed state checked:
- `mctl_get_service_config(admins, mctl-support)`: imageTag `0.3.6`, host
  `support.mctl.ai`, port 8080, base-service, hasDatabase true.
- `mctl_get_service_status(admins, mctl-support)`: Argo CD `admins-mctl-support`
  Healthy / Synced, updated 2026-10-29T17:32:12Z.
- `$MCTL_GITOPS_ROOT/services/admins/mctl-support/values.yaml`: as described above.
  `NEBIUS_BASE_URL` is not set, so the service default (direct Nebius) is in effect.
- The Cloudflare account's AI Gateway list, the `test` gateway's settings, and the
  provider schema for `cloudflare_ai_gateway` were not observed. This run has no
  Cloudflare credentials, and they are recorded as open questions.
- The Nebius console and the live ledger contents were not observed (no access).

## Proposed solution

A two-phase spike. Phase A changes only Cloudflare (through IaC) and adds a report.
Phase B is conditional and is the go PR.

### Phase A: observe (no production values change)

1. **Gateway in IaC.** Add `infrastructure/cloudflare/account/ai-gateway.tf` with one
   `cloudflare_ai_gateway` resource, id `mctl-support`:
   - log collection off (`collect_logs = false`), or metadata-only if the provider
     schema exposes that and it is verified to omit bodies. The setting actually
     applied is written into the report.
   - authentication on (`authentication = true`), so a request must present
     `cf-aig-authorization`.
   - cache off (`cache_ttl = 0`), so cached replies cannot distort token counts.
   - rate limiting either off or set well above the mctl-support turn rate. It is
     observed, not enforced.
   - no provider keys. BYOK is not used: the provider key stays in the request from
     the caller and in Vault.
   The file header follows the `workers-kv.tf` convention and names the needed
   permission groups. Exact attribute names are checked against the pinned provider
   schema (`tofu providers schema -json`) before the PR. If the resource does not
   exist in `~> 5`, Phase A stops with blocker "gateway not declarable in IaC".
2. **Token changes, declared.** In `tokens/manifest.tf`, add `local.pg.ai_gateway_read`
   and `local.pg.ai_gateway_write` (ids read from the permission-groups API). Add read
   to `mctl-gitops-plan-account (CF_ACCOUNT_READ_TOKEN)` and write to
   `mctl-gitops-apply-account (cloudflare-iac #1111)`. Add one new account-owned token
   `mctl-support-ai-gateway-run (Vault platform/mctl-support/ai-gateway)` with only the
   AI Gateway run permission. The dashboard edit and the manifest go in the same PR, as
   `tokens/README.md` requires. The run token value goes straight into Vault
   `secret/data/platform/mctl-support/ai-gateway`, property `token`.
3. **Apply.** After merge, dispatch `cloudflare-apply.yml` with
   `root=infrastructure/cloudflare/account` and approve the plan, which should show
   exactly one create. Read the gateway back via the API and record the log, auth and
   cache settings.
4. **Route discovery.** Send one minimal non-tenant prompt per candidate route. Use a
   dedicated spike Nebius key stored in Vault next to the production key, or the
   production key if the owner allows. Candidate routes, in order: the native provider
   path, if Nebius is listed; the OpenAI-compatible `compat/chat/completions` path; a
   custom provider pointing at `api.tokenfactory.nebius.com/v1`. Record the status
   and **response body** for each route. If none works, repeat with Anthropic using a
   labs key, if a non-disabled one exists. Record both outcomes.
5. **Logging verification.** After the test traffic, confirm in the gateway logs view
   (and via the logs API) that no request or response bodies exist. The report
   records what was observed, not what was configured.
6. **Comparison window.** Run a fixed, bounded harness: N synthetic support-style
   prompts with tool definitions, using the same adapter as mctl-support
   (`OpenAICompatibleProvider` from mctl-support `0.3.6`, with the extra header
   injected in the harness only). Run it through the gateway in one UTC window and
   compute cost with mctl-support's own formula and prices. For the same window, take:
   (a) gateway analytics, (b) Nebius console usage for the harness key, (c) the
   harness-side ledger computation, and (d) the production ledger totals versus the
   Nebius console for the production key. (d) calibrates the agent's counters against
   the same reference. Also record p50/p95 latency, gateway versus direct, for the
   same prompts.
7. **Report.** Add `docs/spikes/2026-11-cloudflare-ai-gateway-mctl-support.md`
   containing: the questions from the issue, the routes tried with bodies, the
   verified logging setting, the comparison table with deltas, the latency deltas, the
   auth finding about the adapter header, and the go/no-go. Post the summary on #2262.

### Phase B: go PR (only after the report is accepted)

- Precondition: mctl-support ships a way to send the gateway auth header (follow-up
  issue in mctlhq/mctl-support, e.g. an optional `MODEL_GATEWAY_TOKEN` env that adds
  `cf-aig-authorization`). Without it, Phase B is blocked and the report says so.
- `platform-gitops/services/admins/mctl-support/values.yaml`: add a data entry
  `MODEL_GATEWAY_TOKEN` to `extraExternalSecrets.admins-mctl-support-model`, reading
  `secret/data/platform/mctl-support/ai-gateway` property `token`. Set
  `NEBIUS_BASE_URL` to the gateway route proven in step 4. Rewrite the comment that
  says it is left unset. Verify the rendered Deployment with `helm template` and verify
  the live env after sync, because of the colon-stripping caveat.

## Alternatives

- **Unauthenticated gateway, base-URL-only switch (no code change).** This matches the
  issue's "no code change beyond a base URL", but the issue explicitly requires
  `cf-aig-authorization`. An open gateway URL also lets anyone who learns it spend
  against the analytics and rate limits. Dropped.
- **BYOK: provider key stored in Cloudflare, gateway token only in the pod.** This
  removes the dual-header need, but it places the provider key in Cloudflare, which
  the issue rules out. Dropped.
- **Run the comparison directly in production by switching `NEBIUS_BASE_URL` for a
  window.** This gives the cleanest gateway-versus-ledger comparison, but it violates
  "nothing changes in production values until the report is accepted" and currently
  needs the code change anyway. Kept only as the post-acceptance validation in
  Phase B. A clarification question asks whether the owner prefers it.
- **Create or configure the gateway in the dashboard (or reuse `test`).** This is
  faster, but the issue and `infrastructure/cloudflare/README.md` both require Git as
  the desired state. Dropped.

## Platform impact

- **Production:** none in Phase A. mctl-support keeps calling Nebius directly.
- **Cloudflare account:** one new gateway, one new API token, and two widened CI
  tokens. All are visible to `cloudflare-drift.yml` and the `tokens` root check.
- **Cost:** Workers Paid already covers AI Gateway. The harness spend is bounded by N
  prompts at GLM-5.1 prices, well under 1 USD. Set N so the total stays below 0.50 USD.
- **Data:** only synthetic prompts pass through the gateway in Phase A, with logging
  off. Tenant prompts first transit Cloudflare (not stored) in Phase B.
- **Risks and mitigations:**
  - The provider schema lacks the resource or a logging field: stop and report. The
    dashboard is not an acceptable fallback.
  - Logging off still retains bodies: verified by reading the logs view after
    traffic. If bodies appear, the outcome is no-go.
  - Widening the CI tokens is a privilege change: read only on the plan token, edit
    only on the apply token, and both are reviewed in the tokens-root plan.
  - Gateway latency adds to each turn: measured in step 6. A p95 increase that pushes
    tasks past existing timeouts is a no-go reason.
  - In Phase B, Cloudflare becomes a single point of failure for support answers.
    Rollback is unsetting `NEBIUS_BASE_URL`.
- **Backward compatibility:** the gateway resource is additive. Removing it is a
  destroy that needs `allow_destroy` on `cloudflare-apply.yml`.
