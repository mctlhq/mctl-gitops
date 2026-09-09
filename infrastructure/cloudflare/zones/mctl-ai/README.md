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
