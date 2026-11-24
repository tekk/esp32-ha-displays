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
    # static SEO pages: board + vendor page, link into the SPA, legacy #model= links, sitemap/robots
    pg.goto(BASE + 'board/' + mid3 + '/'); pg.wait_for_timeout(800)
    res['seo_board_h1'] = pg.locator('h1').inner_text()
    res['seo_board_jsonld'] = pg.locator('script[type="application/ld+json"]').count()
    res['seo_board_canonical'] = pg.locator('link[rel=canonical]').get_attribute('href')
    res['seo_board_specs'] = pg.locator('table.sspec tbody tr').count()
    shot(pg, '14-seo-board-page-Tab5.png', full_page=True)
    pg.locator('a.btn.pri').first.click(); pg.wait_for_timeout(1500)
    res['seo_to_spa'] = pg.locator('.dinfo h1').inner_text() if pg.locator('.dinfo h1').count() else None
    pg.goto(BASE + 'vendor/m5stack/'); pg.wait_for_timeout(800)
    res['seo_vendor_cards'] = pg.locator('.vcard').count()
    shot(pg, '15-seo-vendor-page-M5Stack.png')
    pg.goto(BASE + 'index.html#model=' + mid3); pg.wait_for_timeout(1500)
    res['legacy_hash_redirect'] = 'model.html' in pg.url
    res['sitemap_ok'] = pg.evaluate("fetch('sitemap.xml').then(r=>r.text()).then(t=>t.includes('<urlset') && t.includes('/board/'))")
    res['robots_ok'] = pg.evaluate("fetch('robots.txt').then(r=>r.text()).then(t=>t.includes('Sitemap:'))")
    pg.goto(BASE + 'index.html'); pg.wait_for_timeout(1200)
    res['index_headers'] = pg.locator('body > header.topbar').count()
    res['index_footer_dir_links'] = pg.locator('footer .dir a').count()
    mp = ctx.new_page(); mp.set_viewport_size({'width': 390, 'height': 844})
    mp.goto(BASE + 'board/' + mid3 + '/'); mp.wait_for_timeout(800)
    res['seo_board_mobile_overflow'] = mp.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
    shot(mp, '16-seo-board-page-mobile.png')
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

    # ---------- Phase 8: mobile UX (hasTouch) ----------
    def overflows(page):
        return page.evaluate("""() => {
          const iw = window.innerWidth, sw = document.documentElement.scrollWidth;
          if (sw <= iw + 1) return false;
          let worst = null;
          for (const el of document.querySelectorAll('body *')) {
            const w = Math.max(el.getBoundingClientRect().width, el.scrollWidth);
            if (w > iw + 1 && (!worst || w > worst.w))
              worst = {w, tag: el.tagName, id: el.id, cls: String(el.className || '').slice(0, 80)};
          }
          return {sw, iw, worst};
        }""")

    def new_mobile(w, h):
        c = b.new_context(viewport={'width': w, 'height': h}, has_touch=True, is_mobile=True, service_workers='block')
        c.route('**/*', route)
        page = c.new_page()
        page.on('console', lambda m: m.type == 'error' and errors.append(f'{page.url}: {m.text}'))
        page.on('pageerror', lambda e: errors.append(f'{page.url}: PAGEERROR {e}'))
        page.on('response', lambda r: r.status >= 400 and bad.append(f'{r.status} {r.url}'))
        return c, page

    def check_view(page, key):
        ov = overflows(page)
        res[key] = ov
        return ov

    mctx, mp = new_mobile(390, 844)
    mp.goto(BASE + 'index.html'); mp.wait_for_timeout(1800)
    res['mobile_list_rows'] = mp.locator('.mlist .mrow').count()
    res['mobile_default_view'] = mp.evaluate("document.querySelector('#vlist') && document.querySelector('#vlist').classList.contains('on')")
    res['mobile_first_row_top'] = mp.evaluate("(() => { const r = document.querySelector('.mrow'); return r ? Math.round(r.getBoundingClientRect().top) : null; })()")
    res['mobile_dom_nodes'] = mp.evaluate("document.getElementsByTagName('*').length")
    res['mobile_facets_lazy'] = mp.evaluate("document.querySelectorAll('#facets .facet').length")
    res['mobile_hero_compact'] = mp.locator('.hero-compact').inner_text() if mp.locator('.hero-compact').count() else ''
    res['mobile_header_sticky'] = mp.evaluate("getComputedStyle(document.querySelector('.topbar')).position")
    res['mobile_footer_details_open'] = mp.locator('footer .dir > details[open]').count()
    res['mobile_footer_outer_details'] = mp.locator('footer .dir > details').count()
    res['mobile_footer_dir_links'] = mp.locator('footer .dir a').count()
    check_view(mp, 'mobile_ov_catalog_list')
    shot(mp, 'mobile-01-catalog.png')

    # Show more: 40 -> 80
    if mp.locator('#showmore').count():
        mp.locator('#showmore').tap(); mp.wait_for_timeout(400)
    res['mobile_list_rows_more'] = mp.locator('.mlist .mrow').count()

    # Taps must not open hover preview or tooltips (do not fire click – that follows the row link)
    mp.evaluate("""() => {
      const fi = document.querySelector('.mrow .fi');
      if (!fi) return;
      for (const typ of ['pointerover','pointerenter','pointerdown','pointerup'])
        fi.dispatchEvent(new PointerEvent(typ, {pointerType: 'touch', bubbles: true, cancelable: true, composed: true}));
      if (typeof fi.focus === 'function') try { fi.focus(); } catch (e) {}
    }""")
    mp.wait_for_timeout(400)
    res['mobile_tap_tooltip'] = mp.locator('#ftip.on').count()
    res['mobile_tap_hover'] = mp.locator('#boardpop.on').count()
    res['mobile_list_icon_clickable'] = mp.evaluate("!!document.querySelector('.mrow .fi.fclick')")
    # stay on the catalog for the filter-drawer checks
    if 'model.html' in mp.url or '/board/' in mp.url:
        mp.goto(BASE + 'index.html'); mp.wait_for_timeout(1200)

    # Filter drawer + badge + chip
    mp.locator('#fbtn').tap(); mp.wait_for_timeout(500)
    res['mobile_drawer_open'] = mp.evaluate("document.getElementById('filters').classList.contains('open')")
    res['mobile_facets_in_drawer'] = mp.locator('#facets .facet').count()
    check_view(mp, 'mobile_ov_filters_open')
    shot(mp, 'mobile-02-filters.png')
    # tick first vendor value
    box = mp.locator('#facets .facet[data-k=vendor] .fv label input[type=checkbox]').first
    if box.count():
        box.tap(); mp.wait_for_timeout(500)
    res['mobile_badge'] = mp.locator('#fbadge').inner_text().strip() if not mp.locator('#fbadge').get_attribute('hidden') else ''
    if mp.locator('#fapply').count():
        mp.locator('#fapply').tap(); mp.wait_for_timeout(400)
    res['mobile_chip'] = mp.locator('#achips .chip').count()
    res['mobile_drawer_closed'] = mp.evaluate("!document.getElementById('filters').classList.contains('open')")
    check_view(mp, 'mobile_ov_catalog_filtered')

    # Table + cards views must not overflow the page
    if mp.locator('#vtable').count():
        mp.locator('#vtable').tap(); mp.wait_for_timeout(500)
    check_view(mp, 'mobile_ov_catalog_table')
    res['mobile_table_in_wrap'] = mp.evaluate("""() => {
      const w = document.querySelector('.tblwrap');
      if (!w) return false;
      const iw = window.innerWidth;
      return w.getBoundingClientRect().width <= iw + 1 && document.documentElement.scrollWidth <= iw + 1;
    }""")
    # tooltip on tap in table view
    if mp.locator('table.grid td.feats .fi').count():
        mp.evaluate("""() => {
          const fi = document.querySelector('table.grid td.feats .fi');
          if (!fi) return;
          for (const typ of ['pointerover','pointerdown','pointerup'])
            fi.dispatchEvent(new PointerEvent(typ, {pointerType: 'touch', bubbles: true, cancelable: true, composed: true}));
        }""")
        mp.wait_for_timeout(300)
        res['mobile_table_tap_tooltip'] = mp.locator('#ftip.on').count()
    if mp.locator('#vcards').count():
        mp.locator('#vcards').tap(); mp.wait_for_timeout(500)
    check_view(mp, 'mobile_ov_catalog_cards')

    # SPA board detail
    mp.goto(BASE + 'model.html?id=' + mid3); mp.wait_for_timeout(1500)
    check_view(mp, 'mobile_ov_board_detail')
    res['mobile_detail_title_first'] = mp.evaluate("""() => {
      const h = document.querySelector('.dinfo h1, .dhead h1');
      const g = document.querySelector('.gallery .main');
      if (!h || !g) return null;
      return h.getBoundingClientRect().top <= g.getBoundingClientRect().top + 1;
    }""")
    shot(mp, 'mobile-03-board-detail.png')

    # Static SEO board page at 390 and 360
    mp.goto(BASE + 'board/' + mid3 + '/'); mp.wait_for_timeout(800)
    check_view(mp, 'mobile_ov_static_board_390')
    res['mobile_static_cta_wrap'] = mp.evaluate("""() => {
      const a = document.querySelector('.seo .cta .btn, .seo a.btn.pri');
      if (!a) return false;
      const r = a.getBoundingClientRect();
      return r.width <= window.innerWidth + 1 && getComputedStyle(a).whiteSpace !== 'nowrap';
    }""")
    shot(mp, 'mobile-04-static-board.png')
    mp.set_viewport_size({'width': 360, 'height': 800})
    mp.wait_for_timeout(300)
    check_view(mp, 'mobile_ov_static_board_360')

    # Manufacturer page
    mp.set_viewport_size({'width': 390, 'height': 844})
    mp.goto(BASE + 'vendor/m5stack/'); mp.wait_for_timeout(800)
    check_view(mp, 'mobile_ov_vendor')
    res['mobile_vendor_thumb_h'] = mp.evaluate("(() => { const i = document.querySelector('.vcard img'); return i ? Math.round(i.getBoundingClientRect().height) : null; })()")

    # Files, docs, viewer, about — plus a second phone size
    mp.goto(BASE + 'files.html'); mp.wait_for_timeout(1500)
    check_view(mp, 'mobile_ov_files')
    res['mobile_files_stacked'] = mp.evaluate("getComputedStyle(document.querySelector('table.grid.stack thead') || document.createElement('x')).display === 'none'")

    mp.goto(BASE + 'docs.html#q=GT911'); mp.wait_for_timeout(5000)
    check_view(mp, 'mobile_ov_docs')
    if mp.locator('#arch').count():
        # opening the native select can't be fully simulated; ensure the control itself fits
        res['mobile_arch_select_fits'] = mp.evaluate("document.getElementById('arch').getBoundingClientRect().width <= window.innerWidth + 1")

    mp.goto(BASE + 'viewer.html?a=hmi-display-jc4880p443c-i-w'); mp.wait_for_timeout(3000)
    check_view(mp, 'mobile_ov_viewer')

    mp.goto(BASE + 'about.html'); mp.wait_for_timeout(800)
    check_view(mp, 'mobile_ov_about')
    mctx.close()

    # 375×812 catalog overflow (iPhone-ish)
    c2, p2 = new_mobile(375, 812)
    p2.goto(BASE + 'index.html'); p2.wait_for_timeout(1500)
    check_view(p2, 'mobile_ov_catalog_375')
    p2.goto(BASE + 'board/' + mid3 + '/'); p2.wait_for_timeout(600)
    check_view(p2, 'mobile_ov_static_board_375')
    p2.goto(BASE + 'files.html'); p2.wait_for_timeout(1200)
    check_view(p2, 'mobile_ov_files_375')
    c2.close()

    b.close()
