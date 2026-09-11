# Cloudflare MCP Portal controls

`mcp-portal-controls.json` is the committed state of the account-level
switches on portal `mcp` (`mcp.mctl.ai`, the private aggregate over `tg`,
`seerrsense` and `api`). It is applied by `scripts/portal-controls-apply.sh`
and compared against the live portal by the same script's `--check` mode.

This is not OpenTofu. The portal was created through the API and the
dashboard, and declarative ownership is an import task blocked on a CI
Cloudflare write identity (`mctlhq/mctl-gitops#1092`, `mctlhq/.github#47`,
`#1111`). Until that lands the switches are applied the way the tool
allowlists are: a scripted API call from a repository-pinned file, run by an
operator, with the state recorded here. When the import lands, this file
becomes a resource and the script goes away.

## What is pinned, and why each field

- `secure_web_gateway` — whether the portal routes its traffic through
  Cloudflare Gateway. This is the Phase 2 subject (`mctlhq/.github#43`,
  `#1181`): committed `false` is the baseline the POC returns to.
- `code_mode` / `allow_code_mode` — `code_mode` is one of `off`, `opt_in`,
  `default_on`, `enforced` (the API's own set; it defaults to `opt_in` when
  omitted on create, which is why leaving it unpinned is not the same as
  leaving it off). The two fields must agree — the API answers 400 when they
  disagree — so the script refuses a file where they do not. Pinned `off`/`false` because Phase 2 must
  leave Code Mode untouched, and "untouched" is only checkable if something
  records what it was. A drift here is as interesting as a drift in the
  Gateway switch: it means the portal grew an execution surface nobody
  decided on.
- `portal` and `hostname` — the address. The script refuses a file naming a
  different portal: this file writes to a shared surface, and a retargeted
  file would rewrite a mapping this repository does not own.

The tool allowlists are **not** here. They live with the servers that
register the tools — `mctl-telegram`, `mctl-api`, `seerrsense` — because the
decision "this tool is safe to expose" belongs in the same diff as the tool.

## Running it

```
CLOUDFLARE_API_TOKEN=… CLOUDFLARE_ACCOUNT_ID=… scripts/portal-controls-apply.sh --check
CLOUDFLARE_API_TOKEN=… CLOUDFLARE_ACCOUNT_ID=… scripts/portal-controls-apply.sh --dry-run
CLOUDFLARE_API_TOKEN=… CLOUDFLARE_ACCOUNT_ID=… scripts/portal-controls-apply.sh
```

`--check` exits non-zero on drift and prints the fields that differ; it is
the operator's stand-in for `cloudflare-drift.yml`, which cannot watch this
until CI has a Cloudflare identity. Nothing in CI holds the token today, so
nothing in CI applies or checks this file — that is the gap `#1111` closes,
not something this script works around.
