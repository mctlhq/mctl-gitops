# Platform compatibility matrix and operator host-admission runbook (#784 D1/E4)

## Context

mctl-telegram (`https://tg.mctl.ai/mcp`) lets an MCP host reach its OAuth 2.1
server in three ways: Dynamic Client Registration (DCR) from a callback host on
`OAUTH_ALLOWED_IMPLICIT_HOSTS`, Client ID Metadata Documents (CIMD) from a host
on `OAUTH_CIMD_ALLOWED_HOSTS`, or a byte-exact callback on
`OAUTH_DCR_REDIRECT_URIS`. A client can also be bound to a narrower tool profile
through `MCP_CLIENT_PROFILES`. Today nothing in the repository says, per host,
which path the host takes, whether production admits it, and whether anyone has
actually seen it work. The README is cautious ("Cursor, VS Code and Windsurf may
work, but they are not yet tested"), but the evidence behind each claim is
scattered across gitops comments, PRs and the #784 inventory comment.
Admitting a new platform is also undocumented operator work: Town needed 3
gitops PRs over about 3 days, and it still has no proven token or tool call.

Issue #881 is the documentation slice D1/E4 of spike #784. It asks for an
evidence-backed compatibility matrix (`docs/platforms/compatibility.md`), an
operator runbook "Admitting an agent platform" in `docs/runbooks/`, and a
one-line README link. These are documentation changes only: no code, no
allowlist and no gitops change. A `docs` package test keeps the matrix honest.

## User stories

- AS an operator I WANT one table of every host with its registration path,
  its production allowlist entry and dated evidence SO THAT I can answer "does
  X work?" without digging through gitops history.
- AS an operator admitting a new agent platform I WANT the three gitops
  settings in the order to apply them, with verification and rollback, SO THAT
  I do not cut off existing CIMD clients by advertising CIMD too early.
- AS an integrator or user I WANT to know how far a host has been proven SO
  THAT "allowlisted" is never mistaken for "works".
- AS a maintainer I WANT a test that fails when a `works` cell has no evidence
  SO THAT the matrix cannot drift into unsupported claims.

## Acceptance criteria (EARS)

- WHEN the change is merged THE SYSTEM SHALL contain
  `docs/platforms/compatibility.md` with exactly one row for each of: Claude
  (hosted connector), Claude Code, ChatGPT, Cursor, VS Code, Windsurf, Town, MCP
  Inspector, and the Cloudflare MCP portal.
- THE SYSTEM SHALL give each row these columns: registration path (`DCR`,
  `CIMD`, `byte-exact redirect URI`, or a combination), allowlist entry today,
  status, evidence, and date observed (`YYYY-MM-DD`).
- THE SYSTEM SHALL restrict status values to exactly `works`,
  `works with caveats`, and `not tested`.
- IF a row's status is `works` or `works with caveats` THEN THE SYSTEM SHALL
  cite at least one link in its evidence cell to a test, PR, canary run or dated
  observation, and SHALL give a concrete date observed.
- IF the only evidence for a host is an allowlist entry THEN THE SYSTEM SHALL
  mark that row `not tested`.
- THE SYSTEM SHALL take allowlist cells from mctl-gitops
  `platform-gitops/services/labs/mctl-telegram/values.yaml` and SHALL state the
  gitops revision or date they were read from.
- THE SYSTEM SHALL name `OAUTH_DCR_REDIRECT_URIS` for the Cloudflare portal row,
  because that row is admitted through that setting, and SHALL NOT reproduce the
  portal's per-account dashboard callback URL. It SHALL use the placeholder form
  already used in `docs/cloudflare-portal-compat.md`.
- THE SYSTEM SHALL state in the Town row exactly how far Town got: DCR was
  rejected with `invalid_redirect_uri` until mctl-gitops#2023, its CIMD
  document resolves, authorize reaches the Telegram sign-in, and its
  `MCP_CLIENT_PROFILES` binding to `core-reply` parses. It SHALL also state that
  no completed token, no tool call and no confirmed CIMD-or-DCR choice are
  proven. The Town row SHALL therefore not be `works`.
- WHEN the change is merged THE SYSTEM SHALL contain
  `docs/runbooks/admitting-an-agent-platform.md` with a section "Admitting an
  agent platform". That section SHALL cover: the three settings
  (`OAUTH_ALLOWED_IMPLICIT_HOSTS`, `OAUTH_CIMD_ALLOWED_HOSTS`,
  `MCP_CLIENT_PROFILES`) and the order to apply them; the warning that
  `OAUTH_CIMD_ADVERTISE` leaves CIMD-preferring clients with no DCR fallback;
  verification steps; rollback; and the Town timeline split into integrator,
  operator and waiting time.
- WHILE describing rollback THE SYSTEM SHALL state that removing a host from
  `OAUTH_CIMD_ALLOWED_HOSTS` also cuts off that client's refreshes, while
  setting `OAUTH_CIMD_ADVERTISE=false` returns clients to DCR at their next
  sign-in. This is consistent with SECURITY.md and the values.yaml comment.
- WHEN `docs/runbook.md` is read THE SYSTEM SHALL link to the new runbook file
  next to its existing pointer to `docs/runbooks/canary.md`.
- WHEN README.md is read THE SYSTEM SHALL contain one line linking to
  `docs/platforms/compatibility.md` in the "Cursor, VS Code, Windsurf and
  others" / "Agent platforms" client list.
- THE SYSTEM SHALL NOT contradict the code defaults in `internal/config` and
  `internal/oauth`. These defaults are: CIMD accept and advertise default off;
  advertise requires accept; accept requires a non-empty host allowlist;
  loopback redirects are accepted regardless of the implicit-host list; custom
  schemes such as `cursor://` are refused. Nor SHALL it contradict values.yaml,
  the README, or ADRs 0001-0007 (#779).
- WHEN `go test ./docs/...` runs THE SYSTEM SHALL fail if a matrix row has a
  status outside the three allowed values, if a required host row is missing,
  or if a `works` / `works with caveats` row lacks an evidence link or an ISO
  date.

## Out of scope

- Edits to `platforms.html` / `docs.html` (#840, #841).
- Any allowlist, profile or other gitops change.
- The packaging decision (D3), skills or a CLI.
- The legal trust packet.
- Live host runs to turn `not tested` into `works`. That is operator work,
  grouped with #616 and #650.
- Fixing the four documentation discrepancies listed in #784 (separate PR).

## Open questions

- Claude (hosted connector) and Claude Code: the README says "Claude is the
  client we test against". The #784 inventory, however, records CIMD proof only
  against mctl-api (mctl-gitops#2039), with "no tg.mctl.ai host run recorded".
  Proceeding: the implementer cites a dated tg.mctl.ai observation (PR, issue or
  CHANGELOG entry recording a claude.ai session) if one exists and marks the row
  `works`. Otherwise the row gets `works with caveats`, with the caveat that
  the proof was on mctl-api and with that PR cited, and a note says the README
  claim awaits a recorded host run. The README sentence itself is not reworded
  in this change.
- ChatGPT is in the same position as Claude (CIMD host allowlisted; MCP Apps
  deferred to #650). The same rule applies.
- The issue's allowlist column names three variables, but the Cloudflare
  portal is admitted by a fourth, `OAUTH_DCR_REDIRECT_URIS`. Proceeding: the
  column covers all four.
- `antigravity.google` is on `OAUTH_ALLOWED_IMPLICIT_HOSTS` but is not in the
  issue's host list. Proceeding: it gets a footnote ("allowlisted, not in
  scope of this matrix, not tested"), not a row, so the nine required rows stay
  exactly as specified.
- Integrator-side Town timing is not proven (per #784). Proceeding: the
  runbook records integrator time as "unknown" rather than estimating it.
