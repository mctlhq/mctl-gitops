# Cloudflare — zone `mctl.ru`

Zero-diff import pilot for `mctlhq/.github#47`, tracked in `mctlhq/mctl-gitops#1087`.

## Scope

Three DNS records only:

| Resource | Record |
| --- | --- |
| `cloudflare_dns_record.apex` | `A mctl.ru` → `91.98.10.188`, proxied |
| `cloudflare_dns_record.wildcard` | `A *.mctl.ru` → `91.98.10.188`, proxied |
| `cloudflare_dns_record.acme_challenge` | `TXT _acme-challenge.mctl.ru` |

Deliberately **not** in this slice — they follow once the pilot is green:

- rulesets `http_request_dynamic_redirect` (301 apex → `https://mctl.ai`) and
  `http_request_firewall_custom` (block `.php`)
- page rule `*.mctl.ru/*` → 301 `https://$1.mctl.ai/$2`
- worker routes `mctl.ru/*` and `*.mctl.ru/*` → `mctl-landing-form`
  (blocked on the OpenTofu-vs-Wrangler ownership decision, #1089)

## Running the pilot

```sh
export CLOUDFLARE_API_TOKEN=...   # Zone:Zone:Read + Zone:DNS:Read on mctl.ru
tofu init
tofu plan -generate-config-out=generated.tf   # provider writes normalized HCL
mv generated.tf dns.tf                        # review, drop computed fields
tofu plan                                     # expect: No changes
```

Reversibility check — this must leave Cloudflare untouched:

```sh
tofu state rm cloudflare_dns_record.apex \
              cloudflare_dns_record.wildcard \
              cloudflare_dns_record.acme_challenge
# then re-read the records via the API and diff against the inventory
```

No `apply` that creates, updates or destroys anything runs in this slice. A plan
containing create/update/destroy means stop and investigate — it does not mean
apply and re-import.
