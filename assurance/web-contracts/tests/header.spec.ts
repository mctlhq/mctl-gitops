// HDR-1..16 header cases for the web contract preview assurance harness.
// Preview assurance only; not production conformance (mctlhq/mctl-gitops#2929).
//
// Every test is generated from cases.json (the single catalogue): the test title IS the case id,
// so the JUnit testcase name maps 1:1 to the report. Test ids are
//   WCA-H-<HDR>-<site>-<routeclass>-<viewport>
// where viewport is B-1, B, 375 or 1280 and B is the site's own breakpoint (never a common one).
//
// Rules that keep the results honest:
//  * an exception case (EX-1/2/3) asserts the documented equivalent behaviour; the report maps its
//    pass to EXCEPTION-PENDING, never PASS;
//  * a site with breakpoint null yields a skip ("breakpoint unknown") for its B-1/B cases;
//  * a sensitive route class never targets a consumer, only fixtures;
//  * a consumer whose pins mode is not "image" is skipped with its recorded reason;
//  * `known_gap` (cases.json) turns the failure of ONE named assertion (the Enter step of HDR-4, the
//    checked/hidden-state checks after growing past B in HDR-11) of a fixture-pattern limitation that
//    the contract registers no exception for into a skip carrying the observed reason; every other
//    failure, including earlier steps of the same case, stays a FAIL.
import AxeBuilder from '@axe-core/playwright';
import * as fs from 'fs';
import * as path from 'path';
import type { Page } from '@playwright/test';
import { expect, loadCases, loadPins, OUT, sanitize, test, type CaseDef, type Wca } from './guard';

/** Thrown only at the one assertion a catalogued known_gap describes; anything else stays a FAIL. */
class KnownGap extends Error {}
async function atGap(c: CaseDef, fn: () => Promise<void>): Promise<void> {
  if (!c.known_gap) return fn();
  try { await fn(); } catch (e) { throw new KnownGap(String((e as Error).message).split('\n')[0]); }
}

const BASE = 'http://site.fixture.test:8080';
const HEIGHT = 800;

// `routes` selects the links that are in-app ROUTES (a client navigation moves the current marker). It is declared,
// never guessed from an href: a section anchor or an external link is not a route, and HDR-14's route-change step
// is only meaningful for a site that has route links.
interface Sel { header: string; nav: string; links: string; toggle: string; clickToggle: string; outside: string; routes?: string }
class NoRouteLinks extends Error {}
interface Target { url: string; bp: number; kind: 'button' | 'checkbox'; sel: Sel }

const BUTTON_SEL: Sel = {
  header: '#site-header', nav: '#site-nav', links: '#site-nav a', routes: '#site-nav a', toggle: '.mctl-site-burger',
  clickToggle: '.mctl-site-burger', outside: '#outside-link',
};
const CHECKBOX_SEL: Sel = { ...BUTTON_SEL, toggle: '#nav-toggle', clickToggle: 'label.cb-label' };

const FIXTURES: Record<string, Target> = {
  'fixture-reference': { url: `${BASE}/header/reference.html`, bp: 768, kind: 'button', sel: BUTTON_SEL },
  'fixture-reference-wide': { url: `${BASE}/header/reference-wide.html`, bp: 981, kind: 'button', sel: BUTTON_SEL },
  'fixture-checkbox': { url: `${BASE}/header/checkbox.html`, bp: 768, kind: 'checkbox', sel: CHECKBOX_SEL },
  'fixture-reset': { url: `${BASE}/header/reset.html`, bp: 768, kind: 'button', sel: BUTTON_SEL },
};

function viewportWidth(vp: string, bp: number): number {
  if (vp === 'B-1') return bp - 1;
  if (vp === 'B') return bp;
  const n = parseInt(vp, 10);
  if (!Number.isFinite(n)) throw new Error(`unknown viewport ${vp}`);
  return n;
}

// ------------------------------------------------------------------ helpers
const nav = (p: Page, t: Target) => p.locator(t.sel.nav);
const toggle = (p: Page, t: Target) => p.locator(t.sel.toggle);

