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
    # Backup-file scanners request thousands of invented archive names
    # (/dumps.zip, /known_hosts.zip, ...) in a burst. The landing site serves no
    # archives, HTML is never cached at the edge, so every one of those requests
    # reached Traefik: on 2026-10-06 03:40 UTC one client sent 3,223 of them in
    # a minute and all three Traefik replicas restarted. Blocking at the edge
    # keeps that traffic out of the cluster.
    #
    # Scoped to the apex host on purpose. Other hosts in this zone serve these
    # extensions legitimately -- git.mctl.ai repository archives, tenant
    # downloads -- and must not be caught by it.
    {
      action      = "block"
      description = "mctl.ai: block archive and dump probes (the site serves none)"
      enabled     = true
      expression  = "(http.host eq \"mctl.ai\" and http.request.uri.path.extension in {\"7z\" \"bak\" \"bz2\" \"dump\" \"gz\" \"rar\" \"sql\" \"tar\" \"tgz\" \"xz\" \"zip\" \"zst\"})"
      ref         = "block_archive_probes_apex"
    },
  ]
  zone_id = local.zone_id
}
