# GitHub Code Scanning webhook ingestion plumbing for SecurityFinding v1 (.github#209 slice 3)

## Context

mctlhq/.github#209 adds a normative `SecurityFinding v1` contract. Slice 1
(mctlhq/mctl-api#774, merged as mctl-api PR #799 on 2026-10-26) adds the store
and the authenticated batch ingestion route `POST /api/v1/security/observations`.
That route derives the provider identity (`provider_ref`) from the
authenticated channel, never from a payload `provider` field. Slice 2
(mctlhq/mctl-agents#778) owns remediation and verification. This slice
(mctlhq/mctl-gitops#2103) owns the GitOps side of one real provider path:
endpoint exposure, webhook signing credentials in Vault/ESO, provider
configuration, network policy, and the deployment configuration of the
receiver.

The chosen first path is the one the issue prefers: existing Trivy results
uploaded as SARIF into GitHub Code Scanning for `mctlhq/mctl-api`, then
`code_scanning_alert` webhook deliveries received by a signed, allowlisted
receiver hosted inside mctl-api, next to the GitHub pull-request webhook
receiver mctl-api already runs (mctl-api#323). The receiver turns each verified
delivery into a #774 observation under the configured provider
`github-code-scanning`. Two pieces of code live outside this repository and are
narrow prerequisites: the SARIF upload step in mctl-api's `security.yml`, and the
receiver route in mctl-api. GitOps only wires, configures and secures them, and
never becomes the security-finding source of truth.

## User stories

- AS a platform operator I WANT Trivy findings on mctl-api to reach the
  SecurityFinding store automatically over an authenticated channel SO THAT
  security occurrences are tracked without anyone parsing scanner output by
  hand.
- AS the SecurityFinding store (#774) I WANT every observation from this path to
  arrive under a provider identity that the server configured SO THAT a hostile
  payload cannot claim to be a stronger provider.
- AS a security reviewer I WANT the webhook secret held only in Vault and
  delivered by ESO SO THAT it never appears in Git, values files or logs.
- AS the remediation runner (#778) I WANT each occurrence to carry exact
  repository, revision and file/line identity SO THAT a fix can be bound to the
  revision it lands in.
- AS an on-call engineer I WANT failed deliveries to be visible and
  recoverable SO THAT an outage of the store never silently drops a finding.

## Acceptance criteria (EARS)

Dependency gates
- WHILE mctl-api with #774 (PR #799) is not released and deployed on
  `admins-mctl-api`, THE SYSTEM SHALL keep the receiver disabled
  (`securityCodeScanning.enabled: false` in `platform-gitops/bootstrap/values.yaml`).
- WHILE the mctl-api receiver prerequisite is not released, THE SYSTEM SHALL
  NOT register the GitHub repository webhook.
- WHILE mctl-api's `security.yml` does not upload Trivy SARIF to GitHub Code
  Scanning, THE SYSTEM SHALL treat the path as unproven and SHALL NOT claim
  E2E completion.

Credentials
- THE SYSTEM SHALL source the webhook HMAC secret only from Vault
  `secret/platform/mctl-api/github-code-scanning-webhook` (property `secret`)
  through a dedicated ExternalSecret `mctl-api-security-code-scanning` in
  namespace `mctl-api`.
- THE SYSTEM SHALL use a secret distinct from the organization webhook secret
  `platform/mctl-api/github-webhook` already used for pull-request events.
- IF the Vault property is missing THEN THE SYSTEM SHALL degrade only the
  code scanning receiver (route answers 503), and SHALL NOT affect
  `mctl-api-secrets` or `mctl-api-events`.
- THE SYSTEM SHALL NOT contain the secret value in any Git file, Helm values,
  rendered manifest, workflow log or application log.

Authentication and trust
- WHEN a delivery arrives without a valid `X-Hub-Signature-256` for the
  configured secret, THE SYSTEM SHALL reject it with 401 and record no
  observation.
- WHEN a delivery's `X-GitHub-Event` is not `code_scanning_alert`, or its
  `action` is outside the configured allowlist, THE SYSTEM SHALL acknowledge it
  without recording an observation and SHALL count it as ignored.
- WHEN a delivery's `repository.full_name` is not in the configured repository
  allowlist (initially only `mctlhq/mctl-api`), THE SYSTEM SHALL record no
  observation.
- WHEN a delivery's `alert.tool.name` is not in the configured tool allowlist
  (initially only `Trivy`), THE SYSTEM SHALL record no observation.
- THE SYSTEM SHALL submit every observation from this path under
  `provider_ref = github-code-scanning`, as configured in `SECURITY_PROVIDERS`,
  regardless of any `provider`, tool or verification text in the payload.
- THE SYSTEM SHALL configure provider `github-code-scanning` with
  `max_strength: provider_claim` and `tenants: ["admins"]`, and SHALL derive the
  tenant from the configured repository-to-tenant map, never from the payload.
- THE SYSTEM SHALL pass rule text, message text, severity and description
  only in the #774 `untrusted` object.

Delivery and occurrence semantics
- THE SYSTEM SHALL pass `X-GitHub-Delivery` as `delivery_id`, and SHALL pass the
  alert's stable identity (repository, alert number, instance ref) as
  `source_finding_id`.
- WHEN the same delivery is redelivered, THE SYSTEM SHALL produce no second
  observation or occurrence (#774 answers `duplicate`).
- WHEN one SARIF upload yields several alerts, THE SYSTEM SHALL record one
  observation per alert delivery and lose none.
- WHEN two alerts share a CVE but differ in path or line, THE SYSTEM SHALL
  submit distinct subjects so #774 keeps them as distinct occurrences.
- WHEN the action is `created`, `appeared_in_branch`, `reopened` or
  `reopened_by_user`, THE SYSTEM SHALL submit `claimed_action: present`; WHEN it
  is `fixed`, `fixed`; WHEN it is `closed_by_user`, `withdrawn`.
- THE SYSTEM SHALL NOT start remediation, open issues or call mctl-agents from
  the receiver.

Failure handling
- IF the #774 store is unavailable THEN THE SYSTEM SHALL NOT answer 2xx for a
  delivery it has not durably accepted, so GitHub records the delivery as failed.
- WHEN deliveries fail or are rejected, THE SYSTEM SHALL raise an alert
  through `platform-gitops/infra-components/observability/vm-rules/mctl-api-alerts.yaml`.
- THE SYSTEM SHALL document the manual redelivery procedure in
  `docs/runbooks/security-finding-ingestion.md`, because GitHub does not
  redeliver failed deliveries automatically.

Exposure
- THE SYSTEM SHALL expose the receiver only through the existing `api.mctl.ai`
  ingress and the existing `allow-mctl-api-ingress` NetworkPolicy, with no new
  hostname, ingress or Cloudflare rule.

## Out of scope

- SecurityFinding persistence, lifecycle, fingerprinting and dedup (#774).
- Remediation and verification execution (#778).
- Building a scanner, a generic SARIF ingestion platform, or a Trivy parser.
- Writing the receiver code itself (a prerequisite in mctl-api) and the SARIF
  upload step (a prerequisite in mctl-api `security.yml`).
- A Claude Security adapter.
- UI, auto-remediation, auto-merge.
- Repositories other than `mctlhq/mctl-api` in the first rollout.
- Treating webhook absence as verification. "Successful absence" produces no
  `code_scanning_alert` event, so verification stays an active #778 rerun.

## Open questions

- Is GitHub Code Scanning available for `mctlhq/mctl-api`? For a private
  repository this needs GitHub Code Security / Advanced Security. This run
  could not observe the repository's visibility or settings. If it is
  unavailable, the fallback is the bounded native adapter described in
  design.md Alternatives B.
- Does mctl-api's current release (deployed tag `4.124.0`) already contain #774
  (PR #799, merged 2026-10-26)? Not observed. The gate covers both cases.
- How should the in-process receiver authenticate as the configured provider?
  #774 disables a provider that has no entry in `MCTL_SECURITY_PROVIDER_TOKENS`.
  The mctl-api prerequisite must either accept "webhook-secret configured" as
  the channel credential for `github-code-scanning`, or the receiver calls the
  route with its own provider token (an extra Vault property in the same
  ExternalSecret). The design keeps both open, and the ExternalSecret has room
  for either.
- Does a GitHub redelivery reuse the original `X-GitHub-Delivery` GUID? The
  idempotency proof depends on it. It is expected, and test T5 verifies it
  rather than assuming it.
- Automated redelivery of failed deliveries needs a credential with repository
  webhook read/write on mctl-api. This slice leaves it out, and the runbook
  covers manual redelivery. Should a follow-up add a bounded sweep CronWorkflow?
- Trivy SARIF for a filesystem scan carries the package name and version only
  in message text, which is untrusted. The trusted subject is therefore
  repository + path + line (no `package_purl`). This meets the #774 minimum,
  but cross-provider dedup with a purl-bearing provider will not merge.
- Should the SARIF upload cover the same `CRITICAL` gate severity or a broader
  set? That is decided in the mctl-api prerequisite. This slice works with either.
