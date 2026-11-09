# Web asset integrity contract: immutable CSS, SRI/CORS, provenance and rollback (docs-only)

## Context

Epic mctlhq/.github#330 (`STANDARDIZE_CONTRACTS_KEEP_RUNTIMES`) lists `web-asset-integrity-contract`
as a P2 work item that depends on `web-contract-evidence`. That evidence item (issue #207, PR #208)
is merged as `docs/evidence/web-contract-evidence.md`. The evidence shows that `ui.mctl.ai` serves
`/<version>/{mctl,global,prose,site}.css` with `Cache-Control: public, max-age=31536000, immutable`
and `Access-Control-Allow-Origin: *`. For `0.20.2`, the bodies of all four sheets match the
committed `apps/storybook/public/0.20.2/*.css` by SHA-256. The floating sheets are served at the
edge with `max-age=14400`, while `nginx.conf` declares `3600`. The cause of that difference is
unknown. Several things are still unobserved: what each consumer pins in its source, which source
commit each deployed image came from, edge cache HIT behaviour, and how a real browser handles SRI
and CORS.

This issue asks for one docs-only contract, `docs/contracts/web-asset-integrity.md`. The contract
states how an immutable design-system CSS release is identified, verified, consumed and rolled
back on the six MCTL sites. It changes no runtime, config, CI, CSP, package, version pin or
consumer repository. Enforcement is deferred to the separately approved
`web-contract-preview-assurance` phase.

## User stories

- AS a mctl-design maintainer I WANT a written release-manifest specification for each exact
  version SO THAT "immutable" can be checked against bytes, not only against nginx headers.
- AS a consumer-site owner (mctl-web, docs, telegram, academy, alice, seerrsense) I WANT two
  named, valid delivery modes (exact-version CDN or locally vendored CSS) SO THAT I can pick one
  per route class without relaxing my CSP.
- AS a security reviewer I WANT each SRI/CORS/provenance claim marked as specified, observed on
  `0.20.2`, `unknown (not observed)` or `not-run` SO THAT a missing proof is never read as a pass.
- AS an on-call operator I WANT a documented no-downtime rollback to a previously verified exact
  version, plus fail-safe behaviour on CDN outage or integrity mismatch, SO THAT an incident never
  calls for a CSP bypass.
- AS the epic owner I WANT existing owner tickets referenced instead of duplicated SO THAT this item
  stays a contract and not a second implementation track.

## Acceptance criteria (EARS)

- WHEN the contract is implemented THE SYSTEM SHALL add exactly one new file,
  `docs/contracts/web-asset-integrity.md`, and modify no other file in the repository.
- THE SYSTEM SHALL specify a release manifest for each exact version `X.Y.Z(-prerelease)`. Each
  manifest records: the design version; the canonical 40-hex source commit SHA; build or
  attestation provenance; and, for each asset, the npm path (`@mctlhq/css/<export>` and, where
  applicable, `@mctlhq/tokens`), the CDN URL `https://ui.mctl.ai/<version>/<file>`, size in bytes,
  media type, SHA-256 (hex), and optionally an SRI `sha384-<base64>`.
- THE SYSTEM SHALL present the manifest as an illustrative, non-executable example in a fenced
  block, labelled as an example and not as a published artifact.
- WHEN the example manifest uses `0.20.2` values THE SYSTEM SHALL mark each field as one of:
  `observed` (live HTTP evidence plus a `[CODE]` match), `[CODE]`-only (computed from committed
  bytes and not verified at the edge or in a browser), or `unknown (not observed)` with a reason.
  This rule covers the canonical source SHA for `0.20.2`, which is unknown in this run.
- THE SYSTEM SHALL keep specified requirements separate from evidence proven on `0.20.2`, in
  separate columns or sections.
- THE SYSTEM SHALL define two valid delivery modes:
  (a) Exact-version CDN. A public page loads `https://ui.mctl.ai/<exact semver>/<file>`. It may add
  `integrity` with `crossorigin="anonymous"` only after real CORS, bytes and rollback verification.
  (b) Locally vendored CSS. A deterministic sync puts the CSS into the consumer's own origin, and a
  `--check` style CI step compares it against the manifest. This mode is required for routes that
  use `style-src 'self'` or are sensitive (auth, consent, OAuth).
- THE SYSTEM SHALL state that a successful `curl` does not prove browser SRI or CORS behaviour.
- THE SYSTEM SHALL contain a supply matrix covering route classes on the six sites: mctl.ai, docs,
  tg public, tg lite/auth, academy, alice, seerrsense public, seerrsense consent. For each route
  class it records the source pin, delivery mode, observed `style-src`, integrity status and owner.
  Every unobserved value is `unknown (not observed)` or `not-run`.
- WHILE a route has `style-src 'self'` (for example alice.mctl.ai) or a strict `script-src` THE
  SYSTEM SHALL require locally vendored delivery, and SHALL NOT propose adding `https://ui.mctl.ai`
  or any other relaxation to that CSP.
- THE SYSTEM SHALL specify a release and consumer verification chain: source pin, then package
  lock or URL, then manifest, then build artifact, then OCI image digest, then GitOps desired
  state, then ArgoCD observed state, then a safe anonymous HTTP response. Each link is classified
  as known, `unknown (not observed)` or `not-run`.
- IF a field would need the full docs.mctl.ai CSP header (including its 37 `'sha256-...'` script
  hashes) THEN THE SYSTEM SHALL record it as `unavailable / not-run` and SHALL NOT invent hashes.
- THE SYSTEM SHALL state that sensitive routes (auth, consent, OAuth callback, error, redirect) are
  verified only through source, dev/test fixtures or isolated preview, never by production probes,
  credentials or callback requests.
- THE SYSTEM SHALL specify caching semantics:
  - Versioned URLs are `immutable` and a published version directory is never mutated, moved or
    deleted. This is the rule `scripts/check-token-version-bump.mjs` already enforces.
  - Floating sheets are for previews and internal tools only.
  - The difference between origin `3600` and edge `14400` is recorded as unexplained, with a
    separate follow-up owner, and no config fix is proposed.
- THE SYSTEM SHALL define a no-downtime rollback: repoint the consumer pin to a previously
  verified exact version that is still served (see `apps/storybook/public/<version>/`). Rollback
  never edits or deletes the faulty version's bytes in place.
- IF a CDN request fails or an integrity check does not match THEN THE SYSTEM SHALL require the
  page to fail safe: the stylesheet is not applied or the local copy is used. It SHALL forbid CSP
  widening, removing `integrity`, or switching to the floating URL as a remedy.
- THE SYSTEM SHALL set migration gates: SHA-256 content verification is mandatory, and
  SHA-384/SRI is optional. Any enforcement waits until the separately approved
  `web-contract-preview-assurance` phase has verified ACAO, `crossorigin`, cache and real browser
  outcomes.
- THE SYSTEM SHALL list the existing owners (design#34, design#78, telegram#599, academy#210,
  gitops#500) and SHALL NOT create or duplicate implementation work for them.
- WHEN the new file is checked THE SYSTEM SHALL pass `pnpm format:check`, and
  `pnpm check:token-version` SHALL be unaffected (no path under `packages/{tokens,css}/{src,scripts}`
  and no `apps/storybook/public/<version>/` directory changes).

## Out of scope

- Adding `integrity`/`crossorigin` attributes, SRI generation scripts, or a real manifest file or
  generator in this repo.
- CSS copy or sync tooling and `--check` CI steps, in mctl-design or in any consumer.
- Any change to `nginx.conf`, `security-headers.conf`, `Dockerfile`, workflows, `package.json`
  versions, the `README.md` examples, or `apps/storybook/public/`.
- Cloudflare rules, edge TTL configuration, CDN purge, or GitOps values changes.
- Editing any of the six consumer repositories or their version pins (for example academy's
  `^0.20.2`).
- Live auth, consent or OAuth probing, and production deployment.
- Explaining or fixing the `3600` vs `14400` floating TTL difference.

## Open questions

- Which commit produced the `0.20.2` directory? The investigation clone is shallow (one commit,
  `7340576f6dccbf5da47049d64a5bef216277bb7a`, no tags), so the commit that first wrote
  `apps/storybook/public/0.20.2/` and the matching `0.20.2` git tag were not observed. The contract
  records this as `unknown (not observed)`. The implementer may fill it in only if they read it
  from full history or tags, and must cite the command used.
- Is a signed attestation (for example GitHub artifact attestation or cosign on the GHCR image) a
  requirement or a recommendation? Neither `publish.yml` nor `deploy.yml` produces one today. The
  proposal specifies it as a SHOULD for a future phase.
- The epic routes the floating TTL follow-up to an owner. The evidence report points at gitops#500
  but did not re-read its scope. The contract names it as the candidate owner and leaves the
  routing decision to the epic owner.
- Are the route classes "telegram lite auth" and "SeerrSense consent" the right split? The issue
  names them, but their actual paths are `not-run` because consumer source was not read. The
  matrix keeps them as abstract route classes, with no URLs.
