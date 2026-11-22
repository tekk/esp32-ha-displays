#!/usr/bin/env python3
"""Monthly incremental update of the catalog (runs on GitHub Actions, also works locally).

Checks every source, adds what is new / changed, rebuilds the static site, commits and pushes.
Designed for a CI runner with ~14 GB free disk and NO download cache: files are processed one at
a time (download → extract docs → place in site/ or upload as release asset → delete), and change
detection uses the recorded metadata (data/raw/pan_files.json, site/data/offline.json,
data/release_assets.json, data/auto/*.json) plus size / shard sha256 / ETag / pushed_at.

Sources checked
  1. pan.jczn1688.com file server  – new / changed files (size + shard sha256)
  2. guition.com model-selection (EN+SK) + sitemap product pages – new boards, new product files
  3. Waveshare – ESP32-P4 shop search (new products are reported, never auto-added: specs need curation),
                 HEAD of every referenced Waveshare download (Content-Length / ETag)
  4. GitHub – search for new Guition community repositories (auto-linked to matching boards),
              pushed_at of mirrored repositories (licensed snapshots are refreshed)

Outputs: build/last_update/{log.txt,stats.json,summary.md}
Usage:   build/update.sh [--dry-run] [--no-push] [--no-upload] [--keep-downloads] [--skip pan,guition,waveshare,github]
Env:     GUITION_CACHE  download dir (default: config cache_dir); CI=true deletes downloads after use.
         GH_TOKEN/GITHUB_TOKEN for gh (release upload, GitHub search).
This script never sends e-mail; the workflow does that from the files above."""
import argparse, datetime, hashlib, json, os, re, shutil, subprocess, sys, time, traceback
from urllib.parse import urlsplit, unquote
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'build'))
CFG = json.load(open(os.path.join(ROOT, 'build/config.json')))
OUT = os.path.join(ROOT, 'build/last_update')
AUTO = os.path.join(ROOT, 'data/auto')
UA = {'User-Agent': 'Mozilla/5.0 (esp32-ha-displays catalog updater; +https://github.com/%s)' % CFG['offline']['release_repo']}
S = requests.Session(); S.headers.update(UA)

ap = argparse.ArgumentParser()
ap.add_argument('--dry-run', action='store_true', help='only detect and report; change nothing')
ap.add_argument('--no-push', action='store_true', help='commit locally but do not push')
ap.add_argument('--no-commit', action='store_true')
ap.add_argument('--no-upload', action='store_true', help='do not upload release assets')
ap.add_argument('--keep-downloads', action='store_true', help='keep downloaded files (default on a workstation)')
ap.add_argument('--skip', default='', help='comma list: pan,guition,waveshare,github')
ap.add_argument('--max-download-gb', type=float, default=10.0, help='stop downloading new files after this much')
A = ap.parse_args()
SKIP = set(x for x in A.skip.split(',') if x)
DELETE_AFTER = (os.environ.get('CI') == 'true') and not A.keep_downloads
CACHE = os.path.normpath(os.environ.get('GUITION_CACHE') or os.path.join(ROOT, CFG['cache_dir']))
os.environ['GUITION_CACHE'] = CACHE
EXTRA = os.path.join(CACHE, 'extra') if os.environ.get('GUITION_CACHE') else os.path.normpath(os.path.join(ROOT, CFG['offline']['extra_dir']))

os.makedirs(OUT, exist_ok=True); os.makedirs(AUTO, exist_ok=True)
LOG = open(os.path.join(OUT, 'log.txt'), 'w')
T0 = time.time()
STATS = {'started': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'), 'dry_run': A.dry_run,
         'new_boards': [], 'removed_boards': [], 'new_files': [], 'changed_files': [], 'removed_upstream': [],
         'new_repos': [], 'updated_repos': [], 'waveshare_candidates': [], 'uploaded_assets': [],
         'bytes_downloaded': 0, 'errors': [], 'warnings': [], 'commit': None, 'pushed': False, 'duration_s': 0}


def log(*a):
    s = ' '.join(str(x) for x in a)
    line = time.strftime('%H:%M:%S ') + s
    print(line, flush=True)
    LOG.write(line + '\n'); LOG.flush()


