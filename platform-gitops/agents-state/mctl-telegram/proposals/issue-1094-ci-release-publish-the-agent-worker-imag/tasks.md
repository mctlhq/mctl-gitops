# Tasks: issue-1094-ci-release-publish-the-agent-worker-imag

- [ ] 1. Add the step "Dispatch agent-worker-managed-preview release-deploy" to `.github/workflows/preview-deploy.yml` after the agent-worker-preview step: same inputs, `component_name=agent-worker-managed-preview`, and a comment citing ADR 0008 section 6. DoD: the diff adds only this step; the existing two steps are byte-identical.
- [ ] 2. Add the step "Dispatch agent-worker release-deploy" to `.github/workflows/release-please.yml` directly after "Dispatch centralized release-deploy", gated on `steps.release.outputs.release_created == 'true'`. It uses `GH_TOKEN` from `steps.app`, `TAG` from `steps.release.outputs.tag_name`, `image_name=ghcr.io/mctlhq/agent-worker`, `image_tag="$TAG"`, `git_ref="$TAG"`, `dockerfile_path=Dockerfile.agent-worker`, `team_name=labs` and `component_name=agent-worker-managed`. DoD: the step comes before "Check out the released tag"; no permissions or secrets change.
- [ ] 3. Leave `build.yml` `docker-agent-worker` unchanged. DoD: no diff in `build.yml`.
- [ ] 4. (depends on 1, 2) Add `cmd/agent-worker/deploy_workflows_test.go` with a dispatch-block parser, `checkDeployWorkflows`, `TestDeployWorkflows` and `TestDeployWorkflowsGuardCatchesMutations`, modelled on `cmd/login-proof/workflow_test.go`. DoD: `go test ./cmd/agent-worker/...` passes; `go vet` and `golangci-lint` are clean.
- [ ] 5. In the PR description, state the mutations that make the test fail (removing the managed-preview block, swapping the release image to `agent-worker-preview`, dropping `dockerfile_path`, dropping the `if:` guard, moving the dispatch after `go build`, `push: true` in build.yml). Also state the merge-order dependency on the mctl-gitops component issue. DoD: the PR body lists both.

## Tests
- [ ] T1. `TestDeployWorkflows`: the real workflow files satisfy every invariant (managed-preview dispatch, release dispatch with exact inputs and guard, ordering before the Local Bridge build, build.yml no-push check, existing dispatches still present).
- [ ] T2. `TestDeployWorkflowsGuardCatchesMutations`: each listed mutation changes the source and makes `checkDeployWorkflows` report at least one violation.
- [ ] T3. Manual after merge: the next push to main shows three `release-deploy` runs in mctl-gitops, including `labs/agent-worker-managed-preview main-<sha>`. The next release shows `labs/agent-worker-managed <tag>` and `ghcr.io/mctlhq/agent-worker:<tag>` exists.

## Rollback
Revert the PR (merge commit revert). This removes both new dispatch steps and the test. Images already pushed to `ghcr.io/mctlhq/agent-worker` stay but are unreferenced unless gitops pins them. Gitops tag bumps already made can be left or reverted in mctl-gitops independently. To stop only the production bump, delete the release step alone; the preview step is independent.
