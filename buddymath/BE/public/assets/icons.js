/* ═══════════════════════════════════════════════════════════════════════════
   icons.js — Bộ icon SVG tự thiết kế cho SmartBuddy (style mềm, bo tròn, 2 tông).
   - Nhúng 1 sprite <symbol> vào trang, dùng: <svg class="sb-ic"><use href="#sb-i-home"/></svg>
   - Hoặc markup <span data-i="home"></span> → tự thay bằng icon (kể cả node render sau).
   - Kế thừa màu qua currentColor → đổi màu bằng CSS.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var S = {
    home:      '<path d="M3 10.6 12 3l9 7.6"/><path d="M5.5 9.2V20a1 1 0 0 0 1 1H10v-5.2h4V21h3.5a1 1 0 0 0 1-1V9.2"/>',
    chat:      '<path d="M20.5 12.2c0 3.9-3.8 7-8.5 7-1 0-2-.1-2.9-.4L4 21l1.3-4A6.6 6.6 0 0 1 3.5 12.2c0-3.9 3.8-7 8.5-7s8.5 3.1 8.5 7Z"/><circle cx="8.7" cy="12.2" r=".9" fill="currentColor" stroke="none"/><circle cx="12" cy="12.2" r=".9" fill="currentColor" stroke="none"/><circle cx="15.3" cy="12.2" r=".9" fill="currentColor" stroke="none"/>',
    brain:     '<path d="M9.5 4.2A2.7 2.7 0 0 0 6.8 7a2.8 2.8 0 0 0-1 5.3 2.8 2.8 0 0 0 2.2 4.4A2.6 2.6 0 0 0 12 18.4V5.6a2.6 2.6 0 0 0-2.5-1.4Z"/><path d="M14.5 4.2A2.7 2.7 0 0 1 17.2 7a2.8 2.8 0 0 1 1 5.3 2.8 2.8 0 0 1-2.2 4.4A2.6 2.6 0 0 1 12 18.4"/>',
    math:      '<path d="M4.5 19.5 19.5 4.5"/><path d="M4.5 10.5h5v-5"/><path d="M14.5 14.5h5v5"/>',
    globe:     '<circle cx="12" cy="12" r="8.5"/><path d="M3.6 9.5h16.8M3.6 14.5h16.8"/><path d="M12 3.5c2.4 2.4 3.7 5.3 3.7 8.5s-1.3 6.1-3.7 8.5c-2.4-2.4-3.7-5.3-3.7-8.5S9.6 5.9 12 3.5Z"/>',
    sun:       '<circle cx="12" cy="12" r="4"/><path d="M12 2.6v2.2M12 19.2v2.2M2.6 12h2.2M19.2 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M18.7 5.3l-1.6 1.6M6.9 17.1l-1.6 1.6"/>',
    clock:     '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.2v5.2l3.4 2"/>',
    trophy:    '<path d="M8 4.5h8v4.2a4 4 0 0 1-8 0V4.5Z"/><path d="M8 5.3H5.4a2.6 2.6 0 0 0 2.6 4.6M16 5.3h2.6a2.6 2.6 0 0 1-2.6 4.6"/><path d="M12 12.7v3.1M8.6 20h6.8M10 15.8h4"/>',
    user:      '<circle cx="12" cy="8.3" r="3.6"/><path d="M4.8 20.2a7.4 7.4 0 0 1 14.4 0"/>',
    gear:      '<path d="M4.5 7h15M4.5 12h15M4.5 17h15"/><circle cx="9" cy="7" r="2.1" fill="#fff"/><circle cx="15.5" cy="12" r="2.1" fill="#fff"/><circle cx="8.5" cy="17" r="2.1" fill="#fff"/>',
    book:      '<path d="M5 5.2A2.2 2.2 0 0 1 7.2 3H19v18H7.2A2.2 2.2 0 0 0 5 23V5.2Z"/><path d="M5 18.8h14M8.6 7.4h6.2M8.6 10.8h4.4"/>',
    star:       '<path d="m12 3.4 2.6 5.2 5.8.8-4.2 4.1 1 5.8-5.2-2.8-5.2 2.8 1-5.8L3.6 9.4l5.8-.8Z"/>',
    flame:     '<path d="M12 3.2c3.1 3 5.1 5.5 5.1 8.6a5.1 5.1 0 0 1-10.2 0c0-1.6.7-3 1.8-4.3.2 1.4.9 2.4 1.9 2.4 1 0 1.6-.8 1.6-2.1 0-1.6-.4-3-2.2-5.1Z"/>',
    target:    '<circle cx="12" cy="12" r="8.3"/><circle cx="12" cy="12" r="4.6"/><circle cx="12" cy="12" r="1.1" fill="currentColor" stroke="none"/>',
    crown:     '<path d="M3.8 18.4 5 7.6l4.2 3.5L12 5.4l2.8 5.7L19 7.6l1.2 10.8H3.8Z"/><path d="M3.8 18.4h16.4"/>',
    gift:      '<path d="M4.4 9.4h15.2V20a1 1 0 0 1-1 1H5.4a1 1 0 0 1-1-1V9.4Z"/><path d="M3.4 9.4h17.2V13H3.4zM12 9.4V21"/><path d="M12 9.4C10.8 6 9.2 4.5 7.7 4.8c-1.6.3-1.5 2.4.3 3.3.9.4 2.2.8 4 .9M12 9.4c1.2-3.4 2.8-4.9 4.3-4.6 1.6.3 1.5 2.4-.3 3.3-.9.4-2.2.8-4 .9"/>',
    bell:      '<path d="M18 9.8a6 6 0 1 0-12 0c0 4.3-1.6 5.7-1.6 5.7h15.2S18 14.1 18 9.8Z"/><path d="M10.2 19.2a2 2 0 0 0 3.6 0"/>',
    speaker:   '<path d="M4.4 9.6h3.1l4.6-3.9v12.6l-4.6-3.9H4.4z"/><path d="M16 9.2a4.4 4.4 0 0 1 0 5.6M18.6 7a7.6 7.6 0 0 1 0 10"/>',
    palette:   '<path d="M12 3.4a8.6 8.6 0 0 0 0 17.2c1.5 0 2.1-.9 2.1-1.9 0-1.6-1.4-1.9-1.4-3 0-.9.7-1.5 1.7-1.5h1.9c2.4 0 4.3-1.7 4.3-4.1 0-3.7-3.8-6.7-8.6-6.7Z"/><circle cx="8.3" cy="9.2" r="1.2" fill="currentColor" stroke="none"/><circle cx="12" cy="7" r="1.2" fill="currentColor" stroke="none"/><circle cx="15.6" cy="9.2" r="1.2" fill="currentColor" stroke="none"/>',
    world:     '<circle cx="12" cy="12" r="8.5"/><path d="M4 9.6h16M4 14.4h16M12 3.5c2.3 2.4 3.6 5.3 3.6 8.5s-1.3 6.1-3.6 8.5c-2.3-2.4-3.6-5.3-3.6-8.5S9.7 5.9 12 3.5Z"/>',
    lock:      '<rect x="5" y="10.2" width="14" height="10.2" rx="2.4"/><path d="M8.2 10.2V7.8a3.8 3.8 0 0 1 7.6 0v2.4"/><circle cx="12" cy="15.3" r="1.3" fill="currentColor" stroke="none"/>',
    logout:    '<path d="M14.6 4.6H6.8a1.8 1.8 0 0 0-1.8 1.8v11.2a1.8 1.8 0 0 0 1.8 1.8h7.8"/><path d="M17.4 8.6 20.8 12l-3.4 3.4M10.4 12h10.2"/>',
    mail:      '<rect x="3.6" y="5.4" width="16.8" height="13.2" rx="2.4"/><path d="m4.4 7 7.6 5.6L19.6 7"/>',
    search:    '<circle cx="10.8" cy="10.8" r="6.6"/><path d="m15.6 15.6 4.4 4.4"/>',
    arrow:     '<path d="M4.5 12h14.6M13.4 6.4 19 12l-5.6 5.6"/>',
    check:     '<path d="m4.8 12.6 4.4 4.4L19.2 7"/>',
    sparkle:   '<path d="m12 3 1.5 4.6L18 9.2l-4.5 1.6L12 15.4l-1.5-4.6L6 9.2l4.5-1.6L12 3Z"/><path d="M18.4 15.4l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7Z"/>',
    cloud:     '<path d="M7.2 18.6a4.1 4.1 0 0 1-.5-8.2 5.4 5.4 0 0 1 10.4-1 3.9 3.9 0 0 1 .7 7.7"/>',
    leaf:      '<path d="M5 19c0-8 5-13 14-13 0 9-5.5 14-14 13Z"/><path d="M6.4 17.6C9 13.4 12 11 16 9.4"/>',
    plane:     '<path d="m3.8 11.6 16.4-6.4-5 16.4-3.6-6.2-6.2-2.4Z"/><path d="m11.4 15.4 8.8-10.2"/>',
    pencil:    '<path d="m4 20 1-4.6L16.6 3.8a1.8 1.8 0 0 1 2.6 0l1 1a1.8 1.8 0 0 1 0 2.6L8.6 19 4 20Z"/><path d="m15.4 5.2 3.4 3.4M5 15.4l3.4 3.4"/>',
    books:     '<rect x="3.4" y="13.4" width="7.2" height="7.2" rx="1.2"/><rect x="11.8" y="11" width="8.6" height="9.6" rx="1.2"/><path d="M5.4 9.2h6.8M14.4 6.6h5.2"/>',
    cap:       '<path d="m2.8 9.6 9.2-4.4 9.2 4.4-9.2 4.4L2.8 9.6Z"/><path d="M6.4 11.8v4.4c0 1.4 2.5 2.6 5.6 2.6s5.6-1.2 5.6-2.6v-4.4M21.2 9.6v5.6"/>',
    heart:     '<path d="M12 20s-7.6-4.5-7.6-9.4A4.4 4.4 0 0 1 12 7.6a4.4 4.4 0 0 1 7.6 3C19.6 15.5 12 20 12 20Z"/>',
    plus:      '<path d="M12 5v14M5 12h14"/>',
    chart:     '<path d="M4.6 19.4V10M9.8 19.4V4.8M15 19.4v-6.2M20.2 19.4V7.8"/>',
    bulb:      '<path d="M9.2 17.2a6.2 6.2 0 1 1 5.6 0"/><path d="M9.6 17.2h4.8M10.2 20h3.6"/>'
  };

  var ns = 'http://www.w3.org/2000/svg';
  function sprite() {
    if (document.getElementById('sb-icon-sprite')) return;
    var svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('id', 'sb-icon-sprite');
    svg.setAttribute('aria-hidden', 'true');
    svg.style.cssText = 'position:absolute;width:0;height:0;overflow:hidden';
    var defs = '';
    for (var k in S) {
      if (!Object.prototype.hasOwnProperty.call(S, k)) continue;
      defs += '<symbol id="sb-i-' + k + '" viewBox="0 0 24 24">' + S[k] + '</symbol>';
    }
    svg.innerHTML = defs;
    (document.body || document.documentElement).appendChild(svg);
  }

  function iconHTML(name, cls) {
    return '<svg class="sb-ic ' + (cls || '') + '" aria-hidden="true" focusable="false">' +
      '<use href="#sb-i-' + name + '"></use></svg>';
  }

  function hydrate(root) {
    var nodes = (root || document).querySelectorAll('[data-i]:not([data-i-done])');
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      var name = el.getAttribute('data-i');
      if (!S[name]) continue;
      el.innerHTML = '<svg class="sb-ic" aria-hidden="true" focusable="false"><use href="#sb-i-' + name + '"></use></svg>';
      el.setAttribute('data-i-done', '1');
    }
  }

  function start() {
    sprite();
    hydrate(document);
    try {
      var mo = new MutationObserver(function (muts) {
        for (var i = 0; i < muts.length; i++) {
          var added = muts[i].addedNodes;
          for (var j = 0; j < added.length; j++) {
            var n = added[j];
            if (n.nodeType === 1) hydrate(n);
          }
        }
      });
      mo.observe(document.body, { childList: true, subtree: true });
    } catch (e) { }
  }

  window.sbIcon = iconHTML;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
