# k3s-prod

TODO: Production cluster configuration.

When ready, copy the contents of `k3s-preprod/` and adjust:
- `cluster_name = "mctl-prod"`
- 3 control plane nodes (HA)
- 3+ worker nodes
- Enable automatic OS upgrades
- Restrict firewall rules
- Configure etcd S3 backups
- Update `cluster-bootstrap/` for prod ArgoCD config
