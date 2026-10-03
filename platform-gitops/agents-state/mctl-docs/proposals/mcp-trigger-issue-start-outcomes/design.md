# Design
Update `docs/mcp/tools-reference.md` entry for `mctl_trigger_issue` (and cross-link `mctl_get_dev_loop`). Align the outcome table with the one in proposal `mcp-roadmap-control-plane`. Known caveat from code comments: two racing callers can both be reported `started` (TOCTOU, mctl-api#404) — mention as a note only if the author confirms.
