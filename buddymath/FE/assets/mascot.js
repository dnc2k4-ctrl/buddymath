/* ═══════════════════════════════════════════════════════════════════════════
   mascot.js — BUDDY: mascot mới của BuddyMath (SVG, palette pastel blue).
   window.sbMascot(expr, cls) → trả về chuỗi SVG.
   expr: welcome | thinking | hint | correct | tryagain | celebration | listening | loading
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';
  var FACES = {
    welcome:   { eyes: 'happy',  mouth: 'smile',  extra: 'sparkle' },
    thinking:  { eyes: 'lookup', mouth: 'hmm',    extra: 'gear' },
    hint:      { eyes: 'happy',  mouth: 'smile',  extra: 'bulb' },
    correct:   { eyes: 'happy',  mouth: 'grin',   extra: 'stars' },
    tryagain:  { eyes: 'calm',   mouth: 'small',  extra: 'heart' },
    celebration:{ eyes: 'joy',   mouth: 'grin',   extra: 'confetti' },
    listening: { eyes: 'lookup', mouth: 'small',  extra: 'wave' },
    loading:   { eyes: 'closed', mouth: 'small',  extra: 'dots' }
  };

  function eyes(kind) {
    if (kind === 'happy') return '<path d="M64 112c5-6 12-6 17 0" stroke="#27476B" stroke-width="5" stroke-linecap="round" fill="none"/><path d="M108 112c5-6 12-6 17 0" stroke="#27476B" stroke-width="5" stroke-linecap="round" fill="none"/>';
    if (kind === 'joy') return '<path d="M62 110c6-8 15-8 20 0" stroke="#27476B" stroke-width="5" stroke-linecap="round" fill="none"/><path d="M107 110c6-8 15-8 20 0" stroke="#27476B" stroke-width="5" stroke-linecap="round" fill="none"/>';
    if (kind === 'closed') return '<path d="M62 113c6 4 14 4 20 0" stroke="#27476B" stroke-width="5" stroke-linecap="round" fill="none"/><path d="M107 113c6 4 14 4 20 0" stroke="#27476B" stroke-width="5" stroke-linecap="round" fill="none"/>';
    if (kind === 'lookup') return '<circle cx="72" cy="109" r="8" fill="#27476B"/><circle cx="117" cy="109" r="8" fill="#27476B"/><circle cx="75" cy="106" r="2.6" fill="#fff"/><circle cx="120" cy="106" r="2.6" fill="#fff"/>';
    if (kind === 'calm') return '<circle cx="72" cy="112" r="7" fill="#27476B"/><circle cx="117" cy="112" r="7" fill="#27476B"/><circle cx="74" cy="109.5" r="2.2" fill="#fff"/><circle cx="119" cy="109.5" r="2.2" fill="#fff"/>';
    return '<circle cx="72" cy="111" r="8" fill="#27476B"/><circle cx="117" cy="111" r="8" fill="#27476B"/>';
  }

  function mouth(kind) {
    if (kind === 'smile') return '<path d="M82 132c8 8 20 8 28 0" stroke="#315782" stroke-width="4.5" stroke-linecap="round" fill="none"/>';
    if (kind === 'grin') return '<path d="M80 130c4 14 32 14 36 0Z" fill="#F0918E" stroke="#315782" stroke-width="3.5" stroke-linejoin="round"/>';
    if (kind === 'hmm') return '<path d="M86 134h18" stroke="#315782" stroke-width="4.5" stroke-linecap="round"/>';
    return '<circle cx="96" cy="134" r="3.4" fill="#315782"/>';
  }

  function extra(kind) {
    if (kind === 'bulb') return '<g><circle cx="176" cy="54" r="13" fill="#FFE8A3"/><path d="M170 66h12M172 71h8" stroke="#8A6A12" stroke-width="3" stroke-linecap="round"/><path d="M176 41v-6M166 46l-5-5M186 46l5-5" stroke="#F3C75F" stroke-width="3" stroke-linecap="round"/></g>';
    if (kind === 'gear') return '<g><circle cx="180" cy="58" r="11" fill="#E6F4FF" stroke="#8FC9F4" stroke-width="3"/><path d="M180 48v-5M180 68v5M170 58h-5M190 58h5" stroke="#8FC9F4" stroke-width="3" stroke-linecap="round"/></g>';
    if (kind === 'stars' || kind === 'sparkle') return '<g fill="#FFE8A3"><path d="m176 40 3 7 7 3-7 3-3 7-3-7-7-3 7-3Z"/><circle cx="196" cy="66" r="3.4" fill="#AEBEFF"/><circle cx="160" cy="46" r="2.6" fill="#C9F2E2"/></g>';
    if (kind === 'confetti') return '<g><circle cx="176" cy="44" r="4" fill="#F0918E"/><circle cx="194" cy="60" r="3.4" fill="#FFE8A3"/><circle cx="160" cy="38" r="3" fill="#AEBEFF"/><path d="m188 36 5-5M200 42l6-2" stroke="#8FC9F4" stroke-width="3" stroke-linecap="round"/></g>';
    if (kind === 'heart') return '<path d="M180 62c-8-5-12-9-12-14a6 6 0 0 1 12-1 6 6 0 0 1 12 1c0 5-4 9-12 14Z" fill="#FFD9CB"/>';
    if (kind === 'wave') return '<g><path d="M176 46v-9M186 52l6-6M166 52l-6-6" stroke="#8FC9F4" stroke-width="3.4" stroke-linecap="round"/></g>';
    if (kind === 'dots') return '<g fill="#AEBEFF"><circle cx="170" cy="52" r="4"/><circle cx="182" cy="46" r="4"/><circle cx="194" cy="52" r="4"/></g>';
    return '';
  }

  function build(expr, cls) {
    var f = FACES[expr] || FACES.welcome;
    return '' +
      '<svg class="buddy-svg ' + (cls || '') + '" viewBox="0 0 240 260" role="img" aria-label="Buddy" xmlns="http://www.w3.org/2000/svg">' +
      '<defs>' +
      '<linearGradient id="bBody" x1="40" y1="60" x2="200" y2="250" gradientUnits="userSpaceOnUse">' +
      '<stop stop-color="#CFE9FB"/><stop offset=".55" stop-color="#9FD2F4"/><stop offset="1" stop-color="#7EC0EE"/></linearGradient>' +
      '<linearGradient id="bBelly" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#FFFFFF"/><stop offset="1" stop-color="#EAF6FF"/></linearGradient>' +
      '<radialGradient id="bGlow" cx=".5" cy=".4" r=".6"><stop stop-color="#FFFFFF" stop-opacity=".9"/><stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/></radialGradient>' +
      '</defs>' +
      '<ellipse cx="118" cy="246" rx="62" ry="10" fill="#315782" opacity=".12"/>' +
      '<circle cx="118" cy="118" r="92" fill="url(#bGlow)"/>' +
      /* chân */
      '<rect x="80" y="206" width="30" height="34" rx="15" fill="url(#bBody)"/>' +
      '<rect x="126" y="206" width="30" height="34" rx="15" fill="url(#bBody)"/>' +
      /* thân */
      '<rect x="52" y="104" width="132" height="116" rx="52" fill="url(#bBody)"/>' +
      '<rect x="82" y="146" width="72" height="58" rx="24" fill="url(#bBelly)"/>' +
      /* cánh tay */
      '<rect x="34" y="128" width="26" height="60" rx="13" fill="#B9DFF7"/>' +
      '<rect x="176" y="128" width="26" height="60" rx="13" fill="#B9DFF7"/>' +
      /* đầu */
      '<rect x="46" y="46" width="144" height="112" rx="54" fill="url(#bBody)"/>' +
      '<rect x="64" y="64" width="108" height="80" rx="38" fill="#FFFFFF"/>' +
      eyes(f.eyes) + mouth(f.mouth) +
      '<circle cx="62" cy="132" r="7" fill="#FFD9CB" opacity=".7"/><circle cx="158" cy="132" r="7" fill="#FFD9CB" opacity=".7"/>' +
      /* ăng-ten + mũ thám hiểm */
      '<path d="M118 46V22" stroke="#7EC0EE" stroke-width="6" stroke-linecap="round"/>' +
      '<circle cx="118" cy="16" r="10" fill="#AEBEFF"/>' +
      '<path d="M58 40 118 12l60 28-60 26-60-26Z" fill="#315782"/>' +
      '<path d="M84 52v18c0 7 15 12 34 12s34-5 34-12V52" fill="#27476B"/>' +
      '<circle cx="178" cy="44" r="9" fill="#E7DFFF" stroke="#AEBEFF" stroke-width="3"/>' +
      extra(f.extra) +
      '</svg>';
  }

  window.sbMascot = build;
})();
