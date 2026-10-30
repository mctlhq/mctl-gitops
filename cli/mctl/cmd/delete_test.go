package cmd

import "testing"

// retire-service is RequiresConfirm in mctl-api; without confirm=yes the
// execute route answers 428 (mctl-api#866).
func TestRetireServiceInputsCarryConfirm(t *testing.T) {
	in := retireServiceInputs("team", "svc", "base-service", "true")
	if in["confirm"] != "yes" {
		t.Fatalf("confirm = %q, want %q", in["confirm"], "yes")
	}
	want := map[string]string{
		"team_name":            "team",
		"component_name":       "svc",
		"component_type":       "base-service",
		"delete_vault_secrets": "true",
	}
	for k, v := range want {
		if in[k] != v {
			t.Errorf("%s = %q, want %q", k, in[k], v)
		}
	}
}
