#!/bin/bash
# Keep ~/.claude/skills in sync with the platform-skills catalog on mctl-gitops main.
#
# Why a dedicated mirror: ~/.claude/skills used to symlink straight into the
# working checkout at ~/PycharmProjects/mctlhq/mctl-gitops. That checkout is
# shared with concurrent agents and routinely sits on a feature branch with
# uncommitted changes, so the skills Claude loaded were whatever branch someone
# left it on. On 2026-08-31 that silently served a review-watch from before the
# quota fix, hours after the fix was published to main.
#
# This mirror is checked out on main, sparse to the catalog, and never edited by
# hand -- skill edits go through the mctl_publish_platform_skill MCP tool, which
# commits to main, and land here on the next run.
set -uo pipefail

MIRROR="$HOME/.claude/skills-catalog"
CATALOG="$MIRROR/platform-gitops/platform-skills/catalog"
SKILLS="$HOME/.claude/skills"
LOG="$HOME/.claude/skills-sync.log"

exec >>"$LOG" 2>&1
echo "[$(date -u +%FT%TZ)] sync start"

if [ ! -d "$MIRROR/.git" ]; then
  echo "  mirror missing at $MIRROR -- recreating"
  rm -rf "$MIRROR"
  git clone --filter=blob:none --no-checkout --single-branch --branch main \
    git@github.com:mctlhq/mctl-gitops.git "$MIRROR" || { echo "  clone FAILED"; exit 1; }
  git -C "$MIRROR" sparse-checkout set --cone platform-gitops/platform-skills/catalog
  git -C "$MIRROR" checkout main || { echo "  checkout FAILED"; exit 1; }
fi

BEFORE=$(git -C "$MIRROR" rev-parse HEAD)
# Hard reset rather than pull: the mirror is a read-only view of main, so local
# divergence (a stray edit, an interrupted fetch) must never block the sync.
if ! git -C "$MIRROR" fetch --quiet origin main; then
  echo "  fetch FAILED (offline? ssh key?) -- keeping existing content"
  exit 1
fi
git -C "$MIRROR" reset --quiet --hard origin/main || { echo "  reset FAILED"; exit 1; }
AFTER=$(git -C "$MIRROR" rev-parse HEAD)
[ "$BEFORE" = "$AFTER" ] && echo "  catalog unchanged at ${AFTER:0:8}" \
                         || echo "  catalog ${BEFORE:0:8} -> ${AFTER:0:8}"

mkdir -p "$SKILLS"

# Adopt every catalog skill. Only ever touch symlinks -- a real directory in
# ~/.claude/skills is a hand-made local skill and is left strictly alone.
for src in "$CATALOG"/*/; do
  name=$(basename "$src")
  dst="$SKILLS/$name"
  if [ -L "$dst" ]; then
    [ "$(readlink "$dst")" = "${src%/}" ] || { ln -sfn "${src%/}" "$dst"; echo "  repointed $name"; }
  elif [ -e "$dst" ]; then
    echo "  SKIP $name -- real directory, not a symlink (local skill?)"
  else
    ln -s "${src%/}" "$dst"; echo "  linked $name (new)"
  fi
done

# Drop symlinks whose target is gone (skill deprecated/renamed upstream).
for dst in "$SKILLS"/*; do
  [ -L "$dst" ] || continue
  [ -e "$dst" ] || { rm "$dst"; echo "  removed $(basename "$dst") (dangling)"; }
done

# /tmp/review-watch.sh is generated from the skill body and caches across
# sessions; a catalog change makes it stale, and its freshness predicate only
# gets consulted when the skill is invoked. Drop it so it is regenerated.
if [ "$BEFORE" != "$AFTER" ] && [ -f /tmp/review-watch.sh ]; then
  rm -f /tmp/review-watch.sh && echo "  dropped stale /tmp/review-watch.sh"
fi

echo "[$(date -u +%FT%TZ)] sync done"
