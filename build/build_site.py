#!/usr/bin/env python3
"""Merge scraped + curated data into site/data/models.json (+ facets, files list, docs list).
Inputs: data/raw/{guition_table,guition_products,archives,docs_text}.json, data/curated/*.json
Outputs: site/data/models.json, site/data/archives.json, site/data/docs.json, site/data/meta.json
"""
import json, os, re, hashlib, datetime, collections
from urllib.parse import urlsplit, unquote
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, 'site')
RAW = os.path.join(ROOT, 'data', 'raw')
CUR = os.path.join(ROOT, 'data', 'curated')
CFG = json.load(open(os.path.join(ROOT, 'build', 'config.json')))
load = lambda p: json.load(open(p, encoding='utf-8'))

CAT_LABEL = {'esp32-display-module': 'ESP32 Display Module', 'esp32p4-display-module': 'ESP32-P4 Display Module',
             'esp32s31-display-module-': 'ESP32-S31 Display Module', 'hmi-display-module': 'HMI Display Module',
             'parallel-lcd-display': 'Parallel LCD Display', 'spi-display-module': 'SPI Display Module',
             'spi-lcd-display': 'SPI LCD Display'}

# ---------------------------------------------------------------- helpers

def clean(s):
    return re.sub(r'\s+', ' ', (s or '').replace('\u00a0', ' ')).strip()


def fix_model(m):
    m = clean(m)
    if m.count(')') > m.count('('):
        m = m.rstrip(')')
    return m


def base_key(name):
    n = name.upper()
    m = re.search(r'(JC-ESP32P4-M3-(?:C6|DEV)|ESP32-\d{4}S\d{3}|JC\d{4}[A-Z]\d{3})', n)
    return m.group(1) if m else None


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


def num(s):
    m = re.search(r'(\d+(?:\.\d+)?)', s or '')
    return float(m.group(1)) if m else None


def parse_res(s):
    m = re.search(r'(\d{2,4})\s*[*×xX]\s*(\d{2,4})', s or '')
    return (int(m.group(1)), int(m.group(2))) if m else None


SPEC_MAP = {
    'size': ['Display Size', 'Screen Size', 'Size', 'LCD Size'],
    'resolution': ['Resolution', 'Display Resolution', 'Maximum Resolution'],
    'panel': ['Display Type', 'LCD Type', 'Screen Type', 'Type', 'View Technology', 'View Type'],
    'mcu': ['MCU', 'Main Controller', 'Microcontroller', 'Processor', 'Core', 'CPU Type', 'Main Control'],
    'frequency': ['CPU Frequency', 'Main Frequency', 'Processor Speed', 'Clock Frequency', 'Processor Frequency', 'Clock Speed', 'Operating Frequency'],
    'driver_ic': ['Driver Chip', 'Driver IC', 'Display Driver', 'Drive Chip', 'Display Driver IC'],
    'touch': ['Touch Type', 'Touch Function', 'Touch Options', 'Touch Option', 'Touch Panel'],
    'touch_ic': ['Touch Controller'],
    'sram': ['SRAM', 'RAM'],
    'psram': ['PSRAM'],
    'rom': ['ROM'],
    'flash': ['Flash Memory', 'Flash Storage', 'Flash', 'Flash Size'],
    'memory': ['Memory', 'Memory Configuration'],
    'interface': ['Interface', 'Interface Type', 'Communication Interface', 'Display Interfaces', 'Communication Method', 'Communication', 'Communication Protocol'],
    'connectivity': ['Connectivity', 'Wireless', 'Wireless Connectivity', 'WiFi', 'WIFI', 'WIFI Support', 'Bluetooth', 'Bluetooth Support'],
    'dimensions': ['Module Dimensions', 'PCB Dimensions', 'Module Size', 'External Dimensions', 'LCM Dimension', 'LCM Dimensions', 'Module PCB Size', 'Dimensions', 'PCB Size', 'Module Dimension', 'Display Dimensions'],
    'active_area': ['Effective Display Area', 'Active Area', 'Visual Area', 'Display Area', 'LCD Active Area', 'Viewing Area', 'Active Display Area'],
    'voltage': ['Operating Voltage', 'Working Voltage', 'Power Supply'],
    'power': ['Power Consumption'],
    'operating_temp': ['Operating Temperature', 'Operating Temp'],
    'storage_temp': ['Storage Temperature', 'Storage Temp'],
    'viewing_angle': ['Viewing Angle', 'View Angle', 'Viewing Direction'],
    'color_depth': ['Color Depth', 'Color Support', 'Display Colors', 'Display Color', 'Color Display'],
    'backlight': ['Backlight', 'Backlight Type'],
    'brightness': ['Brightness'],
    'expansion': ['Expansion', 'Interfaces', 'Expandable IO', 'Available GPIO', 'Additional Features', 'I/O Ports', 'Key Interfaces', 'Additional Interfaces', 'Other Interfaces'],
    'software': ['Development Support', 'Development Platforms', 'Operating System', 'Development Modes'],
    'audio': ['Audio', 'Audio Support'],
    'sd': ['SD Card Support', 'TF Card Support', 'Storage Expansion', 'SD Card Slot', 'Storage Support'],
    'rtc': ['RTC', 'RTC Support'],
    'camera': ['Camera Interface'],
    'coprocessor': ['Co-Processor'],
}
LABEL_TO_KEY = {}
for k, labels in SPEC_MAP.items():
    for l in labels:
        LABEL_TO_KEY[l.lower()] = k

