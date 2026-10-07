package cmd

import (
	"context"
	"errors"
	"fmt"
	"os"
	"time"

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
		mode, err := auth.AuthMode()
		if err != nil {
			return err
		}
		if os.Getenv("MCTL_TOKEN") == "" {
			switch mode {
			case auth.ModeZitadel:
				return zitadelStatus()
			case auth.ModeDefault:
				_, expiry, err := auth.APILoginInfo()
				if err == nil {
					return apiStatus(expiry)
				}
				// Only "no sign-in" continues to the GitHub token below; a
				// sign-in that cannot be read is reported as such.
				if !errors.Is(err, auth.ErrNoAPILogin) {
					fmt.Println("❌ The stored sign-in could not be read")
					return err
				}
			}
		}
		user, err := auth.GetUser()
		if err != nil {
			fmt.Println("❌ Not authenticated")
			fmt.Println("   Run 'mctl auth login' to sign in")
			return err
		}

		fmt.Printf("✅ Authenticated as %s (GitHub token)\n", user)
		if mode == auth.ModeDefault && os.Getenv("MCTL_TOKEN") == "" {
			fmt.Println("   Run 'mctl auth login' to sign in with your MCTL account instead.")
		}
		return nil
	},
}

type whoami struct {
	ID      string   `json:"id"`
	Groups  []string `json:"groups"`
	IsAdmin bool     `json:"isAdmin"`
}

// apiStatus shows the stored mctl sign-in and asks the API who it is, which
// is the end-to-end check that the token still works.
func apiStatus(expiry time.Time) error {
	// The token first: it refreshes an expired one.
	token, err := auth.APIToken()
	if err != nil {
		fmt.Println("❌ The stored sign-in no longer works")
		return err
	}
	var who whoami
	if err := api.NewClient(token).Get("/api/v1/whoami", &who); err != nil {
		fmt.Println("❌ The mctl API refused the stored sign-in")
		return err
	}
	fmt.Printf("✅ Signed in to %s as %s (groups: %v, admin: %v)\n", GetAPIURL(), who.ID, who.Groups, who.IsAdmin)
	if _, fresh, err := auth.APILoginInfo(); err == nil {
		expiry = fresh
	}
	if !expiry.IsZero() {
		fmt.Printf("   Access token expires %s and is renewed automatically.\n", expiry.Local().Format("2006-01-02 15:04"))
	}
	warnNoAccess(who)
	return nil
}

// warnNoAccess explains a sign-in that works but opens nothing: the usual
// cause is a ZITADEL account not yet linked to the person's teams.
func warnNoAccess(who whoami) {
	if len(who.Groups) > 0 || who.IsAdmin {
		return
	}
	fmt.Println("⚠️  This sign-in has no team access, so deploy, status and logs will be refused.")
	fmt.Printf("   If you signed in with ZITADEL, link it to your existing account at %s/identity/link/zitadel\n", GetAPIURL())
	fmt.Println("   Until then, MCTL_AUTH=github uses your GitHub token.")
}

// zitadelStatus shows the stored ZITADEL login and asks the API who it is,
// which is the end-to-end check that mctl-api accepts the token.
func zitadelStatus() error {
	// The token first: it refreshes an expired one, so the expiry shown
	// below is that of the token actually sent.
	token, err := auth.ZitadelToken()
	if errors.Is(err, auth.ErrNoZitadelLogin) {
		fmt.Println("❌ Not authenticated with ZITADEL")
		return err
	}
	if err != nil {
		fmt.Println("❌ Could not obtain a ZITADEL access token")
		return err
	}
	sub, username, expiry, err := auth.ZitadelIdentity()
	if err != nil {
		return err
	}
	fmt.Printf("ZITADEL login: %s (sub %s), access token expires %s\n", username, sub, expiry.Local().Format("2006-01-02 15:04"))
	var who whoami
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
	Short: "Sign in to the mctl API",
	Long: `Sign in to the mctl API in your browser with the authorization code flow
and PKCE. The sign-in page sends you to your MCTL account at auth.mctl.ai.
The token is stored in your user config directory, renewed automatically and
used for every command from then on.

With --zitadel, mctl instead stores a raw ZITADEL token, used only when
MCTL_AUTH=zitadel is set. It carries no team access; prefer the default.`,
	RunE: func(cmd *cobra.Command, args []string) error {
		if authLoginZitadel {
			if err := auth.ZitadelLogin(cmd.Context(), cmd.OutOrStdout(), !authLoginNoBrowse); err != nil {
				return err
			}
			fmt.Println("✅ Signed in with ZITADEL.")
			if !auth.UseZitadel() {
				fmt.Println("   Set MCTL_AUTH=zitadel to use this login for API calls.")
			}
			return nil
		}
		if err := auth.APILogin(cmd.Context(), cmd.OutOrStdout(), !authLoginNoBrowse); err != nil {
			return err
		}
		token, err := auth.APIToken()
		if err != nil {
			return err
		}
		var who whoami
		if err := api.NewClient(token).Get("/api/v1/whoami", &who); err != nil {
			fmt.Println("❌ Signed in, but the mctl API refused the new token")
			return err
		}
		fmt.Printf("✅ Signed in to %s as %s (groups: %v, admin: %v)\n", GetAPIURL(), who.ID, who.Groups, who.IsAdmin)
		warnNoAccess(who)
		if mode, err := auth.AuthMode(); err != nil || mode != auth.ModeDefault || os.Getenv("MCTL_TOKEN") != "" {
			fmt.Println("   MCTL_TOKEN or MCTL_AUTH is set and takes precedence: unset it to use this sign-in.")
		}
		return nil
	},
}

var authLogoutCmd = &cobra.Command{
	Use:   "logout",
	Short: "Remove the stored sign-in",
	RunE: func(cmd *cobra.Command, args []string) error {
		if authLogoutZitadel {
			if err := auth.ZitadelLogout(); err != nil {
				return err
			}
			fmt.Println("✅ ZITADEL login removed.")
			return nil
		}
		ctx := cmd.Context()
		if ctx == nil {
			ctx = context.Background()
		}
		revokeErr, err := auth.APILogout(ctx)
		if err != nil {
			return err
		}
		fmt.Println("✅ Signed out.")
		if revokeErr != nil {
			fmt.Printf("⚠️  The API did not confirm the revocation, so the removed token may stay valid until it expires: %v\n", revokeErr)
		}
		return nil
	},
}

func init() {
	authLoginCmd.Flags().BoolVar(&authLoginZitadel, "zitadel", false, "Store a raw ZITADEL token instead (used with MCTL_AUTH=zitadel)")
	authLoginCmd.Flags().BoolVar(&authLoginNoBrowse, "no-browser", false, "Print the sign-in URL instead of opening a browser")
	authLogoutCmd.Flags().BoolVar(&authLogoutZitadel, "zitadel", false, "Remove the stored raw ZITADEL login instead")

	authCmd.AddCommand(authStatusCmd)
	authCmd.AddCommand(authLoginCmd)
	authCmd.AddCommand(authLogoutCmd)
}
