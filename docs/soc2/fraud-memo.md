# Fraud risk memo

As of 2026-08-17.

MCTL does not process customer payments on the platform. There is no
cardholder data, no in-app billing ledger, and no finance role separate
from the founder.

Fraud-relevant surfaces that do exist:

- GitHub OAuth sign-in and tenant creation (landing token is not
  `isAdmin`).
- Public RFC 7591 DCR (bounded registry, 30/min, token TTL). Abuse is
  resource exhaustion / client spam, not funds movement.
- GitHub App tokens and Vault. Dual Apps and Kubernetes/JWT auth limit
  blast radius; there is no second person to collude with.

Residual: a solo operator can approve their own change and merge it.
That is segregation-of-duties risk (see compensating-controls.md), not
payment fraud.

Accepted until a billing system exists. Revisit this memo when money
moves through the platform.
