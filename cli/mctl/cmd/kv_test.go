package cmd

import (
	"strings"
	"testing"

	"github.com/spf13/pflag"
)

// TestEnvAndSecretFlagsKeepCommas parses the real flag sets: a comma inside a
// value must survive as data, one flag occurrence = one entry.
func TestEnvAndSecretFlagsKeepCommas(t *testing.T) {
	for _, tc := range []struct {
		name  string
		flags *pflag.FlagSet
		env   *[]string
		sec   *[]string
	}{
		{"deploy", deployCmd.Flags(), &deployEnv, &deploySecret},
		{"config", configCmd.Flags(), &configEnv, &configSecret},
	} {
		t.Run(tc.name, func(t *testing.T) {
			*tc.env, *tc.sec = nil, nil
			t.Cleanup(func() { *tc.env, *tc.sec = nil, nil })
			err := tc.flags.Parse([]string{
				"--env", "ALLOWED_HOSTS=a.example,b.example",
				"--env", "PORT=3000",
				"--secret", "DSN=host=db,port=5432",
			})
			if err != nil {
				t.Fatal(err)
			}
			env, err := joinKV("env", *tc.env)
			if err != nil || env != "ALLOWED_HOSTS=a.example,b.example\nPORT=3000" {
				t.Errorf("env_vars = %q, %v", env, err)
			}
			sec, err := joinKV("secret", *tc.sec)
			if err != nil || sec != "DSN=host=db,port=5432" {
				t.Errorf("secret_env_vars = %q, %v", sec, err)
			}
		})
	}
}

func TestJoinKVRefusesWhatTheWorkflowWouldSplit(t *testing.T) {
	for _, bad := range []string{"K=a\nINJECTED=1", "K=a\rb", "NOEQUALS", "=value"} {
		if got, err := joinKV("env", []string{bad}); err == nil {
			t.Errorf("joinKV(%q) = %q, want an error", bad, got)
		}
	}
	// The error must not echo a secret value.
	if _, err := joinKV("secret", []string{"API_KEY=sk-1\n2"}); err == nil || strings.Contains(err.Error(), "sk-1") {
		t.Errorf("err = %v, want an error that names the key only", err)
	}
}

// A malformed --secret entry is usually the bare value: it must not be echoed.
func TestJoinKVDoesNotEchoMalformedSecret(t *testing.T) {
	for _, bad := range []string{"sk-live-123", "=sk-live-123"} {
		_, err := joinKV("secret", []string{bad})
		if err == nil || strings.Contains(err.Error(), "sk-live-123") {
			t.Errorf("joinKV(secret, %q) err = %v, want an error without the value", bad, err)
		}
	}
}
