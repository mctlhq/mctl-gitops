package api

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"
)

const defaultBaseURL = "https://api.mctl.ai"

// Client calls the mctl REST API.
type Client struct {
	baseURL    string
	token      string
	httpClient *http.Client
}

// NewClient creates an API client using the given GitHub token.
// The base URL is taken from MCTL_API_URL env var, defaulting to https://api.mctl.ai.
func NewClient(token string) *Client {
	base := os.Getenv("MCTL_API_URL")
	if base == "" {
		base = defaultBaseURL
	}
	return &Client{
		baseURL: base,
		token:   token,
		httpClient: &http.Client{Timeout: 15 * time.Second},
	}
}

// Get performs an authenticated GET request and decodes JSON into v.
func (c *Client) Get(path string, v interface{}) error {
	req, err := http.NewRequest("GET", c.baseURL+path, nil)
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+c.token)
	req.Header.Set("Accept", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close() //nolint:errcheck

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("reading response: %w", err)
	}
	if resp.StatusCode >= 400 {
		var e struct {
			Error string `json:"error"`
		}
		if jsonErr := json.Unmarshal(body, &e); jsonErr == nil && e.Error != "" {
			return fmt.Errorf("API error (%d): %s", resp.StatusCode, e.Error)
		}
		return fmt.Errorf("API returned %d", resp.StatusCode)
	}
	if v != nil {
		return json.Unmarshal(body, v)
	}
	return nil
}

// GetRaw performs an authenticated GET and returns the raw response body.
func (c *Client) GetRaw(path string) ([]byte, int, error) {
	req, err := http.NewRequest("GET", c.baseURL+path, nil)
	if err != nil {
		return nil, 0, err
	}
	req.Header.Set("Authorization", "Bearer "+c.token)
	req.Header.Set("Accept", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, 0, fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close() //nolint:errcheck

	body, err := io.ReadAll(resp.Body)
	return body, resp.StatusCode, err
}

// Post performs an authenticated POST request with a JSON body and decodes
// the JSON response into v (if non-nil). A longer timeout is used because
// workflow submissions can take time.
func (c *Client) Post(path string, reqBody interface{}, v interface{}) error {
	payload, err := json.Marshal(reqBody)
	if err != nil {
		return fmt.Errorf("marshalling request body: %w", err)
	}

	req, err := http.NewRequest("POST", c.baseURL+path, bytes.NewReader(payload))
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+c.token)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")

	client := &http.Client{Timeout: 60 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close() //nolint:errcheck

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("reading response: %w", err)
	}
	if resp.StatusCode >= 400 {
		var e struct {
			Error string `json:"error"`
		}
		if jsonErr := json.Unmarshal(body, &e); jsonErr == nil && e.Error != "" {
			return fmt.Errorf("API error (%d): %s", resp.StatusCode, e.Error)
		}
		return fmt.Errorf("API returned %d", resp.StatusCode)
	}
	if v != nil {
		return json.Unmarshal(body, v)
	}
	return nil
}

// SubmitResult is returned by workflow-submission endpoints.
type SubmitResult struct {
	WorkflowName string `json:"workflowName"`
	Namespace    string `json:"namespace"`
	RequestID    string `json:"requestId"`
	Status       string `json:"status"`
	CreatedAt    string `json:"createdAt"`
}

// WorkflowStatus represents the current state of an Argo Workflow.
type WorkflowStatus struct {
	Name       string `json:"name"`
	Phase      string `json:"phase"`
	StartedAt  string `json:"startedAt"`
	FinishedAt string `json:"finishedAt"`
	Message    string `json:"message"`
}

// ExecuteOperation submits a platform operation and returns the resulting
// workflow reference. The params map is sent directly as the JSON body.
func (c *Client) ExecuteOperation(opName string, params map[string]string) (*SubmitResult, error) {
	var result SubmitResult
	path := fmt.Sprintf("/api/v1/operations/%s/execute", opName)
	if err := c.Post(path, params, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

// PollWorkflow polls the workflow status every 5 seconds until it reaches a
// terminal phase (Succeeded, Failed, Error) or the timeout expires.
// It waits 3 seconds before the first poll to give the workflow time to appear.
func (c *Client) PollWorkflow(workflowName string, timeout time.Duration) (*WorkflowStatus, error) {
	path := fmt.Sprintf("/api/v1/workflows/%s", workflowName)
	deadline := time.Now().Add(timeout)

	// Initial delay — workflow needs time to appear in the API.
	time.Sleep(3 * time.Second)

	for {
		if time.Now().After(deadline) {
			return nil, fmt.Errorf("timed out waiting for workflow %s", workflowName)
		}

		var ws WorkflowStatus
		if err := c.Get(path, &ws); err != nil {
			fmt.Fprintf(os.Stderr, "\r  ⏳ Workflow %s — waiting...", workflowName)
			time.Sleep(5 * time.Second)
			continue
		}

		fmt.Fprintf(os.Stderr, "\r  ⏳ Workflow %s — %s...", ws.Name, ws.Phase)

		switch ws.Phase {
		case "Succeeded", "Failed", "Error":
			fmt.Fprintln(os.Stderr) // newline after carriage-return progress
			return &ws, nil
		}

		time.Sleep(5 * time.Second)
	}
}
