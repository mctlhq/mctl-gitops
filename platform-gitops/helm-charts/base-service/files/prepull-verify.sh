#!/bin/sh
# PreSync gate of a Recreate rollout (mctlhq/mctl-agents#1007). Under Recreate
# the image pull happens after the old pod stopped, so a slow pull is outage.
# A sync may change the image only when the pre-pull DaemonSet proves the exact
# digest is on every eligible node. Exit 1 fails the Argo CD sync BEFORE the
# Deployment is touched, so the old pod keeps running.
# Anything that cannot be read is a STOP: "could not observe" is never "cached".
#
# The Role and RoleBinding this Job reads with come from the tenant Argo CD app,
# which syncs independently of the app that runs this hook. So the first read
# alone, and only on a Forbidden answer, is retried for up to RBAC_WAIT_SECONDS
# (default 0 = no wait); every other failure, and a Forbidden that outlasts the
# wait, is an immediate STOP. One Role grants every verb below at once, so a
# successful first read means the rest are readable.
#
# A revert or rollback is a deploy like any other: restoring an older image
# stops here unless the revert PR first sets prepull.ref to that older
# repository:tag@digest and the DaemonSet holds it. Reverting only image.tag
# and image.digest is a STOP, and an older tag that was never digest-pinned
# cannot pass at all.
set -u
stop() { echo "prepull-verify: STOP: $*" >&2; exit 1; }

waited=0
# --ignore-not-found makes an absent Deployment a successful, EMPTY read, so
# absence is told apart from every failure by structure, not by error prose.
until deploy=$(kubectl get deployment "$DEPLOYMENT" -n "$NAMESPACE" -o json --ignore-not-found); do
  [ "$waited" -lt "${RBAC_WAIT_SECONDS:-0}" ] || stop "cannot read Deployment $DEPLOYMENT"
  err=$(kubectl get deployment "$DEPLOYMENT" -n "$NAMESPACE" -o name 2>&1 >/dev/null)
  case $err in
    *[Ff]orbidden*) ;;
    *) stop "cannot read Deployment $DEPLOYMENT" ;;
  esac
  echo "prepull-verify: waiting for the tenant RBAC (${waited}s of ${RBAC_WAIT_SECONDS}s)" >&2
  sleep "${RBAC_POLL_SECONDS:-3}"
  waited=$((waited + ${RBAC_POLL_SECONDS:-3}))
done
# A first install (DR, cluster rebuild, recreated Application) has no Deployment
# yet: it is created in the Sync phase, after this hook. With no old pod there is
# nothing to protect and nothing to wait out, so this PASSes (and says so). Only
# the successful empty read of the Deployment gets here: every failed read
# above, and every other object read below, is still a STOP.
if [ -z "$deploy" ]; then
  echo "prepull-verify: PASS: Deployment $DEPLOYMENT does not exist yet (first install), no old pod to protect"
  exit 0
fi
live=$(printf '%s' "$deploy" | jq -er --arg c "$CONTAINER" '.spec.template.spec.containers[] | select(.name == $c) | .image') \
  || stop "Deployment $DEPLOYMENT has no container $CONTAINER"
if [ "$live" = "$TARGET_REF" ]; then
  echo "prepull-verify: PASS: image unchanged ($TARGET_REF), nothing to pull"
  exit 0
fi

digest=${TARGET_REF##*@}
printf '%s' "$digest" | grep -Eq '^sha256:[0-9a-f]{64}$' || stop "target $TARGET_REF is not pinned to a digest (a revert to a tag-only reference cannot pass)"

ds=$(kubectl get daemonset "$DAEMONSET" -n "$NAMESPACE" -o json) || stop "cannot read DaemonSet $DAEMONSET"
printf '%s' "$ds" | jq -e --arg ref "$TARGET_REF" '
  .metadata.generation == .status.observedGeneration
  and .status.desiredNumberScheduled >= 1
  and .status.numberReady == .status.desiredNumberScheduled
  and .status.updatedNumberScheduled == .status.desiredNumberScheduled
  and ([.spec.template.spec.containers[].image] == [$ref])
' >/dev/null || stop "DaemonSet $DAEMONSET does not cover every eligible node with $TARGET_REF (a revert must first set prepull.ref to the image it restores)"
desired=$(printf '%s' "$ds" | jq -er '.status.desiredNumberScheduled') || stop "unreadable desiredNumberScheduled"

pods=$(kubectl get pods -n "$NAMESPACE" -l "$POD_SELECTOR" -o json) || stop "cannot list pre-pull pods"
printf '%s' "$pods" | jq -e --arg ref "$TARGET_REF" --arg digest "$digest" --argjson desired "$desired" '
  [.items[] | select(.metadata.deletionTimestamp == null)] as $p
  | ($p | length) == $desired
  and ([$p[].spec.nodeName] | unique | length) == $desired
  and all($p[];
    .status.phase == "Running"
    and (.status.containerStatuses | length) == 1
    and .status.containerStatuses[0].ready == true
    and .spec.containers[0].image == $ref
    and (.status.containerStatuses[0].imageID | endswith("@" + $digest)))
' >/dev/null || stop "not every pre-pull pod runs digest $digest"

echo "prepull-verify: PASS: $digest on $desired node(s)"
