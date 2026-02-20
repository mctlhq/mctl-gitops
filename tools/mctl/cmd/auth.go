package cmd

import (
	"fmt"

	"github.com/dmitriimashkov/mctl.me/tools/mctl/internal/auth"
	"github.com/spf13/cobra"
)

var authCmd = &cobra.Command{
	Use:   "auth",
	Short: "Manage authentication",
}

var authStatusCmd = &cobra.Command{
	Use:   "status",
	Short: "Show current authentication status",
	RunE: func(cmd *cobra.Command, args []string) error {
		user, err := auth.GetUser()
		if err != nil {
			fmt.Println("❌ Not authenticated")
			fmt.Println("   Run 'gh auth login' to authenticate")
			return err
		}

		fmt.Printf("✅ Authenticated as %s\n", user)
		return nil
	},
}

func init() {
	authCmd.AddCommand(authStatusCmd)
}
