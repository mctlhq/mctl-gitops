// Playwright config for the web contract preview assurance harness (mctlhq/mctl-gitops#2929).
// Preview assurance only; not production conformance.
// run.sh passes WCA_OUT (a writable directory); junit.xml, results and guard.jsonl land there.
import { defineConfig } from '@playwright/test';

const out = process.env.WCA_OUT || 'assurance-out';

export default defineConfig({
  testDir: './tests',
  testMatch: /.*\.spec\.ts$/,
  outputDir: `${out}/test-results`,
  // A failure must never be retried into a pass.
  retries: 0,
  workers: 1,
  fullyParallel: false,
  timeout: 30_000,
  expect: { timeout: 3_000 },
  reporter: [['list'], ['junit', { outputFile: `${out}/junit.xml` }]],
  use: {
    browserName: 'chromium',
    screenshot: 'only-on-failure',
    trace: 'off',
    video: 'off',
  },
});
