#!/usr/bin/env python3
"""Read every cached archive from the Guition file server, build a manifest of its
complete file tree, and extract the browsable documentation (PDF, schematics, images,
markdown, text, code) into site/docs/b/ (content addressed, deduplicated) within the
size/file budgets from build/config.json.

Outputs:
  site/data/manifests/<slug>.json   per-archive file tree (+ hosted blob ids)
  site/docs/b/<id><ext>             hosted files
  site/files/archives/<name>        whole archives small enough to host (JSZip viewer)
  site/files/pan/<name>             loose (non-archive) files from the file server
  data/raw/archives.json            summary per archive
  data/raw/docs_text.json           extracted text for the full-text docs index
"""
import fnmatch, json, os, re, sys, io, zipfile, zlib, hashlib, shutil, subprocess, tempfile
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = json.load(open(os.path.join(ROOT, 'build', 'config.json')))
L = CFG['limits']
CACHE = os.path.normpath(os.environ.get('GUITION_CACHE') or os.path.join(ROOT, CFG['cache_dir']))
SITE = os.path.join(ROOT, CFG['site_dir'])
TMP = os.path.join(CACHE, 'tmp')
EXT_KIND = {}
for kind, exts in CFG['hosted_ext'].items():
    for e in exts:
        EXT_KIND[e.lower()] = kind
ARCH_EXT = ('.zip', '.rar', '.7z')
SKIP_RE = [re.compile(p, re.I) for p in CFG['skip_dir_patterns']]
PRIO_RE = re.compile('|'.join(CFG['priority_patterns']), re.I)
DOC_KINDS = {'pdf', 'image', 'markdown', 'text', 'html', 'office'}


def slugify(s):
    s = re.sub(r'[^A-Za-z0-9]+', '-', s).strip('-').lower()
    return s or hashlib.sha1(s.encode()).hexdigest()[:8]


def kind_of(path):
    return EXT_KIND.get(os.path.splitext(path)[1].lower(), 'other') if not path.lower().endswith(ARCH_EXT) else 'archive'


def fix_zip_name(zi):
    n = zi.filename
    if not (zi.flag_bits & 0x800):
        try:
            n = n.encode('cp437').decode('gbk')
        except Exception:
            try:
                n = n.encode('cp437').decode('utf-8')
            except Exception:
                pass
    return n.replace('\\', '/')


class Entry:
    __slots__ = ('path', 'size', 'crc', 'reader', 'kind', 'tier', 'blob', 'nested')

    def __init__(self, path, size, crc, reader):
        self.path, self.size, self.crc, self.reader = path, size, crc, reader
        self.kind = kind_of(path)
        self.tier = None
        self.blob = None
        self.nested = False


def open_source(path, tag):
    """Return list of Entry for an archive file on disk."""
    low = path.lower()
    out = []
    if low.endswith('.zip'):
        try:
            z = zipfile.ZipFile(path)
            for zi in z.infolist():
                if zi.is_dir():
                    continue
                out.append(Entry(fix_zip_name(zi), zi.file_size, zi.CRC, (lambda z=z, zi=zi: z.read(zi))))
            return out
        except Exception as e:
            print('  zipfile failed, falling back to 7z:', e)
    d = os.path.join(TMP, tag)
    if not os.path.isdir(d) or not os.listdir(d):
        os.makedirs(d, exist_ok=True)
        if low.endswith('.rar') and shutil.which('bsdtar'):
            # Debian's 7zip lacks the non-free RAR codec; libarchive (bsdtar) reads RAR4/RAR5
            r = subprocess.run(['bsdtar', '-xf', path, '-C', d], capture_output=True, text=True)
        else:
            r = subprocess.run(['7z', 'x', '-y', '-bd', '-o' + d, path], capture_output=True, text=True)
        if r.returncode != 0:
            print('  extract warning', path, r.stderr[-300:])
    for root, dirs, files in os.walk(d):
        for f in files:
            fp = os.path.join(root, f)
            rel = os.path.relpath(fp, d).replace('\\', '/')
            out.append(Entry(rel, os.path.getsize(fp), None, (lambda fp=fp: open(fp, 'rb').read())))
    return out


