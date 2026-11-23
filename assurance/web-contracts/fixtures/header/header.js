/* Reference behavior for the shared drawer (web-header-a11y). TEST-ONLY fixture.
 * Progressive enhancement: the page has no burger without JS, so the inline nav
 * stays reachable (HDR-16). data-defect on the script tag selects one deliberate
 * defect; it is used only by fixtures/broken/ (negative controls). */
(function () {
  var script = document.currentScript;
  var defect = script.getAttribute('data-defect') || '';
  var bp = parseInt(script.getAttribute('data-breakpoint') || '768', 10);
  var header = document.getElementById('site-header');
  var nav = document.getElementById('site-nav');

  var burger = document.createElement('button');
  burger.type = 'button';
  burger.className = 'mctl-site-burger';
  burger.setAttribute('aria-label', 'Menu');
  if (defect !== 'no-aria-expanded') {
    burger.setAttribute('aria-expanded', 'false');
  }
  burger.setAttribute('aria-controls', 'site-nav');
  nav.parentNode.insertBefore(burger, nav); // toggle precedes the panel in DOM order (HDR-7)

  function isOpen() { return header.hasAttribute('data-nav-open'); }
  function setOpen(open) {
    if (open) { header.setAttribute('data-nav-open', ''); } else { header.removeAttribute('data-nav-open'); }
    if (defect !== 'no-aria-expanded') { burger.setAttribute('aria-expanded', open ? 'true' : 'false'); }
  }

  burger.addEventListener('click', function () { setOpen(!isOpen()); });

  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape' || !isOpen() || defect === 'no-escape') { return; }
    setOpen(false);
    if (defect === 'focus-lost') {
      if (document.activeElement && document.activeElement.blur) { document.activeElement.blur(); }
    } else {
      burger.focus();
    }
  });

  // The scrim is the header ::after, so listen on the document.
  document.addEventListener('pointerdown', function (e) {
    if (isOpen() && !nav.contains(e.target) && !burger.contains(e.target)) { setOpen(false); }
  });

  // Client route change: hash routes stand in for a router afterEach hook.
  function route() {
    var h = location.hash || '#home';
    var links = nav.querySelectorAll('a');
    for (var i = 0; i < links.length; i++) {
      if (links[i].getAttribute('href') === h) { links[i].setAttribute('aria-current', 'page'); }
      else { links[i].removeAttribute('aria-current'); }
    }
    var wasOpen = isOpen();
    setOpen(false);
    if (wasOpen) { burger.focus(); } // close initiated from inside the panel: focus goes to the toggle (HDR-12)
    document.getElementById('route-name').textContent = h.slice(1);
  }
  window.addEventListener('hashchange', route);

  var mq = window.matchMedia('(min-width: ' + bp + 'px)');
  mq.addEventListener('change', function (e) { if (e.matches) { setOpen(false); } });
})();