FIELD_LABELS = {
    'vendor': 'Vendor', 'category': 'Category', 'series': 'Series', 'size': 'Size', 'size_in': 'Size (in)', 'resolution': 'Resolution',
    'shape': 'Shape', 'panel': 'Panel', 'touch': 'Touch', 'touch_ic': 'Touch IC', 'touch_points': 'Touch points', 'driver_ic': 'Display driver',
    'interface': 'Display interface', 'interface_detail': 'Interface detail', 'mcu': 'MCU', 'mcu_family': 'MCU family', 'coprocessor': 'Co-processor',
    'frequency': 'CPU frequency', 'sram': 'SRAM', 'psram': 'PSRAM', 'rom': 'ROM', 'flash': 'Flash', 'memory': 'Memory', 'wifi': 'Wi-Fi', 'bt': 'Bluetooth',
    'connectivity': 'Connectivity', 'speaker': 'Speaker interface', 'audio': 'Audio', 'camera': 'Camera', 'ethernet': 'Ethernet', 'poe': 'PoE',
    'rs485': 'RS-485', 'usb': 'USB', 'sd': 'SD / TF', 'rtc': 'RTC', 'battery': 'Battery', 'gpio': 'GPIO', 'expansion': 'Expansion / IO',
    'shell': 'Case / shell', 'glass': 'Glass', 'dimensions': 'Dimensions', 'active_area': 'Active area', 'pixel_pitch': 'Pixel pitch',
    'voltage': 'Operating voltage', 'power': 'Power consumption', 'operating_temp': 'Operating temp.', 'storage_temp': 'Storage temp.',
    'viewing_angle': 'Viewing angle', 'contrast': 'Contrast', 'brightness': 'Brightness', 'color_depth': 'Colors', 'color_gamut': 'Color gamut',
    'backlight': 'Backlight', 'software': 'Software / dev support', 'form_factor': 'Form factor', 'display_module': 'Display module', 'sku': 'SKU',
}


def norm_touch(s):
    t = (s or '').lower()
    if not t:
        return ''
    if t in ('ctp',) or 'capacit' in t:
        return 'Capacitive'
    if t in ('rtp',) or 'resist' in t:
        return 'Resistive'
    if t in ('ntp',) or 'without' in t or t.startswith('no') or 'none' in t:
        return 'None'
    return clean(s)


def norm_panel(s):
    t = (s or '').upper()
    if not t:
        return ''
    if 'AMOLED' in t: return 'AMOLED'
    if 'IPS' in t: return 'IPS'
    if re.search(r'\bTN\b', t): return 'TN'
    return ''


def norm_interface(s):
    t = (s or '').upper().replace('_', '-')
    if not t:
        return ''
    if 'MIPI' in t: return 'MIPI-DSI'
    if 'QSPI' in t: return 'QSPI'
    if 'RGB' in t: return 'RGB'
    if '8080' in t or 'PARALLEL' in t or 'MCU' in t: return '8080 parallel'
    if 'SPI' in t: return 'SPI'
    if 'UART' in t or 'SERIAL' in t: return 'UART'
    if 'I2C' in t: return 'I2C'
    return ''


def norm_mcu(s):
    s = clean(s)
    s = re.sub(r'\s*-\s*', '-', s)
    s = re.sub(r'\s+', ' ', s)
    return s


def mcu_family(s):
    t = (s or '').upper().replace(' ', '')
    if not t: return ''
    if 'P4' in t: return 'ESP32-P4'
    if 'S31' in t: return 'ESP32-S31'
    if 'S3' in t: return 'ESP32-S3'
    if 'C3' in t: return 'ESP32-C3'
    if 'C6' in t: return 'ESP32-C6'
    if 'D0WD' in t or t.startswith('ESP32-WROOM') or t == 'ESP32': return 'ESP32'
    if 'D12' in t or 'ARTINCHIP' in t: return 'ArtInChip D12x'
    if 'ESP32' in t: return 'ESP32'
    return clean(s)


