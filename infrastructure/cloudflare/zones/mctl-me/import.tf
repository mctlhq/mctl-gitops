# Import of the mctl.me zone — see mctlhq/mctl-gitops#1103.
#
# Object IDs captured from a read-only inventory on 2026-09-09, after the #1089
# hygiene pass. Two objects that inventory would have shown a day earlier are
# deliberately absent:
#
#   * NS launch1/launch2.spaceship.net, deleted as #1089 item 6 — registrar
#     leftovers that the authoritative servers never served to anyone;
#   * page rule *.mctl.me/*, deleted as #1089 item 5 — it matched the same
#     subdomains as the mctl-landing-form worker route and never fired,
#     because the worker runs first and returns.
#
# Also absent: the worker routes mctl.me/* and *.mctl.me/* . #1089 item 9
# settled that routes belong in OpenTofu and the script stays in Wrangler, but
# they are their own slice — see README.md.

locals {
  zone_id = "b0a1f8992b5d4221faf4541a9f75a329" # mctl.me
}

import {
  to = module.baseline.cloudflare_dns_record.apex
  id = "${local.zone_id}/95028b3a4a1f2ff1fd6948df81a45713"
}

import {
  to = module.baseline.cloudflare_dns_record.wildcard
  id = "${local.zone_id}/3f06d1248c352c21eb488938deb6427d"
}

import {
  to = cloudflare_dns_record.www
  id = "${local.zone_id}/e4455f64716ca93bff8f44fefbfd0382"
}

import {
  to = cloudflare_dns_record.platform
  id = "${local.zone_id}/18ce6cb1c003cbffd5ddd515f3d86772"
}

import {
  to = cloudflare_dns_record.send_mx
  id = "${local.zone_id}/6c3e99ecf2c38cc8e2dcb396bd535ab9"
}

import {
  to = cloudflare_dns_record.send_spf
  id = "${local.zone_id}/94c512f3859465ff1889cb0f1f1f78de"
}

import {
  to = cloudflare_dns_record.resend_dkim
  id = "${local.zone_id}/e724c28b99688a097e298359ed7a2d54"
}

import {
  to = cloudflare_dns_record.dmarc
  id = "${local.zone_id}/aefa80e04e20875ce45f60e299784314"
}

import {
  to = cloudflare_dns_record.tbolt
  id = "${local.zone_id}/06c14ea8dc7bc344b510b7f89a3f78bd"
}

import {
  to = module.baseline.cloudflare_ruleset.dynamic_redirect
  id = "zones/${local.zone_id}/5e32eee356bf4fbda2594b2e88582beb"
}

import {
  to = module.baseline.cloudflare_ruleset.firewall_custom
  id = "zones/${local.zone_id}/d68f1fba61ab47649c23d572eea25c4b"
}
