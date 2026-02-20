package cmd

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os/exec"
	"runtime"
	"time"

	"github.com/dmitriimashkov/mctl.me/tools/mctl/internal/auth"
	"github.com/spf13/cobra"
)

const defaultBackstageURL = "https://backstage-preprod.mctl.me"

var repoCmd = &cobra.Command{
	Use:   "repo",
	Short: "Manage repository connections",
	Long:  "Connect and check status of GitHub repository access for private repo deployments.",
}

var (
	repoConnTeam    string
	repoConnService string
	repoConnRepo    string
	repoConnWait    bool
)

var repoConnectCmd = &cobra.Command{
	Use:   "connect",
	Short: "Connect a private repo via GitHub App installation",
	Long: `Opens the GitHub App installation page so you can grant access to your private repository.
After installation, the platform can clone your repo without a PAT.`,
	Example: `  # Connect a repo for a service
  mctl repo connect --repo dmitriimashkov/my-api --team my-team --service my-api

  # Connect and wait for confirmation
  mctl repo connect --repo dmitriimashkov/my-api --team my-team --service my-api --wait`,
	RunE: runRepoConnect,
}

var repoStatusCmd = &cobra.Command{
	Use:   "status",
	Short: "Check repo connection status",
	Example: `  mctl repo status --repo dmitriimashkov/my-api --team my-team --service my-api`,
	RunE: runRepoStatus,
}

func init() {
	repoConnectCmd.Flags().StringVarP(&repoConnTeam, "team", "t", "", "Team name (required)")
	repoConnectCmd.Flags().StringVarP(&repoConnService, "service", "s", "", "Service name (required)")
	repoConnectCmd.Flags().StringVarP(&repoConnRepo, "repo", "r", "", "Repository owner/name (required)")
	repoConnectCmd.Flags().BoolVarP(&repoConnWait, "wait", "w", false, "Wait for connection to complete")
	repoConnectCmd.MarkFlagRequired("team")
	repoConnectCmd.MarkFlagRequired("service")
	repoConnectCmd.MarkFlagRequired("repo")

	repoStatusCmd.Flags().StringVarP(&repoConnTeam, "team", "t", "", "Team name (required)")
	repoStatusCmd.Flags().StringVarP(&repoConnService, "service", "s", "", "Service name (required)")
	repoStatusCmd.Flags().StringVarP(&repoConnRepo, "repo", "r", "", "Repository owner/name (required)")
	repoStatusCmd.MarkFlagRequired("team")
	repoStatusCmd.MarkFlagRequired("service")
	repoStatusCmd.MarkFlagRequired("repo")

	repoCmd.AddCommand(repoConnectCmd)
	repoCmd.AddCommand(repoStatusCmd)
}

func backstageURL() string {
	return defaultBackstageURL
}

func openBrowser(url string) error {
	switch runtime.GOOS {
	case "darwin":
		return exec.Command("open", url).Start()
	case "linux":
		return exec.Command("xdg-open", url).Start()
	default:
		return fmt.Errorf("unsupported OS for browser open")
	}
}

func runRepoConnect(cmd *cobra.Command, args []string) error {
	// Verify auth first
	if _, err := auth.GetToken(); err != nil {
		return err
	}

	base := backstageURL()
	params := url.Values{
		"team":    {repoConnTeam},
		"service": {repoConnService},
		"repo":    {repoConnRepo},
	}

	// Get install URL from backend
	installURLEndpoint := fmt.Sprintf("%s/api/github-app-connect/install-url?%s", base, params.Encode())
	resp, err := http.Get(installURLEndpoint)
	if err != nil {
		return fmt.Errorf("failed to reach Backstage API: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("API error (HTTP %d): %s", resp.StatusCode, string(body))
	}

	var result struct {
		URL   string `json:"url"`
		State string `json:"state"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return fmt.Errorf("failed to parse response: %w", err)
	}

	fmt.Println("🔗 Opening GitHub App installation page...")
	fmt.Printf("   Repo: %s\n", repoConnRepo)
	fmt.Printf("   Team: %s, Service: %s\n\n", repoConnTeam, repoConnService)

	if err := openBrowser(result.URL); err != nil {
		fmt.Printf("⚠️  Could not open browser. Please visit:\n   %s\n\n", result.URL)
	} else {
		fmt.Println("   Browser opened. Install the GitHub App and grant access to your repository.")
	}

	if !repoConnWait {
		fmt.Println("\n💡 Run 'mctl repo status' to check connection status, or use --wait flag.")
		return nil
	}

	fmt.Println("\n⏳ Waiting for connection...")
	statusURL := fmt.Sprintf("%s/api/github-app-connect/install-status?%s", base, params.Encode())

	for i := 0; i < 60; i++ { // 5 min timeout (60 * 5s)
		time.Sleep(5 * time.Second)

		statusResp, err := http.Get(statusURL)
		if err != nil {
			continue
		}
		var statusResult struct {
			Status string `json:"status"`
		}
		json.NewDecoder(statusResp.Body).Decode(&statusResult)
		statusResp.Body.Close()

		if statusResult.Status == "connected" {
			fmt.Printf("\n✅ Repository %s connected successfully!\n", repoConnRepo)
			fmt.Println("   You can now deploy without --pat flag.")
			return nil
		}
		fmt.Print(".")
	}

	return fmt.Errorf("timed out waiting for connection. Check status with 'mctl repo status'")
}

func runRepoStatus(cmd *cobra.Command, args []string) error {
	if _, err := auth.GetToken(); err != nil {
		return err
	}

	base := backstageURL()
	params := url.Values{
		"team":    {repoConnTeam},
		"service": {repoConnService},
		"repo":    {repoConnRepo},
	}

	accessURL := fmt.Sprintf("%s/api/github-app-connect/repo-access?%s", base, params.Encode())
	resp, err := http.Get(accessURL)
	if err != nil {
		return fmt.Errorf("failed to reach Backstage API: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("API error (HTTP %d): %s", resp.StatusCode, string(body))
	}

	var result struct {
		Status         string `json:"status"`
		Method         string `json:"method"`
		InstallationID int64  `json:"installation_id,omitempty"`
		InstallURL     string `json:"install_url,omitempty"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return fmt.Errorf("failed to parse response: %w", err)
	}

	fmt.Printf("📦 Repository: %s\n", repoConnRepo)
	fmt.Printf("   Team: %s, Service: %s\n\n", repoConnTeam, repoConnService)

	switch result.Status {
	case "connected":
		fmt.Printf("✅ Connected via %s", result.Method)
		if result.InstallationID > 0 {
			fmt.Printf(" (installation %d)", result.InstallationID)
		}
		fmt.Println()
	case "accessible":
		fmt.Printf("✅ Public repo — no connection needed (method: %s)\n", result.Method)
	case "needs_install":
		fmt.Println("❌ Not connected — private repo requires GitHub App installation")
		fmt.Printf("   Run: mctl repo connect --repo %s --team %s --service %s\n", repoConnRepo, repoConnTeam, repoConnService)
	default:
		fmt.Printf("⚠️  Unknown status: %s\n", result.Status)
	}

	return nil
}
