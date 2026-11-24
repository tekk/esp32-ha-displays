#!/usr/bin/env python3
"""Automatic discovery + addition of new ESP32 display boards from the configured vendors.

Used by build/update.py (step "vendors") and runnable on its own:
    python3 build/autoadd.py --dry-run                 # discover + extract, print what WOULD be added
    python3 build/autoadd.py                           # write data/auto/boards/<vendor>.json
    python3 build/autoadd.py --url <product-url> ...   # extract specific pages (vendor from the host)
    python3 build/autoadd.py --url <url> --print       # show the extracted record only

Rules (same as the hand-curated data):
  * only what is literally on the official product page – every value keeps the page URL as source;
    fields that are not stated stay empty, nothing is guessed (Wi-Fi/BT versions are derived later by
    features.py from the SoC datasheet and labelled as such);
  * a candidate is accepted only when the page names an ESP32 SoC AND a built-in display with a size or
    resolution; everything else is reported as skipped with the reason;
  * de-duplicated against every existing model id / name / alias / SKU / source URL (Guition, curated, auto);
  * hand-curated files (data/curated/boards/) are never touched – auto entries live in data/auto/boards/
    and build_site.py ignores an auto entry whose model already exists elsewhere.
"""
import argparse, datetime, glob, json, os, re, sys
from urllib.parse import urljoin, urlsplit
import requests
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADIR = os.path.join(ROOT, 'data/auto/boards')
CDIR = os.path.join(ROOT, 'data/curated/boards')
S = requests.Session()
S.headers['User-Agent'] = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36 esp32-ha-displays-updater'

# vendor: (display name, slug, category, listing sources, product-link regex, display-product filter on the slug, URL prefix)
VENDORS = {
    'waveshare': dict(vendor='Waveshare', category='Waveshare ESP32 touch LCD', image_note='official Waveshare product photo',
                      listings=['https://www.waveshare.com/catalogsearch/result/?q=' + q for q in
                                ('ESP32-P4', 'ESP32-P4 LCD', 'ESP32-S3 Touch LCD', 'ESP32-S3 AMOLED', 'ESP32-C6 Touch LCD', 'ESP32-C6 LCD', 'ESP32-S3 LCD')],
                      rx=r'href="(https://www\.waveshare\.com/[a-z0-9.\-]+\.htm)"', flt=r'esp32-(p4|s3|s31|c6|c5|c3)\w*-.*(lcd|amoled|oled|display|touch|knob|epaper|e-paper)', prefix=''),
    'm5stack': dict(vendor='M5Stack', category='M5Stack (all-in-one controllers)', image_note='official M5Stack docs product photo',
                    listings=['https://docs.m5stack.com/sitemap.xml'], rx=r'(/en/core/[A-Za-z0-9_%.\-]+)',
                    flt=r'^core|^tab|dial|paper|cardputer|atoms3(?!-lite|u)|stick|tough|ink|meter|display', prefix='https://docs.m5stack.com'),
    'lilygo': dict(vendor='LilyGO', category='LilyGO (T-series)', image_note='official LilyGO product photo (lilygo.cc)',
                   listings=['https://lilygo.cc/products.json?limit=250'], rx=r'"handle":"([a-z0-9\-]+)"',
                   flt=r't-display|amoled|t-deck|t-rgb|t-panel|t-encoder|^t4|^t5|t-circle|t-qt|t-dongle|t-hmi|lcd|e-?paper|touch', prefix='https://lilygo.cc/products/'),
    'elecrow': dict(vendor='Elecrow', category='Elecrow CrowPanel', image_note='official Elecrow product photo',
                    listings=['https://www.elecrow.com/esp32-display-series-hmi-touch-screen.html'], rx=r'(https://www\.elecrow\.com/[a-z0-9\-]+\.html)',
                    flt=r'crowpanel|esp32-.*(display|hmi|lcd|terminal)', prefix=''),
    'makerfabs': dict(vendor='Makerfabs', category='Makerfabs MaTouch', image_note='official Makerfabs product photo',
                      listings=['https://www.makerfabs.com/catalogsearch/result/?q=matouch', 'https://www.makerfabs.com/catalogsearch/result/?q=esp32+display'],
                      rx=r'(https://www\.makerfabs\.com/[a-z0-9\-]+\.html)', flt=r'matouch.*(esp32|display|tft|ips|amoled)|esp32-s3-parallel|esp32.*(display|lcd|tft)', prefix=''),
    'seeed': dict(vendor='Seeed Studio', category='Seeed Studio', image_note='official Seeed Studio photo',
                  listings=['https://wiki.seeedstudio.com/reterminal_e10xx_main_page/'], rx=r'(https://wiki\.seeedstudio\.com/[A-Za-z0-9_\-]*reterminal_e10\d\d[A-Za-z0-9_\-]*/?)',
                  flt=r'reterminal_e10', prefix=''),
}
HOSTS = {'www.waveshare.com': 'waveshare', 'docs.m5stack.com': 'm5stack', 'lilygo.cc': 'lilygo', 'www.elecrow.com': 'elecrow',
         'www.makerfabs.com': 'makerfabs', 'wiki.seeedstudio.com': 'seeed', 'www.seeedstudio.com': 'seeed'}

