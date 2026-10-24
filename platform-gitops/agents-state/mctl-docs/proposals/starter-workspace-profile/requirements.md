# Document the starter workspace profile and signup administration tools

## Context
mctl-api commits 8081830 (fund only the bounded starter profile), 0244bac (reserve CPU for starter deployment workflows) and b5394f6 (administer invitations with funded workspace reservations), plus mctl-portal de6387a/e29c700, added `workspace_profile` to `mctl_create_tenant` and three admin tools: `mctl_signup_capacity`, `mctl_list_signup_requests`, `mctl_decide_signup_request`. Customer-facing sign-in and deletion flows are still in flight and are out of scope.

version-status: unverified, see commit SHA 8081830 (the parameters appear in the live MCP tool schemas).

## User stories
- AS a platform admin I WANT to know what the starter profile fixes SO THAT I provision funded customers correctly.
- AS a platform admin I WANT the invitation decision workflow described SO THAT I manage funded slots safely.

## Acceptance criteria (EARS)
- WHEN a reader opens the tenants page THE SYSTEM SHALL describe `standard` vs `starter` profiles with the fixed starter numbers.
- THE SYSTEM SHALL state that funded invited customers require `starter` and that quota arguments are fixed for it.
- THE SYSTEM SHALL describe the slot model: default 0, approval reserves one slot, an unused approval expires in seven days, slots cannot go below live reservations, and changing slots does not resize Kubernetes.
- THE SYSTEM SHALL state that these tools need a direct human administrator and `confirm=yes` for mutations.

## Out of scope
- Customer sign-in, account deletion, invitation email content, ZITADEL.