def crc_of(e):
    if e.crc is None:
        e.crc = zlib.crc32(e.reader()) & 0xffffffff
    return e.crc


def tier_of(e):
    p = e.path
    if any(r.search(p) for r in SKIP_RE):
        return None
    parts = p.split('/')
    sec = parts[1] if len(parts) > 2 else ''
    k = e.kind
    if re.match(r'^7-', sec) or k in ('other', 'archive'):
        return None
    if k in ('text', 'code') and e.size > (L['max_text_bytes'] if k == 'text' else L['max_code_bytes']):
        return None
    if e.size > L['max_file_bytes']:
        return None
    in_demo = bool(re.match(r'^1-', sec)) or re.search(r'(^|/)(demo|example|examples)(/|$)', p, re.I)
    if k in DOC_KINDS and not in_demo and (re.match(r'^[2-6]-', sec) or PRIO_RE.search(p) or len(parts) <= 2):
        return 0
    if k in DOC_KINDS and not in_demo:
        return 1
    if in_demo and (k in ('markdown', 'pdf', 'office') or (k == 'text' and re.search(r'readme|说明|\.txt$', p, re.I))):
        return 2
    if in_demo and k == 'code':
        return 3
    if in_demo and k in ('image', 'html', 'text'):
        return 4
    return None


def expand_nested(entries, depth, tag):
    if depth >= L['nested_depth']:
        return entries
    out = list(entries)
    for e in entries:
        if e.kind != 'archive' or e.size > L['nested_archive_max_bytes']:
            continue
        parts = e.path.split('/')
        sec = parts[1] if len(parts) > 2 else ''
        if re.match(r'^7-', sec) or any(r.search(e.path) for r in SKIP_RE) or re.search(r'librar', e.path, re.I):
            continue
        data = e.reader()
        h = hashlib.sha1(data).hexdigest()[:16]
        ext = os.path.splitext(e.path)[1].lower()
        fp = os.path.join(CACHE, 'nested', h + ext)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        if not os.path.exists(fp):
            open(fp, 'wb').write(data)
        try:
            inner = open_source(fp, 'n_' + h)
        except Exception as ex:
            print('  nested fail', e.path, ex)
            continue
        e.nested = True
        for ie in inner:
            ie.path = e.path + '/' + ie.path
        out += expand_nested(inner, depth + 1, tag)
    return out


def pdf_text(fp):
    try:
        r = subprocess.run(['pdftotext', '-l', str(L['pdf_text_pages']), '-enc', 'UTF-8', fp, '-'],
                           capture_output=True, timeout=60)
        return r.stdout.decode('utf-8', 'replace')
    except Exception:
        return ''


