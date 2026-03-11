package cmd

import (
	"fmt"
	"strings"
	"time"

	"github.com/mctlhq/mctl-gitops/cli/mctl/internal/api"
	"github.com/mctlhq/mctl-gitops/cli/mctl/internal/auth"
	"github.com/spf13/cobra"
)

var configCmd = &cobra.Command{
	Use:   "config",
	Short: "Update service configuration (env vars and secrets)",
	Long:  "Update environment variables and secrets for a deployed service without triggering a new build.",
	Example: `  # Update env vars
  mctl config -t my-team -n my-api --env LOG_LEVEL=debug --env TIMEOUT=30

  # Update secrets
  mctl config -t my-team -n my-api --secret API_KEY=sk-new-key

  # Both at once
  mctl config -t my-team -n my-api --env LOG_LEVEL=debug --secret DB_PASS=newpass`,
	RunE: runConfig,
}

var (
	configTeam   string
	configName   string
	configEnv    []string
	configSecret []string
	configWait   bool
)

func init() {
	configCmd.Flags().StringVarP(&configTeam, "team", "t", "", "Team name (required)")
	configCmd.Flags().StringVarP(&configName, "name", "n", "", "Service name (required)")
	configCmd.Flags().StringSliceVar(&configEnv, "env", nil, "Environment variable KEY=VALUE (repeatable)")
	configCmd.Flags().StringSliceVar(&configSecret, "secret", nil, "Secret KEY=VALUE (repeatable)")
	configCmd.Flags().BoolVarP(&configWait, "wait", "w", false, "Wait for workflow to complete")

	configCmd.MarkFlagRequired("team")
	configCmd.MarkFlagRequired("name")
}

func runConfig(cmd *cobra.Command, args []string) error {
	if len(configEnv) == 0 && len(configSecret) == 0 {
		return fmt.Errorf("provide at least one --env or --secret flag")
	}

	token, err := auth.GetToken()
	if err != nil {
		return err
	}

	inputs := map[string]string{
		"action":          "update-config",
		"team_name":       configTeam,
		"component_name":    configName,
		"env_vars":        strings.Join(configEnv, "\n"),
		"secret_env_vars": strings.Join(configSecret, "\n"),
	}

	client := api.NewClient(token)

	fmt.Printf("⚙️  Updating config for %s/%s...\n", configTeam, configName)
	if len(configEnv) > 0 {
		fmt.Printf("   📝 %d env var(s)\n", len(configEnv))
	}
	if len(configSecret) > 0 {
		fmt.Printf("   🔐 %d secret(s)\n", len(configSecret))
	}

	result, err := client.ExecuteOperation("deploy-service", inputs)
	if err != nil {
		return fmt.Errorf("config update failed: %w", err)
	}
	fmt.Println("✅ Config update submitted:", result.WorkflowName)

	if configWait {
		ws, err := client.PollWorkflow(result.WorkflowName, 5*time.Minute)
		if err != nil {
			return err
		}
		if ws.Phase == "Succeeded" {
			fmt.Println("✅ Config updated! ArgoCD will sync automatically.")
		} else {
			fmt.Printf("❌ Config update %s: %s\n", ws.Phase, ws.Message)
			return fmt.Errorf("workflow %s", ws.Phase)
		}
	}

	return nil
}
