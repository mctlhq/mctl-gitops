# Cloudflare — zone `mctl.ru`

Zero-diff import pilot for `mctlhq/.github#47`, tracked in `mctlhq/mctl-gitops#1087`.

## Scope

Two DNS records:

| Resource | Record |
| --- | --- |
| `module.baseline.cloudflare_dns_record.apex` | `A mctl.ru` → `91.98.10.188`, proxied |
| `module.baseline.cloudflare_dns_record.wildcard` | `A *.mctl.ru` → `91.98.10.188`, proxied |

Both rulesets — the apex redirect and the `.php` block — moved into
`../../modules/zone-baseline` with #1103 and are managed now, together with the
apex and wildcard records. This zone and `mctl.me` describe the same four
baseline objects through the same module.

Deliberately **not** managed here:

- `TXT _acme-challenge.mctl.ru` — a DNS-01 challenge digest rotated by the
  certificate issuer. Pinning it in Git would let a later write-capable apply
  restore a stale digest over a live challenge and break renewal. Leaving it
  out of the configuration is safe: OpenTofu only destroys what it tracks.
- worker routes `mctl.ru/*` and `*.mctl.ru/*` → `mctl-landing-form`.
  The ownership question is **settled** (#1089 item 9, 2026-09-09): the routes
  belong here, the script and its secrets stay in Wrangler, because OpenTofu
  does not deploy Worker code. They are still absent from this pilot only
  because importing them is #1103's work, not because anything is undecided.
  Do not read this entry as licence to skip them in the next slice.
- page rules — **deleted**, not deferred. They matched the same subdomains as
  the worker routes but never fired; the worker answers first. See the
  redirect subsection in `infrastructure/cloudflare/README.md`.

## Running the pilot

The resource configuration is already committed, so there is nothing left for
`-generate-config-out` to generate. Import blocks are *previewed* by a plan and
*executed* by an apply, so the import-only apply comes before the verification
plan — a first plan on a fresh checkout will report pending imports, not
`No changes`.

```sh
export CLOUDFLARE_API_TOKEN=...   # Zone:Zone:Read + Zone:DNS:Read is enough
tofu init

# 1. Preview. Expect: "2 to import, 0 to add, 0 to change, 0 to destroy".
#    Anything else — stop and investigate; do not continue.
tofu plan

# 2. Execute the imports. This writes state only.
tofu apply

# 3. Verify. Expect: "No changes."
tofu plan
```

Read scope is sufficient for all three steps: the apply imports rather than
mutates, so no write permission is required to prove zero diff.

Reversibility — this must leave Cloudflare untouched:

```sh
tofu state rm cloudflare_dns_record.apex cloudflare_dns_record.wildcard
```

Then re-read the records through the API and compare, including `modified_on`.
Unchanged timestamps are what proves nothing was written.

A plan containing create, update or destroy means stop and investigate. It does
not mean apply and re-import.
