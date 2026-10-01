# syntax=docker/dockerfile:1
#
# MinIO client (`mc`) built from the last community release of
# github.com/minio/mc (AGPL-3.0). MinIO archived the community repository and
# made quay.io/minio/mc and docker.io/minio/mc private (anonymous pulls answer
# 401), so the platform builds its own copy (mctlhq/mctl-gitops#1485).
#
# Built by .github/workflows/build-image.yaml with
#   repo=mctlhq/mctl-gitops  dockerfile_path=platform-gitops/images/mc/Dockerfile
#   image_name=ghcr.io/mctlhq/mc  image_tag=<MC_RELEASE>
#
# The final image keeps what the claude-remote scripts rely on: a POSIX `sh`,
# `head`, CA certificates and `mc` on PATH, running as root like the previous
# image. Upstream receives no more patches; the pinned source is the last
# community tag and is built with a current Go toolchain.

ARG MC_RELEASE=RELEASE.2025-08-13T08-35-41Z
# Commit the MC_RELEASE tag points to; checked after the clone.
ARG MC_COMMIT=7394ce0dd2a80935aded936b09fa12cbb3cb8096

FROM golang:1.25-alpine@sha256:1ae0735f00daffa3aaf1363a5184c0d2dc55c78e3db4ec70241cdac97bf84b59 AS build
ARG MC_RELEASE
ARG MC_COMMIT
ENV CGO_ENABLED=0 GOTOOLCHAIN=local GOFLAGS=-trimpath
RUN apk add --no-cache git
WORKDIR /src
RUN git clone --depth 1 --branch "${MC_RELEASE}" https://github.com/minio/mc.git . \
 && test "$(git rev-parse HEAD)" = "${MC_COMMIT}"
RUN go build -tags kqueue -ldflags "$(go run buildscripts/gen-ldflags.go)" -o /out/mc . \
 && /out/mc --version

FROM alpine:3.22@sha256:5291449c3df73caf6ed85e649dec1b9e818b39a5d8c871e97afc13e9cd5e8fa8
ARG MC_RELEASE
ARG MC_COMMIT
LABEL org.opencontainers.image.title="mc" \
      org.opencontainers.image.description="MinIO client built from the last community release" \
      org.opencontainers.image.source="https://github.com/mctlhq/mctl-gitops/tree/main/platform-gitops/images/mc" \
      org.opencontainers.image.url="https://github.com/minio/mc" \
      org.opencontainers.image.version="${MC_RELEASE}" \
      org.opencontainers.image.revision="${MC_COMMIT}" \
      org.opencontainers.image.licenses="AGPL-3.0-only"
RUN apk add --no-cache ca-certificates
COPY --from=build /out/mc /usr/bin/mc
COPY --from=build /src/LICENSE /licenses/LICENSE
COPY --from=build /src/CREDITS /licenses/CREDITS
ENTRYPOINT ["mc"]
