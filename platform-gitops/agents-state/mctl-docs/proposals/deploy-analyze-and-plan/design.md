# Design: deploy-analyze-and-plan
Pages: `docs/mcp/tools-reference.md` (new "Deploy analysis and planning" section); `docs/guides/services.md` (short "Check a repo before deploying" subsection).
Evidence: ee7aaca adds GET /api/v1/deploy/analyze and /deploy/bindings with MCP tools; 2400c1f redacts every Vault path key; 72b8175 states redacted path hashes are unsalted (do not claim hashes are secret).
Approval/promote steps for plans are not yet documented in the tool text: say "approval is a later step" and do not invent behaviour. Also add a one-line note to docs/api/index.md only if the REST endpoints are in the OpenAPI spec (needs check).