SOC_RX = re.compile(r'ESP32(?:-?(P4|S31|S3|S2|C61|C6|C5|C3|H2)[A-Z0-9]*)?(?![a-z])', re.I)
DISP_RX = re.compile(r'\b(LCD|TFT|IPS|AMOLED|OLED|e-?paper|e-?ink|display|screen|touch ?screen)\b', re.I)
SIZE_RX = re.compile(r'(\d{1,2}(?:\.\d{1,2})?)\s*(?:-?\s*inch|in\b|"|”|″|\'\')', re.I)
RES_RX = re.compile(r'(\d{2,4})\s*[x×*]\s*(\d{2,4})')

# spec-table label -> param key (first match wins; values are copied verbatim)
LABELS = [
    (r'^(screen|display|lcd|panel)\s*size$|^size$', 'size'),
    (r'resolution', 'resolution'),
    (r'^(display|screen|lcd)\s*(type|panel)$|panel\s*type|^panel$', 'panel'),
    (r'(display|lcd|screen)\s*(driver|controller)(\s*(ic|chip))?$|^driver\s*(ic|chip)?$|^lcd\s*driver', 'driver_ic'),
    (r'^touch\s*(panel\s*)?(driver|ic|chip|controller)', 'touch_ic'),
    (r'^touch(\s*(type|panel|screen))?$', 'touch'),
    (r'(display|lcd|screen|comm(unication)?)\s*interface|^lcd\s*interface', 'interface'),
    (r'^(soc|mcu|chip|chipset|processor|main\s*(chip|controller|processor)|controller|cpu|core|module)$', 'mcu'),
    (r'co-?processor|wireless\s*(chip|module)\b', 'coprocessor'),
    (r'^(flash|flash\s*memory|storage\s*flash)$', 'flash'),
    (r'^psram|^ram$|^memory$', 'psram'),
    (r'wi-?fi|^wireless|^wlan', 'wifi'),
    (r'bluetooth|^ble$', 'bt'),
    (r'^usb(?!\s*-?\s*(ttl|uart|to|supply|power))|usb\s*(port|interface)s?$', 'usb'),
    (r'^(lithium\s*|li-?po\s*|li-?ion\s*)?battery(\s*(capacity|interface|connector))?$', 'battery'),
    (r'speaker|amplifier', 'speaker'),
    (r'micro?phone|^mic', 'mic'),
    (r'camera', 'camera'),
    (r'^rtc', 'rtc'),
    (r'imu|gyro|acceler', 'imu'),
    (r'(micro\s*)?sd|tf\s*card', 'sd'),
    (r'ethernet', 'ethernet'),
    (r'rs-?485', 'rs485'),
    (r'^(product\s*)?(dimensions?|size\s*\(mm\)|product\s*size)$', 'dimensions'),
    (r'(net\s*)?weight', 'weight'),
    (r'operating\s*voltage|power\s*(supply|input)|input\s*voltage', 'power'),
]
SKIP_ROW = re.compile(r'^(G\d+|GPIO\d*|PIN|FUNC|PORT|IO\d*|Driver Name|Version|Date|Packag|Gross Weight|Specification|Parameter|Item|No\.?|Category|Categories|Price|Qty|Quantity|Rating|Reviews?|Availability|Shipping|Check|Orders?|Business|Contact|E-?mail|Support|Follow|Wiki|Quick Overview|Retail|Distributor|History)\b', re.I)


