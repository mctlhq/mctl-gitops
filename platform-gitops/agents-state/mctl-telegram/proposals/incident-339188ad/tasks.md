# Tasks: incident-339188ad

1. [ ] Locate the Telegram client idle-eviction timeout behind the
   `"idle telegram client, closing"` log line (~600s / 10 minutes observed)
   in the mctl-telegram base-service, and determine whether it is an
   env-configurable value or a hardcoded constant in Go source.
2. [ ] If env-configurable, raise the value (e.g. 600s -> 1800s) in the
   labs mctl-telegram Helm values/env config in platform-gitops. If
   hardcoded, bump the constant in the mctl-telegram source and cut a new
   image tag.
3. [ ] Verify the change looks correct: confirm the new idle timeout takes
   effect and that no other logic (metrics bucket boundaries, tests,
   documentation) assumes the old ~600s value.
4. [ ] If a code change and new image were required, bump the image tag in
   the labs mctl-telegram deployment so the fix ships.
