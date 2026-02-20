package cmd

import (
	"fmt"
	"strings"
	"time"

	"github.com/dmitriimashkov/mctl.me/cli/mctl/internal/auth"
	gh "github.com/dmitriimashkov/mctl.me/cli/mctl/internal/github"
	"github.com/dmitriimashkov/mctl.me/cli/mctl/internal/vault"
	"github.com/spf13/cobra"
)

var deployCmd = &cobra.Command{
	Use:   "deploy",
	Short: "Deploy a new service to the platform",
	Long: `Deploy a new service by dispatching the service.yml workflow.
Builds a Docker image from the specified repo and creates the GitOps configuration.`,
	Example: `  # Deploy a web service with ingress
  mctl deploy -t my-team -n my-api -r dmitriimashkov/my-api -g v1.0.0 --host my-api.preview.mctl.me

  # Deploy a background worker (no host = worker)
  mctl deploy -t my-team -n my-worker -r dmitriimashkov/my-worker -g v1.0.0

  # Deploy with env vars and secrets
  mctl deploy -t my-team -n my-api -r dmitriimashkov/my-api -g v1.0.0 \
    --host my-api.preview.mctl.me \
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
	deployEnv        []string
	deploySecret     []string
	deployWait       bool
	deployPat        string
)

func init() {
	deployCmd.Flags().StringVarP(&deployTeam, "team", "t", "", "Team name (required)")
	deployCmd.Flags().StringVarP(&deployName, "name", "n", "", "Service name (required)")
	deployCmd.Flags().StringVarP(&deployRepo, "repo", "r", "", "Dockerfile repo — owner/repo (required)")
	deployCmd.Flags().StringVarP(&deployTag, "tag", "g", "", "Git tag to build (required)")
	deployCmd.Flags().StringVarP(&deployPort, "port", "p", "8080", "Service port")
	deployCmd.Flags().StringVar(&deployHost, "host", "", "Ingress host (omit for worker)")
	deployCmd.Flags().StringVar(&deployDockerfile, "dockerfile", "Dockerfile", "Path to Dockerfile")
	deployCmd.Flags().StringSliceVar(&deployEnv, "env", nil, "Environment variable KEY=VALUE (repeatable)")
	deployCmd.Flags().StringSliceVar(&deploySecret, "secret", nil, "Secret KEY=VALUE (repeatable)")
	deployCmd.Flags().BoolVarP(&deployWait, "wait", "w", false, "Wait for workflow to complete")
	deployCmd.Flags().StringVar(&deployPat, "pat", "", "Repository PAT for private repos (saved to Vault)")

	deployCmd.MarkFlagRequired("team")
	deployCmd.MarkFlagRequired("name")
	deployCmd.MarkFlagRequired("repo")
	deployCmd.MarkFlagRequired("tag")
}

func runDeploy(cmd *cobra.Command, args []string) error {
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
	if deployHost == "" {
		serviceType = "worker-service"
	}

	inputs := map[string]string{
		"action":          "onboard",
		"team_name":       deployTeam,
		"component_name":    deployName,
		"component_type":    serviceType,
		"dockerfile_repo": deployRepo,
		"dockerfile_path": deployDockerfile,
		"git_tag":         deployTag,
		"port":            deployPort,
		"host":            deployHost,
		"env_vars":        strings.Join(deployEnv, "\n"),
		"secret_env_vars": strings.Join(deploySecret, "\n"),
	}

	client := gh.NewClient(token)
	dispatchTime := time.Now().Add(-5 * time.Second)

	fmt.Printf("🚀 Deploying %s/%s (type: %s)...\n", deployTeam, deployName, serviceType)
	if err := client.DispatchWorkflow("service.yml", inputs); err != nil {
		return fmt.Errorf("dispatch failed: %w", err)
	}
	fmt.Println("✅ Workflow dispatched successfully")
	fmt.Printf("   https://github.com/%s/%s/actions/workflows/service.yml\n", gh.Owner, gh.Repo)

	if deployWait {
		fmt.Println("\n⏳ Waiting for workflow to complete...")
		run, err := client.WaitForRun("service.yml", dispatchTime, 10*time.Minute)
		if err != nil {
			return err
		}
		fmt.Println()
		if run.Conclusion == "success" {
			fmt.Printf("✅ Deploy completed successfully!\n   %s\n", run.HTMLURL)
		} else {
			fmt.Printf("❌ Deploy %s\n   %s\n", run.Conclusion, run.HTMLURL)
			return fmt.Errorf("workflow %s", run.Conclusion)
		}
	}

	return nil
}
