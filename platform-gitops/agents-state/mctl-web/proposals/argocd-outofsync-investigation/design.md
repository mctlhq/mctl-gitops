# Design: argocd-outofsync-investigation

## Current state
Status via mctl_get_service_status shows OutOfSync with empty revision.

## Proposed solution
Read-only check: service status/config, recent operations list, and service logs; compare to gitops values. Document findings; file a fix if drift is real.

## Alternatives
- Force a sync: a write operation, risky without understanding the cause.
- Ignore: drift may mask failed deployments.

## Platform impact
- No changes in this proposal; no labs impact. Risk: transient state misread; mitigated by re-checking after 1 hour.
