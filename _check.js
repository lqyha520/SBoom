
const API = '';
let curDiff = 'medium';
let paperData = null;   // {grade, subject, keyword, title, sections:[{type, data}], meta}
let showAnswers = false;

const $ = s => document.querySelector(s);
const TYPE_NAME = { quiz:'选择题', fill_blank:'填空题', match_pair:'连线配对', challenge:'闯关挑战', oral_math:'口算挑战', reading:'阅读理解', vertical_calc:'竖式计算', recursive_calc:'脱式计算', smart_calc:'简便计算' };
const TYPE_ORDER = ['quiz','fill_blank','vertical_calc','recursive_calc','smart_calc','match_pair','oral_math','challenge','reading'];
const CN_NUM = ['一','二','三','四','五','六','七','八','九'];
const DIFF_NAME = { easy:'简单', medium:'中等', hard:'困难' };

/* ── 年级/科目 ── */
async function loadAvailable() {
  try {
    const r = await fetch(API + '/api/v1/scope/available');
    const d = await r.json();
    const grades = Object.keys(d.available);
    $('#grade').innerHTML = '<option value="">请选择年级</option>' +
      grades.map(g => `<option value="${g}">${g}</option>`).join('');
    $('#grade').onchange = () => {
      const g = $('#grade').value;
      const subs = d.available[g] || [];
      $('#subject').disabled = !g;
      $('#subject').innerHTML = `<option value="">请选择科目</option>` +
        subs.map(s => `<option value="${s}">${s}</option>`).join('');
      $('#scopeHint').style.display = 'none';
    };
    $('#subject').onchange = loadScope;
  } catch (e) {
    $('#grade').innerHTML = '<option value="">加载失败，请刷新</option>';
  }
}

async function loadScope() {
  const g = $('#grade').value, s = $('#subject').value;
  if (!g || !s) return;
  try {
    const r = await fetch(API + `/api/v1/scope?grade=${encodeURIComponent(g)}&subject=${encodeURIComponent(s)}`);
    const d = await r.json();
    const box = $('#scopeHint');
    box.style.display = 'block';
    box.innerHTML = `<b>📐 ${g} · ${s} 可出题的知识点</b>（可多选，点击选中/取消，也可在上方手动输入）：<br>` +
      d.allowed.map(k => `<span class="tag">${esc(k)}</span>`).join('');
    box.querySelectorAll('.tag').forEach(t => t.onclick = () => {
      t.classList.toggle('on');
      syncKeywordFromTags();
    });
  } catch (e) {}
}

/* 多选知识点 → 拼入关键词输入框 */
function syncKeywordFromTags() {
  const sel = [...document.querySelectorAll('#scopeHint .tag.on')].map(t => t.textContent);
  $('#keyword').value = sel.join('、');
}

/* ── 题型多选 ── */
document.querySelectorAll('.type-item').forEach(item => {
  item.onclick = (e) => {
    if (e.target.tagName === 'INPUT') return;
    item.classList.toggle('on');
  };
});

/* ── 难度 ── */
document.querySelectorAll('.diff').forEach(d => d.onclick = () => {
  document.querySelectorAll('.diff').forEach(x => x.classList.remove('on-1','on-2','on-3'));
  d.classList.add(d.dataset.v === 'easy' ? 'on-1' : d.dataset.v === 'medium' ? 'on-2' : 'on-3');
  curDiff = d.dataset.v;
});

