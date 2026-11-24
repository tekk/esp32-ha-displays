#!/usr/bin/env python3
"""Static, crawlable SEO layer for the catalog (runs on every build, after features/photos).

Writes (all relative, no external requests, same CSP as the SPA):
  site/board/<id>/index.html     one static page per board: unique title/description/canonical, Open Graph,
                                 Twitter Card, JSON-LD (TechArticle about a Product + BreadcrumbList),
                                 photo with alt/width/height, specs table with source links, features,
                                 official links and a link into the interactive page (model.html?id=…)
  site/vendor/<slug>/index.html  one page per manufacturer (CollectionPage + ItemList + BreadcrumbList)
  site/index.html, about.html, docs.html, files.html
                                 <head> SEO block (canonical, OG/Twitter, JSON-LD WebSite + ItemList on the
                                 home page) and a static footer directory of every board / manufacturer page
  site/og-image.png              1200×630 social preview (Pillow; fonts converted from the bundled woff2)
  site/sitemap.xml, site/robots.txt
Only verified catalog data is used – no prices, ratings or reviews.
lastmod per URL changes only when that page's content changes (state in data/raw/seo_state.json)."""
import datetime, hashlib, html, io, json, os, re, sys
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, 'site')
sys.path.insert(0, os.path.join(ROOT, 'build'))
CFG = json.load(open(os.path.join(ROOT, 'build/config.json')))
BASE = CFG['offline'].get('pages_url', 'https://tekk.github.io/esp32-ha-displays/').rstrip('/') + '/'
NAME = 'ESP32 Display Catalog'
STATE_F = os.path.join(ROOT, 'data/raw/seo_state.json')
CSP = ("default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
       "font-src 'self'; connect-src 'self'; frame-src 'self' blob: data:; worker-src 'self'; object-src 'none'")
try:
    from build_site import FIELD_LABELS
except Exception:
    FIELD_LABELS = {}
LABELS = dict(FIELD_LABELS)
LABELS.update({'size': 'Screen size', 'resolution': 'Resolution', 'panel': 'Panel', 'interface': 'Display interface', 'driver_ic': 'Display driver',
               'touch': 'Touch', 'touch_ic': 'Touch controller', 'mcu': 'MCU / SoC', 'mcu_family': 'MCU family', 'coprocessor': 'Co-processor',
               'flash': 'Flash', 'psram': 'PSRAM', 'wifi': 'Wi-Fi', 'bt': 'Bluetooth', 'usb': 'USB', 'sku': 'SKU', 'category': 'Category'})
SPEC_ORDER = ['size', 'resolution', 'panel', 'shape', 'interface', 'driver_ic', 'touch', 'touch_ic', 'mcu', 'mcu_family', 'coprocessor', 'frequency',
              'flash', 'psram', 'sram', 'wifi', 'bt', 'usb', 'sku', 'category']
SKIP_KEYS = {'size_in', 'w', 'h', 'pixels', 'category_slug'}
e = lambda s: html.escape(str(s if s is not None else ''), quote=True)


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


def clip(s, n):
    s = re.sub(r'\s+', ' ', s).strip()
    return s if len(s) <= n else s[:n - 1].rsplit(' ', 1)[0].rstrip(',;:–-') + '…'


def jsonld(obj):
    return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/') + '</script>'


