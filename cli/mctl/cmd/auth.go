package cmd

import (
	"fmt"
	"os"

	"github.com/mctlhq/mctl-gitops/cli/mctl/internal/api"
	"github.com/mctlhq/mctl-gitops/cli/mctl/internal/auth"
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
		if auth.UseZitadel() && os.Getenv("MCTL_TOKEN") == "" {
			return zitadelStatus()
		}
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

// zitadelStatus shows the stored ZITADEL login and asks the API who it is,
// which is the end-to-end check that mctl-api accepts the token.
func zitadelStatus() error {
	sub, username, expiry, err := auth.ZitadelIdentity()
	if err != nil {
		fmt.Println("❌ Not authenticated with ZITADEL")
		return err
	}
	fmt.Printf("ZITADEL login: %s (sub %s), access token expires %s\n", username, sub, expiry.Local().Format("2006-01-02 15:04"))

	token, err := auth.ZitadelToken()
	if err != nil {
		return err
	}
	var who struct {
		ID      string   `json:"id"`
		Groups  []string `json:"groups"`
		IsAdmin bool     `json:"isAdmin"`
	}
	if err := api.NewClient(token).Get("/api/v1/whoami", &who); err != nil {
		fmt.Println("❌ The mctl API refused the ZITADEL token")
		return err
	}
	fmt.Printf("✅ Authenticated to %s as %s (groups: %v, admin: %v)\n", GetAPIURL(), who.ID, who.Groups, who.IsAdmin)
	return nil
}

var (
	authLoginZitadel  bool
	authLoginNoBrowse bool
	authLogoutZitadel bool
)

var authLoginCmd = &cobra.Command{
	Use:   "login",
	Short: "Sign in (ZITADEL, opt-in)",
	Long: `Sign in to the mctl API through ZITADEL (auth.mctl.ai) with the
authorization code flow and PKCE. The token is stored in your user config
directory and used for API calls when MCTL_AUTH=zitadel is set.

Without --zitadel, mctl keeps using your GitHub token (gh auth login).`,
	RunE: func(cmd *cobra.Command, args []string) error {
		if !authLoginZitadel {
			return fmt.Errorf("mctl uses your GitHub token by default: run 'gh auth login', or 'mctl auth login --zitadel' to sign in through ZITADEL")
		}
		if err := auth.ZitadelLogin(cmd.Context(), cmd.OutOrStdout(), !authLoginNoBrowse); err != nil {
			return err
		}
		fmt.Println("✅ Signed in with ZITADEL.")
		if !auth.UseZitadel() {
			fmt.Println("   Set MCTL_AUTH=zitadel to use this login for API calls.")
		}
		return nil
	},
}

var authLogoutCmd = &cobra.Command{
	Use:   "logout",
	Short: "Remove the stored ZITADEL login",
	RunE: func(cmd *cobra.Command, args []string) error {
		if !authLogoutZitadel {
			return fmt.Errorf("only the ZITADEL login is stored by mctl: use 'mctl auth logout --zitadel' (GitHub: 'gh auth logout')")
		}
		if err := auth.ZitadelLogout(); err != nil {
			return err
		}
		fmt.Println("✅ ZITADEL login removed.")
		return nil
	},
}

func init() {
	authLoginCmd.Flags().BoolVar(&authLoginZitadel, "zitadel", false, "Sign in through ZITADEL (auth.mctl.ai)")
	authLoginCmd.Flags().BoolVar(&authLoginNoBrowse, "no-browser", false, "Print the sign-in URL instead of opening a browser")
	authLogoutCmd.Flags().BoolVar(&authLogoutZitadel, "zitadel", false, "Remove the stored ZITADEL login")

	authCmd.AddCommand(authStatusCmd)
	authCmd.AddCommand(authLoginCmd)
	authCmd.AddCommand(authLogoutCmd)
}
