# Design: mcp-support-tools
Pages: update `docs/mcp/tools-reference.md` (new "Support" section) and `docs/mcp/examples.md` (new example).
Evidence: 907bcdc "mint a short-lived support-audience token for the caller's principal and send only that to mctl-support"; 1a48bb5 "let the support wait outlive the 30s request timeout"; 0832f48 refuses a support call with no user before the tenant check.
Do not document internals (support.token_mint audit details beyond a one-line mention).
