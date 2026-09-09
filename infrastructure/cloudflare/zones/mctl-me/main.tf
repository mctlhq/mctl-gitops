# mctl.me — a redirect-only zone. Everything that serves traffic lives on
# mctl.ai; this zone exists so the old domain keeps working.

locals {
  # Shared origin for the platform zones. Every host resolves through the
  # wildcard in the module below.
  origin_ip = "91.98.10.188"
}

module "baseline" {
  source = "../../modules/zone-baseline"

  zone_id         = local.zone_id
  zone_name       = "mctl.me"
  origin_ip       = local.origin_ip
  redirect_target = "https://mctl.ai"

  # Carried over from the live rules so the import is byte-identical; see the
  # module's variable descriptions for why a ref has to be pinned.
  redirect_rule_ref = "cbb38ce1f4ef42d8ad652000b252051f"
  firewall_rule_ref = "c30653ba02504f5f8f02a4c9ac264f3f"
}
