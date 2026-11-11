# Release bump through a pull request (mctlhq/mctl-gitops#2543, stage 1 fast track)

This is a **fast PR-based path**, not the elimination of the DeployKey P1.
The `DeployKey` bypass actor on ruleset 18465404 stays, and so do the deploy
keys, until every writer is migrated. #2543 stays open until the old bypass
credentials are gone. Nothing here adds `mctl-gitops-pr`, `mctl-agents` or
`mctl-app` to the ruleset's bypass actors.

## What changes

`release-deploy.yaml` and `gitops-bump.yaml` no longer push from the job that
edits the values files. Three jobs:

| Job | Holds | Does |
|---|---|---|
| `bump` | no environment, no secret, `contents: read` | reads the route, runs the release gate `check`, edits the files, makes one commit and hands it over as a patch |
| `publish-direct` | environment `gitops-bump` (deploy key) | applies the patch to a fresh `main`, runs `release-gate.py verify --policy-rev origin/main`, pushes to `main`. Used for every image not listed below |
| `publish-pr` | environment `app-gitops-pr` (`mctl-gitops-pr` App key) | applies the patch, re-authors it as the App bot, runs the gate and the tag-only guard, pushes **only** to `release-bump/<service>-<tag>` and opens a pull request |

`platform-gitops/release-bump-routes.yaml` lists the images on the PR route
(initially `ghcr.io/mctlhq/mctl-api`). `scripts/release-bump-route.py` reads it:
a missing, unreadable or malformed file fails the release, it never falls back
to either route.

## How the PR lands

1. The App opens the PR. `claude-review.yml` lists `mctl-gitops-pr` in
   `allowed-bots`, so the review runs.
2. After an approving review, `auto-merge.yml` checks that the author is
   `mctl-gitops-pr[bot]`, the head is in this repository, and
   `scripts/release-bump-diff-guard.py` accepts the diff at the judged head:
   only image tag lines, paired one to one, same key and image name, at most 8
   files under the three allowed `platform-gitops/` prefixes. Anything else is a
   human merge.
3. It waits until GitHub reports the PR `CLEAN` (approval and the required
   checks `validate`, `cloudflare-plan`, `reserved-hosts`, which run the release
   gate on the PR) and merges the exact head it judged, with a merge commit.

The release hold of #2528 (`version_holds`), the bootstrap gate of #2590 and the
exact-head checks are unchanged: the gate runs before the write in `bump`, again
on the tree to push in each publishing job, and again as the `validate` check.

## Overlapping releases and a stuck bump

- Opening a bump closes every open `release-bump/<service>-<MAJOR.MINOR.PATCH>`
  PR of the same service that the App opened and whose tag is strictly LOWER
  ("Superseded by #N"), and deletes its branch. Tags are ordered numerically
  from the branch suffix; a suffix that is not exactly that shape is never
  matched, so another service named `<service>-<digit>` is untouched. If the new
  tag cannot be ordered, nothing is closed (a warning). A failed listing fails
  the job; it is never read as "nothing to supersede".
- If an open bump of the service is NEWER than this release (a re-run of an old
  release, or crossed dispatches), this release closes its own PR and fails: the
  newer tag is never dropped and the old run is red.
- `await-bump` waits up to 50 minutes for the PR to be MERGED and fails if it is
  closed unmerged, in an unexpected state, or does not merge in time. A PR
  closed by a newer release is only a notice. It is a separate job with no
  environment, no secret, read-only access, and outside the `gitops-bump`
  concurrency group (which in gitops-bump.yaml now covers only publish-direct
  and publish-pr), so a 50-minute wait cannot hold or cancel other bumps.
- `bump` builds its patch from main as it was when that job ran, so two close
  releases of one image conflict on the same tag line. Both publishing jobs
  apply the patch with `scripts/release-bump-apply.sh`: a conflict is resolved
  in favour of the patch (the newer release wins) and the result is judged
  against main by the diff guard with `--strict-order --same-lines-as <patch>`.
  It lands only if it is a FORWARD MAJOR.MINOR.PATCH move of exactly the lines
  the patch bumps. An older release that lost the race, tags that cannot be
  ordered (`main-<sha>`, `staging-N`), or a resolution that would revert a
  neighbouring image line changed on main, fail red instead of landing.
- The bump branch is `release-bump/<image basename>-<tag>` in both workflows, so
  a bump opened by either is seen (and superseded) by the other.
- A DIRTY PR can still arise if an unrelated PR touches the same lines; the
  wait times out red and a human rebases or re-runs the release.

## Roll back

Remove the image from `release-bump-routes.yaml` in a reviewed PR; the next
release goes through `publish-direct` again.

## Pending evidence (only a live trial shows these)

- the review approves a PR opened by the App and `auto-merge.yml` fires for it;
- `validate` finishes within the 45 minutes `auto-merge.yml` waits;
- the App's token cannot push `main` (expected: not a bypass actor).