def main(only=None):
    """only=None: full rebuild from the local cache (all archives).
    only=[paths]: incremental mode (used by build/update.py on CI): process just these freshly downloaded
    files and merge the result into the existing data/raw/{archives,docs_text}.json + manifests."""
    pan = json.load(open(os.path.join(ROOT, 'data/raw/pan_files.json')))
    if only is not None:
        only = set(only)
        pan = [f for f in pan if f['path'] in only]
    os.makedirs(os.path.join(SITE, 'data/manifests'), exist_ok=True)
    os.makedirs(os.path.join(SITE, 'docs/b'), exist_ok=True)
    archives = []
    all_entries = []
    for f in pan:
        local = os.path.join(CACHE, 'pan', f['path'])
        slug = slugify(f['path'].rsplit('.', 1)[0])
        rec = {'slug': slug, 'name': f['name'], 'dir': f['dir'], 'path': f['path'], 'size': f['size'],
               'url': f['directlink'], 'created_at': f.get('created_at'), 'mime': f.get('mime'),
               'cached': os.path.exists(local) and os.path.getsize(local) == f['size']}
        archives.append(rec)
        if not rec['cached']:
            rec['error'] = 'not downloaded'
            continue
        if not f['name'].lower().endswith(ARCH_EXT):
            rec['type'] = 'file'
            if f['size'] <= L['max_file_bytes']:
                dst = os.path.join(SITE, 'files/pan', slug + os.path.splitext(f['name'])[1].lower())
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copyfile(local, dst)
                rec['hosted'] = os.path.relpath(dst, SITE)
                if f['name'].lower().endswith('.pdf'):
                    rec['_text'] = pdf_text(dst)
            continue
        rec['type'] = 'archive'
        print('reading', f['path'], flush=True)
        try:
            ents = open_source(local, slug)
            ents = expand_nested(ents, 0, slug)
        except Exception as ex:
            rec['error'] = 'read failed: %s' % ex
            continue
        for e in ents:
            e.tier = tier_of(e)
        rec['_entries'] = ents
        if f['name'].lower().endswith('.zip') and f['size'] <= L['host_archive_max_bytes']:
            dst = os.path.join(SITE, 'files/archives', slug + '.zip')
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(local, dst)
            rec['hosted_archive'] = os.path.relpath(dst, SITE)
        for e in ents:
            if e.tier is not None:
                all_entries.append((rec, e))
    # ---- selection: global greedy by tier, then priority, then size
    all_entries.sort(key=lambda t: (t[1].tier, 0 if PRIO_RE.search(t[1].path) else 1, t[1].size))
    per_bytes, per_files = {}, {}
    used_bytes, used_files = 0, 0
    if only is not None:                                  # budget already used by the untouched archives
        bdir = os.path.join(SITE, 'docs/b')
        used_bytes = sum(os.path.getsize(os.path.join(bdir, fn)) for fn in os.listdir(bdir))
        used_files = len(os.listdir(bdir))
        for r in json.load(open(os.path.join(ROOT, 'data/raw/archives.json'))):
            if r['path'] in only and r.get('stats'):
                used_bytes -= r['stats'].get('hosted_bytes', 0)
                used_files -= r['stats'].get('hosted_files', 0)
    selected = {}
    skipped_budget = 0
    for rec, e in all_entries:
        key = '%d-%08x' % (e.size, crc_of(e))
        if key in selected:
            e.blob = selected[key]
            continue
        s = rec['slug']
        maxf = L['per_archive_max_files']
        for pat, v in CFG.get('archive_overrides', {}).items():
            if fnmatch.fnmatch(rec['path'], pat):
                maxf = v.get('max_files', maxf)
        if (per_bytes.get(s, 0) + e.size > L['per_archive_hosted_bytes'] or per_files.get(s, 0) >= maxf
                or used_bytes + e.size > L['total_hosted_bytes'] or used_files >= L['max_hosted_files_total']):
            skipped_budget += 1
            continue
        blob = hashlib.sha1(key.encode()).hexdigest()[:16] + os.path.splitext(e.path)[1].lower()
        selected[key] = blob
        e.blob = blob
        per_bytes[s] = per_bytes.get(s, 0) + e.size
        per_files[s] = per_files.get(s, 0) + 1
        used_bytes += e.size
        used_files += 1
    print('selected blobs', len(selected), 'bytes', used_bytes, 'skipped (budget)', skipped_budget)
    # ---- extraction + text
    docs_text = []
    written = set()
    for rec in archives:
        ents = rec.pop('_entries', None)
        if ents is None:
            if rec.get('_text'):
                docs_text.append({'id': 'pan:' + rec['slug'], 'archive': rec['slug'], 'path': rec['name'],
                                  'blob': None, 'url': rec.get('hosted'), 'text': rec.pop('_text')[:L['text_index_chars_per_doc']]})
            continue
        tree = []
        stats = {'files': 0, 'bytes': 0, 'hosted_files': 0, 'hosted_bytes': 0}
        for e in ents:
            stats['files'] += 1
            stats['bytes'] += e.size
            if e.blob:
                dst = os.path.join(SITE, 'docs/b', e.blob)
                if e.blob not in written and not os.path.exists(dst):
                    open(dst, 'wb').write(e.reader())
                written.add(e.blob)
                stats['hosted_files'] += 1
                stats['hosted_bytes'] += e.size
                if e.tier is not None and ((e.tier == 0 and e.kind in ('pdf', 'markdown', 'html', 'text')) or
                                           (e.tier == 1 and e.kind in ('pdf', 'markdown')) or
                                           (e.tier == 2 and (e.kind == 'pdf' or re.search(r'readme[^/]*$', e.path, re.I)))):
                    if e.kind == 'pdf':
                        t = pdf_text(dst)
                    else:
                        raw = open(dst, 'rb').read(200000)
                        try:
                            t = raw.decode('utf-8')
                        except UnicodeDecodeError:
                            t = raw.decode('gbk', 'replace')
                        if e.kind == 'html':
                            t = re.sub(r'<[^>]+>', ' ', t)
                    t = re.sub(r'\s+', ' ', t).strip()
                    if t:
                        docs_text.append({'id': rec['slug'] + ':' + e.path, 'archive': rec['slug'], 'path': e.path,
                                          'blob': e.blob, 'tier': e.tier,
                                          'text': t[:L['text_index_chars_per_doc'] if e.tier == 0 else L['text_index_chars_other']]})
            tree.append([e.path, e.size, e.blob or 0, e.kind] + ([1] if e.nested else []))
        tree.sort(key=lambda r: r[0].lower())
        rec['stats'] = stats
        man = {k: v for k, v in rec.items()}
        man['tree'] = tree
        man['columns'] = ['path', 'size', 'blob', 'kind', 'nested_archive']
        mp = os.path.join(SITE, 'data/manifests', rec['slug'] + '.json')
        json.dump(man, open(mp, 'w'), ensure_ascii=False, separators=(',', ':'))
        rec['manifest'] = os.path.relpath(mp, SITE)
        print(f"  {rec['name']}: {stats['files']} files, hosted {stats['hosted_files']} ({stats['hosted_bytes']/1e6:.1f} MB)")
    if only is not None:
        old = json.load(open(os.path.join(ROOT, 'data/raw/archives.json')))
        new = {r['path']: r for r in archives}
        order = [r['path'] for r in json.load(open(os.path.join(ROOT, 'data/raw/pan_files.json')))]
        merged = {r['path']: r for r in old if r['path'] not in new}
        merged.update(new)
        archives = sorted(merged.values(), key=lambda r: order.index(r['path']) if r['path'] in order else 1e9)
        slugs = {r['slug'] for r in new.values()}
        docs_text = [d for d in json.load(open(os.path.join(ROOT, 'data/raw/docs_text.json'))) if d['archive'] not in slugs] + docs_text
        written = set()                                   # referenced = every blob named in any manifest on disk
        mdir = os.path.join(SITE, 'data/manifests')
        live = {r['slug'] for r in archives}
        for fn in os.listdir(mdir):
            if fn[:-5] not in live:
                os.remove(os.path.join(mdir, fn))
                continue
            for row in json.load(open(os.path.join(mdir, fn))).get('tree', []):
                if row[2]:
                    written.add(row[2])
    json.dump(archives, open(os.path.join(ROOT, 'data/raw/archives.json'), 'w'), indent=1, ensure_ascii=False)
    json.dump(docs_text, open(os.path.join(ROOT, 'data/raw/docs_text.json'), 'w'), ensure_ascii=False)
    # remove blobs no longer referenced
    for fn in os.listdir(os.path.join(SITE, 'docs/b')):
        if fn not in written:
            os.remove(os.path.join(SITE, 'docs/b', fn))
    print('docs text entries', len(docs_text))


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', nargs='+', help='incremental: process only these pan paths and merge')
    a = ap.parse_args()
    main(a.only)
