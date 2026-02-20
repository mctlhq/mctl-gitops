package main

import (
	"os"

	"github.com/dmitriimashkov/mctl.me/tools/mctl/cmd"
)

func main() {
	if err := cmd.Execute(); err != nil {
		os.Exit(1)
	}
}
