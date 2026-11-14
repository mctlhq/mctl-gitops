package cmd

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/mctlhq/mctl-gitops/cli/mctl/internal/api"
)

func TestLogCursorPrintsEachLineOnce(t *testing.T) {
	t0 := time.Date(2026, 11, 14, 10, 0, 0, 0, time.UTC)
	at := func(s int, line string) logLine {
		return logLine{Timestamp: t0.Add(time.Duration(s) * time.Second), Line: line}
	}
	c := &logCursor{}
	var printed []string
	poll := func(newestFirst ...logLine) {
		for _, l := range c.fresh(newestFirst) {
			printed = append(printed, l.Line)
		}
	}
	poll(at(2, "b"), at(1, "a"))
	poll(at(4, "d"), at(2, "b2"), at(2, "b"), at(1, "a")) // overlap; b2 shares b's timestamp
	poll(at(4, "d"), at(2, "b"))                          // nothing new
	poll(at(5, "e"), at(4, "d"))
	if got, want := strings.Join(printed, ","), "a,b,b2,d,e"; got != want {
		t.Errorf("printed %s, want %s", got, want)
	}
}

// TestFollowPollsDoNotRepeatLines drives fetchLogs against an API that
// returns overlapping windows, as Loki does for since=10s polled every 5s.
func TestFollowPollsDoNotRepeatLines(t *testing.T) {
	t0 := time.Date(2026, 11, 14, 10, 0, 0, 0, time.UTC)
	answers := [][]logLine{
		{{Timestamp: t0.Add(2 * time.Second), Line: "two"}, {Timestamp: t0, Line: "one"}},
		{{Timestamp: t0.Add(7 * time.Second), Line: "three"}, {Timestamp: t0.Add(2 * time.Second), Line: "two"}},
	}
	n := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		lines := answers[n]
		n++
		_ = json.NewEncoder(w).Encode(logsResponse{Lines: lines, Count: len(lines)})
	}))
	defer srv.Close()
	t.Setenv("MCTL_API_URL", srv.URL)
	client := api.NewClient("token")

	for _, jsonOut := range []bool{false, true} {
		n = 0
		logsJSON = jsonOut
		var out strings.Builder
		cur := &logCursor{}
		for range answers {
			if err := fetchLogs(client, &out, "10s", cur); err != nil {
				t.Fatal(err)
			}
		}
		for _, line := range []string{"one", "two", "three"} {
			if c := strings.Count(out.String(), line); c != 1 {
				t.Errorf("json=%v: %q printed %d times:\n%s", jsonOut, line, c, out.String())
			}
		}
	}
	logsJSON = false
}

func TestFollowWindowCoversTheGap(t *testing.T) {
	for _, tc := range []struct {
		elapsed time.Duration
		want    string
	}{
		// mctl-api refuses since < 1m with 400, so a short gap still asks for 60s.
		{0, "60s"},
		{5 * time.Second, "60s"},
		{20 * time.Second, "60s"},
		{54*time.Second + 500*time.Millisecond, "60s"},
		{60 * time.Second, "65s"},
		{60*time.Second + time.Millisecond, "66s"},
	} {
		if got := followWindow(tc.elapsed); got != tc.want {
			t.Errorf("followWindow(%v) = %s, want %s", tc.elapsed, got, tc.want)
		}
	}
}
