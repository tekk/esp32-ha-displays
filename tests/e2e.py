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
    res['last_column'] = pg.locator('table.grid thead th').last.inner_text().strip()
    res['header'] = [t.strip() for t in pg.locator('table.grid thead th').all_inner_texts()]
    res['feature_icons'] = pg.locator('table.grid td.feats .fi').count()
    res['value_badges'] = pg.locator('table.grid td.feats .fi .fv').count()
    res['sprite_ok'] = pg.evaluate("fetch('assets/img/features.svg').then(r=>r.ok)")
    shot(pg, '01-catalog.png')
    # tooltip on a feature pictogram (mouse) + keyboard focus
    fi = pg.locator('table.grid tbody tr').nth(20).locator('td.feats .fi').first
    fi.hover(); pg.wait_for_timeout(500)
    res['tooltip'] = pg.locator('#ftip.on').inner_text() if pg.locator('#ftip.on').count() else None
    shot(pg, '07-features-tooltip.png')
    pg.mouse.move(5, 5); pg.wait_for_timeout(200)
    pg.locator('table.grid tbody tr').nth(25).locator('td.feats .fi').nth(1).focus(); pg.wait_for_timeout(300)
    res['tooltip_focus'] = pg.locator('#ftip.on').count()
    pg.keyboard.press('Enter'); pg.wait_for_timeout(600)
    res['feature_filter_hash'] = pg.evaluate('location.hash')
    res['feature_filter_rows'] = pg.locator('table.grid tbody tr').count()
    pg.goto(BASE + 'index.html'); pg.wait_for_timeout(1200)
    # hover preview
    a = pg.locator('table.grid td.m a[data-pv]').nth(14)
    a.hover(); pg.wait_for_timeout(900)
    res['hover_visible'] = pg.locator('#boardpop.on').count()
    res['hover_title'] = pg.locator('#boardpop h3').inner_text() if res['hover_visible'] else None
    res['hover_ports'] = pg.locator('#boardpop ul.pfeat li').count()
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
    res['model_feature_cells'] = pg.locator('.fgrid .fcell').count()
    shot(pg, '04-model-JC1060P470C_I_W_Y.png', full_page=True)
    sec = pg.locator('.sec:has(.fgrid)')
    if sec.count():
        sec.screenshot(path=f'{SHOTS}/08-model-ports-grid-desktop.png') if SHOTS else None
    mp = ctx.new_page(); mp.set_viewport_size({'width': 390, 'height': 844})
    mid2 = [m['id'] for m in ms if m['model'] == 'ESP32-P4-WIFI6-Touch-LCD-7'][0]
    mp.goto(BASE + 'model.html?id=' + mid2); mp.wait_for_timeout(1500)
    sec = mp.locator('.sec:has(.fgrid)')
    res['mobile_grid_cols'] = mp.evaluate("getComputedStyle(document.querySelector('.fgrid')).gridTemplateColumns.split(' ').length")
    res['mobile_overflow'] = mp.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
    if sec.count() and SHOTS:
        sec.screenshot(path=f'{SHOTS}/09-model-ports-grid-mobile.png')
    mp.close()
    # new manufacturers: facet + a curated board (M5Stack Tab5) desktop + mobile
    pg.goto(BASE + 'index.html#f.vendor=M5Stack&view=table'); pg.wait_for_timeout(1200)
    res['vendor_m5_rows'] = pg.locator('table.grid tbody tr').count()
    res['vendors'] = sorted({m['vendor'] for m in ms})
    shot(pg, '10-catalog-manufacturer-M5Stack.png')
    mid3 = [m['id'] for m in ms if m['model'] == 'Tab5'][0]
    pg.goto(BASE + 'model.html?id=' + mid3); pg.wait_for_timeout(1500)
    res['tab5_feature_cells'] = pg.locator('.fgrid .fcell').count()
    res['tab5_has_thread'] = pg.locator('.fgrid .fcell:has-text("Thread")').count()
    shot(pg, '11-model-M5Stack-Tab5-desktop.png', full_page=True)
    mp = ctx.new_page(); mp.set_viewport_size({'width': 390, 'height': 844})
    mp.goto(BASE + 'model.html?id=' + mid3); mp.wait_for_timeout(1500)
    res['tab5_mobile_overflow'] = mp.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
    shot(mp, '13-model-M5Stack-Tab5-mobile.png')
    sec = mp.locator('.sec:has(.fgrid)')
    if sec.count() and SHOTS:
        sec.screenshot(path=f'{SHOTS}/12-model-M5Stack-Tab5-ports-mobile.png')
    mp.close()
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
ok = (not errors and not bad and not external and res.get('hover_visible') and res.get('fonts_loaded') and (res.get('last_column') or '').lower() == 'features'
      and res.get('feature_icons', 0) > 100 and res.get('tooltip') and res.get('model_feature_cells', 0) > 3 and res.get('value_badges', 0) > 50 and res.get('vendor_m5_rows', 0) >= 10 and res.get('tab5_has_thread') and not res.get('tab5_mobile_overflow') and not {'PSRAM', 'FILES'} & {h.upper() for h in res.get('header', [])})
sys.exit(0 if ok else 1)