def norm(s):
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())


def nurl(u):
    return re.sub(r'[?#].*$', '', u or '').rstrip('/').lower()


def existing(include_auto=True):
    """ids, names (normalised), SKUs and source URLs of every board already in the catalog."""
    names, urls, ids = set(), set(), set()
    mj = os.path.join(ROOT, 'site/data/models.json')
    if os.path.exists(mj):
        for m in json.load(open(mj)):
            if not include_auto and m.get('auto_added'):
                continue
            ids.add(m['id']); names.add(norm(m['model']))
            for a in m.get('aliases') or []: names.add(norm(a))
            sku = (m.get('params') or {}).get('sku')
            if sku: names.update(norm(x) for x in re.split(r'[/,]', sku))
            for u in m.get('sources') or []: urls.add(nurl(u))
    for f in glob.glob(os.path.join(CDIR, '*.json')) + (glob.glob(os.path.join(ADIR, '*.json')) if include_auto else []):
        for b in json.load(open(f))['boards']:
            ids.add(b['id']); names.add(norm(b['model']))
            if b['params'].get('sku'): names.update(norm(x) for x in re.split(r'[/,]', b['params']['sku']))
            for u in b.get('sources', []) + [l.get('url', '') for l in b.get('links', [])]: urls.add(nurl(u))
    names.discard('')
    return ids, names, urls


def discover(vendors=None, log=print, include_auto=True):
    """Candidate product URLs per vendor (display-like by name, not yet in the catalog)."""
    _, names, urls = existing(include_auto)
    out = {}
    for key, v in VENDORS.items():
        if vendors and key not in vendors:
            continue
        hits = set()
        for lu in v['listings']:
            try:
                r = S.get(lu, timeout=60); r.raise_for_status()
                hits |= set(re.findall(v['rx'], r.text))
            except Exception as e:
                log(f'  {v["vendor"]}: listing failed {lu}: {e}')
        cand = []
        for h in sorted(hits):
            slug = h.rstrip('/').rsplit('/', 1)[-1].replace('.htm', '').replace('.html', '')
            if not re.search(v['flt'], slug, re.I):
                continue
            full = h if h.startswith('http') else v['prefix'] + h
            if nurl(full) in urls or norm(slug) in names:
                continue
            cand.append(full)
        out[key] = cand
        log(f'  {v["vendor"]}: {len(hits)} listed, {len(cand)} display-like candidates not in the catalog')
    return out


def _text(el):
    return re.sub(r'\s+', ' ', el.get_text(' ')).strip()


