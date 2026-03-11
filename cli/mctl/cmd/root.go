package cmd

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"
)

var version = "dev"
var apiURL string

var rootCmd = &cobra.Command{
	Use:   "mctl",
	Short: "CLI for the mctl.ai platform",
	Long:  "mctl is a command-line tool for deploying, managing, and deleting services on the mctl.ai platform.",
	SilenceUsage: true,
	PersistentPreRun: func(cmd *cobra.Command, args []string) {
		if apiURL != "" {
			os.Setenv("MCTL_API_URL", apiURL)
		}
	},
}

// GetAPIURL returns the effective API base URL: --api-url flag > MCTL_API_URL env > default.
func GetAPIURL() string {
	if apiURL != "" {
		return apiURL
	}
	if v := os.Getenv("MCTL_API_URL"); v != "" {
		return v
	}
	return "https://api.mctl.ai"
}

func Execute() error {
	return rootCmd.Execute()
}

func init() {
	rootCmd.PersistentFlags().StringVar(&apiURL, "api-url", "", "mctl API base URL (default: $MCTL_API_URL or https://api.mctl.ai)")

	rootCmd.AddCommand(deployCmd)
	rootCmd.AddCommand(deleteCmd)
	rootCmd.AddCommand(configCmd)
	rootCmd.AddCommand(authCmd)
	rootCmd.AddCommand(repoCmd)
	rootCmd.AddCommand(statusCmd)
	rootCmd.AddCommand(logsCmd)

	rootCmd.AddCommand(&cobra.Command{
		Use:   "version",
		Short: "Print version",
		Run: func(cmd *cobra.Command, args []string) {
			fmt.Println("mctl", version)
		},
	})
}

func exitError(msg string) {
	fmt.Fprintln(os.Stderr, "Error:", msg)
	os.Exit(1)
}
