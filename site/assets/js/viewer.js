/* in-browser documentation viewer for archive manifests (hosted blobs + optional JSZip for mirrored archives) */
(function () {
  'use strict';
  const slug = qparam('a'), single = qparam('f');
  let MAN = null, BYPATH = {}, ROOT = null, SEL = null, ZIP = null;
  const LANG = { c: 'c', h: 'c', cpp: 'cpp', hpp: 'cpp', cc: 'cpp', ino: 'arduino', py: 'python', js: 'javascript', ts: 'typescript', json: 'json', yaml: 'yaml', yml: 'yaml',
    ini: 'ini', cfg: 'ini', conf: 'ini', toml: 'ini', properties: 'ini', cmake: 'cmake', mk: 'makefile', xml: 'xml', html: 'xml', htm: 'xml', sh: 'bash', bat: 'dos',
    s: 'x86asm', ld: 'plaintext', md: 'markdown', csv: 'plaintext', txt: 'plaintext', lua: 'lua', rs: 'rust', go: 'go', java: 'java', kt: 'kotlin', rst: 'plaintext', log: 'plaintext' };
  const ext = (p) => (/\.([^./]+)$/.exec(p) || [, ''])[1].toLowerCase();
  const kindOf = (p) => {
    const e = ext(p);
    if (/^(png|jpe?g|gif|webp|bmp|svg)$/.test(e)) return 'image';
    if (e === 'pdf') return 'pdf';
    if (/^(md|markdown)$/.test(e)) return 'markdown';
    if (/^(html?)$/.test(e)) return 'html';
    if (LANG[e]) return 'code';
    return 'other';
  };
  header('files');

  function decode(buf) {
    try { return new TextDecoder('utf-8', { fatal: true }).decode(buf); } catch (e) { /* fallthrough */ }
    try { return new TextDecoder('gbk').decode(buf); } catch (e) { return new TextDecoder('latin1').decode(buf); }
  }
  const blobURL = (b) => 'docs/b/' + b;
  const dirOf = (p) => p.includes('/') ? p.slice(0, p.lastIndexOf('/')) : '';
  function resolveRel(base, rel) {
    if (/^(https?:|data:|mailto:|#)/i.test(rel)) return null;
    rel = decodeURIComponent(rel.split('#')[0].split('?')[0]);
    const parts = (rel.startsWith('/') ? [] : base.split('/').filter(Boolean));
    rel.split('/').forEach((s) => { if (s === '..') parts.pop(); else if (s && s !== '.') parts.push(s); });
    return parts.join('/');
  }

  // ---------- tree
  function buildTree(rows) {
    const root = { name: '', path: '', dirs: {}, files: [], hosted: 0, count: 0 };
    for (const r of rows) {
      const [path, size, blob, kind] = r;
      const segs = path.split('/');
      let node = root;
      node.count++; if (blob) node.hosted++;
      for (let i = 0; i < segs.length - 1; i++) {
        const s = segs[i];
        node = node.dirs[s] || (node.dirs[s] = { name: s, path: segs.slice(0, i + 1).join('/'), dirs: {}, files: [], hosted: 0, count: 0 });
        node.count++; if (blob) node.hosted++;
      }
      node.files.push({ name: segs[segs.length - 1], path, size, blob, kind, nested: r[4] });
    }
    return root;
  }
  const onlyHosted = () => $('#onlyhosted').checked;
  function renderNode(node, depth, open) {
    const dirs = Object.values(node.dirs).sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
    let h = '';
    for (const d of dirs) {
      if (onlyHosted() && !d.hosted) continue;
      const isOpen = open || depth < 1 || (SEL && SEL.startsWith(d.path + '/'));
      h += `<div class="n dir" data-dir="${esc(d.path)}"><span class="ic">${isOpen ? '▾' : '▸'}</span>${esc(d.name)}<span class="sz">${d.hosted}/${d.count}</span></div>`;
      h += `<div class="ch" ${isOpen ? '' : 'hidden'} data-for="${esc(d.path)}">${isOpen ? renderNode(d, depth + 1, open) : ''}</div>`;
    }
    const files = node.files.slice().sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
    for (const f of files) {
      if (onlyHosted() && !f.blob) continue;
      h += `<div class="n ${f.blob ? '' : 'nh'} ${SEL === f.path ? 'sel' : ''}" data-path="${esc(f.path)}" title="${f.blob ? '' : 'not hosted – only in the original archive'}"><span class="ic">${KIND_ICON[f.kind] || '·'}</span>${esc(f.name)}<span class="sz">${fmtBytes(f.size)}</span></div>`;
    }
    return h;
  }
  function findDir(path) { let n = ROOT; if (!path) return n; for (const s of path.split('/')) { n = n && n.dirs[s]; } return n; }
  function renderTree() {
    const q = $('#tfilter').value.trim();
    if (q) {
      let re; try { re = new RegExp(q, 'i'); } catch (e) { re = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i'); }
      const hits = MAN.tree.filter((r) => re.test(r[0]) && (!onlyHosted() || r[2])).slice(0, 800);
      $('#tree').innerHTML = hits.map((r) => `<div class="n ${r[2] ? '' : 'nh'} ${SEL === r[0] ? 'sel' : ''}" data-path="${esc(r[0])}"><span class="ic">${KIND_ICON[r[3]] || '·'}</span>${esc(r[0])}<span class="sz">${fmtBytes(r[1])}</span></div>`).join('')
        + (hits.length === 800 ? '<div class="na">… first 800 matches</div>' : '') || '<div class="na">no match</div>';
      return;
    }
    $('#tree').innerHTML = renderNode(ROOT, 0, $('#expandall').checked) || '<div class="na">nothing browsable – untick "browsable only"</div>';
  }

  // ---------- preview
  async function getBytes(f) {
    if (f.blob) { const r = await fetch(blobURL(f.blob)); if (!r.ok) throw new Error('HTTP ' + r.status); return new Uint8Array(await r.arrayBuffer()); }
    if (ZIP) { const zf = findZipEntry(f.path); if (zf) return zf.async('uint8array'); }
    return null;
  }
  function findZipEntry(path) {
    let hit = ZIP.file(path);
    if (hit) return hit;
    // names inside ZIPs may be GBK-encoded; compare normalized
    const norm = (s) => s.replace(/\\/g, '/');
    return Object.values(ZIP.files).find((z) => norm(z.name) === path) || null;
  }
  async function urlFor(f) {
    if (f.blob) return blobURL(f.blob);
    const b = await getBytes(f);
    if (!b) return null;
    const mime = { pdf: 'application/pdf', png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', gif: 'image/gif', webp: 'image/webp', svg: 'image/svg+xml', bmp: 'image/bmp' }[ext(f.path)] || 'application/octet-stream';
    return URL.createObjectURL(new Blob([b], { type: mime }));
  }
  function rewriteRefs(container, basePath, attr) {
    container.querySelectorAll('[' + attr + ']').forEach((el) => {
      const v = el.getAttribute(attr);
      const p = resolveRel(dirOf(basePath), v || '');
      if (p == null) return;
      const t = BYPATH[p];
      if (t && t.blob) {
        if (el.tagName === 'A') el.setAttribute(attr, viewerURL(slug, p));
        else el.setAttribute(attr, blobURL(t.blob));
      } else if (el.tagName === 'A' && t) el.setAttribute(attr, viewerURL(slug, p));
    });
  }
  async function show(path, push) {
    const f = BYPATH[path];
    if (!f) return;
    SEL = path;
    $$('#tree .n.sel').forEach((n) => n.classList.remove('sel'));
    const el = $$('#tree .n[data-path]').find((n) => n.dataset.path === path);
    if (el) { el.classList.add('sel'); el.scrollIntoView({ block: 'nearest' }); }
    const segs = path.split('/');
    $('#vpath').innerHTML = segs.map((s, i) => i < segs.length - 1 ? `<span class="seg">${esc(s)}/</span>` : `<b>${esc(s)}</b>`).join('');
    const acts = [];
    if (f.blob) acts.push(`<a class="btn" href="${blobURL(f.blob)}" download="${esc(segs[segs.length - 1])}">⇩ file</a>`, `<a class="btn" href="${blobURL(f.blob)}" target="_blank">↗ raw</a>`);
    acts.push(`<button id="cplink">⧉ link</button>`);
    $('#vact').innerHTML = acts.join(' ');
    $('#cplink').onclick = () => navigator.clipboard && navigator.clipboard.writeText(location.href);
    if (push !== false) history.replaceState(null, '', viewerURL(slug, path));
    $('#promptcmd').textContent = 'less "' + segs[segs.length - 1] + '"';
    const body = $('#vbody');
    body.innerHTML = '<div class="empty loading">loading</div>';
    const k = f.kind === 'code' || f.kind === 'text' ? 'code' : (f.kind === 'other' || f.kind === 'office' ? kindOf(path) : f.kind);
    if (!f.blob && !ZIP) {
      body.innerHTML = `<div class="empty">⚠ <b>${esc(segs[segs.length - 1])}</b> (${fmtBytes(f.size)}) is not hosted on this site (size/type budget).<br><br>It is inside the original archive: <a href="${esc(MAN.url)}" target="_blank" rel="noopener">${esc(MAN.name)}</a> (${fmtBytes(MAN.size)})${MAN.hosted_archive ? `<br><br><button id="loadzip">open full archive in browser (JSZip, ${fmtBytes(MAN.size)})</button>` : ''}</div>`;
      const lz = $('#loadzip'); if (lz) lz.onclick = () => loadZip().then(() => show(path));
      return;
    }
    try {
      if (k === 'image') {
        const u = await urlFor(f);
        body.innerHTML = `<div class="imgv"><img src="${esc(u)}" alt="${esc(path)}"></div>`;
        const iv = $('.imgv', body); $('img', iv).onclick = () => iv.classList.toggle('full');
      } else if (k === 'pdf') {
        const u = await urlFor(f);
        body.innerHTML = `<iframe src="${esc(u)}#view=FitH" title="pdf"></iframe>`;
      } else if (k === 'markdown') {
        const txt = decode(await getBytes(f));
        const div = document.createElement('div');
        div.className = 'md-body';
        div.innerHTML = DOMPurify.sanitize(marked.parse(txt));
        rewriteRefs(div, path, 'src'); rewriteRefs(div, path, 'href');
        div.querySelectorAll('pre code').forEach((c) => { try { hljs.highlightElement(c); } catch (e) { /* ignore */ } });
        body.innerHTML = ''; body.appendChild(div);
      } else if (k === 'html') {
        const txt = decode(await getBytes(f));
        const doc = new DOMParser().parseFromString(txt, 'text/html');
        doc.querySelectorAll('script').forEach((s) => s.remove());
        rewriteRefs(doc, path, 'src'); rewriteRefs(doc, path, 'href');
        doc.querySelectorAll('a[href]').forEach((a) => a.setAttribute('target', '_top'));
        const ifr = document.createElement('iframe');
        ifr.setAttribute('sandbox', 'allow-top-navigation-by-user-activation allow-popups');
        ifr.srcdoc = '<base target="_top">' + doc.documentElement.outerHTML;
        body.innerHTML = ''; body.appendChild(ifr);
      } else if (k === 'code') {
        const bytes = await getBytes(f);
        const txt = decode(bytes);
        const pre = document.createElement('pre');
        pre.className = 'code';
        const code = document.createElement('code');
        const lang = LANG[ext(path)] || 'plaintext';
        if (txt.length < 400000 && lang !== 'plaintext' && hljs.getLanguage(lang)) code.innerHTML = hljs.highlight(txt, { language: lang, ignoreIllegals: true }).value;
        else code.textContent = txt;
        pre.appendChild(code);
        body.innerHTML = '';
        const bar = document.createElement('div');
        bar.className = 'toolbar'; bar.style.cssText = 'margin:0;padding:4px 12px;border-bottom:1px solid var(--line)';
        bar.innerHTML = `<span class="na">${esc(lang)} · ${txt.split('\n').length} lines · ${fmtBytes(bytes.length)}</span><button id="wrapbtn">wrap</button>`;
        body.appendChild(bar); body.appendChild(pre);
        $('#wrapbtn').onclick = () => pre.classList.toggle('wrap');
      } else {
        const u = await urlFor(f);
        body.innerHTML = `<div class="empty">no inline preview for <b>.${esc(ext(path))}</b> files.<br><br>${u ? `<a class="btn" href="${esc(u)}" download="${esc(segs[segs.length - 1])}">⇩ download ${esc(segs[segs.length - 1])}</a>` : ''}</div>`;
      }
    } catch (e) {
      body.innerHTML = `<div class="empty">failed to load: ${esc(e.message)}</div>`;
    }
  }
  async function loadZip() {
    $('#vbody').innerHTML = '<div class="empty loading">downloading + unzipping ' + esc(MAN.name) + '</div>';
    const buf = await (await fetch(MAN.hosted_archive)).arrayBuffer();
    ZIP = await JSZip.loadAsync(buf, { decodeFileName: (bytes) => { try { return new TextDecoder('utf-8', { fatal: true }).decode(bytes); } catch (e) { return new TextDecoder('gbk').decode(bytes); } } });
    $('#onlyhosted').checked = false;
    $('#astats').innerHTML += ' · <b style="color:var(--acc)">full archive loaded (JSZip)</b>';
    renderTree();
  }

  // ---------- single hosted file mode (product PDFs etc.)
  function singleMode() {
    const name = qparam('n') || single.split('/').pop();
    $('.vside').style.display = 'none';
    $('.vlayout').style.gridTemplateColumns = '1fr';
    $('#vpath').innerHTML = `<b>${esc(name)}</b>`;
    $('#vact').innerHTML = `<a class="btn" href="${esc(single)}" download>⇩ file</a> <a class="btn" href="javascript:history.back()">← back</a>`;
    const k = kindOf(single);
    $('#vbody').innerHTML = k === 'image' ? `<div class="imgv"><img src="${esc(single)}"></div>` : `<iframe src="${esc(single)}#view=FitH" title="document"></iframe>`;
  }

  // ---------- init
  if (single) { if (/^(files|docs|assets)\//.test(single) && !single.includes('..')) singleMode(); else $('#vbody').innerHTML = '<div class="empty">invalid file</div>'; return; }
  if (!slug) { location.href = 'files.html'; return; }
  Promise.all([getJSON('data/manifests/' + encodeURIComponent(slug) + '.json'), getJSON('data/meta.json')]).then(([man, meta]) => {
    MAN = man;
    document.title = man.name + ' – docs viewer';
    MAN.tree.forEach((r) => { BYPATH[r[0]] = { path: r[0], size: r[1], blob: r[2], kind: r[3] }; });
    ROOT = buildTree(MAN.tree);
    const s = man.stats || {};
    $('#aname').textContent = '🗜 ' + man.name;
    const models = (meta.slug2models[slug] || []);
    $('#astats').innerHTML = `${s.files} files · ${fmtBytes(s.bytes)} unpacked · <b>${s.hosted_files}</b> browsable (${fmtBytes(s.hosted_bytes)})<br>archive ${fmtBytes(man.size)} · folder “${esc(man.dir)}”`;
    $('#alinks').innerHTML = `<a class="btn" href="${esc(man.url)}" target="_blank" rel="noopener">⇩ original</a>` + (man.hosted_archive ? ` <button id="zipbtn">open full zip</button>` : '')
      + (models.length ? ` <span class="na">for:</span> ` + models.slice(0, 6).map((m) => `<a href="index.html#q=${encodeURIComponent(m)}">${esc(m)}</a>`).join(', ') : '');
    const zb = $('#zipbtn'); if (zb) zb.onclick = () => loadZip();
    const want = qparam('p');
    SEL = want;
    renderTree();
    if (want && BYPATH[want]) show(want, false);
    else {
      // auto-open the first schematic / spec PDF
      const first = MAN.tree.find((r) => r[2] && /schematic|原理图/i.test(r[0]) && /\.(png|jpe?g|pdf)$/i.test(r[0])) || MAN.tree.find((r) => r[2] && /\.pdf$/i.test(r[0]));
      if (first) { SEL = first[0]; renderTree(); show(first[0], false); }
    }
    $('#tree').addEventListener('click', (e) => {
      const d = e.target.closest('.n.dir');
      if (d) {
        const ch = d.nextElementSibling;
        const open = ch.hasAttribute('hidden');
        if (open) { ch.removeAttribute('hidden'); if (!ch.innerHTML) ch.innerHTML = renderNode(findDir(d.dataset.dir), 1, false); } else ch.setAttribute('hidden', '');
        d.querySelector('.ic').textContent = open ? '▾' : '▸';
        return;
      }
      const f = e.target.closest('.n[data-path]');
      if (f) show(f.dataset.path);
    });
    let t; $('#tfilter').addEventListener('input', () => { clearTimeout(t); t = setTimeout(renderTree, 150); });
    $('#onlyhosted').addEventListener('change', renderTree);
    $('#expandall').addEventListener('change', renderTree);
  }).catch((e) => { $('#tree').innerHTML = `<div class="empty">manifest not found: ${esc(e.message)}</div>`; });
})();