/* ── 生成（每次都是全新题目，不使用缓存） ── */
async function doGenerate() {
  const grade = $('#grade').value, subject = $('#subject').value, keyword = $('#keyword').value.trim();
  if (!grade || !subject || !keyword) { alert('请先选好年级、科目，并填写知识点关键词～'); return; }

  const picked = [];
  document.querySelectorAll('.type-item.on').forEach(it => {
    const n = parseInt(it.querySelector('input').value) || 1;
    picked.push({ type: it.dataset.v, count: Math.min(10, Math.max(1, n)) });
  });
  if (!picked.length) { alert('至少勾选一种题型～'); return; }

  const btn = $('#btnGo'), btn2 = $('#btnRegen');
  btn.disabled = true; btn.textContent = '出题中…';
  btn2.disabled = true; btn2.textContent = '出题中…';
  $('#loadingBar').style.display = 'block';
  $('#errBox').style.display = 'none';
  $('#resultArea').style.display = 'none';

  try {
    const results = await Promise.all(picked.map(p =>
      fetch(API + '/api/v1/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          grade, subject, keyword,
          game_type: p.type, difficulty: curDiff,
          question_count: p.count, use_cache: false
        })
      }).then(async r => {
        if (!r.ok) {
          const e = await r.json().catch(() => ({}));
          throw new Error(`${TYPE_NAME[p.type]}：${e.detail?.error || r.status}`);
        }
        return r.json();
      })
    ));

    paperData = {
      grade, subject, keyword,
      title: $('#titleInput').value.trim(),
      sections: picked.map((p, i) => ({ type: p.type, data: results[i] })),
    };
    showAnswers = false;
    $('#btnPreviewAns').textContent = '👁 预览答案';
    renderPaper();
    $('#resultArea').style.display = 'block';
    $('#resultArea').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (err) {
    const eb = $('#errBox');
    eb.style.display = 'block';
    eb.textContent = '⚠ 生成失败：' + err.message + '（可稍等重试）';
  } finally {
    btn.disabled = false; btn.textContent = '生成试卷';
    btn2.disabled = false; btn2.textContent = '🔄 重新生成';
    $('#loadingBar').style.display = 'none';
  }
}
$('#btnGo').onclick = doGenerate;
$('#btnRegen').onclick = doGenerate;

/* ── 渲染试卷 ── */
function esc(s) { return String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

function ansText(q) {
  if (q.options && typeof q.answer === 'number') return String.fromCharCode(65 + q.answer);
  if (Array.isArray(q.answer)) return q.answer.map(p => `${p[0]+1}－${p[1]+1}`).join('，');
  return String(q.answer);
}

/* 剥掉 LLM 可能误带的选项字母前缀（如 "A." "B：" "(C)" "D、"），避免出现 "A. A" 重复 */
function stripOptPrefix(o) {
  const m = String(o).trim().match(/^(?:[（(][A-H][）)]|[A-H](?:\.|:|：|、|．|\)|）))\s*(.+)$/);
  return m ? m[1] : String(o);
}

