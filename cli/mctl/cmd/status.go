package cmd

import (
	"fmt"
	"strings"
	"time"

	"github.com/mctlhq/mctl-gitops/cli/mctl/internal/api"
	"github.com/mctlhq/mctl-gitops/cli/mctl/internal/auth"
	"github.com/spf13/cobra"
)

var statusCmd = &cobra.Command{
	Use:   "status",
	Short: "Get live status of a deployed service",
	Long: `Get ArgoCD sync state, health, and service configuration for a deployed service.

Shows:
  - Sync status (Synced / OutOfSync)
  - Health status (Healthy / Degraded / Progressing)
  - Current image tag
  - Ingress host`,
	Example: `  mctl status -t billing -n payment-api
  mctl status -t data-team -n worker --json`,
	RunE: runStatus,
}

var (
	statusTeam    string
	statusName    string
	statusJSON    bool
)

func init() {
	statusCmd.Flags().StringVarP(&statusTeam, "team", "t", "", "Team name (required)")
	statusCmd.Flags().StringVarP(&statusName, "name", "n", "", "Service name (required)")
	statusCmd.Flags().BoolVar(&statusJSON, "json", false, "Output raw JSON")

	statusCmd.MarkFlagRequired("team")
	statusCmd.MarkFlagRequired("name")
}

type statusResponse struct {
	ArgoCD *struct {
		Name         string `json:"name"`
		SyncStatus   string `json:"syncStatus"`
		HealthStatus string `json:"healthStatus"`
		Message      string `json:"message"`
	} `json:"argocd"`
	Service *struct {
		Team          string `json:"team"`
		Name          string `json:"name"`
		ImageTag      string `json:"imageTag"`
		Host          string `json:"host"`
		Port          string `json:"port"`
		ComponentType string `json:"componentType"`
		HasDatabase   bool   `json:"hasDatabase"`
	} `json:"service"`
}

func runStatus(cmd *cobra.Command, args []string) error {
	token, err := auth.GetToken()
	if err != nil {
		return err
	}

	client := api.NewClient(token)

	path := fmt.Sprintf("/api/v1/status/%s/%s", statusTeam, statusName)

	if statusJSON {
		body, code, err := client.GetRaw(path)
		if err != nil {
			return err
		}
		if code >= 400 {
			return fmt.Errorf("API error (%d): %s", code, string(body))
		}
		fmt.Println(string(body))
		return nil
	}

	var resp statusResponse
	if err := client.Get(path, &resp); err != nil {
		return err
	}

	// Print formatted output
	fmt.Printf("Service: %s/%s\n", statusTeam, statusName)
	fmt.Println(strings.Repeat("─", 40))

	if resp.ArgoCD != nil {
		syncIcon := iconForSync(resp.ArgoCD.SyncStatus)
		healthIcon := iconForHealth(resp.ArgoCD.HealthStatus)
		fmt.Printf("Sync:    %s %s\n", syncIcon, resp.ArgoCD.SyncStatus)
		fmt.Printf("Health:  %s %s\n", healthIcon, resp.ArgoCD.HealthStatus)
		if resp.ArgoCD.Message != "" {
			fmt.Printf("Message: %s\n", resp.ArgoCD.Message)
		}
	} else {
		fmt.Println("ArgoCD:  not found")
	}

	if resp.Service != nil {
		fmt.Println(strings.Repeat("─", 40))
		if resp.Service.ImageTag != "" {
			fmt.Printf("Image:   %s\n", resp.Service.ImageTag)
		}
		if resp.Service.Host != "" {
			fmt.Printf("Host:    https://%s\n", resp.Service.Host)
		}
		if resp.Service.Port != "" {
			fmt.Printf("Port:    %s\n", resp.Service.Port)
		}
		fmt.Printf("Type:    %s\n", resp.Service.ComponentType)
		if resp.Service.HasDatabase {
			fmt.Println("DB:      yes")
		}
	}

	// Hint: suggest checking logs if degraded
	if resp.ArgoCD != nil && resp.ArgoCD.HealthStatus == "Degraded" {
		fmt.Printf("\nService is degraded. Check logs:\n  mctl logs -t %s -n %s\n", statusTeam, statusName)
	}

	_ = time.Now() // keep time import for potential future use

	return nil
}

func iconForSync(s string) string {
	switch s {
	case "Synced":
		return "✓"
	case "OutOfSync":
		return "!"
	default:
		return "?"
	}
}

func iconForHealth(s string) string {
	switch s {
	case "Healthy":
		return "✓"
	case "Progressing":
		return "~"
	case "Degraded":
		return "✗"
	case "Suspended":
		return "⏸"
	default:
		return "?"
	}
}
