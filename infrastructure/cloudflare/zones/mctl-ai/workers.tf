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

# glovo.mctl.ai -- the landing page, served by the glovo-landing worker
# (mctlhq/mctl-glovo, landing-worker/). Cloudflare matches a route pattern
# against the WHOLE request URL, query string included, and a pattern may not
# itself contain a query ("example.com/?x=*" is invalid), so "glovo.mctl.ai/"
# matches the bare root only: "/?lang=en" (what the language switcher links
# to) fell through to the tunnel origin and got a stale copy. The only way to
# match a URL with a query is a trailing wildcard. Docs:
# https://developers.cloudflare.com/workers/configuration/routing/routes/
#
# Hence three more routes. When several patterns match, the most specific
# wins, and a route with no script makes matching requests bypass Workers:
#   glovo.mctl.ai/*             -> glovo-landing  (root with a query; anything
#                                  else reaches the worker, which answers 404,
#                                  as the origin does for every other path)
#   glovo.mctl.ai/mcp*          -> no script      (stays on the tunnel origin)
#   glovo.mctl.ai/.well-known/* -> no script      (stays on the tunnel origin)
# The origin serves only /, /mcp and /.well-known/*, so nothing else is lost.
# scripts/validate-cloudflare-glovo-routes.py pins this set. Rollback: remove
# the three added resources; the origin serves the same page as a fallback.
resource "cloudflare_workers_route" "glovo_landing" {
  zone_id = local.zone_id
  pattern = "glovo.mctl.ai/"
  script  = "glovo-landing"
}

resource "cloudflare_workers_route" "glovo_landing_query" {
  zone_id = local.zone_id
  pattern = "glovo.mctl.ai/*"
  script  = "glovo-landing"
}

resource "cloudflare_workers_route" "glovo_origin_mcp" {
  zone_id = local.zone_id
  pattern = "glovo.mctl.ai/mcp*"
}

resource "cloudflare_workers_route" "glovo_origin_well_known" {
  zone_id = local.zone_id
  pattern = "glovo.mctl.ai/.well-known/*"
}
