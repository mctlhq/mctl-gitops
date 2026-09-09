# The shape mctl.me and mctl.ru share: an apex and a wildcard pointing at the
# platform origin, an apex redirect to mctl.ai, and a block on .php probes.
#
# Every resource body below was produced by `tofu plan -generate-config-out`
# against the live zones and then reduced — the generator emits each optional
# attribute as an explicit null, which is noise rather than intent. What was
# parameterised is only what actually differs between the two zones. The
# zero-diff plan is what proves both the reduction and the parameterisation.
#
# Not in here, because the zones do not share it: mctl.me's mail records
# (SES/Resend) and its www/platform hosts. Those live in that zone's root.
#
# Also not in here: the worker routes. #1089 item 9 put routes in OpenTofu and
# the script in Wrangler, but both zones' routes point at one shared worker, so
# they are not a per-zone baseline.

resource "cloudflare_dns_record" "apex" {
  zone_id = var.zone_id
  name    = var.zone_name
  type    = "A"
  content = var.origin_ip
  proxied = true
  ttl     = 1 # 1 = automatic
}

resource "cloudflare_dns_record" "wildcard" {
  zone_id = var.zone_id
  name    = "*.${var.zone_name}"
  type    = "A"
  content = var.origin_ip
  proxied = true
  ttl     = 1
}

# Apex only. Subdomains are redirected by the mctl-landing-form worker, in
# code, and have been all along — the page rules that appeared to do it were
# never reached. See the redirect subsection in ../../README.md.
resource "cloudflare_ruleset" "dynamic_redirect" {
  zone_id     = var.zone_id
  name        = "default"
  description = ""
  kind        = "zone"
  phase       = "http_request_dynamic_redirect"

  rules = [
    {
      ref         = var.redirect_rule_ref
      description = "Redirect ${var.zone_name} to ${replace(var.redirect_target, "https://", "")}"
      enabled     = true
      expression  = "(http.host eq \"${var.zone_name}\")"
      action      = "redirect"
      action_parameters = {
        from_value = {
          preserve_query_string = false
          status_code           = 301
          target_url = {
            expression = "concat(\"${var.redirect_target}\", http.request.uri)"
          }
        }
      }
    },
  ]
}

resource "cloudflare_ruleset" "firewall_custom" {
  zone_id     = var.zone_id
  name        = "default"
  description = ""
  kind        = "zone"
  phase       = "http_request_firewall_custom"

  rules = [
    {
      ref               = var.firewall_rule_ref
      description       = "Block PHP scanner bots"
      enabled           = true
      expression        = "(http.request.uri.path contains \".php\")"
      action            = "block"
      action_parameters = {}
    },
  ]
}
