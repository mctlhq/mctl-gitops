# Design: issue-716-refactor-db-replace-logtoolcall-s-positi

## Current state
- `internal/db/store.go:1957` defines
  `func (s *Store) LogToolCall(ctx context.Context, userID int64, tool, peerRedacted, status, errMsg, callPath, reason string)`.
  The body:
  1. reads correlation data from `edgectx.From(ctx)`;
  2. opens a transaction and reads the user's last `entry_hash` as `prev`;
  3. calls `hashAuditEntry(prev, userID, tool, peerRedacted, status, errMsg, sql.NullString{String: callPath, Valid: true}, createdAt, edge)`;
  4. inserts into `audit_logs`, using `nullable(...)` for `peerRedacted`, `errMsg` and `reason`.

  `reason` is deliberately not passed to `hashAuditEntry`; the doc comment on lines 1950-1955 explains this. The comment on lines 1960-1963 still says "~25 existing call sites".
- Production call sites. The issue's 33 lines include the definition and comment-only matches. The rg count of actual calls is:
  - `internal/agentapi/json.go:75`: the `audit` helper, `s.Store.LogToolCall(ctx, userID, tool, "", status, errMsg, "", "")`.
  - `internal/agentapi/profilehandler.go:195, 214`.
  - `internal/mcp/tools.go:2551`: `writeAuditRow`, `s.Store.LogToolCall(ctx, uid, rec.tool, rec.peer, rec.status, rec.errMsg, rec.callPath, rec.reason)`. This is the only caller that fills all seven fields.
  - `internal/oauth/demo_login.go:169`, `internal/oauth/enable_access.go` (15 calls between lines 756 and 1074), `internal/oauth/local_bridge_activate.go:1096`, `internal/oauth/local_bridge_credential.go` (6 calls: 307, 344, 368, 391, 403, 447), `internal/oauth/server.go:1953`.
  - `internal/web/account.go:121`: the only non-MCP caller that passes a reason, `reasonScopeDenied`. Also `internal/web/account.go:384`, `internal/web/broadcasts.go:105, 459` and `internal/web/manage_notifications.go:186`.
- Test call sites:
  - `internal/db/audit_chain_test.go` (18 matches, including `TestLogToolCall_ReasonIsExcludedFromTheHash` at line 191);
  - `audit_edge_test.go` (6), `connect_step_test.go` (6), `store_audit_test.go` (7), `identity_migration_test.go` (1).
  - The `internal/mcp` tests mention `LogToolCall` only in comments.
- No interface declares `LogToolCall`, and nothing uses it as a method value (`grep -E 'LogToolCall[^(]'` finds only comments and test names). Every caller therefore uses the concrete `*db.Store`, and a signature change has no hidden implementers.
- No `ToolCall` identifier exists in `internal/db`.
- Docs mention `LogToolCall` by name only, never its arguments: `internal/bridge/DESIGN.md:95`, `docs/troubleshooting.md:280`, `docs/plans/communication-agent.md:267`.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram` and `services/labs/mctl-telegram-preview` exist. The service runs in tenant `labs`. Their values were not read in detail because this change has no config, env or schema surface.
- The mctl MCP tools were not used. Deployed runtime state is irrelevant to a compile-time-only refactor, so not observing it leaves no open question.

## Proposed solution
1. In `internal/db/store.go`, directly above `LogToolCall`, add this struct and give every field a short doc comment that carries over the parameter semantics from the current comment:

   ```go
   // ToolCall is one audit row passed to Store.LogToolCall. Zero values
   // mean "absent": empty PeerRedacted, ErrMsg and Reason are stored as NULL;
   // empty CallPath is stored as "" (hosted call).
   type ToolCall struct {
       UserID       int64
       Tool         string
       PeerRedacted string
       Status       string
       ErrMsg       string
       CallPath     string // "local" for relay-forwarded calls, "" for hosted
       Reason       string // operator-only; never hashed (see hashAuditEntry)
   }
   ```

2. Change the signature to `func (s *Store) LogToolCall(ctx context.Context, c ToolCall)`. Leave the body as it is: either bind locals at the top (`userID, tool, ... := c.UserID, c.Tool, ...`) or replace each identifier with `c.Field`. Statement order, the SQL, the `nullable(...)` wrapping and the `hashAuditEntry` argument list stay the same. Update the doc comment so it refers to the field names (`CallPath`, `Reason`), and remove the outdated "~25 existing call sites did not have to be rewritten" remark.
3. Rewrite every call site to a keyed struct literal and omit zero-valued fields. For example:
   - `s.store.LogToolCall(r.Context(), es.uid, "connect:success", "", "ok", "", "", "")` becomes `s.store.LogToolCall(r.Context(), db.ToolCall{UserID: es.uid, Tool: "connect:success", Status: "ok"})`.
   - In `internal/mcp/tools.go:2551`, set all seven fields from `rec`.
   - In `internal/web/account.go:121`, keep `Reason: reasonScopeDenied`.
   - In `local_bridge_credential.go:307, 391`, keep `UserID` set explicitly to `0`, or omit it with a comment that says it is intentionally 0, so the "unknown user" meaning stays visible.

   The `internal/db` tests use `ToolCall{...}` without the package qualifier. Each file that does not already import `internal/db` adds that import; the `oauth`, `web`, `agentapi` and `mcp` packages already use `db.Store`.
4. Make it one commit (`refactor(db): take a ToolCall struct in LogToolCall`) with no positional wrapper. Every leftover positional call then fails the build.

Keyed literals turn the transposition bug into a visible field-name mismatch at review time. Omitting zero fields also shortens the 30+ OAuth/web calls that currently end in `"", "", ""`.

## Alternatives
- **Distinct named string types** (`type AuditStatus string`, `type CallPath string`, ...). These catch transpositions only for the typed fields, and untyped string constants still convert implicitly, so `"ok"` would still fit any slot. They also spread new types across many packages. Rejected.
- **Functional options / builder** (`LogToolCall(ctx, uid, tool, db.WithStatus("ok"), ...)`). This is heavier, allocates, and leaves required versus optional fields unclear. The issue explicitly asks for a struct. Rejected.
- **Keep the positional method as a deprecated wrapper next to the struct form.** This leaves the bug-prone signature callable. The issue says `internal/db` is internal and no overload may remain. Rejected.
- **Pass `*ToolCall`.** A pointer adds nil handling for no gain on a 7-field value type. Rejected in favour of passing by value.

## Platform impact
- **Migrations:** none. The `audit_logs` schema, the hash input and the stored values do not change.
- **Backward compatibility:** the change is compile-time only. Rows written before and after the change are byte-identical for the same inputs, so `VerifyAuditChain` works across a deploy or a rollback in either direction. No external API changes; `internal/db` cannot be imported from outside the module.
- **Resource impact:** negligible. One small struct is passed by value per audit write.
- **Risks and mitigations:**
  - *A field is mis-mapped during migration*, for example a former `errMsg` argument written as `Status:`. Mitigations: the diff is reviewed per call site, and the unchanged hash-chain and edge tests in `internal/db` check stored columns. Reviewers should pay attention to `tools.go:2551` and `account.go:121`, the only call sites that carry `CallPath`/`Reason`.
  - *A call site is missed.* The build fails because no wrapper exists.
  - *Merge conflicts with in-flight #703 work* that touches the same call sites. Land this PR on its own; whichever lands second rebases mechanically.
