#!/usr/bin/env python3
"""Scrape guition.com: the Model List table (EN + SK) and every product page from
sitemap.xml (spec table, description, gallery images, spec PDFs).
Writes data/raw/guition_table.json, data/raw/guition_products.json and downloads
images / product PDFs into site/assets/img/guition and site/files/guition.
"""
import json, os, re, sys, time, hashlib
from urllib.parse import urljoin, quote, unquote, urlsplit
import requests
from bs4 import BeautifulSoup
import concurrent.futures as cf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, 'site')
BASE = 'https://www.guition.com'
S = requests.Session()
S.headers['User-Agent'] = 'Mozilla/5.0 (guition-catalog-builder)'
CATS = ['esp32-display-module', 'esp32p4-display-module', 'esp32s31-display-module-', 'hmi-display-module',
        'parallel-lcd-display', 'spi-display-module', 'spi-lcd-display']


def get(url, binary=False):
    for i in range(5):
        try:
            r = S.get(url, timeout=60)
            r.raise_for_status()
            return r.content if binary else r.content.decode('utf-8', 'replace')
        except Exception:
            if i == 4:
                raise
            time.sleep(2 * (i + 1))


def clean(s):
    s = (s or '').replace('\u00a0', ' ').replace('Â', '').replace('″', '"')
    return re.sub(r'\s+', ' ', s).strip()


def abs_url(u):
    return urljoin(BASE, u)


def parse_table(html, lang):
    soup = BeautifulSoup(html, 'html.parser')
    tb = soup.find('table')
    rows = tb.find_all('tr')
    header = [clean(c.get_text(' ')) for c in rows[0].find_all(['td', 'th'])]
    grid, pending = [], {}
    for tr in rows[1:]:
        cells = tr.find_all(['td', 'th'])
        row, ci, col = [], 0, 0
        while col < len(header):
            if col in pending and pending[col][0] > 0:
                n, val = pending[col]
                row.append(val)
                pending[col] = (n - 1, val)
                col += 1
                continue
            if ci >= len(cells):
                row.append(None); col += 1; continue
            c = cells[ci]; ci += 1
            imgs = [abs_url((i.get('data-src') or i.get('src') or '').split('?')[0]) for i in c.find_all('img')
                    if 'upload' in (i.get('data-src') or i.get('src') or '')]
            links = [{'text': clean(a.get_text(' ')), 'href': a['href']} for a in c.find_all('a', href=True)]
            val = {'text': clean(c.get_text(' ')), 'imgs': imgs, 'links': links}
            rs = int(c.get('rowspan') or 1)
            if rs > 1:
                pending[col] = (rs - 1, val)
            row.append(val)
            col += 1
        grid.append(dict(zip(header, row)))
    return header, grid


def table_records(header, grid):
    recs = []
    for r in grid:
        def T(k):
            v = r.get(k)
            return v['text'] if v else ''
        mcell = r.get('Model Number') or {}
        txt = mcell.get('text', '')
        m = re.match(r'^(\S+)\s*(.*)$', txt)
        model = m.group(1) if m else txt
        resm = re.search(r'(\d+)\s*[*×x]\s*(\d+)', txt)
        prod = next((l['href'] for l in mcell.get('links', []) if 'guition.com' in l['href'] or l['href'].startswith('/')), None)
        dl = r.get('Download Development Files') or {}
        dls = []
        for l in dl.get('links', []):
            href = l['href'].replace('https://https://', 'https://')
            name = l['text']
            # the site sometimes links the wrong archive; trust the label and rebuild from it
            if name and href.rsplit('/', 1)[-1] != quote(name):
                fixed = href.rsplit('/', 1)[0] + '/' + quote(name)
                dls.append({'name': name, 'url': fixed, 'site_href': l['href'], 'note': 'link on guition.com pointed elsewhere; URL rebuilt from label'})
            else:
                dls.append({'name': name, 'url': href})
        img = (r.get('Product  Image') or r.get('Product Image') or {}).get('imgs') or []
        recs.append({
            'model': model,
            'resolution': f"{resm.group(1)}x{resm.group(2)}" if resm else '',
            'size': T('Size'), 'panel': T('TFT'), 'touch': T('Touch Type'), 'shell': T('Shell'),
            'controller': T('Controller'), 'frequency': T('Main Frequency'), 'wifi': T('WIFI'), 'bt': T('BT'),
            'sram': T('SRAM'), 'psram': T('PSRAM'), 'rom': T('ROM'), 'flash': T('Flash'), 'interface': T('Interface'),
            'speaker': T('Speaker Interface'), 'software': T('Software'),
            'product_url': abs_url(prod) if prod else None, 'downloads': dls, 'thumb': img[0] if img else None,
        })
    return recs


