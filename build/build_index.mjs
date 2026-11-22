// Build prebuilt MiniSearch indexes: site/data/search-models.json and site/data/search-docs.json
import fs from 'node:fs';
import path from 'node:path';
import MiniSearch from 'minisearch';

const root = path.dirname(path.dirname(new URL(import.meta.url).pathname));
const site = path.join(root, 'site');
const models = JSON.parse(fs.readFileSync(path.join(site, 'data/models.json'), 'utf8'));
const docs = JSON.parse(fs.readFileSync(path.join(root, 'data/raw/docs_for_index.json'), 'utf8'));
const meta = JSON.parse(fs.readFileSync(path.join(site, 'data/meta.json'), 'utf8'));

// shared options – MUST match site/assets/js/common.js
const tokenize = (s) => (s || '').toLowerCase().split(/[\s,;:!?()\[\]{}"'`<>|\\/=+*&^%$#@~]+/).flatMap((t) => {
  const parts = t.split(/[-_.]/).filter(Boolean);
  return parts.length > 1 ? [t, ...parts] : [t];
}).filter((t) => t.length > 0);

const modelOpts = {
  idField: 'id',
  fields: ['model', 'aliases', 'title', 'vendor', 'tags', 'params', 'description', 'files', 'notes'],
  storeFields: ['model'],
  tokenize,
};
const ms = new MiniSearch(modelOpts);
ms.addAll(models.map((m) => ({
  id: m.id,
  model: m.model,
  aliases: (m.aliases || []).join(' '),
  title: m.title,
  vendor: m.vendor,
  tags: (m.tags || []).join(' '),
  params: Object.entries(m.params).map(([k, v]) => `${k} ${v}`).join(' ') + ' ' + (m.specs_raw || []).map((r) => `${r.label} ${r.value}`).join(' '),
  description: m.description,
  files: (m.files || []).map((f) => f.name).join(' '),
  notes: (m.notes || []).map((n) => n.text).join(' '),
})));
fs.writeFileSync(path.join(site, 'data/search-models.json'), JSON.stringify(ms));

// CJK: also index individual Han characters for Chinese file names/texts
const tokenizeDocs = (s) => {
  const base = tokenize(s);
  const out = [];
  for (const t of base) {
    if (/[\u3400-\u9fff]/.test(t)) {
      const chars = [...t].filter((c) => /[\u3400-\u9fff]/.test(c));
      for (let i = 0; i < chars.length - 1; i++) out.push(chars[i] + chars[i + 1]);
      if (chars.length === 1) out.push(chars[0]);
      const latin = t.replace(/[\u3400-\u9fff]+/g, ' ').split(' ').filter(Boolean);
      out.push(...latin);
    } else out.push(t);
  }
  return out;
};
const docOpts = { idField: 'id', fields: ['p', 't'], storeFields: ['a', 'p', 'b', 'u'], tokenize: tokenizeDocs };
const ds = new MiniSearch(docOpts);
ds.addAll(docs.map((d) => ({ ...d, t: d.t.slice(0, 4000) })));
fs.writeFileSync(path.join(site, 'data/search-docs.json'), JSON.stringify(ds));
// snippets for docs (first 220 chars)
fs.writeFileSync(path.join(site, 'data/docs-snippets.json'), JSON.stringify(Object.fromEntries(docs.map((d) => [d.id, d.t.slice(0, 220)]))));
const sz = (f) => (fs.statSync(path.join(site, 'data', f)).size / 1e6).toFixed(2) + ' MB';
console.log('models index', sz('search-models.json'), 'docs index', sz('search-docs.json'), 'snippets', sz('docs-snippets.json'), 'docs', docs.length);
