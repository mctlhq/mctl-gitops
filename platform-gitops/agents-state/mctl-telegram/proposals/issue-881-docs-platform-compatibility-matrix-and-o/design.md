# Design: issue-881-docs-platform-compatibility-matrix-and-o

## Current state

**Admission code paths:**

- `internal/config/config.go` reads the admission settings:
  - `OAUTH_ALLOWED_IMPLICIT_HOSTS` (`OAUTHAllowedImplicitHosts`, line ~655)
  - `OAUTH_CIMD_ACCEPT` / `OAUTH_CIMD_ADVERTISE`, both `envBool(..., false)` (line ~492)
  - `OAUTH_CIMD_ALLOWED_HOSTS`, parsed by `cimd.ParseAllowedHosts`. Accept
    requires it to be non-empty.
  - `OAUTH_DCR_REDIRECT_URIS`
  - `OAUTH_PREREGISTERED_CLIENTS`
  - `MCP_CLIENT_PROFILES`, as `ClientProfiles toolprofile.Bindings`
- Startup refuses `OAUTH_CIMD_ADVERTISE=true` without accept. The error text:
  "advertising documents the server would refuse leaves CIMD clients with no
  DCR fallback".
- `internal/oauth/server.go` enforces the redirect rules: https only, except
  http on the three loopback forms (`isLoopbackHost`). Loopback is accepted
  regardless of `AllowedImplicitHosts`, and custom schemes are refused.
- `internal/oauth/cimd/cimd.go` resolves CIMD documents.

**Existing documentation:**

- `README.md`:
  - lines 13-19 and 151-161 say Claude is tested, ChatGPT adds the server by
    URL, and Cursor/VS Code/Windsurf are "not yet tested";
  - lines 279-284 document the OAuth env vars, including the warning on
    `OAUTH_CIMD_ADVERTISE`.
- `docs/runbook.md`:
  - is alert-organized;
  - has a "Client tool profiles and MCP_CLIENT_PROFILES" section (anchor
    `client-tool-profiles`) and a "Rejected dynamic client registrations"
    section (metric `mctl_oauth_client_registrations_total{outcome,reason}`);
  - links `docs/runbooks/canary.md`, which is the only file in `docs/runbooks/`
    today.
- `docs/cloudflare-portal-compat.md` uses the convention "a cell nobody has run
  says `PENDING-OPERATOR`, not `PASS`". Its `direct-deployed` and
  `cloudflare-portal` cells are pending. It writes the portal callbacks as
  placeholders (`<portal servers-callback>,<dashboard oauth-callback ...>`).
- `docs/runbook_test.go` and `docs/troubleshooting_test.go` (package `docs`,
  `docs/doc.go`) are Go tests that read markdown with `os.ReadFile` and assert
  anchors and metric names. The new matrix test follows that pattern.
