# Fix OPENCLAW_VERSION drift from image.tag in openclaw values.yaml

## Context

Every tenant's `platform-gitops/services/<team>/openclaw/values.yaml` pins two
independent copies of the same version: `image.tag` (the container image
actually deployed) and `env.OPENCLAW_VERSION` (an environment variable read
by the `mctl-openclaw` process itself). The platform's own documentation,
`platform-gitops/platform-skills/catalog/mctl-platform/references/k8s.md`,
states plainly that "Tag + `OPENCLAW_VERSION` env ... (both must stay in
sync on every bump)" and its "Image bump recipe" (step 4) instructs bumping
"`image.tag` **and** `env.OPENCLAW_VERSION` in every tenant's `values.yaml`"
together.

That convention was not followed for two of the three tenants. As of this
proposal:

| Tenant | `image.tag` | `env.OPENCLAW_VERSION` | In sync? |
|---|---|---|---|
| `admins` | `2026.7.11-beta.2` | `2026.5.14-beta.1` | No |
| `labs` | `2026.7.11-beta.2` | `2026.5.14-beta.1` | No |
| `ovk` | `2026.7.11-beta.2` | `2026.7.11-beta.2` | Yes |

`admins` and `ovk` were bumped to `2026.7.11-beta.2` (per prior proposals
`openclaw-upgrade-2026-5-12` / `openclaw-cve-upgrade` / `openclaw-cve-batch`
under `platform-gitops/agents-state/mctl-openclaw/proposals/`), but only
`ovk`'s `OPENCLAW_VERSION` was bumped along with `image.tag`. `admins` and
`labs` are left announcing a version banner, and feeding any migration or
upstream-sync check gated on `OPENCLAW_VERSION`, that is two releases
behind the binary actually running in the pod. Issue #1032 (image tag bump)
and #1036 did not touch these two lines, so the drift has stood since
whichever PR bumped `image.tag` without the paired env update.

Separately, `platform-gitops/argo-workflows/service-templates/openclaw/values.yaml.tpl`
— the Backstage scaffolder template used to onboard a brand-new openclaw
tenant — hardcodes `OPENCLAW_VERSION: "2026.3.25-beta.26"` as a literal,
independent of the `image.tag: "__IMAGE_TAG__"` placeholder it sits a few
lines above. Every newly onboarded tenant starts from this stale, unrelated
value, which is the same failure mode as the issue, just at onboarding time
instead of at bump time. Fixing only the three existing tenants' values.yaml
would leave the next `create-tenant` / onboarding run reproducing the exact
same class of drift.

## User stories

- AS a platform operator I WANT `OPENCLAW_VERSION` to always match
  `image.tag` in every tenant's `values.yaml` SO THAT the version banner,
  migrations, and any upstream-sync check gated on that env variable see
  the version of the binary that is actually running.
- AS a maintainer following the "Image bump recipe" in `k8s.md` I WANT a CI
  check that fails a PR bumping one of the two fields without the other SO
  THAT this drift cannot silently reappear on the next version bump.
- AS an operator onboarding a new tenant I WANT the scaffolder template to
  seed `OPENCLAW_VERSION` from the same value as `image.tag` SO THAT a
  freshly onboarded tenant does not start pre-drifted.

## Acceptance criteria (EARS)

- WHEN this proposal is applied THE SYSTEM SHALL have
  `env.OPENCLAW_VERSION` equal to `image.tag` in
  `platform-gitops/services/admins/openclaw/values.yaml`,
  `platform-gitops/services/labs/openclaw/values.yaml`, and
  `platform-gitops/services/ovk/openclaw/values.yaml`.
- WHEN `platform-gitops/argo-workflows/service-templates/openclaw/values.yaml.tpl`
  is rendered for a new tenant THE SYSTEM SHALL populate
  `env.OPENCLAW_VERSION` from the same `__IMAGE_TAG__` substitution used for
  `image.tag`, not a separate hardcoded literal.
- WHEN a pull request changes `image.tag` or `env.OPENCLAW_VERSION` under
  `platform-gitops/services/*/openclaw/values.yaml` such that the two no
  longer match THE SYSTEM SHALL fail the `validate-manifests` CI job with an
  error naming the file and both mismatched values.
- IF a values.yaml carries the existing `# release-drift: ignore` marker
  (a tenant deliberately held on an older release per
  `.github/scripts/release-drift.sh`) THEN THE SYSTEM SHALL still require
  `OPENCLAW_VERSION` to match that same held-back `image.tag` — the marker
  opts a tenant out of chasing upstream releases, it does not license the
  two fields to disagree with each other.
- WHILE no proposal or human explicitly documents `OPENCLAW_VERSION` as
  intentionally independent of `image.tag` THE SYSTEM SHALL treat any
  mismatch between them as a defect, consistent with the existing `k8s.md`
  documentation.

## Out of scope

- Deciding whether `2026.7.11-beta.2` is the correct target version for any
  tenant, or performing a fresh image bump. This proposal only closes the
  gap between the two fields at whatever `image.tag` each tenant already
  has pinned; it does not change what that pinned tag is.
- Changing what `OPENCLAW_VERSION` gates inside the `mctl-openclaw`
  application code (version banner text, migration logic, upstream-sync
  checks). That logic lives in the `mctl-openclaw` repo, not here.
- The broader `release-drift.sh` check, which compares `image.tag` against
  upstream GitHub releases of the source repo. That is a different kind of
  drift (deployed vs. released) from the one in this issue (two fields
  inside the same file disagreeing with each other) and is already covered
  by its own workflow.
- Any change to the fork-sync process described in proposal
  `issue-38-sync-mctl-openclaw-fork-with-upstream-op`.

## Open questions

- The issue itself raises the possibility that `OPENCLAW_VERSION` is
  "meant to be independent of the image." No file in this clone documents
  that as intentional, and `k8s.md` explicitly documents the opposite (kept
  in sync on every bump), so this proposal takes the "must match" reading
  as the correct one and treats the current state as a bug, per the
  issue's own framing ("Either bump ... or, if independent, say so"). If a
  human reviewer knows of an actual reason for independence, this proposal
  should be rejected in favor of documenting that reason next to the env
  var instead.
- Exactly which PR introduced the drift for `admins` and `labs` (bumped
  `image.tag` without the paired `OPENCLAW_VERSION` line) is not
  determinable from this shallow, read-only clone (only one commit of
  history is visible). This does not block the fix; it would only help a
  human wanting to add a regression note to that specific PR.