async function load(wca: Wca, t: Target, width: number, extra: { javaScript?: boolean; reducedMotion?: 'reduce' | 'no-preference' } = {}) {
  const { page } = await wca.open({ viewport: { width, height: HEIGHT }, ...extra });
  await page.goto(t.url);
  if (extra.javaScript !== false && width < t.bp) {
    // The burger is added by script, so the drawer rules start matching after load and the panel
    // leaves through a delayed visibility transition: wait for narrow-closed to settle first.
    await expect(nav(page, t)).toBeHidden();
  }
  return page;
}

async function clickToggle(p: Page, t: Target) { await p.locator(t.sel.clickToggle).click(); }

async function expectOpen(p: Page, t: Target, width: number) {
  await expect(nav(p, t)).toBeVisible();
  await expect.poll(async () => {
    const b = await nav(p, t).boundingBox();
    return !!b && b.x >= 0 && b.x + b.width <= width + 1;
  }, { message: 'panel settled inside the viewport' }).toBe(true);
}
async function expectClosed(p: Page, t: Target) { await expect(nav(p, t)).toBeHidden(); }

async function openPanel(p: Page, t: Target, width: number) {
  await clickToggle(p, t);
  await expectOpen(p, t, width);
}

async function activeInNav(p: Page, t: Target): Promise<boolean> {
  return p.evaluate((sel) => !!document.activeElement && !!document.querySelector(sel)?.contains(document.activeElement), t.sel.nav);
}

async function tabUntil(p: Page, target: ReturnType<Page['locator']>, max = 8) {
  for (let i = 0; i < max; i++) {
    await p.keyboard.press('Tab');
    if (await target.evaluate((el) => el === document.activeElement).catch(() => false)) return;
  }
  throw new Error('keyboard focus never reached the expected element');
}

async function outline(loc: ReturnType<Page['locator']>) {
  return loc.evaluate((e) => { const s = getComputedStyle(e); return { style: s.outlineStyle, width: parseFloat(s.outlineWidth) }; });
}
const hasRing = (o: { style: string; width: number }) => o.style !== 'none' && o.width > 0;

/** The transitions and animations that would actually RUN on the panel and on the toggle's icon lines (its ::before
 *  and ::after): exactly the selectors of the site.css prefers-reduced-motion block that the contract names as the
 *  implementation. The toggle element itself is not measured: its default transition-property is `all`, so any global
 *  duration reset would count a change that is not the panel opening. A transition counts when its property is not
 *  none and duration plus delay is above zero, an animation when its name is not none and its duration is above zero. transition-property: none means nothing runs at any duration,
 *  so a global `transition-duration: 0.01ms !important` reset on top of `transition: none` is correctly not counted. */
async function running(p: Page, t: Target): Promise<string[]> {
  return p.evaluate(([navSel, togSel]) => {
    const out: string[] = [];
    const num = (x: string) => parseFloat(x) || 0;
    const add = (el: Element | null, label: string, pseudo?: string) => {
      if (!el) return;
      const cs = getComputedStyle(el, pseudo);
      const props = cs.transitionProperty.split(',').map((x) => x.trim());
      const durs = cs.transitionDuration.split(',').map(num);
      const dels = cs.transitionDelay.split(',').map(num);
      props.forEach((prop, i) => {
        const d = durs[i % durs.length], dl = dels[i % dels.length];
        if (prop !== 'none' && d + dl > 0) out.push(`${label}${pseudo || ''} transition ${prop} ${d}s+${dl}s`);
      });
      const names = cs.animationName.split(',').map((x) => x.trim());
      const ad = cs.animationDuration.split(',').map(num);
      names.forEach((name, i) => { if (name !== 'none' && ad[i % ad.length] > 0) out.push(`${label}${pseudo || ''} animation ${name} ${ad[i % ad.length]}s`); });
    };
    add(document.querySelector(navSel), 'nav');
    const tog = document.querySelector(togSel);
    add(tog, 'toggle', '::before'); add(tog, 'toggle', '::after');
    return out;
  }, [t.sel.nav, t.sel.toggle]);
}

