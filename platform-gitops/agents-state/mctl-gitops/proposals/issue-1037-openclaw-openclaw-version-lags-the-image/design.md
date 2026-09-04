# Design: issue-1037-openclaw-openclaw-version-lags-the-image

## Current state

Each openclaw tenant has its own values.yaml consumed by the shared
`base-service` Helm chart:

- `platform-gitops/services/admins/openclaw/values.yaml`
  - `image.tag: "2026.7.11-beta.2"` (line 10, right after a
    `# release-drift: ignore` comment explaining this is a hand-pinned
    upstream mirror, not on the org's normal release train)
  - `env.OPENCLAW_VERSION: "2026.5.14-beta.1"` (line 71)
- `platform-gitops/services/labs/openclaw/values.yaml`
  - `image.tag: "2026.7.11-beta.2"` (line 20)
  - `env.OPENCLAW_VERSION: "2026.5.14-beta.1"` (line 60)
- `platform-gitops/services/ovk/openclaw/values.yaml`
  - `image.tag: "2026.7.11-beta.2"` and
    `env.OPENCLAW_VERSION: "2026.7.11-beta.2"` — already in sync.

The two fields are rendered into completely different parts of the pod spec
by `platform-gitops/helm-charts/base-service`: `image.tag` becomes the
container image reference; `env.OPENCLAW_VERSION` becomes a plain
environment variable on the `base-service` container. Nothing in the chart
ties them together — they are two independent scalar values that happen to
need the same content, by convention rather than by templating.

That convention is documented, not enforced. `platform-gitops/platform-skills/catalog/mctl-platform/references/k8s.md`:

- line 57: "Tag + `OPENCLAW_VERSION` env in
  `platform-gitops/services/<team>/openclaw/values.yaml` (both must stay in
  sync on every bump)."
- line 149 ("Image bump recipe", step 4): "PR on `mctl-gitops` bumping
  `image.tag` **and** `env.OPENCLAW_VERSION` in every tenant's
  `values.yaml` to the new version."

`ovk` shows the recipe was followed there. `admins` and `labs` show it was
missed — `image.tag` moved from whatever it was before up to
`2026.7.11-beta.2` (consistent with the `openclaw-upgrade-2026-5-12` /
`openclaw-cve-upgrade` proposals under
`platform-gitops/agents-state/mctl-openclaw/proposals/`), but
`OPENCLAW_VERSION` was left at `2026.5.14-beta.1`, an earlier version this
repo's proposals do reference (`openclaw-upgrade-2026-5-12`'s design.md
talks about a `v2026.5.12` / `v2026.5.14-beta.2` timeframe).

