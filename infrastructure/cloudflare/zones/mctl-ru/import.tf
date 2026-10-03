# Import of the mctl.ru zone — pilot #1087, completed by #1103.
#
# The two DNS records were the zero-diff pilot. The two rulesets were deferred
# then and arrive here, so this zone and mctl.me now describe the same four
# baseline objects through the same module.
#
# Deliberately absent:
#
#   * page rule *.mctl.ru/* — deleted as #1089 item 5. It matched the same
#     subdomains as the mctl-landing-form worker route and never fired, because
#     the worker runs first and returns.
#
# The worker routes mctl.ru/* and *.mctl.ru/* arrived later, with #1179: see
# the end of this file and workers.tf.

locals {
  zone_id = "a7ec983a32a4b15097fbb80b1f5f6924" # mctl.ru
}

import {
  to = module.baseline.cloudflare_dns_record.apex
  id = "${local.zone_id}/98d95445856c846ec72819617cfe3109"
}

import {
  to = module.baseline.cloudflare_dns_record.wildcard
  id = "${local.zone_id}/dc70fc9f9868d310840475dc32d6a425"
}

import {
  to = module.baseline.cloudflare_ruleset.dynamic_redirect
  id = "zones/${local.zone_id}/e5d94d2e57d943089eb3cc892741c36a"
}

import {
  to = module.baseline.cloudflare_ruleset.firewall_custom
  id = "zones/${local.zone_id}/c9b64fa93a0844a0a3a529b456aabec1"
}

# Zone settings are objects that always exist — Cloudflare has no notion of an
# unset setting, only its default. So these import rather than create, and the
# plan shows a change on the ones whose live value differs from the baseline.
import {
  to = module.baseline.cloudflare_zone_setting.min_tls_version
  id = "${local.zone_id}/min_tls_version"
}

import {
  to = module.baseline.cloudflare_zone_setting.always_use_https
  id = "${local.zone_id}/always_use_https"
}

import {
  to = module.baseline.cloudflare_zone_setting.ssl
  id = "${local.zone_id}/ssl"
}

# Worker routes (#1179), ids from a read-only GET /zones/{zone_id}/workers/routes
# on 2026-09-25. Resources in workers.tf.
import {
  to = cloudflare_workers_route.landing_form_apex
  id = "${local.zone_id}/8a4944f8e5844dd898269b663a7a1766"
}

import {
  to = cloudflare_workers_route.landing_form_subdomains
  id = "${local.zone_id}/b8df8f07796e4ae9b3554fcb9d99c36a"
}
