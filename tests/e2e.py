"""Headless browser test + screenshots, with ALL non-local network requests blocked.
Usage: python3 tests/e2e.py [base_url] [--no-shots]   (serve site/ first: python3 -m http.server -d site 8765)"""
import sys, json, os
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
BASE = next((a for a in sys.argv[1:] if a.startswith('http')), 'http://localhost:8765/')
SHOTS = None if '--no-shots' in sys.argv else os.path.join(os.path.dirname(__file__), '..', 'screenshots')
HOST = urlsplit(BASE).netloc
errors, bad, external = [], [], []
res = {}
def shot(pg, name, **kw):
    if SHOTS: pg.screenshot(path=f'{SHOTS}/{name}', **kw)
with sync_playwright() as p:
    b = p.chromium.launch(channel='chrome', headless=True)
    ctx = b.new_context(viewport={'width': 1500, 'height': 950}, service_workers='block')
    def route(r):
        h = urlsplit(r.request.url)
        if h.scheme in ('data', 'blob') or h.netloc == HOST:
            return r.continue_()
        external.append(r.request.url); r.abort()
    ctx.route('**/*', route)
    pg = ctx.new_page()
    pg.on('console', lambda m: m.type == 'error' and errors.append(f'{pg.url}: {m.text}'))
    pg.on('pageerror', lambda e: errors.append(f'{pg.url}: PAGEERROR {e}'))
    pg.on('response', lambda r: r.status >= 400 and bad.append(f'{r.status} {r.url}'))
    pg.goto(BASE + 'index.html'); pg.wait_for_timeout(1500)
    res['fonts_loaded'] = pg.evaluate("document.fonts.check('14px Montserrat') && document.fonts.check('14px \"Roboto Condensed\"') && document.fonts.check('14px \"JetBrains Mono\"')")
    res['catalog_rows'] = pg.locator('table.grid tbody tr').count()
    shot(pg, '01-catalog.png')
    # hover preview
    a = pg.locator('table.grid td.m a[data-pv]').nth(14)
    a.hover(); pg.wait_for_timeout(900)
    res['hover_visible'] = pg.locator('#boardpop.on').count()
    res['hover_title'] = pg.locator('#boardpop h3').inner_text() if res['hover_visible'] else None
    res['hover_ports'] = pg.locator('#boardpop ul.ports li').count()
    shot(pg, '02-hover-preview.png')
    pg.mouse.move(5, 5); pg.wait_for_timeout(300)
    res['hover_hidden_after'] = pg.locator('#boardpop.on').count() == 0
    # keyboard focus preview
    pg.locator('table.grid td.m a[data-pv]').nth(3).focus(); pg.wait_for_timeout(500)
    res['focus_preview'] = pg.locator('#boardpop.on').count()
    pg.keyboard.press('Escape')
    pg.fill('#q', 'mcu:esp32-p4'); pg.wait_for_timeout(700)
    res['p4_rows'] = pg.locator('table.grid tbody tr').count()
    pg.fill('#q', 'JC4880'); pg.wait_for_timeout(700)
    res['search_JC4880'] = pg.locator('table.grid tbody tr').count()
    pg.goto(BASE + 'index.html#f.touch=Capacitive&f.size=7%22&view=cards'); pg.wait_for_timeout(1200)
    res['facet_cards'] = pg.locator('.card').count()
    shot(pg, '03-catalog-cards-filtered.png')
    ms = json.loads(pg.evaluate("fetch('data/models.json').then(r=>r.text())"))
    mid = [m['id'] for m in ms if m['model'] == 'JC1060P470C_I_W_Y'][0]
    pg.goto(BASE + 'model.html?id=' + mid); pg.wait_for_timeout(1500)
    res['model_h1'] = pg.locator('.dinfo h1').inner_text()
    res['model_files'] = pg.locator('.filelist .f').count()
    shot(pg, '04-model-JC1060P470C_I_W_Y.png', full_page=True)
    pg.goto(BASE + 'viewer.html?a=hmi-display-jc4880p443c-i-w'); pg.wait_for_timeout(3000)
    res['viewer_tree_nodes'] = pg.locator('#tree .n').count()
    shot(pg, '05-viewer-JC4880P443C_I_W.png')
    pg.fill('#tfilter', r'README\.md$'); pg.wait_for_timeout(500)
    md = pg.locator('#tree .n[data-path]')
    if md.count():
        md.first.click(); pg.wait_for_timeout(1500); res['viewer_md'] = pg.locator('.md-body').count()
    pg.fill('#tfilter', r'\.(c|h|ino)$'); pg.wait_for_timeout(500)
    cd = pg.locator('#tree .n[data-path]')
    if cd.count():
        cd.first.click(); pg.wait_for_timeout(1500); res['viewer_code_spans'] = pg.locator('pre.code span').count()
    pg.goto(BASE + 'docs.html#q=GT911'); pg.wait_for_timeout(5000)
    res['docs_hits'] = pg.locator('.docres').count()
    shot(pg, '06-docs-search.png')
    pg.goto(BASE + 'files.html'); pg.wait_for_timeout(1500)
    res['files_rows'] = pg.locator('table.grid tbody tr').count()
    pg.goto(BASE + 'about.html'); pg.wait_for_timeout(800)
    res['about'] = pg.locator('.sec').count()
    b.close()
print(json.dumps(res, indent=1, ensure_ascii=False))
print('console errors:', len(errors)); [print(' ', e) for e in errors[:20]]
print('bad responses:', len(bad)); [print(' ', e) for e in bad[:20]]
print('blocked external requests:', len(external)); [print(' ', e) for e in external[:20]]
ok = not errors and not bad and not external and res.get('hover_visible') and res.get('fonts_loaded')
sys.exit(0 if ok else 1)
