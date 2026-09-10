# Cloudflare — zone `mctl.ai`

The zone that serves the platform. Imported by #1115, which was split out of
#1088 because that issue bundled this zone-scoped slice with the account-scoped
Access one — different roots, different blockers.

## Scope

22 objects: 13 DNS records, the `http_request_firewall_custom` ruleset, seven
Email Routing forward rules and the catch-all.

`A *.mctl.ai` is the path every tenant host resolves through. Nothing else in
this root is as load-bearing.

## Deliberately not here

- **`jellyfin.mctl.ai` and `media.mctl.ai`**, and the ruleset
  `mac-mini media cache policy` (`e74a2913…`, phase
  `http_request_cache_settings`). All three are owned by `mashkovd/mac-mini-infra`
  until #1090 transfers them; importing them here would create dual management.
  The two DNS records carry the comment `Managed by mac-mini-infra OpenTofu`;
  **the ruleset carries no marker at all** and is identifiable only by its name,
  which makes it the easiest of the three to import by accident.
  `media.mctl.ai` does appear in this root — inside the `seerr` rule's host
  list, as a string in a WAF expression. That is not the DNS record.
- **Email Routing verification status** — runtime state, per `mctlhq/.github#47`.

## The `seerr` rule

Super Bot Fight Mode is skipped for the platform's own server-to-server calls,
which arrive from Hetzner (AS24940) and were being classified as bot traffic.
Until #1089 item 8 it was an ASN-wide bypass across the whole zone — every
Hetzner customer, on every host including the wildcard.

The host list is narrow and therefore fragile in one direction: a host that
belongs on it and is missing does not fail at the edge, it surfaces as an
unexplained `403` inside whichever service made the call. `../../README.md`
records where the list came from and which caller each entry serves.

## State

Local, and listed in `../../.local-state-roots`, like the other two zone roots.
Proving zero diff needs no write access; keeping state on R2 does, and the
apply identity does not exist yet (#1111).

## Evidence

Generated, reduced, re-planned, imported into throwaway local state, re-planned
again — with the read-only plan identity:

```
Plan: 21 to import, 0 to add, 0 to change, 0 to destroy.
Apply complete! Resources: 21 imported, 0 added, 0 changed, 0 destroyed.
tofu plan -> No changes.
```

The counts above are what the import run itself printed and are left as they
were. The 22nd object arrived afterwards: the Google Search Console TXT record
at the apex, created through the API because this root cannot apply, then
pinned here with an `import` block so the plan stays empty. CI re-proved it on
that change:

```
Plan: 22 to import, 0 to add, 0 to change, 0 to destroy.
```

## Zone settings

`min_tls_version` and `always_use_https` are declared in `tls.tf` as of #1154,
and `ssl` as of #1153. This root does not use `modules/zone-baseline`, so it
carries its own copy; the values are the same on purpose.

Zone settings always exist at Cloudflare — there is no unset, only a default —
so they import rather than create.

The values were applied through the Cloudflare API **before** this landed, the
same way the Google Search Console TXT record was: these roots keep local state
and cannot apply from CI (#1111), and their whole verification ritual runs on
the read-only plan identity. Declaring a value the configuration cannot reach
would have left `cloudflare-drift.yml` — which fails closed — red on every
scheduled run until someone got round to it.

So the plan stays zero-diff and the rule above never bends:

```
Plan: 26 to import, 0 to add, 0 to change, 0 to destroy.
```

(Twenty-six: the twenty-two from the import run and the Search Console record,
plus the MCP Portal record from #1092 and these three settings.)

`ssl` is declared and is `strict` as of 2026-09-10. It was `full` while the
origin presented `TRAEFIK DEFAULT CERT` for every name except the apex; #1153
fixed that by giving Traefik a Cloudflare Origin CA certificate as its default,
which is what made `strict` reachable.
