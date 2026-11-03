# CI: publish the agent-worker release image and dispatch agent-worker-managed-preview

## Context
Issue #1094 (part of epic #1088, P5 of #1002; ADR `docs/adr/0008-managed-runtime.md` section 6) asks for two
changes to this repo's CI. These changes add the deploy plumbing for the managed agent runtime. First, every
merge to `main` must also bump the new preview component `labs/agent-worker-managed-preview`, which runs the
same `ghcr.io/mctlhq/agent-worker-preview:main-<sha>` image that `labs/agent-worker-preview` runs today. Second,
every release must build and publish a release-tagged worker image `ghcr.io/mctlhq/agent-worker:<tag>` from
`Dockerfile.agent-worker` and bump the production component `labs/agent-worker-managed`.

Today `.github/workflows/preview-deploy.yml` dispatches two builds: the server and `agent-worker-preview`.
`.github/workflows/release-please.yml` dispatches only the server image. No release-tagged worker image exists,
so the ADR's production step ("with the release image `ghcr.io/mctlhq/agent-worker:<tag>` published by the
release workflow") cannot happen. The matching gitops components are a separate issue in mctl-gitops.

## User stories
- AS the platform operator I WANT each merge to main to bump `agent-worker-managed-preview` in gitops SO THAT the managed-runtime preview soak always runs current main, the same way `agent-worker-preview` does.
- AS the platform operator I WANT each release to publish `ghcr.io/mctlhq/agent-worker:<tag>` SO THAT production `agent-worker-managed` runs an immutable, release-tagged worker image instead of a `main-<sha>` preview build.
- AS a reviewer I WANT a Go test that pins these dispatches SO THAT a later workflow edit cannot silently drop them.

## Acceptance criteria (EARS)
- WHEN a commit is pushed to `main` AND the gitops existence guard reports `platform-gitops/services/labs/agent-worker-managed-preview/values.yaml` present on mctl-gitops `main` THE SYSTEM SHALL dispatch `mctlhq/mctl-gitops` `release-deploy.yaml` with `repo=mctlhq/mctl-telegram`, `git_ref=<sha>`, `image_name=ghcr.io/mctlhq/agent-worker-preview`, `image_tag=main-<short sha>`, `dockerfile_path=Dockerfile.agent-worker`, `team_name=labs`, `component_name=agent-worker-managed-preview`.
- WHEN a commit is pushed to `main` THE SYSTEM SHALL continue to dispatch the existing `mctl-telegram-preview` and `agent-worker-preview` deploys unchanged and unguarded.
- WHEN release-please creates a release (`release_created == 'true'`) AND the gitops existence guard reports `platform-gitops/services/labs/agent-worker-managed/values.yaml` present on mctl-gitops `main` THE SYSTEM SHALL dispatch `release-deploy.yaml` with `repo=mctlhq/mctl-telegram`, `git_ref=$TAG`, `image_name=ghcr.io/mctlhq/agent-worker`, `image_tag=$TAG`, `dockerfile_path=Dockerfile.agent-worker`, `team_name=labs`, `component_name=agent-worker-managed`.
- WHEN release-please creates a release THE SYSTEM SHALL run the guarded agent-worker release dispatch before the Local Bridge binary build steps, so that a failed cross-compile cannot block it.
- IF release-please did not create a release THEN THE SYSTEM SHALL NOT dispatch the agent-worker release deploy.

### Gitops existence guard (owner amendment 2026-11-03)
`release-deploy.yaml` has no build-only mode: it exits 2 (`ERROR: file(s) not found`) when the component's
values file is missing. `agent-worker-managed-preview` is created only by mctl-gitops#2345, which the roadmap
opens after this issue closes, and production `agent-worker-managed` is not created by #2345 at all (production
follows mctl-telegram#889/#334). Unguarded, every merge to `main` and every release (several a day) would leave
a red `release-deploy` run for weeks. Each new dispatch is therefore guarded; the two existing dispatches are not.
- BEFORE each new dispatch THE SYSTEM SHALL read the component's values file on mctl-gitops `main` through the GitHub contents API with the dispatch step's existing App token.
- IF the read answers HTTP 200 THEN THE SYSTEM SHALL dispatch.
- IF the read answers HTTP 404 THEN THE SYSTEM SHALL NOT dispatch, SHALL emit one `::notice::` naming the missing path and the component, and SHALL let the job succeed.
- IF the read fails in any other way (any other HTTP status, a transport error, a missing token, a missing status code) THEN THE SYSTEM SHALL fail the step. A read that could not be observed is never treated as "component absent".
- WHILE `agent-worker-managed` does not exist in gitops THE SYSTEM SHALL NOT publish `ghcr.io/mctlhq/agent-worker:<tag>`. The issue's acceptance "a release publishes `ghcr.io/mctlhq/agent-worker:<tag>`" holds from the first release after that component lands, which belongs to the production rollout after #889/#334.
- WHILE a pull request is open THE SYSTEM SHALL keep building `Dockerfile.agent-worker` in `build.yml` job `docker-agent-worker` with `push: false`. That job name and its no-push behaviour stay unchanged.
- IF any of the dispatches above is removed, or one of its `image_name`, `dockerfile_path`, `component_name` or tag inputs is changed, or a new dispatch loses its existence guard, or the guard's path no longer matches the dispatch's component, THEN THE SYSTEM SHALL fail `go test ./cmd/agent-worker/...`.
- IF the existence guard treats any answer other than HTTP 404 as "absent", or any answer other than HTTP 200 as "present", THEN THE SYSTEM SHALL fail `go test ./cmd/agent-worker/...`.
- THE SYSTEM SHALL use only the existing `mctl-agents` App token (`AGENTS_APP_CLIENT_ID` / `AGENTS_APP_PRIVATE_KEY`) for the new dispatches and the guard reads. It shall add no new secret and no new job permission.

## Out of scope
- Creating `platform-gitops/services/labs/agent-worker-managed-preview/` and `.../agent-worker-managed/` values, ExternalSecrets and Vault paths. That is the separate mctl-gitops issue.
- A slimmer worker image without Node and the claude CLI. ADR section 6 calls it a follow-up.
- Changing the preview image name to `agent-worker`. Preview stays on `agent-worker-preview`, per the issue.
- Server flags (`MANAGED_RUNTIME_ENABLED`, caps) and the rollout and soak itself.
- Any change to mctl-gitops `release-deploy.yaml` or `build-image.yaml`.

## Open questions
- Merge order with the gitops issue: RESOLVED by the owner amendment of 2026-11-03 (gitops existence guard above). Landing the gitops components first is impossible for preview (the roadmap opens mctl-gitops#2345 only after this issue closes) and out of scope for production, and accepting red runs was rejected.
- Preview build duplication. The issue asks for a third dispatch block, which builds and pushes the same `agent-worker-preview:main-<sha>` tag a second time in parallel. `release-deploy.yaml` accepts a comma-separated `values_path` that could bump both preview components from one build. Proceeding on the literal issue (third dispatch block) and recording the alternative in design.md.
