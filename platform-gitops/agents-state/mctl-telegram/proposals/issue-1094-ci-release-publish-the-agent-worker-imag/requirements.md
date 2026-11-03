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
- WHEN a commit is pushed to `main` THE SYSTEM SHALL dispatch `mctlhq/mctl-gitops` `release-deploy.yaml` with `repo=mctlhq/mctl-telegram`, `git_ref=<sha>`, `image_name=ghcr.io/mctlhq/agent-worker-preview`, `image_tag=main-<short sha>`, `dockerfile_path=Dockerfile.agent-worker`, `team_name=labs`, `component_name=agent-worker-managed-preview`.
- WHEN a commit is pushed to `main` THE SYSTEM SHALL continue to dispatch the existing `mctl-telegram-preview` and `agent-worker-preview` deploys unchanged.
- WHEN release-please creates a release (`release_created == 'true'`) THE SYSTEM SHALL dispatch `release-deploy.yaml` with `repo=mctlhq/mctl-telegram`, `git_ref=$TAG`, `image_name=ghcr.io/mctlhq/agent-worker`, `image_tag=$TAG`, `dockerfile_path=Dockerfile.agent-worker`, `team_name=labs`, `component_name=agent-worker-managed`.
- WHEN release-please creates a release THE SYSTEM SHALL dispatch the agent-worker release deploy before the Local Bridge binary build steps, so that a failed cross-compile cannot block it.
- IF release-please did not create a release THEN THE SYSTEM SHALL NOT dispatch the agent-worker release deploy.
- WHILE a pull request is open THE SYSTEM SHALL keep building `Dockerfile.agent-worker` in `build.yml` job `docker-agent-worker` with `push: false`. That job name and its no-push behaviour stay unchanged.
- IF any of the dispatches above is removed, or one of its `image_name`, `dockerfile_path`, `component_name` or tag inputs is changed, THEN THE SYSTEM SHALL fail `go test ./cmd/agent-worker/...`.
- THE SYSTEM SHALL use only the existing `mctl-agents` App token (`AGENTS_APP_CLIENT_ID` / `AGENTS_APP_PRIVATE_KEY`) for the new dispatches. It shall add no new secret and no new job permission.

## Out of scope
- Creating `platform-gitops/services/labs/agent-worker-managed-preview/` and `.../agent-worker-managed/` values, ExternalSecrets and Vault paths. That is the separate mctl-gitops issue.
- A slimmer worker image without Node and the claude CLI. ADR section 6 calls it a follow-up.
- Changing the preview image name to `agent-worker`. Preview stays on `agent-worker-preview`, per the issue.
- Server flags (`MANAGED_RUNTIME_ENABLED`, caps) and the rollout and soak itself.
- Any change to mctl-gitops `release-deploy.yaml` or `build-image.yaml`.

## Open questions
- Merge order with the gitops issue. `release-deploy.yaml` (mctl-gitops, "update gitops" step) exits with `ERROR: file(s) not found` when `platform-gitops/services/<team>/<component>/values.yaml` does not exist. It does this after the image build job has already pushed. Neither component exists in gitops today. Proceeding on: merge the gitops components first, or accept one or more red release-deploy runs until they land. The image still gets pushed in that case.
- Preview build duplication. The issue asks for a third dispatch block, which builds and pushes the same `agent-worker-preview:main-<sha>` tag a second time in parallel. `release-deploy.yaml` accepts a comma-separated `values_path` that could bump both preview components from one build. Proceeding on the literal issue (third dispatch block) and recording the alternative in design.md.
