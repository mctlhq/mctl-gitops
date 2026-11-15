# Spike: ZITADEL vs Vault as the Temporal workload JWT issuer (document-only)

## Context

ADR 0003 (`docs/adr/0003-temporal-client-authz.md`, status Proposed) picks
Vault identity-engine JWTs, delivered to a file by ESO `VaultDynamicSecret`, as
the identity of Temporal clients. Separately, the platform runs ZITADEL v4.19.2
at `https://auth.mctl.ai` (`docs/runbooks/zitadel.md`) for human and business
identity, and it already holds one machine user
(`zitadel_machine_user.customer_lifecycle` in
`platform-gitops/helm-charts/zitadel-iac/iac/customers.tf`). Issue #2506 asks
whether moving the Temporal machine issuer to ZITADEL would reduce operational
and security complexity without weakening the shared OSS Temporal frontend or
the existing `mctl-agents` / `kuptsi` isolation.

Spike #2469 has already established, from `temporalio/temporal@v1.31.0`
source, that the stock claim mapper does not validate `iss`, enforces `aud`
only when `global.authorization.audience` is non-empty, fetches JWKS with
`http.Get` and system trust roots only, and accepts RS256/ES256 only
(`docs/runbooks/temporal-authz-role-matrix.md`). Its verdict is `BLOCKED`
(`docs/runbooks/temporal-client-auth.md`). This spike must reuse that evidence
rather than restate it, compare four issuer options against it, and produce a
single verdict plus a proposed ADR amendment. Nothing in the spike changes
runtime state.

## User stories

- AS a platform security owner I WANT a source-backed comparison of Vault and
  ZITADEL as the Temporal workload issuer SO THAT the issuer choice does not
  silently widen who can control DevLoop or kuptsi workflows.
- AS the ADR 0003 approver I WANT one explicit verdict and a proposed
  amendment text SO THAT I can accept or reject it as a separate decision.
- AS the operator of the future #2469 canary (node F) I WANT negative tests
  that are issuer-specific and mapped to T1-T11 SO THAT the canary proves the
  chosen issuer, not just the authorizer.
- AS a platform operator I WANT the cost, rotation and incident-recovery
  burden of each option stated SO THAT the choice is supportable at 03:00.

## Acceptance criteria (EARS)

- WHEN the spike document is written THE SYSTEM SHALL be a single new file
  `docs/spikes/2506-temporal-jwt-issuer.md` and SHALL change no file under
  `platform-gitops/`, `infrastructure/` or `docs/adr/`.
- THE SYSTEM SHALL label every fact as `VERIFIED_SOURCE` (Git or upstream
  source at a pinned commit or tag), `VERIFIED_LIVE` (dated operator command
  output) or `NOT_OBSERVED`, using the vocabulary of
  `docs/runbooks/temporal-client-auth.md`; a `NOT_OBSERVED` fact SHALL never be
  stated as absent.
- THE SYSTEM SHALL cite the #2469 documents for every Temporal server fact it
  relies on and SHALL NOT present any #2469 inventory row as new live proof.
- THE SYSTEM SHALL inventory, from `platform-gitops/helm-charts/zitadel-iac/iac/`,
  the existing ZITADEL projects, machine users, token types, project checks and
  Actions v2 token hooks, and SHALL state for each whether it is reusable for
  Temporal.
- THE SYSTEM SHALL compare options A (Vault workload JWT), B (ZITADEL M2M JWT),
  C (hybrid: ZITADEL for humans/business, Vault for Temporal workloads) and
  D (no-go pending a custom mapper or a better JWKS trust path) on: claim
  compatibility with the stock mapper, issuer/audience enforcement, JWKS trust
  path, signing-key sharing, trusted computing base, TTL and refresh, rotation,
  revocation, JWKS outage behaviour, audit provenance, platform cost, migration,
  rollback and incident recovery.
- THE SYSTEM SHALL answer research questions 1-4 of #2506 each with a cited
  answer or an explicit `NOT_OBSERVED` gap.
