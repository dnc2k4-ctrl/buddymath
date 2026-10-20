/* ═══════════════════════════════════════════════════════════════════════════
   app-v2.js — Override giao diện v2 (mint) cho mathbuddy-kids.html
   Load SAU mathbuddy-kids.js. Chỉ thay phần TRÌNH BÀY (markup/CSS), giữ nguyên
   toàn bộ logic dữ liệu/API của app cũ bằng cách tái dùng hàm & biến toàn cục.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  const M = (n, d) => (typeof n === 'number' ? n : (Number(n) || 0));

  /* ── tiện ích ─────────────────────────────────────────────────────────── */
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function appPanel(html) {
    ['intro-welcome-screen', 'app-generic-panel'].forEach(id => {
      const e = document.getElementById(id); if (e) e.remove();
    });
    document.querySelectorAll('.topic-content-panel, .grade-panel').forEach(p => p.classList.remove('active'));
    const mainArea = document.getElementById('main-area');
    if (!mainArea) return null;
    const p = document.createElement('div');
    p.id = 'app-generic-panel';
    p.style.cssText = 'position:absolute;inset:0;z-index:5;overflow:hidden;padding:0;background:transparent;animation:fadeInUp .28s ease;';
    p.innerHTML = html;
    mainArea.insertBefore(p, mainArea.firstChild);
    try { if (typeof toggleSidebar === 'function') toggleSidebar(false); } catch (e) { }
    return p;
  }

  /* ═══════════════ 1. CHAT: chip gợi ý + nút "Học bài mới" ═══════════════ */
  window.sbChatSuggest = function (text) {
    try {
      const i = document.getElementById('user-input');
      if (!i) return;
      i.value = text || '';
      i.focus();
      if (typeof autoH === 'function') autoH(i);
    } catch (e) { }
  };

  const _oldNewChat = window.newChat;
  window.newChat = function () {
    try { if (typeof _oldNewChat === 'function') _oldNewChat(); } catch (e) { }
    const wrap = document.getElementById('messages');
    if (wrap) wrap.innerHTML = '';                       // hero đã là màn chào
    const hero = document.getElementById('sb-chat-hero');
    if (hero) hero.style.display = '';
    const i = document.getElementById('user-input');
    if (i) { i.value = ''; i.focus(); i.style.height = 'auto'; }
  };

  /* ═══════════════ 2. TRANG CHỦ ═══════════════ */
  window.sbHomeCat = function (topic, ico, title, sub, bg, c, arr) {
    return `<button type="button" class="sb-cat" style="--cbg:${bg};--c:${c};--carr:${arr || c}" onclick="homeOpen('${topic}')">
      <span class="sb-cat__ico"><span data-i="${ico}"></span></span>
      <span class="sb-cat__text">
        <span class="sb-cat__name">${title}</span>
        <span class="sb-cat__sub">${sub}</span>
      </span>
      <span class="sb-cat__arrow"><span data-i="arrow"></span></span>
    </button>`;
  };

  window.showHomeScreen = function () {
    ['intro-welcome-screen', 'app-generic-panel'].forEach(id => { const e = document.getElementById(id); if (e) e.remove(); });
    document.querySelectorAll('.topic-content-panel, .grade-panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.topic-btn').forEach(b => b.classList.remove('active'));

    const mainArea = document.getElementById('main-area');
    if (!mainArea) return;
    const introPanel = document.createElement('div');
    introPanel.id = 'intro-welcome-screen';
    introPanel.style.cssText = 'position:absolute;inset:0;z-index:5;display:flex;flex-direction:column;padding:0 clamp(2px,.4vw,6px) clamp(4px,.8vh,10px);overflow:hidden;background:transparent;animation:fadeInUp .28s ease;';

    const _done = (typeof done === 'number' ? done : 0);
    const _score = (typeof score === 'number' ? score : 0);
    const _pct = Math.max(0, Math.min(100, Math.round(_done / 10 * 100)));

    introPanel.innerHTML = `
    <style>@media(max-width:900px){.sb-home__grid{grid-template-columns:1fr !important}.sb-cats{grid-template-columns:repeat(2,minmax(0,1fr)) !important}}</style>
    <div class="sb-home" id="home-fit-wrap">
      <div class="sb-home__head">
        <div>
          <h1 class="sb-home__greet">Xin chào, Buddy! 👋</h1>
          <p class="sb-home__quote">“Học tập là chìa khóa mở ra cánh cửa tương lai” ✨</p>
        </div>
      </div>
      <div class="sb-home__grid">
        <div class="sb-home__main">
          <section class="sb-hero-scene">
            <div class="sb-hero-scene__art">
              <img loading="lazy" src="/images/mascot/waving.png" alt="SmartBuddy" onerror="this.style.display='none'">
            </div>
            <div class="sb-hero-scene__copy">
              <div class="sb-brand-word">Smart<span>Buddy</span></div>
              <div class="sb-brand-tag">Học thông minh – Tiến vững vàng</div>
              <button class="sb-hero-scene__cta" onclick="quickStartBuddy()"><span data-i="chat"></span> Hỏi ngay với Buddy</button>
            </div>
            <span class="sb-hero-scene__float" style="right:7%;top:10%;width:clamp(18px,3.2vh,34px);height:clamp(18px,3.2vh,34px);color:#4E8CFF;"><span data-i="books"></span></span>
            <span class="sb-hero-scene__float" style="right:20%;top:22%;width:clamp(12px,2.2vh,24px);height:clamp(12px,2.2vh,24px);color:#FFB020;"><span data-i="star"></span></span>
            <span class="sb-hero-scene__float" style="right:12%;bottom:14%;width:clamp(16px,2.6vh,28px);height:clamp(16px,2.6vh,28px);color:#A55EEA;"><span data-i="plane"></span></span>
            <span class="sb-hero-scene__float" style="right:32%;top:8%;width:clamp(14px,2.4vh,26px);height:clamp(14px,2.4vh,26px);color:#2FCBA6;"><span data-i="sparkle"></span></span>
          </section>
          <section class="sb-card sb-home__cats">
            <div class="sb-home__cats-head">
              <h2 class="sb-home__cats-title"><span data-i="books"></span> Chọn danh mục học tập</h2>
              <button class="sb-home__link" onclick="if(typeof showAuthToast==='function')showAuthToast('Chọn một danh mục bên dưới nhé! 😊','var(--mint-500)')">Xem tất cả →</button>
            </div>
            <div class="sb-cats">
              ${sbHomeCat('math_hub', 'math', 'Toán học', 'Học chủ đề + kiểm tra', '#E9F9F2', '#12A98D', '#2FCBA6')}
              ${sbHomeCat('english_hub', 'globe', 'Tiếng Anh', 'Từ vựng · hội thoại', '#EAF2FF', '#2F74D0', '#4E8CFF')}
              ${sbHomeCat('life_skills', 'sun', 'Kỹ năng sống', 'Tư duy &amp; cảm xúc', '#F3ECFF', '#7B3EAE', '#A55EEA')}
              ${sbHomeCat('prompt-playground', 'bulb', 'Tư duy đặt câu hỏi', 'Học cách hỏi hay', '#FFF7E3', '#C98A00', '#FFB020')}
            </div>
          </section>
        </div>
        <aside class="sb-home__side">
          <section class="sb-sidecard">
            <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;">
              <h2 class="sb-sidecard__title"><span data-i="chart"></span> Tiến độ học tập</h2>
              <button class="sb-home__link" onclick="openAchievements()">Xem chi tiết →</button>
            </div>
            <div class="sb-progress">
              <div class="sb-donut" id="home-prog-ring" style="background:conic-gradient(#2FCBA6 0deg ${_pct * 3.6}deg,#E4F5EF ${_pct * 3.6}deg 360deg)">
                <div class="sb-donut__inner"><span class="sb-donut__val" id="home-pct-text">${_pct}%</span></div>
              </div>
              <div style="flex:1;min-width:0;">
                <div class="sb-progress__label">Tiến độ hôm nay</div>
                <div class="sb-progress__desc">Bạn đã hoàn thành <b id="home-done-strong">${_done}/10</b> bài tập</div>
                <button class="sb-btn sb-btn--primary" onclick="openAchievements()" style="padding:clamp(6px,1vh,10px) clamp(12px,1.1vw,18px);font-size:clamp(11px,1.3vh,14px);">Xem chi tiết</button>
              </div>
            </div>
          </section>
          <section class="sb-sidecard">
            <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;">
              <h2 class="sb-sidecard__title"><span data-i="trophy"></span> Thành tích nổi bật</h2>
              <button class="sb-home__link" onclick="openAchievements()">Xem tất cả →</button>
            </div>
            ${sbAchRow('star', 'Điểm số', _score, 'home-ach-score', '#C98A00')}
            ${sbAchRow('target', 'Bài đã làm hôm nay', _done + '/10', 'home-ach-done', '#2F74D0')}
            ${sbAchRow('flame', 'Tinh thần học tập', 'Cố lên!', '', '#E06A2B')}
          </section>
          <section class="sb-sidecard sb-motiv" onclick="quickStartBuddy()" title="Cùng học với Buddy nào!">
            <img loading="lazy" src="/images/mascot/reading.png" alt="Buddy đang đọc sách" onerror="this.style.display='none'">
            <div class="sb-motiv__text">Mỗi ngày một chút,<br>bạn sẽ tiến bộ mỗi <span style="color:#0AAE9F">ngày! ✨</span></div>
          </section>
        </aside>
      </div>
    </div>`;

    mainArea.insertBefore(introPanel, mainArea.firstChild);
    try { if (typeof refreshHomeStats === 'function') refreshHomeStats(); } catch (e) { }
    const homeBtn = document.querySelector('.topic-btn[data-nav="home"]');
    try { if (homeBtn && typeof setNavActive === 'function') setNavActive(homeBtn); } catch (e) { }
    try { if (typeof fitHomeContent === 'function') fitHomeContent(); } catch (e) { }
  };

  window.sbAchRow = function (ico, label, value, valId, color) {
    return `<div class="sb-achrow">
      <span class="sb-achrow__icon" style="color:${color || 'var(--mint-700)'}"><span data-i="${ico}"></span></span>
      <span class="sb-achrow__val"${valId ? ` id="${valId}"` : ''}>${value}</span>
      <span class="sb-achrow__label">${label}</span>
    </div>`;
  };

  /* ═══════════════ 3. THÀNH TÍCH ═══════════════ */
  window.sbStatCard = function (img, label, val) {
    return `<div class="sb-stat">
      <span class="sb-stat__icon"><img src="${img}" alt="" loading="lazy"></span>
      <div style="min-width:0"><div class="sb-stat__val">${val}</div><div class="sb-stat__label">${label}</div></div>
      <span class="sb-stat__arrow">›</span>
    </div>`;
  };

  window.openAchievements = function () {
    const s = (typeof score === 'number') ? score : 0;
    const badges = Math.floor(s / 50);
    const tok = (typeof _sbToken !== 'undefined' && _sbToken) || localStorage.getItem('sb_token');
    appPanel(`
      <div class="sb-view">
        <div class="sb-view__banner">
          <div class="sb-view__head-copy">
            <h1 class="sb-view__title"><img class="sb-title-ic" src="/images/v2/ic-trophy-title.png" alt=""> Thành tích của em</h1>
            <p class="sb-view__sub">Cùng xem em đã tiến bộ thế nào nhé!</p>
          </div>
          <img loading="lazy" class="sb-view__art" src="/images/mascot/celebrate.png" alt="" onerror="this.style.display='none'">
        </div>
        <div class="sb-stat-grid">
          ${sbStatCard('/images/v2/ic-trophy3d.png', 'Điểm tổng', s)}
          ${sbStatCard('/images/v2/ic-star3d-2.png', 'Chuỗi ngày học', '1')}
          ${sbStatCard('/images/v2/ic-flame3d-2.png', 'Huy hiệu', badges)}
        </div>
        <div style="display:flex;align-items:center;gap:8px;padding:0 clamp(2px,.3vw,4px);">
          <h2 class="sb-h2" style="font-size:clamp(15px,2.05vh,22px);">🏅 Bảng thành tích gần đây</h2>
        </div>
        <div id="ach-list" class="sb-hist__body"></div>
      </div>`);

    const el = () => document.getElementById('ach-list');
    const empty = `<div class="sb-hist__empty">
        <img loading="lazy" src="/images/v2/ach-empty-art.png" alt="" onerror="this.style.display='none'">
        <div class="sb-hist__empty-title">Chưa có bài nào</div>
        <p class="sb-hist__empty-sub">Hãy làm bài để nhận huy hiệu nhé! ⭐</p>
      </div>`;

    if (tok) {
      fetch(`${CL_API}/scores/history`, { headers: { Authorization: 'Bearer ' + tok } })
        .then(r => r.json()).then(recs => {
          if (!el()) return;
          if (!Array.isArray(recs) || !recs.length) { el().innerHTML = empty; return; }
          el().innerHTML = `<div class="sb-hist__list">${recs.slice(0, 6).map(r => {
            const pct = r.pct || 0;
            const c = pct >= 80 ? '#2ED573' : pct >= 60 ? '#FF8A5B' : '#EF5B5B';
            const em = pct >= 80 ? '🏆' : pct >= 60 ? '👍' : '📚';
            return `<div class="sb-record">
              <span class="sb-record__icon">${em}</span>
              <div class="sb-record__main">
                <div class="sb-record__title">${esc(r.subject)} · ${esc(r.topic || 'Tổng hợp')}</div>
                <div class="sb-record__meta">${new Date(r.created_at).toLocaleDateString('vi-VN')}</div>
              </div>
              <div class="sb-record__pct" style="color:${c}">${pct}%</div>
            </div>`;
          }).join('')}</div>`;
        })
        .catch(() => { if (el()) el().innerHTML = empty; });
    } else {
      setTimeout(() => { if (el()) el().innerHTML = empty; }, 30);
    }
  };

  /* ═══════════════ 4. HỒ SƠ CÁ NHÂN ═══════════════ */
  window.sbProfileRow = function (ic, label, val) {
    return `<div class="sb-prow">
      <span class="sb-prow__ic"><img src="${ic}" alt="" loading="lazy"></span>
      <span class="sb-prow__label">${label}</span>
      <span class="sb-prow__val">${val}</span>
    </div>`;
  };

  window.sbProfilePlanCard = function (id) {
    const P = (typeof _sbp === 'function') ? _sbp() : null;
    if (!P) return '';
    const plan = P.plans[id]; if (!plan) return '';
    const cur = (typeof _sbCurrentPlanId === 'function') ? _sbCurrentPlanId() : P.defaultPlan;
    const color = (typeof _sbPlanColor === 'function') ? _sbPlanColor(id) : '#2FCBA6';
    const isCur = id === cur;
    const hot = id === 'standard';
    const gold = id === 'premium';
    const icon = `/images/v2/${id === 'premium' ? 'ic-crown3d-p' : id === 'standard' ? 'ic-crown3d-s' : 'ic-gift3d'}.png`;
    const bgIcon = id === 'premium' ? '#FFF3D6' : id === 'standard' ? '#E4FBF3' : '#EEF3F1';
    const price = (typeof _sbFmtPrice === 'function') ? _sbFmtPrice(plan) : '0đ';
    const suffix = (typeof _sbPriceSuffix === 'function') ? _sbPriceSuffix(plan) : '';
    const highlights = (typeof _sbHighlights === 'function') ? _sbHighlights(id) : [];
    const cta = isCur
      ? `<button class="sb-plan__cta" disabled>Đang dùng</button>`
      : `<button class="sb-plan__cta" onclick="sbChoosePlan('${id}')">${id === P.defaultPlan ? P.ui.cta.free : P.ui.cta.paid}</button>`;
    return `<div class="sb-plan ${hot ? 'sb-plan--hot' : ''} ${gold ? 'sb-plan--gold' : ''}" style="--pl:${color};--plbg:${bgIcon}">
      ${hot ? '<span class="sb-plan__ribbon">PHỔ BIẾN</span>' : ''}
      <span class="sb-plan__icon"><img src="${icon}" alt="" loading="lazy"></span>
      <div class="sb-plan__name">${esc(plan.name)}</div>
      <div class="sb-plan__price"><b>${price}</b>${suffix ? `<span>${suffix}</span>` : ''}</div>
      <ul class="sb-plan__feat">${highlights.map(f => `<li><span>✓</span>${esc(f)}</li>`).join('')}</ul>
      ${cta}
    </div>`;
  };

  window.openProfile = function () {
    let u = (typeof authCurrentUser !== 'undefined' && authCurrentUser) ? authCurrentUser : null;
    if (!u) { try { u = JSON.parse(localStorage.getItem('sb_user') || 'null'); } catch (e) { } }
    u = u || {};
    const loggedIn = !!(u.username || u.email);
    const name = u.username || u.name || 'Khách';
    const email = u.email || (loggedIn ? '—' : '(chưa đăng nhập)');
    const role = u.role === 'parent' ? 'Phụ huynh' : u.role === 'admin' ? 'Quản trị' : 'Học sinh';
    const grade = (u.role === 'student' || !u.role) ? ('Lớp ' + (u.grade || 5)) : role;
    const P = (typeof _sbp === 'function') ? _sbp() : null;
    const curPlanName = P ? ((P.plans[(typeof _sbCurrentPlanId === 'function' ? _sbCurrentPlanId() : P.defaultPlan)] || {}).name || 'Miễn phí') : 'Miễn phí';

    appPanel(`
      <div class="sb-view">
        <div class="sb-view__head" style="padding:0 clamp(2px,.4vw,6px);">
          <div class="sb-view__head-copy">
            <h1 class="sb-view__title">Hồ sơ cá nhân</h1>
            <p class="sb-view__sub">Quản lý thông tin và gói học của bạn</p>
          </div>
        </div>
        <div class="sb-profile">
          <section class="sb-profile__card">
            <div class="sb-profile__top">
              <div class="sb-profile__avatar">${esc((name[0] || '?').toUpperCase())}</div>
              <div style="position:relative;z-index:1;min-width:0;">
                <div class="sb-profile__name">${esc(name)}</div>
                <span class="sb-profile__grade">🎓 ${esc(grade)}</span>
              </div>
              <img loading="lazy" class="sb-profile__art" src="/images/mascot/thumbsup.png" alt="" onerror="this.style.display='none'">
            </div>
            <div class="sb-profile__rows">
              ${sbProfileRow('/images/v2/ic-mail3d.png', 'Email', esc(email))}
              ${sbProfileRow('/images/v2/ic-user3d.png', 'Vai trò', role)}
              ${sbProfileRow('/images/v2/ic-crown3d.png', 'Gói hiện tại', `<b style="color:var(--mint-700)">${esc(curPlanName)}</b>`)}
            </div>
            <div class="sb-profile__actions">
              ${loggedIn
        ? `<button class="sb-btn sb-btn--ghost" onclick="openForgotModal()"><img class="sb-btn-ic" src="/images/v2/ic-lock3d.png" alt=""> Đổi mật khẩu</button>
                   <button class="sb-btn sb-btn--danger" onclick="logoutUser()"><img class="sb-btn-ic" src="/images/v2/ic-logout3d.png" alt=""> Đăng xuất</button>`
        : `<button class="sb-btn sb-btn--primary" onclick="openAuthModal('login')">Đăng nhập / Đăng ký</button>`}
            </div>
          </section>
          <section class="sb-profile__card" style="padding:clamp(12px,1.9vh,20px) clamp(14px,1.5vw,22px);gap:clamp(6px,1vh,10px);">
            <div style="display:flex;align-items:center;gap:10px;">
              <span class="sb-tile sb-tile--amber" style="width:clamp(30px,4vh,44px);height:clamp(30px,4vh,44px);font-size:clamp(15px,2vh,21px);">⭐</span>
              <div>
                <h2 class="sb-h2" style="font-size:clamp(15px,2.1vh,23px);">Nâng cấp gói học</h2>
                <p class="sb-sub" style="font-size:clamp(10.5px,1.3vh,14px);">Chat với AI thông minh hơn, học không giới hạn.</p>
              </div>
            </div>
            <div class="sb-plans">
              ${P ? ['free', 'standard', 'premium'].map(sbProfilePlanCard).join('')
        : '<div class="sb-sub">Đang tải bảng giá…</div>'}
            </div>
          </section>
        </div>
      </div>`);
  };

  /* ═══════════════ 5. CÀI ĐẶT ═══════════════ */
  window.sbSettingRow = function (ic, title, sub, control) {
    return `<div class="sb-srow">
      <span class="sb-srow__ic"><img src="${ic}" alt="" loading="lazy"></span>
      <div style="min-width:0"><div class="sb-srow__title">${title}</div><div class="sb-srow__sub">${sub}</div></div>
      <div class="sb-srow__ctrl">${control}</div>
    </div>`;
  };

  window.sbSwitch = function (id, on) {
    return `<div class="sb-switch" data-on="${on ? '1' : '0'}" onclick="sbFlipSetting('${id}',this)"></div>`;
  };

  window.sbFlipSetting = function (id, el) {
    const on = el.dataset.on !== '1';
    el.dataset.on = on ? '1' : '0';
    if (id === 'notif') localStorage.setItem('sb_notif_off', on ? '0' : '1');
    if (id === 'sound') localStorage.setItem('sb_sound_off', on ? '0' : '1');
    if (id === 'sound' && on) { try { const ac = _sbAudio(); if (ac && ac.state === 'suspended') ac.resume(); sbPlaySound('toggle'); } catch (e) { } }
    if (id === 'notif' && on) { try { sbPlaySound('notify'); } catch (e) { } }
    if (typeof showAuthToast === 'function') showAuthToast(id === 'notif' ? (on ? '🔔 Đã bật thông báo' : '🔕 Đã tắt thông báo') : (on ? '🔊 Đã bật âm thanh' : '🔇 Đã tắt âm thanh'), 'var(--mint-500)');
  };

  window.openSettings = function () {
    const notifOn = localStorage.getItem('sb_notif_off') !== '1';
    const soundOn = localStorage.getItem('sb_sound_off') !== '1';
    const LANG = (typeof SB_LANG !== 'undefined') ? SB_LANG : 'vi';
    appPanel(`
      <div class="sb-view">
        <div class="sb-view__head" style="padding:0 clamp(2px,.4vw,6px);">
          <span class="sb-view__gear"><img src="/images/v2/ic-gear3d.png" alt=""></span>
          <div class="sb-view__head-copy">
            <h1 class="sb-view__title">Cài đặt</h1>
            <p class="sb-view__sub">Tùy chỉnh trải nghiệm học tập của em</p>
          </div>
          <img loading="lazy" class="sb-view__art" src="/images/mascot/waving.png" alt="" onerror="this.style.display='none'">
        </div>
        <div class="sb-settings__card">
          ${sbSettingRow('/images/v2/ic-bell3d.png', 'Thông báo', 'Nhận thông báo trong ứng dụng', sbSwitch('notif', notifOn))}
          ${sbSettingRow('/images/v2/ic-speaker3d.png', 'Âm thanh', 'Hiệu ứng âm thanh khi học', sbSwitch('sound', soundOn))}
          ${sbSettingRow('/images/v2/ic-palette3d.png', 'Giao diện', 'Tông màu Mint (mặc định)', `<span class="sb-pill sb-pill--mint" style="font-size:clamp(10px,1.25vh,13px)">Mint 🌿</span><span style="color:var(--muted-2);font-weight:900">⌄</span>`)}
          ${sbSettingRow('/images/v2/ic-globe3d.png', 'Ngôn ngữ', 'Chọn ngôn ngữ hiển thị', `<select id="sb-lang-select" onchange="setLang(this.value)" style="padding:clamp(6px,1vh,9px) clamp(12px,1.2vw,18px);border:1.6px solid var(--mint-300);border-radius:var(--r-pill);background:#fff;font-family:var(--font-body);font-weight:800;font-size:clamp(11px,1.32vh,14px);color:var(--mint-700);cursor:pointer;outline:none;"><option value="vi"${LANG !== 'en' ? ' selected' : ''}>Tiếng Việt</option><option value="en"${LANG === 'en' ? ' selected' : ''}>English</option></select>`)}
        </div>
        <div class="sb-settings__actions">
          <button class="sb-btn sb-btn--ghost" onclick="openLearningGuide(true)">📖 Xem lại hướng dẫn và mẹo</button>
          <button class="sb-btn sb-btn--danger" onclick="logoutUser()">🚪 Đăng xuất</button>
        </div>
      </div>`);
  };

  /* ═══════════════ 6. MODAL HƯỚNG DẪN: style mint + icon 3D + mascot ═══════════════ */
  const _oldGuide = window.openLearningGuide;
  window.openLearningGuide = function (markSeen) {
    try { if (typeof _oldGuide === 'function') _oldGuide(markSeen); } catch (e) { }
    try {
      const card = document.querySelector('#sb-learning-guide .sb-help-card');
      if (!card) return;
      card.classList.add('sb-guide');
      // gán class cho 3 khối nội dung theo màu nền gốc
      [...card.children].forEach(ch => {
        if (!(ch instanceof HTMLElement) || ch.tagName !== 'DIV') return;
        const bg = getComputedStyle(ch).backgroundColor.replace(/\s/g, '');
        if (bg.includes('240,251,247')) ch.classList.add('sb-guide__box', 'sb-guide__box--mint');
        else if (bg.includes('247,248,255')) ch.classList.add('sb-guide__box', 'sb-guide__box--violet');
        else if (bg.includes('255,248,236')) ch.classList.add('sb-guide__box', 'sb-guide__box--amber');
        const b = ch.querySelector('b');
        if (b) b.textContent = b.textContent.replace(/^[^\p{L}\d]+/u, '').trim();
      });
      if (!card.querySelector('.sb-guide__mascot')) {
        const img = document.createElement('img');
        img.className = 'sb-guide__mascot';
        img.src = '/images/mascot/reading.png';
        img.alt = '';
        card.appendChild(img);
      }
      const h2 = card.querySelector('h2');
      if (h2) h2.classList.add('sb-guide__title');
      const pIntro = card.querySelector('p');
      if (pIntro) pIntro.classList.add('sb-guide__intro');
    } catch (e) { }
  };

  /* ═══════════════ 7. KHÔNG auto-zoom: giữ tỉ lệ 1:1 như ảnh mẫu ═══════════════ */
  window.fitHomeContent = function () {
    const w = document.getElementById('home-fit-wrap');
    if (!w) return;
    w.style.zoom = '1';
    w.style.width = '100%';
    w.style.maxWidth = '100%';
    w.style.visibility = 'visible';
    const host = document.getElementById('intro-welcome-screen');
    if (host) { host.style.overflow = 'hidden'; }
  };

  /* ═══════════════ 8. KHỞI ĐỘNG LẠI MÀN HÌNH ĐẦU ═══════════════ */
  function boot() {
    try {
      if (typeof showHomeScreen === 'function') showHomeScreen();
    } catch (e) { console.warn('sb-v2 boot:', e); }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else setTimeout(boot, 0);
})();