def _rows(soup):
    rows, seen = [], set()
    def add(a, b):
        a, b = a.strip(' :：\u00a0'), b.strip(' \u00a0')
        if not a or not b or len(a) > 50 or len(b) > 300 or SKIP_ROW.match(a) or a.lower() in seen or re.match(r'^[\d.\-]', a):
            return
        if re.match(r'^(G\d+|GPIO\d+|-?\d+)$', b):
            return
        seen.add(a.lower()); rows.append([a, b])
    pin = re.compile(r'_|^(G|GPIO|IO|LPG|PY|PYG)\d+$|^(D[+\-−]|VBUS|GND|3V3|5V|SDA|SCL|RST|INT|TX|RX|EN|BOOT)$')
    for tab in soup.find_all('table'):
        pairs = []
        for tr in tab.find_all('tr'):
            c = [_text(td) for td in tr.find_all(['td', 'th'])]
            if len(c) == 2:
                pairs.append(c)
            elif len(c) == 4 and all(c):
                pairs += [c[:2], c[2:]]
        if not pairs:
            continue
        pinlike = sum(1 for a, b in pairs if pin.search(b) or pin.search(a))
        if pinlike / len(pairs) > 0.3:           # pin-map / GPIO tables are not specs
            continue
        for a, b in pairs:
            add(a, b)
    for dl in soup.find_all('dl'):
        for dt, dd in zip(dl.find_all('dt'), dl.find_all('dd')):
            add(_text(dt), _text(dd))
    for li in soup.find_all(['li', 'p']):
        t = _text(li)
        m = re.match(r'^([A-Za-z][A-Za-z0-9 /&\-().]{2,40})\s*(?::\s+|：\s*)(.{1,250})$', t)
        if m and not li.find(['li', 'table']):
            add(m.group(1), m.group(2))
    return rows


HEAD_END = re.compile(r'^(Specifications?|Hardware Description|Onboard Resources|Interfaces?|Pinout|Pin ?definition|Dimensions?|outline dimensions|'
                      r'Resources & Services|Application scenarios|Package Content|Shipping List|Documents|Resources?|Download|FAQ|Reviews?)$', re.I)


ONBOARD = set()


def _bullets(soup, have):
    """Verbatim 'Features' sentences and 'What's On Board' (component | description) pairs."""
    L = [re.sub(r'\s+', ' ', l).strip() for l in soup.get_text('\n').split('\n')]
    L = [l for l in L if l]
    out = []
    i = next((k for k, l in enumerate(L) if re.match(r'^(Features?|Key Features|Product Features)$', l, re.I)), None)
    if i is not None:
        for l in L[i + 1:i + 40]:
            if HEAD_END.match(l) or re.match(r"^What'?s On Board$", l, re.I):
                break
            if 25 < len(l) < 400:
                out.append(['Feature', l])
    j = next((k for k, l in enumerate(L) if re.match(r"^What'?s On Board$", l, re.I)), None)
    if j is not None:
        seg = []
        for l in L[j + 1:j + 80]:
            if HEAD_END.match(l) or re.match(r'^(Wiki|Weight)\s*:?$', l, re.I):
                break
            seg.append(l)
        # items are not reliably 'name | description' pairs → keep every line verbatim as its own row
        for k, l in enumerate(seg):
            if len(l) < 200:
                out.append(['On board', l])
                prev = seg[k - 1] if k else ''
                if re.match(r'^[A-Z0-9][A-Z0-9\-]{3,}$', prev):          # chip name followed by its role
                    out[-1] = ['On board', f'{prev} – {l}']
    return out[:45]


TEXT_PARAMS = [   # (key, regex over a row value) – the matched page text is stored verbatim
    ('wifi', r'(?:2\.4\s*GHz\s*(?:and 5\s*GHz\s*)?)?Wi-?Fi\s*\d?\s*(?:\(802\.11[^)]*\))?'),
    ('bt', r'Bluetooth\s*(?:BLE\s*)?\d(?:\.\d)?\s*(?:\(LE\)|LE)?|BLE\s*\d(?:\.\d)?'),
]


_SHOP = {}


def _m5shop():
    """SKU -> (handle, first image) from the official M5Stack Shopify catalogue."""
    if not _SHOP:
        for pg in range(1, 10):
            try:
                ps = S.get(f'https://shop.m5stack.com/products.json?limit=250&page={pg}', timeout=60).json().get('products', [])
            except Exception:
                break
            for p in ps:
                for v in p.get('variants', []):
                    if v.get('sku'):
                        _SHOP[v['sku'].upper()] = (p['handle'], p['images'][0]['src'] if p.get('images') else None)
            if len(ps) < 250:
                break
        _SHOP.setdefault('', None)
    return _SHOP


