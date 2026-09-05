#!/usr/bin/env bash
# Show, per service image, the three states that "the PR is merged" hides:
#
#   merged    releasable commits on main that no tag covers yet
#   released  the latest GitHub release / tag of the source repository
#   deployed  the tag pinned in platform-gitops/services/*/*/values.yaml
#
# Why this exists: on 2026-09-03 release-please on mctl-telegram started
# failing on every push to main (the org forbids GITHUB_TOKEN from creating
# pull requests). Seven releasable merges later nothing had shipped, every
# merge was green, and the preview environment tracked main, so the gap was
# invisible until someone compared the prod tag by hand (mctl-telegram#498).
# Neither Argo CD nor release-please raises anything for "main is ahead of
# the last tag": one sees only the tag it is given, the other only its own
# run. This script asks all three questions and fails when they disagree
# for longer than a release should take.
#
# Usage:
#   release-drift.sh              # needs GH_TOKEN able to read every source repo
#   release-drift.sh --self-test  # exercises the classifiers on fixtures
#
# Exit 1 when any image is in a drifted state, 0 otherwise. Images whose
# source repository is not on GitHub under mctlhq, or that pin a non-release
# tag (main-<sha> previews, bare SHAs), are reported and skipped.
set -euo pipefail

ORG="${ORG:-mctlhq}"
SERVICES_DIR="${SERVICES_DIR:-platform-gitops/services}"
# How long merged, releasable work may wait for a tag before that counts as
# drift. release-please cuts a PR within minutes; a day covers the human
# merge of that PR.
RELEASE_LAG_HOURS="${RELEASE_LAG_HOURS:-24}"
# How long a published release may wait for the gitops bump. release-deploy
# builds and bumps in ~10 min; two hours absorbs a retry.
DEPLOY_LAG_HOURS="${DEPLOY_LAG_HOURS:-2}"

now_epoch() { date -u +%s; }
to_epoch() {
  # GNU date on the runner; BSD date locally.
  date -u -d "$1" +%s 2>/dev/null || date -u -j -f '%Y-%m-%dT%H:%M:%SZ' "$1" +%s
}
strip_v() { printf '%s' "${1#v}"; }

# A tag that release-please or a human tagged as a version. Anything else
# (main-<sha>, bare SHAs, dates) is a preview or a manual pin and is not a
# release this check can reason about.
RELEASE_TAG_RE='^[0-9]+\.[0-9]+\.[0-9]+([-.][0-9A-Za-z.]+)?$'
is_release_tag() {
  [[ "$(strip_v "$1")" =~ $RELEASE_TAG_RE ]]
}

# Conventional-commit subjects that bump a release: the same set
# release-please's default changelog sections treat as releasable.
RELEASABLE_RE='^(feat|fix|perf|revert)(\([^)]*\))?!?: '
BREAKING_RE='^[a-z]+(\([^)]*\))?!: '
is_releasable_subject() {
  [[ "$1" =~ $RELEASABLE_RE ]] || [[ "$1" =~ $BREAKING_RE ]]
}

