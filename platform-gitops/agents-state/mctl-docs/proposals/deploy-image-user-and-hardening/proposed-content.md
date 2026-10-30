# Proposed content: deploy-image-user-and-hardening

> **Apply to:** `mctl-docs/docs/guides/services.md` (UPDATE: append section) and `docs/reference/troubleshooting.md` (UPDATE: append entry)
> **Source:** mctl-gitops@187a366, c8448e0, 2db594d, 23b9f10

---

## Section to append to `docs/guides/services.md`

```md
## Container security

Every service deployed with the `base-service` chart runs with these defaults:

- seccomp profile `RuntimeDefault`
- privilege escalation disabled
- all Linux capabilities dropped

### Running as non-root

The chart can additionally enforce `runAsNonRoot: true` and a read-only root
filesystem. Kubernetes can only verify `runAsNonRoot` when the image declares a
**numeric** user, so use:

\`\`\`dockerfile
USER 1000:1000
\`\`\`

`USER app` (a name) or no `USER` (root) is rejected by the kubelet.

When the root filesystem is read-only, list directories the app must write to in
`writablePaths`; each becomes an `emptyDir` mount.

\`\`\`yaml
containerSecurityContext:
  runAsNonRoot: true
  readOnlyRootFilesystem: true
writablePaths:
  - /tmp
  - /var/cache/nginx
\`\`\`

A path already mounted through `extraVolumeMounts` is not mounted twice.
<TODO: confirm with author of c8448e0 how tenants set these values>

### Image-user check

During `deploy` and `onboard`, the deploy workflow runs a `check-image-user` step
after the image is built and before anything is committed. If `runAsNonRoot` applies
and the image user is root or a name, the deploy **fails here** rather than leaving
a pod in `CreateContainerConfigError`. Without `runAsNonRoot` the check only warns.
`update-config` does not change the image and skips the check.
```

## Entry to append to `docs/reference/troubleshooting.md`

```md
### Deploy fails at `check-image-user` / pod in `CreateContainerConfigError`

The image's `USER` is root or a non-numeric name while the service requires
`runAsNonRoot`. Set a numeric user in the Dockerfile (`USER 1000:1000`), rebuild and
redeploy. See [Container security](/guides/services#container-security).
```

---