// ------------------------------------------------------------------ behaviours
type Ctx = { wca: Wca; t: Target; width: number; narrow: boolean; c: CaseDef };
const behaviours: Record<number, (x: Ctx) => Promise<void>> = {
  1: async ({ wca, t, width, narrow }) => {
    const p = await load(wca, t, width);
    const navs = p.locator(`${t.sel.header} nav`);
    await expect(navs).toHaveCount(1);
    const label = await navs.first().evaluate((n) => n.getAttribute('aria-label')
      || (n.getAttribute('aria-labelledby') ? document.getElementById(n.getAttribute('aria-labelledby')!)?.textContent : '') || '');
    expect(label.trim(), 'navigation landmark has an accessible name').not.toBe('');
    const axe = async () => (await new AxeBuilder({ page: p }).include(t.sel.header).analyze()).violations.map((v) => `${v.id}:${v.nodes.length}`);
    if (narrow) {
      expect(await axe(), 'axe, narrow-closed').toEqual([]);
      await openPanel(p, t, width);
    }
    // the header region's landmark (AC-1: "inspect the header navigation landmark"); a named landmark elsewhere on the
    // page, in content or the footer, is not the header's
    await expect(p.locator(t.sel.header).getByRole('navigation', { name: /\S/ })).toHaveCount(1);
    expect(await axe(), 'axe on the header region').toEqual([]);
  },

  2: async ({ wca, t, width }) => {
    const p = await load(wca, t, width);
    const role = t.kind === 'checkbox' ? 'checkbox' : 'button';
    // the toggle itself: the control selected as the toggle has the role and a name (not every named button on the page)
    await expect(p.getByRole(role, { name: /\S/ }).and(p.locator(t.sel.toggle))).toHaveCount(1);
    await toggle(p, t).focus();
    await expect(toggle(p, t)).toBeFocused();
  },

  3: async ({ wca, t, width }) => {
    const p = await load(wca, t, width);
    await expectClosed(p, t);
    await openPanel(p, t, width);
    await clickToggle(p, t);
    await expectClosed(p, t);
  },

  4: async ({ wca, t, width, c }) => {
    const p = await load(wca, t, width);
    await toggle(p, t).focus();
    const cycle = async (key: string) => {
      await p.keyboard.press(key);
      await expectOpen(p, t, width);
      await p.keyboard.press(key);
      await expectClosed(p, t);
    };
    // Space first and outside the gap wrapper: a broken toggle is never mistaken for the Enter gap.
    await cycle('Space');
    await atGap(c, () => cycle('Enter'));
  },

  5: async ({ wca, t, width }) => {
    const p = await load(wca, t, width);
    if (t.kind === 'checkbox') {
      // EX-1 documented equivalent: the checkbox reports checked/unchecked in step with the panel.
      await expect(toggle(p, t)).not.toBeChecked();
      await openPanel(p, t, width);
      await expect(toggle(p, t)).toBeChecked();
      return;
    }
    await expect(toggle(p, t)).toHaveAttribute('aria-expanded', 'false');
    await openPanel(p, t, width);
    await expect(toggle(p, t)).toHaveAttribute('aria-expanded', 'true');
  },

  6: async ({ wca, t, width }) => {
    const p = await load(wca, t, width);
    if (t.kind === 'checkbox') {
      // EX-1 documented equivalent: a label bound to the checkbox (no aria-controls exists).
      const id = await toggle(p, t).getAttribute('id');
      await expect(p.locator(`label[for="${id}"]`).first()).toBeAttached();
      return;
    }
    const controls = await toggle(p, t).getAttribute('aria-controls');
    expect(controls, 'aria-controls present').toBeTruthy();
    const same = await p.evaluate(([id, sel]) => document.getElementById(id as string) === document.querySelector(sel as string), [controls, t.sel.nav]);
    expect(same, 'aria-controls points at the panel').toBe(true);
  },

  7: async ({ wca, t, width, c }) => {
    const p = await load(wca, t, width);
    // narrow-closed: the panel links are skipped and focus is never trapped
    await toggle(p, t).focus();
    let reached = false;
    for (let i = 0; i < 4 && !reached; i++) {
      await p.keyboard.press('Tab');
      expect(await activeInNav(p, t), 'closed panel links must not take focus').toBe(false);
      reached = await p.locator(t.sel.outside).evaluate((el) => el === document.activeElement);
    }
    expect(reached, 'Tab leaves the header while closed').toBe(true);
    // narrow-open: the toggle, then the panel links in DOM order
    await toggle(p, t).focus();
    await p.keyboard.press(t.kind === 'checkbox' ? 'Space' : 'Enter');
    await expectOpen(p, t, width);
    const hrefs = await p.locator(t.sel.links).evaluateAll((as) => as.map((a) => a.textContent!.trim()));
    // the one assertion a catalogued known_gap names (a header whose toggle follows the panel in DOM order)
    await atGap(c, async () => {
      const seen: string[] = [];
      for (let i = 0; i < hrefs.length; i++) {
        await p.keyboard.press('Tab');
        seen.push(await p.evaluate(() => (document.activeElement?.textContent || '').trim()));
      }
      expect(seen).toEqual(hrefs);
    });
  },

  8: async ({ wca, t, width }) => {
    const p = await load(wca, t, width);
    if (t.kind === 'checkbox') {
      // EX-2 documented equivalent: no Escape without JS; the keyboard user re-toggles to dismiss.
      await toggle(p, t).focus();
      await p.keyboard.press('Space');
      await expectOpen(p, t, width);
      await p.keyboard.press('Space');
      await expectClosed(p, t);
      await expect(toggle(p, t)).toBeFocused();
      return;
    }
    await openPanel(p, t, width);
    // focus inside the open panel is a precondition set directly: reaching it by Tab from the toggle depends on
    // the DOM order HDR-7 covers, and HDR-8/12 only require where focus goes after the close
    await p.locator(t.sel.links).first().focus();
    expect(await activeInNav(p, t), 'precondition: focus is inside the open panel').toBe(true);
    await p.keyboard.press('Escape');
    await expectClosed(p, t);
    await expect(toggle(p, t)).toBeFocused();
  },

  9: async ({ wca, t, width }) => {
    const p = await load(wca, t, width);
    await openPanel(p, t, width);
    await p.mouse.click(10, 400); // left of the drawer: the scrim
    await expectClosed(p, t);
  },

  10: async ({ wca, t, width }) => {
    const p = await load(wca, t, width);
    await openPanel(p, t, width);
    const before = p.url();
    await p.locator(t.sel.links).nth(1).click();
    await expect.poll(() => p.url()).not.toBe(before);
    await expectClosed(p, t);
  },

  11: async ({ wca, t, width, c }) => {
    const p = await load(wca, t, width);
    await openPanel(p, t, width);
    await p.setViewportSize({ width: t.bp, height: HEIGHT });
    await expect(nav(p, t)).toBeVisible();
    expect(await nav(p, t).evaluate((e) => getComputedStyle(e).position), 'inline nav, not the fixed drawer').not.toBe('fixed');
    await expect(p.locator(t.sel.clickToggle)).toBeHidden();
    // the checkbox's :checked state cannot be cleared by CSS alone: that, and the panel reopening on
    // return to narrow, are the two observations the HDR-11 known_gap describes
    if (t.kind === 'checkbox') await atGap(c, async () => { await expect(toggle(p, t)).not.toBeChecked(); });
    else await expect(toggle(p, t)).toHaveAttribute('aria-expanded', 'false');
    await p.setViewportSize({ width, height: HEIGHT });
    await atGap(c, () => expectClosed(p, t)); // no hidden open state returns
  },

  12: async ({ wca, t, width }) => {
    const p = await load(wca, t, width);
    if (t.kind === 'checkbox') {
      // EX-2 documented equivalent: re-toggling closes it and focus stays on the toggle.
      await toggle(p, t).focus();
      await p.keyboard.press('Space');
      await expectOpen(p, t, width);
      await p.keyboard.press('Space');
      await expectClosed(p, t);
      await expect(toggle(p, t)).toBeFocused();
      return;
    }
    await openPanel(p, t, width);
    // focus inside the open panel is a precondition set directly: reaching it by Tab from the toggle depends on
    // the DOM order HDR-7 covers, and HDR-8/12 only require where focus goes after the close
    await p.locator(t.sel.links).first().focus();
    expect(await activeInNav(p, t), 'precondition: focus is inside the open panel').toBe(true);
    await p.keyboard.press('Escape');
    await expectClosed(p, t);
    expect(await p.evaluate((sel) => document.activeElement === document.querySelector(sel), t.sel.toggle),
      'focus is on the toggle, not lost to body').toBe(true);
    // Close initiated from inside the panel (a link click): focus must be the toggle or the
    // navigation target, never body.
    await openPanel(p, t, width);
    const before = p.url();
    await p.locator(t.sel.links).nth(1).click();
    await expect.poll(() => p.url()).not.toBe(before);
    await expectClosed(p, t);
    const where = await p.evaluate((sel) => {
      const a = document.activeElement;
      if (!a || a === document.body || a === document.documentElement) return 'body';
      if (a === document.querySelector(sel)) return 'toggle';
      return a.id && a.id === location.hash.slice(1) ? 'target' : 'other:' + a.tagName;
    }, t.sel.toggle);
    expect(['toggle', 'target'], `after a link-initiated close focus is ${where}, not on the toggle or the target`).toContain(where);
  },

  13: async ({ wca, t, width, narrow }) => {
    const p = await load(wca, t, width);
    if (narrow) {
      // Tab from the top of the page until the toggle holds focus: other controls (a theme switch) may sit before it
      await p.locator('body').press('Tab');
      await tabUntil(p, toggle(p, t));
      await expect(toggle(p, t)).toBeFocused();
      const ring = t.kind === 'checkbox' ? p.locator(t.sel.clickToggle) : toggle(p, t);
      expect(hasRing(await outline(ring)), 'focus indicator on the toggle').toBe(true);
      await p.keyboard.press(t.kind === 'checkbox' ? 'Space' : 'Enter');
      await expectOpen(p, t, width);
    }
    const count = await p.locator(t.sel.links).count();
    for (let i = 0; i < count; i++) {
      const link = p.locator(t.sel.links).nth(i);
      // Narrow: the indicator is what HDR-13 checks, not the Tab order (HDR-7 owns that and is a known gap when the toggle
      // follows the panel in DOM order), so each panel link gets focus directly (owner decision, 2026-11-23, as HDR-8/12).
      if (narrow) await link.focus();
      else await tabUntil(p, link);
      await expect(link, `nav link ${i + 1} holds focus`).toBeFocused();
      expect(hasRing(await outline(link)), `focus indicator on nav link ${i + 1}`).toBe(true);
    }
    const axe = (await new AxeBuilder({ page: p }).include(t.sel.header).analyze()).violations.map((v) => `${v.id}:${v.nodes.length}`);
    expect(axe, 'axe on the header region').toEqual([]);
  },

  14: async ({ wca, t, width, narrow }) => {
    const p = await load(wca, t, width);
    // every link of the header region, the brand link included: exactly one carries the current marker
    await expect(p.locator(`${t.sel.header} a[aria-current="page"]`)).toHaveCount(1);
    if (t.kind === 'checkbox') return; // server-rendered: every route is a full page load, there is no client transition
    // client route change: the current marker must follow, still exactly one. Only for a site that declares route links.
    if (!t.sel.routes) throw new NoRouteLinks('no in-app route link declared for this site (its nav holds section anchors and external links only)');
    if (narrow) await openPanel(p, t, width);
    const target = p.locator(t.sel.routes).nth(1);
    await target.click();
    await expect(p.locator(`${t.sel.header} a[aria-current="page"]`)).toHaveCount(1);
    await expect(target).toHaveAttribute('aria-current', 'page');
  },

  15: async ({ wca, t, width }) => {
    // Precondition: with no reduced-motion preference something on the panel or toggle does run, so an empty
    // list below is a measured absence and not a page that never animated.
    const base = await load(wca, t, width, { reducedMotion: 'no-preference' });
    expect((await running(base, t)).length, 'detector precondition: a transition runs on the panel or the toggle icon without the preference').toBeGreaterThan(0);
    const p = await load(wca, t, width, { reducedMotion: 'reduce' });
    expect(await running(p, t), 'closed: no transition or animation runs on the panel or the toggle').toEqual([]);
    await openPanel(p, t, width);
    expect(await running(p, t), 'open: no transition or animation runs on the panel or the toggle').toEqual([]);
  },

  16: async ({ wca, t, width }) => {
    const p = await load(wca, t, width, { javaScript: false });
    const count = await p.locator(t.sel.links).count();
    expect(count).toBeGreaterThan(0);
    const ctl = p.locator(t.sel.clickToggle);
    const reach = async () => {
      const bad: string[] = [];
      for (let i = 0; i < count; i++) {
        const l = p.locator(t.sel.links).nth(i);
        const b = (await l.isVisible()) ? await l.boundingBox() : null;
        if (!b || b.x < 0 || b.x + b.width > width + 1) bad.push(String(i));
      }
      return bad;
    };
    const hidden = await reach();
    const toggleShown = await ctl.first().isVisible();
    if (hidden.length === 0) {
      expect(toggleShown, 'a toggle is shown although every link is already reachable (a control that does nothing)').toBe(false);
      return;
    }
    expect(toggleShown, 'links are hidden and no no-JS toggle is available').toBe(true);
    await ctl.first().click();
    await expect.poll(reach, { message: 'every primary link is reachable through the no-JS toggle' }).toEqual([]);
  },
};

