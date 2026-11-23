// web-asset-integrity (G1-G4) cases and the isolation guard cases for the web contract preview
// assurance harness. Preview assurance only; not production conformance (mctlhq/mctl-gitops#2929).
//
// Every test is generated from cases.json: the test title IS the case id (WCA-A-G<n>-<case>).
// Negative controls (kind negative-control) run the SAME assertion as the conformant case against
// a deliberately broken fixture; the report requires every one of them to FAIL.
import * as crypto from 'crypto';
import * as fs from 'fs';
import * as path from 'path';
import type { Page } from '@playwright/test';
import { expect, loadCases, loadPins, ROOT, test, type CaseDef, type Wca } from './guard';

const UI = 'http://ui.fixture.test:8080';
const SITE = 'http://site.fixture.test:8080';
// The read-only git archive of the pinned mctl-design commit: /design/<version>/<sheet>.
const DESIGN = process.env.WCA_DESIGN_DIR || '/design';

const sha256 = (b: Buffer) => crypto.createHash('sha256').update(b).digest('hex');
const sha384 = (b: Buffer) => 'sha384-' + crypto.createHash('sha384').update(b).digest('base64');

interface Observed { page: Page; logs: string[]; violations: () => Promise<string[]>; status: number; headers: Record<string, string> }

async function visit(wca: Wca, url: string, opts: { javaScript?: boolean; abortUi?: boolean } = {}): Promise<Observed> {
  const { page } = await wca.open({ viewport: { width: 1280, height: 800 }, javaScript: opts.javaScript ?? true });
  const logs: string[] = [];
  page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') logs.push(m.text()); });
  await page.addInitScript(() => {
    (window as any).__csp = [];
    document.addEventListener('securitypolicyviolation', (e) => (window as any).__csp.push(e.violatedDirective));
  });
  if (opts.abortUi) {
    // The stand-in "CDN" is unreachable. A route registered later wins over the guard's route.
    await page.route(`${UI}/**`, (r) => r.abort('connectionrefused'));
  }
  const resp = await page.goto(url);
  return {
    page, logs, status: resp ? resp.status() : 0, headers: resp ? resp.headers() : {},
    violations: async () => (opts.javaScript === false ? [] : await page.evaluate(() => (window as any).__csp as string[])),
  };
}

const applied = (p: Page) => p.locator('#site-header').evaluate((e) => getComputedStyle(e).position === 'sticky');

/** The conformant assertion: the sheet applied. Used by the valid case and by the controls. */
async function expectSheetApplies(o: Observed) {
  expect(await applied(o.page), `the sheet applies; console: ${o.logs.join(' | ').slice(0, 300)}`).toBe(true);
}
async function expectBlockedButReadable(o: Observed, logPattern: RegExp) {
  expect(await applied(o.page), 'the sheet must not apply').toBe(false);
  await expect(o.page.locator('#readable')).toBeVisible();
  await expect(o.page.locator('main p')).toContainText('must stay readable');
  expect(o.logs.some((l) => logPattern.test(l)), `a console message matching ${logPattern} was captured; got: ${o.logs.join(' | ').slice(0, 300)}`).toBe(true);
}

