# Upgrade Node.js Runtime to v22.22.2 (CVE-2026-21710 + 7 more)

## Context
The mctl-portal backend currently runs on Node.js 22 (declared in `engines.node: "22 || 24"`). On 2026-03-24, the Node.js project released v22.22.2 as a security-fix LTS release addressing eight CVEs. The most severe is CVE-2026-21710 (High), a denial-of-service vulnerability triggered by sending an HTTP request with `__proto__` as a header name, which pollutes `Object.prototype` via `req.headersDistinct` and can crash or hang the backend process. CVE-2026-21711 (Medium) allows a Unix Domain Socket server to bind and listen without the required `--allow-net` permission when the Node.js permission model is active.

Because mctl-portal's Backstage backend exposes an HTTP server directly handling incoming requests (auth, catalog, scaffolder, proxy), CVE-2026-21710 represents a direct availability threat. Upgrading the base image and runtime pin from whatever patch release is currently in use to v22.22.2 is a low-effort, high-value security fix that stays within the same major version, minimising regression risk.

## User stories
- AS a platform engineer I WANT the portal backend to run on Node.js v22.22.2 SO THAT the service is not vulnerable to HTTP-level denial-of-service via prototype pollution.
- AS a security officer I WANT all eight CVEs addressed in the v22.22.2 release to be resolved in our runtime SO THAT the portal meets the platform's patching SLA for High-severity findings.
- AS a developer I WANT the Node.js upgrade to be transparent SO THAT no application code changes are required and CI pipelines continue to pass.

## Acceptance criteria (EARS)
- WHEN the mctl-portal Docker image is built THE SYSTEM SHALL use a Node.js base image pinned to v22.22.2 or higher within the v22 LTS line.
- WHEN a runtime version check is performed inside the deployed container THE SYSTEM SHALL report `node --version` as `v22.22.2` or higher.
- WHILE the portal backend is serving HTTP requests THE SYSTEM SHALL not be susceptible to CVE-2026-21710 (prototype pollution via `__proto__` header name in `req.headersDistinct`).
- IF a request is received with `__proto__` as an HTTP header name THE SYSTEM SHALL handle it safely without polluting `Object.prototype` or degrading process availability.
- WHEN the new image is deployed to the `admins` tenant THE SYSTEM SHALL pass all backend health checks within 60 seconds of pod startup.
- WHEN `engines.node` is evaluated during `yarn install` THE SYSTEM SHALL accept only Node.js versions 22.22.2 or higher (within the v22/v24 envelope already declared).

## Out of scope
- Upgrading from Node.js 22 to Node.js 24 (a separate major-version migration decision).
- Changes to any Backstage application code or plugin configuration.
- Patching individual npm packages that may have their own prototype-pollution issues (separate proposals as needed).
- Changes to the permission model configuration (`--allow-net` or similar flags) beyond what is required for the runtime upgrade.
