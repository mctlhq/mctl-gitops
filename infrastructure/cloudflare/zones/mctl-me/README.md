# `mctl.me`

A redirect-only zone. Everything that serves traffic lives on `mctl.ai`; this
zone exists so the old domain keeps working. Imported by #1103.

## What is here

The four objects both redirect zones share come from
`../../modules/zone-baseline`: the apex and wildcard `A` records, the apex
redirect ruleset, and the `.php` scanner block. What is left in this root is
what `mctl.ru` has no equivalent of — `www` and `platform` hosts, and the
SES/Resend mail records.

## What redirects what

Worth knowing before changing anything here, because the intuitive answer is
wrong:

- **apex** — the `http_request_dynamic_redirect` ruleset in the module;
- **subdomains** — the `mctl-landing-form` worker, in code.

The page rule that appeared to redirect subdomains never fired and was deleted
as #1089 item 5. So a change to that worker's routes moves the subdomain
redirect, and nothing in this root will catch that regression. See the redirect
subsection in `../../README.md`.

## Deliberately not here

- **Worker routes `mctl.me/*` and `*.mctl.me/*`.** #1089 item 9 settled the
  ownership question — routes in OpenTofu, script and secrets in Wrangler — but
  both zones' routes point at one shared worker, so they are their own slice
  rather than part of a per-zone baseline.
- **The in-zone `NS launch1/launch2.spaceship.net` records.** Registrar
  leftovers, deleted as #1089 item 6; the authoritative servers never served
  them.

## State

Local, and listed in `../../.local-state-roots`. Proving zero diff needs no
write access — the import below ran against a throwaway state file with a
read-only token — but *keeping* state on R2 is a write, and the apply identity
does not exist yet (#1111). The migration is that issue's follow-on.

## How the configuration got here

Generated, then reduced, then re-verified — do not hand-write resource bodies:

1. write `import.tf` only, then `tofu plan -generate-config-out=generated.tf`;
2. reduce: the generator emits every optional attribute as an explicit `null`;
3. **re-run the plan.** This is not a formality. The first reduction of this
   zone set `ttl = 1` on `send.mctl.me` TXT and `resend._domainkey`, which
   actually carry `3600`, and the re-plan is what caught it —
   `11 to import, 0 to add, 2 to change` instead of `0 to change`.

Evidence for the final state:

```
Plan: 11 to import, 0 to add, 0 to change, 0 to destroy.
Apply complete! Resources: 11 imported, 0 added, 0 changed, 0 destroyed.
tofu plan -> No changes.
```

The token used was the read-only plan identity, negative-control verified: a
`POST` creating a DNS record in this zone is refused (`10000`). Nothing in this
procedure can mutate Cloudflare.

## Zone settings — the one place this root is not zero-diff

`min_tls_version` and `always_use_https` are declared in the shared baseline as
of #1154. They are the first objects in this root whose live value the
configuration deliberately disagrees with, so the rule above — a plan with a
change means stop — does not apply to them, once, on that change.

Zone settings always exist at Cloudflare; there is no unset, only a default.
They therefore import rather than create. `always_use_https` was already `on`
here, so only the TLS floor moves:

```
Expect: 13 to import, 0 to add, 1 to change, 0 to destroy.
        ~ cloudflare_zone_setting.min_tls_version  value: "1.0" -> "1.2"
```

After that apply the plan is `No changes` again and the rule is back in force.
