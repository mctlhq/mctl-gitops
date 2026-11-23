// Request guard and shared test plumbing for the web contract preview assurance harness.
// Preview assurance only; not production conformance (mctlhq/mctl-gitops#2929).
//
// The guard registers a context-level route on '**/*' and aborts every request whose host is
// outside the allowlist, or whose path looks like a sensitive route (oauth, connect, manage,
// consent, callback, auth). Each abort is recorded as `guard-blocked`. A test that did not
// declare a deliberate probe fails when anything was blocked, so a green run proves the
// "no request to an unexpected host" counter was zero.
import { test as base, expect, request, type Browser, type BrowserContext, type Page, type TestInfo } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

export { expect };

export const ROOT = path.resolve(__dirname, '..');
export const OUT = process.env.WCA_OUT || path.join(ROOT, 'assurance-out');

export const SENSITIVE_PATH = /\/(oauth\d*|connect|manage|consent|callback|auth)([\/?#._-]|$)/i;
const NON_NETWORK = new Set(['data:', 'blob:', 'about:']);

export interface Pins {
  fixture_hosts: string[];
  sites: Array<{ name: string; mode: string; breakpoint: number | null; not_run_reason?: string; image: string | null;
                 selectors?: Record<string, string> }>;
}
export interface CaseDef {
  id: string; site: string; kind?: string; contract_id?: string | null; gate?: string | null;
  route_class?: string | null; viewport?: string | null; provenance?: string; exception?: string | null;
  hdr?: number; defect?: string; known_gap?: string; target?: string; version?: string; sheet?: string;
  note?: string; behaviour?: string;
}

export function loadPins(): Pins {
  return JSON.parse(fs.readFileSync(path.join(ROOT, 'pins.json'), 'utf8'));
}
export function loadCases(): CaseDef[] {
  return JSON.parse(fs.readFileSync(path.join(ROOT, 'cases.json'), 'utf8')).cases;
}

export function allowedHosts(): Set<string> {
  const hosts = new Set<string>(loadPins().fixture_hosts);
  for (const h of (process.env.WCA_ALLOW_HOSTS || '').split(',')) {
    if (h.trim()) hosts.add(h.trim());
  }
  return hosts;
}

export type Decision = { allow: true } | { allow: false; reason: 'host-not-allowlisted' | 'sensitive-path' | 'unparseable-url' };

export function decide(rawUrl: string, hosts: Set<string> = allowedHosts()): Decision {
  let u: URL;
  try { u = new URL(rawUrl); } catch { return { allow: false, reason: 'unparseable-url' }; }
  if (NON_NETWORK.has(u.protocol)) return { allow: true };
  if (!hosts.has(u.hostname)) return { allow: false, reason: 'host-not-allowlisted' };
  if (SENSITIVE_PATH.test(u.pathname)) return { allow: false, reason: 'sensitive-path' };
  return { allow: true };
}

/** Host and path only: a query string, fragment or userinfo never reaches a log or a result. */
export function sanitize(rawUrl: string): string {
  try { const u = new URL(rawUrl); return u.hostname + u.pathname; } catch { return '[unparseable-url]'; }
}

interface Blocked { url: string; reason: string; expected: boolean }

export interface OpenOpts {
  viewport?: { width: number; height: number };
  javaScript?: boolean;
  reducedMotion?: 'reduce' | 'no-preference';
}

export class Wca {
  private contexts: BrowserContext[] = [];
  readonly blocked: Blocked[] = [];
  readonly seen: Record<string, number> = {};
  private hosts = allowedHosts();
  /** Set by a test that probes the guard on purpose; those aborts are expected. */
  probe = false;

  constructor(private browser: Browser, private info: TestInfo) {}

  private note(url: string, d: Decision): void {
    if (d.allow) {
      let h = '';
      try { h = new URL(url).hostname; } catch { /* non-network */ }
      if (h) this.seen[h] = (this.seen[h] || 0) + 1;
    } else {
      this.blocked.push({ url: sanitize(url), reason: d.reason, expected: this.probe });
    }
  }

  async open(opts: OpenOpts = {}): Promise<{ page: Page; context: BrowserContext }> {
    const context = await this.browser.newContext({
      viewport: opts.viewport ?? { width: 1280, height: 800 },
      javaScriptEnabled: opts.javaScript ?? true,
      reducedMotion: opts.reducedMotion ?? 'no-preference',
      serviceWorkers: 'block',
    });
    await context.route('**/*', async (route) => {
      const url = route.request().url();
      const d = decide(url, this.hosts);
      this.note(url, d);
      if (d.allow) await route.continue();
      else await route.abort('blockedbyclient');
    });
    this.contexts.push(context);
    return { page: await context.newPage(), context };
  }

  /** Node-side GET through the same allowlist (an APIRequestContext bypasses page routes). */
  async get(url: string): Promise<{ status: number; headers: Record<string, string>; body: Buffer }> {
    const d = decide(url, this.hosts);
    this.note(url, d);
    if (!d.allow) throw new Error(`guard-blocked (${d.reason}): ${sanitize(url)}`);
    const ctx = await request.newContext();
    try {
      const r = await ctx.get(url);
      return { status: r.status(), headers: r.headers(), body: await r.body() };
    } finally {
      await ctx.dispose();
    }
  }

  async finish(): Promise<void> {
    for (const c of this.contexts) await c.close().catch(() => undefined);
    fs.mkdirSync(OUT, { recursive: true });
    fs.appendFileSync(path.join(OUT, 'guard.jsonl'), JSON.stringify({
      test: this.info.title, hosts: this.seen, blocked: this.blocked,
      unexpected_blocked: this.blocked.filter((b) => !b.expected).length,
    }) + '\n');
  }

  unexpected(): Blocked[] { return this.blocked.filter((b) => !b.expected); }
}

export const test = base.extend<{ wca: Wca }>({
  wca: async ({ browser }, use, testInfo) => {
    const w = new Wca(browser, testInfo);
    await use(w);
    await w.finish();
    // A request the guard had to abort that no test asked for is a failure of the run.
    if (w.unexpected().length) {
      throw new Error('guard-blocked unexpected request(s): ' + JSON.stringify(w.unexpected()));
    }
  },
});