function renderPaper() {
  const d = paperData;

  // 大题按固定顺序排列（客观题→计算题→主观题）；人工排版过的卷子保持用户顺序
  if (!d._manualOrder) {
    d.sections.sort((a, b) => TYPE_ORDER.indexOf(a.type) - TYPE_ORDER.indexOf(b.type));
  }

  // 全局题号 + 稳定qid（供排版模式 DOM↔数据双向绑定）
  let no = 0;
  d.sections.forEach(sec => sec.data.questions.forEach(q => { no++; q._no = no; q._qid = q._qid || `q${no}_${Math.random().toString(36).slice(2,7)}`; }));
  d.allQs = d.sections.flatMap(s => s.data.questions);
  const totalQ = no;

  // 分值：客观题(有选项)每题2分，其余平摊剩余，总和恒为 100
  const isObj = q => !!q.options;
  const objQs = [], subQs = [];
  d.sections.forEach(sec => sec.data.questions.forEach(q => (isObj(q) ? objQs : subQs).push(q)));
  const score = new Map();
  if (subQs.length) {
    objQs.forEach(q => score.set(q, 2));
    let remain = Math.max(100 - objQs.length * 2, subQs.length);
    const base = Math.floor(remain / subQs.length);
    let extra = remain - base * subQs.length;
    subQs.forEach(q => { score.set(q, base + (extra-- > 0 ? 1 : 0)); });
  } else {
    const base = Math.floor(100 / totalQ);
    let extra = 100 - base * totalQ;
    d.allQs.forEach(q => { score.set(q, base + (extra-- > 0 ? 1 : 0)); });
  }
  const secTotal = sec => sec.data.questions.reduce((s, q) => s + score.get(q), 0);

  $('#sumLine').textContent = `📋 ${d.grade} ${d.subject} ｜ ${d.keyword} ｜ 共 ${totalQ} 题（${d.sections.map(s => `${TYPE_NAME[s.type]}×${s.data.questions.length}`).join(' + ')}）｜ 满分 100 分`;

  // ── 学生卷 ──
  let html = `<div class="paper"><div class="exam">`;
  html += `<h1>${esc(d.title || (d.grade + d.subject + '测试卷'))}</h1>`;
  html += `<div class="sub-line">范围：${esc(d.keyword)} ｜ 难度：${DIFF_NAME[curDiff]} ｜ 满分 100 分 ｜ 时间 60 分钟</div>`;
  html += `<div class="info-row"><div>姓名：<span>&nbsp;</span></div><div>班级：<span>&nbsp;</span></div><div>学号：<span>&nbsp;</span></div><div>得分：<span>&nbsp;</span></div></div>`;
  html += `<div class="notice"><b>注意事项：</b>① 答题前请将姓名、班级填写清楚；② 选择题答案填入答题卡；③ 保持卷面整洁，字迹工整。</div>`;

  d.sections.forEach((sec, si) => {
    const qs = sec.data.questions;
    sec._sid = sec._sid || `s${si}_${Math.random().toString(36).slice(2,7)}`;
    html += `<div class="sec-block" data-type="${sec.type}" data-sid="${sec._sid}">`;
    html += `<h2 class="sec"><span>${CN_NUM[si]}、${TYPE_NAME[sec.type]}</span><span class="score-box">共 ${secTotal(sec)} 分</span></h2>`;

    if (sec.type === 'reading' && sec.data.passage) {
      html += `<div class="reading-box" data-e="passage">${esc(sec.data.passage).replace(/\n/g, '<br>')}</div>`;
    }

    qs.forEach(q => {
      const lv = q.difficulty_level ? `<span class="lv">[第${q.difficulty_level}关]</span> ` : '';
      const stem = q.stem ? esc(q.stem) : '请把左右两组中相互对应的内容用线连起来。';
      html += `<div class="q" data-qid="${q._qid}"><div data-e="stem">${q._no}. ${lv}${stem}</div>`;
      if (q.options) {
        html += `<div class="opts" data-e="opts">` + q.options.map((o, j) =>
          `<div>${String.fromCharCode(65 + j)}. ${esc(stripOptPrefix(o))}</div>`).join('') + `</div>`;
      } else if (q.left_items) {
        html += `<table class="match-table" data-e="match"><tr><th style="width:50%">左栏</th><th style="width:50%">右栏</th></tr>`;
        q.left_items.forEach((lft, i) => {
          html += `<tr data-i="${i}"><td>（${i + 1}）${esc(lft)}</td><td>（${i + 1}）${esc(q.right_items[i])}</td></tr>`;
        });
        html += `</table>`;
      } else if (q.type === 'oral_math' || sec.type === 'oral_math') {
        html += `<div class="opts one"><div>得数：<span class="blank">&nbsp;</span></div></div>`;
      } else if (q.type === 'vertical_calc' || sec.type === 'vertical_calc') {
        html += `<div class="calc-area"></div>`;
      } else if (q.type === 'recursive_calc' || q.type === 'smart_calc' || sec.type === 'recursive_calc' || sec.type === 'smart_calc') {
        html += `<div class="calc-area tall"></div>`;
      } else if (q.type !== 'fill_blank' && sec.type !== 'fill_blank') {
        html += `<div class="opts one"><div>答：<span class="blank">&nbsp;</span></div></div>`;
      }
      html += `</div>`;
    });

    const objInSec = qs.filter(q => q.options);
    if (objInSec.length) {
      html += `<table class="answer-sheet"><tr><th>题号</th>`;
      objInSec.forEach(q => { html += `<th>${q._no}</th>`; });
      html += `</tr><tr><td>答案</td>`;
      objInSec.forEach(() => { html += `<td></td>`; });
      html += `</tr></table>`;
    }
    html += `</div>`;  // sec-block
  });
  html += `<div class="footer-note">—— 卷终 · 认真检查，你一定行！——</div>`;
  html += `</div></div><div class="paper-breaker"></div>`;

  // ── 答案页 ──
  html += `<div class="paper"><div class="exam"><h1 style="font-size:16pt;">参考答案与解析</h1>`;
  d.sections.forEach((sec, si) => {
    html += `<h2 class="sec"><span>${CN_NUM[si]}、${TYPE_NAME[sec.type]}</span></h2>`;
    sec.data.questions.forEach(q => {
      let a;
      if (sec.type === 'match_pair') {
        a = q.answer.map(p => `（${p[0] + 1}）→（${p[1] + 1}）`).join('；');
      } else {
        a = ansText(q);
        if (q.options && typeof q.answer === 'number') a += `（${stripOptPrefix(q.options[q.answer])}）`;
      }
      html += `<div class="ans-item">${q._no}. <span class="ans-mark">${esc(a)}</span><div class="ans-why">${esc(q.analysis || '')}</div></div>`;
    });
  });
  html += `</div></div>`;

  $('#paperStack').innerHTML = html;
}

