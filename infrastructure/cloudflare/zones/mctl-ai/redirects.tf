# www.mctl.ai resolves through the `*.mctl.ai` wildcard and reaches Traefik,
# which has no route for it, so it answered 404. Google Search Console listed it
# as a not-found page of the site. The landing page lives on the apex.
#
# Same rule shape as the apex redirect in ../../modules/zone-baseline.
# http.request.uri already carries the query string, hence
# preserve_query_string = false.
resource "cloudflare_ruleset" "dynamic_redirect" {
  zone_id     = local.zone_id
  name        = "default"
  description = ""
  kind        = "zone"
  phase       = "http_request_dynamic_redirect"

  rules = [
    {
      ref         = "www_to_apex"
      description = "Redirect www.mctl.ai to mctl.ai"
      enabled     = true
      expression  = "(http.host eq \"www.mctl.ai\")"
      action      = "redirect"
      action_parameters = {
        from_value = {
          preserve_query_string = false
          status_code           = 301
          target_url = {
            expression = "concat(\"https://mctl.ai\", http.request.uri)"
          }
        }
      }
    },
  ]
}
