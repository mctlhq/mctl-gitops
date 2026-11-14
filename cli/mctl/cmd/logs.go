package cmd

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
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
  mctl logs -t billing -n payment-api --lines 20 --since 1m --follow`,
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
	Team  string    `json:"team"`
	App   string    `json:"app"`
	Lines []logLine `json:"lines"`
	Count int       `json:"count"`
	Note  string    `json:"note"`
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

	if !logsFollow {
		return fetchLogs(client, os.Stdout, logsSince, nil)
	}

	// Follow mode: re-poll every 5s. Each poll asks for a window that
	// overlaps the previous one, so no line falls into a gap between polls;
	// the cursor drops what was already printed.
	// Status goes to stderr: stdout carries only log lines, so --json
	// stays parseable.
	fmt.Fprintf(os.Stderr, "Following logs for %s/%s (Ctrl+C to stop)\n", logsTeam, logsName)
	fmt.Fprintln(os.Stderr, strings.Repeat("─", 50))

	cur := &logCursor{}
	var lastOK time.Time
	for {
		started := time.Now()
		if err := fetchLogs(client, os.Stdout, followSince(logsSince, lastOK, started), cur); err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		} else {
			lastOK = started
		}
		time.Sleep(5 * time.Second)
	}
}

// followSince is the window for a poll starting at now. It reaches back to the
// start of the last successful poll, not the last attempt: a failed poll
// printed nothing, so the lines it would have covered are still owed. Until a
// poll succeeds, the user's --since stands, raised to the API's floor: a
// shorter one would be refused on every poll and follow mode would never
// recover.
func followSince(initial string, lastOK, now time.Time) string {
	if lastOK.IsZero() {
		if d, err := time.ParseDuration(initial); err == nil && d < minFollowWindow*time.Second {
			return fmt.Sprintf("%ds", minFollowWindow)
		}
		return initial
	}
	return followWindow(now.Sub(lastOK))
}

// minFollowWindow is mctl-api's lower bound for since (minLogWindow in
// internal/api/handlers_read.go): a shorter window is refused with 400.
const minFollowWindow = 60

// followWindow is the window for the next poll: the time since the last one
// started plus a margin, in whole seconds, never under the API's 1m floor.
// The overlap this creates is dropped by logCursor.
func followWindow(elapsed time.Duration) string {
	secs := int((elapsed + 5*time.Second + time.Second - 1) / time.Second)
	if secs < minFollowWindow {
		secs = minFollowWindow
	}
	return fmt.Sprintf("%ds", secs)
}

// logCursor remembers what follow mode has printed, so overlapping polls do
// not print a line twice. Lines are ordered by timestamp; several can share
// one, so the lines printed at the newest timestamp are counted too: the same
// text can legitimately appear more than once at one timestamp.
type logCursor struct {
	last   time.Time
	atLast map[string]int
}

// fresh returns the lines not yet seen, in chronological order, and moves the
// cursor past them. lines is most-recent-first, as the API returns it.
func (c *logCursor) fresh(lines []logLine) []logLine {
	if c.atLast == nil {
		c.atLast = map[string]int{}
	}
	var out []logLine
	// seen counts this poll's occurrences at c.last; the first atLast[line]
	// of them were printed by an earlier poll.
	seen := map[string]int{}
	for i := len(lines) - 1; i >= 0; i-- {
		l := lines[i]
		switch {
		case l.Timestamp.Before(c.last):
			continue
		case l.Timestamp.Equal(c.last):
			seen[l.Line]++
			if seen[l.Line] <= c.atLast[l.Line] {
				continue
			}
		default:
			c.last = l.Timestamp
			c.atLast = map[string]int{}
			seen = map[string]int{l.Line: 1}
		}
		c.atLast[l.Line]++
		out = append(out, l)
	}
	return out
}

// fetchLogs prints one poll. With a cursor (follow mode) it prints only the
// lines the cursor has not seen, and stays quiet when there are none.
func fetchLogs(client *api.Client, w io.Writer, since string, cur *logCursor) error {
	path := buildLogsPath(logsTeam, logsName, since, logsLines)

	if logsJSON && cur == nil {
		body, code, err := client.GetRaw(path)
		if err != nil {
			return err
		}
		if code >= 400 {
			return fmt.Errorf("API error (%d): %s", code, string(body))
		}
		fmt.Fprintln(w, string(body))
		return nil
	}

	var resp logsResponse
	if err := client.Get(path, &resp); err != nil {
		return err
	}

	if cur != nil {
		lines := cur.fresh(resp.Lines)
		if logsJSON {
			// One JSON object per new line: a whole response per poll
			// would repeat the overlap.
			enc := json.NewEncoder(w)
			for _, l := range lines {
				if err := enc.Encode(l); err != nil {
					return err
				}
			}
			return nil
		}
		for _, l := range lines {
			fmt.Fprintf(w, "%s  %s\n", l.Timestamp.Format("15:04:05"), l.Line)
		}
		return nil
	}

	if resp.Note != "" && resp.Count == 0 {
		fmt.Fprintf(w, "Note: %s\n", resp.Note)
		return nil
	}

	if resp.Count == 0 {
		fmt.Fprintf(w, "No logs found for %s/%s in the last %s\n", logsTeam, logsName, since)
		return nil
	}

	// Print log lines in chronological order (reverse the most-recent-first slice).
	for i := len(resp.Lines) - 1; i >= 0; i-- {
		l := resp.Lines[i]
		fmt.Fprintf(w, "%s  %s\n", l.Timestamp.Format("15:04:05"), l.Line)
	}

	if resp.Note != "" {
		fmt.Fprintf(w, "\nNote: %s\n", resp.Note)
	}

	return nil
}
