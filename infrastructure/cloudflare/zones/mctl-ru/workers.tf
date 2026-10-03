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

# mctl.ru/* -- the apex. The redirect ruleset in module.baseline also matches
# it; the worker runs first.
resource "cloudflare_workers_route" "landing_form_apex" {
  zone_id = local.zone_id
  pattern = "mctl.ru/*"
  script  = "mctl-landing-form"
}

# *.mctl.ru/* -- every subdomain, redirected to *.mctl.ai by the worker.
resource "cloudflare_workers_route" "landing_form_subdomains" {
  zone_id = local.zone_id
  pattern = "*.mctl.ru/*"
  script  = "mctl-landing-form"
}