/* ── 预览答案 / 打印 ── */
$('#btnPreviewAns').onclick = () => {
  showAnswers = !showAnswers;
  if (showAnswers) fillBlanks(); else clearBlanks();
  $('#btnPreviewAns').textContent = showAnswers ? '👁 隐藏答案' : '👁 预览答案';
};

function fillBlanks() {
  if (!paperData) return;
  document.querySelectorAll('#paperStack .paper:first-child .q').forEach(el => {
    if (el.querySelector('.q-ans-inline')) return;
    const num = parseInt(el.querySelector('div').textContent);
    const q = paperData.allQs.find(x => x._no === num);
    if (!q) return;
    let a;
    if (q.left_items) {
      a = q.answer.map(p => `（${p[0] + 1}）→（${p[1] + 1}）`).join('；');
    } else {
      a = ansText(q);
      if (q.options && typeof q.answer === 'number') a += `（${stripOptPrefix(q.options[q.answer])}）`;
    }
    const span = document.createElement('div');
    span.className = 'q-ans-inline';
    span.style.cssText = 'color:#d0342c;font-weight:600;font-size:10.5pt;margin-top:1mm;';
    span.textContent = `✎ 答案：${a}`;
    el.appendChild(span);
  });
}
function clearBlanks() {
  document.querySelectorAll('#paperStack .q-ans-inline').forEach(el => el.remove());
}

/* ── 人工排版模式（SortableJS 拖拽 + contenteditable 编辑）── */
let layoutMode = false;
let sortables = [];

function initLayoutMode() {
  const stack = $('#paperStack');
  const tip = document.createElement('div');
  tip.className = 'layout-tip';
  tip.innerHTML = `<b>✏️ 排版模式</b>：拖 ⠿ 调整顺序（题目可跨大题移动）｜虚线框文字点击可直接修改｜✕ 删除题目或大题｜完成后点「✅ 完成排版」重新计算题号与分值`;
  stack.parentNode.insertBefore(tip, stack);

  $('#btnLayout').onclick = () => {
    if (!paperData) return;
    if (showAnswers) { $('#btnPreviewAns').click(); }
    exitLayout(false);
    enterLayout();
  };
  $('#btnLayoutDone').onclick = () => exitLayout(true);
}

