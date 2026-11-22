"""Download non-Guition-server documents so they are available offline:
 - every Waveshare / other http(s) file referenced in models.json that is not already local
 - snapshot ZIP (HEAD) of every GitHub repository listed in data/curated/mirror_repos.txt
Into <extra_dir>/waveshare and <extra_dir>/github. Resumable (skips existing non-empty files)."""
import json, os, subprocess, sys, concurrent.futures as cf
from urllib.parse import urlsplit, unquote
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = json.load(open(os.path.join(ROOT, 'build/config.json')))
EXTRA = os.path.normpath(os.path.join(ROOT, CFG['offline']['extra_dir']))

def curl(url, dst):
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        return dst, 'cached'
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    r = subprocess.run(['curl', '-sfL', '--retry', '3', '-o', dst + '.part', url])
    if r.returncode:
        return dst, 'FAILED %d' % r.returncode
    os.replace(dst + '.part', dst)
    return dst, 'ok'

def main():
    jobs = []
    models = json.load(open(os.path.join(ROOT, 'site/data/models.json')))
    for m in models:
        for f in m['files']:
            u = f['url']
            if 'pan.jczn1688.com' in u or 'guition.com' in u or f.get('hosted'):
                continue
            jobs.append((u, os.path.join(EXTRA, 'waveshare', unquote(urlsplit(u).path.rsplit('/', 1)[-1]))))
    for line in open(os.path.join(ROOT, 'data/curated/mirror_repos.txt')):
        r = line.strip()
        if r and not r.startswith('#'):
            jobs.append((f'https://codeload.github.com/{r}/zip/HEAD', os.path.join(EXTRA, 'github', r.replace('/', '__') + '.zip')))
    jobs = list(dict(jobs).items()) if False else list({d: (u, d) for u, d in jobs}.values())
    with cf.ThreadPoolExecutor(6) as ex:
        for dst, st in ex.map(lambda j: curl(*j), jobs):
            print(st, os.path.relpath(dst, EXTRA))

if __name__ == '__main__':
    main()
