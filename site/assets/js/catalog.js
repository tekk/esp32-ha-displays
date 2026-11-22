/* catalog page: faceted search, sorting, table/cards, URL state */
(function () {
  'use strict';
  const FACETS = [
    ['vendor', 'Vendor'], ['category', 'Category'], ['mcu_family', 'MCU family'], ['size', 'Size'], ['resolution', 'Resolution'],
    ['panel', 'Panel'], ['touch', 'Touch'], ['interface', 'Display interface'], ['shape', 'Shape'], ['driver_ic', 'Display driver'],
    ['flash', 'Flash'], ['psram', 'PSRAM'], ['sram', 'SRAM'], ['frequency', 'CPU frequency'], ['coprocessor', 'Co-processor'],
    ['wifi', 'Wi-Fi'], ['bt', 'Bluetooth'], ['speaker', 'Speaker'], ['shell', 'Case / shell'], ['tags', 'Tags'],
  ];
  const OPEN_DEFAULT = new Set(['vendor', 'category', 'mcu_family', 'size', 'resolution', 'touch', 'interface', 'tags']);
  const COLS = [
    ['thumb', '', true], ['model', 'Model', true], ['vendor', 'Vendor', true], ['size', 'Size', true], ['resolution', 'Resolution', true],
    ['panel', 'Panel', true], ['touch', 'Touch', true], ['interface', 'Interface', true], ['mcu_family', 'MCU', true], ['mcu', 'MCU part', false],
    ['flash', 'Flash', true], ['psram', 'PSRAM', true], ['sram', 'SRAM', false], ['frequency', 'CPU', false], ['driver_ic', 'Driver', false],
    ['wifi', 'Wi-Fi', false], ['bt', 'BT', false], ['speaker', 'Speaker', false], ['shell', 'Case', false], ['category', 'Category', false],
    ['dimensions', 'Dimensions', false], ['files', 'Files', true], ['tags', 'Tags', false],
  ];
  const SORTS = [['relevance', 'relevance'], ['model', 'model'], ['vendor', 'vendor'], ['size', 'size'], ['resolution', 'resolution (pixels)'],
    ['panel', 'panel'], ['touch', 'touch'], ['interface', 'interface'], ['mcu_family', 'MCU'], ['flash', 'flash'], ['psram', 'PSRAM'], ['sram', 'SRAM'],
    ['frequency', 'CPU frequency'], ['driver_ic', 'driver IC'], ['category', 'category'], ['files', 'number of files']];
  let MODELS = [], BYID = {}, INDEX = null, META = null;
  const st = { q: '', f: {}, sort: 'size', dir: 'asc', view: 'table', cols: null, closed: new Set(), open: new Set() };

  const val = (m, k) => {
    if (k === 'tags') return m.tags;
    if (k === 'files') return m.files.length;
    const v = m.params[k];
    return v == null ? '' : v;
  };
  const sortVal = (m, k) => {
    const p = m.params;
    switch (k) {
      case 'size': return p.size_in == null ? Infinity : p.size_in;
      case 'resolution': return p.pixels == null ? Infinity : p.pixels;
      case 'flash': case 'psram': case 'sram': { const b = toBytes(p[k]); return b == null ? Infinity : b; }
      case 'frequency': { const n = parseFloat((/(\d+(?:\.\d+)?)\s*MHz/i.exec(p.frequency || '') || [])[1]); return isNaN(n) ? Infinity : n; }
      case 'files': return m.files.length;
      case 'model': return m.model.toLowerCase();
      default: return String(val(m, k) || '\uffff').toLowerCase();
    }
  };
  const numericFacet = { size: (v) => parseFloat(v) || 0, resolution: (v) => { const a = v.split('x').map(Number); return a[0] * a[1] || 0; },
    flash: (v) => toBytes(v) || 0, psram: (v) => toBytes(v) || 0, sram: (v) => toBytes(v) || 0, frequency: (v) => parseFloat(v) || 0 };

  // ---------- URL state
  function readHash() {
    const h = new URLSearchParams(location.hash.slice(1));
    st.q = h.get('q') || '';
    st.f = {};
    for (const [k, v] of h) if (k.startsWith('f.')) st.f[k.slice(2)] = new Set(v.split('|').filter(Boolean));
    st.sort = h.get('sort') || (st.q ? 'relevance' : 'size');
    st.dir = h.get('dir') || 'asc';
    st.view = h.get('view') || (localStorage.getItem('gc.view') || 'table');
    const c = h.get('cols') || localStorage.getItem('gc.cols');
    st.cols = c ? new Set(c.split(',')) : new Set(COLS.filter((x) => x[2]).map((x) => x[0]));
  }
  function writeHash() {
    const h = new URLSearchParams();
    if (st.q) h.set('q', st.q);
    for (const [k, s] of Object.entries(st.f)) if (s.size) h.set('f.' + k, [...s].join('|'));
    if (st.sort !== (st.q ? 'relevance' : 'size')) h.set('sort', st.sort);
    if (st.dir !== 'asc') h.set('dir', st.dir);
    if (st.view !== 'table') h.set('view', st.view);
    const s = h.toString();
    history.replaceState(null, '', s ? '#' + s : location.pathname + location.search);
    localStorage.setItem('gc.view', st.view);
    localStorage.setItem('gc.cols', [...st.cols].join(','));
  }

  // ---------- query parsing: free text + key:value filters
  function parseQuery(q) {
    const kv = [], free = [];
    const re = /(\w+)[:=]("([^"]*)"|(\S+))|("([^"]*)")|(\S+)/g;
    let m;
    while ((m = re.exec(q))) {
      if (m[1]) kv.push([m[1].toLowerCase(), (m[3] != null ? m[3] : m[4]).toLowerCase()]);
      else free.push(m[6] != null ? m[6] : m[7]);
    }
    return { kv, free: free.join(' ') };
  }
  const KEY_ALIAS = { tag: 'tags', mcu: 'mcu', size: 'size', res: 'resolution', touch: 'touch', panel: 'panel', iface: 'interface', vendor: 'vendor', driver: 'driver_ic', cat: 'category' };
  function kvMatch(m, k, v) {
    k = KEY_ALIAS[k] || k;
    if (k === 'tags') return m.tags.some((t) => t.toLowerCase().includes(v));
    if (k === 'size') { const n = parseFloat(v); if (!isNaN(n) && m.params.size_in != null) return Math.abs(m.params.size_in - n) < 0.051; }
    if (k === 'mcu') return [m.params.mcu, m.params.mcu_family].some((x) => (x || '').toLowerCase().includes(v));
    const x = m.params[k];
    if (x == null) return k === 'model' ? m.model.toLowerCase().includes(v) : false;
    return String(x).toLowerCase().includes(v);
  }

  // ---------- filtering
  function compute() {
    const { kv, free } = parseQuery(st.q);
    let base = MODELS, scores = null, fallback = false;
    if (free.trim()) {
      const opts = { prefix: true, fuzzy: 0.15, boost: { model: 5, aliases: 4, tags: 2, title: 2, vendor: 2 }, combineWith: 'AND' };
      let res = INDEX.search(free, opts);
      if (!res.length) { res = INDEX.search(free, { ...opts, combineWith: 'OR' }); fallback = res.length > 0; }
      scores = {};
      res.forEach((r) => { scores[r.id] = r.score; });
      base = MODELS.filter((m) => scores[m.id] != null);
    }
    if (kv.length) base = base.filter((m) => kv.every(([k, v]) => kvMatch(m, k, v)));
    const passes = (m, skip) => Object.entries(st.f).every(([k, s]) => {
      if (!s.size || k === skip) return true;
      const v = val(m, k);
      return Array.isArray(v) ? v.some((x) => s.has(x)) : s.has(String(v || '∅'));
    });
    const list = base.filter((m) => passes(m));
    // facet counts (each facet ignores its own selection)
    const counts = {};
    for (const [k] of FACETS) {
      const c = {};
      for (const m of base) {
        if (!passes(m, k)) continue;
        const v = val(m, k);
        (Array.isArray(v) ? v : [String(v || '∅')]).forEach((x) => { c[x] = (c[x] || 0) + 1; });
      }
      // keep selected values visible even with 0
      (st.f[k] || new Set()).forEach((x) => { if (!(x in c)) c[x] = 0; });
      // also show all values (count 0) for discoverability
      for (const m of MODELS) { const v = val(m, k); (Array.isArray(v) ? v : [String(v || '∅')]).forEach((x) => { if (!(x in c)) c[x] = 0; }); }
      counts[k] = c;
    }
    // sorting
    const dir = st.dir === 'desc' ? -1 : 1;
    if (st.sort === 'relevance' && scores) list.sort((a, b) => (scores[b.id] - scores[a.id]) * dir);
    else {
      const k = st.sort === 'relevance' ? 'size' : st.sort;
      list.sort((a, b) => {
        const x = sortVal(a, k), y = sortVal(b, k);
        if (x === y) return a.model.localeCompare(b.model, undefined, { numeric: true });
        if (x === Infinity) return 1; if (y === Infinity) return -1;
        return (x < y ? -1 : 1) * dir;
      });
    }
    return { list, counts, fallback };
  }

  // ---------- rendering
  function renderFacets(counts) {
    const html = FACETS.map(([k, label]) => {
      const c = counts[k];
      let entries = Object.entries(c);
      if (numericFacet[k]) entries.sort((a, b) => (a[0] === '∅') - (b[0] === '∅') || numericFacet[k](a[0]) - numericFacet[k](b[0]));
      else entries.sort((a, b) => (a[0] === '∅') - (b[0] === '∅') || b[1] - a[1] || a[0].localeCompare(b[0]));
      const sel = st.f[k] || new Set();
      const max = Math.max(1, ...entries.map((e) => e[1]));
      const closed = st.open.has(k) ? false : st.closed.has(k) ? true : !OPEN_DEFAULT.has(k) && !sel.size;
      const nonEmpty = entries.filter((e) => e[0] !== '∅').length;
      return `<div class="facet ${closed ? 'closed' : ''}" data-k="${k}"><h4><span>${esc(label)} <span class="na">(${nonEmpty})</span></span><span class="tw">${closed ? '+' : '−'}</span></h4>
        ${entries.length > 12 ? `<input class="small ffilter" placeholder="filter ${esc(label.toLowerCase())}…">` : ''}
        <div class="fv">${entries.map(([v, n]) => `<label class="${n ? '' : 'zero'}" data-v="${esc(v.toLowerCase())}"><input type="checkbox" value="${esc(v)}" ${sel.has(v) ? 'checked' : ''}>
          <span>${v === '∅' ? '<span class="na">(unknown)</span>' : esc(v)}</span><span class="n">${n}</span></label><div class="bar" style="width:${Math.round((n / max) * 100)}%"></div>`).join('')}</div></div>`;
    }).join('');
    $('#facets').innerHTML = html;
    const chips = [];
    for (const [k, s] of Object.entries(st.f)) s.forEach((v) => chips.push(`<span class="chip x" data-k="${k}" data-v="${esc(v)}"><b>${esc(k)}</b>=${esc(v)}</span>`));
    $('#chips').innerHTML = chips.join('') || '<span class="na">None — pick values below or type key:value</span>';
  }
  const cell = (m, k, q) => {
    const p = m.params;
    switch (k) {
      case 'thumb': { const im = m.images[0]; return `<td>${im ? `<a href="${modelURL(m.id)}" data-pv="${esc(m.id)}" tabindex="-1"><img class="th" loading="lazy" src="${esc(im.thumb || im.src)}" alt="${esc(m.model)}"></a>` : ''}</td>`; }
      case 'model': return `<td class="m"><a href="${modelURL(m.id)}" data-pv="${esc(m.id)}">${highlight(m.model, q)}</a>${m.notes.some((n) => n.level === 'warning') ? ' <span class="badge warn" title="variant warning">!</span>' : ''}${m.downloads_only ? ' <span class="badge info" title="only on the file server">fs</span>' : ''}</td>`;
      case 'files': { const a = m.files.filter((f) => f.type === 'archive').length, d = m.files.length - a; return `<td class="dim">${a ? a + '🗜 ' : ''}${d ? d + '📕' : ''}</td>`; }
      case 'tags': return `<td>${m.tags.slice(0, 6).map((t) => `<span class="tag" data-tag="${esc(t)}">${esc(t)}</span>`).join(' ')}</td>`;
      default: { const v = val(m, k); return `<td class="${v ? '' : 'na'}" title="${esc(v)}">${v ? esc(String(v).length > 34 ? String(v).slice(0, 32) + '…' : v) : '—'}</td>`; }
    }
  };
  function renderTable(list) {
    const cols = COLS.filter((c) => st.cols.has(c[0]));
    const head = cols.map(([k, l]) => `<th data-sort="${k === 'thumb' ? '' : k}">${esc(l)}${st.sort === k ? ` <span class="ar">${st.dir === 'asc' ? '▲' : '▼'}</span>` : ''}</th>`).join('');
    const q = parseQuery(st.q).free;
    return `<div class="tblwrap"><table class="grid"><thead><tr>${head}</tr></thead><tbody>${list.map((m) => `<tr>${cols.map((c) => cell(m, c[0], q)).join('')}</tr>`).join('')}</tbody></table></div>`;
  }
  function renderCards(list) {
    const q = parseQuery(st.q).free;
    return `<div class="cards">${list.map((m) => {
      const p = m.params, im = m.images[0];
      const kv = [['size', p.size], ['res', p.resolution], ['mcu', p.mcu_family], ['touch', p.touch], ['iface', p.interface], ['flash', p.flash], ['psram', p.psram]].filter((x) => x[1]);
      return `<div class="card"><a href="${modelURL(m.id)}" class="im" data-pv="${esc(m.id)}" style="background-image:url('${im ? esc(im.thumb || im.src) : ''}')"><span class="vend">${esc(m.vendor)}</span></a>
        <div class="bd"><a class="md" href="${modelURL(m.id)}">${highlight(m.model, q)}</a>
        <div class="kv">${kv.map(([k, v]) => `<span>${k}</span><span>${esc(v)}</span>`).join('')}</div>
        <div class="tags">${m.tags.filter((t) => !t.startsWith('vendor:')).slice(0, 8).map((t) => `<span class="tag" data-tag="${esc(t)}">${esc(t)}</span>`).join('')}</div></div></div>`;
    }).join('')}</div>`;
  }
  function render() {
    const { list, counts, fallback } = compute();
    renderFacets(counts);
    $('#count').innerHTML = `<b>${list.length}</b> / ${MODELS.length} boards${fallback ? ' <span class="na">(no exact match – showing any-term results)</span>' : ''}`;
    hidePop();
    $('#results').innerHTML = list.length ? (st.view === 'cards' ? renderCards(list) : renderTable(list))
      : `<div class="empty">No boards match. Try fewer terms or <a href="#" id="clearall">reset filters</a>.</div>`;
    $('#vtable').classList.toggle('on', st.view === 'table');
    $('#vcards').classList.toggle('on', st.view === 'cards');
    $('#colsmenu').style.display = st.view === 'table' ? '' : 'none';
    $('#sort').value = st.sort;
    $('#dir').textContent = st.dir === 'asc' ? '↑ Asc' : '↓ Desc';
    writeHash();
    window.__lastList = list;
  }
  function toggle(k, v) {
    const s = st.f[k] || (st.f[k] = new Set());
    s.has(v) ? s.delete(v) : s.add(v);
    if (!s.size) delete st.f[k];
    render();
  }
  function exportCSV() {
    const list = window.__lastList || [];
    const keys = ['model', 'vendor', 'category', 'size', 'resolution', 'panel', 'touch', 'interface', 'mcu', 'mcu_family', 'frequency', 'sram', 'psram', 'rom', 'flash', 'driver_ic', 'wifi', 'bt', 'speaker', 'shell', 'dimensions'];
    const q = (s) => '"' + String(s == null ? '' : s).replace(/"/g, '""') + '"';
    const rows = [keys.concat(['tags', 'url']).join(',')].concat(list.map((m) => keys.map((k) => q(k === 'model' ? m.model : k === 'vendor' ? m.vendor : m.params[k])).concat([q(m.tags.join('; ')), q(new URL(modelURL(m.id), location.href).href)]).join(',')));
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([rows.join('\n')], { type: 'text/csv' }));
    a.download = 'guition-catalog.csv';
    a.click();
  }

  // ---------- events
  function bind() {
    const qi = $('#q');
    qi.value = st.q;
    let t;
    qi.addEventListener('input', () => { clearTimeout(t); t = setTimeout(() => { const had = !!st.q; st.q = qi.value.trim(); if (!had && st.q && st.sort === 'size') st.sort = 'relevance'; if (!st.q && st.sort === 'relevance') st.sort = 'size'; render(); }, 120); });
    document.addEventListener('keydown', (e) => { if (e.key === '/' && document.activeElement !== qi && !/input|select|textarea/i.test(document.activeElement.tagName)) { e.preventDefault(); qi.focus(); qi.select(); } if (e.key === 'Escape' && document.activeElement === qi) { qi.value = ''; st.q = ''; render(); } });
    $('#facets').addEventListener('change', (e) => { if (e.target.type === 'checkbox') toggle(e.target.closest('.facet').dataset.k, e.target.value); });
    $('#facets').addEventListener('click', (e) => {
      const h = e.target.closest('h4');
      if (h) { const f = h.parentElement, k = f.dataset.k; const nowClosed = !f.classList.contains('closed'); f.classList.toggle('closed'); h.querySelector('.tw').textContent = nowClosed ? '+' : '−'; if (nowClosed) { st.closed.add(k); st.open.delete(k); } else { st.open.add(k); st.closed.delete(k); } }
    });
    $('#facets').addEventListener('input', (e) => {
      if (!e.target.classList.contains('ffilter')) return;
      const v = e.target.value.toLowerCase();
      $$('label', e.target.parentElement).forEach((l) => { const show = l.dataset.v.includes(v); l.style.display = show ? '' : 'none'; l.nextElementSibling.style.display = show ? '' : 'none'; });
    });
    $('#chips').addEventListener('click', (e) => { const c = e.target.closest('.chip'); if (c) toggle(c.dataset.k, c.dataset.v); });
    $('#results').addEventListener('click', (e) => {
      const th = e.target.closest('th[data-sort]');
      if (th && th.dataset.sort) { const k = th.dataset.sort; if (st.sort === k) st.dir = st.dir === 'asc' ? 'desc' : 'asc'; else { st.sort = k; st.dir = ['files', 'flash', 'psram', 'sram', 'frequency'].includes(k) ? 'desc' : 'asc'; } render(); return; }
      const tg = e.target.closest('.tag[data-tag]');
      if (tg) { e.preventDefault(); toggle('tags', tg.dataset.tag); return; }
      if (e.target.id === 'clearall') { e.preventDefault(); reset(); }
    });
    $('#sort').innerHTML = SORTS.map(([k, l]) => `<option value="${k}">${l}</option>`).join('');
    $('#sort').addEventListener('change', (e) => { st.sort = e.target.value; render(); });
    $('#dir').addEventListener('click', () => { st.dir = st.dir === 'asc' ? 'desc' : 'asc'; render(); });
    $('#vtable').addEventListener('click', () => { st.view = 'table'; render(); });
    $('#vcards').addEventListener('click', () => { st.view = 'cards'; render(); });
    $('#csv').addEventListener('click', exportCSV);
    $('#reset').addEventListener('click', reset);
    $('#colsbtn').addEventListener('click', (e) => { e.stopPropagation(); $('#colsmenu').classList.toggle('open'); });
    document.addEventListener('click', (e) => { if (!e.target.closest('#colsmenu')) $('#colsmenu').classList.remove('open'); });
    $('#colslist').innerHTML = COLS.filter((c) => c[0] !== 'model').map(([k, l]) => `<label><input type="checkbox" value="${k}" ${st.cols.has(k) ? 'checked' : ''}> ${esc(l || 'image')}</label>`).join('');
    $('#colslist').addEventListener('change', (e) => { e.target.checked ? st.cols.add(e.target.value) : st.cols.delete(e.target.value); render(); });
    window.addEventListener('hashchange', () => { readHash(); qi.value = st.q; render(); });
  }
  function reset() { st.q = ''; st.f = {}; st.sort = 'size'; st.dir = 'asc'; $('#q').value = ''; render(); }

  // ---------- hover preview (mouse hover + keyboard focus; no-op on touch – tap opens the detail page)
  const POP_KEYS = [['size', 'Size'], ['resolution', 'Resolution'], ['panel', 'Panel'], ['touch', 'Touch'], ['interface', 'Display interface'], ['driver_ic', 'Display driver'],
    ['mcu', 'MCU'], ['coprocessor', 'Co-processor'], ['frequency', 'CPU'], ['flash', 'Flash'], ['psram', 'PSRAM'], ['sram', 'SRAM'], ['wifi', 'Wi-Fi'], ['bt', 'Bluetooth'],
    ['ethernet', 'Ethernet'], ['rs485', 'RS-485'], ['speaker', 'Speaker'], ['shell', 'Case'], ['dimensions', 'Dimensions'], ['voltage', 'Supply'], ['power', 'Power']];
  const pop = document.createElement('div');
  pop.className = 'pop'; pop.setAttribute('role', 'tooltip'); pop.id = 'boardpop';
  document.body.appendChild(pop);
  let popTimer = null, popFor = null, lastPointer = 'mouse';
  function popHTML(m) {
    const p = m.params, im = m.images.find((i) => i.kind === 'photo') || m.images[0];
    const rows = POP_KEYS.filter(([k]) => p[k]).map(([k, l]) => `<dt>${l}</dt><dd title="${esc(p[k])}">${esc(String(p[k]).length > 60 ? String(p[k]).slice(0, 58) + '…' : p[k])}</dd>`).join('');
    const ports = portsOf(m);
    const warn = m.notes.find((n) => n.level === 'warning');
    return `<div class="ph ${im ? '' : 'none'}">${im ? `<img src="${esc(im.thumb || im.src)}" data-hd="${esc(im.src)}" alt="${esc(m.model)}">${im.kind !== 'photo' ? `<div class="src">${esc(im.kind)} · ${esc(im.note || '')}</div>` : ''}` : 'no photo available'}</div>
      <div class="inf"><h3>${esc(m.model)}</h3><div class="sub">${esc([m.vendor, p.category].filter(Boolean).join(' · '))}</div>
      <dl>${rows}</dl>
      ${ports.length ? `<h4>Ports, connectors &amp; interfaces</h4><ul class="ports">${ports.slice(0, 14).map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}
      ${warn ? `<div class="warnline">⚠ ${esc(warn.text.split('. ')[0])}.</div>` : ''}</div>`;
  }
  function placePop(anchor) {
    const r = anchor.getBoundingClientRect(), vw = window.innerWidth, vh = window.innerHeight, gap = 14;
    const pw = pop.offsetWidth, ph = pop.offsetHeight;
    let x = r.right + gap;
    if (x + pw > vw - 8) x = r.left - gap - pw;
    if (x < 8) x = Math.max(8, Math.min(vw - pw - 8, r.left));
    let y = r.top + r.height / 2 - ph / 2;
    if (x < r.right && x + pw > r.left) y = r.bottom + gap + ph > vh - 8 ? r.top - gap - ph : r.bottom + gap;   // overlapping horizontally → above/below
    y = Math.max(8, Math.min(vh - ph - 8, y));
    pop.style.left = Math.round(x) + 'px'; pop.style.top = Math.round(y) + 'px';
  }
  function showPop(anchor) {
    const m = BYID[anchor.dataset.pv];
    if (!m) return;
    popFor = anchor;
    pop.innerHTML = popHTML(m);
    pop.classList.add('on');
    anchor.setAttribute('aria-describedby', 'boardpop');
    placePop(anchor);
    const img = pop.querySelector('img[data-hd]');
    if (img && img.dataset.hd !== img.getAttribute('src')) { const hd = new Image(); hd.onload = () => { if (popFor === anchor) { img.src = hd.src; placePop(anchor); } }; hd.src = img.dataset.hd; }
    if (img) img.onload = () => { if (popFor === anchor) placePop(anchor); };
  }
  function hidePop() { clearTimeout(popTimer); if (popFor) popFor.removeAttribute('aria-describedby'); popFor = null; pop.classList.remove('on'); }
  function bindPop() {
    const res = $('#results');
    res.addEventListener('pointerover', (e) => { lastPointer = e.pointerType || 'mouse'; const a = e.target.closest('[data-pv]'); if (!a || lastPointer !== 'mouse') return; if (a === popFor) return; clearTimeout(popTimer); popTimer = setTimeout(() => showPop(a), 280); });
    res.addEventListener('pointerout', (e) => { const a = e.target.closest('[data-pv]'); if (!a || (e.relatedTarget && a.contains(e.relatedTarget))) return; hidePop(); });
    res.addEventListener('focusin', (e) => { const a = e.target.closest('[data-pv]'); if (a && lastPointer !== 'touch') { clearTimeout(popTimer); popTimer = setTimeout(() => showPop(a), 150); } });
    res.addEventListener('focusout', hidePop);
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') hidePop(); });
    window.addEventListener('scroll', () => { if (popFor) hidePop(); }, { passive: true, capture: true });
    window.addEventListener('resize', () => { if (popFor) hidePop(); });
  }

  header('models');
  readHash();
  Promise.all([getJSON('data/models.json'), getJSON('data/meta.json'), loadIndex('data/search-models.json', MODEL_INDEX_OPTS)]).then(([models, meta, idx]) => {
    MODELS = models; META = meta; INDEX = idx;
    models.forEach((m) => { BYID[m.id] = m; });
    const c = meta.counts;
    $('#stats').innerHTML = `<span><b>${models.length}</b> boards</span>` + Object.entries(c).map(([v, n]) => `<span>${esc(v)}: <b>${n}</b></span>`).join('')
      + `<span><b>${meta.archives}</b> archives (${fmtBytes(meta.archive_bytes)})</span><span><b>${meta.hosted_blobs}</b> docs hosted</span><span>updated <b>${esc(meta.generated.slice(0, 10))}</b></span>`;
    bind();
    bindPop();
    render();
    footer(meta);
  }).catch((e) => { $('#results').innerHTML = `<div class="empty">failed to load data: ${esc(e.message)}<br>serve the site over http (python3 -m http.server -d site)</div>`; });
})();