def parse_product(url, nuxt_ver):
    try:
        html = get(url)
    except Exception as e:
        return {'url': url, 'error': str(e), 'category': urlsplit(url).path.strip('/').split('/')[0], 'title': '',
                'model': None, 'intro': '', 'specs': [], 'files': [], 'main_image': None, 'gallery': []}
    soup = BeautifulSoup(html, 'html.parser')
    for s in soup(['script', 'style', 'noscript']):
        s.decompose()
    txt = soup.get_text('\n', strip=True)
    model = None
    m = re.search(r'Model:\s*\n?\s*([^\n]+)', txt)
    if m:
        model = clean(m.group(1))
    intro = ''
    m2 = re.search(r'Model:[^\n]*\n(.*?)\nSend Inquiry', txt, re.S)
    if m2:
        intro = clean(m2.group(1))
    h1 = soup.find('h1')
    specs = []
    for tb in soup.find_all('table'):
        for tr in tb.find_all('tr'):
            cs = [clean(c.get_text(' ')) for c in tr.find_all(['td', 'th'])]
            if len(cs) >= 2 and cs[0] and cs[0].lower() not in ('parameter', 'parameters', 'item', 'specification'):
                specs.append([cs[0], ' / '.join(x for x in cs[1:] if x)])
    files = sorted(set(abs_url(a['href']) for a in BeautifulSoup(html, 'html.parser').find_all('a', href=True) if '/file/' in a['href']))
    og = BeautifulSoup(html, 'html.parser').find('meta', property='og:image')
    path = urlsplit(url).path
    gallery = []
    try:
        pl = get(f'{BASE}/_nuxt/static/{nuxt_ver}{path}/payload.js').replace('\\u002F', '/')
        for g in re.findall(r'/icms/upload/[^"]*?productmanager-productpic/[^"]+?\.(?:webp|jpg|jpeg|png)', pl):
            u = abs_url(g)
            if u not in gallery:
                gallery.append(u)
    except Exception as e:
        pass
    main = abs_url(og['content']) if og and og.get('content') else None
    return {'url': url, 'category': path.strip('/').split('/')[0], 'title': clean(h1.get_text()) if h1 else '',
            'model': model, 'intro': intro, 'specs': specs, 'files': files, 'main_image': main, 'gallery': gallery}


def fetch_asset(url, subdir):
    name = unquote(urlsplit(url).path.rsplit('/', 1)[-1])
    ext = os.path.splitext(name)[1].lower() or '.bin'
    h = hashlib.sha1(url.encode()).hexdigest()[:12]
    if subdir.startswith('files'):
        fn = re.sub(r'[^A-Za-z0-9._-]+', '_', os.path.splitext(name)[0])[:80] + '_' + h[:6] + ext
    else:
        fn = h + ext
    rel = f'{subdir}/{fn}'
    dst = os.path.join(SITE, rel)
    if not os.path.exists(dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        data = get(quote(url, safe=':/?=&%'), binary=True)
        open(dst, 'wb').write(data)
    return rel


def main():
    out = {}
    for lang, u in [('en', BASE + '/model-selection'), ('sk', BASE + '/sk/model-selection')]:
        html = get(u)
        header, grid = parse_table(html, lang)
        out[lang] = {'url': u, 'header': header, 'records': table_records(header, grid)}
        print(lang, len(out[lang]['records']), 'table rows')
    html = get(BASE + '/model-selection')
    nuxt_ver = re.search(r'_nuxt/static/(\d+)', html).group(1)
    sm = get(BASE + '/sitemap.xml')
    urls = sorted(set(u for u in re.findall(r'<loc>([^<]+)</loc>', sm)
                      if re.match(r'https://www\.guition\.com/(%s)/[^/]+$' % '|'.join(map(re.escape, CATS)), u)))
    for rec in out['en']['records']:
        if rec['product_url'] and rec['product_url'] not in urls:
            urls.append(rec['product_url'])
    print(len(urls), 'product pages')
    prods = []
    with cf.ThreadPoolExecutor(6) as ex:
        for p in ex.map(lambda u: (lambda: parse_product(u, nuxt_ver))() if True else None, urls):
            prods.append(p)
    # assets
    jobs = []
    for p in prods:
        imgs = ([p['main_image']] if p['main_image'] else []) + p['gallery']
        p['images_local'] = []
        p['files_local'] = []
    def dl_prod(p):
        imgs = []
        for u in ([p['main_image']] if p['main_image'] else []) + p['gallery'][:8]:
            if u in imgs: continue
            imgs.append(u)
        for u in imgs:
            try:
                p['images_local'].append({'src': u, 'local': fetch_asset(u, 'assets/img/guition')})
            except Exception as e:
                p.setdefault('errors', []).append(f'img {u}: {e}')
        for u in p['files']:
            try:
                p['files_local'].append({'src': u, 'local': fetch_asset(u, 'files/guition')})
            except Exception as e:
                p.setdefault('errors', []).append(f'file {u}: {e}')
    with cf.ThreadPoolExecutor(8) as ex:
        list(ex.map(dl_prod, prods))
    for rec in out['en']['records']:
        if rec['thumb']:
            try:
                rec['thumb_local'] = fetch_asset(rec['thumb'], 'assets/img/guition')
            except Exception as e:
                rec['thumb_error'] = str(e)
    json.dump(out, open(os.path.join(ROOT, 'data/raw/guition_table.json'), 'w'), indent=1, ensure_ascii=False)
    json.dump(prods, open(os.path.join(ROOT, 'data/raw/guition_products.json'), 'w'), indent=1, ensure_ascii=False)
    print('products', len(prods), 'with model', sum(1 for p in prods if p['model']))


if __name__ == '__main__':
    main()