# A path that can never affect what a service ships: repo/CI metadata only.
# Deliberately tiny (see requirements.md) -- docs/**, README*, and other
# config paths are excluded on purpose so they keep surfacing as drift.
is_metadata_path() {
  case "$1" in
    .github/*) return 0 ;;
    CLAUDE.md) return 0 ;;
    *) return 1 ;;
  esac
}

# stdin: the GitHub compare payload for <tag>...main.
# stdout: "<count>\t<oldest-releasable-commit-date-or-empty>".
unreleased_from_compare() {
  local count=0 oldest=""
  while IFS=$'\t' read -r date subject; do
    [ -z "$subject" ] && continue
    if is_releasable_subject "$subject"; then
      count=$((count + 1))
      if [ -z "$oldest" ] || [ "$(to_epoch "$date")" -lt "$(to_epoch "$oldest")" ]; then
        oldest="$date"
      fi
    fi
  done < <(jq -r '.commits[]? | [.commit.committer.date, (.commit.message | split("\n")[0])] | @tsv')
  printf '%s\t%s\n' "$count" "$oldest"
}

# stdin: the same GitHub compare payload for <tag>...main already used by
# unreleased_from_compare. Success iff the aggregate changed-path set is
# non-empty and every path in it is a metadata path. An empty or absent
# `files` list is treated as NOT metadata-only (fail safe): the compare
# API's file list can be truncated or missing entirely, and defaulting an
# unusable list to "nothing to worry about" would silently suppress a real
# drift signal instead of falling back to today's subject-only behavior.
# The compare API caps `.files` at 300 entries and gives no explicit
# truncation flag, so a list AT the cap is indistinguishable from a longer
# one that was cut off. Reading such a list to the end and concluding
# "metadata-only" would suppress the drift signal for every file past the
# 300th -- a 400-file diff whose first 300 happen to be under .github/ would
# report clean. A list at the cap is therefore treated as unusable, the same
# way an empty or absent one is.
COMPARE_FILES_CAP=300

is_metadata_only_diff() {
  local p seen=0 payload count
  payload=$(cat)
  count=$(jq -r '(.files | length?) // 0' <<<"$payload")
  [ "$count" -ge "$COMPARE_FILES_CAP" ] && return 1
  while IFS= read -r p; do
    [ -z "$p" ] && continue
    seen=1
    is_metadata_path "$p" || return 1
  done < <(jq -r '.files[]?.filename' <<<"$payload")
  [ "$seen" -eq 1 ]
}

# "<path>\t<image-repo>\t<tag>" for every values.yaml under SERVICES_DIR whose
# top-level `image:` block pins a ghcr.io/<org>/<repo> image. Only that
# block is read: `repository:` and `tag:` keys elsewhere in the file (a
# sidecar, a label, an init container) are neither paired with it nor
# reported. The service chart has exactly one `image:` block per values.yaml
# today; a second image would need its own block name here, not a wider
# grep. Preview and non-release pins are kept in the list so the report can
# say why they were skipped.
pinned_images() {
  local f img tag
  for f in "$SERVICES_DIR"/*/*/values.yaml; do
    [ -f "$f" ] || continue
    IFS=$'\t' read -r img tag < <(image_block_fields "$f")
    [ -n "$img" ] || continue
    printf '%s\t%s\t%s\n' "$f" "${img#ghcr.io/$ORG/}" "$tag"
  done
}

