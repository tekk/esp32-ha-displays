// Copy browser builds of third-party libraries into site/assets/vendor (no CDN needed at runtime)
import fs from 'node:fs';
import path from 'node:path';
const root = path.dirname(path.dirname(new URL(import.meta.url).pathname));
const out = path.join(root, 'site/assets/vendor');
fs.mkdirSync(out, { recursive: true });
const nm = (p) => path.join(root, 'node_modules', p);
const files = [
  ['minisearch/dist/umd/index.js', 'minisearch.js'],
  ['jszip/dist/jszip.min.js', 'jszip.min.js'],
  ['marked/lib/marked.umd.js', 'marked.umd.js'],
  ['dompurify/dist/purify.min.js', 'purify.min.js'],
  ['@highlightjs/cdn-assets/highlight.min.js', 'highlight.min.js'],
  ['@highlightjs/cdn-assets/styles/github-dark.min.css', 'hljs-github-dark.min.css'],
];
for (const lang of ['arduino', 'cmake', 'ini', 'yaml', 'makefile', 'x86asm', 'lua', 'rust', 'go', 'kotlin', 'dos', 'properties']) {
  const p = `@highlightjs/cdn-assets/languages/${lang}.min.js`;
  if (fs.existsSync(nm(p))) files.push([p, `hljs-${lang}.min.js`]);
}
for (const [src, dst] of files) {
  fs.copyFileSync(nm(src), path.join(out, dst));
  console.log('vendor', dst);
}
for (const lic of ['minisearch/LICENSE.txt', 'jszip/LICENSE.markdown', 'marked/LICENSE.md', 'dompurify/LICENSE', '@highlightjs/cdn-assets/LICENSE']) {
  if (fs.existsSync(nm(lic))) fs.copyFileSync(nm(lic), path.join(out, lic.split('/')[0].replace('@', '') + '-' + path.basename(lic)));
}