/* 进入排版：激活 Sortable + contenteditable + 注入工具按钮 */
function enterLayout() {
  layoutMode = true;
  $('#paperStack').classList.add('layouting');
  $('#btnLayout').style.display = 'none';
  $('#btnLayoutDone').style.display = '';
  $('.layout-tip').style.display = 'block';

  const paper = $('#paperStack .paper');
  if (!paper) return;

  // 大题工具条（删除大题）
  paper.querySelectorAll('.sec-block').forEach(secEl => {
    const tools = document.createElement('div');
    tools.className = 'sec-tools';
    tools.innerHTML = `<span class="tool-btn del" data-act="del-sec">✕ 删除整题（大题）</span>`;
    secEl.insertBefore(tools, secEl.firstChild);
  });

  // 题目工具条 + 拖拽手柄 + 可编辑字段
  paper.querySelectorAll('.q').forEach((qEl, qi) => {
    const tools = document.createElement('div');
    tools.className = 'q-tools';
    tools.innerHTML = `<span class="tool-btn del" data-act="del-q">✕ 删</span>`;
    qEl.appendChild(tools);
    const stem = qEl.querySelector('[data-e="stem"]');
    if (stem) {
      const h = document.createElement('span');
      h.className = 'sort-handle';
      h.textContent = '⠿';
      stem.appendChild(h);
      qEl._dragHandle = h;
    }
    qEl.querySelectorAll('[data-e]').forEach(ed => {
      ed.contentEditable = 'true';
      ed.spellcheck = false;
    });
  });

  // 初始化 Sortable：外层大题排序 + 内层题目排序（共享 group，可跨大题拖）
  if (typeof Sortable !== 'undefined') {
    sortables = [];
    new Sortable(paper.querySelector('.exam'), {
      animation: 150,
      handle: 'h2.sec',
      draggable: '.sec-block',
      ghostClass: 'sortable-ghost',
      onEnd: syncFromDOM
    });
    paper.querySelectorAll('.sec-block').forEach(secEl => {
      sortables.push(new Sortable(secEl, {
        group: 'questions',
        animation: 150,
        handle: '.sort-handle',
        draggable: '.q',
        ghostClass: 'sortable-ghost',
        onEnd: syncFromDOM
      }));
    });
  }
}

/* 退出排版：回写数据 + 重渲染（重新编号、重新算分） */
function exitLayout(apply) {
  if (!layoutMode) return;
  if (apply) syncFromDOM();
  layoutMode = false;
  sortables.forEach(s => s.destroy());
  sortables = [];
  $('#paperStack').classList.remove('layouting');
  $('#btnLayout').style.display = '';
  $('#btnLayoutDone').style.display = 'none';
  $('.layout-tip').style.display = 'none';
  if (apply) renderPaper();
}

/* DOM → 数据回写：顺序、编辑文本、删除 */
function syncFromDOM() {
  if (!paperData) return;
  const paper = $('#paperStack .paper');
  if (!paper) return;

  // 1) 读取顺序与编辑内容
  const secs = [];
  paper.querySelectorAll('.sec-block').forEach(secEl => {
    const sid = secEl.dataset.sid;
    const sec = paperData.sections.find(s => s._sid === sid);
    if (!sec) return;
    sec._used = true;
    const qs = [];
    secEl.querySelectorAll(':scope > .q').forEach(qEl => {
      const q = findQByQid(qEl);
      if (!q) return;
      if (layoutMode) writeBackQ(qEl, q);
      qs.push(q);
    });
    secs.push({ type: sec.type, _sid: sec._sid, data: { ...sec.data, questions: qs } });
  });
  paperData.sections.forEach(s => delete s._used);

  // 2) 删除的大题/题目不再出现在数据里（上面重建时已天然剔除）
  paperData.sections = secs;

  // 3) 全量重新编号 + 标记人工顺序
  renumberAll();
  paperData._manualOrder = true;
}

/* 由 DOM 的 data-qid 精确反查题目对象（跨大题移动/删题后依然稳定） */
function findQByQid(qEl) {
  const qid = qEl.dataset.qid;
  return qid ? paperData.allQs.find(x => x._qid === qid) : null;
}

