/* ═══════════════════════════════════════════════════════════════════════════
   stage-loader.js — "Design canvas 1:1" cho SmartBuddy (v4).

   Ảnh mẫu thiết kế ở khung 1672×941 (16:9). Trang gốc chuyển ngay sang
   /stage.html?to=<url>; trang đó dựng khung 1672×941 (iframe chở lại chính
   trang với ?embed=1) rồi scale đều cho vừa màn hình → không méo, không cuộn,
   thừa thì viền mint. Trang trong iframe chạy với viewport đúng 1672×941 nên
   mọi đơn vị vh/vw khớp ảnh mẫu 1:1.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';
  try {
    if (window.top !== window.self || /(?:^|[?&])embed=1(?:&|$)/.test(location.search)) {
      document.documentElement.setAttribute('data-sb-embed', '1');
      return;
    }
    if (/\/stage\.html$/.test(location.pathname)) return;

    /* Ẩn trang gốc trong lúc chờ chuyển sang khung stage (tránh nháy) */
    document.write('<style id="sb-stage-prehide">body{display:none!important;overflow:hidden!important}</style>');

    var to = location.pathname + location.search + location.hash;
    location.replace('/stage.html?to=' + encodeURIComponent(to));
  } catch (e) {
    /* lỗi: để trang chạy bình thường */
  }
})();
