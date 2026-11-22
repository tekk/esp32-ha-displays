/* shared helpers for GUITION//CATALOG (no build step, plain ES2019) */
(function (G) {
  'use strict';
  const cache = {};
  G.$ = (sel, el) => (el || document).querySelector(sel);
  G.$$ = (sel, el) => Array.from((el || document).querySelectorAll(sel));
  G.getJSON = (url) => cache[url] || (cache[url] = fetch(url).then((r) => { if (!r.ok) throw new Error(url + ' → HTTP ' + r.status); return r.json(); }));
  G.esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  G.fmtBytes = (n) => { if (n == null || isNaN(n)) return ''; const u = ['B', 'KB', 'MB', 'GB']; let i = 0; while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; } return n.toFixed(i ? 1 : 0) + ' ' + u[i]; };
  G.qparam = (k) => new URLSearchParams(location.search).get(k);
  G.KIND_ICON = { pdf: '📕', image: '🖼', markdown: '📝', html: '🌐', text: '📄', code: '⌨', office: '📊', archive: '🗜', other: '·', dir: '▸' };
  G.viewerURL = (slug, path) => 'viewer.html?a=' + encodeURIComponent(slug) + (path ? '&p=' + encodeURIComponent(path) : '');
  G.fileViewerURL = (hosted, name) => 'viewer.html?f=' + encodeURIComponent(hosted) + (name ? '&n=' + encodeURIComponent(name) : '');
  G.modelURL = (id) => 'model.html?id=' + encodeURIComponent(id);
  // parse "16MB" / "384KB" / "32MB (in package)" to bytes for sorting
  G.toBytes = (s) => { const m = /(\d+(?:\.\d+)?)\s*(K|M|G)B?/i.exec(s || ''); if (!m) return null; return parseFloat(m[1]) * { K: 1024, M: 1048576, G: 1073741824 }[m[2].toUpperCase()]; };
  // primary (offline) download button + badge; original server URL becomes a secondary mirror link
  G.offlineLinks = (off, name, original) => {
    const out = [];
    if (off) {
      const where = off.type === 'local' ? 'this site' : 'GitHub release';
      if (off.parts) {
        out.push(`<span class="badge ok" title="sha256 ${G.esc(off.sha256)}">offline · ${where}</span>`);
        off.parts.forEach((u, i) => out.push(`<a class="btn pri" href="${G.esc(u)}">⇩ part ${i + 1}/${off.parts.length}</a>`));
        out.push(`<span class="na" title="rejoin">cat *.0?? &gt; ${G.esc(name)}</span>`);
      } else {
        out.push(`<a class="btn pri" href="${G.esc(off.url)}" ${off.type === 'local' ? `download="${G.esc(name)}"` : ''} title="sha256 ${G.esc(off.sha256)}">⇩ download</a>`,
          `<span class="badge ok" title="stored on ${where}${off.size ? ', ' + G.fmtBytes(off.size) : ''}">offline · ${where}</span>`);
      }
    }
    if (original) out.push(`<a class="btn" href="${G.esc(original)}" rel="noopener" target="_blank" title="original vendor server">↗ mirror: original</a>`);
    return out.join(' ');
  };
  G.header = (active) => {
    const nav = [['index.html', 'catalog', 'models'], ['docs.html', 'docs-search', 'docs'], ['files.html', 'archives', 'files'], ['about.html', 'about', 'about']];
    const el = document.createElement('header');
    el.className = 'topbar';
    el.innerHTML = `<a class="brand" href="index.html">GUITION<span class="sl">//</span>CATALOG<small>esp32 display boards</small></a>
      <nav class="nav">${nav.map(([h, t, k]) => `<a href="${h}" class="${k === active ? 'active' : ''}">./${t}</a>`).join('')}</nav>
      <div class="prompt">root@guition:~$ <b id="promptcmd">${G.esc(G.promptText || 'ls -la ./boards')}</b> <span class="cursor"></span></div>`;
    document.body.prepend(el);
  };
  G.footer = (meta) => {
    const el = document.createElement('footer');
    el.className = 'footer';
    el.innerHTML = `Data scraped from <a href="https://www.guition.com/model-selection">guition.com</a>, the official Guition file server <a href="https://pan.jczn1688.com/">pan.jczn1688.com</a>, <a href="https://www.waveshare.com/">waveshare.com</a> / <a href="https://docs.waveshare.com/">docs.waveshare.com</a> and community repositories. `
      + `Unofficial, not affiliated with Guition or Waveshare. Every parameter links to its source; empty = unknown. ${meta ? 'Generated ' + G.esc(meta.generated) + '.' : ''}`;
    document.body.appendChild(el);
  };
  G.highlight = (text, q) => {
    const t = G.esc(text);
    if (!q) return t;
    const terms = q.toLowerCase().split(/\s+/).filter((x) => x.length > 1 && !x.includes(':')).map((x) => x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    if (!terms.length) return t;
    return t.replace(new RegExp('(' + terms.join('|') + ')', 'gi'), '<span class="hl">$1</span>');
  };
  // must match build/build_index.mjs
  G.tokenize = (s) => (s || '').toLowerCase().split(/[\s,;:!?()\[\]{}"'`<>|\\/=+*&^%$#@~]+/).flatMap((t) => {
    const parts = t.split(/[-_.]/).filter(Boolean);
    return parts.length > 1 ? [t, ...parts] : [t];
  }).filter((t) => t.length > 0);
  G.tokenizeDocs = (s) => {
    const out = [];
    for (const t of G.tokenize(s)) {
      if (/[\u3400-\u9fff]/.test(t)) {
        const chars = [...t].filter((c) => /[\u3400-\u9fff]/.test(c));
        for (let i = 0; i < chars.length - 1; i++) out.push(chars[i] + chars[i + 1]);
        if (chars.length === 1) out.push(chars[0]);
        out.push(...t.replace(/[\u3400-\u9fff]+/g, ' ').split(' ').filter(Boolean));
      } else out.push(t);
    }
    return out;
  };
  G.MODEL_INDEX_OPTS = { idField: 'id', fields: ['model', 'aliases', 'title', 'vendor', 'tags', 'params', 'description', 'files', 'notes'], storeFields: ['model'], tokenize: G.tokenize };
  G.DOCS_INDEX_OPTS = { idField: 'id', fields: ['p', 't'], storeFields: ['a', 'p', 'b', 'u'], tokenize: G.tokenizeDocs };
  G.loadIndex = (url, opts) => fetch(url).then((r) => r.text()).then((txt) => MiniSearch.loadJSON(txt, opts));
})(window);
