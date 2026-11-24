#!/usr/bin/env python3
"""Validate the static SEO layer: every board/vendor page exists, unique <title>/description/canonical,
OG/Twitter tags, parseable JSON-LD of the expected types, local refs resolve, images have width/height/alt,
sitemap.xml is valid and lists every page, robots.txt points to it, no file > 25 MiB, no external
resource loads (links to vendor sites are fine; <img>/<script>/<link rel=stylesheet> must be local)."""
import glob, json, os, re, sys, xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, unquote
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, 'site')
BASE = json.load(open(os.path.join(ROOT, 'build/config.json')))['offline']['pages_url'].rstrip('/') + '/'
errs = []


class P(HTMLParser):
    def __init__(self):
        super().__init__(); self.tags = []; self.ld = []; self._ld = False; self.title = ''; self._t = False; self.h1 = 0; self.lms = set()
    def handle_starttag(self, t, a):
        a = dict(a); self.tags.append((t, a))
        if t == 'script' and a.get('type') == 'application/ld+json': self._ld = True; self.ld.append('')
        if t == 'title': self._t = True
        if t == 'h1': self.h1 += 1
        if t in ('header', 'nav', 'main', 'footer'): self.lms.add(t)
    def handle_endtag(self, t):
        if t == 'script': self._ld = False
        if t == 'title': self._t = False
    def handle_data(self, d):
        if self._ld: self.ld[-1] += d
        if self._t: self.title += d


def check(path, types, need_main=True):
    rel = os.path.relpath(path, SITE)
    p = P(); p.feed(open(path, encoding='utf-8').read())
    meta = {(a.get('name') or a.get('property')): a.get('content') for t, a in p.tags if t == 'meta'}
    canon = [a.get('href') for t, a in p.tags if t == 'link' and a.get('rel') == 'canonical']
    for k in ('description', 'og:title', 'og:description', 'og:image', 'og:url', 'twitter:card', 'twitter:image'):
        if not meta.get(k): errs.append(f'{rel}: missing {k}')
    if not p.title.strip(): errs.append(f'{rel}: empty <title>')
    if len(canon) != 1 or not canon[0].startswith(BASE): errs.append(f'{rel}: canonical {canon}')
    if not (50 <= len(meta.get('description') or '') <= 170): errs.append(f'{rel}: description length {len(meta.get("description") or "")}')
    if need_main and p.h1 != 1: errs.append(f'{rel}: {p.h1} <h1>')   # about/docs/files render their h1 client-side
    for lm in ('header', 'nav', 'footer') + (('main',) if need_main else ()):
        if lm not in p.lms: errs.append(f'{rel}: no <{lm}>')
    got = []
    for blob in p.ld:
        try:
            o = json.loads(blob); got.append(o.get('@type'))
            if o.get('@context') != 'https://schema.org': errs.append(f'{rel}: JSON-LD @context')
            if re.search(r'"(offers|aggregateRating|review|price)"', blob): errs.append(f'{rel}: JSON-LD contains price/rating/review')
        except Exception as ex:
            errs.append(f'{rel}: JSON-LD parse error {ex}')
    for t in types:
        if t not in got: errs.append(f'{rel}: JSON-LD {t} missing (got {got})')
    for t, a in p.tags:
        ref = a.get('src') if t in ('img', 'script') else a.get('href') if t == 'link' and a.get('rel') in ('stylesheet', 'icon', 'manifest') else a.get('href') if t == 'a' else None
        if t == 'img':
            if not (a.get('width') and a.get('height') and a.get('alt')): errs.append(f'{rel}: <img> without width/height/alt {a.get("src")}')
        if t == 'use':
            ref = a.get('href', '').split('#')[0] or None
        if not ref or ref.startswith(('#', 'mailto:', 'javascript:', 'data:')):
            continue
        if ref.startswith(('http://', 'https://', '//')):
            if t != 'a': errs.append(f'{rel}: external resource {ref}')
            continue
        u = urljoin('/' + rel, ref); pth = unquote(urlsplit(u).path).lstrip('/')
        if pth.endswith('/') or pth == '': pth += 'index.html'
        if not os.path.exists(os.path.join(SITE, pth)): errs.append(f'{rel}: broken local ref {ref}')
    return p.title.strip(), meta.get('description'), canon[0] if canon else None


models = json.load(open(os.path.join(SITE, 'data/models.json')))
titles, descs, canons = {}, {}, {}
for m in models:
    f = os.path.join(SITE, 'board', m['id'], 'index.html')
    if not os.path.exists(f):
        errs.append(f'missing board page {m["id"]}'); continue
    t, d, c = check(f, ['TechArticle', 'BreadcrumbList'])
    titles.setdefault(t, []).append(m['id']); descs.setdefault(d, []).append(m['id']); canons.setdefault(c, []).append(m['id'])
vend = glob.glob(os.path.join(SITE, 'vendor/*/index.html'))
for f in vend:
    check(f, ['CollectionPage', 'BreadcrumbList'])
check(os.path.join(SITE, 'index.html'), ['WebSite', 'ItemList'])
for fn in ('about.html', 'docs.html', 'files.html'):
    check(os.path.join(SITE, fn), [], need_main=False)
for k, v in list(titles.items()) + list(descs.items()) + list(canons.items()):
    if len(v) > 1: errs.append(f'duplicate title/description/canonical {k!r}: {v[:4]}')
# sitemap + robots
try:
    sm = ET.parse(os.path.join(SITE, 'sitemap.xml')).getroot()
    ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    locs = [u.find('s:loc', ns).text for u in sm.findall('s:url', ns)]
    lms = [u.find('s:lastmod', ns).text for u in sm.findall('s:url', ns)]
    if any(not re.match(r'^\d{4}-\d\d-\d\d$', x or '') for x in lms): errs.append('sitemap: bad lastmod')
    want = {BASE} | {f'{BASE}board/{m["id"]}/' for m in models} | {BASE + os.path.relpath(os.path.dirname(f), SITE) + '/' for f in vend}
    miss = want - set(locs)
    if miss: errs.append(f'sitemap missing {len(miss)}: {sorted(miss)[:3]}')
    if len(locs) != len(set(locs)): errs.append('sitemap has duplicates')
except Exception as ex:
    errs.append(f'sitemap.xml invalid: {ex}'); locs = []
rb = open(os.path.join(SITE, 'robots.txt')).read()
if f'Sitemap: {BASE}sitemap.xml' not in rb: errs.append('robots.txt does not point to the sitemap')
big = [f for f in glob.glob(os.path.join(SITE, '**', '*'), recursive=True) if os.path.isfile(f) and os.path.getsize(f) > 25 * 1024 * 1024]
if big: errs.append(f'files > 25 MiB: {big}')
if not os.path.exists(os.path.join(SITE, 'og-image.png')): errs.append('og-image.png missing')
print(f'seo check: {len(models)} board pages, {len(vend)} vendor pages, sitemap {len(locs)} URLs, errors {len(errs)}')
for x in errs[:40]: print('  ', x)
sys.exit(1 if errs else 0)