# stdin/file: a values.yaml. stdout: "<repository>\t<tag>" from the top-level
# `image:` block only, empty when the file has none or the repository is not
# under ghcr.io/<org>/. Block scope = the lines indented under `image:` up to
# the next top-level key.
image_block_fields() {
  awk -v org="$ORG" '
    /^image:[[:space:]]*$/ { inblock = 1; next }
    inblock && /^[^[:space:]#]/ { inblock = 0 }
    inblock && /^[[:space:]]+repository:/ { repo = $2; gsub(/["'"'"']/, "", repo) }
    inblock && /^[[:space:]]+tag:/ { tag = $2; gsub(/["'"'"']/, "", tag) }
    END {
      if (repo ~ ("^ghcr\\.io/" org "/")) printf "%s\t%s\n", repo, tag
    }
  ' "$1"
}

# "<tag>\t<date>" of the newest release of <repo>: the GitHub release when
# the repo publishes them (release-please does), otherwise the newest
# semver tag with its commit date, for repos that only tag. Fails when the
# repo is unreachable or has no release-shaped tag at all.
latest_release() {
  local repo="$1" rel tags
  if rel=$(gh api "repos/$ORG/$repo/releases/latest" 2>/dev/null); then
    jq -r '[.tag_name, .published_at] | @tsv' <<<"$rel"
    return 0
  fi
  tags=$(gh api --paginate "repos/$ORG/$repo/tags?per_page=100" --jq '.[].name' 2>/dev/null) || return 1
  # Newest version wins, pre-release or not: a repo that only ever cuts
  # pre-releases is "released" at its newest one, and a stable tag sorts
  # above the pre-releases of the same version anyway.
  local t best="" best_v=""
  while read -r t; do
    [ -n "$t" ] && is_release_tag "$t" || continue
    if [ -z "$best" ] || [ "$(printf '%s\n%s\n' "$best_v" "$(strip_v "$t")" | sort -V | tail -1)" != "$best_v" ]; then
      best="$t"; best_v="$(strip_v "$t")"
    fi
  done <<<"$tags"
  [ -n "$best" ] || return 1
  local date
  date=$(gh api "repos/$ORG/$repo/commits/$best" --jq '.commit.committer.date' 2>/dev/null) || return 1
  printf '%s\t%s\n' "$best" "$date"
}

# One line of verdict per pinned image. A values.yaml carrying the comment
# `# release-drift: ignore` (a tenant deliberately held on an older release)
# is listed and skipped. Fields:
#   repo  deployed  released  released_at  unreleased  oldest  rp_run  verdict
check_image() {
  local path="$1" repo="$2" deployed="$3"
  if ! is_release_tag "$deployed"; then
    printf '%s\t%s\t%s\t-\t-\t-\t-\t-\tskip: non-release pin\n' "$path" "$repo" "$deployed"
    return
  fi
  # File-level on purpose: one image block per values.yaml (see
  # image_block_fields), so the marker cannot hide a second image.
  if grep -qE '^\s*#\s*release-drift:\s*ignore' "$path"; then
    printf '%s\t%s\t%s\t-\t-\t-\t-\t-\tskip: release-drift: ignore\n' "$path" "$repo" "$deployed"
    return
  fi
  local released released_at
  if ! IFS=$'\t' read -r released released_at < <(latest_release "$repo"); then
    printf '%s\t%s\t%s\t-\t-\t-\t-\t-\tskip: no release tag under %s/%s\n' "$path" "$repo" "$deployed" "$ORG" "$repo"
    return
  fi

  # A compare that cannot be read is a verdict of its own, never an "ok":
  # defaulting to zero commits would turn a rate limit or a renamed default
  # branch into a silent pass, the exact failure this check exists to end.
  local cmp count oldest
  if ! cmp=$(gh api "repos/$ORG/$repo/compare/$released...main" 2>/dev/null); then
    printf '%s\t%s\t%s\t%s\t%s\t-\t-\t-\tCOMPARE_FAILED_%s...main\n' \
      "$path" "$repo" "$deployed" "$released" "$released_at" "$released"
    return
  fi
  IFS=$'\t' read -r count oldest < <(unreleased_from_compare <<<"$cmp")

  # Last release-please run on main; "n/a" for repos that tag by hand.
  local rp_run
  if ! rp_run=$(gh api "repos/$ORG/$repo/actions/workflows/release-please.yml/runs?branch=main&per_page=1" \
      --jq '.workflow_runs[0].conclusion // "in_progress"' 2>/dev/null); then
    rp_run="n/a"
  fi

  local verdict="" metadata_note="" now
  now=$(now_epoch)
  if [ "$rp_run" = "failure" ]; then
    verdict="RELEASE_PLEASE_FAILED"
  fi
  if [ "$count" -gt 0 ] && [ $((now - $(to_epoch "$oldest"))) -gt $((RELEASE_LAG_HOURS * 3600)) ]; then
    if is_metadata_only_diff <<<"$cmp"; then
      metadata_note="ok: metadata-only changes (${count} commits since ${oldest})"
    else
      verdict="${verdict:+$verdict,}UNRELEASED_${count}_commits_since_${oldest}"
    fi
  fi
  if [ "$(strip_v "$deployed")" != "$(strip_v "$released")" ] \
     && [ $((now - $(to_epoch "$released_at"))) -gt $((DEPLOY_LAG_HOURS * 3600)) ]; then
    verdict="${verdict:+$verdict,}NOT_DEPLOYED_released_${released}_pinned_${deployed}"
  fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$path" "$repo" "$deployed" "$released" "$released_at" "$count" "${oldest:--}" "$rp_run" "${verdict:-${metadata_note:-ok}}"
}

report() {
  local failed=0 line
  {
    echo "| values.yaml | repo | deployed | released | unreleased | release-please | verdict |"
    echo "|---|---|---|---|---|---|---|"
  } | tee -a "${GITHUB_STEP_SUMMARY:-/dev/null}"
  while IFS=$'\t' read -r path repo deployed released released_at count oldest rp verdict; do
    line="| \`${path#$SERVICES_DIR/}\` | $repo | $deployed | $released | $count | $rp | $verdict |"
    echo "$line" | tee -a "${GITHUB_STEP_SUMMARY:-/dev/null}"
    case "$verdict" in ok|ok:*|skip:*) ;; *) failed=1; echo "::error::$repo: $verdict ($path)";; esac
  done < <(pinned_images | while IFS=$'\t' read -r p r t; do check_image "$p" "$r" "$t"; done)
  return $failed
}

