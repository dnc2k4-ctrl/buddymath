/* world-home.js — Trang chủ dạng BẢN ĐỒ KHÁM PHÁ (Blue Pastel Learning World).
   Ghi đè showHomeScreen sau app-v2.js; giữ nguyên mọi handler hiện có. */
(function () {
  'use strict';

  var ISLES = [
    {
      key: 'math_hub', icon: 'math', name: 'Đảo Số Học', desc: 'Học theo chủ đề & kiểm tra',
      tone: '#5FAEE6', tint: '#E6F4FF', act: "homeOpen('math_hub')"
    },
    {
      key: 'english_hub', icon: 'globe', name: 'Vịnh Tiếng Anh', desc: 'Từ vựng · hội thoại · bài tập',
      tone: '#6FA7D8', tint: '#EAF6FF', act: "homeOpen('english_hub')"
    },
    {
      key: 'life_skills', icon: 'sun', name: 'Khu Vườn Kỹ Năng', desc: 'Tư duy & cảm xúc mỗi ngày',
      tone: '#7C8FE0', tint: '#E7DFFF', act: "homeOpen('life_skills')"
    },
    {
      key: 'prompt-playground', icon: 'brain', name: 'Đài Tư Duy', desc: 'Học cách hỏi đúng, hỏi hay',
      tone: '#C79A3E', tint: '#FFE8A3', act: "homeOpen('prompt-playground')"
    }
  ];

  function n(x, d) { return typeof x === 'number' ? x : (Number(x) || d || 0); }

  window.sbWorldHome = function () {
    ['intro-welcome-screen', 'app-generic-panel'].forEach(function (id) {
      var e = document.getElementById(id); if (e) e.remove();
    });
    document.querySelectorAll('.topic-content-panel, .grade-panel').forEach(function (p) { p.classList.remove('active'); });
    document.querySelectorAll('.topic-btn').forEach(function (b) { b.classList.remove('active'); });

    var main = document.getElementById('main-area');
    if (!main) return;
    var done = n(typeof done !== 'undefined' ? done : 0, 0);
    var score = n(typeof score !== 'undefined' ? score : 0, 0);
    var pct = Math.max(0, Math.min(100, Math.round(done / 10 * 100)));
    var name = 'bạn nhỏ';
    try {
      var u = JSON.parse(localStorage.getItem('sb_user') || 'null');
      if (u && (u.username || u.name)) name = u.username || u.name;
    } catch (e) { }

    var panel = document.createElement('div');
    panel.id = 'intro-welcome-screen';
    panel.style.cssText = 'position:absolute;inset:0;z-index:5;display:flex;flex-direction:column;padding:0 clamp(2px,.4vw,6px) clamp(4px,.8vh,10px);overflow:hidden;background:transparent;animation:fadeInUp .28s ease;';

    panel.innerHTML = '' +
      '<div class="world" id="world-home">' +
      '<div class="world__head"><div>' +
      '<h1 class="world__hi">Chào ' + name.replace(/[<>&]/g, '') + '! <span>Sẵn sàng khám phá?</span></h1>' +
      '<p class="world__sub">Chọn một vùng đất để bắt đầu — Buddy đồng hành và gợi mở từng bước.</p>' +
      '</div></div>' +

      '<section class="world__map">' +
      '<svg class="world__path" viewBox="0 0 100 100" preserveAspectRatio="none"><path d="M18 22 C 34 12, 44 30, 52 40 S 74 42, 82 56 S 70 78, 54 82" /></svg>' +
      '<div class="world__title"><span data-i="books"></span> Bản đồ học tập của ' + name.replace(/[<>&]/g, '') + '</div>' +
      '<div class="world__isles">' +
      ISLES.map(function (s, i) {
        return '<button class="isle" style="--tone:' + s.tone + ';--tint:' + s.tint + '" onclick="' + s.act + '">' +
          '<span class="isle__art"><span data-i="' + s.icon + '"></span></span>' +
          '<span class="isle__body"><span class="isle__name">' + s.name + '</span>' +
          '<span class="isle__desc">' + s.desc + '</span></span>' +
          '<span class="isle__go"><span data-i="arrow"></span></span></button>';
      }).join('') +
      '</div></section>' +

      '<aside class="world__side">' +
      '<section class="guide">' +
      sbMascot('welcome', 'guide__ava') +
      '<div class="guide__bubble">Mình là <b>Buddy</b> — bạn đồng hành của bạn. Muốn bắt đầu bằng một câu hỏi hay một thử thách?<br>' +
      '<button class="sb-btn sb-btn--primary guide__cta" onclick="quickStartBuddy()"><span data-i="chat"></span> Hỏi Buddy ngay</button></div>' +
      '</section>' +
      '<section class="quest">' +
      '<div class="quest__title"><span data-i="target"></span> Nhiệm vụ hôm nay</div>' +
      '<div class="quest__row"><span class="quest__ico"><span data-i="chart"></span></span>' +
      '<div style="flex:1"><div class="quest__val" id="w-q1">' + done + '/10</div><div class="quest__label">bài đã hoàn thành</div></div>' +
      '<span class="chipx chipx--mint">+' + (done ? 'giữ nhịp' : 'bắt đầu') + '</span></div>' +
      '<div class="quest__row"><span class="quest__ico"><span data-i="star"></span></span>' +
      '<div style="flex:1"><div class="quest__val" id="w-q2">' + score + '</div><div class="quest__label">điểm tích luỹ</div></div>' +
      '<span class="chipx chipx--lemon">' + pct + '%</span></div>' +
      '<div class="bar"><i id="w-bar" style="width:' + pct + '%"></i></div>' +
      '<div class="chips"><span class="chipx"><span data-i="trophy"></span> ' + (score >= 50 ? (score >= 100 ? 'Nhà thám hiểm' : 'Người khám phá') : 'Tân binh') + '</span>' +
      '<span class="chipx chipx--lav"><span data-i="flame"></span> Chuỗi học tập</span></div>' +
      '</section>' +
      '<section class="quest" style="display:flex;gap:8px;flex-wrap:wrap;padding:clamp(8px,1.3vh,14px)">' +
      '<button class="sb-btn sb-btn--ghost" onclick="openAchievements()"><span data-i="trophy"></span> Thành tích</button>' +
      '<button class="sb-btn sb-btn--ghost" onclick="openProfile()"><span data-i="user"></span> Hồ sơ</button>' +
      '<button class="sb-btn sb-btn--ghost" onclick="openSettings()"><span data-i="gear"></span> Cài đặt</button>' +
      '</section>' +
      '</aside>' +
      '</div>';

    main.insertBefore(panel, main.firstChild);
    try { if (typeof refreshHomeStats === 'function') refreshHomeStats(); } catch (e) { }
    var homeBtn = document.querySelector('.topic-btn[data-nav="home"]');
    try { if (homeBtn && typeof setNavActive === 'function') setNavActive(homeBtn); } catch (e) { }
    if (window.sbIcon && document.querySelectorAll) { /* icons hydrate qua MutationObserver */ }
  };

  window.showHomeScreen = window.sbWorldHome;
  try { window.fitHomeContent = function () { }; } catch (e) { }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { window.showHomeScreen(); });
  else setTimeout(function () { window.showHomeScreen(); }, 0);
})();
