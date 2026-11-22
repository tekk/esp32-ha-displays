(function () {
  'use strict';
  window.promptText = 'cat README';
  header('about');
  getJSON('data/meta.json').then((meta) => {
    const c = { 'Guition boards': (meta.counts || {}).Guition, 'Waveshare boards': (meta.counts || {}).Waveshare, 'files on server': meta.archives, 'archive bytes': meta.archive_bytes, 'hosted doc files': meta.hosted_blobs };
    $('#app').innerHTML = `<pre class="ascii">
  ██████  ██    ██ ██ ████████ ██  ██████  ███    ██
 ██       ██    ██ ██    ██    ██ ██    ██ ████   ██
 ██   ███ ██    ██ ██    ██    ██ ██    ██ ██ ██  ██
 ██    ██ ██    ██ ██    ██    ██ ██    ██ ██  ██ ██
  ██████   ██████  ██    ██    ██  ██████  ██   ████  //catalog</pre>
    <div class="sec"><h2>what is this</h2>
      <p>Unofficial, static, searchable catalog of all <b>Guition</b> (Shenzhen Jingcai Intelligent, “JC…” / “ESP32-…” / “CYD”) display boards and selected <b>Waveshare ESP32-P4</b> boards: parameters, images, spec PDFs, the full file tree of every official archive and a built-in browser for the documentation inside them.</p>
      <p><i>SK: Neoficiálny statický katalóg všetkých displejov Guition a vybraných dosiek Waveshare ESP32-P4 – parametre, obrázky, PDF, kompletný strom súborov každého ZIP archívu a vstavaný prehliadač dokumentácie.</i></p>
      <div class="stats">${Object.entries(c).map(([k, v]) => `<div><b>${esc(typeof v === 'number' && v > 1e6 ? fmtBytes(v) : String(v))}</b><span>${esc(k.replace(/_/g, ' '))}</span></div>`).join('')}</div></div>
    <div class="sec"><h2>data rules</h2><ul>
      <li>No invented specs. Every parameter comes from a real source and the source URL is stored per value (hover the ↗ on a model page; “raw specs by source” shows the untouched rows).</li>
      <li>Empty cell = unknown / not published by the manufacturer.</li>
      <li>When manufacturer sources disagree, the model page shows a <b>source conflict</b> warning instead of silently picking one.</li>
      <li>Community information (pinouts, notes) is attributed and linked to the original repository.</li></ul></div>
    <div class="sec"><h2>sources</h2><ul>${(meta.sources || []).map((s) => `<li><a href="${esc(s.url || s)}">${esc(s.title || s.url || s)}</a>${s.desc ? ' <span class="na">– ' + esc(s.desc) + '</span>' : ''}</li>`).join('')}</ul></div>
    <div class="sec"><h2>hosting / files</h2><ul>
      <li><b>Everything is available offline.</b> Files ≤ 24 MB (Cloudflare Pages per-file limit) are stored on this site; larger ZIP/RAR archives (up to ~600 MB) and repository snapshots are GitHub Release assets of <a href="https://github.com/tekk/esp32-ha-displays/releases/tag/files-v1">tekk/esp32-ha-displays · files-v1</a> (sha256 shown on hover). The original vendor server is kept as a mirror link. ZIPs ≤ 24 MB can be opened completely in the browser (JSZip).</li><li>Community repositories are snapshotted only when they carry a licence file (or are vendor-official); others are linked.</li>
      <li>From each archive the documentation (schematics, datasheets, spec sheets, READMEs, selected demo code) is extracted and de-duplicated into <code>docs/b/</code>; every file of the archive is still listed in its manifest with a link to the original archive.</li>
      <li>Search uses prebuilt <a href="https://github.com/lucaong/minisearch">MiniSearch</a> indexes. Viewer uses marked + DOMPurify + highlight.js + JSZip (vendored, licenses in <code>assets/vendor/</code>).</li></ul></div>
    <div class="sec"><h2>query syntax</h2><pre class="code">JC4880          free text (model, params, tags, file names)
mcu:esp32-p4    parameter filter  (mcu, size, res, iface, driver, cat, tag, vendor, panel, touch …)
tag:rs485 7"    combine
/               focus search</pre></div>`;
    footer(meta);
  });
})();