KIT_RX = re.compile(r'\b(kit|keyboard|case|shell|accessor(y|ies)|meshtastic|bundle|breakout|chatbot|shield|expansion|demo)\b', re.I)


def _model(key, url, soup, title):
    slug = urlsplit(url).path.rstrip('/').rsplit('/', 1)[-1].replace('.htm', '').replace('.html', '')
    if key == 'waveshare':
        txt = soup.get_text(' ')
        for m in re.finditer(r'ESP32-[A-Za-z0-9]+(?:-[A-Za-z0-9.]+)+', txt):
            if norm(m.group(0)) == norm(slug):
                return m.group(0)
        return slug.upper().replace('-TOUCH-', '-Touch-').replace('-LCD-', '-LCD-')
    if key == 'm5stack':
        h1 = soup.find('h1')
        return (_text(h1) if h1 else slug.replace('_', ' ')).strip()
    t = re.sub(r'\s*[|–-]\s*(LILYGO|Elecrow|Makerfabs|Seeed Studio|Waveshare|M5Stack).*$', '', title, flags=re.I).strip()
    if key == 'lilygo':
        t = re.sub(r'^LILYGO®?\s*', '', t, flags=re.I)
    return t[:80] or slug


def _img(key, url, soup):
    cands = []
    og = soup.find('meta', property='og:image') or soup.find('meta', attrs={'name': 'og:image'})
    if key == 'waveshare':      # product gallery: '<slug>-1.jpg' is the main photo; request the 800x800 rendition
        slug = urlsplit(url).path.rsplit('/', 1)[-1].replace('.htm', '')
        for m in re.findall(r'https://www\.waveshare\.com/media/catalog/product/cache/1/image/\d+x\d+/[0-9a-f]+/./././?[^"\' ]+?\.(?:jpg|png)', str(soup)):
            if re.search('/' + re.escape(slug) + r'-1(_\d+)*\.(jpg|png)$', m):
                cands.insert(0, re.sub(r'/image/\d+x\d+/', '/image/800x800/', m))
            elif re.search('/' + re.escape(slug) + r'-\d+(_\d+)*\.(jpg|png)$', m):   # e.g. '<slug>-2.jpg' (never another product's slug)
                cands.append(re.sub(r'/image/\d+x\d+/', '/image/800x800/', m))
    if og and og.get('content'):
        cands.append(urljoin(url, og['content'].split('?')[0] if key == 'lilygo' else og['content']))
    if key == 'm5stack':
        cands += [urljoin(url, i.get('src')) for i in soup.find_all('img') if i.get('src') and 'static-cdn.m5stack.com/resource/docs/products' in i.get('src') and 'img-' in i.get('src')]
    for u in dict.fromkeys(cands):
        u = u.replace(' ', '%20')
        if u.startswith('//'): u = 'https:' + u
        if key == 'lilygo': u = re.sub(r'^http://', 'https://', u)
        try:
            h = S.head(u, timeout=30, allow_redirects=True)
            if h.status_code >= 400:
                h = S.get(u, timeout=30, stream=True); h.close()
            if h.status_code < 400 and h.headers.get('Content-Type', 'image').startswith('image'):
                return u
        except Exception:
            pass
    return None


