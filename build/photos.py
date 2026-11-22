"""Optimised HD photos for every board (run after build_site.py / offline.py).

Sources, in priority order (never a photo of a different board – if unsure, skip):
  1. vendor product photos already scraped (guition.com product gallery = vendor max 800x800,
     Waveshare shop images – the full-resolution original is fetched instead of the 800px cache copy)
  2. images from the board's own official archive (folder "Structure_Diagram"/"Dimension": annotated
     board photos showing the connectors) – only when the archive name matches the model exactly
     (touch-letter variants C/N/R share the PCB; colour/case variants like _Y, (GY) are excluded)
  3. data/curated/photos.json – manually verified extra photos {model: [{url, source_page, note}]}
Output: site/assets/img/hd/<key>.webp (≤1600 px, <1 MB) + site/assets/img/th/<key>.webp (≤400 px),
models.json images[] = {src, thumb, w, h, kind, orig, source_page, note}."""
import json, os, re, io, hashlib, subprocess
from PIL import Image
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, 'site')
CFG = json.load(open(os.path.join(ROOT, 'build/config.json')))
CACHE = os.path.normpath(os.environ.get('GUITION_CACHE') or os.path.join(ROOT, CFG['cache_dir']))
PH_CACHE = os.path.join(CACHE, 'photos')
HD, TH = 'assets/img/hd', 'assets/img/th'
MAX_HD, MAX_TH, MAX_BYTES = 1600, 400, 1_000_000
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36'

def fetch(url):
    os.makedirs(PH_CACHE, exist_ok=True)
    fp = os.path.join(PH_CACHE, hashlib.sha1(url.encode()).hexdigest()[:20])
    if not os.path.exists(fp):
        r = subprocess.run(['curl', '-sfL', '-m', '60', '-A', UA, '-o', fp + '.part', url])
        if r.returncode or not os.path.exists(fp + '.part'):
            return None
        os.replace(fp + '.part', fp)
    return open(fp, 'rb').read()

def optimise(data):
    """-> (key, w, h) ; writes hd + thumb webp (idempotent)."""
    key = hashlib.sha1(data).hexdigest()[:16]
    hd, th = os.path.join(SITE, HD, key + '.webp'), os.path.join(SITE, TH, key + '.webp')
    im = Image.open(io.BytesIO(data))
    im.load()
    if im.mode in ('RGBA', 'LA', 'P'):
        im = im.convert('RGBA')
        bg = Image.new('RGB', im.size, 'white'); bg.paste(im, mask=im.split()[-1]); im = bg
    else:
        im = im.convert('RGB')
    w, h = im.size
    if not os.path.exists(hd):
        os.makedirs(os.path.dirname(hd), exist_ok=True); os.makedirs(os.path.dirname(th), exist_ok=True)
        big = im.copy(); big.thumbnail((MAX_HD, MAX_HD), Image.LANCZOS)
        for q in (84, 76, 68, 60, 50):
            buf = io.BytesIO(); big.save(buf, 'WEBP', quality=q, method=6)
            if buf.tell() <= MAX_BYTES: break
        open(hd, 'wb').write(buf.getvalue())
        sm = im.copy(); sm.thumbnail((MAX_TH, MAX_TH), Image.LANCZOS); sm.save(th, 'WEBP', quality=78, method=6)
    big_w, big_h = (w, h) if max(w, h) <= MAX_HD else ((MAX_HD, round(h * MAX_HD / w)) if w >= h else (round(w * MAX_HD / h), MAX_HD))
    return key, big_w, big_h

def full_res_waveshare(url):
    return re.sub(r'/media/catalog/product/cache/\d+/image/(\d+x\d+/)?[0-9a-f]{32}/', '/media/catalog/product/', url)

def norm(s):
    return re.sub(r'[^A-Z0-9]', '', s.upper())

def archive_matches(model, archive_name):
    stem = re.sub(r'\.(zip|rar|7z)$', '', archive_name, flags=re.I)
    stem = re.sub(r'^\d+(\.\d+)?inch_', '', stem, flags=re.I)
    stem = re.sub(r'(_?(EN|CN))$', '', stem)
    a, m = norm(stem), norm(model)
    return m.startswith(a) and re.fullmatch(r'[CNR]?(I)?', m[len(a):]) is not None

