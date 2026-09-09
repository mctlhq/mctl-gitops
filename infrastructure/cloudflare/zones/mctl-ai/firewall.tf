# The `seerr` rule: Super Bot Fight Mode is skipped for the platform's own
# server-to-server calls, which arrive from Hetzner (AS24940) and were being
# classified as bot traffic.
#
# It was an ASN-wide bypass across the whole zone until #1089 item 8 narrowed
# it to the hostnames that actually need it. The host list is not decoration —
# `../../README.md` records where it came from and what happens when an entry
# is missing, which is a 403 inside whichever service made the call rather than
# an error at the edge.

resource "cloudflare_ruleset" "firewall_custom" {
  description = ""
  kind        = "zone"
  name        = "default"
  phase       = "http_request_firewall_custom"
  rules = [
    {
      action = "skip"
      action_parameters = {
        phases   = ["http_request_sbfm"]
        products = ["bic"]
      }
      description = "seerr — skip SBFM/BIC for in-cluster server-to-server calls (gitops#1089 item 8)"
      enabled     = true
      expression  = "(ip.src.asnum eq 24940 and http.host in {\"secrets.mctl.ai\" \"ops.mctl.ai\" \"app.mctl.ai\" \"api.mctl.ai\" \"media.mctl.ai\" \"tg.mctl.ai\" \"workflows.mctl.ai\"})"
      logging = {
        enabled = true
      }
      ref = "1493169d2b0947769321b3375a153715"
    },
  ]
  zone_id = local.zone_id
}
