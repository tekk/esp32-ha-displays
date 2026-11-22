"""Make every file available offline (run after build_site.py).

For each file (Guition file-server archives/docs, Waveshare downloads, GitHub repo snapshots):
  size <= offline.local_max_bytes  -> copied into site/ (served by GitHub/Cloudflare Pages)
  larger                           -> GitHub Release asset  https://github.com/<repo>/releases/download/<tag>/<asset>
                                      (> release_asset_max_bytes is split into .001/.002… parts, rejoin with `cat`)
Writes:
  data/release_assets.json  – what build/upload_release.sh uploads (asset name ↔ source file ↔ sha256 ↔ original URL)
  site/data/offline.json    – key -> {type, url, size, sha256, parts?, original}
and patches site/data/models.json + archives.json (adds `offline` objects, keeps original URL as mirror).
Asset names are pre-sanitised to [A-Za-z0-9._-] so GitHub does not rename them."""
import json, os, re, shutil, hashlib, zipfile
from urllib.parse import urlsplit, unquote
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, 'site')
CFG = json.load(open(os.path.join(ROOT, 'build/config.json')))
O = CFG['offline']
CACHE = os.path.normpath(os.path.join(ROOT, CFG['cache_dir']))
EXTRA = os.path.normpath(os.path.join(ROOT, O['extra_dir']))
REL_BASE = f"https://github.com/{O['release_repo']}/releases/download/{O['release_tag']}/"
HASHES_F = os.path.join(ROOT, 'data/raw/offline_hashes.json')
HASHES = json.load(open(HASHES_F)) if os.path.exists(HASHES_F) else {}

def sha256(fp):
    st = os.stat(fp)
    k = f'{fp}|{st.st_size}|{int(st.st_mtime)}'
    if k not in HASHES:
        h = hashlib.sha256()
        with open(fp, 'rb') as f:
            for b in iter(lambda: f.read(1 << 22), b''):
                h.update(b)
        HASHES[k] = h.hexdigest()
    return HASHES[k]

def safe(name):
    name = re.sub(r'[^A-Za-z0-9._-]+', '-', name).strip('-.')
    return re.sub(r'-{2,}', '-', name) or 'file'

assets, offline = [], {}