def err(where, e):
    msg = f'{where}: {e}'
    log('ERROR', msg)
    STATS['errors'].append(msg)


def run(cmd, check=True, env=None, quiet=False, log_output=True):
    log('$', ' '.join(cmd) if isinstance(cmd, list) else cmd)
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=env, shell=isinstance(cmd, str))
    out = (p.stdout or '') + (p.stderr or '')
    lines = out.rstrip().splitlines()
    for l in ([] if not log_output else lines[-25:] if quiet else lines[-200:]):
        LOG.write('    ' + l + '\n')
    LOG.flush()
    if check and p.returncode:
        raise RuntimeError(f'{cmd if isinstance(cmd, str) else cmd[0:3]} exited {p.returncode}: ' + ' | '.join(lines[-5:]))
    return p


def jload(p, default=None):
    p = os.path.join(ROOT, p)
    return json.load(open(p)) if os.path.exists(p) else default


def jsave(p, obj, **kw):
    json.dump(obj, open(os.path.join(ROOT, p), 'w'), ensure_ascii=False, **(kw or {'indent': 1}))


def rm(path):
    if DELETE_AFTER and os.path.exists(path):
        os.remove(path)
        log('  deleted local copy', os.path.relpath(path, CACHE))


def py(script, *args):
    return run([sys.executable, os.path.join('build', script), *args])


def rebuild_data():
    """build_site + offline (cheap, ~seconds): needed after every new file so offline.py can place it."""
    py('build_site.py')
    py('features.py')          # normalized feature pictograms for every board (also new ones)
    py('offline.py')


def upload(assets):
    if A.no_upload or not assets:
        return
    env = dict(os.environ, ONLY_ASSETS=' '.join(assets), STAGE_DIR=os.path.join(CACHE, 'release-staging'))
    p = run(['bash', 'build/upload_release.sh'], check=False, env=env)
    if p.returncode:
        err('upload', 'upload_release.sh failed for ' + ', '.join(assets))
    else:
        STATS['uploaded_assets'] += assets
    shutil.rmtree(os.path.join(CACHE, 'release-staging'), ignore_errors=True)


def assets_for(key):
    ent = (jload('site/data/offline.json', {}).get('files') or {}).get(key)
    return [ent['asset']] if ent and ent.get('type') == 'release' else []


# ---------------------------------------------------------------- 1. Guition file server
def step_pan():
    import fetch_pan
    old = {f['path']: f for f in jload('data/raw/pan_files.json', [])}
    files = fetch_pan.walk()
    log(f'pan: {len(files)} files listed ({sum(f["size"] for f in files)/1e9:.2f} GB), previously {len(old)}')
    if len(files) < 0.8 * len(old):
        raise RuntimeError(f'pan listing suspiciously short ({len(files)} vs {len(old)}) – not touching anything')
    todo = []
    for f in files:
        f['directlink'] = fetch_pan.directlink(f)
        o = old.get(f['path'])
        try:
            f['manifest'] = fetch_pan.get_json(fetch_pan.BASE + '/api/manifest/' + fetch_pan.quote(f['path']))
        except Exception as e:
            f['manifest'] = None; f['error'] = f'manifest: {e}'
            if o:
                f['manifest'] = o.get('manifest')
            err('pan manifest ' + f['path'], e)
        sig = lambda x: [s['sha256'] for s in sorted((x.get('manifest') or {}).get('shards', []), key=lambda s: s['seq'])]
        if not o:
            STATS['new_files'].append({'source': 'guition-server', 'path': f['path'], 'size': f['size']})
            todo.append(f)
        elif o['size'] != f['size'] or (sig(o) and sig(f) and sig(o) != sig(f)):
            STATS['changed_files'].append({'source': 'guition-server', 'path': f['path'], 'size': f['size'], 'old_size': o['size']})
            todo.append(f)
    for p in old:
        if p not in {f['path'] for f in files}:
            STATS['removed_upstream'].append({'source': 'guition-server', 'path': p})
            log('  removed upstream (offline copy kept):', p)
    todo = [f for f in todo if fetch_pan.included(f) and f.get('manifest')]
    log(f'pan: {len(todo)} new/changed files to process')
    if A.dry_run:
        return
    # keep records of upstream-removed files so their offline copies stay listed
    jsave('data/raw/pan_files.json', files + [o for p, o in old.items() if p not in {f['path'] for f in files}])
    budget = A.max_download_gb * 1e9
    for f in todo:
        if f['size'] > budget:
            STATS['warnings'].append(f'download budget reached – {f["path"]} postponed to next run')
            log('  budget reached, postponing', f['path']); continue
        try:
            log(f'  download {f["path"]} ({f["size"]/1e6:.1f} MB)')
            dst = fetch_pan.local_path(f)
            if os.path.exists(dst) and os.path.getsize(dst) != f['size']:
                os.remove(dst)
            fetch_pan.download(f)
            STATS['bytes_downloaded'] += f['size']; budget -= f['size']
            py('process_archives.py', '--only', f['path'])
            rebuild_data()
            slug = next(a['slug'] for a in jload('data/raw/archives.json') if a['path'] == f['path'])
            upload(assets_for('pan:' + slug))
            rm(dst)
        except Exception as e:
            err('pan ' + f['path'], e)
            if f['path'] not in old:   # leave it out so the next run retries
                jsave('data/raw/pan_files.json', [x for x in jload('data/raw/pan_files.json') if x['path'] != f['path']])


