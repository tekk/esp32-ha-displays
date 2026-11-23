(function () {
  'use strict';
  header('about');
  getJSON('data/meta.json').then((meta) => {
    const c = { ...Object.fromEntries(Object.entries(meta.counts || {}).map(([k, v]) => [k + ' boards', v])), 'files on server': meta.archives, 'archive bytes': meta.archive_bytes, 'hosted doc files': meta.hosted_blobs };
    $('#app').innerHTML = `<div class="hero"><h1>About</h1></div>
    <div class="sec"><h2>What is this</h2>
      <p>Unofficial, static, searchable catalog of all <b>Guition</b> (Shenzhen Jingcai Intelligent, “JC…” / “ESP32-…” / “CYD”) display boards and selected ESP32 display boards from <b>Waveshare</b>, <b>M5Stack</b>, <b>LilyGO</b>, <b>Elecrow</b>, <b>Seeed Studio</b>, <b>Makerfabs</b> and <b>DFRobot</b>: parameters, images, spec PDFs, the full file tree of every official archive and a built-in browser for the documentation inside them.</p>
      <p><i>SK: Neoficiálny statický katalóg všetkých displejov Guition a vybraných ESP32 displejových dosiek Waveshare, M5Stack, LilyGO, Elecrow, Seeed Studio, Makerfabs a DFRobot – parametre, obrázky, PDF, kompletný strom súborov každého ZIP archívu a vstavaný prehliadač dokumentácie.</i></p>
      <div class="stats big">${Object.entries(c).map(([k, v]) => `<div><b>${esc(typeof v === 'number' && v > 1e6 ? fmtBytes(v) : String(v))}</b><span>${esc(k.replace(/_/g, ' '))}</span></div>`).join('')}</div></div>
    <div class="sec"><h2>Data rules</h2><ul>
      <li>No invented specs. Every parameter comes from a real source and the source URL is stored per value (hover the ↗ on a model page; “raw specs by source” shows the untouched rows).</li>
      <li>Empty cell = unknown / not published by the manufacturer.</li>
      <li>When manufacturer sources disagree, the model page shows a <b>source conflict</b> warning instead of silently picking one.</li>
      <li>Community information (pinouts, notes) is attributed and linked to the original repository.</li></ul></div>
    <div class="sec"><h2>Sources</h2><ul>${(meta.sources || []).map((s) => `<li><a href="${esc(s.url || s)}">${esc(s.title || s.url || s)}</a>${s.desc ? ' <span class="na">– ' + esc(s.desc) + '</span>' : ''}</li>`).join('')}</ul></div>
    <div class="sec"><h2>Hosting / files</h2><ul>
      <li><b>Everything is available offline.</b> Files ≤ 24 MB (Cloudflare Pages per-file limit) are stored on this site; larger ZIP/RAR archives (up to ~600 MB) and repository snapshots are GitHub Release assets of <a href="https://github.com/tekk/esp32-ha-displays/releases/tag/files-v1">tekk/esp32-ha-displays · files-v1</a> (sha256 shown on hover). The original vendor server is kept as a mirror link. ZIPs ≤ 24 MB can be opened completely in the browser (JSZip).</li><li>Community repositories are snapshotted only when they carry a licence file (or are vendor-official); others are linked.</li>
      <li>From each archive the documentation (schematics, datasheets, spec sheets, READMEs, selected demo code) is extracted and de-duplicated into <code>docs/b/</code>; every file of the archive is still listed in its manifest with a link to the original archive.</li>
      <li><b>Photos</b>: vendor product photos (guition.com galleries are 800×800 at most – the largest the manufacturer publishes; Waveshare originals up to 1600 px; other manufacturers: official product photos from their shop / docs pages) plus annotated board pictures from each board's own official archive, all converted to WebP (≤1600 px) and stored here. The source of every photo is shown under it on the board page. Boards without a verified photo show none rather than a photo of a different board.</li>
      <li><b>Fully offline</b>: fonts (Montserrat, Roboto Condensed, JetBrains Mono, Meslo LG), libraries, photos and documents are self-hosted; a Content-Security-Policy forbids any external request and a service worker keeps the catalog usable offline after the first visit.</li>
      <li>Search uses prebuilt <a href="https://github.com/lucaong/minisearch">MiniSearch</a> indexes. Viewer uses marked + DOMPurify + highlight.js + JSZip (vendored, licenses in <code>assets/vendor/</code>).</li></ul></div>
    <div class="sec"><h2>Query syntax</h2><pre class="plain">JC4880          free text (model, params, tags, file names)
mcu:esp32-p4    parameter filter  (mcu, size, res, iface, driver, cat, tag, vendor, panel, touch …)
tag:rs485 7"    combine
/               focus search</pre></div>`;
    footer(meta);
  });
})();
