# Tasks: incident-264ce1c0

1. [ ] Locate the labs tenant's mctl-telegram preview overlay in mctl-gitops
       (the config backing `labs-mctl-telegram-preview-base-service`) and
       identify which Vault path/secret it uses for OAuth/JWT token
       signature validation.
2. [ ] Compare that secret reference against the one the OAuth authorization
       server uses to sign tokens for the `labs-mctl-telegram` host. If it
       differs or is stale, update the preview overlay's secret reference to
       match the current signing secret.
3. [ ] If the preview overlay pins an image tag or config version older than
       production's, confirm whether that also needs bumping alongside the
       secret fix so the two stay consistent.
4. [ ] After the change lands, verify `labs-mctl-telegram-preview-base-service`
       logs no longer show `auth failed err="invalid JWT signature"`, and
       confirm the `MctlTelegramToolAvailabilitySlowBurn` alert clears.