# ---------------------------------------------------------------- 2. guition.com
def model_ids():
    return {m['model'] for m in jload('site/data/models.json', [])}


def step_guition():
    import scrape_guition as sg
    old_t = jload('data/raw/guition_table.json', {})
    old_p = jload('data/raw/guition_products.json', [])
    old_models = {r.get('model') for r in old_t.get('en', {}).get('records', [])}
    html = sg.get(sg.BASE + '/model-selection')
    header, grid = sg.parse_table(html, 'en')
    recs = sg.table_records(header, grid)
    new_models = {r.get('model') for r in recs}
    sm = sg.get(sg.BASE + '/sitemap.xml')
    urls = set(u for u in re.findall(r'<loc>([^<]+)</loc>', sm)
               if re.match(r'https://www\.guition\.com/(%s)/[^/]+$' % '|'.join(map(re.escape, sg.CATS)), u))
    old_urls = {p['url'] for p in old_p}
    log(f'guition: table {len(recs)} rows (was {len(old_t.get("en", {}).get("records", []))}), sitemap {len(urls)} product pages (known {len(old_urls)})')
    for m in sorted(x for x in new_models - old_models if x):
        log('  new model in table:', m)
    for u in sorted(urls - old_urls):
        log('  new product page:', u)
    for m in sorted(x for x in old_models - new_models if x):
        STATS['warnings'].append(f'model no longer in guition table (kept): {m}')
    if A.dry_run:
        STATS['new_boards'] += [{'model': m, 'vendor': 'Guition', 'source': 'model-selection'} for m in sorted(x for x in new_models - old_models if x)]
        STATS['new_files'] += [{'source': 'guition.com', 'path': u, 'note': 'new product page'} for u in sorted(urls - old_urls)]
        return
    if len(recs) < 0.9 * len(old_t.get('en', {}).get('records', [])):
        raise RuntimeError('guition table shrank by >10 % – keeping the previous scrape')
    bak = {p: open(os.path.join(ROOT, p), 'rb').read() for p in ('data/raw/guition_table.json', 'data/raw/guition_products.json')}
    before_files = {u for p in old_p for u in p.get('files', [])}
    before_imgs = set(os.listdir(os.path.join(ROOT, 'site/assets/img/guition')))
    try:
        py('scrape_guition.py')
        t = jload('data/raw/guition_table.json'); prods = jload('data/raw/guition_products.json')
        if len(t['en']['records']) < 0.9 * len(old_t['en']['records']) or len(prods) < 0.9 * len(old_p):
            raise RuntimeError('scrape result smaller than before')
    except Exception as e:
        for p, b in bak.items():
            open(os.path.join(ROOT, p), 'wb').write(b)
        raise
    for p in prods:
        for u in p.get('files', []):
            if u not in before_files:
                STATS['new_files'].append({'source': 'guition.com', 'path': u})
    n_img = len(set(os.listdir(os.path.join(ROOT, 'site/assets/img/guition'))) - before_imgs)
    if n_img:
        log(f'  {n_img} new product images')


