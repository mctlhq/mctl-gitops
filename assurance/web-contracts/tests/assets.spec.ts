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
import * as os from 'os';
import { DESIGN_DIR, decide, expect, loadCases, loadPinnedSheet, loadPins, pinnedDesignVersions, ROOT, substitution, test, type CaseDef, type Wca } from './guard';

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
  async 'guard-design-host'(wca) {
    const V = pinnedDesignVersions();
    expect(V, 'pinned versions come from pins.json').toEqual([loadPins().mctl_design!.css_version, ...(loadPins().mctl_design!.also_verified_versions ?? [])]);
    expect(V.length).toBeGreaterThan(0);
    // pure decision table
    const acc = (u: string, m = 'GET') => substitution(u, m, V);
    expect(acc('https://ui.mctl.ai/0.20.2/site.css')).toEqual({ kind: 'design', version: '0.20.2', sheet: 'site.css' });
    expect(acc('https://ui.mctl.ai/0.21.0/mctl.css?cb=1')).toEqual({ kind: 'design', version: '0.21.0', sheet: 'mctl.css' });
    for (const u of ['http://ui.mctl.ai/0.20.2/site.css', 'https://ui.mctl.ai:8443/0.20.2/site.css',
                     'https://a:b@ui.mctl.ai/0.20.2/site.css', 'https://ui.mctl.ai/0.0.1/site.css',
                     'https://ui.mctl.ai/0.20.2/evil.css', 'https://ui.mctl.ai/0.20.2/SITE.CSS',
                     'https://ui.mctl.ai/0.20.2/site.css/', 'https://ui.mctl.ai/0.20.2/site.css.map',
                     'https://ui.mctl.ai/0.20.2/oauth/x.css', 'https://ui.mctl.ai/0.20.2/%2fsite.css',
                     'https://ui.mctl.ai//0.20.2/site.css', 'https://ui.mctl.ai/', 'https://ui.mctl.ai/site.css']) {
      expect(acc(u), `denied: ${u}`).toMatchObject({ kind: 'deny', reason: 'design-path-not-pinned' });
    }
    expect(acc('https://ui.mctl.ai/0.20.2/site.css', 'POST'), 'only GET').toMatchObject({ kind: 'deny', reason: 'substituted-host-refused' });
    for (const u of ['https://ui.mctl.ai.evil.test/0.20.2/site.css', 'https://ui.mctl.ai./0.20.2/site.css',
                     'https://sub.ui.mctl.ai/0.20.2/site.css', 'https://xui.mctl.ai/0.20.2/site.css', 'https://mctl.ai/']) {
      expect(acc(u), `ordinary allowlist decides: ${u}`).toBeNull();
    }
    // and the ordinary allowlist then refuses every one of them
    const fixtureHosts = new Set(loadPins().fixture_hosts);
    for (const u of ['https://ui.mctl.ai.evil.test/0.20.2/site.css', 'https://ui.mctl.ai./0.20.2/site.css',
                     'https://sub.ui.mctl.ai/0.20.2/site.css', 'https://xui.mctl.ai/0.20.2/site.css', 'https://mctl.ai/']) {
      expect(decide(u, fixtureHosts), `blocked end to end: ${u}`).toMatchObject({ allow: false, reason: 'host-not-allowlisted' });
    }
    // serve-time loader: missing, corrupted, symlinked and unpinned sheets are refused, the pinned one is served
    const pinned = loadPins().mctl_design!.sheets!;
    const v0 = V[0];
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'wca-design-'));
    try {
      fs.mkdirSync(path.join(tmp, v0));
      expect(loadPinnedSheet(tmp, v0, 'site.css', pinned), 'absent file').toEqual({ ok: false, reason: 'design-file-missing' });
      const real = fs.readFileSync(path.join(DESIGN_DIR, v0, 'site.css'));
      fs.writeFileSync(path.join(tmp, v0, 'site.css'), Buffer.concat([real, Buffer.from(' ')]));
      expect(loadPinnedSheet(tmp, v0, 'site.css', pinned), 'corrupted file').toEqual({ ok: false, reason: 'design-file-mismatch' });
      fs.rmSync(path.join(tmp, v0, 'site.css'));
      fs.symlinkSync(path.join(DESIGN_DIR, v0, 'site.css'), path.join(tmp, v0, 'site.css'));
      expect(loadPinnedSheet(tmp, v0, 'site.css', pinned), 'symlink is never followed').toEqual({ ok: false, reason: 'design-file-missing' });
      fs.rmSync(path.join(tmp, v0, 'site.css'));
      fs.writeFileSync(path.join(tmp, v0, 'site.css'), real);
      expect(loadPinnedSheet(tmp, v0, 'site.css', pinned)).toMatchObject({ ok: true });
      expect(loadPinnedSheet(tmp, v0, 'site.css', undefined), 'no pin, no serve').toEqual({ ok: false, reason: 'design-file-unpinned' });
      expect(loadPinnedSheet(tmp, v0, 'extra.css', pinned), 'sheet without a pin').toEqual({ ok: false, reason: 'design-file-unpinned' });
    } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
    expect(acc('https://fonts.googleapis.com/css2?family=Onest')).toEqual({ kind: 'font', host: 'fonts.googleapis.com' });
    expect(acc('http://fonts.googleapis.com/css2')).toMatchObject({ kind: 'deny' });
    expect(acc('https://fonts.gstatic.com/s/x.woff2', 'POST')).toMatchObject({ kind: 'deny' });
    expect(acc('https://fonts.googleapis.com.evil.test/css2')).toBeNull();
    // live: the browser gets the pinned bytes, and nothing reaches the host
    const { page } = await wca.open();
    await page.goto(`${SITE}/header/reference.html`);
    const sheets = loadPins().mctl_design!.sheets!;
    for (const v of V) {
      expect(Object.keys(sheets[v]).sort(), `all four sheets are pinned for ${v}`).toEqual(['global.css', 'mctl.css', 'prose.css', 'site.css']);
      for (const sheet of Object.keys(sheets[v])) {
        const got = await page.evaluate(async (u) => {
          const r = await fetch(u); return { status: r.status, body: Array.from(new Uint8Array(await r.arrayBuffer())) };
        }, `https://ui.mctl.ai/${v}/${sheet}`);
        expect(got.status).toBe(200);
        expect(sha256(Buffer.from(got.body)), `${v}/${sheet} is the pinned sheet`).toBe(sheets[v][sheet].sha256);
      }
    }
    const fontLoaded = await page.evaluate(() => new Promise<boolean>((res) => {
      const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = 'https://fonts.googleapis.com/css2?family=Onest';
      l.onload = () => res(true); l.onerror = () => res(false); document.head.appendChild(l);
    }));
    expect(fontLoaded, 'the font stylesheet request is answered with an empty sheet').toBe(true);
    expect(wca.substituted['ui.mctl.ai']).toBe(V.reduce((n, v) => n + Object.keys(sheets[v]).length, 0));
    expect(wca.substituted['fonts.googleapis.com']).toBe(1);
    expect(wca.blocked, 'nothing was blocked so far').toEqual([]);
    expect(Object.keys(wca.seen).filter((h) => h.includes('mctl.ai') || h.includes('google')), 'no request reached those hosts').toEqual([]);
    // live: a path outside the pin is blocked, not answered
    wca.probe = true;
    const unpinnedV = '0.0.1';
    expect(V).not.toContain(unpinnedV);
    const unpinned = await page.evaluate((u) => fetch(u).then(() => 'answered', () => 'failed'), `https://ui.mctl.ai/${unpinnedV}/site.css`);
    expect(unpinned).toBe('failed');
    expect(wca.blocked.map((b) => `${b.reason} ${b.url}`)).toContain(`design-path-not-pinned ui.mctl.ai/${unpinnedV}/site.css`);
  },
  async 'guard-expected-blocked'(wca) {
    // a declared host+path is still aborted and never answered, and only that exact entry is tolerated
    const { page } = await wca.open();
    await page.goto(`${SITE}/header/reference.html`);
    wca.expectBlocked(['stats.example.test/insights.js', 'site.fixture.test/oauth/authorize']);
    const probe = (u: string) => page.evaluate((x) => fetch(x, { mode: 'no-cors' }).then(() => 'answered', () => 'failed'), u);
    expect(await probe('https://stats.example.test/insights.js?cb=1'), 'a declared request is aborted, not answered').toBe('failed');
    expect(wca.expectedBlocked).toEqual({ 'stats.example.test/insights.js': 1 });
    expect(wca.blocked, 'a declared block is not an unexpected one').toEqual([]);
    wca.probe = true; // everything below must be recorded as a block no case declared
    expect(await probe('https://stats.example.test/other.js')).toBe('failed');                 // same host, other path
    expect(await probe('https://other.example.test/insights.js')).toBe('failed');              // same path, other host
    expect(await probe(`${SITE}/oauth/authorize`)).toBe('failed');                              // declared, but an allowlisted host: sensitive-path wins
    expect(wca.blocked.map((b) => `${b.reason} ${b.url}`).sort()).toEqual([
      'host-not-allowlisted other.example.test/insights.js',
      'host-not-allowlisted stats.example.test/other.js',
      'sensitive-path site.fixture.test/oauth/authorize',
    ]);
    expect(wca.expectedBlocked, 'the declared count did not grow').toEqual({ 'stats.example.test/insights.js': 1 });
    expect(Object.keys(wca.seen).filter((h) => h.includes('example.test')), 'nothing reached those hosts').toEqual([]);
  },
  async 'guard-oauth-path'(wca) {
    // pure decision table: encodings, params and sibling auth routes must not slip past the guard
    const hosts = new Set(['site.fixture.test']);
    for (const p of ['/authorize', '/oauth2callback', '/login', '/signin', '/logout', '/connected', '/%6Fauth/x',
                     '/%256Fauth/x', '/oauth;a=1/x', '/a/b/OAuth/x', '/api/auth', '/oauth/authorize']) {
      expect(decide(`http://site.fixture.test${p}`, hosts), `sensitive path ${p}`).toMatchObject({ allow: false, reason: 'sensitive-path' });
    }
    for (const p of ['/', '/header/reference.html', '/0.21.0/site.css', '/broken/no-acao.html', '/healthz']) {
      expect(decide(`http://site.fixture.test${p}`, hosts), `fixture path ${p}`).toEqual({ allow: true });
    }
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
