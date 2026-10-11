# syntax=docker/dockerfile:1
#
# Throwaway workload for the smoke-test ClusterWorkflowTemplate. It only has
# to satisfy what base-service and the smoke checks expect: listen on 8080,
# answer 200 on /healthz and /readyz, and ship a shell with `env` so the
# checks can read the pod environment through kubectl exec.
#
# Built by .github/workflows/build-image.yaml with
#   repo=mctlhq/mctl-gitops  dockerfile_path=platform-gitops/images/smoke-app/Dockerfile
# whenever smoke-test onboards or deploys (its defaults point here). The
# previous source, mctlhq/spring-test, no longer exists.

FROM busybox:1.36.1

RUN mkdir -p /www && echo ok > /www/healthz && echo ok > /www/readyz

USER 65534:65534
EXPOSE 8080
CMD ["httpd", "-f", "-v", "-p", "8080", "-h", "/www"]
