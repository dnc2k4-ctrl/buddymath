/**
 * auth_patch.js — MathBuddy × MSSQL Auth Integration
 * ─────────────────────────────────────────────────────
 * Chèn vào cuối <body> của mathbuddy-kids.html (trước </script> cuối).
 * Cung cấp các hàm đăng nhập / đăng ký / đăng xuất / kiểm tra session thật
 * qua backend FastAPI + MSSQL (xem auth_routes.py, db.py).
 *
 * Form HTML (username/password + đăng ký) đã có sẵn trong mathbuddy-kids.html;
 * file này chỉ cung cấp các hàm gọi API mà HTML đó dùng:
 *   - window.loginWithCredentials(username, password)
 *   - window.registerAccount({ username, password, display_name, email })
 *   - window.logoutWithBackend()
 * và tự kiểm tra session khi trang vừa load (checkExistingSession),
 * gọi lockApp()/unlockApp() (định nghĩa trong mathbuddy-kids.html) tương ứng.
 */

(function () {
  'use strict';

  // ── Config ────────────────────────────────────────────────────────────────
  const AUTH_BASE = '';   // same-origin. Đổi thành 'http://host:8000' nếu cần.
  const TOKEN_KEY = 'mb_auth_token';

  // ── Token helpers ─────────────────────────────────────────────────────────
  function getToken()   { return localStorage.getItem(TOKEN_KEY); }
  function setToken(t)  { localStorage.setItem(TOKEN_KEY, t); }
  function clearToken() { localStorage.removeItem(TOKEN_KEY); }
  function authHeader() { const t = getToken(); return t ? { 'Authorization': 'Bearer ' + t } : {}; }

  async function apiFetch(path, opts = {}) {
    const headers = { 'Content-Type': 'application/json', ...authHeader(), ...(opts.headers || {}) };
    const res = await fetch(AUTH_BASE + path, { ...opts, headers });
    let data = null;
    try { data = await res.json(); } catch (e) { /* body rỗng hoặc không phải JSON */ }
    if (!res.ok) {
      const detail = (data && data.detail) ? data.detail : `Lỗi ${res.status}`;
      throw new Error(detail);
    }
    return data;
  }

  // ── Check session on page load ────────────────────────────────────────────
  async function checkExistingSession() {
    if (!getToken()) {
      // Không có token thật → khoá app, bắt buộc đăng nhập
      window._mbSessionChecked = true;
      if (typeof lockApp === 'function') lockApp();
      return;
    }
    try {
      const me = await apiFetch('/auth/me');
      if (me.authenticated) {
        // Đã có session hợp lệ → cập nhật UI + mở app
        const acct = {
          name:           me.display_name || me.username,
          username:       me.username,
          role:           me.role,
          type:           'db',
          avatar:         null,
          email:          me.email || '',
          allowed_grades: me.allowed_grades || [],
        };
        if (typeof authCurrentUser !== 'undefined') authCurrentUser = acct;
        try { localStorage.setItem('mb_user', JSON.stringify(acct)); } catch (e) {}
        if (typeof renderAuthState === 'function') renderAuthState();
        if (typeof applyGradePermissions === 'function') applyGradePermissions();
        window._mbUsername = acct.username;
        window._mbRole     = acct.role;
        window._mbSessionChecked = true;
        if (typeof unlockApp === 'function') unlockApp();
        console.log('[MathBuddy Auth] Auto-login từ session:', me.username, '| grades:', acct.allowed_grades);
      } else {
        clearToken();
        window._mbSessionChecked = true;
        if (typeof lockApp === 'function') lockApp();
      }
    } catch (e) {
      clearToken();
      window._mbSessionChecked = true;
      if (typeof lockApp === 'function') lockApp();
    }
  }

  // ── Đăng nhập bằng username + password ────────────────────────────────────
  window.loginWithCredentials = async function (username, password) {
    let data;
    try {
      data = await apiFetch('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      });
    } catch (e) {
      // Message từ backend đã rõ ràng cho từng trường hợp:
      // 401 = sai user/pass, 403 = tài khoản pending/rejected/disabled
      throw new Error(e.message || 'Sai tên đăng nhập hoặc mật khẩu.');
    }
    setToken(data.token);
    window._mbUsername = data.username;
    window._mbRole     = data.role;
    return {
      name:           data.display_name || data.username,
      username:       data.username,
      role:           data.role,
      type:           'db',
      avatar:         null,
      email:          data.email || '',
      allowed_grades: data.allowed_grades || [],
    };
  };

  // ── Đăng ký tài khoản mới (role=student, status=pending) ──────────────────
  window.registerAccount = async function ({ username, password, display_name, email }) {
    try {
      return await apiFetch('/auth/register', {
        method: 'POST',
        body: JSON.stringify({
          username,
          password,
          display_name: display_name || '',
          email: email || '',
        }),
      });
    } catch (e) {
      throw new Error(e.message || 'Đăng ký thất bại, vui lòng thử lại.');
    }
  };

  // ── Đăng xuất ──────────────────────────────────────────────────────────────
  async function logoutWithBackend() {
    try { await apiFetch('/auth/logout', { method: 'POST', body: '{}' }); } catch (e) {}
    clearToken();
  }
  window.logoutWithBackend = logoutWithBackend;

  // ── Patch logoutUser (định nghĩa trong mathbuddy-kids.html) để gọi backend ─
  const _origLogout = window.logoutUser;
  window.logoutUser = async function () {
    await logoutWithBackend();
    window._mbUsername = null;
    window._mbRole     = null;
    if (typeof _origLogout === 'function') _origLogout();
  };

  // ── Gửi username kèm vào mỗi chat request ─────────────────────────────────
  // Intercept fetch calls tới /chat để thêm username vào session_id, giúp
  // backend/monitor biết tin nhắn nào thuộc về user nào.
  const _origFetch = window.fetch;
  window.fetch = function (url, opts = {}) {
    if (typeof url === 'string' && (url.includes('/chat') || url.includes('/v1/messages'))) {
      if (opts.body && window._mbUsername) {
        try {
          const body = JSON.parse(opts.body);
          if (body && !body.username) {
            body.username   = window._mbUsername;
            body.session_id = body.session_id || (window._mbUsername + '_' + Date.now());
            opts = { ...opts, body: JSON.stringify(body) };
          }
        } catch (e) {}
      }
    }
    return _origFetch.call(window, url, opts);
  };

  // ── Init ──────────────────────────────────────────────────────────────────
  function init() {
    checkExistingSession();
  }

  // Đợi DOM sẵn sàng
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    // DOM đã sẵn (script chèn cuối body)
    setTimeout(init, 0);
  }

})();
