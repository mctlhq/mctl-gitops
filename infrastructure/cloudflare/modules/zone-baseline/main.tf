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

# Edge TLS policy. Both zones sat on Cloudflare's defaults because zone
# settings were outside the scope of the #1089 import programme — they were
# never considered and deferred, they simply were not on the list.
#
# Both values were applied through the API on 2026-09-10, before this file
# declared them, so importing here is zero-diff. That order is deliberate:
# these roots cannot apply from CI while they hold local state (#1111), and a
# declared-but-unapplied value would leave the fail-closed drift check red.
#
# min_tls_version was "1.0". Over 2026-09-03..09 the four zones served
# 837 277 TLS handshakes and not one of them was TLS 1.0 or 1.1 — 832 003 were
# TLS 1.3 and the remaining 5 274 TLS 1.2 — so raising the floor to 1.2 refuses
# nothing that actually connects. It closes a downgrade path rather than
# changing behaviour.
#
# always_use_https was "on" for mctl.me and "off" for mctl.ru, which is the
# kind of difference that is an accident rather than a decision. Both redirect
# their apex to mctl.ai anyway, so plaintext requests here are redirected
# either way; declaring it makes the edge answer :80 with a 301 before the
# redirect ruleset runs, rather than serving that first hop in the clear.
#
# ssl is deliberately NOT declared. It is "full" on every zone and cannot be
# raised to "strict" today: the origin presents TRAEFIK DEFAULT CERT for every
# name except the mctl.ai and mctl.ru apexes, so strict would answer 526 for
# platform.mctl.me and every wildcard subdomain. Tracked in #1153.
resource "cloudflare_zone_setting" "min_tls_version" {
  zone_id    = var.zone_id
  setting_id = "min_tls_version"
  value      = "1.2"
}

resource "cloudflare_zone_setting" "always_use_https" {
  zone_id    = var.zone_id
  setting_id = "always_use_https"
  value      = "on"
}
