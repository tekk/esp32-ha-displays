#!/usr/bin/env python3
"""Enumerate the Guition GUITION-DISK file server (pan.jczn1688.com) and download
every file into the cache (sharded downloads, sha256 verified, resumable).

Usage: python3 build/fetch_pan.py [--list-only] [--only SUBSTR]
Output: data/raw/pan_files.json (full listing incl. shard manifests)
"""
import json, os, sys, hashlib, fnmatch, argparse, time
import concurrent.futures as cf
from urllib.parse import quote
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = json.load(open(os.path.join(ROOT, 'build', 'config.json')))
CACHE = os.path.normpath(os.path.join(ROOT, CFG['cache_dir']))
BASE = CFG['pan_base']
S = requests.Session()
S.headers['User-Agent'] = 'guition-catalog-builder/1.0'


def get_json(url, **kw):
    for i in range(5):
        try:
            r = S.get(url, timeout=60, **kw)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if i == 4:
                raise
            time.sleep(2 * (i + 1))


def walk(dir_id=None, path=''):
    d = get_json(BASE + '/api/browse', params={'dir_id': dir_id} if dir_id else {})
    out = []
    for f in d.get('files', []):
        f['dir'] = path.strip('/')
        out.append(f)
    for sd in d.get('directories', []):
        out += walk(sd['id'], path + '/' + sd['name'])
    return out


def included(f):
    return any(fnmatch.fnmatch(f['dir'], p) for p in CFG['pan_include_dirs'])


def directlink(f):
    return BASE + '/directlink/1/' + quote(f['path'])


def local_path(f):
    return os.path.join(CACHE, 'pan', f['path'])


def download(f):
    dst = local_path(f)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst) and os.path.getsize(dst) == f['size']:
        return f['path'], 'cached'
    man = f['manifest']
    tmp = dst + '.part'
    with open(tmp, 'wb') as out:
        for sh in sorted(man['shards'], key=lambda s: s['seq']):
            for attempt in range(6):
                try:
                    r = S.get(sh['url'], timeout=120)
                    r.raise_for_status()
                    data = r.content
                    if hashlib.sha256(data).hexdigest() != sh['sha256']:
                        raise ValueError('sha256 mismatch shard %d' % sh['seq'])
                    out.write(data)
                    break
                except Exception as e:
                    if attempt == 5:
                        raise
                    time.sleep(3 * (attempt + 1))
    if os.path.getsize(tmp) != f['size']:
        raise ValueError('size mismatch')
    os.replace(tmp, dst)
    return f['path'], 'downloaded'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--list-only', action='store_true')
    ap.add_argument('--only', default=None)
    a = ap.parse_args()
    files = walk()
    for f in files:
        f['directlink'] = directlink(f)
        try:
            f['manifest'] = get_json(BASE + '/api/manifest/' + quote(f['path']))
        except Exception as e:
            f['manifest'] = None
            f['error'] = 'manifest: %s' % e
    os.makedirs(os.path.join(ROOT, 'data', 'raw'), exist_ok=True)
    json.dump(files, open(os.path.join(ROOT, 'data', 'raw', 'pan_files.json'), 'w'), indent=1, ensure_ascii=False)
    print('listed', len(files), 'files,', sum(f['size'] for f in files) / 1e9, 'GB')
    if a.list_only:
        return
    todo = [f for f in files if included(f) and f.get('manifest') and (not a.only or a.only in f['path'])]
    status = {}
    with cf.ThreadPoolExecutor(CFG.get('download_workers', 4)) as ex:
        futs = {ex.submit(download, f): f for f in todo}
        for fu in cf.as_completed(futs):
            f = futs[fu]
            try:
                p, st = fu.result()
                status[p] = st
            except Exception as e:
                status[f['path']] = 'FAILED: %s' % e
            print(f"[{len(status)}/{len(todo)}] {f['path']}: {status[f['path']]}", flush=True)
    json.dump(status, open(os.path.join(ROOT, 'data', 'raw', 'download_status.json'), 'w'), indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()
