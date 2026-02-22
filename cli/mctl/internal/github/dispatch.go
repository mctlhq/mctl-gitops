package github

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

const (
	Owner = "mctlhq"
	Repo  = "mctl.me"
	APIURL = "https://api.github.com"
)

// Client wraps GitHub API calls.
type Client struct {
	Token      string
	HTTPClient *http.Client
}

// NewClient creates a GitHub API client.
func NewClient(token string) *Client {
	return &Client{
		Token:      token,
		HTTPClient: &http.Client{Timeout: 30 * time.Second},
	}
}

// DispatchWorkflow triggers a workflow_dispatch event.
func (c *Client) DispatchWorkflow(workflowFile string, inputs map[string]string) error {
	url := fmt.Sprintf("%s/repos/%s/%s/actions/workflows/%s/dispatches", APIURL, Owner, Repo, workflowFile)

	body := map[string]interface{}{
		"ref":    "main",
		"inputs": inputs,
	}
	jsonBody, err := json.Marshal(body)
	if err != nil {
		return fmt.Errorf("failed to marshal request: %w", err)
	}

	req, err := http.NewRequest("POST", url, bytes.NewReader(jsonBody))
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+c.Token)
	req.Header.Set("Accept", "application/vnd.github+json")
	req.Header.Set("X-GitHub-Api-Version", "2022-11-28")

	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusNoContent {
		respBody, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("workflow dispatch failed (HTTP %d): %s", resp.StatusCode, string(respBody))
	}

	return nil
}

// WorkflowRun represents a GitHub Actions workflow run.
type WorkflowRun struct {
	ID         int64  `json:"id"`
	Status     string `json:"status"`
	Conclusion string `json:"conclusion"`
	HTMLURL    string `json:"html_url"`
	CreatedAt  string `json:"created_at"`
}

type workflowRunsResponse struct {
	TotalCount int           `json:"total_count"`
	Runs       []WorkflowRun `json:"workflow_runs"`
}

// FindLatestRun finds the most recent run for a workflow, created after the given time.
func (c *Client) FindLatestRun(workflowFile string, after time.Time) (*WorkflowRun, error) {
	url := fmt.Sprintf("%s/repos/%s/%s/actions/workflows/%s/runs?per_page=5&event=workflow_dispatch",
		APIURL, Owner, Repo, workflowFile)

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+c.Token)
	req.Header.Set("Accept", "application/vnd.github+json")

	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var result workflowRunsResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, err
	}

	for _, run := range result.Runs {
		created, err := time.Parse(time.RFC3339, run.CreatedAt)
		if err != nil {
			continue
		}
		if created.After(after) {
			return &run, nil
		}
	}
	return nil, nil
}

// WaitForRun polls until the workflow run completes or times out.
func (c *Client) WaitForRun(workflowFile string, dispatchTime time.Time, timeout time.Duration) (*WorkflowRun, error) {
	deadline := time.Now().Add(timeout)

	// Wait a bit for the run to appear
	time.Sleep(3 * time.Second)

	for time.Now().Before(deadline) {
		run, err := c.FindLatestRun(workflowFile, dispatchTime)
		if err != nil {
			return nil, err
		}

		if run != nil {
			if run.Status == "completed" {
				return run, nil
			}
			fmt.Printf("\r  ⏳ Run #%d — %s...", run.ID, run.Status)
		} else {
			fmt.Print("\r  ⏳ Waiting for run to start...")
		}

		time.Sleep(5 * time.Second)
	}

	return nil, fmt.Errorf("timed out waiting for workflow run")
}