// ------------------------------------------------------------------ catalogue -> tests
const pins = loadPins();
const cases = loadCases().filter((c) => c.id.startsWith('WCA-H-'));

function consumers(): Record<string, { healthy?: boolean; url?: string; reason?: string }> {
  try { return JSON.parse(fs.readFileSync(path.join(OUT, 'consumers.json'), 'utf8')); } catch { return {}; }
}

/** Returns a skip reason, or a target to run against. */
function resolve(c: CaseDef): { skip: string } | { t: Target; vp: string; expected?: string[] } {
  const vp = c.viewport || '375';
  if (c.kind === 'negative-control') {
    return { t: { url: `${BASE}/broken/${c.defect}.html`, bp: 768, kind: 'button', sel: BUTTON_SEL }, vp };
  }
  if (FIXTURES[c.site]) return { t: FIXTURES[c.site], vp };
  const site = pins.sites.find((s) => s.name === c.site);
  if (!site) return { skip: `site ${c.site} is not in pins.json` };
  if (c.route_class === 'sensitive') {
    return { skip: 'sensitive-route guard: sensitive route classes run against fixtures only, never a consumer target' };
  }
  if (site.breakpoint === null && (vp === 'B-1' || vp === 'B')) {
    return { skip: 'breakpoint unknown (not observed): not stated in the contract at the pinned commit' };
  }
  if (site.mode !== 'image') {
    return { skip: `pins mode is ${site.mode}: ${site.not_run_reason || 'no reason recorded'}` };
  }
  const st = consumers()[site.name];
  if (!st) return { skip: 'consumer status unknown (not observed): run.sh recorded nothing for this site' };
  if (!st.healthy || !st.url) return { skip: `image did not start: ${sanitize(st.reason || 'no reason recorded')}` };
  if (!site.selectors) return { skip: 'consumer header selectors unknown (not observed): add sites[].selectors to pins.json before promoting this site' };
  const s = site.selectors as Record<string, string>;
  // a CSS checkbox header declares kind 'checkbox' and the element a user clicks (the label) as click_toggle;
  // the default stays a native button, where the toggle is also what is clicked
  const kind = s.kind === 'checkbox' ? 'checkbox' : 'button';
  return { t: { url: st.url, bp: site.breakpoint as number, kind,
    sel: { header: s.header, nav: s.nav, links: s.links, routes: s.routes, toggle: s.toggle, clickToggle: s.click_toggle ?? s.toggle, outside: s.outside } }, vp,
    expected: site.expected_blocked ?? [] };
}

for (const c of cases) {
  test(c.id, async ({ wca }) => {
    const r = resolve(c);
    if ('skip' in r) test.skip(true, r.skip);
    const { t, vp, expected } = r as { t: Target; vp: string; expected?: string[] };
    wca.expectBlocked(expected ?? []);
    const width = viewportWidth(vp, t.bp);
    const narrow = width < t.bp;
    const fn = behaviours[c.hdr as number];
    if (!fn) throw new Error(`no behaviour for HDR-${c.hdr}`);
    try {
      await fn({ wca, t, width, narrow, c });
    } catch (e) {
      // only the one assertion the known_gap names is a skip; any other failure stays a FAIL
      // the conformant part ran and passed; the route-change step cannot run here, so the case is NOT-RUN, never PASS
      if (e instanceof NoRouteLinks) test.skip(true, `route-change step not run: ${e.message}`);
      if (e instanceof KnownGap) test.skip(true, `observed gap, no exception registered: ${c.known_gap} (${e.message})`);
      throw e;
    }
  });
}
