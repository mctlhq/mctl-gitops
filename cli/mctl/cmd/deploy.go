package cmd

import (
	"fmt"
	"strings"
	"time"

	"github.com/mctlhq/mctl-gitops/cli/mctl/internal/api"
	"github.com/mctlhq/mctl-gitops/cli/mctl/internal/auth"
	"github.com/mctlhq/mctl-gitops/cli/mctl/internal/vault"
	"github.com/spf13/cobra"
)

var deployCmd = &cobra.Command{
	Use:   "deploy",
	Short: "Deploy a new service to the platform",
	Long: `Deploy a new service via the mctl API. Supports both repo-based deploys and template-based onboard flows such as openclaw.`,
	Example: `  # Deploy a web service with ingress
  mctl deploy -t my-team -n my-api -r mctlhq/my-api -g v1.0.0 --host my-api.preview.mctl.ai

  # Deploy a background worker (no host = worker)
  mctl deploy -t my-team -n my-worker -r mctlhq/my-worker -g v1.0.0

  # Deploy OpenClaw from the built-in service template
  mctl deploy -t my-team -n openclaw --service-template openclaw \
    --telegram-owner-id 123456789 --telegram-bot-token 123:abc

  # Deploy with env vars and secrets
  mctl deploy -t my-team -n my-api -r mctlhq/my-api -g v1.0.0 \
    --host my-api.preview.mctl.ai \
    --env LOG_LEVEL=info --env PORT=3000 \
    --secret API_KEY=sk-xxx --secret DB_PASS=hunter2`,
	RunE: runDeploy,
}

var (
	deployTeam       string
	deployName       string
	deployRepo       string
	deployTag        string
	deployPort       string
	deployHost       string
	deployDockerfile string
	deployTemplate   string
	deployImageTag   string
	deployModel      string
	deployEnv        []string
	deploySecret     []string
	deployWait       bool
	deployPat        string
	deployTelegramOwnerID string
	deployTelegramBotToken string
)

func init() {
	deployCmd.Flags().StringVarP(&deployTeam, "team", "t", "", "Team name (required)")
	deployCmd.Flags().StringVarP(&deployName, "name", "n", "", "Service name (required)")
	deployCmd.Flags().StringVarP(&deployRepo, "repo", "r", "", "Dockerfile repo — owner/repo (required unless --service-template is used)")
	deployCmd.Flags().StringVarP(&deployTag, "tag", "g", "", "Git tag to build (required unless a template-only deploy is used)")
	deployCmd.Flags().StringVarP(&deployPort, "port", "p", "8080", "Service port")
	deployCmd.Flags().StringVar(&deployHost, "host", "", "Ingress host (omit for worker)")
	deployCmd.Flags().StringVar(&deployDockerfile, "dockerfile", "Dockerfile", "Path to Dockerfile")
	deployCmd.Flags().StringVar(&deployTemplate, "service-template", "default", "Service template to use, e.g. default or openclaw")
	deployCmd.Flags().StringVar(&deployImageTag, "image-tag", "", "Pre-built image tag override (skip repo build)")
	deployCmd.Flags().StringVar(&deployModel, "default-model", "openai-codex/gpt-5.4", "Default model for templates that support it")
	deployCmd.Flags().StringVar(&deployTelegramOwnerID, "telegram-owner-id", "", "Telegram user ID to auto-approve for openclaw")
	deployCmd.Flags().StringVar(&deployTelegramBotToken, "telegram-bot-token", "", "Telegram bot token to store for openclaw")
	deployCmd.Flags().StringSliceVar(&deployEnv, "env", nil, "Environment variable KEY=VALUE (repeatable)")
	deployCmd.Flags().StringSliceVar(&deploySecret, "secret", nil, "Secret KEY=VALUE (repeatable)")
	deployCmd.Flags().BoolVarP(&deployWait, "wait", "w", false, "Wait for workflow to complete")
	deployCmd.Flags().StringVar(&deployPat, "pat", "", "Repository PAT for private repos (saved to Vault)")

	deployCmd.MarkFlagRequired("team")
	deployCmd.MarkFlagRequired("name")
}

func runDeploy(cmd *cobra.Command, args []string) error {
	if deployTemplate == "" {
		deployTemplate = "default"
	}
	if deployTemplate == "default" && deployRepo == "" && deployImageTag == "" {
		return fmt.Errorf("--repo is required unless --service-template is set to a non-default template or --image-tag is provided")
	}
	if deployTag == "" && deployImageTag == "" && deployTemplate == "default" {
		return fmt.Errorf("--tag is required unless --image-tag is provided or a template-only deploy is used")
	}
	if deployTemplate != "default" && deployHost == "" {
		deployHost = "auto"
	}

	token, err := auth.GetToken()
	if err != nil {
		return err
	}

	// Save PAT to Vault if provided
	if deployPat != "" {
		fmt.Printf("🔐 Saving repo PAT to Vault for %s/%s...\n", deployTeam, deployName)
		vc, err := vault.NewClientFromEnv()
		if err != nil {
			return fmt.Errorf("cannot save PAT: %w\n  Set VAULT_ADDR and VAULT_TOKEN environment variables", err)
		}
		if err := vc.SaveRepoPAT(deployTeam, deployName, deployPat); err != nil {
			return fmt.Errorf("failed to save PAT to Vault: %w", err)
		}
		fmt.Println("   ✅ PAT saved to Vault")
	}

	serviceType := "base-service"
	if deployHost == "" && deployTemplate == "default" {
		serviceType = "worker-service"
	}

	inputs := map[string]string{
		"action":            "onboard",
		"team_name":         deployTeam,
		"component_name":    deployName,
		"component_type":    serviceType,
		"dockerfile_repo": deployRepo,
		"dockerfile_path": deployDockerfile,
		"git_tag":           deployTag,
		"image_tag":         deployImageTag,
		"port":              deployPort,
		"host":              deployHost,
		"env_vars":          strings.Join(deployEnv, "\n"),
		"secret_env_vars":   strings.Join(deploySecret, "\n"),
		"service_template":  deployTemplate,
		"default_model":     deployModel,
		"telegram_owner_id": deployTelegramOwnerID,
		"telegram_bot_token": deployTelegramBotToken,
	}

	client := api.NewClient(token)

	fmt.Printf("🚀 Deploying %s/%s (type: %s)...\n", deployTeam, deployName, serviceType)
	result, err := client.ExecuteOperation("deploy-service", inputs)
	if err != nil {
		return fmt.Errorf("deploy failed: %w", err)
	}
	fmt.Println("✅ Workflow submitted:", result.WorkflowName)

	if deployWait {
		ws, err := client.PollWorkflow(result.WorkflowName, 10*time.Minute)
		if err != nil {
			return err
		}
		if ws.Phase == "Succeeded" {
			fmt.Printf("✅ Deploy completed successfully!\n")
		} else {
			fmt.Printf("❌ Deploy %s: %s\n", ws.Phase, ws.Message)
			return fmt.Errorf("workflow %s", ws.Phase)
		}
	}

	return nil
}