print(json.dumps(res, indent=1, ensure_ascii=False))
print('console errors:', len(errors)); [print(' ', e) for e in errors[:20]]
print('bad responses:', len(bad)); [print(' ', e) for e in bad[:20]]
print('blocked external requests:', len(external)); [print(' ', e) for e in external[:20]]
ov_keys = [k for k in res if k.startswith('mobile_ov_')]
ov_fail = [k for k in ov_keys if res.get(k)]
ok = (not errors and not bad and not external and res.get('hover_visible') and res.get('fonts_loaded') and (res.get('last_column') or '').lower() == 'features'
      and res.get('feature_icons', 0) > 100 and res.get('tooltip') and res.get('model_feature_cells', 0) > 3 and res.get('value_badges', 0) > 50 and res.get('vendor_m5_rows', 0) >= 10 and res.get('tab5_has_thread') and res.get('seo_board_jsonld', 0) >= 2 and res.get('seo_to_spa') and res.get('legacy_hash_redirect') and res.get('sitemap_ok') and res.get('robots_ok') and res.get('index_headers') == 1 and res.get('seo_vendor_cards', 0) >= 10 and not res.get('seo_board_mobile_overflow') and not res.get('tab5_mobile_overflow') and not {'PSRAM', 'FILES'} & {h.upper() for h in res.get('header', [])}
      and res.get('mobile_list_rows') == 40 and res.get('mobile_list_rows_more') == 80 and res.get('mobile_default_view')
      and not res.get('mobile_tap_tooltip') and not res.get('mobile_tap_hover') and not res.get('mobile_table_tap_tooltip')
      and not res.get('mobile_list_icon_clickable') and res.get('mobile_drawer_open') and res.get('mobile_facets_in_drawer', 0) >= 5
      and res.get('mobile_facets_lazy') == 0 and res.get('mobile_chip', 0) >= 1 and res.get('mobile_badge')
      and res.get('mobile_footer_outer_details') == 1 and res.get('mobile_footer_details_open') == 0 and res.get('mobile_footer_dir_links') == 280
      and res.get('mobile_header_sticky') == 'static' and (res.get('mobile_first_row_top') or 999) <= 420
      and res.get('mobile_table_in_wrap') and res.get('mobile_files_stacked')
      and not ov_fail)
if ov_fail:
    print('horizontal overflow:', {k: res[k] for k in ov_fail})
sys.exit(0 if ok else 1)