/* 编辑内容回写到题目对象 */
function writeBackQ(qEl, q) {
  const stemEl = qEl.querySelector('[data-e="stem"]');
  if (stemEl) {
    let t = stemEl.textContent.replace(/\s*⠿\s*$/, '').trim();
    const m = t.match(/^(\d+)\s*[.、]?\s*(.*)$/s);
    if (m) {
      q.stem = m[2].trim() || q.stem;
    }
  }
  const optsEl = qEl.querySelector('[data-e="opts"]');
  if (optsEl && q.options) {
    const lines = Array.from(optsEl.querySelectorAll(':scope > div')).map(d => d.textContent.replace(/^[A-H][.、:：]\s*/, '').trim()).filter(Boolean);
    if (lines.length) q.options = lines;
  }
  const matchEl = qEl.querySelector('[data-e="match"]');
  if (matchEl && q.left_items) {
    matchEl.querySelectorAll('tr[data-i]').forEach(tr => {
      const i = parseInt(tr.dataset.i);
      const tds = tr.querySelectorAll('td');
      if (tds.length === 2 && i < q.left_items.length) {
        q.left_items[i] = tds[0].textContent.replace(/^（\d+）\s*/, '').trim();
        q.right_items[i] = tds[1].textContent.replace(/^（\d+）\s*/, '').trim();
        q.left_items[i] = q.left_items[i] || ' ';
        q.right_items[i] = q.right_items[i] || ' ';
      }
    });
  }
}

/* 重新编号 + 计分 + 更新汇总行 */
function renumberAll() {
  let no = 0;
  paperData.sections.forEach(sec => sec.data.questions.forEach(q => { no++; q._no = no; }));
  paperData.allQs = paperData.sections.flatMap(s => s.data.questions);
  $('#sumLine').textContent = `📋 ${paperData.grade} ${paperData.subject} ｜ ${paperData.keyword} ｜ 共 ${no} 题（${paperData.sections.map(s => `${TYPE_NAME[s.type]}×${s.data.questions.length}`).join(' + ')}）｜ 满分 100 分`;
}

/* 删除按钮（事件委托） */
document.addEventListener('click', e => {
  const btn = e.target.closest('.tool-btn[data-act]');
  if (!btn || !layoutMode) return;
  const act = btn.dataset.act;
  if (act === 'del-q') {
    if (confirm('确定删除这道题吗？')) {
      btn.closest('.q').remove();
      syncFromDOM();
    }
  } else if (act === 'del-sec') {
    if (confirm('确定删除整个大题（含所有题目和答题卡）吗？')) {
      btn.closest('.sec-block').remove();
      syncFromDOM();
    }
  }
});


/* ── 存 PDF：点击直接下载，不走打印对话框 ── */
$('#btnPrint').onclick = () => exportPDF(false, $('#btnPrint'));
$('#btnPrintAns').onclick = () => exportPDF(true, $('#btnPrintAns'));

/* ── 导出 PNG：按 A4 尺寸切页，超出一页自动分多张 ── */
$('#btnPNG').onclick = () => exportPNG(false, $('#btnPNG'));
$('#btnPNGAns').onclick = () => exportPNG(true, $('#btnPNGAns'));