def main():
    models = json.load(open(os.path.join(SITE, 'data/models.json')))
    curated = {k: v for k, v in json.load(open(os.path.join(ROOT, 'data/curated/photos.json'))).items() if not k.startswith('_')} if os.path.exists(os.path.join(ROOT, 'data/curated/photos.json')) else {}
    manifests = {}
    by_archive = {}
    for o in models:
        for f in o['files']:
            if f.get('type') == 'archive': by_archive.setdefault(f['name'], []).append(o)
    stats = {'models': len(models), 'with_photo': 0, 'hd_ge_1000': 0, 'missing': [], 'images': 0}
    used = set()
    for m in models:
        if m['images'] and all(i['src'].startswith(HD) for i in m['images']):   # already processed (re-run)
            used.update(os.path.basename(i['src'])[:-5] for i in m['images'])
            photos = [i for i in m['images'] if i['kind'] == 'photo']
            stats['images'] += len(m['images']); stats['with_photo'] += bool(photos)
            stats['hd_ge_1000'] += bool(photos) and max(max(i['w'], i['h']) for i in photos) >= 1000
            if not photos: stats['missing'].append(m['model'])
            continue
        out, seen = [], set()
        def add(data, kind, orig, page=None, note=None):
            if not data: return
            try:
                key, w, h = optimise(data)
            except Exception as e:
                print('  bad image', orig, e); return
            if key in seen: return
            seen.add(key); used.add(key)
            out.append({'src': f'{HD}/{key}.webp', 'thumb': f'{TH}/{key}.webp', 'w': w, 'h': h, 'kind': kind, 'orig': orig, 'source_page': page, 'note': note})
        cur = curated.get(m['model'], {})
        if isinstance(cur, list): cur = {'photos': cur}
        for c in cur.get('photos', []):
            if c.get('kind', 'photo') == 'photo':
                add(fetch(c['url']), 'photo', c['url'], c.get('source_page'), c.get('note'))
        for im in ([] if cur.get('replace_vendor') else m['images']):
            if im.get('kind') == 'thumb' and any(i.get('kind') == 'product' for i in m['images']):
                continue
            orig = im.get('orig') or ''
            data = None
            if 'waveshare.com/media/catalog/product/cache' in orig:
                data = fetch(full_res_waveshare(orig))
                if data: orig = full_res_waveshare(orig)
            if data is None:
                lp = os.path.join(SITE, im['src'])
                data = open(lp, 'rb').read() if os.path.exists(lp) and not im['src'].startswith(HD) else None
            if data is None and orig:
                data = fetch(orig)
            page = next((s for s in m['sources'] if 'guition.com/' in s and '/model-selection' not in s), None) if m['vendor'] == 'Guition' else (m['sources'][0] if m['sources'] else None)
            add(data, 'photo', orig, page, im.get('note'))
        for c in cur.get('photos', []):
            if c.get('kind', 'photo') != 'photo':
                add(fetch(c['url']), c['kind'], c['url'], c.get('source_page'), c.get('note'))
        # official archive images (structure / dimension) for exactly this board
        for f in m['files']:
            if f.get('type') != 'archive' or not f.get('manifest') or not archive_matches(m['model'], f['name']):
                continue
            if any(o is not m and not archive_matches(o['model'], f['name']) for o in by_archive.get(f['name'], [])):
                continue   # a case/colour variant shares this archive – its pictures may show the other variant
            man = manifests.get(f['manifest']) or manifests.setdefault(f['manifest'], json.load(open(os.path.join(SITE, f['manifest']))))
            cand = [r for r in man['tree'] if r[2] and re.search(r'\.(jpe?g|png)$', r[0], re.I) and r[1] > 40_000
                    and re.search(r'structure|dimension|尺寸|结构', r[0], re.I) and not re.search(r'demo|lib|example', r[0], re.I)]
            cand.sort(key=lambda r: (not re.search(r'/\d+(-\d+)?\.(jpe?g|png)$|主图', r[0], re.I), -r[1]))
            for r in cand[:3]:
                kind = 'drawing' if re.search(r'dimension|尺寸', r[0], re.I) else 'diagram'
                add(open(os.path.join(SITE, 'docs/b', r[2]), 'rb').read(), kind, f['url'] + ' :: ' + r[0], f['url'], 'from the official archive ' + f['name'])
        m['images'] = out
        photos = [i for i in out if i['kind'] == 'photo']
        stats['images'] += len(out)
        if photos:
            stats['with_photo'] += 1
            if max(max(i['w'], i['h']) for i in photos) >= 1000: stats['hd_ge_1000'] += 1
        else:
            stats['missing'].append(m['model'] + (' (diagram only)' if out else ''))
    # remove orphaned optimised files
    for d in (HD, TH):
        for fn in os.listdir(os.path.join(SITE, d)):
            if fn[:-5] not in used: os.remove(os.path.join(SITE, d, fn))
    json.dump(models, open(os.path.join(SITE, 'data/models.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
    json.dump(stats, open(os.path.join(ROOT, 'data/raw/photo_stats.json'), 'w'), indent=1, ensure_ascii=False)
    sz = sum(os.path.getsize(os.path.join(SITE, d, f)) for d in (HD, TH) for f in os.listdir(os.path.join(SITE, d)))
    print(f"photos: {stats['with_photo']}/{len(models)} boards with photos, {stats['hd_ge_1000']} ≥1000px, {stats['images']} images, {sz/1e6:.1f} MB; missing: {stats['missing']}")

if __name__ == '__main__':
    main()