- ADRs 0001-0007 (`docs/adr/`, added by #779): ADR 0004 covers the own
  authorization server and CIMD.
- `docs/design/core-profiles.md` and `docs/design/core-endpoint.md` describe the
  Town profile binding. Town is not migrated to `/core` automatically.
- There is no `docs/platforms/` directory.

**Evidence source:** the #784 inventory comment (2026-10-23) already holds
per-host evidence:

- Claude and ChatGPT: CIMD proven against mctl-api only (mctl-gitops#2039).
- Cursor: allowlisted only.
- VS Code and Windsurf: proposed only (#840).
- MCP Inspector / probe: in-process only, deployed cells pending.
- Town: what is proven and what is not, and 3 gitops PRs over about 3 days.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`. Production
  values:
  - `OAUTH_ALLOWED_IMPLICIT_HOSTS: claude.ai,claude.com,chatgpt.com,antigravity.google,www.cursor.com,cursor.com,www.town.com,town.com,localhost,127.0.0.1`
  - `OAUTH_CIMD_ACCEPT: "true"`, `OAUTH_CIMD_ADVERTISE: "true"`
  - `OAUTH_CIMD_ALLOWED_HOSTS: chatgpt.com,claude.ai,vscode.dev,www.town.com`
  - `MCP_CLIENT_PROFILES` binds `https://www.town.com/.well-known/oauth-client-id`
    to `core-reply`
  - `OAUTH_DCR_REDIRECT_URIS` holds the Cloudflare portal's servers-callback
    and per-account dashboard callback
  - no `OAUTH_PREREGISTERED_CLIENTS`: the static portal client was retired on
    2026-09-26 (mctl-gitops#1363)
  - the Cursor comment records 464 rejected registrations on 2026-09-21..23
  - the CIMD comment states the rollback ("set OAUTH_CIMD_ADVERTISE to false")
    and that removing a host cuts off that client's refreshes.
- `mctl_get_service_status(labs, mctl-telegram)`: ArgoCD Synced/Healthy, image
  `0.94.0`, host `tg.mctl.ai`.
- `gh issue view 784 --comments`: read the 2026-10-23 inventory comment cited
  above.
- `gh issue view 779`: title "docs: rework the README and add architecture
  decision records", merged. These are the ADRs present in `docs/adr/`.
- Not observed: production OAuth logs or metrics per host (no log query was
  run). Whether Town currently uses CIMD or DCR is therefore unknown, not
  absent, and stays an open question in the matrix.

## Proposed solution

Three documentation artifacts and one test. No code under `internal/` or `cmd/`
changes.

### 1. `docs/platforms/compatibility.md`

- **Header:**
  - Purpose and the status legend:
    - `works`: a cited run completed sign-in, token and at least one tool call
    - `works with caveats`: completed, but with a stated limitation or on a
      sibling service
    - `not tested`: anything else, including allowlisted only
  - The rule "An allowlist entry alone means `not tested`".
  - The gitops path and the date the allowlist cells were read.
- **Table:** one GitHub-flavoured markdown table, exact header
  `| Host | Registration path | Allowlist entry today | Status | Evidence | Date observed |`,
  with these nine rows, filled from the evidence above:

| Host | Registration path | Allowlist today | Initial status |
| --- | --- | --- | --- |
| Claude (hosted connector) | CIMD (claude.ai), DCR fallback only while not advertised | implicit `claude.ai`, `claude.com`; CIMD `claude.ai` | per open question: `works` with tg.mctl.ai evidence, else `works with caveats` citing mctl-gitops#2039 |
| Claude Code | DCR with loopback redirect | loopback always accepted | same rule as Claude |
| ChatGPT | CIMD (chatgpt.com; also covers Codex) | implicit `chatgpt.com`; CIMD `chatgpt.com` | same rule; MCP Apps deferred to #650 |
| Cursor | DCR, hosted callback `www.cursor.com` (`cursor://` refused) | implicit `www.cursor.com`, `cursor.com` | `not tested` |
| VS Code | CIMD (vscode.dev) | CIMD `vscode.dev` | `not tested` |
| Windsurf | unknown (DCR assumed) | none | `not tested` |
| Town | CIMD document published; DCR via `www.town.com` callback | implicit `www.town.com`, `town.com`; CIMD `www.town.com`; profile `core-reply` | `not tested`, with the exact progress text |
| MCP Inspector | DCR with loopback redirect | loopback always accepted | `not tested` against tg.mctl.ai; links the `in-process-current-main` cell of `docs/cloudflare-portal-compat.md` |
| Cloudflare MCP portal | byte-exact redirect URI (`OAUTH_DCR_REDIRECT_URIS`), automatic DCR mode | `OAUTH_DCR_REDIRECT_URIS` (2 URIs, placeholders) | `not tested`, mirroring `PENDING-OPERATOR` |

- **Town row:** the evidence cell spells out what is proven and what is not:
  - proven: `invalid_redirect_uri` until mctl-gitops#2023; CIMD document
    resolves; authorize reaches Telegram sign-in; profile binding parses;
  - not proven: completed token, first tool call, CIMD-vs-DCR.
- **Below the table:**
  - a footnote for `antigravity.google` (allowlisted, out of this matrix, not
    tested);
  - a note that `localhost`/`127.0.0.1` on the implicit list are redundant with
    the code's loopback rule;
  - a "How to update a row" paragraph pointing at the runbook.

### 2. `docs/runbooks/admitting-an-agent-platform.md`

Section "Admitting an agent platform", grounded in the config code and the
values.yaml comments:

1. **Intake.** Decide the path:
   - CIMD preferred: an https `client_id` document on the platform's own host,
     exact host, no suffix entries in production;
   - DCR: callback host;
   - byte-exact URI: a gateway with fixed callbacks.
   Fetch and inspect the CIMD document.
2. **Settings, in order, one gitops PR each, each verified before the next:**
   1. `OAUTH_ALLOWED_IMPLICIT_HOSTS`: admit the DCR callback host, so the host
      works whatever discovery says.
   2. `OAUTH_CIMD_ALLOWED_HOSTS`: admit the CIMD host. Keep the implicit entry
      until the platform is confirmed on CIMD and its connections have
      re-authorized.
   3. `MCP_CLIENT_PROFILES`: optional. Prefer a `client_id` binding (CIMD URL).
      A malformed table stops the server at startup. A `redirect_uri` record
      refuses pre-0.87.0 refresh families. Link the existing
      `docs/runbook.md#client-tool-profiles` section rather than duplicating it.
3. **Warning box.** `OAUTH_CIMD_ADVERTISE=true` makes CIMD-preferring clients
   (ChatGPT, Codex, Claude, VS Code) switch on their next new connection with no
   DCR fallback. A CIMD client off `OAUTH_CIMD_ALLOWED_HOSTS` gets 400 on new
   authorizations. Production already advertises, so every new CIMD host must
   be on the allowlist before the platform's users connect.
4. **Verification:**
   - ArgoCD synced to the new revision;
   - `GET /.well-known/oauth-authorization-server` shows
     `client_id_metadata_document_supported`;
   - `mctl_oauth_client_registrations_total{outcome="rejected",reason="redirect_host_not_allowed"}`
     stops rising for that host;
   - the platform reaches the Telegram sign-in, receives a token, makes one
     read-only tool call;
   - record the result as a dated row update in the matrix.
5. **Rollback:**
   - revert the gitops PR;
   - removing a CIMD host cuts off that client's refreshes, while turning
     `OAUTH_CIMD_ACCEPT` off does not;
   - `OAUTH_CIMD_ADVERTISE=false` returns clients to DCR at their next sign-in;
   - removing a profile binding takes effect at the next refresh.
6. **Measured example: Town.**
   - Integrator time: unknown/not measured.
   - Operator time: 3 gitops PRs, about 3 days, including mctl-gitops#2023
     (DCR host) and mctl-gitops#2063 (profile binding). The third PR is
     identified by the implementer from gitops history; it is likely the CIMD
     host addition, but `git log -S "www.town.com"` decides.
   - Waiting time: sync, plus waiting on the integrator.
   - Outcome: reached Telegram sign-in; no token or tool call proven.

`docs/runbook.md` gains one line next to its existing canary pointer (line ~11)
linking the new file. That keeps the alert-organized runbook's anchors intact,
since `TestRunbookAnchorsPresent` only checks presence.

### 3. README link

One line appended to the "Cursor, VS Code, Windsurf and others" or "Agent
platforms" bullet (README ~151-161):
"Per-host status and evidence: [docs/platforms/compatibility.md](docs/platforms/compatibility.md)."
No existing README claim is reworded.

### 4. `docs/compatibility_test.go` (package `docs`)

- Reads `platforms/compatibility.md` and locates the table by its exact header.
- Parses the rows and asserts:
  - the nine required host names are each present exactly once;
  - status is one of the three values;
  - every `works` / `works with caveats` row has a markdown link in Evidence
    and a `\d{4}-\d{2}-\d{2}` date;
  - the Town row is not `works`.
- Also reads `../README.md` and asserts that it links
  `docs/platforms/compatibility.md`.
- A second test checks that every env var name the runbook mentions matching
  `OAUTH_[A-Z_]+|MCP_CLIENT_PROFILES` appears in
  `../internal/config/config.go`. This catches renames, in the same spirit as
  `TestRunbookMetricNamesRegistered`.

Why this way: the matrix lives next to the code it describes, so a PR that
changes admission behaviour can update it in the same diff. The test enforces
the DoD rule "every `works` cell cites evidence" mechanically instead of by
review.

## Alternatives

- **Add the matrix to `docs/cloudflare-portal-compat.md` or the README.**
  Dropped. The portal doc is specific to one gateway and protocol probe, and
  the README is already long. The issue names `docs/platforms/compatibility.md`.
- **Put "Admitting an agent platform" inside `docs/runbook.md`.** Dropped.
  That file is organized by alert rule, and admission is a planned procedure,
  not an alert response. The issue says "in the existing runbooks directory",
  which is `docs/runbooks/`, and `canary.md` sets the one-topic-per-file
  precedent. A link from `docs/runbook.md` keeps it discoverable.
- **Generate the allowlist column from gitops at build time.** Dropped. The
  gitops repo is not a dependency of this repo. The README and `canary.md`
  deliberately keep no live copy of gitops values ("check those files for the
  current values"), and the `/platforms` page already renders from the running
  config. A dated snapshot, with its source path, is the honest form.
- **No test, review only.** Dropped. The DoD invariant is easy to violate in a
  later edit, and the `docs` package already hosts this kind of check.

## Platform impact

- No migrations, no runtime change, no image behaviour change. Docs and one
  `_test.go` file only. No gitops change.
- Backward compatible. Existing `docs` tests are unaffected, because only a
  link line is added to `runbook.md`.
- **Risk:** the matrix goes stale as allowlists change. Mitigation: each
  allowlist cell carries the date read, the runbook's verification step
  requires a matrix update, and the header states that values.yaml is
  authoritative.
- **Risk:** leaking the Cloudflare account-scoped dashboard callback into a
  public repo. Mitigation: use the existing placeholder form.
- **Risk:** the matrix contradicts the README's "Claude is the client we test
  against". Mitigation: the open-question rule. Cite tg.mctl.ai evidence if
  found; otherwise mark `works with caveats` with the mctl-api proof and flag it
  in the PR description, without rewriting the README here.
- **Risk:** fixture rules. No Telegram identifiers are added. Evidence links
  point at PRs and issues only.