def extract(url, key=None):
    """-> (board dict, None) or (None, reason)."""
    key = key or HOSTS.get(urlsplit(url).netloc)
    if not key:
        return None, 'unknown vendor host'
    V = VENDORS[key]
    try:
        r = S.get(url, timeout=60)
    except Exception as e:
        return None, f'fetch failed: {e.__class__.__name__}'
    if r.status_code >= 400:
        return None, f'HTTP {r.status_code}'
    soup = BeautifulSoup(r.text, 'html.parser')
    ogt = soup.find('meta', property='og:title')
    title = (ogt.get('content') if ogt else '') or (soup.title.string if soup.title else '') or ''
    title = re.sub(r'\s+', ' ', title).strip()
    desc_el = soup.find('meta', attrs={'name': 'description'}) or soup.find('meta', property='og:description')
    desc = re.sub(r'\s+', ' ', desc_el.get('content', '')).strip()[:400] if desc_el else ''
    rows = _rows(soup)
    sku_any = None
    ps = soup.select_one('.product-sku')
    if ps:
        m = re.search(r'SKU\s*[:：]\s*([A-Za-z0-9][A-Za-z0-9.\-]{1,20})', _text(ps))
        if m: sku_any = m.group(1)
    for tr in soup.find_all('tr'):                # SKU rows can sit in tables that are otherwise pin maps
        c = [_text(td) for td in tr.find_all(['td', 'th'])]
        if len(c) >= 2 and re.match(r'^SKU$', c[0], re.I) and re.match(r'^[A-Za-z0-9][A-Za-z0-9.\-]{1,20}$', c[1]):
            sku_any = c[1]; break
    for t in soup(['script', 'style', 'nav', 'footer', 'header']):
        t.decompose()
    rows += _bullets(soup, {a.lower() for a, _ in rows})
    model = _model(key, url, soup, title)
    if not title or title.lower() in ('m5-docs', 'm5stack docs'):
        title = f'{V["vendor"]} {model}'
    params = {}
    for lab, val in rows:
        for rx, k in LABELS:
            if re.search(rx, lab, re.I) and k not in params:
                params[k] = f'{lab} – {val}' if lab in ONBOARD else val; break
    for lab, val in rows:                        # 'IPS LCD Screen | 2.0"@320 x 240 ILI9342C' style rows
        if re.search(r'screen|display|lcd|e-?paper|amoled|oled', lab, re.I):
            if not (params.get('size') and SIZE_RX.search(params['size'])) and SIZE_RX.search(val): params['size'] = val
            if not params.get('resolution') and RES_RX.search(val): params['resolution'] = val
            if not params.get('display'): params['display'] = val
        if re.match(r'^sku$', lab, re.I) and not params.get('sku'): params['sku'] = re.match(r'[A-Za-z0-9.\-]+', val).group(0)
        for k, rx in (('flash', r'(\d+)\s*MB?\s*(?:Nor\s*|SPI\s*)?flash'), ('psram', r'(\d+)\s*MB?\s*(?:Octal\s*|OPI\s*)?PSRAM')):
            m = re.search(rx, val, re.I)
            if m and not params.get(k): params[k] = m.group(1) + 'MB'
    for lab, val in rows:
        for k, rx in TEXT_PARAMS:
            m = re.search(rx, val, re.I)
            if m and not params.get(k): params[k] = m.group(0).strip()
        if not params.get('panel') and re.search(r'inch|screen|display|lcd', val, re.I):
            m = re.search(r'\b(IPS|AMOLED|OLED|TFT|E-?Paper|E-?Ink)\b', val)
            if m: params['panel'] = m.group(1)
        if not params.get('touch_points'):
            m = re.search(r'(\d+)-point touch', val, re.I)
            if m: params['touch_points'] = m.group(1)
        if lab == 'On board':                    # one verbatim line per on-board item
            for k, rx in (('rtc', r'\bRTC\b'), ('imu', r'\bIMU\b|gyroscope'), ('pmu', r'power management'), ('sd', r'\bTF\b|micro\s*SD'),
                          ('rs485', r'RS-?485'), ('can', r'\bCAN\b'), ('speaker', r'speaker'), ('mic', r'microphone'), ('camera', r'camera'),
                          ('battery', r'lithium|battery header|li-?po'), ('ethernet', r'ethernet|RJ45'), ('buzzer', r'buzzer'), ('ir', r'\bIR\b|infrared')):
                if re.search(rx, val, re.I) and not params.get(k): params[k] = val
            m = re.match(r'(ESP32-[A-Z0-9]+-[A-Z0-9\-]+)', val)
            if m and not params.get('module'): params['module'] = m.group(1)
    hay = ' '.join([title, model, ' '.join(v for _, v in rows)])
    if KIT_RX.search(model):
        return None, 'kit / bundle / accessory variant of a board (not a separate display board)'
    socs = [m.group(0).upper() for m in SOC_RX.finditer(hay)]
    if not socs:
        return None, 'no ESP32 SoC named on the page'
    g = SOC_RX.match(socs[0]).group(1)
    fam = 'ESP32' + ('-' + g.upper() if g else '')
    if not params.get('mcu'):
        params['mcu'] = params.pop('module', None) or fam
    params.pop('module', None)
    params['mcu_family'] = fam
    # size / resolution only from a stated value (spec row first, then the product title)
    if not params.get('size') or not SIZE_RX.search(params['size']):
        m = SIZE_RX.search(title + ' ' + model)
        if m: params['size'] = m.group(1) + '"'
        else: params.pop('size', None)
    else:
        params['size'] = SIZE_RX.search(params['size']).group(1) + '"'
    if params.get('resolution') and RES_RX.search(params['resolution']):
        m = RES_RX.search(params['resolution']); params['resolution'] = f'{m.group(1)}x{m.group(2)}'
    else:
        params.pop('resolution', None)
        m = RES_RX.search(title)
        if m: params['resolution'] = f'{m.group(1)}x{m.group(2)}'
    if not DISP_RX.search(title + ' ' + model + ' ' + ' '.join(a + ' ' + b for a, b in rows)) or not (params.get('size') or params.get('resolution')):
        return None, 'no built-in display with a stated size / resolution'
    if sku_any and not params.get('sku'):
        params['sku'] = sku_any
    w = params.get('wifi', '')
    if re.search(r'not included|optional|expansion|add-?on', w, re.I):     # Wi-Fi only via an add-on module
        params['connectivity'] = params.pop('wifi')
    t = params.get('touch', '')
    if t and not re.search(r'capacit|resist', t, re.I):
        params['touch_detail'] = t              # e.g. 'Supported', 'CST3530 touch controller …' – type taken from the page text below
        t = ''
    if t:
        params['touch'] = 'Capacitive' if re.search(r'capacit', t, re.I) else 'Resistive'
    elif re.search(r'capacitive\s*(\d+-point\s*)?touch', hay, re.I):
        params['touch'] = 'Capacitive'
    elif re.search(r'resistive\s*touch', hay, re.I):
        params['touch'] = 'Resistive'
    else:
        params.pop('touch', None)
    img = _img(key, url, soup)
    extra_src = []
    if img and key == 'm5stack':                 # docs photo filed under another product's folder → prefer the shop photo of this SKU
        folder = re.search(r'/products/core/([^/]+)/', img)
        if folder and norm(folder.group(1).replace('%20', '')) != norm(model) and params.get('sku') and (_m5shop().get(params['sku'].upper()) or (0, 0))[1]:
            img = None
    if not img and key == 'm5stack' and params.get('sku'):     # docs pages load the hero photo via JS → official shop, same SKU
        hit = _m5shop().get(params['sku'].upper())
        if hit and hit[1]:
            img = hit[1].split('?')[0]; extra_src.append('https://shop.m5stack.com/products/' + hit[0])
    files, links = [], []
    for a in soup.find_all('a', href=True):
        u = urljoin(url, a['href'])
        if re.search(r'\.pdf(\?|$)', u, re.I) and re.search(r'sch', u.rsplit('/', 1)[-1], re.I):
            files.append({'name': re.sub(r'%20', ' ', u.rsplit('/', 1)[-1].split('?')[0]), 'url': u, 'host': True})
        elif re.search(r'github\.com/(m5stack|Seeed-Studio|Xinyuan-LilyGO|Makerfabs|Elecrow-RD|waveshareteam)/[^/#?]+/?$', u, re.I):
            links.append({'title': 'GitHub: ' + u.split('github.com/')[1].strip('/'), 'url': u, 'type': 'official-github'})
    files = list({f['url']: f for f in files}.values())[:6]
    links = list({l['url']: l for l in links}.values())[:6]
    today = datetime.date.today().isoformat()
    bid = key + '-' + re.sub(r'[^a-z0-9]+', '-', model.lower()).strip('-')
    return {'id': bid, 'model': model, 'title': (title or model)[:160], 'series': '', 'sources': [url] + extra_src, 'description': desc,
            'params': params, 'spec_rows': rows[:40], 'images': [img] if img else [], 'files': files, 'links': links,
            'notes': [f'Auto-added by the monthly scraper on {today} from the official product page; values are copied verbatim '
                      'from that page, fields it does not state are empty. Not yet hand-reviewed.'],
            'auto': {'added': today, 'vendor_key': key}}, None