- THE SYSTEM SHALL state exactly one verdict from `KEEP_VAULT_JWT`,
  `UNIFY_ZITADEL_M2M`, `HYBRID_WITH_BOUNDARIES`,
  `BLOCKED_NEEDS_AUTHORIZER_OR_TRUST_PATH` or `DEFER`, together with the
  conditions that would change it.
- THE SYSTEM SHALL include a threat model covering at least: tenant or provider
  token replay, self-asserted permissions, issuer compromise, signing-key
  compromise, JWKS spoofing or outage, credential theft from a pod, and
  cross-namespace control calls.
- THE SYSTEM SHALL include a role/claim mapping from each ADR 0003 identity to
  its `permissions` value and to the issuer-side object that binds it, so that
  no workload can self-assert a role.
- THE SYSTEM SHALL include an issuer-specific negative-test contract whose
  steps map onto ADR 0003 T1-T11 and `docs/runbooks/temporal-auth-canary.md`
  S1-S17, adding only issuer-specific steps and stop conditions.
- THE SYSTEM SHALL include a proposed ADR 0003 amendment as text inside the
  spike document only, marked "proposed, not adopted".
- THE SYSTEM SHALL name the handoff into the #2469 DAG (which node each
  finding feeds) and SHALL NOT create a competing roadmap or new DAG.
- WHILE #2469 is `BLOCKED` THE SYSTEM SHALL NOT recommend any TLS, credential
  or authorizer enablement, whatever the verdict.
- IF a verdict depends on a fact that is `NOT_OBSERVED` THEN THE SYSTEM SHALL
  name that fact as a precondition of the verdict.
- IF option B is selected THEN THE SYSTEM SHALL show how the stock mapper's
  `permissions` array-of-strings claim is produced without a custom server
  build and without a claim the workload or its organization can influence;
  otherwise option B SHALL NOT be selected.
- WHEN the document is merged THE SYSTEM SHALL leave ADR 0003 status
  `Proposed` and #2457 release blockers unchanged.

## Out of scope

- Any ZITADEL, Vault, ESO, Kubernetes, NetworkPolicy or Temporal server change;
  any new machine user, Vault role, OIDC key, ExternalSecret or credential.
- Claim mapper or authorizer builds or deployment, namespace creation, endpoint
  activation, TLS, canary deployment or any test against production.
- Editing or adopting ADR 0003; the amendment is a deliverable only.
- Approval of mctl-api#962, release or activation grants, Glovo rollout.
- Re-running the #2469 inventory or the Temporal role/RPC matrix.

## Open questions

- ZITADEL v4.19.2 web-key algorithm and rotation: whether the instance signs
  access tokens with RSA or ECDSA (Temporal accepts RS256/ES256 only) and
  whether keys rotate automatically. Not declared in
  `bootstrap/templates/core-infra/zitadel.yaml` or the IaC; `NOT_OBSERVED`.
  Treated as a precondition of option B, not resolved by this spike.
- Whether ZITADEL Actions v2 `preaccesstoken` may append a top-level
  `permissions` array claim (name collisions with reserved claims, size
  limits). Upstream docs/source at v4.19.2 must be cited; if not citable the
  spike records it as a gap.
- Whether Vault's identity OIDC JWKS is reachable over HTTPS through
  `https://secrets.mctl.ai/v1/identity/oidc/.well-known/keys` from the
  `temporal` namespace. The listener is plaintext (`tls_disable = 1`) and the
  public hostname is Cloudflare-fronted; mctl-api moved off it after a
  five-hour in-cluster timeout on 2026-10-09
  (`bootstrap/templates/mctl-platform/mctl-api.yaml`). This feeds #2469 node C;
  the spike does not decide node C.
- The issue's DEFER versus HYBRID wording: this proposal reads "one explicit
  verdict or BLOCKED" as allowing a direction verdict (HYBRID) that is
  explicitly conditional on #2469 node C and the canary, rather than requiring
  `BLOCKED_NEEDS_AUTHORIZER_OR_TRUST_PATH` as the only outcome while #2469 is
  blocked. The reviewer may prefer the latter label; the document states both
  readings and why HYBRID was chosen.
