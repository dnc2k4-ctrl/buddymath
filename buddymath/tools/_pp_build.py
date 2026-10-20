# -*- coding: utf-8 -*-
"""Ghép parent.html mới: giữ nguyên 100% JS, thay CSS + markup."""
from pathlib import Path

root = Path(r'C:\Users\Admin\Downloads\AI Web\buddymath\buddymath')
p = root / 'FE' / 'parent.html'
orig = p.read_text(encoding='utf-8')

(CSS_START := orig.index('<style>\n*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}'))
head_prefix = orig[:CSS_START]

# backup lần đầu
bak = root / 'tools' / '_parent_orig.html'
if not bak.exists():
    bak.write_text(orig, encoding='utf-8')

head_prefix = head_prefix.replace('<html lang="vi">', '<html lang="vi" class="sb-fixed">', 1)
head_prefix += '<link rel="stylesheet" href="/assets/mint-v2.css">\n'

TAIL_MARK = '<script src="/config/plans.js"></script>'
tail = orig[orig.index(TAIL_MARK):]

style = (root / 'tools' / '_pp_style.txt').read_text(encoding='utf-8')
body = (root / 'tools' / '_pp_body.txt').read_text(encoding='utf-8')

new = head_prefix + style + '</head>\n' + body + tail

old_tpl = """    list.innerHTML=children.map(c=>`
      <div class="child-card" onclick="selectChild('${c.id}')" id="child-${c.id}">
        <div class="cc-name">🎒 ${c.username}</div>
        <div class="cc-meta">Lớp ${c.grade} · ${c.email}</div>
        <div class="cc-stats">
          <div class="cc-stat">Tuần này: <span>${c.week_sessions} bài</span></div>
          ${c.week_avg_pct!==null?`<div class="cc-stat">TB: <span>${c.week_avg_pct}%</span></div>`:''}
          <div class="cc-stat">Tổng: <span>${c.total_sessions}</span></div>
        </div>
      </div>`).join('');"""

new_tpl = """    list.innerHTML=children.map(c=>`
      <div class="child-card" onclick="selectChild('${c.id}')" id="child-${c.id}">
        <div class="cc-avatar"><img src="/images/mascot/head.png" alt="" onerror="this.outerHTML='🎒'"></div>
        <div class="cc-body">
          <div class="cc-name">${c.username}</div>
          <div class="cc-meta">Lớp ${c.grade} · ${c.email}</div>
        </div>
        <span class="cc-caret" aria-hidden="true">›</span>
        <div class="cc-stats">
          <span class="cc-stat">📊 Tuần này: <b>${c.week_sessions} bài</b></span>
          <span class="cc-stat">📈 Tổng: <b>${c.total_sessions}</b></span>
        </div>
      </div>`).join('');"""

assert old_tpl in new, 'loadChildren template not found'
new = new.replace(old_tpl, new_tpl, 1)

p.write_text(new, encoding='utf-8')
print('written', p, len(new), 'chars')
print('has sb-fixed:', 'class="sb-fixed"' in new)
print('has mint-v2:', '/assets/mint-v2.css' in new)
print('script blocks:', new.count('<script'))