# ---------------------------------------------------------------- 3. Waveshare
def ws_urls():
    ws = jload('data/curated/waveshare.json')
    files, pages = [], set()
    for g in list(ws['common'].values()) + ws['models']:
        files += [f['url'] for f in g.get('files', [])]
        pages.update(g.get('sources', []))
    return list(dict.fromkeys(files)), pages


def step_waveshare():
    seen_f = os.path.join(AUTO, 'waveshare_seen.json')
    seen = json.load(open(seen_f)) if os.path.exists(seen_f) else {'products': [], 'etags': {}}
    files, pages = ws_urls()
    # 3a. new ESP32-P4 products in the shop
    found = set()
    for q in ('ESP32-P4', 'ESP32-P4 display', 'ESP32-P4 LCD'):
        r = S.get('https://www.waveshare.com/catalogsearch/result/', params={'q': q}, timeout=60)
        r.raise_for_status()
        for u in re.findall(r'href="(https://www\.waveshare\.com/[a-z0-9.\-]+\.htm)"', r.text):
            if re.search(r'esp32-p4', u, re.I):
                found.add(u)
    disp = {u for u in found if re.search(r'lcd|amoled|oled|display|touch|knob|screen', u, re.I)}
    known = set(seen['products']) | {u for u in pages if u.startswith('https://www.waveshare.com/')}
    log(f'waveshare: {len(found)} ESP32-P4 shop products found ({len(disp)} with a display), {len(disp - known)} display products not in the catalog')
    found -= disp - known          # display products stay 'candidates' every run until curated into waveshare.json
    for u in sorted(disp - known):
        STATS['waveshare_candidates'].append(u)
        log('  candidate (needs manual curation, not auto-added):', u)
    # 3b. referenced downloads changed?
    off = (jload('site/data/offline.json', {}).get('files') or {})
    changed = []
    for u in files:
        try:
            h = S.head(u, timeout=60, allow_redirects=True)
            size = int(h.headers.get('Content-Length') or 0)
            etag = h.headers.get('ETag') or h.headers.get('Last-Modified')
            if h.status_code >= 400:
                STATS['warnings'].append(f'waveshare file HTTP {h.status_code}: {u}'); continue
            prev = off.get(u, {})
            old_etag = seen['etags'].get(u)
            if (prev.get('size') and size and size != prev['size']) or (old_etag and etag and etag != old_etag):
                changed.append((u, size))
                STATS['changed_files'].append({'source': 'waveshare', 'path': u, 'size': size, 'old_size': prev.get('size')})
            elif not prev:
                changed.append((u, size))
                STATS['new_files'].append({'source': 'waveshare', 'path': u, 'size': size})
            if etag and u not in [c[0] for c in changed]:
                seen['etags'][u] = etag
        except Exception as e:
            err('waveshare HEAD ' + u, e)
    log(f'waveshare: {len(files)} referenced files checked, {len(changed)} new/changed')
    if A.dry_run:
        return
    for u, size in changed:
        try:
            name = unquote(urlsplit(u).path.rsplit('/', 1)[-1])
            dst = os.path.join(EXTRA, 'waveshare', name)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            log('  download', u)
            with S.get(u, stream=True, timeout=300) as r, open(dst + '.part', 'wb') as fo:
                r.raise_for_status()
                for b in r.iter_content(1 << 20):
                    fo.write(b)
            os.replace(dst + '.part', dst)
            STATS['bytes_downloaded'] += os.path.getsize(dst)
            # invalidate the previous placement so offline.py re-hashes / re-places it
            oj = jload('site/data/offline.json'); prev = oj['files'].pop(u, None); jsave('site/data/offline.json', oj, indent=0)
            if prev and prev['type'] == 'local':
                lp = os.path.join(ROOT, 'site', prev['url'])
                if os.path.exists(lp): os.remove(lp)
            for root in ('site/files/waveshare',):          # copies hosted directly by build_site
                lp = os.path.join(ROOT, root, name)
                if os.path.exists(lp): os.remove(lp)
            rebuild_data()
            upload(assets_for(u))
            h = S.head(u, timeout=60, allow_redirects=True)
            if h.headers.get('ETag') or h.headers.get('Last-Modified'):
                seen['etags'][u] = h.headers.get('ETag') or h.headers.get('Last-Modified')
            rm(dst)
        except Exception as e:
            err('waveshare ' + u, e)
    seen['products'] = sorted(set(seen['products']) | found)
    json.dump(seen, open(seen_f, 'w'), indent=1)


