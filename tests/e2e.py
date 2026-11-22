"""Headless smoke test + screenshots. Usage: python3 tests/e2e.py [base_url]  (serve site/ first)"""
import sys, json, os
from playwright.sync_api import sync_playwright
BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8765/'
SHOTS = os.path.join(os.path.dirname(__file__), '..', 'screenshots')
errors, bad = [], []
res = {}
with sync_playwright() as p:
    b = p.chromium.launch(channel='chrome', headless=True)
    pg = b.new_page(viewport={'width': 1500, 'height': 950})
    pg.on('console', lambda m: m.type == 'error' and errors.append(f'{pg.url}: {m.text}'))
    pg.on('pageerror', lambda e: errors.append(f'{pg.url}: PAGEERROR {e}'))
    pg.on('response', lambda r: r.status >= 400 and bad.append(f'{r.status} {r.url}'))
    pg.goto(BASE + 'index.html'); pg.wait_for_timeout(1500)
    res['catalog_rows'] = pg.locator('table.grid tbody tr').count()
    pg.screenshot(path=f'{SHOTS}/01-catalog.png')
    pg.fill('#q', 'mcu:esp32-p4'); pg.wait_for_timeout(700)
    res['p4_rows'] = pg.locator('table.grid tbody tr').count()
    pg.fill('#q', 'JC4880'); pg.wait_for_timeout(700)
    res['search_JC4880'] = pg.locator('table.grid tbody tr').count()
    pg.goto(BASE + 'index.html#f.touch=Capacitive&f.size=7%22&view=cards'); pg.wait_for_timeout(1200)
    res['facet_cards'] = pg.locator('.card').count()
    pg.screenshot(path=f'{SHOTS}/02-catalog-cards-filtered.png')
    pg.goto(BASE + 'model.html?id=jc1060p470c-i-w-y'); pg.wait_for_timeout(1500)
    if pg.locator('.dinfo h1').count() == 0:
        ms = json.loads(pg.evaluate("fetch('data/models.json').then(r=>r.text())"))
        mid = [m['id'] for m in ms if m['model'] == 'JC1060P470C_I_W_Y'][0]
        pg.goto(BASE + 'model.html?id=' + mid); pg.wait_for_timeout(1500)
    res['model_h1'] = pg.locator('.dinfo h1').inner_text()
    res['model_files'] = pg.locator('.filelist .f').count()
    pg.screenshot(path=f'{SHOTS}/03-model-JC1060P470C_I_W_Y.png', full_page=True)
    pg.goto(BASE + 'viewer.html?a=hmi-display-jc4880p443c-i-w'); pg.wait_for_timeout(3000)
    res['viewer_tree_nodes'] = pg.locator('#tree .n').count()
    res['viewer_body'] = pg.locator('#vbody').inner_html()[:80]
    pg.screenshot(path=f'{SHOTS}/04-viewer-JC4880P443C_I_W.png')
    pg.fill('#tfilter', r'\.md$'); pg.wait_for_timeout(500)
    md = pg.locator('#tree .n[data-path]')
    if md.count():
        md.first.click(); pg.wait_for_timeout(1500); res['viewer_md'] = pg.locator('.md-body').count()
    pg.fill('#tfilter', r'\.(c|h|ino)$'); pg.wait_for_timeout(500)
    cd = pg.locator('#tree .n[data-path]')
    if cd.count():
        cd.first.click(); pg.wait_for_timeout(1500); res['viewer_code_hljs'] = pg.locator('pre.code .hljs-keyword, pre.code span').count()
    pg.screenshot(path=f'{SHOTS}/05-viewer-code.png')
    pg.goto(BASE + 'docs.html#q=GT911'); pg.wait_for_timeout(5000)
    res['docs_hits'] = pg.locator('.docres').count()
    pg.screenshot(path=f'{SHOTS}/06-docs-search.png')
    pg.goto(BASE + 'files.html'); pg.wait_for_timeout(1500)
    res['files_rows'] = pg.locator('table.grid tbody tr').count()
    pg.goto(BASE + 'about.html'); pg.wait_for_timeout(800)
    res['about'] = pg.locator('.sec').count()
    b.close()
print(json.dumps(res, indent=1, ensure_ascii=False))
print('console errors:', len(errors)); [print(' ', e) for e in errors[:20]]
print('bad responses:', len(bad)); [print(' ', e) for e in bad[:20]]
sys.exit(1 if errors or bad else 0)