const behaviours: Record<string, (wca: Wca, c: CaseDef) => Promise<void>> = {
  async 'sha256'(wca, c) {
    const version = c.version!, sheet = c.sheet!;
    const bytes = fs.readFileSync(path.join(DESIGN, version, sheet));
    const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, c.target!), 'utf8')).versions[version][sheet];
    expect(sha256(bytes), 'archive bytes equal the manifest sha256').toBe(manifest.sha256);
    expect(sha384(bytes), 'archive bytes equal the manifest sha384').toBe(manifest.sha384);
    const pinned = (loadPins() as any).mctl_design.sheets[version][sheet];
    expect(sha256(bytes), 'archive bytes equal pins.json').toBe(pinned.sha256);
    const served = await wca.get(`${UI}/${version}/${sheet}`);
    expect(served.status).toBe(200);
    expect(sha256(served.body), 'the fixture origin serves the same bytes').toBe(manifest.sha256);
  },

  async 'sri-valid-applies'(wca) {
    await expectSheetApplies(await visit(wca, `${SITE}/assets/sri-valid.html`));
  },
  async 'sri-mismatch-blocked'(wca) {
    await expectBlockedButReadable(await visit(wca, `${SITE}/assets/sri-mismatch.html`), /integrity|digest/i);
  },
  async 'no-acao-blocked'(wca) {
    await expectBlockedButReadable(await visit(wca, `${SITE}/assets/no-acao.html`), /Access-Control-Allow-Origin|CORS/i);
  },
  async 'modeb-parity'(wca) {
    const a = await wca.get(`${UI}/0.21.0/site.css`);
    const b = await wca.get(`${SITE}/vendor/0.21.0/site.css`);
    expect(a.status).toBe(200);
    expect(b.status).toBe(200);
    expect(sha256(b.body), 'Mode B (vendored) bytes equal Mode A (CDN) bytes').toBe(sha256(a.body));
    await expectSheetApplies(await visit(wca, `${SITE}/assets/vendored.html`));
  },

  async 'cache-versioned'(wca) {
    for (const v of ['0.21.0', '0.20.2']) {
      const r = await wca.get(`${UI}/${v}/site.css`);
      expect(r.headers['cache-control'], `${v} versioned`).toBe('public, max-age=31536000, immutable');
      expect(r.headers['access-control-allow-origin'], `${v} ACAO`).toBe('*');
    }
  },
  async 'cache-floating'(wca) {
    const r = await wca.get(`${UI}/site.css`);
    expect(r.headers['cache-control']).toBe('public, max-age=3600');
    expect(r.headers['access-control-allow-origin']).toBe('*');
  },
  async 'origin-down-nojs'(wca) {
    const o = await visit(wca, `${SITE}/assets/sri-valid.html`, { javaScript: false, abortUi: true });
    expect(await applied(o.page), 'the sheet is unreachable, so it cannot apply').toBe(false);
    await expect(o.page.locator('#readable')).toBeVisible();
    await expect(o.page.locator('main p')).toContainText('must stay readable');
  },

  async 'csp-allow-applies'(wca) {
    const o = await visit(wca, `${SITE}/csp-allow/sri-valid.html`);
    expect(o.headers['content-security-policy']).toContain('style-src');
    await expectSheetApplies(o);
    expect(await o.violations(), 'no violation under the allow policy').toEqual([]);
  },
  async 'csp-deny-blocked'(wca) {
    const o = await visit(wca, `${SITE}/csp-deny/sri-valid.html`);
    expect(o.headers['content-security-policy']).toBe("style-src 'self'");
    expect(await applied(o.page), 'the sheet must not apply').toBe(false);
    await expect(o.page.locator('#readable')).toBeVisible();
    expect((await o.violations()).join(',')).toContain('style-src');
  },

  async 'exact-pinning'() {
    test.skip(true, 'not run here: exact pinning is a [CODE] check of consumer manifests and consumer source is out of scope');
  },

  // negative controls: the conformant assertion against a deliberately broken page
  async 'control-sri-mismatch'(wca) { await expectSheetApplies(await visit(wca, `${SITE}/broken/sri-mismatch.html`)); },
  async 'control-no-acao'(wca) { await expectSheetApplies(await visit(wca, `${SITE}/broken/no-acao.html`)); },
  async 'control-csp-deny'(wca) { await expectSheetApplies(await visit(wca, `${SITE}/broken/csp-deny.html`)); },

  // isolation: the guard must abort these and record them as guard-blocked
  async 'guard-prod-host'(wca) {
    wca.probe = true;
    const { page } = await wca.open();
    await page.goto('https://mctl.ai/').catch(() => undefined); // aborted by the guard, never sent
    expect(wca.blocked.map((b) => `${b.reason} ${b.url}`)).toContain('host-not-allowlisted mctl.ai/');
    expect(Object.keys(wca.seen), 'no request reached any host').toEqual([]);
  },
  async 'guard-oauth-path'(wca) {
    wca.probe = true;
    const { page } = await wca.open();
    await page.goto(`${SITE}/oauth/authorize?code=probe`).catch(() => undefined);
    expect(wca.blocked.map((b) => `${b.reason} ${b.url}`)).toContain('sensitive-path site.fixture.test/oauth/authorize');
    expect(Object.keys(wca.seen), 'the allowlisted host was not contacted either').toEqual([]);
  },
};

for (const c of loadCases().filter((x) => x.id.startsWith('WCA-A-'))) {
  test(c.id, async ({ wca }) => {
    const fn = behaviours[c.behaviour as string];
    if (!fn) throw new Error(`no behaviour for ${c.id}`);
    await fn(wca, c);
  });
}
