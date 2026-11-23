// Request guard and shared test plumbing for the web contract preview assurance harness.
// Preview assurance only; not production conformance (mctlhq/mctl-gitops#2929).
//
// The guard registers a context-level route on '**/*' and aborts every request whose host is
// outside the allowlist, or whose path looks like a sensitive route (oauth, connect, manage,
// consent, callback, auth, login, ...; percent-encoding and ;params do not hide a segment). Each abort is recorded as `guard-blocked`. A test that did not
// declare a deliberate probe fails when anything was blocked, so a green run proves the
// "no request to an unexpected host" counter was zero.
import { test as base, expect, request, type Browser, type BrowserContext, type Page, type TestInfo } from '@playwright/test';
import * as crypto from 'crypto';
import * as fs from 'fs';
import * as path from 'path';

export { expect };

export const ROOT = path.resolve(__dirname, '..');
export const OUT = process.env.WCA_OUT || path.join(ROOT, 'assurance-out');
// The read-only git archive of the pinned mctl-design commit: <dir>/<version>/<sheet>.
export const DESIGN_DIR = process.env.WCA_DESIGN_DIR || '/design';

// Prefix semantics on a path segment: /authorize, /oauth2callback, /login and /connected all match.
// Over-blocking is the safe direction here; the fixtures never use such a segment.
export const SENSITIVE_SEGMENT =
  /^(oauth|oidc|auth|authorize|connect|manage|consent|callback|login|logout|signin|signup|sso|token|session)/;

/** Percent-decode until stable (a server decodes %6Fauth), lowercase, drop ;params, split into segments. */
export function pathSegments(pathname: string): string[] | null {
  let p = pathname;
  for (let i = 0; i < 8; i++) {
    let d: string;
    try { d = decodeURIComponent(p); } catch { return null; } // undecodable: caller blocks
    if (d === p) break;
    p = d;
  }
  return p.toLowerCase().replace(/\\/g, '/').split('/').map((s) => s.split(';')[0]).filter((s) => s !== '');
}

export function isSensitivePath(pathname: string): boolean {
  const segs = pathSegments(pathname);
  return segs === null || segs.some((s) => SENSITIVE_SEGMENT.test(s));
}
const NON_NETWORK = new Set(['data:', 'blob:', 'about:']);

export interface Pins {
  fixture_hosts: string[];
  mctl_design?: { css_version: string; also_verified_versions?: string[];
                  sheets?: Record<string, Record<string, { sha256: string }>> };
  sites: Array<{ name: string; mode: string; breakpoint: number | null; not_run_reason?: string; image: string | null;
                 selectors?: Record<string, string>; expected_blocked?: string[] }>;
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
  if (isSensitivePath(u.pathname)) return { allow: false, reason: 'sensitive-path' };
  return { allow: true };
}

// ---------------------------------------------------------------------------------------------
// Substituted hosts. A consumer page references the design sheets on the production CDN host and web
// fonts on a third-party host. Neither is reachable (the network is internal) and neither is a fixture
// host, so the page would render unstyled and every layout assertion would fail for a harness reason.
// These two kinds of request are answered locally instead of being sent anywhere:
//   * DESIGN_HOST /<pinned version>/<sheet>.css  -> the pinned mctl-design bytes under WCA_DESIGN_DIR
//     (the same bytes whose sha-256 pins.json records; nothing else on that host is answered)
//   * FONT_HOSTS (GET only)                        -> an empty response, so web fonts never load
// Everything else on those hosts is blocked like any other non-allowlisted host. Each answered
// request is counted per host as `substituted` in the guard log and never as a request that reached
// the host: the run proves "nothing left the network", not "nothing was requested".
export const DESIGN_HOST = 'ui.mctl.ai';
export const FONT_HOSTS = new Set(['fonts.googleapis.com', 'fonts.gstatic.com']);
const DESIGN_SHEETS = new Set(['mctl.css', 'global.css', 'prose.css', 'site.css']);
const DESIGN_PATH = /^\/(\d+\.\d+\.\d+)\/([a-z]+\.css)$/;

export type Substitution =
  | { kind: 'design'; version: string; sheet: string }
  | { kind: 'font'; host: string }
  | { kind: 'deny'; reason: 'design-path-not-pinned' | 'substituted-host-refused' };

/** null: not a substituted host, the ordinary allowlist decides. No percent-decoding on purpose: an
 *  encoded or dotted path simply does not match the one accepted shape and is denied. */
