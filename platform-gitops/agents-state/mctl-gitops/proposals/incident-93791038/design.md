# Design: incident-93791038

## Diagnosis
In workflow mctl-agents-shepherd-f9979a5a the shepherd, shepherd-fallback and commit steps all failed in their clone-gitops init with "Error (exit code 128)" within about 80 seconds. Exit 128 is a git fatal error (clone/auth/network), and its recurrence across three independent pods suggests a transient failure on the gitops remote or credentials at that moment, not a problem in the shepherd logic. The summary text "post-deploy-verify did not complete" is a consequence: the workflow failed before verification ran. Earlier incidents with the same summary (for example incident-93785218) are the same family.

## Proposed Fix
In the workflow template that defines the clone-gitops step (used by run-shepherd and commit-and-push in the mctl-agents shepherd workflow template under mctl-gitops), wrap the git clone in a retry loop: up to 3 attempts with 10s, 30s backoff, and print the git stderr on each failure so the cause is recorded in the archived logs. Do not change credential references or secret values.

## Scope
Minimal. Only the clone-gitops step of the shared workflow templates.

## Confidence: LOW
The git error message itself was not retrievable, only the exit code; verify the clone failure cause (auth versus network versus rate limit) before applying.
