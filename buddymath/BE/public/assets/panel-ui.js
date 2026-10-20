(function () {
  'use strict';
  if (typeof _appPanel !== 'function') return;
  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g,'&').replace(/</g,'<').replace(/>/g,'>').replace(/"/g,'"');
  }
  window.openAchievements = function openAchievements() {
    var s = (typeof score === 'number') ? score : 0;
    var badges = Math.floor(s / 50);
    _appPanel(
      '<div class="sb-panel sb-ach">' +
        '<div class="sb-panel-banner">' +
          '<div class="sb-panel-banner-text">' +
            '<div class="sb-panel-title">🏆 Thành tích của em</div>' +
            '<div class="sb-panel-sub">Cùng xem em đã tiến bộ thế nào nhé!</div>' +
          '</div>' +
          '<img class="sb-panel-mascot" src="/images/mascot/celebrate.png" alt="" onerror="this.style.display=\'none\'">' +
        '</div>' +
        '<div class="sb-stat-row">' +
          '<div class="sb-stat-card" style="--c:#FFF7DC"><span class="sb-stat-ico">⭐</span><div class="sb-stat-num">' + s + '</div><div class="sb-stat-lbl">Điểm tổng</div></div>' +
          '<div class="sb-stat-card" style="--c:#FFF1E8"><span class="sb-stat-ico">🔥</span><div class="sb-stat-num">1</div><div class="sb-stat-lbl">Chuỗi ngày học</div></div>' +
          '<div class="sb-stat-card" style="--c:#EAF3FF"><span class="sb-stat-ico">🎖️</span><div class="sb-stat-num">' + badges + '</div><div class="sb-stat-lbl">Huy hiệu</div></div>' +
        '</div>' +
        '<div class="sb-section-title">🏅 Bảng thành tích gần đây</div>' +
        '<div id="ach-list" class="sb-ach-list"><div class="sb-muted">Đang tải...</div></div>' +
      '</div>'
    );
    var list = document.getElementById('ach-list');
    if (!list) return;
    if (typeof _sbToken === 'undefined' || !_sbToken) {
      list.innerHTML = '<div class="empty-state"><img class="empty-mascot" src="/images/mascot/trophy.png" alt="" onerror="this.style.display=\'none\'"><div>Chưa có bài nào. Hãy làm bài để nhận huy hiệu nhé! ⭐</div></div>';
      return;
    }
    fetch((typeof CL_API !== 'undefined' ? CL_API : '') + '/scores/history', {
      headers: { Authorization: 'Bearer ' + _sbToken }
    }).then(function (r) { return r.json(); }).then(function (recs) {
      if (!document.getElementById('ach-list')) return;
      if (!recs || !recs.length) {
        document.getElementById('ach-list').innerHTML =
          '<div class="empty-state"><img class="empty-mascot" src="/images/mascot/trophy.png" alt="" onerror="this.style.display=\'none\'"><div>Chưa có bài nào. Hãy làm bài để nhận huy hiệu nhé! ⭐</div></div>';
        return;
      }
      document.getElementById('ach-list').innerHTML = recs.slice(0, 10).map(function (r) {
        var pct = r.pct || 0;
        var em = pct >= 80 ? '🏆' : pct >= 60 ? '👍' : '📚';
        return '<div class="sb-ach-item"><span class="sb-ach-em">' + em + '</span><div class="sb-ach-body"><div class="sb-ach-title">' +
          esc(r.subject) + ' · ' + esc(r.topic || 'Tổng hợp') + '</div><div class="sb-ach-date">' +
          new Date(r.created_at).toLocaleDateString('vi-VN') + '</div></div><div class="sb-ach-pct">' + pct + '%</div></div>';
      }).join('');
    }).catch(function () {
      if (document.getElementById('ach-list'))
        document.getElementById('ach-list').innerHTML = '<div class="sb-muted">Không tải được lịch sử.</div>';
    });
  };
  window.openSettings = function openSettings() {
    var notifOn = localStorage.getItem('sb_notif_off') !== '1';
    var soundOn = localStorage.getItem('sb_sound_off') !== '1';
    function sw(id, on) {
      return '<label class="sb-switch"><input type="checkbox" id="sb-sw-' + id + '" ' + (on ? 'checked' : '') +
        ' onchange="(function(el){if(el.id===\'sb-sw-notif\')localStorage.setItem(\'sb_notif_off\',el.checked?\'0\':\'1\');if(el.id===\'sb-sw-sound\')localStorage.setItem(\'sb_sound_off\',el.checked?\'0\':\'1\');})(this)"><span class="sb-switch-ui"></span></label>';
    }
    _appPanel(
      '<div class="sb-panel sb-settings">' +
        '<div class="sb-panel-head-row">' +
          '<div><div class="sb-panel-title">⚙️ Cài đặt</div><div class="sb-panel-sub">Tùy chỉnh trải nghiệm học tập của em</div></div>' +
          '<img class="sb-panel-mascot sm" src="/images/mascot/idea.png" alt="" onerror="this.style.display=\'none\'">' +
        '</div>' +
        '<div class="sb-settings-card">' +
          '<div class="sb-set-row"><div class="sb-set-ico">🔔</div><div class="sb-set-text"><div class="sb-set-title">Thông báo</div><div class="sb-set-sub">Nhận thông báo trong ứng dụng</div></div>' + sw('notif', notifOn) + '</div>' +
          '<div class="sb-set-row"><div class="sb-set-ico">🔊</div><div class="sb-set-text"><div class="sb-set-title">Âm thanh</div><div class="sb-set-sub">Hiệu ứng âm thanh khi học</div></div>' + sw('sound', soundOn) + '</div>' +
          '<div class="sb-set-row"><div class="sb-set-ico">🎨</div><div class="sb-set-text"><div class="sb-set-title">Giao diện</div><div class="sb-set-sub">Tông màu Mint (mặc định)</div></div><span class="sb-mint-tag">Mint</span></div>' +
          '<div class="sb-set-row"><div class="sb-set-ico">🌐</div><div class="sb-set-text"><div class="sb-set-title">Ngôn ngữ</div><div class="sb-set-sub">Chọn ngôn ngữ hiển thị</div></div>' +
            '<select id="sb-lang-select" onchange="typeof setLang===\'function\'&&setLang(this.value)" class="sb-lang-select"><option value="vi">Tiếng Việt</option><option value="en">English</option></select></div>' +
        '</div>' +
        '<div class="sb-settings-actions">' +
          '<button type="button" class="sb-btn-ghost" onclick="typeof openLearningGuide===\'function\'&&openLearningGuide(true)">📘 Xem lại hướng dẫn và mẹo</button>' +
          '<button type="button" class="sb-btn-danger" onclick="typeof logoutUser===\'function\'&&logoutUser()">🚪 Đăng xuất</button>' +
        '</div>' +
      '</div>'
    );
  };
  console.log('[SmartBuddy] panel-ui.js loaded');
})();
