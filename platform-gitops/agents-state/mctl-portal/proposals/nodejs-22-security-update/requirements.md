# Node.js 22 Security Update (v22.22.3)

## Context
Node.js v22.22.3 LTS was released on 2026-05-13 and closes several runtime-level vulnerabilities that affect any Node.js 22 service regardless of application code: a Zlib use-after-free, an HTTP2 FileHandle leak, a URL parser crash via malformed UNC hostnames, and an HTTP keep-alive race condition. OpenSSL is upgraded to 3.5.6 and root certificates are refreshed to NSS 3.121.

mctl-portal runs on Node.js 22 (declared in `engines.node: "22 || 24"`) inside a Docker image. The backend serves authenticated requests and internal API calls; a Zlib use-after-free or HTTP2 memory leak in the runtime is a direct risk to service availability and, in adversarial conditions, potentially exploitable for memory disclosure. Updating the base image tag is the minimal-change path to closing these runtime vulnerabilities.

## User stories
- AS a platform engineer I WANT the mctl-portal Docker base image updated to Node.js v22.22.3 SO THAT known runtime vulnerabilities are eliminated from the running service.
- AS a security team member I WANT the Node.js runtime to be at a patched version SO THAT the service is not vulnerable to Zlib, HTTP2, or URL parser exploits.
- AS an operator I WANT the updated image to be deployed with zero downtime SO THAT portal users experience no service interruption during the upgrade.

## Acceptance criteria (EARS)
- WHEN the Docker image is built THEN THE SYSTEM SHALL use `node:22.22.3` (or `node:22.22.3-alpine` / `node:22.22.3-slim`) as the base image.
- WHEN the updated image is running THEN THE SYSTEM SHALL report Node.js version `v22.22.3` from `node --version` inside the container.
- WHEN the updated image is running THEN THE SYSTEM SHALL include OpenSSL version 3.5.6 or later.
- WHILE the new pod is starting during rollout THEN THE SYSTEM SHALL keep the previous pod running until the new pod passes its readiness probe.
- WHEN the new pod is healthy THEN THE SYSTEM SHALL serve authenticated portal requests without errors.
- IF a container image scan is run against the new image THEN THE SYSTEM SHALL show no Critical or High CVEs in the Node.js runtime layer that were present in the previous base image.
- WHEN `node --version` is executed inside the running container THEN THE SYSTEM SHALL output `v22.22.3`.

## Out of scope
- Upgrading Node.js to v24 (the `engines.node` field already permits v24, but that is a separate proposal requiring broader testing).
- Application-level code changes — this is a base image bump only.
- Changes to npm or yarn versions unless required by the new Node.js runtime.
- Operating system package updates beyond what the official Node.js Docker image provides.
