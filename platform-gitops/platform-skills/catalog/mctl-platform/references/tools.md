# MCP Tool Reference

Complete reference for all `mctl_*` tools.

## Identity & Workspace

| Tool | Parameters | Description |
|------|-----------|-------------|
| `mctl_whoami` | — | User ID, teams, admin status |
| `mctl_create_tenant` | `tenant_name` | Create workspace (1 per user) |
| `mctl_get_tenant` | `name` | Workspace details, members, quotas |
| `mctl_delete_tenant` | `tenant_name` | ⚠️ Delete workspace permanently |

## Service Lifecycle

| Tool | Parameters | Description |
|------|-----------|-------------|
| `mctl_deploy_service` | `action, team_name, component_name, [dockerfile_repo], [git_tag], [service_template], [image_tag], [telegram_owner_id], [telegram_bot_token]` | Onboard / deploy / update-config. `dockerfile_repo` not required when `service_template != "default"` |
| `mctl_get_service_status` | `team_name, service_name` | Sync state + health from ArgoCD |
| `mctl_get_service_config` | `team_name, service_name` | Full Helm values from GitOps |
| `mctl_get_service_logs` | `team_name, service_name, [lines], [since]` | Logs from Loki |
| `mctl_rollback_service` | `team_name, component_name, target_tag` | Revert to a previous image tag |
| `mctl_scale_service` | `team_name, component_name, autoscaling_enabled` | Toggle HPA |
| `mctl_retire_service` | `team_name, component_name` | ⚠️ Delete service permanently |

## Repository Management

| Tool | Parameters | Description |
|------|-----------|-------------|
| `mctl_list_repos` | `team_name` | Available repos for the team |
| `mctl_sync_repos` | `team_name` | Discover new repos from GitHub App |
| `mctl_grant_repo_access` | `team_name, repo` | Get GitHub App install URL |

## Preview Environments

| Tool | Parameters | Description |
|------|-----------|-------------|
| `mctl_create_preview` | `team_name, component_name, image_tag` | Ephemeral env (24h TTL) |
| `mctl_list_previews` | `team_name` | Active previews |
| `mctl_delete_preview` | `team_name, component_name, preview_id` | Remove preview |

## Custom Domains

| Tool | Parameters | Description |
|------|-----------|-------------|
| `mctl_add_custom_domain` | `team_name, service_name, domain` | Add custom domain |
| `mctl_verify_domain` | `team_name, service_name` | Check CNAME configuration |
| `mctl_list_domains` | `team_name` | All domains + status |
| `mctl_remove_custom_domain` | `team_name, service_name, domain` | Remove domain |

## Database

| Tool | Parameters | Description |
|------|-----------|-------------|
| `mctl_provision_database` | `team_name, app_name` | PostgreSQL on shared CNPG cluster |

Credentials auto-injected as env vars: `DATABASE_URL`, `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`.

## Monitoring & Audit

| Tool | Parameters | Description |
|------|-----------|-------------|
| `mctl_get_resource_usage` | `team_name` | CPU, memory, pods vs quotas |
| `mctl_get_workflow_status` | `workflow_name` | Argo Workflow progress + logs |
| `mctl_list_workflows` | `team_name` | Recent workflow runs |
| `mctl_list_recent_operations` | — | Audit log (last 50 operations) |
| `mctl_list_operations` | — | All available operation types |
| `mctl_get_operation` | `name` | Operation parameter schema |
