/* full-text search over hosted documentation inside the archives (lazy-loaded prebuilt MiniSearch index) */
(function () {
  'use strict';
  header('docs');
  const app = $('#app');
  app.innerHTML = `<div class="hero"><h1>Documentation search</h1>
    <p class="na">Full-text search across extracted text of PDFs, READMEs, markdown and selected source files from all Guition archives (file names + first pages). Chinese supported (bigram search). Results open in the built-in viewer.</p></div>
    <div class="search"><input id="q" placeholder="e.g. JD9165, GT911 i2c address, 原理图, lvgl config, backlight pwm" autofocus></div>
    <div class="toolbar"><select id="arch" class="small"><option value="">all archives</option></select>
      <label class="count"><input type="checkbox" id="names"> file names only</label>
      <span class="count" id="cnt"></span></div>
    <div id="res"><div class="empty loading">loading index (~10 MB, once)</div></div>`;
  let IDX = null, SNIP = {}, META = null;
  const st = new URLSearchParams(location.hash.slice(1));
  $('#q').value = st.get('q') || '';
  Promise.all([loadIndex('data/search-docs.json', DOCS_INDEX_OPTS), getJSON('data/docs-snippets.json'), getJSON('data/meta.json'), getJSON('data/archives.json')]).then(([idx, snip, meta, arch]) => {
    IDX = idx; SNIP = snip; META = meta;
    const opts = arch.filter((a) => a.type === 'archive' || a.hosted).map((a) => `<option value="${esc(a.slug)}">${esc(a.dir)} / ${esc(a.name)}</option>`).join('');
    $('#arch').insertAdjacentHTML('beforeend', opts);
    if (st.get('a')) $('#arch').value = st.get('a');
    run();
    footer(meta);
  });
  function run() {
    const q = $('#q').value.trim();
    const a = $('#arch').value;
    const h = new URLSearchParams(); if (q) h.set('q', q); if (a) h.set('a', a);
    history.replaceState(null, '', '#' + h.toString());
    if (!IDX) return;
    if (!q) { $('#res').innerHTML = `<div class="empty">${IDX.documentCount} documents indexed. Type to search.</div>`; $('#cnt').textContent = ''; return; }
    const o = { prefix: (t) => t.length > 2, fuzzy: (t) => (t.length > 5 ? 0.15 : 0), combineWith: 'AND', boost: { p: 2 } };
    if ($('#names').checked) o.fields = ['p'];
    if (a) o.filter = (r) => r.a === a;
    let r = IDX.search(q, o);
    if (!r.length) r = IDX.search(q, { ...o, combineWith: 'OR' });
    $('#cnt').textContent = r.length + ' hits';
    const terms = q.toLowerCase().split(/\s+/).filter(Boolean);
    $('#res').innerHTML = r.slice(0, 200).map((x) => {
      const url = x.b ? viewerURL(x.a, x.p) : (x.u ? fileViewerURL(x.u, x.p.split('/').pop()) : '#');
      const models = (META.slug2models[x.a] || []).slice(0, 5).join(', ');
      return `<div class="docres"><a class="p" href="${url}">${highlight(x.p, terms.join(' '))}</a>
        <div class="a">🗜 ${esc(x.a)}${models ? ' · ' + esc(models) : ''} · score ${x.score.toFixed(1)}</div>
        <div class="s">${highlight((SNIP[x.id] || '').replace(/\s+/g, ' '), terms.join(' '))}…</div></div>`;
    }).join('') + (r.length > 200 ? '<div class="na">showing first 200</div>' : '') || '<div class="empty">no results</div>';
  }
  let t; $('#q').addEventListener('input', () => { clearTimeout(t); t = setTimeout(run, 200); });
  $('#arch').addEventListener('change', run); $('#names').addEventListener('change', run);
})();
