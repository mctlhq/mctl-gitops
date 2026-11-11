#!/usr/bin/env bash
# Apply the bump patch written by the `bump` job onto the current checkout of
# main (mctlhq/mctl-gitops#2543). Run from the repository root with a git
# identity configured; the patch is a single `git format-patch` commit.
#
# `bump` builds its patch from main as it was when that job ran. Another bump of
# the same image can land in between, and then the same tag line conflicts. A
# bump is only an image tag move, so the conflict is resolved in favour of the
# patch (the newer release wins) and the result is then judged against main by
# release-bump-diff-guard.py: anything but paired image-tag lines (an unrelated
# line of the same file reverted by taking the patch side, or a tag moving
# backwards because an OLDER release lost the race) is refused. Failing here is
# visible and never pushes; the caller stops on a non-zero exit.
set -euo pipefail

patch=${1:?usage: release-bump-apply.sh <patch>}

if git am --3way "$patch"; then
  exit 0
fi

# git am stopped. Only a plain content conflict is resolved; anything else
# (a patch that does not apply at all, a missing file) is a failure.
conflicted=$(git diff --name-only --diff-filter=U) || { git am --abort || true; echo "::error::could not list conflicted files"; exit 1; }
if [[ -z "$conflicted" ]]; then
  git am --abort || true
  echo "::error::bump patch does not apply and there is nothing to resolve"
  exit 1
fi
while IFS= read -r f; do
  git checkout --theirs -- "$f"
  git add -- "$f"
done <<< "$conflicted"
GIT_EDITOR=true git am --continue

# The resolved commit must still be nothing but an image tag move over main.
git diff "$(git rev-parse HEAD~1)" HEAD | python3 scripts/release-bump-diff-guard.py || {
  echo "::error::the conflict resolution is not a plain image tag move over main (a newer bump may already be there); refusing"
  exit 1
}
