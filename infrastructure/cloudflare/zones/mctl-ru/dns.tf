# mctl.ru — a redirect-only zone, the same shape as mctl.me.
#
# The apex, the wildcard, the apex redirect and the .php block all moved into
# ../../modules/zone-baseline with #1103. What was here before was the pilot's
# hand-reduced copy of the first two; keeping a second copy of the same four
# resources is what the module exists to prevent.

locals {
  # Shared origin for the platform zones. Every host resolves through the
  # wildcard in the module below.
  origin_ip = "91.98.10.188"
}

module "baseline" {
  source = "../../modules/zone-baseline"

  zone_id         = local.zone_id
  zone_name       = "mctl.ru"
  origin_ip       = local.origin_ip
  redirect_target = "https://mctl.ai"

  redirect_rule_ref = "37cc4b9b960f4879acbe822e985d36d0"
  firewall_rule_ref = "298f62f070b54b489d10370595afa99b"
}

# Deliberately NOT managed here: TXT _acme-challenge.mctl.ru
#
# The value is a DNS-01 challenge digest rotated by the certificate issuer.
# Pinning it in Git would mean a later write-capable apply could restore a
# stale digest over a live challenge and break certificate renewal.
#
# An earlier revision imported it "so that a plan does not propose deleting
# it". That reasoning was wrong: OpenTofu only destroys resources it tracks,
# so a record absent from this configuration is simply left alone.