def place(key, src, asset, local_rel, original, kind, extra=None):
    size = os.path.getsize(src)
    ent = {'size': size, 'sha256': sha256(src), 'original': original, 'kind': kind}
    if size <= O['local_max_bytes']:
        dst = os.path.join(SITE, local_rel)
        if not (os.path.exists(dst) and os.path.getsize(dst) == size):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
        ent.update(type='local', url=local_rel)
    else:
        ent.update(type='release', url=REL_BASE + asset, asset=asset)
        a = {'asset': asset, 'src': os.path.relpath(src, ROOT), 'size': size, 'sha256': ent['sha256'], 'original': original, 'kind': kind}
        if size > O['release_asset_max_bytes']:
            n = -(-size // O['split_part_bytes'])
            a['parts'] = [f'{asset}.{i + 1:03d}' for i in range(n)]
            ent['parts'] = [REL_BASE + p for p in a['parts']]
            ent['url'] = ent['parts'][0]
        assets.append(a)
    if extra:
        ent.update(extra)
    offline[key] = ent
    return ent

def main():
    archives = json.load(open(os.path.join(SITE, 'data/archives.json')))
    models = json.load(open(os.path.join(SITE, 'data/models.json')))
    # 1) Guition file server
    for a in archives:
        src = os.path.join(CACHE, 'pan', a['path'])
        ext = os.path.splitext(a['name'])[1].lower()
        if a.get('hosted'):
            local = a['hosted']
        elif a.get('hosted_archive'):
            local = a['hosted_archive']
        else:
            local = f"files/archives/{a['slug']}{ext}"
        ent = place('pan:' + a['slug'], src, safe(a['slug']) + ext, local, a['url'], 'guition-server')
        a['offline'] = ent
        if ext == '.zip' and ent['type'] == 'local' and not a.get('hosted_archive'):
            a['hosted_archive'] = ent['url']          # small zips can be opened completely by the viewer (JSZip)
    by_slug = {a['slug']: a for a in archives}
    for a in archives:                                   # manifests carry the offline link for the viewer
        if a.get('manifest'):
            mp = os.path.join(SITE, a['manifest'])
            man = json.load(open(mp))
            if man.get('offline') != a['offline'] or man.get('hosted_archive') != a.get('hosted_archive'):
                man['offline'], man['hosted_archive'] = a['offline'], a.get('hosted_archive')
                json.dump(man, open(mp, 'w'), ensure_ascii=False, separators=(',', ':'))
    # 2) other downloadable files referenced by models (Waveshare …)
    for m in models:
        for f in m['files']:
            if f.get('slug') in by_slug:
                a = by_slug[f['slug']]
                f['offline'] = a['offline']
                f['hosted_archive'] = a.get('hosted_archive')
                continue
            if f.get('hosted'):
                if f['url'] not in offline:
                    fp = os.path.join(SITE, f['hosted'])
                    offline[f['url']] = {'type': 'local', 'url': f['hosted'], 'size': os.path.getsize(fp), 'sha256': sha256(fp), 'original': f['url'], 'kind': 'vendor-file'}
                f['offline'] = offline[f['url']]
                continue
            name = unquote(urlsplit(f['url']).path.rsplit('/', 1)[-1])
            src = os.path.join(EXTRA, 'waveshare', name)
            if not os.path.exists(src):
                print('MISSING offline copy for', f['url'])
                continue
            if f['url'] not in offline:
                place(f['url'], src, 'waveshare-' + safe(name), 'files/waveshare/' + safe(name), f['url'], 'vendor-file')
            f['offline'] = offline[f['url']]
            f['size'] = f.get('size') or offline[f['url']]['size']
    # 3) GitHub repository snapshots (only repos with a licence file, or vendor-official repos)
    repo_info = {}
    for line in open(os.path.join(ROOT, 'data/curated/mirror_repos.txt')):
        r = line.strip()
        if not r or r.startswith('#'):
            continue
        src = os.path.join(EXTRA, 'github', r.replace('/', '__') + '.zip')
        if not os.path.exists(src):
            repo_info[r] = {'mirrored': False, 'reason': 'download failed'}
            continue
        try:
            names = zipfile.ZipFile(src).namelist()
        except zipfile.BadZipFile:
            repo_info[r] = {'mirrored': False, 'reason': 'bad zip'}
            continue
        lic = next((n.split('/', 1)[1] for n in names if re.match(r'^[^/]+/(LICEN[CS]E|COPYING)[^/]*$', n, re.I)), None)
        owner = r.split('/')[0]
        if not lic and owner not in O['mirror_unlicensed_repo_owners'] and not O.get('mirror_unlicensed_repos'):
            repo_info[r] = {'mirrored': False, 'reason': 'no licence file – linked only'}
            continue
        asset = 'github-' + safe(r.replace('/', '__')) + '.zip'
        ent = place('repo:' + r.lower(), src, asset, 'files/repos/' + asset, f'https://github.com/{r}', 'repo-snapshot', {'license_file': lic})
        repo_info[r] = {'mirrored': True, 'type': ent['type']}
    for m in models:
        for l in m['links']:
            mm = re.match(r'https://github\.com/([^/]+/[^/#?]+)', l['url'])
            if mm and ('repo:' + mm.group(1).lower()) in offline:
                l['offline'] = offline['repo:' + mm.group(1).lower()]
    json.dump(archives, open(os.path.join(SITE, 'data/archives.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
    json.dump(models, open(os.path.join(SITE, 'data/models.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
    json.dump({'release': {'repo': O['release_repo'], 'tag': O['release_tag'], 'base': REL_BASE}, 'files': offline, 'repos': repo_info},
              open(os.path.join(SITE, 'data/offline.json'), 'w'), ensure_ascii=False, indent=0)
    json.dump({'repo': O['release_repo'], 'tag': O['release_tag'], 'assets': assets}, open(os.path.join(ROOT, 'data/release_assets.json'), 'w'), ensure_ascii=False, indent=1)
    json.dump(HASHES, open(HASHES_F, 'w'))
    loc = [e for e in offline.values() if e['type'] == 'local']
    print(f"offline: {len(offline)} files – local {len(loc)} ({sum(e['size'] for e in loc)/1e6:.0f} MB), "
          f"release assets {len(assets)} ({sum(a['size'] for a in assets)/1e9:.2f} GB, split: {[a['asset'] for a in assets if a.get('parts')]})")
    print('repos not mirrored:', {k: v['reason'] for k, v in repo_info.items() if not v['mirrored']})
    names = [a['asset'] for a in assets]
    assert len(names) == len(set(names)), 'duplicate asset names'

if __name__ == '__main__':
    main()
