variable "zone_id" {
  description = "Cloudflare zone ID this baseline applies to."
  type        = string
}

variable "zone_name" {
  description = "Apex name of the zone, e.g. mctl.me. Used in the record names and in the redirect rule's host match, so it must be the real apex rather than a label."
  type        = string
}

variable "origin_ip" {
  description = "Origin the apex and wildcard A records point at."
  type        = string
}

variable "redirect_target" {
  description = "Base URL the apex redirect sends traffic to, without a trailing slash."
  type        = string
}

variable "redirect_rule_ref" {
  description = "Existing rule ref of the dynamic-redirect rule, carried over on import so the imported rule matches the configuration byte for byte. Cloudflare assigns a ref when a rule is created; pinning it here is what keeps a re-plan at zero diff."
  type        = string
}

variable "firewall_rule_ref" {
  description = "Existing rule ref of the PHP-scanner block rule, for the same reason as redirect_rule_ref."
  type        = string
}
