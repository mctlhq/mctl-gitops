# Cloudflare — zone `mctl.ru`

Zero-diff import pilot for `mctlhq/.github#47`, tracked in `mctlhq/mctl-gitops#1087`.

## Scope

Two DNS records:

| Resource | Record |
| --- | --- |
| `cloudflare_dns_record.apex` | `A mctl.ru` → `91.98.10.188`, proxied |
| `cloudflare_dns_record.wildcard` | `A *.mctl.ru` → `91.98.10.188`, proxied |

Deliberately **not** managed here:

- `TXT _acme-challenge.mctl.ru` — a DNS-01 challenge digest rotated by the
  certificate issuer. Pinning it in Git would let a later write-capable apply
  restore a stale digest over a live challenge and break renewal. Leaving it
  out of the configuration is safe: OpenTofu only destroys what it tracks.
- rulesets `http_request_dynamic_redirect` (301 apex → `https://mctl.ai`) and
  `http_request_firewall_custom` (block `.php`)
- page rule `*.mctl.ru/*` → 301 `https://$1.mctl.ai/$2`
- worker routes `mctl.ru/*` and `*.mctl.ru/*` → `mctl-landing-form`
  (blocked on the OpenTofu-vs-Wrangler ownership decision, #1089)

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
