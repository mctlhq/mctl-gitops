package cmd

import (
	"bufio"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/dmitriimashkov/mctl.me/cli/mctl/internal/auth"
	gh "github.com/dmitriimashkov/mctl.me/cli/mctl/internal/github"
	"github.com/spf13/cobra"
)

var deleteCmd = &cobra.Command{
	Use:   "delete",
	Short: "Delete a service from the platform",
	Long:  "Delete a service by dispatching the delete-service.yml workflow. Removes GitOps files, Vault secrets, and Kubernetes resources.",
	Example: `  # Delete with confirmation prompt
  mctl delete -t my-team -n my-api

  # Delete without confirmation
  mctl delete -t my-team -n my-api --type base-service -y`,
	RunE: runDelete,
}

var (
	deleteTeam    string
	deleteName    string
	deleteType    string
	deleteYes     bool
	deleteWait    bool
	deleteNoVault bool
)

func init() {
	deleteCmd.Flags().StringVarP(&deleteTeam, "team", "t", "", "Team name (required)")
	deleteCmd.Flags().StringVarP(&deleteName, "name", "n", "", "Service name (required)")
	deleteCmd.Flags().StringVar(&deleteType, "type", "base-service", "Service type: base-service or worker-service")
	deleteCmd.Flags().BoolVarP(&deleteYes, "yes", "y", false, "Skip confirmation prompt")
	deleteCmd.Flags().BoolVarP(&deleteWait, "wait", "w", false, "Wait for workflow to complete")
	deleteCmd.Flags().BoolVar(&deleteNoVault, "no-vault", false, "Skip Vault secrets deletion")

	deleteCmd.MarkFlagRequired("team")
	deleteCmd.MarkFlagRequired("name")
}

func runDelete(cmd *cobra.Command, args []string) error {
	if !deleteYes {
		fmt.Printf("⚠️  This will permanently delete %s/%s and all its resources.\n", deleteTeam, deleteName)
		fmt.Print("   Type 'DELETE' to confirm: ")
		reader := bufio.NewReader(os.Stdin)
		confirm, _ := reader.ReadString('\n')
		if strings.TrimSpace(confirm) != "DELETE" {
			fmt.Println("Aborted.")
			return nil
		}
	}

	token, err := auth.GetToken()
	if err != nil {
		return err
	}

	deleteVault := "true"
	if deleteNoVault {
		deleteVault = "false"
	}

	inputs := map[string]string{
		"team_name":            deleteTeam,
		"component_name":         deleteName,
		"component_type":         deleteType,
		"delete_vault_secrets": deleteVault,
	}

	client := gh.NewClient(token)
	dispatchTime := time.Now().Add(-5 * time.Second)

	fmt.Printf("🗑️  Deleting %s/%s...\n", deleteTeam, deleteName)
	if err := client.DispatchWorkflow("delete-service.yml", inputs); err != nil {
		return fmt.Errorf("dispatch failed: %w", err)
	}
	fmt.Println("✅ Delete workflow dispatched")
	fmt.Printf("   https://github.com/%s/%s/actions/workflows/delete-service.yml\n", gh.Owner, gh.Repo)

	if deleteWait {
		fmt.Println("\n⏳ Waiting for workflow to complete...")
		run, err := client.WaitForRun("delete-service.yml", dispatchTime, 5*time.Minute)
		if err != nil {
			return err
		}
		fmt.Println()
		if run.Conclusion == "success" {
			fmt.Printf("✅ Service deleted successfully!\n   %s\n", run.HTMLURL)
		} else {
			fmt.Printf("❌ Delete %s\n   %s\n", run.Conclusion, run.HTMLURL)
			return fmt.Errorf("workflow %s", run.Conclusion)
		}
	}

	return nil
}
