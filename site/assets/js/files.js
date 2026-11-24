/* list of every archive / file on the official file server + mapping to models */
(function () {
  'use strict';
  header('files');
  Promise.all([getJSON('data/archives.json'), getJSON('data/meta.json'), getJSON('data/models.json'), getJSON('data/offline.json')]).then(([arch, meta, models, off]) => {
    const byModel = Object.fromEntries(models.map((m) => [m.model, m.id]));
    const tot = arch.reduce((s, a) => s + (a.size || 0), 0);
    const hostedF = arch.reduce((s, a) => s + (a.stats ? a.stats.hosted_files : 0), 0);
    $('#app').classList.add('files-page');
    $('#app').innerHTML = `<div class="hero"><h1>Files &amp; archives</h1>
      <p class="na">${arch.length} files on the official Guition file server (${fmtBytes(tot)} total). <b>Every file is available offline</b>: files ≤ 24 MB are stored on this site, larger ones as <a href="${esc(off.release.base.replace('/download/', '/tag/').replace(/\/$/, ''))}">GitHub release assets</a>; the original vendor server stays as a mirror. ${hostedF} documentation files were extracted and are browsable here.</p></div>
      <div class="toolbar"><input id="flt" class="small" placeholder="filter…" style="min-width:260px"><span class="count" id="cnt"></span></div>
      <div class="tblwrap"><table class="grid stack" id="tbl"><thead><tr><th data-k="dir">folder</th><th data-k="name">file</th><th data-k="size">size</th><th data-k="files">files inside</th><th data-k="hosted">browsable</th><th>models</th><th>actions</th></tr></thead><tbody></tbody></table></div>`;
    let sortK = 'dir', dir = 1;
    function render() {
      const q = $('#flt').value.toLowerCase();
      const rows = arch.filter((a) => !q || (a.path + ' ' + (a.models || []).join(' ')).toLowerCase().includes(q));
      const val = (a) => ({ dir: a.dir + a.name, name: a.name, size: a.size || 0, files: a.stats ? a.stats.files : 0, hosted: a.stats ? a.stats.hosted_files : (a.hosted ? 1 : 0) })[sortK];
      rows.sort((x, y) => { const a = val(x), b = val(y); return (typeof a === 'number' ? a - b : String(a).localeCompare(String(b), undefined, { numeric: true })) * dir; });
      $('#cnt').textContent = rows.length + ' / ' + arch.length;
      $('#tbl tbody').innerHTML = rows.map((a) => {
        const acts = [];
        if (a.manifest) acts.push(`<a class="btn" href="${viewerURL(a.slug)}">⌕ browse</a>`);
        if (a.hosted) acts.push(`<a class="btn" href="${fileViewerURL(a.hosted, a.name)}">👁 view</a>`);
        acts.push(offlineLinks(a.offline, a.name, a.url));
        const ms = (a.models || []).map((m) => byModel[m] ? `<a href="${modelURL(byModel[m])}">${esc(m)}</a>` : esc(m)).join(', ') || '<span class="na">–</span>';
        return `<tr><td class="na" data-label="folder">${esc(a.dir)}</td><td data-label="file">${esc(a.name)}${a.error ? ` <span class="badge warn" title="${esc(a.error)}">error</span>` : ''}</td><td data-label="size">${fmtBytes(a.size)}</td>
          <td data-label="files inside">${a.stats ? a.stats.files + ' · ' + fmtBytes(a.stats.bytes) : '<span class="na">–</span>'}</td><td data-label="browsable">${a.stats ? `${a.stats.hosted_files} · ${fmtBytes(a.stats.hosted_bytes)}` : (a.hosted ? 'yes' : '<span class="na">no</span>')}</td><td data-label="models">${ms}</td><td data-label="actions">${acts.join(' ')}</td></tr>`;
      }).join('');
    }
    $$('#tbl th[data-k]').forEach((th) => th.addEventListener('click', () => { if (sortK === th.dataset.k) dir = -dir; else { sortK = th.dataset.k; dir = 1; } render(); }));
    $('#flt').addEventListener('input', render);
    render();
    footer(meta);
  });
})();