Nothing today checks the two fields against each other. The closest
existing check, `.github/scripts/release-drift.sh` (wired into
`.github/workflows/release-drift.yml`), compares `image.tag` against the
*upstream GitHub release* of the source repo — a different axis (deployed
vs. released), and it explicitly reads only the `image:` block of a
values.yaml (see `image_block_fields()`), so it has no way to even see
`env.OPENCLAW_VERSION`. `admins` and `ovk` opt out of that check entirely
via `# release-drift: ignore` (both repos' comment: "upstream mirror,
pinned by hand to a vetted pre-release"), which is orthogonal to this
issue: opting out of "are we on the latest upstream release" says nothing
about whether the two fields inside the file agree with each other.

The onboarding path for a *new* tenant is
`platform-gitops/argo-workflows/service-templates/openclaw/values.yaml.tpl`,
rendered by the `create-tenant` / Backstage scaffolder flow (per this
repo's `CLAUDE.md`, "Add a new tenant"). It has:

```
image:
  repository: ghcr.io/mctlhq/mctl-openclaw
  tag: "__IMAGE_TAG__"
...
env:
  APP_ENV: production
  OPENCLAW_VERSION: "2026.3.25-beta.26"
```

`__IMAGE_TAG__` is a real substitution token filled in by the scaffolder;
`OPENCLAW_VERSION` is a plain literal, already stale relative to every
current tenant. Any tenant onboarded from this template today would start
pre-drifted, reproducing the issue at t=0 instead of at the next bump.

`.github/workflows/validate-manifests.yml` is this repo's PR-time gate. It
already runs a series of small, single-purpose Python checkers from
`scripts/` (`validate-profile-version-bumps.py`,
`validate-shell-param-interpolation.py`,
`validate-yq-interpolation.py`, ...), each following the same shape: a
`--selftest` mode that proves the detector fires on a known-bad fixture,
then a real run against the repository. This is the natural place to add a
check for this specific drift, and the natural style to copy.

## Proposed solution

1. **Data fix.** Edit `env.OPENCLAW_VERSION` in
   `platform-gitops/services/admins/openclaw/values.yaml` and
   `platform-gitops/services/labs/openclaw/values.yaml` from
   `"2026.5.14-beta.1"` to `"2026.7.11-beta.2"`, matching each file's own
   `image.tag`. `ovk/openclaw/values.yaml` needs no change. This is a
   one-line value edit per file, no chart changes, no restart-affecting
   structural change beyond what a normal env var edit already causes
   (`base-service` container restarts — same blast radius as any other env
   var bump via `update-config`).

2. **Template fix.** Change
   `platform-gitops/argo-workflows/service-templates/openclaw/values.yaml.tpl`
   so `env.OPENCLAW_VERSION` uses the same `__IMAGE_TAG__` substitution
   token as `image.tag`, e.g.:

   ```
   env:
     APP_ENV: production
     OPENCLAW_VERSION: "__IMAGE_TAG__"
   ```

   This makes the two fields derive from one substitution value at render
   time instead of two independently maintained literals, closing off the
   onboarding-time recurrence of this exact bug. The rendering mechanism
   already supports reusing one token in multiple places: the commit step
   in `platform-gitops/argo-workflows/cluster-templates/tpl-git-commit.yaml`
   (lines 368-375) substitutes `__IMAGE_TAG__` via
   `sed -e "s|__IMAGE_TAG__|${TAG}|g"` — the `g` flag rewrites every
   occurrence in the file, so a second `__IMAGE_TAG__` under `env:` is
   substituted the same way as the one under `image:` with no pipeline
   change required.

3. **New CI guard.** Add `scripts/validate-openclaw-version-pin.py`,
   following the existing `scripts/validate-*.py` pattern (pure stdlib +
   `pyyaml`, a `--selftest` mode, invoked from
   `.github/workflows/validate-manifests.yml` alongside the other
   `scripts/validate-*.py` steps). It:
   - Globs `platform-gitops/services/*/openclaw/values.yaml` (matching this
     repo's tenant layout: `admins`, `labs`, `ovk` today, any future
     openclaw tenant automatically).
   - Reads `image.tag` and `env.OPENCLAW_VERSION` from each file.
   - Fails (prints `::error::`, non-zero exit) for any file where both keys
     are present and their values differ, naming the file and both values,
     mirroring the `::error::` style already used in `release-drift.sh`'s
     `report()` and in `validate-shell-param-interpolation.py`.
   - Passes silently when a file has only one of the two keys (that shape
     is unrelated to this check) or when the tenant directory does not use
     the `openclaw` service template at all.
   - Deliberately ignores `# release-drift: ignore`: per the requirements,
     that marker opts a tenant out of the upstream-release check, not out
     of internal file self-consistency.
   - Ships a `--selftest` that builds a small fixture with a known
     mismatch and asserts the detector fires, plus a matched-fixture case
     that asserts it stays quiet — same shape as
     `validate-shell-param-interpolation.py --selftest`.

This is the minimal change that (a) fixes the two drifted files today, (b)
stops the scaffolder from seeding new drift, and (c) prevents this specific
two-field disagreement from silently reappearing on the next manual or
automated bump — closing the same class of gap that motivated
`release-drift.sh` itself ("neither Argo CD nor release-please raises
anything" for gaps that a human has to notice by hand).

## Alternatives

### A. Fix only the two drifted values, no CI guard
Simplest possible change, and it satisfies the issue's literal ask ("bump
the two env values to match"). Dropped as the sole fix because it does
nothing to prevent recurrence: the documented recipe in `k8s.md` already
told whoever bumped `admins`/`labs` to update both fields, and it was
still missed. A repo that already builds bespoke `scripts/validate-*.py`
checks for narrower classes of drift (profile version bumps, shell
interpolation) has both the precedent and the CI slot to catch this
mechanically instead of relying on a human re-reading a markdown recipe
under time pressure.

### B. Template `OPENCLAW_VERSION` off `image.tag` inside the Helm chart itself
Instead of setting `env.OPENCLAW_VERSION` as a literal in every values.yaml,
have `base-service`'s `deployment.yaml` template default the env var from
`.Values.image.tag` when `env.OPENCLAW_VERSION` is absent, or always derive
it and ignore any values.yaml override to make drift structurally
impossible. Dropped for this proposal: `base-service` is a shared chart
used by more than just openclaw tenants (per `CLAUDE.md`, "used by every
deployed service"), and `OPENCLAW_VERSION` is an openclaw-application-
specific env var name, not a generic chart concept — baking
openclaw-specific knowledge into the generic chart is a bigger, riskier
change than this issue calls for. Worth reconsidering only if a second
service is found to have the same tag/env split problem.

### C. Extend `release-drift.sh` to also check `OPENCLAW_VERSION`
`release-drift.sh` already parses each values.yaml and already has an
`::error::` reporting path, so bolting the check on there was considered.
Dropped: `release-drift.sh` is explicitly scoped to comparing against
*external* GitHub state (`gh api` calls to the source repo) and runs once
a day on a schedule, not on every PR (`on: schedule` / `workflow_dispatch`,
no `pull_request` trigger). A same-file, two-field consistency check is a
pure, fast, offline check that belongs at PR time in
`validate-manifests.yml`, not folded into a slower, network-dependent,
schedule-only script whose failure classification logic (`RELEASE_LAG_HOURS`,
`DEPLOY_LAG_HOURS`, GitHub compare payloads) has nothing to do with this
class of bug.

## Platform impact

- **Migrations:** none. This only changes a plaintext env var value and
  adds an offline CI script; no schema, no data, no S3 state layout change.
- **Backward compatibility:** `OPENCLAW_VERSION` moving from
  `2026.5.14-beta.1` to `2026.7.11-beta.2` on `admins` and `labs` is exactly
  the value `ovk` has already been running with since its own bump, so this
  is a known-safe value from the platform's own experience, not a new
  version being introduced. The requirements explicitly keep "which version
  is correct" out of scope; this only removes the disagreement.
- **Resource impact:** none — a plaintext env var change causes the same
  pod restart as any other `update-config`-class edit already documented
  in `CLAUDE.md`'s "Deploy a new image tag" / "Secrets Management" flows.
  No CPU/memory/replica changes.
- **Risks and mitigations:**
  - *Risk:* if `OPENCLAW_VERSION` gates a real code path inside
    `mctl-openclaw` (a migration, a feature flag, an upstream-compat check)
    that behaves differently at `2026.7.11-beta.2` than at
    `2026.5.14-beta.1`, correcting the env var could newly exercise a path
    that was accidentally dormant on `admins`/`labs`. Mitigation: this is
    exactly the scenario the issue asks to be resolved either way (bump or
    document independence); since no code in this clone documents
    independence, and the binary in the pod is already
    `2026.7.11-beta.2` regardless of what the env var claims, the safer
    state is for the env var to reflect reality. Roll out `admins` and
    `labs` one at a time and watch logs (task 4) rather than both at once.
  - *Risk:* the new CI script has a bug that false-positives on a
    legitimately intentional mismatch (should that ever be introduced).
    Mitigation: the check only fires when both keys exist and disagree,
    and the design explicitly leaves a documented-independence escape
    hatch open (a reviewer can special-case a tenant in the script, the
    same way `# release-drift: ignore` special-cases a tenant in the
    existing script) if a future issue establishes a real reason for
    independence — no such case exists today.
  - *Risk:* the scaffolder template change silently stops working if a
    future refactor of `tpl-git-commit.yaml` moves away from the global
    `sed ... /g` substitution confirmed above. Mitigation: the new CI guard
    from step 3 runs against every tenant's rendered `values.yaml`
    including any newly onboarded one, so a regression here surfaces the
    next time a tenant is onboarded and `validate-manifests` runs against
    its committed file, not silently.