export function substitution(rawUrl: string, method: string, versions: string[]): Substitution | null {
  let u: URL;
  try { u = new URL(rawUrl); } catch { return null; }
  const design = u.hostname === DESIGN_HOST;
  if (!design && !FONT_HOSTS.has(u.hostname)) return null;
  if (method !== 'GET') return { kind: 'deny', reason: 'substituted-host-refused' };
  if (!design) return u.protocol === 'https:' ? { kind: 'font', host: u.hostname } : { kind: 'deny', reason: 'substituted-host-refused' };
  if (u.protocol !== 'https:' || u.port !== '' || u.username !== '' || u.password !== '') {
    return { kind: 'deny', reason: 'design-path-not-pinned' };
  }
  const m = DESIGN_PATH.exec(u.pathname);
  if (!m || !versions.includes(m[1]) || !DESIGN_SHEETS.has(m[2])) return { kind: 'deny', reason: 'design-path-not-pinned' };
  return { kind: 'design', version: m[1], sheet: m[2] };
}

export function pinnedDesignVersions(): string[] {
  const d = loadPins().mctl_design;
  return d ? [d.css_version, ...(d.also_verified_versions ?? [])] : [];
}

export type SheetLoad = { ok: true; body: Buffer } | { ok: false; reason: 'design-file-missing' | 'design-file-mismatch' | 'design-file-unpinned' };

/** Serve-time check: the bytes about to be handed to a page must be a regular file (never a symlink) whose
 *  sha-256 equals the one pins.json records for exactly this version and sheet. A sheet without a pin cannot
 *  be verified and is refused. */
export function loadPinnedSheet(dir: string, version: string, sheet: string,
                                sheets: Record<string, Record<string, { sha256: string }>> | undefined): SheetLoad {
  const want = sheets?.[version]?.[sheet]?.sha256;
  if (typeof want !== 'string') return { ok: false, reason: 'design-file-unpinned' };
  const file = path.join(dir, version, sheet);
  let body: Buffer;
  try {
    if (!fs.lstatSync(file).isFile()) return { ok: false, reason: 'design-file-missing' };
    body = fs.readFileSync(file);
  } catch { return { ok: false, reason: 'design-file-missing' }; }
  return crypto.createHash('sha256').update(body).digest('hex') === want ? { ok: true, body } : { ok: false, reason: 'design-file-mismatch' };
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
  /** Requests answered locally (see Substituted hosts): per host, never counted as reaching it. */
  readonly substituted: Record<string, number> = {};
  /** Requests a site is DECLARED to make to hosts the allowlist refuses (pins.json expected_blocked): still aborted,
   *  never answered, but not a failure of the test. Counted per host+path and reported. */
  readonly expectedBlocked: Record<string, number> = {};
  private expected = new Set<string>();
  private hosts = allowedHosts();
  private versions = pinnedDesignVersions();
  /** Set by a test that probes the guard on purpose; those aborts are expected. */
  probe = false;

  constructor(private browser: Browser, private info: TestInfo) {}

  /** Exact host+path entries only. Honoured solely for a host the allowlist refuses; a sensitive path, an
   *  unparseable URL or any entry that is not an exact match stays an unexpected block. */
  expectBlocked(entries: string[]): void { this.expected = new Set(entries); }

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
      const sub = substitution(url, route.request().method(), this.versions);
      if (sub) {
        if (sub.kind === 'deny') {
          this.blocked.push({ url: sanitize(url), reason: sub.reason, expected: this.probe });
          await route.abort('blockedbyclient');
          return;
        }
        const host = new URL(url).hostname;
        if (sub.kind === 'font') {
          this.substituted[host] = (this.substituted[host] || 0) + 1;
          await route.fulfill({ status: 200, contentType: 'text/css', body: '' });
          return;
        }
        // design sheet: both path parts matched a closed pattern and a closed set, and the bytes are checked
        // against the pinned sha-256 before a page ever sees them
        const loaded = loadPinnedSheet(DESIGN_DIR, sub.version, sub.sheet, loadPins().mctl_design?.sheets);
        if (!loaded.ok) {
          this.blocked.push({ url: sanitize(url), reason: loaded.reason, expected: this.probe });
          await route.abort('blockedbyclient');
          return;
        }
        const body = loaded.body;
        this.substituted[host] = (this.substituted[host] || 0) + 1;
        await route.fulfill({ status: 200, contentType: 'text/css', body, headers: { 'access-control-allow-origin': '*' } });
        return;
      }
      const d = decide(url, this.hosts);
      if (!d.allow && d.reason === 'host-not-allowlisted' && this.expected.has(sanitize(url))) {
        const key = sanitize(url);
        this.expectedBlocked[key] = (this.expectedBlocked[key] || 0) + 1;
        await route.abort('blockedbyclient');
        return;
      }
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
      test: this.info.title, hosts: this.seen, substituted: this.substituted, expected_blocked: this.expectedBlocked, blocked: this.blocked,
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
