# Glovo canary P0: immutable, render-only production GitOps package, MCP ingress shape and evidence/hold gates

## Context

Issue mctlhq/mctl-gitops#2569 follows the closed planning issue #2470 under the Direct Production
Canary plan #2457. The first user-facing version will be an authenticated, allowlisted, multi-tenant,
fake-only Streamable HTTP MCP at `https://glovo.mctl.ai/mcp`. It is built from three images: the
public facade and the private fake provider (both mctl-telegram, tg#1235/PR #1259 and tg#1262), and the
trusted control worker (mctl-agents#1044). The issue asks for **P0 preparation only**. It also asks for
the P1 (dark runtime) and P2 (public activation) evidence and hold gates to be written down now, and
each of those phases stays separately gated.

#2470 already landed an inert package in this repo: `deploy/staged/glovo-m1/`, the runbook
`docs/runbooks/glovo-m1.md`, the validator `scripts/validate-glovo-m1-staging.py` and the CI job
`glovo-m1` in `.github/workflows/validate-manifests.yml`. Since then the contracts have moved. The
provider became a bridge-only HTTP client with no Temporal identity (tg#1262, mctl-api#968). The facade
talks to mctl-api, not to the control worker. `GLOVO_TEAM_FALLBACK` was withdrawn (CROSSWALK C2,
M14-M16). The package also lacks image supply-chain fields, the mctl-api F2 migration role wiring
(`glovo_migrator`/`glovo_runtime`, mctl-api#1004 / A15 #2563), and a machine-checked evidence checklist
and hold registry. This proposal brings the staged package up to the target contract. It stays
render-only and inert: nothing is applied, released, routed or activated.

## User stories

- AS the release owner I WANT one staged package that names, for each of the three images, its source
  repo, the pinned source HEAD, the build workflow, the immutable digest, the SBOM, the provenance
  attestation, the vulnerability scan and the release owner SO THAT P1 can bind a GO to exact artifacts.
  Until GHCR confirms an image, its fields stay `<pending>`.
- AS a security reviewer I WANT the staged manifests to show the final network, OAuth audience,
  protected-resource discovery, explicit team selector, allowlist, HTTPS and DNS shape SO THAT I can
  review the public surface before any of it is reconciled.
- AS the platform operator I WANT a deployment evidence checklist with a named slot, phase and owner per
  item SO THAT P1 and P2 cannot be declared done on partial evidence. The items are: manifest and image
  digest, owner grant, Argo Synced/Healthy, DB migration grants and ownership, the Temporal decision,
  scoped secret issuance, readiness and metrics, kill switch and rollback, and the 2x2 negative matrix.
- AS the owner I WANT an exact hold registry (mctl-api#934, #2523, #2528, #2457 P1/P2, mctl-api#1004,
  Temporal isolation, mctl-agents#993, mctl-agents#1007 B4) with an owner, the approval it needs and its
  evidence SO THAT no phase moves while a hold is open.
- AS a reviewer I WANT CI to prove that all of this stays inert SO THAT merging P0 cannot expose
  `glovo.mctl.ai`.

## Acceptance criteria (EARS)

- WHEN a PR touches `deploy/staged/glovo-m1/**`, `scripts/validate-glovo-m1-staging.py` or the
  `glovo-m1` CI job THE SYSTEM SHALL run `validate-glovo-m1-staging.py --selftest`, then the full
  validator, and fail the job on exit 6 (refused) or 7 (unknown).
- THE SYSTEM SHALL keep every Glovo values file, NetworkPolicy, migration Job and patch under
  `deploy/staged/glovo-m1/`. The existing leak guard SHALL keep refusing any `glovo`/`mctl-assistants`
  reference or staged image repository in `platform-gitops/**` outside `agents-state/`.
- WHILE the package is in P0 THE SYSTEM SHALL require, in the staged facade values,
  `ingress.enabled: false`, `GLOVO_ENABLED: "false"`, an empty allowlist, `AUTH_REQUIRED: "true"`, and an
  OAuth resource equal to `https://glovo.mctl.ai/mcp`. The facade's only routed paths SHALL be `/mcp` and
  `/.well-known/oauth-protected-resource`, and its only host SHALL be `glovo.mctl.ai`.
- THE SYSTEM SHALL refuse a staged provider worker that carries any `TEMPORAL_*` env key, a Temporal
  credential ExternalSecret, an Ingress, or a non-ClusterIP Service. Its only allowed egress is DNS and
  the mctl-api bridge.
- THE SYSTEM SHALL refuse the withdrawn `GLOVO_TEAM_FALLBACK` key anywhere in the staged package
  (facade env, `compatibility.yaml`, `budgets.yaml`).
- THE SYSTEM SHALL require a staged facade value that names the explicit team selector, and SHALL refuse
  any value that enables personal scope or a default team.
- WHEN `provenance.yaml` is validated in P0 THE SYSTEM SHALL require, for each of `facade`, `provider`
  and `control`, the keys `repository`, `sourceRepo`, `sourceHead`, `buildWorkflow`, `digest`, `sbom`,
  `provenanceAttestation`, `vulnScan`, `releaseOwner` and `ghcrConfirmed`. It SHALL accept either a
  `<...-pending>` placeholder or a well-formed value.
- IF any image entry has `ghcrConfirmed: true` while its `digest` is not `sha256:<64 hex>` or its
  `sourceHead` is not a 40-hex commit THEN THE SYSTEM SHALL refuse. A digest is never claimed without
  GHCR confirmation.
- THE SYSTEM SHALL provide a P1 provenance policy function (`--policy p1`). It SHALL refuse any pending
  field, and it SHALL run in `--selftest` only. Wiring it into CI is a P1 PR.
- THE SYSTEM SHALL render the facade, provider and control values with a sample `image.digest`, and
  every staged NetworkPolicy and the staged migration Job, through `helm template`/`kubeconform -strict`.
  This proves the digest-pinned shape renders.
- THE SYSTEM SHALL stage the mctl-api F2 migration as text plus manifests under
  `deploy/staged/glovo-m1/api-migration/`. That covers the `glovo_migrator` (DDL) and `glovo_runtime`
  (DML) roles, the `ApplySchema` migration Job shape and a grants/ownership proof query. It SHALL NOT
  modify `platform-gitops/infra-components/data/cnpg/shared/cluster.yaml` or `databases.yaml`.
- THE SYSTEM SHALL keep `deploy/staged/glovo-m1/evidence.yaml`. It has one slot per required evidence
  item, each with `phase` (p1|p2), `owner`, `status` and `evidence` fields. WHILE in P0 every slot SHALL
  have `status: pending` and an empty `evidence`.
- THE SYSTEM SHALL keep `deploy/staged/glovo-m1/holds.yaml` with exactly the holds named in #2569. Each
  has `ref`, `owner`, `requiredApproval`, `evidence` and `state`. It SHALL refuse a missing hold. Like
  `gate.yaml`, it SHALL never read the registry as an unlock.
- IF a staged file contains a secret-shaped value THEN THE SYSTEM SHALL refuse. This is the existing
  `SECRET_SHAPED` check.
- WHEN this proposal is implemented THE SYSTEM SHALL NOT create or change any Argo CD Application, DNS
  record, Vault path, Temporal namespace, image tag, release or runtime flag.

## Out of scope

- Building, tagging, publishing or releasing any image. The CI build workflows live in mctl-telegram and
  mctl-agents. This repo records only their required contract and outputs.
- Any apply: moving files to their `target-paths.yaml` targets, Argo CD Applications, DNS/Cloudflare
  changes, `reservedPlatformHosts` edits, Vault paths, Temporal namespaces or authorizer changes.
- P1 (dark runtime) and P2 (public activation) execution, and wiring the P1 provenance policy into CI.
- Contract crosswalk and drift resolution between slices. That belongs to the separately linked P0 issue
  under #2457; this proposal only consumes CROSSWALK M14-M16.
- The facade contract fix tg#1264, the control worker mctl-agents#1044 and the mctl-api release
  (#934/#2523/#2528) themselves.
- P3: real Glovo credentials, scraping, checkout or payment.

## Open questions

- The facade env key names (`OAUTH_RESOURCE`, the team-selector key, the allowlist key) are still
  placeholders until tg#1264 settles the contract. The proposal stages `GLOVO_TEAM_SELECTOR: explicit`
  as a placeholder and records the final names in `compatibility.yaml` once tg#1264 lands.
- The control worker's target namespace and Temporal namespace name (`admins` / `mctl-assistants` in the
  staged files) are decided by Temporal node I (CROSSWALK section 4). They stay as staged assumptions.
- The facade reaches mctl-api either over `https://api.mctl.ai` (public, via traefik) or in-cluster to
  the `mctl-api` namespace. The proposal stages the in-cluster egress NetworkPolicy and keeps
  `MCTL_API_URL` public-HTTPS. The P1 owner chooses.
- Whether the mctl-api F2 roles live in shared-pg `cluster.yaml` `managed.roles` or are created by the
  migration itself depends on mctl-api#1004 / A15 (#2563). Neither was readable at a pinned revision in
  this run, so the staged patch documents both and marks the choice for A15.
- The release owner for each image is not named in the issue. It is staged as
  `<release-owner-pending>`.
