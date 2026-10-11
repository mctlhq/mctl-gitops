# Design: Tenant roles and the write gate

- **Source commits:** 890b675 (fix(authz): enforce tenant member role on write operations), 538d022 (fix(authz): keep scoped roles apart; OpenClaw reads off the write gate)
- **Page to update:** `docs/security/authorization.md (new section "Tenant roles"); one-line link from docs/guides/tenants.md` (relative to `mctl-docs/docs/`)
- **Approach:** Add a section with a role table and error-code table.
- Cross-links are root-relative without extension. Do not invent behaviour beyond the cited commits; anything not confirmed by the diff is omitted.
