# Design: integration-credential-leak-fix

## Current state
mctl-portal uses `@backstage/integration` to resolve GitHub URLs and attach
the appropriate personal access token (PAT) or GitHub App credential before
making server-side requests. The integration is configured in
`app-config.yaml` under `integrations.github` with at least one entry for
`github.com`. The credential is sourced from Vault via ExternalSecret and
mounted into the backend pod at runtime.

The currently installed version of `@backstage/integration` does not
normalize encoded path components in SCM URLs before performing host-based
credential lookup. A URL such as
`https://github.com%2F@evil.example.com/repo` can pass host validation
while actually routing the HTTP request to `evil.example.com`, carrying the
GitHub credential in the `Authorization` header.

## Proposed solution
Upgrade `@backstage/integration` to >=1.20.1 as part of the Backstage
v1.50.3 patch bump already required by `techdocs-path-traversal-fix`. Because
both CVEs are addressed by the same Backstage patch release, the two proposals
share a single `yarn backstage-cli versions:bump --release 1.50.3` execution.
The two fix proposals are therefore coordinated but independently tracked so
that either can be rolled back in isolation if necessary.

The fix in `@backstage/integration` >=1.20.1 adds URL normalization (percent
decoding + canonicalization) before the host-matching step, ensuring that
encoded traversal sequences cannot be used to spoof the matched host entry.

No configuration changes are required. The normalization is applied
transparently to all URL resolutions performed by the integration library.

## Alternatives

### Option A: Add an HTTP-proxy layer that strips suspicious URLs
Place a proxy (e.g., Squid or an Envoy filter) in front of all outbound
backend requests and reject URLs containing encoded path separators.
Dropped because it adds operational complexity, does not fix the root cause
in the library, and does not cover in-process URL resolution that never
reaches the network stack.

### Option B: Allowlist outbound GitHub traffic at the network policy level
Use a Kubernetes NetworkPolicy or egress gateway to restrict all outbound
traffic from the backend pod to known GitHub IP ranges only. Dropped because
GitHub IP ranges are large, change frequently, and managing them is operationally
expensive. It also does not prevent the credential from being read by the
library before the network layer would block the connection.

### Option C: Rotate the GitHub token and monitor for misuse before patching
Rotate the PAT immediately and delay the library upgrade. Dropped because
rotation alone does not eliminate the vulnerability; any future token would
be equally exposed. Upgrading the library is the correct and complete fix.

## Platform impact

### Migrations
None. No schema changes. The fix is entirely within the integration library's
URL normalization logic.

### Backward compatibility
Legitimate SCM URLs (no encoded traversal sequences) are unaffected. The
only behavioral change is that malformed URLs that previously resolved
ambiguously are now rejected with an error — this is the intended outcome.
Scaffolder templates using standard `https://github.com/<org>/<repo>` URLs
are unaffected.

### Resource impact
The URL normalization step is O(n) on URL length and adds negligible CPU
overhead. No memory increase. No impact on the `labs` tenant. No flag required.

### Risks and mitigations
- **Risk:** A scaffolder template in the wild may use a non-standard
  (but benign) encoded URL that the new validation rejects.
  **Mitigation:** Run all existing scaffolder e2e tests against staging before
  promoting; review the three most-used scaffolder templates manually.
- **Risk:** Rotating the GitHub token concurrently with the upgrade could
  cause a deployment window where the new token is not yet available.
  **Mitigation:** If the security team rotates the token, coordinate the
  rotation to happen after the new image is live and verified.
