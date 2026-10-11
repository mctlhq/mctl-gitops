# Design: Services listing: managed rows and incomplete results

- **Source commits:** be89400 (feat(api): list tenant workloads deployed outside the catalogue), 199443f, 672db07
- **Page to update:** `docs/mcp/tools-reference.md (`mctl_list_services`, `mctl_get_tenant`); link from docs/guides/services.md` (relative to `mctl-docs/docs/`)
- **Approach:** Extend the existing tool entry with a field table and a warning admonition.
- Cross-links are root-relative without extension. Do not invent behaviour beyond the cited commits; anything not confirmed by the diff is omitted.