/* 共用：离屏渲染试卷 → 按A4比例切成页画布数组 */
async function buildPageCanvases(withAnswers) {
  if (typeof html2canvas === 'undefined') throw new Error('组件加载失败，请检查网络后刷新重试');
  clearBlanks();   // 卷面始终是干净的学生卷，答案只出现在末尾答案页

  // 离屏克隆试卷，去掉屏幕装饰，固定为 A4 版式
  const holder = document.createElement('div');
  holder.style.cssText = 'position:fixed;left:-99999px;top:0;background:#fff;z-index:-1;';
  const clone = $('#paperStack').cloneNode(true);
  clone.querySelectorAll('.paper-breaker').forEach(b => b.remove());
  clone.querySelectorAll('.paper').forEach(p => {
    p.style.cssText = 'width:210mm;max-width:none;margin:0;padding:15mm 16mm 20mm;border:none;box-shadow:none;background:#fff;';
  });
  // 学生卷：只保留第一张试卷；含答案版：完整学生卷 + 末尾独立的参考答案页
  if (!withAnswers) clone.querySelectorAll('.paper:not(:first-child)').forEach(p => p.remove());
  holder.appendChild(clone);
  document.body.appendChild(holder);

  const pages = [];
  try {
    for (const paper of clone.querySelectorAll('.paper')) {
      // 高分辨率渲染（约 288 DPI）
      const canvas = await html2canvas(paper, { scale: 3, backgroundColor: '#ffffff' });
      const W = canvas.width;
      const pageH = Math.round(W * 297 / 210);   // A4 比例页高

      // 收集块级元素的分界位置（避免把题目从中间切开）
      const scale = W / paper.offsetWidth;
      const breaks = [];
      paper.querySelectorAll('.exam > *').forEach(el => {
        breaks.push(Math.round(el.offsetTop * scale) + Math.round(el.offsetHeight * scale));
      });
      breaks.sort((a, b) => a - b);

      // 逐页切片
      let y = 0;
      while (y < canvas.height - 2) {
        let cut = y + pageH;
        if (cut < canvas.height) {
          // 优先在元素边界处断页
          const ok = breaks.filter(b => b > y + pageH * 0.55 && b <= cut);
          if (ok.length) cut = ok[ok.length - 1];
        } else { cut = canvas.height; }
        const h = cut - y;

        const page = document.createElement('canvas');
        page.width = W; page.height = pageH;
        const ctx = page.getContext('2d');
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, W, pageH);
        ctx.drawImage(canvas, 0, y, W, h, 0, 0, W, h);
        pages.push(page);
        y = cut;
      }
    }
  } finally {
    document.body.removeChild(holder);
  }
  return pages;
}

/* 统一的按钮状态管理 */
async function withExportState(btn, job) {
  const wasShown = showAnswers;
  const old = btn.textContent;
  btn.disabled = true; btn.textContent = '导出中…';
  try {
    await job();
  } catch (e) {
    alert('导出失败：' + e.message);
  } finally {
    btn.disabled = false; btn.textContent = old;
    if (wasShown) fillBlanks(); else clearBlanks();  // 恢复原预览状态
  }
}

async function exportPDF(withAnswers, btn) {
  if (!paperData) return;
  if (layoutMode) exitLayout(true);
  await withExportState(btn, async () => {
    if (typeof window.jspdf === 'undefined') throw new Error('PDF 组件加载失败，请检查网络后刷新重试');
    const pages = await buildPageCanvases(withAnswers);
    const { jsPDF } = window.jspdf;
    const doc = new jsPDF({ unit: 'mm', format: 'a4', orientation: 'portrait' });
    pages.forEach((pc, i) => {
      if (i) doc.addPage();
      doc.addImage(pc.toDataURL('image/jpeg', 0.92), 'JPEG', 0, 0, 210, 297);
    });
    // 页码：仅显示页数，无其他页眉页脚
    const total = pages.length;
    doc.setFont('times', 'normal');
    doc.setFontSize(9);
    for (let i = 1; i <= total; i++) {
      doc.setPage(i);
      const t = `- ${i} / ${total} -`;
      doc.text(t, 105, 292.5, { align: 'center' });
    }
    const title = paperData.title || (paperData.grade + paperData.subject + '测试卷');
    doc.save(`${title}${withAnswers ? '（含答案）' : ''}.pdf`);
  });
}

async function exportPNG(withAnswers, btn) {
  if (!paperData) return;
  if (layoutMode) exitLayout(true);
  await withExportState(btn, async () => {
    const pages = await buildPageCanvases(withAnswers);
    const title = paperData.title || (paperData.grade + paperData.subject + '测试卷');
    pages.forEach((pc, i) => {
      const a = document.createElement('a');
      a.href = pc.toDataURL('image/png');
      a.download = `${title}_第${i + 1}页.png`;
      a.click();
    });
  });
}

loadAvailable();
initLayoutMode();

