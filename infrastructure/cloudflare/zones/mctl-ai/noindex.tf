# Keep service hosts out of search results.
#
# Google Search Console lists these hostnames as pages of the site (2026-11-17,
# 90-day report): the user portal at app.mctl.ai, the lab proxy root at
# labs-pelican-proxy.mctl.ai (it answers 200 with JSON) and an OAuth link
# endpoint on api.mctl.ai. None of them is a landing page, and none should be a
# search result.
#
# A response header, not robots.txt, on purpose. A Disallow neither removes a URL
# that is already indexed nor lets Google see a noindex on it, so the page would
# stay listed with no description. `X-Robots-Tag: noindex` is read on the next
# crawl and drops the URL.
#
# Set at the edge so no service has to change. The header is harmless for API
# clients: MCP and OAuth traffic on api.mctl.ai ignores it. `set` replaces any
# value the origin sends; none of the three sends one today.
#
# Deliberately not listed:
#   - coolify.mctl.ai and seerrsense.mctl.ai are working sites that stay indexed.
#   - labs-seerrsense.mctl.ai is the base CNAME of seerrsense and may become a
#     redirect to it instead (tracked separately).
#
# noindex hides a page from search; it is not access control. Whether the
# labs-pelican-proxy root should be public at all is a separate question
# (Cloudflare Access), not answered here.
#
# Phase `http_response_headers_transform` has one ruleset per zone. If the live
# zone already carries an entrypoint for this phase, import it before applying
# rather than creating a second one.

resource "cloudflare_ruleset" "response_headers_transform" {
  zone_id     = local.zone_id
  name        = "default"
  description = ""
  kind        = "zone"
  phase       = "http_response_headers_transform"

  rules = [
    {
      ref         = "noindex_service_hosts"
      description = "Service hosts: X-Robots-Tag noindex (app, api, labs-pelican-proxy)"
      enabled     = true
      expression  = "(http.host in {\"app.mctl.ai\" \"api.mctl.ai\" \"labs-pelican-proxy.mctl.ai\"})"
      action      = "rewrite"
      action_parameters = {
        headers = {
          "X-Robots-Tag" = {
            operation = "set"
            value     = "noindex"
          }
        }
      }
    },
  ]
}
