/* model detail page */
(function () {
  'use strict';
  const ORDER = ['vendor', 'category', 'series', 'sku', 'size', 'resolution', 'shape', 'panel', 'driver_ic', 'interface', 'interface_detail', 'touch', 'touch_detail', 'touch_ic', 'touch_points',
    'mcu', 'mcu_family', 'coprocessor', 'frequency', 'sram', 'psram', 'rom', 'flash', 'memory', 'wifi', 'bt', 'connectivity', 'camera', 'audio', 'speaker',
    'ethernet', 'poe', 'rs485', 'can', 'lora', 'gps', 'nfc', 'ir', 'usb', 'sd', 'rtc', 'battery', 'charger', 'pmu', 'dc_in', 'mic', 'jack', 'buzzer',
    'imu', 'als', 'sensors', 'keyboard', 'encoder', 'buttons', 'rgbled', 'vibration', 'grove', 'uart', 'i2c', 'relay', 'epaper', 'gpio', 'expansion', 'shell', 'glass', 'display_module', 'form_factor', 'dimensions', 'active_area', 'pixel_pitch',
    'brightness', 'contrast', 'viewing_angle', 'color_depth', 'color_gamut', 'backlight', 'voltage', 'power', 'operating_temp', 'storage_temp', 'weight', 'software'];
  const FACETABLE = new Set(['vendor', 'category', 'mcu_family', 'size', 'resolution', 'panel', 'touch', 'interface', 'shape', 'driver_ic', 'flash', 'psram', 'sram', 'frequency', 'coprocessor', 'wifi', 'bt', 'speaker', 'shell']);
  const id = qparam('id');
  header('models');
  Promise.all([getJSON('data/models.json'), getJSON('data/meta.json')]).then(([models, meta]) => {
    const m = models.find((x) => x.id === id) || models.find((x) => x.model === id);
    if (!m) { $('#app').innerHTML = `<div class="empty"><pre>404: board "${esc(id)}" not found</pre><br><a href="index.html">← back to catalog</a></div>`; return; }
    document.title = m.model + ' – ESP32 Display Catalog';
    const L = meta.field_labels;
    const p = m.params;
    const srcFor = (key) => (m.specs_raw.find((r) => r.key === key) || {}).source;
    const specRows = ORDER.filter((k) => p[k] != null && p[k] !== '' && k !== 'size_in' && k !== 'pixels').map((k) => {
      const v = String(p[k]);
      const link = FACETABLE.has(k) ? `<a class="fl" title="show all boards with ${esc(L[k] || k)} = ${esc(v)}" href="index.html#f.${k}=${encodeURIComponent(v)}">${esc(v)}</a>` : esc(v);
      const s = srcFor(k);
      return `<tr><td>${esc(L[k] || k)}</td><td>${link}${s ? ` <a class="na" href="${esc(s)}" title="source: ${esc(s)}">↗</a>` : ''}</td></tr>`;
    }).join('');
    const imgs = m.images;
    const host = (u) => { try { return new URL(u).host; } catch (e) { return ''; } };
    const capOf = (im) => `${esc(im.kind === 'photo' ? 'Photo' : im.kind === 'diagram' ? 'Board diagram' : 'Drawing')} · ${im.w}×${im.h}${im.source_page ? ` · source: <a href="${esc(im.source_page)}" target="_blank" rel="noopener">${esc(host(im.source_page))}</a>` : im.orig ? ' · ' + esc(host(im.orig)) : ''}${im.note ? ' · ' + esc(im.note) : ''}`;
    const ports = portsOf(m);
    const feats = m.features || [];
    const notes = m.notes.map((n) => `<div class="note ${esc(n.level)}"><b class="lvl">${n.level === 'warning' ? '⚠ WARNING' : 'ℹ NOTE'}</b> ${esc(n.text)}${n.sk ? `<br><i>SK: ${esc(n.sk)}</i>` : ''}${n.source ? `<div class="src">source: <a href="${esc(n.source)}">${esc(n.source)}</a></div>` : ''}</div>`).join('');
    const conflicts = m.conflicts.length ? `<div class="note warning"><b class="lvl">⚠ SOURCE CONFLICT</b> The manufacturer's own pages disagree:<ul>${m.conflicts.map((c) => `<li>${esc(c.field)}: ${Object.entries(c.values).map(([v, s]) => `<b>${esc(v)}</b> (${esc(s.join(', '))})`).join(' vs ')}</li>`).join('')}</ul>Check the spec PDF / archive.</div>` : '';
    const files = m.files.map((f) => {
      const st = f.stats ? `${f.stats.files} files · ${fmtBytes(f.stats.bytes)} unpacked · <b>${f.stats.hosted_files}</b> browsable here` : '';
      const acts = [];
      if (f.manifest) acts.push(`<a class="btn" href="${viewerURL(f.slug)}">⌕ browse docs</a>`);
      if (f.hosted && f.type !== 'archive') acts.push(`<a class="btn" href="${fileViewerURL(f.hosted, f.name)}">👁 view</a>`);
      if (f.offline) acts.push(offlineLinks(f.offline, f.name, f.url));
      else acts.push(`<a class="btn" href="${esc(f.url)}" rel="noopener" target="_blank">⇩ original</a> <span class="badge warn">online only</span>`);
      return `<div class="f"><span>${f.type === 'archive' ? '🗜' : '📕'}</span><div><div class="nm">${esc(f.name)} ${f.lang ? `<span class="badge info">${esc(f.lang)}</span>` : ''} ${f.missing ? '<span class="badge warn">missing on server</span>' : ''}</div>
        <div class="meta">${f.size ? fmtBytes(f.size) + ' · ' : ''}${esc(f.origin || '')}${st ? ' · ' + st : ''}${f.note ? ' · ' + esc(f.note) : ''}</div></div><div class="act">${acts.join('')}</div></div>`;
    }).join('') || '<div class="na">no downloadable files known</div>';
    const linkGroups = { vendor: 'Manufacturer', 'official-github': 'Official GitHub', community: 'Community' };
    const links = Object.entries(linkGroups).map(([t, lab]) => {
      const ls = m.links.filter((l) => l.type === t);
      return ls.length ? `<h3 class="count">${lab}</h3><ul>${ls.map((l) => `<li><a href="${esc(l.url)}" rel="noopener" target="_blank">${esc(l.title)}</a>${l.offline ? ` <a class="badge ok" href="${esc(l.offline.url)}" title="offline snapshot of the repository (${fmtBytes(l.offline.size)}, ${l.offline.type === 'local' ? 'this site' : 'GitHub release'})">⇩ offline zip</a>` : ''}${l.desc ? ` <span class="na">– ${esc(l.desc)}</span>` : ''}</li>`).join('')}</ul>` : '';
    }).join('');
    const pins = m.pinouts.map((pt) => `<h3 class="count">${esc(pt.title)} <a class="na" href="${esc(pt.source)}">[source]</a></h3><table class="kv2"><tr><th>Function</th><th>Pins</th><th>Notes</th></tr>${pt.rows.map((r) => `<tr><td>${esc(r[0])}</td><td>${esc(r[1])}</td><td class="na">${esc(r[2])}</td></tr>`).join('')}</table>`).join('');
    const bySrc = {};
    m.specs_raw.forEach((r) => { (bySrc[r.source] = bySrc[r.source] || []).push(r); });
    const raw = Object.entries(bySrc).map(([s, rows]) => `<details><summary>${esc(rows[0].src)} — ${esc(s)}</summary><table class="kv2">${rows.map((r) => `<tr><td>${esc(r.label)}</td><td>${esc(r.value)}</td></tr>`).join('')}</table></details>`).join('');
    const sibs = m.siblings.map((sid) => models.find((x) => x.id === sid)).filter(Boolean);
    $('#app').innerHTML = `
      <div class="toolbar"><a href="index.html">← catalog</a><span class="na">/ ${esc(p.category || m.vendor)} /</span><b>${esc(m.model)}</b></div>
      <div class="dhead">
        <div class="gallery">${imgs.length ? `<div class="main" id="gmain" role="img" aria-label="${esc(m.model)}" style="background-image:url('${esc(imgs[0].src)}')"></div><div class="cap" id="gcap">${capOf(imgs[0])}</div>
          <div class="thumbs">${imgs.map((im, i) => `<img src="${esc(im.thumb || im.src)}" data-i="${i}" class="${i ? '' : 'sel'}" loading="lazy" alt="${esc(im.kind)}" title="${esc(im.kind + (im.note ? ' – ' + im.note : ''))}">`).join('')}</div>` : '<div class="main empty"></div><div class="cap">No photo available for this board.</div>'}</div>
        <div class="dinfo">
          <h1>${esc(m.model)}</h1>
          <div class="sub">${esc(m.vendor)} · ${esc(m.title || '')}${m.aliases.length ? ' · aka ' + esc(m.aliases.join(', ')) : ''}</div>
          <div class="tags">${m.tags.map((t) => `<a class="tag" href="index.html#f.tags=${encodeURIComponent(t)}">${esc(t)}</a>`).join('')}</div>
          ${notes}${conflicts}
          ${m.description ? `<p>${esc(m.description)}</p>` : ''}
          <table class="kv2">${specRows}</table>
        </div>
      </div>
      <div class="cols2">
        <div class="sec"><h2>Files &amp; documentation</h2><div class="filelist">${files}</div></div>
        <div class="sec"><h2>Links</h2>${links || '<span class="na">none</span>'}</div>
      </div>
      ${feats.length ? `<div class="sec"><h2>Ports, connectors &amp; interfaces</h2><div class="fgrid">${feats.map((f) => `<a class="fcell fc-${esc(f.category)}" href="index.html#f.feat=${encodeURIComponent(f.name)}" title="${esc(f.label)}${f.source ? '\nsource: ' + esc(f.source) : ''}${f.basis && f.basis !== f.source ? '\nbasis: ' + esc(f.basis) : ''}"><span class="fi${f.value ? ' fhasv' : ''}" style="--s:40px"><svg width="40" height="40" aria-hidden="true"><use href="${FEAT_SPRITE}#f-${esc(f.icon)}"/></svg>${f.value ? `<b class="fv">${esc(f.value)}</b>` : ''}</span><span class="fl1">${esc(f.label)}</span>${f.connector && !f.label.includes(f.connector) ? `<span class="fl2">${esc(f.connector)}</span>` : ''}</a>`).join('')}</div>
        <div class="na" style="font-size:12px;margin-top:8px">Derived only from stated sources: the manufacturer's spec rows${feats.some((f) => f.source && /github\.com/.test(f.source)) ? ' and community pin maps' : ''} (hover a cell for its source; see “Raw specs by source”). Click a cell to list every board with that feature.${ports.length ? ` Manufacturer wording: ${ports.map(esc).join(' · ')}.` : ''}</div></div>` : ''}
      ${pins ? `<div class="sec"><h2>Pinout (community)</h2>${pins}</div>` : ''}
      ${sibs.length ? `<div class="sec"><h2>Variants / same family</h2><div class="tags">${sibs.map((s) => `<a class="tag" href="${modelURL(s.id)}">${esc(s.model)}</a>`).join('')}</div></div>` : ''}
      <div class="sec"><h2>Raw specs by source</h2>${raw}</div>
      <div class="sec"><h2>Sources</h2><ul>${m.sources.map((s) => `<li><a href="${esc(s)}">${esc(s)}</a></li>`).join('')}</ul></div>`;
    $$('.thumbs img').forEach((t) => t.addEventListener('click', () => { const im = imgs[+t.dataset.i]; $$('.thumbs img').forEach((x) => x.classList.remove('sel')); t.classList.add('sel'); $('#gmain').style.backgroundImage = `url('${im.src}')`; $('#gmain').dataset.src = im.src; $('#gcap').innerHTML = capOf(im); }));
    const gm = $('#gmain');
    if (gm) gm.addEventListener('click', () => { $('#lb img').src = gm.dataset.src || imgs[0].src; $('#lb').classList.add('on'); });
    $('#lb').addEventListener('click', () => $('#lb').classList.remove('on'));
    footer(meta);
  });
})();
