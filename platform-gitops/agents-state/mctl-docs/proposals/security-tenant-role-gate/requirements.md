# Requirements: Tenant roles and the write gate

version-status: unverified, see commit SHA

## Acceptance criteria (EARS)
- WHEN a user reads the authorization page, THE page SHALL list the roles `viewer` < `developer` < `owner`.
- THE page SHALL state that tenant writes require a per-operation minimum role and that platform admins pass every minimum.
- THE page SHALL state that an unknown or missing role yields 403 and an unreadable role yields 503.
- THE page SHALL state that OpenClaw skill and identity reads and writes are owner-only.
