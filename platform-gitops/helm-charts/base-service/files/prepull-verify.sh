#!/bin/sh
# PreSync gate of a Recreate rollout (mctlhq/mctl-agents#1007). Under Recreate
# the image pull happens after the old pod stopped, so a slow pull is outage.
# A sync may change the image only when the pre-pull DaemonSet proves the exact
# digest is on every eligible node. Exit 1 fails the Argo CD sync BEFORE the
# Deployment is touched, so the old pod keeps running.
# Anything that cannot be read is a STOP: "could not observe" is never "cached".
set -u
stop() { echo "prepull-verify: STOP: $*" >&2; exit 1; }

deploy=$(kubectl get deployment "$DEPLOYMENT" -n "$NAMESPACE" -o json) || stop "cannot read Deployment $DEPLOYMENT"
live=$(printf '%s' "$deploy" | jq -er --arg c "$CONTAINER" '.spec.template.spec.containers[] | select(.name == $c) | .image') \
  || stop "Deployment $DEPLOYMENT has no container $CONTAINER"
if [ "$live" = "$TARGET_REF" ]; then
  echo "prepull-verify: PASS: image unchanged ($TARGET_REF), nothing to pull"
  exit 0
fi

digest=${TARGET_REF##*@}
printf '%s' "$digest" | grep -Eq '^sha256:[0-9a-f]{64}$' || stop "target $TARGET_REF is not pinned to a digest"

ds=$(kubectl get daemonset "$DAEMONSET" -n "$NAMESPACE" -o json) || stop "cannot read DaemonSet $DAEMONSET"
printf '%s' "$ds" | jq -e --arg ref "$TARGET_REF" '
  .metadata.generation == .status.observedGeneration
  and .status.desiredNumberScheduled >= 1
  and .status.numberReady == .status.desiredNumberScheduled
  and .status.updatedNumberScheduled == .status.desiredNumberScheduled
  and ([.spec.template.spec.containers[].image] == [$ref])
' >/dev/null || stop "DaemonSet $DAEMONSET does not cover every eligible node with $TARGET_REF"
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