def write(boards_by_vendor):
    os.makedirs(ADIR, exist_ok=True)
    for key, boards in boards_by_vendor.items():
        if not boards:
            continue
        V = VENDORS[key]
        p = os.path.join(ADIR, key + '.json')
        cur = json.load(open(p)) if os.path.exists(p) else {
            'vendor': V['vendor'], 'slug': key, 'category': V['category'], 'image_note': V['image_note'],
            '_note': 'AUTO-DISCOVERED by build/autoadd.py from official product pages (verbatim values, empty = not stated). '
                     'Move an entry to data/curated/boards/ after review; curated entries always win.', 'boards': []}
        have = {b['id'] for b in cur['boards']}
        cur['boards'] += [b for b in boards if b['id'] not in have]
        json.dump(cur, open(p, 'w'), indent=1, ensure_ascii=False)


def run(dry_run=False, vendors=None, urls=None, log=print, include_auto=True):
    """-> (added [(vendor, model, url)], skipped [(vendor, url, reason)])"""
    ids, names, _ = existing(include_auto)
    if urls:
        cand = {}
        for u in urls:
            cand.setdefault(HOSTS.get(urlsplit(u).netloc, '?'), []).append(u)
    else:
        cand = discover(vendors, log, include_auto)
    added, skipped, out = [], [], {}
    for key, us in cand.items():
        for u in us:
            if key not in VENDORS:
                skipped.append((key, u, 'unknown vendor host')); continue
            b, why = extract(u, key)
            if not b:
                skipped.append((VENDORS[key]['vendor'], u, why)); log(f'  skip {u}: {why}'); continue
            if b['id'] in ids or norm(b['model']) in names:
                skipped.append((VENDORS[key]['vendor'], u, f'duplicate of existing model {b["model"]}')); continue
            if not b['images']:
                b['notes'].append('No product photo could be verified on the page.')
            ids.add(b['id']); names.add(norm(b['model']))
            out.setdefault(key, []).append(b)
            added.append((VENDORS[key]['vendor'], b['model'], u))
            log(f'  {"would add" if dry_run else "add"} [{VENDORS[key]["vendor"]}] {b["model"]} – {u}')
    if not dry_run:
        write(out)
    return added, skipped, out


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--vendor', action='append')
    ap.add_argument('--url', action='append')
    ap.add_argument('--print', action='store_true', help='print extracted records (implies --dry-run)')
    ap.add_argument('--pretend-new', action='store_true', help='test: treat already auto-added boards as unknown (use with --dry-run)')
    a = ap.parse_args()
    added, skipped, out = run(a.dry_run or a.print or a.pretend_new, a.vendor, a.url, include_auto=not (a.print or a.pretend_new))
    if a.print:
        print(json.dumps(out, indent=1, ensure_ascii=False))
    print(f'added {len(added)}, skipped {len(skipped)}')
    for s in skipped:
        print('  skipped', *s)
