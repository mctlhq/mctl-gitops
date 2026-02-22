package main

import (
	"os"

	"github.com/mctlhq/mctl-core/cli/mctl/cmd"
)

func main() {
	if err := cmd.Execute(); err != nil {
		os.Exit(1)
	}
}
