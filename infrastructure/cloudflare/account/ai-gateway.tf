# AI Gateway for the mctl-support model calls (spike #2262, Phase A).
#
# The question of the spike is whether Cloudflare's per-request accounting
# (requests, tokens, cost, errors) can serve as an independent reference for
# mctl-support's own spend ledger. This gateway is the object under test. In
# Phase A nothing in production points at it: mctl-support keeps calling
# Nebius directly, and only a bounded off-production harness sends traffic
# through here (docs/spikes/, report to follow). Phase B, which would set
# NEBIUS_BASE_URL on the service, needs the accepted report and a mctl-support
# release that can send the gateway header.
#
# Settings, and why each is fixed rather than left at the dashboard default:
#   * collect_logs = false. Tenant prompts and model replies must not be stored
#     in Cloudflare. The analytics (counts, tokens, cost) do not depend on
#     logs. Verified after apply by reading the gateway back and, after the
#     harness traffic, by checking that the logs view holds no entries.
#   * authentication = true. Every request must carry
#     `cf-aig-authorization: Bearer <token>` next to the provider key, so a
#     leaked gateway URL alone spends nothing. The token is
#     `mctl-support-ai-gateway-run` in ../tokens/manifest.tf; its value lives
#     only in Vault secret/platform/mctl-support/ai-gateway.
#   * cache_ttl = 0. A cached reply would be counted by the gateway and not by
#     the provider, which is exactly the discrepancy the spike must not
#     manufacture. cache_invalidate_on_update is required by the provider and
#     has no effect while the TTL is 0.
#   * rate limiting off (interval 0, limit 0, the API's own "off" encoding,
#     as the pre-existing gateway `test` shows). AI Gateway has no observe-only
#     rate limit, and an enforced one would hide provider errors behind 429s.
#   * no provider keys stored (no BYOK): the Nebius key stays in the request
#     from the caller and in Vault.
#
# Not prevent_destroy: removing the gateway is the no-go outcome of the spike,
# applied with allow_destroy on cloudflare-apply.
#
# Creating it needs `Account -> AI Gateway: Edit` on CF_APPLY_TOKEN_ACCOUNT,
# and refreshing it needs `AI Gateway: Read` on the plan token. Both edits are
# declared in ../tokens/manifest.tf.
resource "cloudflare_ai_gateway" "mctl_support" {
  account_id = var.account_id
  id         = "mctl-support"

  collect_logs   = false
  authentication = true

  cache_ttl                  = 0
  cache_invalidate_on_update = true

  rate_limiting_interval  = 0
  rate_limiting_limit     = 0
  rate_limiting_technique = "fixed"

  # Server-side defaults the API returns. Provider 5.24.0 modelled them as
  # optional and not computed, so undeclared they planned as an in-place
  # update to null on every run (seen on the #2268 plan; upstream issue
  # cloudflare/terraform-provider-cloudflare#7336, fixed in 5.26.0). Declared
  # at their live values; none of them is a choice. log_management only
  # applies while collect_logs is true. The same bug left the computed
  # otel and spend_limits "known after apply" on every plan, which no
  # declaration can silence: that is why this root's lock pins 5.28.1 while
  # the other Cloudflare roots stay on 5.24.0.
  log_classification      = false
  log_management          = 100000
  log_management_strategy = "DELETE_OLDEST"
  logpush                 = false
  zdr                     = false
}

# The gateway base URL is an identifier, not a secret. The route under it
# (native provider, compat, or custom provider) is what the spike discovers.
output "mctl_support_ai_gateway_url" {
  value = "https://gateway.ai.cloudflare.com/v1/${var.account_id}/${cloudflare_ai_gateway.mctl_support.id}"
}