# ---------------------------------------------------------------- 4. GitHub
def gh_api(path):
    p = run(['gh', 'api', '-H', 'Accept: application/vnd.github+json', path], check=True, log_output=False)
    return json.loads(p.stdout)


def model_prefixes():
    pre = set()
    for m in model_ids():
        mm = re.match(r'(JC\d{4}[A-Z]\d{3}|ESP32-\d{4}S\d{3})', m)
        if mm:
            pre.add(mm.group(1))
    return pre


GH_MIN_STARS, GH_MAX_NEW, GH_MAX_SNAPSHOT_KB = 3, 40, 500_000


def norm(s):
    return re.sub(r'[^A-Z0-9]', '', s.upper())


def step_github():
    community = jload('data/curated/community.json')
    mirror_f = os.path.join(ROOT, 'data/curated/mirror_repos.txt')
    mirror = [l.strip() for l in open(mirror_f) if l.strip() and not l.startswith('#')]
    auto_f = os.path.join(AUTO, 'community_auto.json')
    auto = json.load(open(auto_f)) if os.path.exists(auto_f) else {'_comment': 'Auto-discovered by build/update.py (GitHub search). Linked to boards whose model number appears in the repo name/description.', 'repos': [], 'ignored': []}
    known = {c['url'].lower().rstrip('/') for c in community['repos'] + community['official_github_series']}
    known |= {('https://github.com/' + r).lower() for r in mirror}
    known |= {c['url'].lower() for c in auto['repos']} | {u.lower() for u in auto['ignored']}
    prefixes = model_prefixes()
    queries = ['guition', 'guition esp32', 'guition display', 'jczn', 'JC4880P443', 'JC8012P4A1', 'JC1060P470', 'JC3248W535',
               'JC3636W518', 'JC4827W543', 'JC2432W328', 'ESP32-8048S043', 'ESP32-2432S028', 'ESP32-3248S035']
    found = {}
    for q in queries:
        try:
            d = gh_api(f'search/repositories?q={requests.utils.quote(q)}+fork:false&sort=updated&per_page=50')
            for it in d.get('items', []):
                found[it['html_url']] = it
            time.sleep(2.5)
        except Exception as e:
            err('github search ' + q, e)
    new, low = [], []
    for url, it in sorted(found.items()):
        if url.lower() in known or it['full_name'].lower() == CFG['offline']['release_repo'].lower():
            continue
        text = norm(it['full_name'] + ' ' + (it.get('description') or ''))
        hits = sorted(p for p in prefixes if norm(p) in text)
        guition = 'GUITION' in text or 'JCZN' in text
        if not hits and not guition:
            continue
        lic = (it.get('license') or {}).get('spdx_id')
        lic = None if lic in (None, 'NOASSERTION', 'NONE') else lic
        stars = it.get('stargazers_count') or 0
        # signal filter: link only repos that name a board and have some traction; the rest is remembered as
        # 'ignored' so it is not reported again every month (hundreds of tiny CYD sketches exist)
        if not hits or not (stars >= GH_MIN_STARS or (lic and stars >= 1)) or not it.get('description'):
            low.append(url)
            continue
        ent = {'url': url, 'title': it['full_name'], 'desc': (it.get('description') or '').strip()[:200],
               'match': '^(' + '|'.join(re.escape(h) for h in hits) + ')',
               'license': lic, 'stars': stars, 'size_kb': it.get('size'),
               'pushed_at': it.get('pushed_at'), 'discovered': STATS['started'][:10]}
        new.append(ent)
    new.sort(key=lambda e: -e['stars'])
    for ent in new[GH_MAX_NEW:]:
        low.append(ent['url'])
    new = new[:GH_MAX_NEW]
    for ent in new:
        STATS['new_repos'].append({k: ent[k] for k in ('url', 'license', 'match', 'stars')})
        log('  new repo:', ent['url'], 'license', ent['license'], 'stars', ent['stars'], 'boards', ent['match'])
    STATS['github_low_signal_skipped'] = len(low)
    log(f'github: {len(found)} search hits, {len(new)} new linked repos, {len(low)} low-signal repos remembered as ignored')
    # pushed_at of mirrored repos
    state_f = os.path.join(AUTO, 'repos_state.json')
    state = json.load(open(state_f)) if os.path.exists(state_f) else {}
    repos_off = jload('site/data/offline.json', {}).get('repos', {})
    refresh = []
    for r in mirror:
        try:
            d = gh_api(f'repos/{r}')
        except Exception as e:
            err('github repo ' + r, e); continue
        pa = d.get('pushed_at')
        if r in state and pa and pa != state[r] and repos_off.get(r, {}).get('mirrored'):
            refresh.append(r)
            STATS['updated_repos'].append({'repo': r, 'pushed_at': pa, 'previous': state[r]})
        if r not in state or r not in refresh:
            state[r] = pa
    log(f'github: {len(mirror)} mirrored/known repos checked, {len(refresh)} updated since last snapshot')
    if A.dry_run:
        return
    auto['repos'] += new
    auto['ignored'] = sorted(set(auto['ignored']) | set(low))
    json.dump(auto, open(auto_f, 'w'), indent=1, ensure_ascii=False)
    # snapshot new licensed repos + refresh updated mirrored ones, one at a time
    to_snap = refresh + [e['title'] for e in new if e['license'] and (e.get('size_kb') or 0) < GH_MAX_SNAPSHOT_KB]
    for r in to_snap:
        try:
            dst = os.path.join(EXTRA, 'github', r.replace('/', '__') + '.zip')
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            log('  snapshot', r)
            with S.get(f'https://codeload.github.com/{r}/zip/HEAD', stream=True, timeout=600) as resp, open(dst + '.part', 'wb') as fo:
                resp.raise_for_status()
                for b in resp.iter_content(1 << 20):
                    fo.write(b)
            os.replace(dst + '.part', dst)
            STATS['bytes_downloaded'] += os.path.getsize(dst)
            if r not in mirror:
                with open(mirror_f, 'a') as fo:
                    fo.write(r + '\n')
                mirror.append(r)
            oj = jload('site/data/offline.json'); oj['files'].pop('repo:' + r.lower(), None); oj['repos'].pop(r, None)
            jsave('site/data/offline.json', oj, indent=0)
            rebuild_data()
            upload(assets_for('repo:' + r.lower()))
            if r in refresh:
                state[r] = next(x['pushed_at'] for x in STATS['updated_repos'] if x['repo'] == r)
            rm(dst)
        except Exception as e:
            err('snapshot ' + r, e)
    json.dump(state, open(state_f, 'w'), indent=1, sort_keys=True)


