"""Static integrity check: every local file referenced by data JSON / HTML exists; size + count limits for Pages hosts."""
import json, os, re, glob, sys
S = os.path.join(os.path.dirname(__file__), '..', 'site')
miss = []
ex = lambda p: os.path.isfile(os.path.join(S, p + 'index.html' if p.endswith('/') else p))   # 'board/<id>/' → index.html
models = json.load(open(f'{S}/data/models.json'))
arch = json.load(open(f'{S}/data/archives.json'))
for m in models:
    for i in m['images']:
        ex(i['src']) or miss.append(i['src'])
    for f in m['files']:
        for k in ('hosted', 'hosted_archive', 'manifest'):
            if f.get(k) and not ex(f[k]): miss.append(f[k])
for a in arch:
    for k in ('hosted', 'hosted_archive', 'manifest'):
        if a.get(k) and not ex(a[k]): miss.append(a[k])
off = json.load(open(f'{S}/data/offline.json'))
for k, e in off['files'].items():
    if e['type'] == 'local' and not ex(e['url']): miss.append('offline ' + e['url'])
    if e['type'] == 'release' and not e['url'].startswith(off['release']['base']): miss.append('bad release url ' + e['url'])
no_off = [f['url'] for m in models for f in m['files'] if not f.get('offline')] + [a['url'] for a in arch if not a.get('offline')]
print('files without offline copy:', len(no_off), no_off[:5])
blobs = 0
for mf in glob.glob(f'{S}/data/manifests/*.json'):
    for r in json.load(open(mf))['tree']:
        if r[2]:
            blobs += 1
            ex('docs/b/' + r[2]) or miss.append('docs/b/' + r[2])
for h in glob.glob(f'{S}/*.html'):
    for u in re.findall(r'(?:src|href)="([^"#?]+)"', open(h).read()):
        if not re.match(r'(https?:|mailto:|javascript:|\$\{|/|\./$)', u) and not ex(u): miss.append(f'{os.path.basename(h)} -> {u}')
files = [p for p in glob.glob(f'{S}/**', recursive=True) if os.path.isfile(p)]
big = [(p, os.path.getsize(p)) for p in files if os.path.getsize(p) > 25 * 1024 * 1024]
tot = sum(os.path.getsize(p) for p in files)
print(f'files: {len(files)} (CF limit 20000) total {tot/1e6:.0f} MB; >25MiB: {big}; manifest blob refs {blobs}; missing: {len(miss)}')
for x in miss[:30]: print('  MISSING', x)
sys.exit(1 if miss or big or len(files) > 20000 else 0)
