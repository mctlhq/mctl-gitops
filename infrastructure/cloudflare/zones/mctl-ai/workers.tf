# Worker routes for mctl-landing-form (mctlhq/mctl-gitops#1179).
#
# Ownership split, #1089 item 9 / README decision 9: the route objects are
# owned here; the worker script and its runtime secrets stay in Wrangler
# (mctlhq/mctl-web, cloudflare-worker/). Only the route is declared -- `script`
# names the worker, it does not manage it.
#
# The patterns are the worker's contract: index.js decides what to do from the
# host and path it is routed, so a pattern change here changes what its bot
# filter and redirect code see. Change them here, never in wrangler.toml.
#
# Not representable in provider 5.24 and so not managed: the API's
# `request_limit_fail_open` (false on every route, the default).

# mctl.ai/api/* -- the landing form's submit and provisioning API.
resource "cloudflare_workers_route" "landing_form_api" {
  zone_id = local.zone_id
  pattern = "mctl.ai/api/*"
  script  = "mctl-landing-form"
}