# ---------------------------------------------------------------- main
def finish():
    STATS['duration_s'] = round(time.time() - T0, 1)
    STATS['finished'] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
    json.dump(STATS, open(os.path.join(OUT, 'stats.json'), 'w'), indent=1, ensure_ascii=False)
    md = [f"# Catalog update {STATS['started'][:10]}{' (dry run)' if A.dry_run else ''}", '',
          f"Result: **{'OK' if not STATS['errors'] else str(len(STATS['errors'])) + ' error(s)'}** · duration {STATS['duration_s']/60:.1f} min · "
          f"downloaded {STATS['bytes_downloaded']/1e6:.1f} MB", '',
          '| | count |', '|---|---|',
          f"| New boards | {len(STATS['new_boards'])} |", f"| New files | {len(STATS['new_files'])} |",
          f"| Changed files | {len(STATS['changed_files'])} |", f"| Removed upstream (kept) | {len(STATS['removed_upstream'])} |",
          f"| New community repos | {len(STATS['new_repos'])} |", f"| Updated mirrored repos | {len(STATS['updated_repos'])} |",
          f"| Waveshare candidates (manual) | {len(STATS['waveshare_candidates'])} |", f"| Release assets uploaded | {len(STATS['uploaded_assets'])} |",
          f"| Errors | {len(STATS['errors'])} |", '']
    def sec(title, items, fmt):
        if items:
            md.append(f'## {title}'); md.extend('- ' + fmt(x) for x in items[:100]); md.append('')
    sec('New boards', STATS['new_boards'], lambda x: f"{x['model']} ({x['vendor']})")
    sec('New files', STATS['new_files'], lambda x: f"[{x['source']}] {x['path']}" + (f" – {x['size']/1e6:.1f} MB" if x.get('size') else ''))
    sec('Changed files', STATS['changed_files'], lambda x: f"[{x['source']}] {x['path']}")
    sec('Removed upstream (offline copy kept)', STATS['removed_upstream'], lambda x: f"[{x['source']}] {x['path']}")
    sec('New community repositories', STATS['new_repos'], lambda x: f"{x['url']} (license: {x['license'] or 'none'})")
    sec('Updated mirrored repositories', STATS['updated_repos'], lambda x: x['repo'])
    sec('Waveshare products to curate', STATS['waveshare_candidates'], str)
    sec('Errors', STATS['errors'], str)
    sec('Warnings', STATS['warnings'], str)
    if STATS['commit']:
        md.append(f"Commit: {STATS['commit']}{' (pushed)' if STATS['pushed'] else ''}")
    md.append(f"Site: {CFG['offline'].get('pages_url', '')}")
    open(os.path.join(OUT, 'summary.md'), 'w').write('\n'.join(md) + '\n')
    log(f"done in {STATS['duration_s']}s – new boards {len(STATS['new_boards'])}, new files {len(STATS['new_files'])}, "
        f"changed {len(STATS['changed_files'])}, errors {len(STATS['errors'])}")
    LOG.close()


