package cmd

import (
	"fmt"
	"strings"
	"time"

	"github.com/dmitriimashkov/mctl.me/cli/mctl/internal/auth"
	gh "github.com/dmitriimashkov/mctl.me/cli/mctl/internal/github"
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

	client := gh.NewClient(token)
	dispatchTime := time.Now().Add(-5 * time.Second)

	fmt.Printf("⚙️  Updating config for %s/%s...\n", configTeam, configName)
	if len(configEnv) > 0 {
		fmt.Printf("   📝 %d env var(s)\n", len(configEnv))
	}
	if len(configSecret) > 0 {
		fmt.Printf("   🔐 %d secret(s)\n", len(configSecret))
	}

	if err := client.DispatchWorkflow("service.yml", inputs); err != nil {
		return fmt.Errorf("dispatch failed: %w", err)
	}
	fmt.Println("✅ Config update dispatched")
	fmt.Printf("   https://github.com/%s/%s/actions/workflows/service.yml\n", gh.Owner, gh.Repo)

	if configWait {
		fmt.Println("\n⏳ Waiting for workflow to complete...")
		run, err := client.WaitForRun("service.yml", dispatchTime, 5*time.Minute)
		if err != nil {
			return err
		}
		fmt.Println()
		if run.Conclusion == "success" {
			fmt.Printf("✅ Config updated! ArgoCD will sync automatically.\n   %s\n", run.HTMLURL)
		} else {
			fmt.Printf("❌ Config update %s\n   %s\n", run.Conclusion, run.HTMLURL)
			return fmt.Errorf("workflow %s", run.Conclusion)
		}
	}

	return nil
}