self_test() {
  local out
  # Releasable subjects.
  for s in "feat(x): a" "fix: b" "perf(y)!: c" "chore!: d" "revert: e"; do
    is_releasable_subject "$s" || { echo "self-test: '$s' should be releasable"; return 1; }
  done
  for s in "chore(main): release 1.2.3" "docs: x" "test(local): y" "ci: z" "refactor(a): b"; do
    is_releasable_subject "$s" && { echo "self-test: '$s' should not be releasable"; return 1; }
  done
  # Release tags.
  for t in 0.60.0 v1.2.3 2026.7.11-beta.2 0.1.0-r2; do
    is_release_tag "$t" || { echo "self-test: '$t' should be a release tag"; return 1; }
  done
  for t in main-8d2b988 4c7b7d55ec02 latest ""; do
    is_release_tag "$t" && { echo "self-test: '$t' should not be a release tag"; return 1; }
  done
  # Compare payload: two releasable commits, one not; oldest picked by date.
  out=$(unreleased_from_compare <<'JSON'
{"commits":[
 {"commit":{"committer":{"date":"2026-09-04T10:00:00Z"},"message":"test(local): drive init (#501)\n\nbody"}},
 {"commit":{"committer":{"date":"2026-09-03T18:35:00Z"},"message":"feat(agents): issue-481 (#486)"}},
 {"commit":{"committer":{"date":"2026-09-04T02:57:00Z"},"message":"fix(db): revoking (#490)"}}
]}
JSON
)
  [ "$out" = $'2\t2026-09-03T18:35:00Z' ] || { echo "self-test: compare classification got '$out'"; return 1; }
  out=$(unreleased_from_compare <<<'{"commits":[]}')
  [ "$out" = $'0\t' ] || { echo "self-test: empty compare got '$out'"; return 1; }
  # Metadata paths: repo/CI-only paths, deliberately not docs/README/source.
  for p in ".github/workflows/x.yml" "CLAUDE.md"; do
    is_metadata_path "$p" || { echo "self-test: '$p' should be a metadata path"; return 1; }
  done
  for p in "docs/api/index.md" "README.md" "src/app.py"; do
    is_metadata_path "$p" && { echo "self-test: '$p' should not be a metadata path"; return 1; }
  done
  # Aggregate-diff classifier: metadata-only, one runtime file added, and
  # the fail-safe cases (empty/missing files list).
  is_metadata_only_diff <<<'{"files":[{"filename":".github/workflows/claude-review.yml"},{"filename":"CLAUDE.md"}]}' \
    || { echo "self-test: .github/** + CLAUDE.md should be metadata-only"; return 1; }
  is_metadata_only_diff <<<'{"files":[{"filename":".github/workflows/claude-review.yml"},{"filename":"CLAUDE.md"},{"filename":"src/app.py"}]}' \
    && { echo "self-test: adding src/app.py should not be metadata-only"; return 1; }
  is_metadata_only_diff <<<'{"files":[]}' \
    && { echo "self-test: empty files list should not be metadata-only"; return 1; }
  is_metadata_only_diff <<<'{"commits":[]}' \
    && { echo "self-test: missing files key should not be metadata-only"; return 1; }
  # A files list at the API cap is truncation-indistinguishable: even when
  # every entry read IS metadata, the unread remainder is unknown.
  local capped
  capped=$(jq -nc --argjson n "$COMPARE_FILES_CAP" \
    '{files: [range($n) | {filename: ".github/workflows/w\(.).yml"}]}')
  is_metadata_only_diff <<<"$capped" \
    && { echo "self-test: a files list at the $COMPARE_FILES_CAP cap should not be metadata-only"; return 1; }
  local under_cap
  under_cap=$(jq -nc --argjson n "$((COMPARE_FILES_CAP - 1))" \
    '{files: [range($n) | {filename: ".github/workflows/w\(.).yml"}]}')
  is_metadata_only_diff <<<"$under_cap" \
    || { echo "self-test: a metadata-only list below the cap should still be metadata-only"; return 1; }
  # Image block parser: only the top-level image: block, not a sidecar's
  # repository/tag or a tag: key under another mapping.
  local fixture; fixture=$(mktemp)
  cat >"$fixture" <<'YAML'
sidecar:
  image:
    repository: ghcr.io/mctlhq/other
    tag: "9.9.9"
image:
  repository: "ghcr.io/mctlhq/svc"
  # release-drift: ignore
  tag: "1.2.3"
  pullPolicy: IfNotPresent
labels:
  tag: nope
YAML
  out=$(image_block_fields "$fixture"); rm -f "$fixture"
  [ "$out" = $'ghcr.io/mctlhq/svc\t1.2.3' ] || { echo "self-test: image block parse got '$out'"; return 1; }
  # latest_release: gh api --paginate is required to see tags past page 1. A
  # fake gh stub simulates a repo with 105 tags where the newest, 9.9.9,
  # only exists on page 2; without --paginate the tags call truncates at
  # 100 and never sees it, so the best-tag scan would land on 0.0.100.
  local ghstub; ghstub=$(mktemp -d)
  cat >"$ghstub/gh" <<'GHSTUB'
#!/usr/bin/env bash
argstr="$*"
jqexpr=""
prev=""
for a in "$@"; do
  if [ "$prev" = "--jq" ]; then
    jqexpr="$a"
  fi
  prev="$a"
done
case "$argstr" in
  *"releases/latest"*)
    exit 1
    ;;
  *"commits/9.9.9"*)
    json='{"commit":{"committer":{"date":"2026-08-01T00:00:00Z"}}}'
    if [ -n "$jqexpr" ]; then
      printf '%s' "$json" | jq -r "$jqexpr"
    else
      printf '%s' "$json"
    fi
    ;;
  *"tags?per_page=100"*)
    if [[ "$argstr" == *"--paginate"* ]]; then
      for i in $(seq 1 104); do printf '0.0.%d\n' "$i"; done
      echo "9.9.9"
    else
      for i in $(seq 1 100); do printf '0.0.%d\n' "$i"; done
    fi
    ;;
  *)
    exit 1
    ;;
esac
GHSTUB
  chmod +x "$ghstub/gh"
  out=$(PATH="$ghstub:$PATH" latest_release "paginated-fixture") || out="<failed>"
  rm -rf "$ghstub"
  [ "$out" = $'9.9.9\t2026-08-01T00:00:00Z' ] || { echo "self-test: paginated tag lookup got '$out'"; return 1; }
  echo "self-test: ok"
}

case "${1:-}" in
  --self-test) self_test ;;
  "") report ;;
  *) echo "usage: $0 [--self-test]" >&2; exit 2 ;;
esac