def main():
    log(f"update start ({'DRY RUN' if A.dry_run else 'live'}), cache {CACHE}, delete-after {DELETE_AFTER}")
    shutil.disk_usage(ROOT) and log('disk free: %.1f GB' % (shutil.disk_usage(ROOT).free / 1e9))
    before = model_ids()
    for name, fn in (('pan', step_pan), ('guition', step_guition), ('waveshare', step_waveshare), ('github', step_github)):
        if name in SKIP:
            log('skip', name); continue
        log(f'== {name}')
        try:
            fn()
        except Exception as e:
            err(name, f'{e}\n' + traceback.format_exc(limit=3))
    if A.dry_run:
        return
    log('== rebuild')
    try:
        rebuild_data()
        py('photos.py')
        run(['node', 'build/build_index.mjs'])
        py('gen_sw.py')
        run([sys.executable, 'tests/check_links.py'])
    except Exception as e:
        err('rebuild', e)
        return
    after = model_ids()
    models = {m['model']: m for m in jload('site/data/models.json')}
    STATS['new_boards'] += [{'model': m, 'vendor': models[m]['vendor'], 'source': 'rebuild'} for m in sorted(after - before)]
    STATS['removed_boards'] = sorted(before - after)
    # commit only when something besides the timestamp in meta.json changed
    st = run(['git', 'status', '--porcelain'], quiet=True).stdout.splitlines()
    changed = [l[3:] for l in st if not l[3:].startswith('build/last_update/')]
    if changed == ['site/data/meta.json']:
        run(['git', 'checkout', '--', 'site/data/meta.json']); changed = []
    log(f'{len(changed)} changed paths in the repository')
    if not changed or A.no_commit:
        return
    finish_partial = dict(STATS)  # summary is committed too
    run(['git', 'add', '-A', 'site', 'data', 'build/last_update'])
    msg = (f"Monthly update {STATS['started'][:10]}: {len(STATS['new_boards'])} new boards, {len(STATS['new_files'])} new files, "
           f"{len(STATS['changed_files'])} changed files")
    run(['git', '-c', 'user.name=' + os.environ.get('GIT_AUTHOR_NAME', 'catalog-updater'),
         '-c', 'user.email=' + os.environ.get('GIT_AUTHOR_EMAIL', 'catalog-updater@users.noreply.github.com'), 'commit', '-q', '-m', msg])
    STATS['commit'] = run(['git', 'rev-parse', 'HEAD'], quiet=True).stdout.strip()
    if not A.no_push:
        p = run(['git', 'push', 'origin', 'HEAD'], check=False)
        STATS['pushed'] = p.returncode == 0
        if p.returncode:
            err('git push', p.stderr[-500:])


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        err('fatal', f'{e}\n' + traceback.format_exc())
    finally:
        finish()
    sys.exit(1 if STATS['errors'] else 0)
