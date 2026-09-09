locals { zone_id = "86a90fe2fdfe87b9702842218b607f60" }

import {
  to = cloudflare_dns_record.apex
  id = "${local.zone_id}/3d7254ca1bbccadf4d676d3e723f7abb"
}

import {
  to = cloudflare_dns_record.wildcard
  id = "${local.zone_id}/637682af8d2f8fce1a0c9297372b1156"
}

import {
  to = cloudflare_dns_record.mx_route1
  id = "${local.zone_id}/1fbcc656c43f5afb8547a3ec5e629f86"
}

import {
  to = cloudflare_dns_record.mx_route2
  id = "${local.zone_id}/04e6a8a999871a8d9a9cae0cbfcf504a"
}

import {
  to = cloudflare_dns_record.mx_route3
  id = "${local.zone_id}/223bdddc2f513a767a4f57907b504357"
}

import {
  to = cloudflare_dns_record.send_mx
  id = "${local.zone_id}/7b33877822e206611ceadfa02e6d340e"
}

import {
  to = cloudflare_dns_record.send_spf
  id = "${local.zone_id}/c05888ab158e42add4d631e4cde952e8"
}

import {
  to = cloudflare_dns_record.spf
  id = "${local.zone_id}/389e959e9d7a5b06dd8a65e4bb4a7abf"
}

import {
  to = cloudflare_dns_record.dmarc
  id = "${local.zone_id}/501ffd5aef9bc97521a7947c3b6daf1f"
}

import {
  to = cloudflare_dns_record.cf_dkim
  id = "${local.zone_id}/d8ecf472d42885195f15570726b173b0"
}

import {
  to = cloudflare_dns_record.resend_dkim
  id = "${local.zone_id}/b37e5d531649ab8782b5740d819ec218"
}

import {
  to = cloudflare_dns_record.gh_org_verify
  id = "${local.zone_id}/32501e8309717c5e139f5a4ef42fb34b"
}

import {
  to = cloudflare_ruleset.firewall_custom
  id = "zones/${local.zone_id}/4bdd5c0da7004933b40aae8fd0d5ce78"
}

import {
  to = cloudflare_email_routing_rule.dmitrii
  id = "${local.zone_id}/ebfa0baa875e431fada134bef5e3aae4"
}

import {
  to = cloudflare_email_routing_rule.agent
  id = "${local.zone_id}/a8d61cb4db0146f3bac8462a82d9e2e7"
}

import {
  to = cloudflare_email_routing_rule.ci
  id = "${local.zone_id}/c533d2b5b4ae4a9491652dcc9b24742a"
}

import {
  to = cloudflare_email_routing_rule.privacy
  id = "${local.zone_id}/e4e5c2d43cc64fb3a56c431feb18e7be"
}

import {
  to = cloudflare_email_routing_rule.noreply
  id = "${local.zone_id}/7241cdb2af2045a1b38fb79f9d29e164"
}

import {
  to = cloudflare_email_routing_rule.support
  id = "${local.zone_id}/5c767a0b4b0d44ca822fbe4fff07f57e"
}

import {
  to = cloudflare_email_routing_rule.security
  id = "${local.zone_id}/2c1be7061fda45588a4cb118b41419e5"
}

import {
  to = cloudflare_email_routing_catch_all.default
  id = local.zone_id
}
