# Design: go-github-v85-upgrade

## Current state

`mctl-agent` imports `github.com/google/go-github/v68/github` (see `context/architecture.md`). The library is used in the fix pipeline to create pull requests against `mctlhq/mctl-gitops`. Authentication is done via GitHub App installation tokens stored in Vault (`secret/platform/github-app`) and rotated every 30 minutes by the `cwft-rotate-github-token` CronWorkflow.

The v68 client does not validate redirect hosts. If an attacker could poison DNS or a proxy intercepts a redirect response pointing to a different host, the `Authorization: Bearer <token>` header would be forwarded to that host.

## Proposed solution

**Bump `go.mod` from `google/go-github/v68` to `google/go-github/v85`.**

v85.0.0 adds two hard-coded guards in the `Do()` method of the underlying HTTP client wrapper:
1. **Cross-host redirect rejection** — if a redirect response points to a hostname different from the original request's hostname, the client returns `ErrRedirectNotAllowed` without following the redirect.
2. **Path traversal rejection** — URL path segments containing `..` are rejected before the request is dispatched.

These guards are unconditional (no opt-out flag), which is the correct posture for a service-account token bearer.

### Breaking-API changes to handle

| Symbol | v68 signature | v85 signature | mctl-agent impact |
|---|---|---|---|
| `GetOrgRole` | `(ctx, org, roleID int64)` | `(ctx, org string, roleID int64)` | Audit call sites; likely none (mctl-agent does not manage org roles) |
| `CreateCustomOrgRole` | returns `(*CustomOrgRole, *Response, error)` | changed return type | Same — audit only |
| `UpdateCustomOrgRole` | same as above | changed return type | Same — audit only |
| `MarkThreadDone` | `(ctx, id int64)` | `(ctx, id string)` | Audit call sites; likely none (mctl-agent does not read GitHub notifications) |

Expected outcome: zero call sites in `mctl-agent` use any of the four changed symbols. The audit must confirm this before the PR is merged.

### Import-path change

The module path changes from `github.com/google/go-github/v68` to `github.com/google/go-github/v85`. A sed-style find-replace across all `*.go` files is required.

## Alternatives

1. **Vendor a custom fork of v68 with the redirect fix backported** — Rejected: maintenance burden of tracking a fork is higher than a straight upgrade; the breaking changes are minor and very likely do not affect mctl-agent.
2. **Wrap the standard `net/http` client with a custom `CheckRedirect` function** — Rejected: this is exactly what v85 does internally; re-implementing it at the application layer duplicates logic and misses future upstream hardening.
3. **Stay on v68 and rely on token rotation** — Rejected: rotation reduces but does not eliminate the 30-minute exposure window; the fix is low-effort and the correct long-term posture.

## Platform impact

- **Migrations:** None. No database or configuration schema changes.
- **Backward compatibility:** The import path changes from `/v68` to `/v85`; this is a compile-time change only.
- **Resource impact for `labs`:** None. go-github is used only by the `admins` tenant's mctl-agent binary. No memory or CPU overhead change expected.
- **Risks:**
  - *Risk*: A call site using one of the four changed symbols was missed in the audit → *Mitigation*: CI must fail to compile; automated grep over the codebase before the PR is opened.
  - *Risk*: The new cross-host redirect guard blocks a legitimate internal redirect (e.g., GitHub Enterprise mirror) → *Mitigation*: mctl-agent targets `api.github.com` exclusively; no internal redirects are expected.