def yes_no(s):
    t = (s or '').strip().lower()
    if t in ('c6', 'esp32-c6'): return 'Yes (via ESP32-C6)'
    if t in ('yes', 'y'): return 'Yes'
    if t in ('no', 'n', '-'): return 'No'
    return clean(s)


def size_label(v):
    if v is None: return ''
    return ('%g' % v) + '"'

# ---------------------------------------------------------------- assets

S = requests.Session()
S.headers['User-Agent'] = 'Mozilla/5.0 (guition-catalog-builder)'


def fetch_asset(url, subdir, keep_name=False):
    name = unquote(urlsplit(url).path.rsplit('/', 1)[-1])
    ext = os.path.splitext(name)[1].lower() or '.bin'
    h = hashlib.sha1(url.encode()).hexdigest()[:12]
    fn = (re.sub(r'[^A-Za-z0-9._-]+', '_', os.path.splitext(name)[0])[:80] + '_' + h[:6] + ext) if keep_name else h + ext
    rel = f'{subdir}/{fn}'
    dst = os.path.join(SITE, rel)
    if not os.path.exists(dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        r = S.get(url, timeout=120)
        r.raise_for_status()
        open(dst, 'wb').write(r.content)
    return rel


def dedupe_files(paths):
    """Content-dedupe hosted files; returns map rel -> canonical rel (duplicates deleted).
    The map is persisted (data/raw/pdf_dedupe.json) so re-runs still resolve already-deleted duplicates."""
    store = os.path.join(ROOT, 'data', 'raw', 'pdf_dedupe.json')
    old = json.load(open(store)) if os.path.exists(store) else {}
    seen, mp = {}, {}
    for rel in sorted(set(paths)):
        fp = os.path.join(SITE, rel)
        if not os.path.exists(fp):
            if rel in old and os.path.exists(os.path.join(SITE, old[rel])):
                mp[rel] = old[rel]
            continue
        h = hashlib.sha1(open(fp, 'rb').read()).hexdigest()
        if h in seen:
            mp[rel] = seen[h]
            os.remove(fp)
        else:
            seen[h] = rel
            mp[rel] = rel
    old.update(mp)
    json.dump(old, open(store, 'w'), indent=0)
    return mp

# ---------------------------------------------------------------- build


def main():
    table = load(os.path.join(RAW, 'guition_table.json'))
    prods = [p for p in load(os.path.join(RAW, 'guition_products.json')) if not re.search(r'/page-\d+$', p['url'])]
    archives = load(os.path.join(RAW, 'archives.json'))
    docs_text = load(os.path.join(RAW, 'docs_text.json'))
    community = load(os.path.join(CUR, 'community.json'))
    notes = load(os.path.join(CUR, 'notes.json'))['notes']
    pinouts = load(os.path.join(CUR, 'pinouts.json'))['pinouts']
    ws = load(os.path.join(CUR, 'waveshare.json'))
    now = datetime.datetime.now().astimezone().isoformat(timespec='seconds')

    # product pages by model
    for p in prods:
        m = p.get('model')
        if not m:
            mm = [v for k, v in p['specs'] if k.strip().lower() in ('model', 'model number')]
            m = mm[0] if mm else None
        p['model_n'] = fix_model(m) if m else None
    url2model = {p['url']: p['model_n'] for p in prods if p['model_n']}

    models = collections.OrderedDict()

    def get(mid):
        if mid not in models:
            models[mid] = {'model': mid, 'vendor': 'Guition', 'p': {}, 'raw': [], 'sources': [], 'images': [], 'files': [],
                           'links': [], 'notes': [], 'conflicts': [], 'product_pages': [], 'categories': set(), 'aliases': set(),
                           'titles': [], 'intros': []}
        return models[mid]

    # 1) model list table (EN)
    t_url = table['en']['url']
    for r in table['en']['records']:
        mid = r['model']
        # the table sometimes names a product whose page states a more specific model number
        if r.get('product_url') and url2model.get(r['product_url']) and url2model[r['product_url']] != mid \
                and base_key(url2model[r['product_url']]) == base_key(mid):
            alias = mid
            mid = url2model[r['product_url']]
            get(mid)['aliases'].add(alias)
        e = get(mid)
        e['table'] = r
        e['sources'].append(t_url)
        vals = {
            'size': r['size'], 'resolution': r['resolution'], 'panel': r['panel'], 'touch': r['touch'], 'shell': r['shell'],
            'mcu': r['controller'], 'frequency': r['frequency'], 'wifi': r['wifi'], 'bt': r['bt'], 'sram': r['sram'],
            'psram': r['psram'], 'rom': r['rom'], 'flash': r['flash'], 'interface': r['interface'], 'speaker': r['speaker'],
            'software': r['software'],
        }
        for k, v in vals.items():
            if clean(v):
                e['raw'].append({'label': table['en']['header'][0] if False else FIELD_LABELS.get(k, k), 'key': k, 'value': clean(v), 'source': t_url, 'src': 'guition model list'})
        if r.get('thumb_local'):
            e['images'].append({'src': r['thumb_local'], 'orig': r['thumb'], 'kind': 'thumb'})
        for d in r['downloads']:
            e.setdefault('table_downloads', []).append(d)
        if r.get('product_url'):
            e['product_pages'].append(r['product_url'])

    # 2) product pages
    for p in prods:
        if p.get('error') and not p['model_n']:
            continue
        mid = p['model_n']
        if not mid:
            continue
        e = get(mid)
        if p['url'] not in e['product_pages']:
            e['product_pages'].append(p['url'])
        e['sources'].append(p['url'])
        e['categories'].add(p['category'])
        if p['title']: e['titles'].append(p['title'])
        if p['intro']: e['intros'].append(p['intro'])
        for k, v in p['specs']:
            lab = clean(k).rstrip(':')
            if lab.lower() in ('brand', 'model', 'model number', 'parameter'):
                continue
            e['raw'].append({'label': lab, 'key': LABEL_TO_KEY.get(lab.lower()), 'value': clean(v), 'source': p['url'], 'src': 'guition product page'})
        for im in p.get('images_local', []):
            e['images'].append({'src': im['local'], 'orig': im['src'], 'kind': 'product'})
        for f in p.get('files_local', []):
            e['files'].append({'type': 'pdf', 'name': unquote(f['src'].rsplit('/', 1)[-1]), 'url': f['src'], 'hosted': f['local'],
                               'origin': 'guition product page'})

    # 3) archives -> models
    arch_by_name = {a['name']: a for a in archives}
    model_names_norm = {re.sub(r'[^A-Z0-9]', '', m.upper()): m for m in models}

    def arch_norm(name):
        n = os.path.splitext(name)[0]
        n = re.sub(r'^\d+(\.\d+)?inch_', '', n)
        n = re.sub(r'(_knob)?_?(EN|CN)$', '', n, flags=re.I)
        n = re.sub(r'^xiaozhi_', '', n, flags=re.I)
        return re.sub(r'[^A-Z0-9]', '', n.upper())

    assigned = collections.defaultdict(list)
    for mid, e in models.items():
        names = set()
        for d in e.get('table_downloads', []):
            if d['name'] in arch_by_name:
                names.add((d['name'], 'linked on guition.com model list'))
            else:
                e['files'].append({'type': 'archive', 'name': d['name'], 'url': d['url'], 'origin': 'guition.com model list',
                                   'missing': True, 'note': 'not present on the file server listing'})
        bk = base_key(mid)
        for a in archives:
            ab = base_key(a['name'])
            if not ab or not bk or ab != bk or any(a['name'] == n for n, _ in names):
                continue
            an = arch_norm(a['name'])
            mine = re.sub(r'[^A-Z0-9]', '', mid.upper())
            # archive is the exact name of a *different* model -> not ours
            if an in model_names_norm and model_names_norm[an] != mid and not mine.startswith(an):
                continue
            if any(d['name'] == a['name'] for d in [])  :
                continue
            names.add((a['name'], 'matched by model number'))
        for n, how in sorted(names):
            assigned[n].append(mid)
            a = arch_by_name[n]
            e['files'].append({'type': 'archive' if a.get('type') == 'archive' else 'file', 'name': a['name'], 'url': a['url'],
                               'size': a['size'], 'slug': a['slug'], 'manifest': a.get('manifest'), 'hosted': a.get('hosted') or a.get('hosted_archive'),
                               'hosted_archive': a.get('hosted_archive'), 'stats': a.get('stats'), 'origin': how,
                               'lang': 'EN' if re.search(r'EN\.zip$', n) else ('CN' if re.search(r'CN\.zip$', n) else '')})

    # SPI / 8080 module archives: match by size + driver IC stated on product pages
    for a in archives:
        m = re.match(r'(\d+(?:\.\d+)?)inch_(SPI|8080)_Module_(\w+)\.zip$', a['name'])
        if not m or assigned.get(a['name']):
            continue
        size, bus, ic = float(m.group(1)), m.group(2), m.group(3).upper()
        hits = []
        for mid, e in models.items():
            vals = ' '.join(r['value'] for r in e['raw']).upper()
            sz = [num(r['value']) for r in e['raw'] if r['key'] == 'size']
            if ic in vals and sz and abs(sz[0] - size) < 0.05 and not e.get('table'):
                hits.append(mid)
        for mid in hits:
            assigned[a['name']].append(mid)
            models[mid]['files'].append({'type': 'archive', 'name': a['name'], 'url': a['url'], 'size': a['size'], 'slug': a['slug'],
                                         'manifest': a.get('manifest'), 'hosted': a.get('hosted_archive'), 'hosted_archive': a.get('hosted_archive'),
                                         'stats': a.get('stats'), 'origin': f'matched by size ({size}") + driver IC ({ic}) on product page'})

    # Downloads-only display entries (archive on the file server, no model page)
    for a in archives:
        if assigned.get(a['name']) or a['dir'] in ('F100S', 'TOOL', 'PC_monitor'):
            continue
        if a['dir'] == 'Bare screen':
            continue
        nm = os.path.splitext(a['name'])[0]
        mid = nm if re.search(r'_(SPI|8080)_Module_', nm) else re.sub(r'^\d+(\.\d+)?inch_', '', nm)
        mid = re.sub(r'(_knob)?_(EN|CN)$', '', mid)
        e = get(mid)
        e['downloads_only'] = True
        e['sources'].append(a['url'])
        sz = re.match(r'(\d+(?:\.\d+)?)inch_', nm)
        mm = re.match(r'(\d+(?:\.\d+)?)inch_(SPI|8080)_Module_(\w+)', nm)
        if sz:
            e['raw'].append({'label': 'Size', 'key': 'size', 'value': sz.group(1) + '"', 'source': a['url'], 'src': 'archive file name'})
        if mm:
            e['raw'].append({'label': 'Interface', 'key': 'interface', 'value': mm.group(2), 'source': a['url'], 'src': 'archive file name'})
            e['raw'].append({'label': 'Driver IC', 'key': 'driver_ic', 'value': mm.group(3), 'source': a['url'], 'src': 'archive file name'})
        e['notes'].append({'level': 'info', 'text': 'Not listed on guition.com (model list / product pages); this entry exists because the archive is on the official file server. Parameters only from the file name and the archive contents.', 'source': a['url']})
        assigned[a['name']].append(mid)
        e['files'].append({'type': 'archive', 'name': a['name'], 'url': a['url'], 'size': a['size'], 'slug': a['slug'], 'manifest': a.get('manifest'),
                           'hosted': a.get('hosted_archive'), 'hosted_archive': a.get('hosted_archive'), 'stats': a.get('stats'), 'origin': 'official file server'})
    # bare-screen PDFs
    for a in archives:
        if a['dir'] != 'Bare screen':
            continue
        bk = base_key(a['name'])
        for mid, e in list(models.items()):
            if bk and base_key(mid) == bk:
                assigned[a['name']].append(mid)
                e['files'].append({'type': 'pdf', 'name': a['name'], 'url': a['url'], 'size': a['size'], 'hosted': a.get('hosted'),
                                   'slug': a['slug'], 'origin': 'file server "Bare screen" folder (matched by model number)'})
        if not assigned.get(a['name']):
            mid = re.sub(r'\s*Spec$', '', os.path.splitext(a['name'])[0])
            e = get(mid)
            e['downloads_only'] = True
            e['bare'] = True
            e['sources'].append(a['url'])
            e['notes'].append({'level': 'info', 'text': 'Bare LCD panel (no MCU) found only in the "Bare screen" folder of the official file server; see the spec PDF for parameters.', 'source': a['url']})
            e['files'].append({'type': 'pdf', 'name': a['name'], 'url': a['url'], 'size': a['size'], 'hosted': a.get('hosted'), 'slug': a['slug'],
                               'origin': 'file server "Bare screen" folder'})
            assigned[a['name']].append(mid)

    # 4) Waveshare
    def ws_img(url):
        try:
            return fetch_asset(url, 'assets/img/waveshare')
        except Exception as ex:
            print('ws img fail', url, ex)
            return None
    for wm in ws['models']:
        g = ws['common'][wm['group']]
        mid = wm['model']
        e = get(mid)
        e['vendor'] = 'Waveshare'
        e['id'] = wm['id']
        e['series'] = wm['series']
        e['titles'].append(wm['title'])
        e['sources'] += g['sources'] + wm.get('extra_sources', [])
        params = dict(g['params'])
        params.update(wm['params'])
        if wm.get('sku'): params['sku'] = wm['sku']
        for k, v in params.items():
            e['raw'].append({'label': FIELD_LABELS.get(k, k), 'key': k, 'value': v, 'source': g['sources'][0], 'src': 'waveshare'})
        e['ws_params'] = params
        for u in g['images']:
            loc = ws_img(u)
            if loc: e['images'].append({'src': loc, 'orig': u, 'kind': 'product', 'note': g.get('image_note')})
        for f in g['files']:
            ent = {'type': 'pdf' if f['url'].endswith('.pdf') else 'archive', 'name': f['name'], 'url': f['url'], 'origin': 'waveshare'}
            if f.get('host'):
                try:
                    ent['hosted'] = fetch_asset(f['url'], 'files/waveshare', keep_name=True)
                except Exception as ex:
                    ent['note'] = 'download failed: %s' % ex
            e['files'].append(ent)
        e['links'] += [dict(l) for l in g['links']]
        for n in g.get('notes', []) + wm.get('notes', []):
            e['notes'].append({'level': 'info', 'text': n, 'source': g['sources'][0]})
        e['categories'].add('waveshare-esp32-p4')

    # ---------------------------------------------------------- normalize
    out = []
    pdf_paths = [f['hosted'] for e in models.values() for f in e['files'] if f.get('hosted', '') and f['hosted'].startswith('files/guition/')]
    dmap = dedupe_files(pdf_paths)
    for mid, e in models.items():
        P = {}
        conflicts = []
        by_key = collections.defaultdict(list)
        for r in e['raw']:
            if r['key']:
                by_key[r['key']].append(r)
        def pick(key, norm=lambda x: x, prefer_page=True):
            rows = by_key.get(key, [])
            if not rows: return ''
            pages = [r for r in rows if r['src'] != 'guition model list']
            tab = [r for r in rows if r['src'] == 'guition model list']
            ordered = (pages + tab) if prefer_page else (tab + pages)
            vals = [norm(r['value']) for r in ordered if norm(r['value'])]
            return vals[0] if vals else ''
        if e['vendor'] == 'Waveshare':
            wp = e['ws_params']
            P.update({k: v for k, v in wp.items()})
        else:
            P['size'] = pick('size', lambda v: size_label(num(v)) if num(v) else '')
            if not P['size']:
                for t in e['titles']:
                    mt = re.search(r'(\d+(?:\.\d+)?)\s*(?:inch|")', t, re.I)
                    if mt:
                        P['size'] = size_label(float(mt.group(1)))
                        e['raw'].append({'label': 'Size (from product page title)', 'key': None, 'value': t, 'source': e['product_pages'][0] if e['product_pages'] else '', 'src': 'guition product page'})
                        break
            P['resolution'] = pick('resolution', lambda v: '%dx%d' % parse_res(v) if parse_res(v) else '')
            P['panel'] = pick('panel', norm_panel)
            P['touch'] = pick('touch', norm_touch)
            P['mcu'] = pick('mcu', norm_mcu, prefer_page=False)
            for k in ('frequency', 'sram', 'psram', 'rom', 'flash'):
                P[k] = pick(k, clean, prefer_page=False)
            P['interface'] = pick('interface', norm_interface, prefer_page=False)
            P['interface_detail'] = pick('interface', clean)
            P['wifi'] = pick('wifi', yes_no)
            P['bt'] = pick('bt', yes_no)
            conn = ' '.join(r['value'] for r in by_key.get('connectivity', []))
            if not P['wifi'] and re.search(r'wi-?fi', conn, re.I): P['wifi'] = 'Yes'
            if not P['bt'] and re.search(r'bluetooth|ble', conn, re.I): P['bt'] = 'Yes'
            P['speaker'] = pick('speaker', yes_no)
            P['shell'] = pick('shell', yes_no)
            P['software'] = pick('software', clean)
            for k in ('driver_ic', 'touch_ic', 'memory', 'dimensions', 'active_area', 'voltage', 'power', 'operating_temp', 'storage_temp',
                      'viewing_angle', 'color_depth', 'backlight', 'brightness', 'expansion', 'audio', 'sd', 'rtc', 'camera', 'coprocessor', 'connectivity'):
                P[k] = pick(k, clean)
            # conflicts between model list and product page
            for k, normf in (('resolution', lambda v: '%dx%d' % parse_res(v) if parse_res(v) else ''), ('size', lambda v: size_label(num(v)) if num(v) else ''),
                             ('touch', norm_touch), ('panel', norm_panel)):
                vs = {}
                for r in by_key.get(k, []):
                    nv = normf(r['value'])
                    if nv:
                        vs.setdefault(nv, set()).add(r['src'])
                if len(vs) > 1:
                    conflicts.append({'field': FIELD_LABELS.get(k, k), 'values': {v: sorted(s) for v, s in vs.items()}})
            mtxt = ' '.join([P.get('mcu', '')] + [r['value'] for r in by_key.get('mcu', [])])
            if re.search(r'C6', mtxt) and 'P4' in mtxt.upper() and not P.get('coprocessor'):
                P['coprocessor'] = 'ESP32-C6'
            cats = sorted(e['categories'])
            if not cats:
                for om, oe in models.items():
                    if om != mid and base_key(mid) and base_key(om) == base_key(mid) and oe['categories']:
                        cats = sorted(oe['categories']); break
            P['category'] = CAT_LABEL.get(cats[0], cats[0]) if cats else ('Bare screen (file server)' if e.get('bare') else 'File server only' if e.get('downloads_only') else '')
        P['mcu_family'] = P.get('mcu_family') or mcu_family(P.get('mcu', ''))
        if not P.get('mcu') and e['vendor'] == 'Guition' and (P.get('category') in ('SPI Display Module', 'Parallel LCD Display', 'SPI LCD Display') or e.get('bare') or re.search(r'_(SPI|8080)_Module_', mid)):
            P['mcu_family'] = 'none (bare display)'
        P['vendor'] = e['vendor']
        if e['vendor'] == 'Waveshare':
            P['category'] = 'Waveshare ESP32-P4'
        P['size_in'] = num(P.get('size', ''))
        res = parse_res(P.get('resolution', ''))
        P['pixels'] = res[0] * res[1] if res else None
        if res:
            P['resolution'] = '%dx%d' % res
        # shape
        txt_all = ' '.join(e['titles'] + e['intros'] + [e['model']] + [r['value'] for r in e['raw']]).lower()
        if not P.get('shape'):
            P['shape'] = 'Round' if re.search(r'\bround\b|circular', txt_all) else ('Rectangular' if res and res[0] != res[1] else '')
        # tags
        tags = set()
        tags.add('vendor:' + P['vendor'])
        if P.get('mcu_family'): tags.add(P['mcu_family'])
        if P.get('interface'): tags.add(P['interface'])
        if P.get('touch') and P['touch'] != 'None': tags.add(P['touch'] + ' touch')
        if P.get('touch') == 'None': tags.add('no touch')
        if P.get('panel'): tags.add(P['panel'])
        if P.get('shape') == 'Round': tags.add('round')
        if re.search(r'\bknob\b', txt_all) or re.search(r'K518|K718|F118|F318', mid): tags.add('knob')
        if (P.get('wifi') or '').lower().startswith(('yes', 'wi-fi')) or 'wi-fi 6' in txt_all: tags.add('Wi-Fi')
        if 'wi-fi 6' in txt_all or 'wifi 6' in txt_all or 'wifi6' in txt_all or P.get('coprocessor', '').startswith('ESP32-C6'): tags.add('Wi-Fi 6')
        if (P.get('bt') or '').lower().startswith(('yes', 'bluetooth')): tags.add('Bluetooth')
        if P.get('coprocessor'): tags.add('ESP32-C6 co-processor')
        if P.get('camera') or re.search(r'\bcamera\b|mipi-csi|ov5647|ov02c10', txt_all): tags.add('camera')
        if P.get('ethernet') or re.search(r'ethernet|rj45', txt_all): tags.add('Ethernet')
        if P.get('poe') or re.search(r'\bpoe\b', txt_all): tags.add('PoE')
        if re.search(r'rs-?485', txt_all): tags.add('RS-485')
        if (P.get('speaker') or '').startswith('Yes') or re.search(r'speaker', txt_all): tags.add('speaker')
        if re.search(r'micro ?phone|\bmic\b', txt_all): tags.add('microphone')
        if (P.get('shell') or '').startswith('Yes') or re.search(r'metal case|\bshell\b: yes|with (a )?(case|shell|housing)', txt_all): tags.add('case / shell')
        if re.search(r'lithium|battery', txt_all): tags.add('battery')
        if re.search(r'\btf\b|sd card|micro ?sd|tf card', txt_all): tags.add('SD / TF')
        if re.search(r'\brtc\b', txt_all): tags.add('RTC')
        if (P.get('psram') or '') and P['psram'] not in ('-', 'None', 'No'): tags.add('PSRAM')
        if e.get('downloads_only'): tags.add('file-server only')
        if P.get('size_in'):
            s = P['size_in']
            tags.add('size: ≤2"' if s <= 2 else 'size: 2–3.5"' if s <= 3.5 else 'size: 3.6–5"' if s <= 5 else 'size: 5.1–7"' if s <= 7 else 'size: >7"')
        # notes / pinouts / community
        for n in notes:
            if re.search(n['match'], mid):
                e['notes'].append({k: n[k] for k in ('level', 'text', 'sk', 'source') if k in n})
        pins = [p for p in pinouts if re.search(p['match'], mid)]
        links = list(e['links'])
        for u in e['product_pages']:
            links.insert(0, {'title': 'guition.com product page', 'url': u, 'type': 'vendor'})
        if e['vendor'] == 'Guition':
            links.append({'title': 'guition.com model list', 'url': 'https://www.guition.com/model-selection', 'type': 'vendor'})
        for o in community['official_github_series']:
            if re.search(o['match'], mid):
                links.append({'title': o['title'], 'url': o['url'], 'type': 'official-github'})
        for c in community['repos']:
            if re.search(c['match'], mid):
                links.append({'title': c['title'], 'url': c['url'], 'type': 'community', 'desc': c.get('desc', '')})
        seen = set(); links = [l for l in links if not (l['url'] in seen or seen.add(l['url']))]
        # files: dedupe
        files, fseen = [], set()
        for f in e['files']:
            if f.get('hosted') in dmap: f['hosted'] = dmap[f['hosted']]
            key = f.get('hosted') if f['type'] == 'pdf' and f.get('hosted') else f['url']
            if key in fseen: continue
            fseen.add(key); files.append(f)
        imgs, iseen = [], set()
        for im in e['images']:
            if im['src'] in iseen: continue
            iseen.add(im['src']); imgs.append(im)
        imgs.sort(key=lambda x: 0 if x['kind'] == 'product' else 1)
        title = e['titles'][0] if e['titles'] else ''
        mid_id = e.get('id') or slug(mid)
        desc = max(e['intros'], key=len) if e['intros'] else ''
        rec = {
            'id': mid_id, 'model': mid, 'vendor': e['vendor'], 'title': title, 'description': desc,
            'aliases': sorted(e['aliases']), 'series': e.get('series') or (base_key(mid) or ''),
            'params': {k: v for k, v in P.items() if v not in ('', None)},
            'tags': sorted(tags), 'images': imgs, 'files': files, 'links': links, 'notes': e['notes'],
            'conflicts': conflicts, 'pinouts': pins, 'specs_raw': e['raw'], 'sources': sorted(set(e['sources'])),
            'downloads_only': bool(e.get('downloads_only')),
        }
        out.append(rec)
    # siblings (same base key)
    bykey = collections.defaultdict(list)
    for r in out:
        bk = base_key(r['model']) or r.get('series')
        bykey[bk].append(r['id'])
    for r in out:
        bk = base_key(r['model']) or r.get('series')
        r['siblings'] = [i for i in bykey[bk] if i != r['id']]
    out.sort(key=lambda r: (r['vendor'] != 'Guition', r['params'].get('size_in') or 99, r['model']))
    ids = collections.Counter(r['id'] for r in out)
    assert all(v == 1 for v in ids.values()), [k for k, v in ids.items() if v > 1]

    os.makedirs(os.path.join(SITE, 'data'), exist_ok=True)
    json.dump(out, open(os.path.join(SITE, 'data/models.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
    # archives list for the downloads page
    arch_out = []
    for a in archives:
        arch_out.append({k: a.get(k) for k in ('slug', 'name', 'dir', 'path', 'size', 'url', 'type', 'manifest', 'hosted', 'hosted_archive', 'stats', 'error', 'created_at')}
                        | {'models': sorted(set(assigned.get(a['name'], [])))})
    json.dump(arch_out, open(os.path.join(SITE, 'data/archives.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
    # docs list (for docs search)
    slug2models = {a['slug']: sorted(set(assigned.get(a['name'], []))) for a in archives}
    docs = [{'id': i, 'a': d['archive'], 'p': d['path'], 'b': d.get('blob') or '', 'u': d.get('url') or '', 't': d['text']} for i, d in enumerate(docs_text)]
    json.dump(docs, open(os.path.join(RAW, 'docs_for_index.json'), 'w'), ensure_ascii=False)
    fields = [k for k in FIELD_LABELS]
    meta = {'generated': now, 'counts': dict(collections.Counter(r['vendor'] for r in out)), 'models': len(out),
            'archives': len(archives), 'archive_bytes': sum(a['size'] for a in archives),
            'hosted_blobs': len(os.listdir(os.path.join(SITE, 'docs/b'))) if os.path.isdir(os.path.join(SITE, 'docs/b')) else 0,
            'field_labels': FIELD_LABELS, 'slug2models': slug2models,
            'sources': ['https://www.guition.com/model-selection', 'https://www.guition.com/sk/model-selection', 'https://www.guition.com/sitemap.xml',
                        'https://pan.jczn1688.com/', 'https://www.waveshare.com/', 'https://docs.waveshare.com/']}
    json.dump(meta, open(os.path.join(SITE, 'data/meta.json'), 'w'), ensure_ascii=False, indent=1)
    print('models', len(out), meta['counts'])
    print('unassigned archives', [a['name'] for a in archives if not assigned.get(a['name'])])


if __name__ == '__main__':
    main()
