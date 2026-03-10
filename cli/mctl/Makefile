VERSION ?= $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")
LDFLAGS := -ldflags "-X github.com/mctlhq/mctl-gitops/tools/mctl/cmd.version=$(VERSION)"

.PHONY: build install clean

build:
	go build $(LDFLAGS) -o mctl .

install:
	go install $(LDFLAGS) .

clean:
	rm -f mctl
