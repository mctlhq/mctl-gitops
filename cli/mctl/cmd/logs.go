package cmd

import (
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/mctlhq/mctl-gitops/cli/mctl/internal/api"
	"github.com/mctlhq/mctl-gitops/cli/mctl/internal/auth"
	"github.com/spf13/cobra"
)

var logsCmd = &cobra.Command{
	Use:   "logs",
	Short: "Fetch recent log lines for a service",
	Long: `Fetch recent log lines for a deployed service from Loki.

Logs are returned most-recent-first by default.
Requires the platform to be running with Loki enabled (in-cluster deployment).`,
	Example: `  # Last 100 lines from the past hour
  mctl logs -t billing -n payment-api

  # Last 50 lines from the past 15 minutes
  mctl logs -t billing -n payment-api --lines 50 --since 15m

  # Raw JSON output (includes labels)
  mctl logs -t billing -n payment-api --json

  # Follow (re-poll every 5s)
  mctl logs -t billing -n payment-api --lines 20 --since 30s --follow`,
	RunE: runLogs,
}

var (
	logsTeam   string
	logsName   string
	logsLines  int
	logsSince  string
	logsJSON   bool
	logsFollow bool
)

func init() {
	logsCmd.Flags().StringVarP(&logsTeam, "team", "t", "", "Team name (required)")
	logsCmd.Flags().StringVarP(&logsName, "name", "n", "", "Service name (required)")
	logsCmd.Flags().IntVar(&logsLines, "lines", 100, "Number of log lines to return (max 1000)")
	logsCmd.Flags().StringVar(&logsSince, "since", "1h", "Time window: 15m, 1h, 6h, 24h")
	logsCmd.Flags().BoolVar(&logsJSON, "json", false, "Output raw JSON (includes labels)")
	logsCmd.Flags().BoolVarP(&logsFollow, "follow", "f", false, "Re-poll every 5 seconds (press Ctrl+C to stop)")

	logsCmd.MarkFlagRequired("team")
	logsCmd.MarkFlagRequired("name")
}

type logsResponse struct {
	Team  string     `json:"team"`
	App   string     `json:"app"`
	Lines []logLine  `json:"lines"`
	Count int        `json:"count"`
	Note  string     `json:"note"`
}

type logLine struct {
	Timestamp time.Time         `json:"timestamp"`
	Line      string            `json:"line"`
	Labels    map[string]string `json:"labels"`
}

func buildLogsPath(team, name, since string, lines int) string {
	return fmt.Sprintf("/api/v1/logs/%s/%s?lines=%d&since=%s", team, name, lines, since)
}

func runLogs(cmd *cobra.Command, args []string) error {
	token, err := auth.GetToken()
	if err != nil {
		return err
	}

	client := api.NewClient(token)

	fetch := func() error {
		path := buildLogsPath(logsTeam, logsName, logsSince, logsLines)

		if logsJSON {
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

		var resp logsResponse
		if err := client.Get(path, &resp); err != nil {
			return err
		}

		if resp.Note != "" && resp.Count == 0 {
			fmt.Printf("Note: %s\n", resp.Note)
			return nil
		}

		if resp.Count == 0 {
			fmt.Printf("No logs found for %s/%s in the last %s\n", logsTeam, logsName, logsSince)
			return nil
		}

		// Print log lines in chronological order (reverse the most-recent-first slice).
		for i := len(resp.Lines) - 1; i >= 0; i-- {
			l := resp.Lines[i]
			ts := l.Timestamp.Format("15:04:05")
			fmt.Printf("%s  %s\n", ts, l.Line)
		}

		if resp.Note != "" {
			fmt.Printf("\nNote: %s\n", resp.Note)
		}

		return nil
	}

	if !logsFollow {
		return fetch()
	}

	// Follow mode: re-poll every 5s, shrinking since window to avoid duplicate lines.
	fmt.Printf("Following logs for %s/%s (Ctrl+C to stop)\n", logsTeam, logsName)
	fmt.Println(strings.Repeat("─", 50))

	for {
		if err := fetch(); err != nil {
			fmt.Printf("Error: %v\n", err)
		}
		time.Sleep(5 * time.Second)
		// Tighten the window after first fetch.
		logsSince = "10s"
	}
}

// Ensure json import is used.
var _ = json.Marshal