def head(title, desc, canon, image, depth, og_type='website', extra=''):
    r = '../' * depth
    img_abs = BASE + image
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{e(canon)}">
<meta name="robots" content="index,follow,max-image-preview:large">
<meta property="og:site_name" content="{NAME}">
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(canon)}">
<meta property="og:image" content="{e(img_abs)}">
<meta property="og:image:alt" content="{e(title)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{e(title)}">
<meta name="twitter:description" content="{e(desc)}">
<meta name="twitter:image" content="{e(img_abs)}">
<meta name="theme-color" content="#0e0f11">
<link rel="manifest" href="{r}manifest.webmanifest">
<link rel="icon" href="{r}assets/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="{r}assets/css/app.css">
{extra}</head>
"""


def topbar(depth, active=''):
    r = '../' * depth
    nav = [('index.html', 'Boards', 'models'), ('docs.html', 'Docs search', 'docs'), ('files.html', 'Files', 'files'), ('about.html', 'About', 'about')]
    return (f'<header class="topbar"><a class="brand" href="{r}index.html">{NAME}<small>Guition · Waveshare · M5Stack · LilyGO · Elecrow · Seeed · more</small></a>'
            f'<nav class="nav" aria-label="Main">' + ''.join(f'<a href="{r}{h}" class="{"active" if k == active else ""}">{t}</a>' for h, t, k in nav) + '</nav></header>')


def footer(depth, vendors):
    r = '../' * depth
    return (f'<footer class="footer"><nav aria-label="Manufacturers">Manufacturers: ' +
            ' · '.join(f'<a href="{r}vendor/{v}/">{e(n)}</a>' for v, n, _ in vendors) +
            '</nav><p>Unofficial catalog – not affiliated with any manufacturer. Every parameter links to its source; empty = not stated by the source. '
            f'<a href="{r}sitemap.xml">Sitemap</a></p></footer>')


def img_dims(rel):
    try:
        from PIL import Image
        with Image.open(os.path.join(SITE, rel)) as im:
            return im.size
    except Exception:
        return None


def summary(m):
    p = m['params']
    bits = [p.get('size'), p.get('resolution'), p.get('panel'), (p.get('touch') + ' touch') if p.get('touch') in ('Capacitive', 'Resistive') else None]
    disp = ' '.join(b for b in bits if b)
    chip = p.get('mcu_family') or ''
    mem = ', '.join(x for x in [(p.get('flash') + ' flash') if p.get('flash') else '', (p.get('psram') + ' PSRAM') if p.get('psram') else ''] if x)
    return disp, chip, mem


def board_page(m, vname, vslug, depth=2):
    p = m['params']
    disp, chip, mem = summary(m)
    canon = f'{BASE}board/{m["id"]}/'
    photo = next((i for i in m['images'] if i.get('kind') in ('photo', 'product')), m['images'][0] if m['images'] else None)
    og = photo['src'] if photo else 'og-image.png'
    title = clip(f'{m["model"]} – {vname} {" ".join(x for x in [p.get("size"), chip] if x)} display board specs', 70) + f' | {NAME}'
    feats = m.get('features') or []
    desc_bits = [f'{m["model"]} by {vname}', disp + ' display' if disp else '', f'{chip}' if chip else '', mem,
                 ', '.join(f['name'] if 'name' in f else f['label'] for f in feats[:6])]
    desc = clip('; '.join(b for b in desc_bits if b) + '. Specs with sources, photos, official docs and downloads.', 158)
    srcs = {}
    for r in m.get('specs_raw', []):
        if r.get('key') and r.get('source') and r['key'] not in srcs:
            srcs[r['key']] = r['source']
    keys = [k for k in SPEC_ORDER if p.get(k)] + sorted(k for k in p if k not in SPEC_ORDER and k not in SKIP_KEYS and p.get(k) and not k.startswith('_'))
    rows = ''.join(f'<tr><th scope="row">{e(LABELS.get(k, k.replace("_", " ").capitalize()))}</th><td>{e(p[k])}</td>'
                   f'<td>{f"<a href=\"{e(srcs[k])}\" rel=\"noopener nofollow\">source</a>" if srcs.get(k) else ""}</td></tr>' for k in keys)
    fl = ''.join(f'<li class="fc-{e(f["category"])}"><svg width="18" height="18" aria-hidden="true"><use href="../../assets/img/features.svg#f-{e(f["icon"])}"/></svg>'
                 f'<span>{e(f["label"])}</span></li>' for f in feats)
    links = [l for l in m.get('links', []) if l.get('url', '').startswith('http')]
    ll = ''.join(f'<li><a href="{e(l["url"])}" rel="noopener">{e(l.get("title") or l["url"])}</a></li>' for l in links[:25])
    files = [f for f in m.get('files', []) if f.get('name')]
    fil = ''.join(f'<li>{e(f["name"])}' + (f' – <a href="{e(f["url"])}" rel="noopener nofollow">original</a>' if f.get('url', '').startswith('http') else '') + '</li>' for f in files[:30])
    notes = ''.join(f'<li>{e(n["text"])}</li>' for n in m.get('notes', [])[:8])
    fig = ''
    if photo:
        w, h = photo.get('w'), photo.get('h')
        if not (w and h):
            w, h = img_dims(photo['src']) or (800, 600)
        alt = f'{m["model"]} – {vname} ESP32 display board' + (f' ({disp})' if disp else '')
        fig = (f'<figure class="sfig"><img src="../../{e(photo["src"])}" width="{w}" height="{h}" alt="{e(alt)}" decoding="async" fetchpriority="high">'
               f'<figcaption>Photo: {e(photo.get("note") or photo.get("kind") or "")}' +
               (f' – <a href="{e(photo["source_page"])}" rel="noopener nofollow">source</a>' if photo.get('source_page') else '') + '</figcaption></figure>')
    sku = p.get('sku')
    product = {'@type': 'Product', 'name': m['model'], 'description': desc, 'brand': {'@type': 'Brand', 'name': vname},
               'manufacturer': {'@type': 'Organization', 'name': vname}, 'category': 'ESP32 display development board', 'url': canon,
               'additionalProperty': [{'@type': 'PropertyValue', 'name': LABELS.get(k, k), 'value': str(p[k])} for k in keys[:25]]}
    if photo: product['image'] = [BASE + photo['src']]
    if sku: product['sku'] = sku
    if m.get('sources'): product['sameAs'] = [s for s in m['sources'] if s.startswith('http')][:5]
    ld = [{'@context': 'https://schema.org', '@type': 'TechArticle', 'headline': clip(f'{m["model"]} ({vname}) – specifications and features', 110),
           'description': desc, 'url': canon, 'mainEntityOfPage': canon, 'inLanguage': 'en', 'about': product,
           'publisher': {'@type': 'Organization', 'name': NAME, 'url': BASE}, **({'image': [BASE + photo['src']]} if photo else {})},
          {'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
              {'@type': 'ListItem', 'position': 1, 'name': 'ESP32 display boards', 'item': BASE},
              {'@type': 'ListItem', 'position': 2, 'name': vname, 'item': f'{BASE}vendor/{vslug}/'},
              {'@type': 'ListItem', 'position': 3, 'name': m['model'], 'item': canon}]}]
    interactive = f'../../model.html?id={quote(m["id"])}'
    body = f"""<body>
{topbar(depth)}
<main class="wrap seo" id="main">
<nav class="crumbs" aria-label="Breadcrumb"><a href="../../index.html">ESP32 display boards</a> › <a href="../../vendor/{vslug}/">{e(vname)}</a> › <span aria-current="page">{e(m['model'])}</span></nav>
<article>
<div class="dhead">
{fig}
<div class="dinfo">
<h1>{e(m['model'])}</h1>
<p class="sub">{e(vname)}{(' · ' + e(m['title'])) if m.get('title') and m['title'] != m['model'] else ''}</p>
<p>{e(m['model'])} is {('an' if (disp or 'x')[0] in '18' else 'a')} {e(disp + ' ' if disp else '')}ESP32 display board by {e(vname)}{(' based on the ' + e(chip)) if chip else ''}{(' with ' + e(mem)) if mem else ''}.</p>
<p class="cta"><a class="btn pri" href="{interactive}">Open the interactive page (gallery, files, archives) →</a></p>
</div>
</div>
{f'<section class="sec"><h2>Features, ports &amp; interfaces</h2><ul class="sfeat">{fl}</ul></section>' if fl else ''}
<section class="sec"><h2>Specifications</h2><table class="kv2 sspec"><thead><tr><th scope="col">Parameter</th><th scope="col">Value</th><th scope="col">Source</th></tr></thead><tbody>{rows}</tbody></table></section>
{f'<section class="sec"><h2>Official links &amp; documentation</h2><ul>{ll}</ul></section>' if ll else ''}
{f'<section class="sec"><h2>Files</h2><p>Offline copies are available on the <a href="{interactive}">interactive page</a>.</p><ul>{fil}</ul></section>' if fil else ''}
{f'<section class="sec"><h2>Notes</h2><ul>{notes}</ul></section>' if notes else ''}
</article>
</main>
"""
    return head(title, desc, canon, og, depth, 'article', '\n'.join(jsonld(x) for x in ld) + '\n') + body


def vendor_page(vslug, vname, ms, vendors, depth=2):
    canon = f'{BASE}vendor/{vslug}/'
    title = f'{vname} ESP32 display boards ({len(ms)}) – specs & features | {NAME}'
    chips = sorted({m['params'].get('mcu_family') for m in ms if m['params'].get('mcu_family')})
    desc = clip(f'All {len(ms)} {vname} ESP32 display boards in the catalog ({", ".join(chips)}): screen size, resolution, touch, flash/PSRAM, Wi-Fi/Bluetooth, ports and official docs.', 158)
    cards = []
    for m in ms:
        disp, chip, mem = summary(m)
        im = m['images'][0] if m['images'] else None
        th = ''
        if im:
            rel = im.get('thumb') or im['src']
            w, h = img_dims(rel) or (400, 300)
            th = f'<img src="../../{e(rel)}" width="{w}" height="{h}" loading="lazy" decoding="async" alt="{e(m["model"] + " – " + vname + " ESP32 display board")}">'
        cards.append(f'<li class="vcard"><a href="../../board/{e(m["id"])}/">{th}<b>{e(m["model"])}</b><span>{e(" · ".join(x for x in [disp, chip, mem] if x))}</span></a></li>')
    ld = [{'@context': 'https://schema.org', '@type': 'CollectionPage', 'name': f'{vname} ESP32 display boards', 'url': canon, 'description': desc,
           'mainEntity': {'@type': 'ItemList', 'numberOfItems': len(ms), 'itemListElement': [
               {'@type': 'ListItem', 'position': i + 1, 'url': f'{BASE}board/{m["id"]}/', 'name': m['model']} for i, m in enumerate(ms)]}},
          {'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
              {'@type': 'ListItem', 'position': 1, 'name': 'ESP32 display boards', 'item': BASE},
              {'@type': 'ListItem', 'position': 2, 'name': vname, 'item': canon}]}]
    og = next((m['images'][0]['src'] for m in ms if m['images']), 'og-image.png')
    body = f"""<body>
{topbar(depth, 'models')}
<main class="wrap seo" id="main">
<nav class="crumbs" aria-label="Breadcrumb"><a href="../../index.html">ESP32 display boards</a> › <span aria-current="page">{e(vname)}</span></nav>
<h1>{e(vname)} ESP32 display boards</h1>
<p>{len(ms)} boards{(' – ' + e(', '.join(chips))) if chips else ''}. <a href="../../index.html#f.vendor={quote(vname)}">Filter and compare them in the interactive catalog →</a></p>
<ul class="vgrid">{''.join(cards)}</ul>
</main>
{footer(depth, vendors)}
</body>
</html>
"""
    return head(title, desc, canon, og, depth, 'website', '\n'.join(jsonld(x) for x in ld) + '\n') + body


def replace_block(text, tag, block):
    a, b = f'<!--SEO:{tag}-->', f'<!--/SEO:{tag}-->'
    if a in text:
        return re.sub(re.escape(a) + r'.*?' + re.escape(b), lambda _: a + block + b, text, flags=re.S)
    return None


def top_pages(models, vendors, meta):
    n = len(models)
    pages = {
        'index.html': (f'ESP32 Display Catalog – {n} ESP32 display boards with specs (Guition, Waveshare, M5Stack, LilyGO …)',
                       f'Searchable offline catalog of {n} ESP32 / ESP32-S3 / ESP32-P4 / C6 display boards from ' + ', '.join(v[1] for v in vendors) +
                       ': screen, touch, flash/PSRAM, Wi-Fi/BT, ports, photos, official docs and downloads.'),
        'about.html': (f'About – {NAME}', 'How the ESP32 Display Catalog is built: sources, data rules (every value sourced, nothing guessed), offline files, monthly updates.'),
        'docs.html': (f'Documentation search – {NAME}', 'Full-text search across the extracted documentation, schematics and READMEs of ESP32 display boards (offline).'),
        'files.html': (f'Files & archives – {NAME}', 'All official ZIP/RAR archives, PDFs and repository snapshots of ESP32 display boards, available offline with sha256.'),
    }
    for fn, (title, desc) in pages.items():
        p = os.path.join(SITE, fn)
        t = open(p).read()
        canon = BASE if fn == 'index.html' else BASE + fn
        desc = clip(desc, 160)
        ld = ''
        if fn == 'index.html':
            ld = jsonld({'@context': 'https://schema.org', '@type': 'WebSite', 'name': NAME, 'url': BASE, 'description': desc, 'inLanguage': 'en'}) + jsonld(
                {'@context': 'https://schema.org', '@type': 'ItemList', 'name': 'ESP32 display boards', 'numberOfItems': n, 'itemListElement': [
                    {'@type': 'ListItem', 'position': i + 1, 'url': f'{BASE}board/{m["id"]}/', 'name': m['model']} for i, m in enumerate(models)]})
        blk = (f'\n<title>{e(title)}</title>\n<meta name="description" content="{e(desc)}">\n<link rel="canonical" href="{canon}">\n'
               f'<meta property="og:site_name" content="{NAME}">\n<meta property="og:type" content="website">\n<meta property="og:title" content="{e(title)}">\n'
               f'<meta property="og:description" content="{e(desc)}">\n<meta property="og:url" content="{canon}">\n<meta property="og:image" content="{BASE}og-image.png">\n'
               f'<meta property="og:image:width" content="1200">\n<meta property="og:image:height" content="630">\n<meta name="twitter:card" content="summary_large_image">\n'
               f'<meta name="twitter:title" content="{e(title)}">\n<meta name="twitter:description" content="{e(desc)}">\n<meta name="twitter:image" content="{BASE}og-image.png">\n{ld}\n')
        new = replace_block(t, 'HEAD', blk)
        if new is None:      # first run: swap the old <title>/<meta description> for the marked block
            t = re.sub(r'<title>.*?</title>\s*', '', t, flags=re.S)
            t = re.sub(r'<meta name="description"[^>]*>\s*', '', t)
            new = t.replace('<meta name="theme-color"', f'<!--SEO:HEAD-->{blk}<!--/SEO:HEAD-->\n<meta name="theme-color"', 1)
        t = new
        foot = footer(0, vendors)
        if fn == 'index.html':
            groups = ''.join(f'<details><summary>{e(vn)} ({cnt})</summary><ul>' + ''.join(
                f'<li><a href="board/{e(m["id"])}/">{e(m["model"])}</a></li>' for m in models if m['vendor'] == vn) + '</ul></details>' for _, vn, cnt in vendors)
            foot = foot.replace('<footer class="footer">', f'<footer class="footer"><section class="dir" aria-label="All boards"><details><summary>All {n} boards</summary>{groups}</details></section>', 1)
        act = {'index.html': 'models', 'docs.html': 'docs', 'files.html': 'files', 'about.html': 'about'}[fn]
        t2 = replace_block(t, 'TOP', topbar(0, act))
        t = t2 if t2 is not None else re.sub(r'<body([^>]*)>', lambda mm: f'<body{mm.group(1)}>\n<!--SEO:TOP-->{topbar(0, act)}<!--/SEO:TOP-->', t, count=1)
        nb = replace_block(t, 'FOOT', '\n' + foot + '\n')
        if nb is None:
            i = t.find('<script src=')
            i = i if i > t.find('<body') else t.rfind('</body>')
            nb = t[:i] + f'<!--SEO:FOOT-->\n{foot}\n<!--/SEO:FOOT-->\n' + t[i:]
        open(p, 'w').write(nb)


def og_image(models, vendors):
    from PIL import Image, ImageDraw, ImageFont
    def font(name, size):
        try:
            from fontTools.ttLib import TTFont
            f = TTFont(os.path.join(SITE, 'assets/fonts', name)); f.flavor = None
            b = io.BytesIO(); f.save(b); b.seek(0)
            return ImageFont.truetype(b, size)
        except Exception:
            return ImageFont.load_default()
    W, H = 1200, 630
    im = Image.new('RGB', (W, H), (14, 15, 17))
    d = ImageDraw.Draw(im)
    d.text((60, 52), NAME, font=font('roboto-condensed-latin-700-normal.woff2', 64), fill=(255, 255, 255))
    d.text((62, 132), f'{len(models)} ESP32 display boards · specs with sources · offline', font=font('montserrat-latin-500-normal.woff2', 28), fill=(170, 174, 182))
    d.text((62, 176), ' · '.join(v[1] for v in vendors), font=font('montserrat-latin-500-normal.woff2', 22), fill=(120, 124, 132))
    cols = [(61, 123, 255), (255, 138, 31), (0, 232, 208), (255, 61, 154), (46, 230, 107), (255, 214, 10), (154, 107, 255), (168, 255, 31), (31, 182, 255), (255, 69, 69)]
    for i, c in enumerate(cols):
        d.rounded_rectangle((62 + i * 34, 222, 88 + i * 34, 230), 3, fill=c)
    picks, seen = [], set()
    for m in models:            # one photo per manufacturer first, then fill
        if m['images'] and m['vendor'] not in seen and m['images'][0].get('thumb'):
            picks.append(m); seen.add(m['vendor'])
    picks += [m for m in models if m['images'] and m not in picks and m['images'][0].get('thumb')][:10 - len(picks)]
    x0, y0, tw, th = 62, 262, 208, 160
    for i, m in enumerate(picks[:10]):
        x, y = x0 + (i % 5) * (tw + 14), y0 + (i // 5) * (th + 14)
        d.rounded_rectangle((x, y, x + tw, y + th), 10, fill=(255, 255, 255))
        try:
            with Image.open(os.path.join(SITE, m['images'][0]['thumb'])) as t:
                t = t.convert('RGB'); t.thumbnail((tw - 16, th - 16))
                im.paste(t, (x + (tw - t.width) // 2, y + (th - t.height) // 2))
        except Exception:
            pass
    im.save(os.path.join(SITE, 'og-image.png'), optimize=True)


def main():
    models = json.load(open(os.path.join(SITE, 'data/models.json')))
    meta = json.load(open(os.path.join(SITE, 'data/meta.json')))
    today = datetime.date.today().isoformat()
    state = json.load(open(STATE_F)) if os.path.exists(STATE_F) else {}
    vorder = {}
    for m in models:
        vorder.setdefault(m['vendor'], []).append(m)
    vendors = sorted(((slug(v), v, len(ms)) for v, ms in vorder.items()), key=lambda x: (-x[2], x[1]))
    pages = {}
    # stale static pages of boards that no longer exist are removed
    for sub in ('board', 'vendor'):
        d = os.path.join(SITE, sub)
        keep = {m['id'] for m in models} if sub == 'board' else {v[0] for v in vendors}
        if os.path.isdir(d):
            for x in os.listdir(d):
                if x not in keep:
                    import shutil; shutil.rmtree(os.path.join(d, x))
    for m in models:
        vs = slug(m['vendor'])
        h = board_page(m, m['vendor'], vs) + footer(2, vendors) + '\n</body>\n</html>\n'
        pages[f'board/{m["id"]}/'] = h
    for vs, vn, _ in vendors:
        pages[f'vendor/{vs}/'] = vendor_page(vs, vn, vorder[vn], vendors)
    for rel, h in pages.items():
        os.makedirs(os.path.join(SITE, rel), exist_ok=True)
        open(os.path.join(SITE, rel, 'index.html'), 'w').write(h)
    top_pages(models, vendors, meta)
    og_image(models, vendors)
    # sitemap with content-based lastmod
    urls = {'': open(os.path.join(SITE, 'index.html')).read(), 'about.html': open(os.path.join(SITE, 'about.html')).read(),
            'docs.html': open(os.path.join(SITE, 'docs.html')).read(), 'files.html': open(os.path.join(SITE, 'files.html')).read()}
    urls.update(pages)
    if 'data/models.json':
        urls[''] += json.dumps([m['id'] for m in models])
    new_state, out = {}, []
    for rel, content in urls.items():
        hsh = hashlib.sha1(content.encode()).hexdigest()[:16]
        old = state.get(rel)
        lm = old[1] if old and old[0] == hsh else today
        new_state[rel] = [hsh, lm]
        pri = '1.0' if rel == '' else '0.8' if rel.startswith('vendor/') else '0.6' if rel.startswith('board/') else '0.4'
        out.append(f'<url><loc>{e(BASE + rel)}</loc><lastmod>{lm}</lastmod><priority>{pri}</priority></url>')
    open(os.path.join(SITE, 'sitemap.xml'), 'w').write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                                                     + '\n'.join(out) + '\n</urlset>\n')
    open(os.path.join(SITE, 'robots.txt'), 'w').write(f'User-agent: *\nAllow: /\nDisallow: /viewer.html\n\nSitemap: {BASE}sitemap.xml\n')
    json.dump(new_state, open(STATE_F, 'w'), indent=0)
    print(f'seo: {len(models)} board pages, {len(vendors)} vendor pages, sitemap {len(out)} URLs, og-image.png')


if __name__ == '__main__':
    main()
