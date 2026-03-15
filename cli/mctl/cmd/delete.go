package cmd

import (
	"bufio"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/mctlhq/mctl-gitops/cli/mctl/internal/api"
	"github.com/mctlhq/mctl-gitops/cli/mctl/internal/auth"
	"github.com/spf13/cobra"
)

var deleteCmd = &cobra.Command{
	Use:   "delete",
	Short: "Delete a service from the platform",
	Long:  "Delete a service via the mctl API. Removes GitOps files, Vault secrets, and Kubernetes resources.",
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

	client := api.NewClient(token)

	fmt.Printf("🗑️  Deleting %s/%s...\n", deleteTeam, deleteName)
	result, err := client.ExecuteOperation("retire-service", inputs)
	if err != nil {
		return fmt.Errorf("delete failed: %w", err)
	}
	fmt.Println("✅ Delete workflow submitted:", result.WorkflowName)

	if deleteWait {
		ws, err := client.PollWorkflow(result.WorkflowName, 5*time.Minute)
		if err != nil {
			return err
		}
		if ws.Phase == "Succeeded" {
			fmt.Println("✅ Service deleted successfully!")
		} else {
			fmt.Printf("❌ Delete %s: %s\n", ws.Phase, ws.Message)
			return fmt.Errorf("workflow %s", ws.Phase)
		}
	}

	return nil
}
